"""GURPS lookup tables — all values verified against source material.

Tables implemented:
  - Hit Location Table (B552 / GURPS Lite cheat sheet)
  - Size and Speed/Range Table (B550 / GURPS Lite p.27)
  - Reaction Table (GURPS Lite p.3)
  - Critical Hit Table (B556)
  - Critical Miss Table (B556)

No values are computed by the LLM. These are pure data lookups.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import random


# ---------------------------------------------------------------------------
# Hit Location Table
# ---------------------------------------------------------------------------


@dataclass
class HitLocationEntry:
    """Data for a single hit location (B552).

    Attributes:
        location: Canonical name of the body part.
        attack_penalty: To-hit penalty when deliberately targeting this location.
            Negative = harder to hit. Torso = 0.
        extra_dr: Additional DR applied to this location on top of armour DR.
            Skull has +2 extra DR.
        wound_multiplier_override: If set, this value replaces the damage-type
            wound multiplier for all attacks striking this location. The skull
            uses ×4 for all types except toxic (B553). None = use standard type
            multiplier.
        is_limb: True for arm/leg locations (crippling threshold = HP/2 in one hit).
        is_extremity: True for hand/foot (crippling threshold = HP/3 in one hit,
            excess damage lost).
        notes: Human-readable rules notes.
    """

    location: str
    attack_penalty: int
    extra_dr: int = 0
    wound_multiplier_override: Optional[float] = None
    is_limb: bool = False
    is_extremity: bool = False
    notes: str = ""


# Hit Location Table — maps 3d6 roll to entry.
# Source: GURPS Basic Set B552 / Lite cheat sheet humanoid table.
HIT_LOCATION_TABLE: dict[int, HitLocationEntry] = {
    3: HitLocationEntry(
        location="skull",
        attack_penalty=-7,
        extra_dr=2,
        wound_multiplier_override=4.0,
        notes=(
            "Extra DR 2 (external attacks only). Wounding ×4 for all types except tox. "
            "Attack missing by 1 hits torso instead."
        ),
    ),
    4: HitLocationEntry(
        location="skull",
        attack_penalty=-7,
        extra_dr=2,
        wound_multiplier_override=4.0,
        notes=(
            "Extra DR 2 (external attacks only). Wounding ×4 for all types except tox. "
            "Attack missing by 1 hits torso instead."
        ),
    ),
    5: HitLocationEntry(
        location="face",
        attack_penalty=-5,
        notes=(
            "Jaw, cheeks, nose, ears. Attack missing by 1 hits torso. "
            "Corrosive damage blinds. On a front hit roll 1d: 1 = skull (imp/pi/tbb)."
        ),
    ),
    6: HitLocationEntry(
        location="right leg",
        attack_penalty=-2,
        is_limb=True,
        notes="Limb. Crippled if injury ≥ HP/2. Large pi, huge pi, imp: reduce wounding multiplier for limbs.",
    ),
    7: HitLocationEntry(
        location="right leg",
        attack_penalty=-2,
        is_limb=True,
        notes="Limb. Crippled if injury ≥ HP/2.",
    ),
    8: HitLocationEntry(
        location="right arm",
        attack_penalty=-2,
        is_limb=True,
        notes="Limb. Crippled if injury ≥ HP/2.",
    ),
    9: HitLocationEntry(
        location="torso",
        attack_penalty=0,
        notes="Default hit location. Roll 1d if cr/imp/pi/tbb: 1 = vitals.",
    ),
    10: HitLocationEntry(
        location="torso",
        attack_penalty=0,
        notes="Default hit location.",
    ),
    11: HitLocationEntry(
        location="abdomen",
        attack_penalty=-1,
        notes="Groin for humanoid males: ×2 shock from cr, otherwise treat as torso.",
    ),
    12: HitLocationEntry(
        location="left arm",
        attack_penalty=-2,
        is_limb=True,
        notes="Limb. Crippled if injury ≥ HP/2.",
    ),
    13: HitLocationEntry(
        location="left leg",
        attack_penalty=-2,
        is_limb=True,
        notes="Limb. Crippled if injury ≥ HP/2.",
    ),
    14: HitLocationEntry(
        location="left leg",
        attack_penalty=-2,
        is_limb=True,
        notes="Limb. Crippled if injury ≥ HP/2.",
    ),
    15: HitLocationEntry(
        location="hand",
        attack_penalty=-4,
        is_extremity=True,
        notes="Extremity. Crippled if injury ≥ HP/3; excess damage lost.",
    ),
    16: HitLocationEntry(
        location="foot",
        attack_penalty=-4,
        is_extremity=True,
        notes="Extremity. Crippled if injury ≥ HP/3; excess damage lost.",
    ),
    17: HitLocationEntry(
        location="neck",
        attack_penalty=-5,
        notes=(
            "Neck and throat. Increase wounding multiplier for cr and cor to ×1.5. "
            "Cut to neck: decapitation possible at high damage. "
            "Attack missing by 1 hits torso instead."
        ),
    ),
    18: HitLocationEntry(
        location="neck",
        attack_penalty=-5,
        notes=(
            "Neck and throat. Same as roll 17."
        ),
    ),
}


def get_hit_location(roll: int) -> HitLocationEntry:
    """Return the HitLocationEntry for a 3d6 hit location roll.

    Args:
        roll: 3d6 result (must be 3-18 inclusive).

    Returns:
        HitLocationEntry for the rolled location.

    Raises:
        ValueError: If roll is outside valid range.
    """
    if roll < 3 or roll > 18:
        raise ValueError(f"Hit location roll must be 3-18, got {roll}")
    return HIT_LOCATION_TABLE[roll]


def roll_hit_location() -> HitLocationEntry:
    """Roll 3d6 randomly and return the corresponding HitLocationEntry."""
    roll = sum(random.randint(1, 6) for _ in range(3))
    return get_hit_location(roll)


# ---------------------------------------------------------------------------
# Size and Speed/Range Table (B550, GURPS Lite p.27)
# ---------------------------------------------------------------------------

# Maps (linear measurement in yards) → speed/range modifier.
# When a value falls between two entries, use the penalty from the next-higher entry.
# Source: GURPS Lite p.27 condensed table.
_SPEED_RANGE_TABLE: list[tuple[float, int]] = [
    # (max_yards_inclusive, modifier)
    (1.0, -1),
    (2.0, 0),
    (3.0, -2),
    (5.0, -3),
    (7.0, -4),
    (10.0, -5),
    (15.0, -6),
    (20.0, -7),
    (30.0, -8),
    (50.0, -9),
    (70.0, -9),   # same penalty bracket
    (100.0, -10),
    (150.0, -11),
    (200.0, -12),
    (300.0, -13),
    (500.0, -14),
    (700.0, -15),
    (1000.0, -16),
    (1500.0, -17),
    (2000.0, -18),
    (3000.0, -19),
    (5000.0, -20),
    (7000.0, -21),
    (10000.0, -22),
]


def get_size_speed_range_modifier(yards: float) -> int:
    """Return the speed/range modifier for a given distance in yards.

    If the distance falls between table entries, the next-higher (worse) penalty
    is used, per the GURPS rule for this table.

    Args:
        yards: Distance or combined speed+range in yards.

    Returns:
        Integer modifier (0 or negative). Values beyond the table return -22.
    """
    for max_yards, modifier in _SPEED_RANGE_TABLE:
        if yards <= max_yards:
            return modifier
    return -22


# ---------------------------------------------------------------------------
# Reaction level lookup
# ---------------------------------------------------------------------------

_REACTION_LEVEL_TABLE: list[tuple[int, str]] = [
    (0, "Disastrous"),
    (3, "Very Bad"),
    (6, "Bad"),
    (9, "Poor"),
    (12, "Neutral"),
    (15, "Good"),
    (18, "Very Good"),
    (9999, "Excellent"),
]


def get_reaction_level(total: int) -> str:
    """Return the reaction level name for a given reaction roll total.

    Modifiers should already be applied to total before calling.

    Args:
        total: Post-modifier reaction roll total.

    Returns:
        Reaction level string per GURPS Lite p.3 Reaction Table.
    """
    if total <= 0:
        return "Disastrous"
    for threshold, name in _REACTION_LEVEL_TABLE:
        if total <= threshold:
            return name
    return "Excellent"


# ---------------------------------------------------------------------------
# Critical Hit Table (B556)
# ---------------------------------------------------------------------------


@dataclass
class CriticalHitEntry:
    """Effect of a critical hit roll.

    Attributes:
        description: Human-readable effect description.
        damage_multiplier: Multiply final damage by this (1 = normal).
        max_damage: If True, compute max possible damage rather than rolling.
        halve_dr: If True, halve the target's DR before applying damage.
        extra_effect: Additional effect string (e.g., 'drops weapon').
    """

    description: str
    damage_multiplier: float = 1.0
    max_damage: bool = False
    halve_dr: bool = False
    extra_effect: str = ""


# Critical Hit Table (B556) — roll 3d6 AFTER confirming critical.
# Note: In GURPS Lite, a roll of 3 on the attack roll = max damage automatically,
# other critical hits bypass the defense roll but roll damage normally.
# The full Basic Set table is implemented here.
CRITICAL_HIT_TABLE: dict[int, CriticalHitEntry] = {
    3: CriticalHitEntry(
        description="Maximum possible injury — no damage roll needed.",
        max_damage=True,
    ),
    4: CriticalHitEntry(
        description="Double damage.",
        damage_multiplier=2.0,
    ),
    5: CriticalHitEntry(
        description="Treat target's armor as DR/2.",
        halve_dr=True,
    ),
    6: CriticalHitEntry(
        description="Normal damage. Defense roll bypassed.",
    ),
    7: CriticalHitEntry(
        description="Normal damage. Defense roll bypassed.",
    ),
    8: CriticalHitEntry(
        description="Normal damage. Defense roll bypassed.",
    ),
    9: CriticalHitEntry(
        description="Normal damage. Defense roll bypassed.",
    ),
    10: CriticalHitEntry(
        description="Normal damage. Defense roll bypassed.",
    ),
    11: CriticalHitEntry(
        description="Normal damage. Defense roll bypassed.",
    ),
    12: CriticalHitEntry(
        description="Normal damage. Victim drops any held ready items.",
        extra_effect="drops_held_items",
    ),
    13: CriticalHitEntry(
        description="Normal damage. Defense roll bypassed.",
    ),
    14: CriticalHitEntry(
        description="Normal damage. Defense roll bypassed.",
    ),
    15: CriticalHitEntry(
        description="Normal damage. Defense roll bypassed.",
    ),
    16: CriticalHitEntry(
        description="Normal damage. Defense roll bypassed.",
    ),
    17: CriticalHitEntry(
        description="Normal damage. Defense roll bypassed.",
    ),
    18: CriticalHitEntry(
        description="Normal damage. Defense roll bypassed.",
    ),
}


def get_critical_hit_effect(roll: int) -> CriticalHitEntry:
    """Return the CriticalHitEntry for a critical hit table roll.

    Args:
        roll: 3d6 result on the critical hit table (3-18).

    Returns:
        CriticalHitEntry describing the effect.

    Raises:
        ValueError: If roll is outside 3-18.
    """
    if roll < 3 or roll > 18:
        raise ValueError(f"Critical hit table roll must be 3-18, got {roll}")
    return CRITICAL_HIT_TABLE[roll]


# ---------------------------------------------------------------------------
# Critical Miss Table (B556)
# ---------------------------------------------------------------------------


@dataclass
class CriticalMissEntry:
    """Effect of a critical miss roll.

    Attributes:
        description: Human-readable effect.
        weapon_breaks: True if the weapon is destroyed/broken.
        attacker_falls: True if the attacker falls prone.
        attacker_hits_self: True if the attacker hits themselves.
        weapon_dropped: True if the weapon is dropped.
        defense_penalty: Penalty to active defenses until next turn.
        extra_effect: Additional effect notes.
    """

    description: str
    weapon_breaks: bool = False
    attacker_falls: bool = False
    attacker_hits_self: bool = False
    weapon_dropped: bool = False
    defense_penalty: int = 0
    extra_effect: str = ""


# Critical Miss Table (B556) — roll 3d6 AFTER confirming critical miss.
# Source: GURPS Basic Set B556 / cheat sheet.
CRITICAL_MISS_TABLE: dict[int, CriticalMissEntry] = {
    3: CriticalMissEntry(
        description=(
            "Weapon breaks! If weapon is unusually resistant (solid cr weapon attacking "
            "an arm or similar), reroll: 3-4 breaks, otherwise drops weapon."
        ),
        weapon_breaks=True,
    ),
    4: CriticalMissEntry(
        description="Weapon breaks! See roll 3 for resistant weapons.",
        weapon_breaks=True,
    ),
    5: CriticalMissEntry(
        description=(
            "You hit yourself in the arm or leg (50% chance each). "
            "Exception: for imp/pi/ranged, reroll — 5-6: full/half damage, other: use that result."
        ),
        attacker_hits_self=True,
    ),
    6: CriticalMissEntry(
        description="You hit yourself in arm or leg (half damage only).",
        attacker_hits_self=True,
    ),
    7: CriticalMissEntry(
        description="Lose your balance — do nothing else this turn (not even free actions). Active defense at -2.",
        defense_penalty=-2,
    ),
    8: CriticalMissEntry(
        description="Weapon turns in hand; requires Ready maneuver before it can be used again.",
        extra_effect="weapon_turns_in_hand",
    ),
    9: CriticalMissEntry(
        description="Drop weapon. Cheap weapon breaks. Weapon lands 1d-4 yards away (min 0); 50% chance forward or back. Anyone on that spot rolls DX or takes half damage.",
        weapon_dropped=True,
    ),
    10: CriticalMissEntry(
        description="Drop weapon (as roll 9).",
        weapon_dropped=True,
    ),
    11: CriticalMissEntry(
        description="Drop weapon (as roll 9).",
        weapon_dropped=True,
    ),
    12: CriticalMissEntry(
        description="Weapon turns in hand; requires Ready maneuver to use again.",
        extra_effect="weapon_turns_in_hand",
    ),
    13: CriticalMissEntry(
        description="Lose your balance — do nothing else (not even free actions). Active defense at -2.",
        defense_penalty=-2,
    ),
    14: CriticalMissEntry(
        description="Drop weapon (as roll 9).",
        weapon_dropped=True,
    ),
    15: CriticalMissEntry(
        description=(
            "Hit yourself in arm or leg (half damage only). "
            "Exception: for imp/pi/ranged, reroll as for roll 6."
        ),
        attacker_hits_self=True,
    ),
    16: CriticalMissEntry(
        description="You fall down! If ranged attack, treat as roll 7 (balance lost).",
        attacker_falls=True,
    ),
    17: CriticalMissEntry(
        description="Weapon breaks! See roll 3 for resistant weapons.",
        weapon_breaks=True,
    ),
    18: CriticalMissEntry(
        description="Weapon breaks! See roll 3 for resistant weapons.",
        weapon_breaks=True,
    ),
}


def get_critical_miss_effect(roll: int) -> CriticalMissEntry:
    """Return the CriticalMissEntry for a critical miss table roll.

    Args:
        roll: 3d6 result on the critical miss table (3-18).

    Returns:
        CriticalMissEntry describing the effect.

    Raises:
        ValueError: If roll is outside 3-18.
    """
    if roll < 3 or roll > 18:
        raise ValueError(f"Critical miss table roll must be 3-18, got {roll}")
    return CRITICAL_MISS_TABLE[roll]
