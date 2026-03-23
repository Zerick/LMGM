"""Deterministic GURPS combat resolution pipeline.

Every function in this module is pure Python (except for dice randomness).
The LLM never computes damage or checks success — it calls these functions
and narrates the results.

Attack resolution follows the 7-step pipeline from the blueprint (Section 3.2):
  1. Attack roll (success_check against effective skill)
  2. Defense roll (dodge / parry / block against defender's scores)
  3. Hit location (roll or declared target)
  4. Damage roll (weapon dice)
  5. Apply DR (subtract armour, add location extra DR)
  6. Calculate injury (penetrating × wound multiplier, round down)
  7. Wound effects (knockdown, stun, death checks, conditions)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from engine.dice import CheckResult, success_check
from engine.tables import (
    HIT_LOCATION_TABLE,
    get_hit_location,
    roll_hit_location as _roll_loc,
)


# ---------------------------------------------------------------------------
# Enums and constants
# ---------------------------------------------------------------------------


class DamageType(str, Enum):
    """GURPS damage type abbreviations."""
    CRUSHING = "cr"
    CUTTING = "cut"
    IMPALING = "imp"
    PIERCING = "pi"
    SMALL_PIERCING = "pi-"
    LARGE_PIERCING = "pi+"
    HUGE_PIERCING = "pi++"
    BURNING = "burn"
    CORROSIVE = "cor"
    TOXIC = "tox"
    FATIGUE = "fat"


# Standard wound multipliers by damage type (GURPS Lite p.29 / B379)
_WOUND_MULTIPLIERS: dict[DamageType, float] = {
    DamageType.CRUSHING: 1.0,
    DamageType.CUTTING: 1.5,
    DamageType.IMPALING: 2.0,
    DamageType.PIERCING: 1.0,
    DamageType.SMALL_PIERCING: 0.5,
    DamageType.LARGE_PIERCING: 1.5,
    DamageType.HUGE_PIERCING: 2.0,
    DamageType.BURNING: 1.0,
    DamageType.CORROSIVE: 1.0,
    DamageType.TOXIC: 1.0,
    DamageType.FATIGUE: 1.0,
}

# Locations that use a wound multiplier override (B553)
# skull: ×4 for everything except tox
_SKULL_OVERRIDE_MULTIPLIER = 4.0
_SKULL_EXEMPT_TYPES = {DamageType.TOXIC}

# Limb crippling threshold: injury ≥ HP/2 (arm, leg)
# Extremity crippling threshold: injury ≥ HP/3 (hand, foot)
_LIMB_LOCATIONS = {"right arm", "left arm", "right leg", "left leg"}
_EXTREMITY_LOCATIONS = {"hand", "foot"}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Weapon:
    """Weapon statistics needed for damage computation."""

    name: str
    damage_dice: str        # e.g. '2d6', '1d', '2d+1'
    damage_bonus: int       # flat bonus added to damage roll (may be negative)
    damage_type: DamageType
    min_st: int = 0         # minimum ST to wield without penalty


@dataclass
class Modifier:
    """A named situational modifier applied to a roll."""

    name: str
    value: int   # positive = bonus, negative = penalty


@dataclass
class Maneuver:
    """Mechanical effects of a combat maneuver."""

    name: str
    attack_modifier: int = 0       # added to effective skill for attack roll
    damage_bonus: int = 0          # flat bonus added to damage (AoA Strong)
    allows_defense: bool = True    # False for All-Out Attack variants
    max_effective_skill: int = 99  # cap on effective skill (Move and Attack = 9)
    dodge_bonus: int = 0           # bonus to defender's Dodge (AoA Defense Dodge)
    defense_penalty: int = 0       # penalty subtracted from all defenses (not used currently)


@dataclass
class AttackAction:
    """Complete description of a single attack attempt."""

    attacker_id: str
    target_id: str
    weapon: Weapon
    maneuver: str                    # key into MANEUVER_REGISTRY
    target_location: str             # 'torso', 'skull', 'random', etc.
    modifiers: list[Modifier] = field(default_factory=list)


@dataclass
class DefenseResult:
    """Result of a defense roll attempt."""

    roll: int
    target: int                  # effective defense score used
    margin: int
    success: bool
    defense_type: str            # 'dodge', 'parry', 'block', or 'none'
    target_description: str = ""


@dataclass
class CombatResult:
    """Complete result of one attack-defense-damage sequence."""

    attack_roll: CheckResult
    defense_roll: Optional[DefenseResult]
    defense_type: Optional[str]
    hit_location: str
    raw_damage: int
    dr: int
    penetrating_damage: int
    wound_multiplier: float
    injury: int
    effects: list[str]           # e.g. ['knockdown_check', 'death_check']


# ---------------------------------------------------------------------------
# Maneuver registry
# ---------------------------------------------------------------------------


MANEUVER_REGISTRY: dict[str, Maneuver] = {
    "attack": Maneuver(
        name="attack",
        attack_modifier=0,
        allows_defense=True,
    ),
    "all_out_attack_determined": Maneuver(
        name="all_out_attack_determined",
        attack_modifier=4,
        allows_defense=False,
    ),
    "all_out_attack_strong": Maneuver(
        name="all_out_attack_strong",
        attack_modifier=0,
        damage_bonus=2,           # +2 to damage (or +1/die; +2 flat used here)
        allows_defense=False,
    ),
    "all_out_attack_double": Maneuver(
        name="all_out_attack_double",
        attack_modifier=0,
        allows_defense=False,
    ),
    "all_out_defense_dodge": Maneuver(
        name="all_out_defense_dodge",
        attack_modifier=0,        # cannot attack
        allows_defense=True,
        dodge_bonus=2,
    ),
    "all_out_defense_increased": Maneuver(
        name="all_out_defense_increased",
        attack_modifier=0,
        allows_defense=True,
        dodge_bonus=2,            # +2 to one chosen active defense
    ),
    "deceptive_attack": Maneuver(
        name="deceptive_attack",
        attack_modifier=0,        # attacker chooses own penalty via modifiers
        allows_defense=True,
    ),
    "move_and_attack": Maneuver(
        name="move_and_attack",
        attack_modifier=-4,
        allows_defense=True,
        max_effective_skill=9,
    ),
    "wait": Maneuver(
        name="wait",
        attack_modifier=0,
        allows_defense=True,
    ),
    "feint": Maneuver(
        name="feint",
        attack_modifier=0,
        allows_defense=True,
    ),
}


# ---------------------------------------------------------------------------
# Wound multiplier logic
# ---------------------------------------------------------------------------


def get_wound_multiplier(damage_type: DamageType, location: str) -> float:
    """Return the wound multiplier for a damage type hitting a given location.

    Skull uses ×4 for all types except toxic (B553).
    All other locations use the standard type-based multiplier.

    Args:
        damage_type: Type of damage (cut, imp, cr, etc.).
        location: Hit location string (lowercase).

    Returns:
        Float wound multiplier.
    """
    if location == "skull" and damage_type not in _SKULL_EXEMPT_TYPES:
        return _SKULL_OVERRIDE_MULTIPLIER
    return _WOUND_MULTIPLIERS.get(damage_type, 1.0)


def apply_damage_minimum(raw: int, damage_type: DamageType) -> int:
    """Enforce GURPS damage minimums (GURPS Lite p.29 / B379).

    - Crushing damage: minimum 0 (can be completely absorbed).
    - All other types: minimum 1 (once any damage penetrates DR).

    This function applies minimums to raw damage values (before DR).
    For penetrating minimums, see calculate_injury.

    Args:
        raw: Raw damage total (may be negative due to negative adds).
        damage_type: Type of damage.

    Returns:
        Damage after minimum enforcement.
    """
    if damage_type == DamageType.CRUSHING:
        return max(0, raw)
    return max(1, raw)


# ---------------------------------------------------------------------------
# Step 1 — Attack roll
# ---------------------------------------------------------------------------


def attack_roll(
    skill: int,
    modifier: int = 0,
    maneuver: str = "attack",
    _force_roll: Optional[int] = None,
) -> CheckResult:
    """Resolve an attack roll against effective skill.

    Applies the maneuver's attack_modifier automatically.
    Additional situational modifiers (range, posture, etc.) should be
    summed by the caller and passed as modifier.

    Args:
        skill: Base weapon skill of the attacker.
        modifier: Sum of all situational bonuses/penalties.
        maneuver: Maneuver name (looked up in MANEUVER_REGISTRY).
        _force_roll: Testing parameter.

    Returns:
        CheckResult with roll, target (effective skill), margin, and critical info.
    """
    reg = MANEUVER_REGISTRY.get(maneuver, MANEUVER_REGISTRY["attack"])
    effective_skill = skill + modifier + reg.attack_modifier
    effective_skill = min(effective_skill, reg.max_effective_skill)
    return success_check(effective_skill, _force_roll=_force_roll)


# ---------------------------------------------------------------------------
# Step 2 — Defense roll
# ---------------------------------------------------------------------------


def defense_roll(
    dodge: Optional[int] = None,
    parry: Optional[int] = None,
    block: Optional[int] = None,
    stunned: bool = False,
    attacker_maneuver: str = "attack",
    deceptive_penalty: int = 0,
    _force_roll: Optional[int] = None,
) -> DefenseResult:
    """Resolve a defender's active defense roll.

    The defender uses the first non-None defense value provided, in the
    order: dodge → parry → block. If the attacker used an All-Out Attack,
    no defense is allowed.

    Args:
        dodge: Defender's Dodge score (None if not using).
        parry: Defender's Parry score (None if not using).
        block: Defender's Block score (None if not using).
        stunned: True if the defender is currently stunned (-4 to defenses).
        attacker_maneuver: The maneuver the attacker used.
        deceptive_penalty: Penalty applied to the defense from a Deceptive Attack.
            Per the rules, this is floor(skill_penalty / 2) subtracted from defense.
        _force_roll: Testing parameter.

    Returns:
        DefenseResult with roll, effective defense, success, and type.

    Raises:
        ValueError: If no defense values are provided.
    """
    # Check whether the attacker's maneuver prevents active defense
    reg = MANEUVER_REGISTRY.get(attacker_maneuver, MANEUVER_REGISTRY["attack"])
    if not reg.allows_defense:
        return DefenseResult(
            roll=0,
            target=0,
            margin=-99,
            success=False,
            defense_type="none",
            target_description="no defense — attacker used all-out attack",
        )

    # Select defense type
    if dodge is not None:
        defense_score = dodge
        defense_type = "dodge"
    elif parry is not None:
        defense_score = parry
        defense_type = "parry"
    elif block is not None:
        defense_score = block
        defense_type = "block"
    else:
        raise ValueError("At least one of dodge, parry, or block must be provided.")

    # Apply penalties
    penalties = 0
    if stunned:
        penalties -= 4
    penalties -= deceptive_penalty

    effective_defense = defense_score + penalties

    result = success_check(effective_defense, _force_roll=_force_roll)

    return DefenseResult(
        roll=result.roll,
        target=effective_defense,
        margin=result.margin,
        success=result.success,
        defense_type=defense_type,
    )


# ---------------------------------------------------------------------------
# Step 3 — Hit location
# ---------------------------------------------------------------------------


def hit_location_roll(
    declared_location: Optional[str] = None,
    _force_roll: Optional[int] = None,
) -> str:
    """Determine the hit location.

    If the attacker declared a specific target location, that is returned.
    Otherwise, roll 3d6 on the humanoid hit location table.

    Args:
        declared_location: Pre-declared target (e.g. 'skull', 'face'). If
            provided, no dice are rolled.
        _force_roll: Testing parameter — forces the 3d6 location roll result.

    Returns:
        Location string (lowercase), e.g. 'torso', 'skull', 'right arm'.
    """
    if declared_location:
        return declared_location.lower()

    if _force_roll is not None:
        return get_hit_location(_force_roll).location

    return _roll_loc().location


# ---------------------------------------------------------------------------
# Step 5 — Apply DR
# ---------------------------------------------------------------------------


def apply_dr(
    raw_damage: int,
    dr: int,
    location: str = "torso",
) -> int:
    """Subtract armour DR (plus any location extra DR) from raw damage.

    Returns the penetrating damage (0 if armour absorbs all damage).

    Args:
        raw_damage: Basic damage before DR.
        dr: Armour DR at the struck location.
        location: Hit location string (used to add extra DR for skull).

    Returns:
        Penetrating damage (non-negative integer).
    """
    loc_entry = None
    # Look up extra DR for the location
    for roll_val, entry in HIT_LOCATION_TABLE.items():
        if entry.location == location.lower():
            loc_entry = entry
            break

    extra_dr = loc_entry.extra_dr if loc_entry else 0
    total_dr = dr + extra_dr
    penetrating = max(0, raw_damage - total_dr)
    return penetrating


# ---------------------------------------------------------------------------
# Step 6 — Calculate injury
# ---------------------------------------------------------------------------


def calculate_injury(
    penetrating: int,
    damage_type: DamageType,
    location: str = "torso",
    target_hp: Optional[int] = None,
    return_cripple: bool = False,
) -> int | tuple[int, bool]:
    """Apply wound multiplier to penetrating damage to get injury (HP lost).

    Fractions are rounded down, but minimum injury is 1 if any damage
    penetrated (except for crushing damage which can be 0).

    For limb/extremity locations, excess damage beyond the crippling
    threshold is lost and crippling is flagged when return_cripple=True.

    Args:
        penetrating: Penetrating damage (after DR).
        damage_type: Type of damage.
        location: Hit location string.
        target_hp: Target's full HP (required when return_cripple=True).
        return_cripple: If True, return (injury, crippled) tuple.

    Returns:
        injury (int) or (injury, crippled) tuple when return_cripple=True.
    """
    if penetrating == 0:
        if return_cripple:
            return 0, False
        return 0

    multiplier = get_wound_multiplier(damage_type, location.lower())
    raw_injury = int(penetrating * multiplier)  # floor

    # Enforce minimum 1 for any damage type except crushing
    if damage_type != DamageType.CRUSHING and raw_injury < 1:
        raw_injury = 1

    # Limb/extremity crippling — excess damage lost (B421)
    crippled = False
    loc_lower = location.lower()
    if return_cripple and target_hp is not None:
        if loc_lower in _LIMB_LOCATIONS:
            threshold = target_hp  # injury ≥ HP/2 means crippled (cap at HP)
            half_hp = target_hp // 2
            if raw_injury > half_hp:
                crippled = True
            raw_injury = min(raw_injury, target_hp)  # excess damage lost
        elif loc_lower in _EXTREMITY_LOCATIONS:
            third_hp = math.ceil(target_hp / 3)
            if raw_injury >= third_hp:
                crippled = True
            raw_injury = min(raw_injury, target_hp)

    if return_cripple:
        return raw_injury, crippled
    return raw_injury


# ---------------------------------------------------------------------------
# Step 7 — Wound effects
# ---------------------------------------------------------------------------


def check_wound_effects(
    injury: int,
    target_hp: int,
    target_current_hp: int,
) -> list[str]:
    """Determine wound effects from a single injury instance.

    Checks for:
      - half_move_dodge: current HP after injury drops below HP/3
      - check_consciousness: current HP drops to 0 or below
      - knockdown_check: single injury > HP/2 (major wound)
      - death_check: cumulative HP crosses a -N×HP threshold
      - instant_death: cumulative HP reaches -5×HP

    Args:
        injury: HP lost from this single attack.
        target_hp: Target's full HP.
        target_current_hp: Target's HP before this injury is applied.

    Returns:
        List of effect strings. Empty list if no special effects triggered.
    """
    effects: list[str] = []
    new_hp = target_current_hp - injury

    # Half Move/Dodge below 1/3 HP
    one_third = math.ceil(target_hp / 3)
    if new_hp < one_third:
        effects.append("half_move_dodge")

    # Consciousness check at 0 HP or below
    if new_hp <= 0:
        effects.append("check_consciousness")

    # Major wound knockdown check (injury > HP/2 in a single hit)
    if injury > target_hp / 2:
        effects.append("knockdown_check")

    # Death checks at -1×HP, -2×HP, -3×HP, -4×HP (B380)
    for multiplier in range(1, 5):
        threshold = -multiplier * target_hp
        if target_current_hp > threshold >= new_hp:
            effects.append("death_check")

    # Instant death at -5×HP
    if new_hp <= -5 * target_hp:
        effects.append("instant_death")

    return effects


# ---------------------------------------------------------------------------
# Full pipeline — resolve_attack
# ---------------------------------------------------------------------------


def _parse_damage_dice(weapon: Weapon) -> tuple[str, int]:
    """Return (dice_str, total_bonus) from weapon, separating dice from bonus."""
    # e.g. weapon.damage_dice = '2d', damage_bonus = +1 → '2d', 1
    return weapon.damage_dice, weapon.damage_bonus


def _roll_weapon_damage(
    weapon: Weapon,
    maneuver: str = "attack",
    _force_damage_dice: Optional[list[int]] = None,
) -> int:
    """Roll weapon damage including maneuver bonuses.

    Returns the raw damage total (before DR).
    """
    from engine.dice import damage_roll

    dice_str = weapon.damage_dice
    base_total = damage_roll(dice_str, _force_dice=_force_damage_dice) + weapon.damage_bonus

    # All-Out Attack (Strong): +2 to damage
    reg = MANEUVER_REGISTRY.get(maneuver, MANEUVER_REGISTRY["attack"])
    base_total += reg.damage_bonus

    # Apply damage type minimum to raw damage
    return apply_damage_minimum(base_total, weapon.damage_type)


def resolve_attack(
    action: AttackAction,
    attacker_skill: int,
    defender_dodge: Optional[int],
    defender_dr: int,
    defender_hp: int,
    defender_current_hp: int,
    defender_parry: Optional[int] = None,
    defender_block: Optional[int] = None,
    defender_stunned: bool = False,
    _force_attack_roll: Optional[int] = None,
    _force_defense_roll: Optional[int] = None,
    _force_damage_dice: Optional[list[int]] = None,
    _force_location_roll: Optional[int] = None,
) -> CombatResult:
    """Execute the full 7-step attack resolution pipeline.

    Args:
        action: Complete attack description (attacker, weapon, maneuver, etc.).
        attacker_skill: Base weapon skill of the attacker.
        defender_dodge: Defender's Dodge score.
        defender_dr: Armour DR at the target location.
        defender_hp: Defender's full HP.
        defender_current_hp: Defender's current HP before this attack.
        defender_parry: Defender's Parry score (optional).
        defender_block: Defender's Block score (optional).
        defender_stunned: True if defender is currently stunned.
        _force_attack_roll: Testing override for attack roll.
        _force_defense_roll: Testing override for defense roll.
        _force_damage_dice: Testing override for damage dice values.
        _force_location_roll: Testing override for hit location roll.

    Returns:
        CombatResult with all intermediate values and wound effects.
    """
    # Sum all situational modifiers
    total_modifier = sum(m.value for m in action.modifiers)

    # Deceptive attack: attacker takes -N skill penalty; defender gets -N/2 to defense
    deceptive_penalty = 0
    for m in action.modifiers:
        if m.name == "deceptive_penalty":
            # deceptive_penalty value is the skill reduction (negative number)
            # defender penalty = floor(abs(skill_reduction) / 2)
            deceptive_penalty = abs(m.value) // 2

    # Step 1 — Attack roll
    atk = attack_roll(
        skill=attacker_skill,
        modifier=total_modifier,
        maneuver=action.maneuver,
        _force_roll=_force_attack_roll,
    )

    # Determine hit location (for penalty to effective skill on declared target)
    if action.target_location and action.target_location != "random":
        location = action.target_location.lower()
    else:
        location = hit_location_roll(_force_roll=_force_location_roll)

    # If the attack failed, short-circuit
    if not atk.success:
        return CombatResult(
            attack_roll=atk,
            defense_roll=None,
            defense_type=None,
            hit_location=location,
            raw_damage=0,
            dr=defender_dr,
            penetrating_damage=0,
            wound_multiplier=0.0,
            injury=0,
            effects=[],
        )

    # Step 2 — Defense roll (skipped on critical hit)
    defense_res: Optional[DefenseResult] = None
    if atk.critical and atk.critical_type == "success":
        # Critical hit: defender gets no defense roll
        defense_res = None
        defender_hit = True
    else:
        defense_res = defense_roll(
            dodge=defender_dodge,
            parry=defender_parry,
            block=defender_block,
            stunned=defender_stunned,
            attacker_maneuver=action.maneuver,
            deceptive_penalty=deceptive_penalty,
            _force_roll=_force_defense_roll,
        )
        defender_hit = not defense_res.success

    # If defender succeeded, no damage
    if not defender_hit:
        return CombatResult(
            attack_roll=atk,
            defense_roll=defense_res,
            defense_type=defense_res.defense_type if defense_res else None,
            hit_location=location,
            raw_damage=0,
            dr=defender_dr,
            penetrating_damage=0,
            wound_multiplier=0.0,
            injury=0,
            effects=[],
        )

    # Step 4 — Damage roll
    raw_damage = _roll_weapon_damage(
        action.weapon,
        maneuver=action.maneuver,
        _force_damage_dice=_force_damage_dice,
    )

    # Step 5 — Apply DR (including location extra DR)
    penetrating = apply_dr(raw_damage=raw_damage, dr=defender_dr, location=location)

    # Step 6 — Calculate injury
    wound_mult = get_wound_multiplier(action.weapon.damage_type, location)
    injury = calculate_injury(
        penetrating=penetrating,
        damage_type=action.weapon.damage_type,
        location=location,
        target_hp=defender_hp,
    )

    # Step 7 — Wound effects
    effects = check_wound_effects(
        injury=injury,
        target_hp=defender_hp,
        target_current_hp=defender_current_hp,
    )

    return CombatResult(
        attack_roll=atk,
        defense_roll=defense_res,
        defense_type=defense_res.defense_type if defense_res else None,
        hit_location=location,
        raw_damage=raw_damage,
        dr=defender_dr,
        penetrating_damage=penetrating,
        wound_multiplier=wound_mult,
        injury=injury,
        effects=effects,
    )
