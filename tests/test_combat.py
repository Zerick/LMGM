"""Unit tests for engine/combat.py — Phase 2.

Tests cover the full attack resolution pipeline (7 steps), maneuver registry,
damage type wound multipliers, DR application, and wound effects.
Edge cases: DR > damage, crushing minimum 0, skull wound ×4, death checks.
"""
import pytest

from engine.combat import (
    AttackAction,
    CombatResult,
    Modifier,
    Weapon,
    DamageType,
    Maneuver,
    MANEUVER_REGISTRY,
    attack_roll,
    defense_roll,
    hit_location_roll,
    apply_dr,
    calculate_injury,
    check_wound_effects,
    resolve_attack,
    get_wound_multiplier,
    apply_damage_minimum,
)


# ---------------------------------------------------------------------------
# Fixtures — reusable test data
# ---------------------------------------------------------------------------


def _broadsword() -> Weapon:
    return Weapon(
        name="broadsword",
        damage_dice="2d",
        damage_bonus=1,
        damage_type=DamageType.CUTTING,
        min_st=10,
    )


def _dagger() -> Weapon:
    return Weapon(
        name="dagger",
        damage_dice="1d",
        damage_bonus=-1,
        damage_type=DamageType.IMPALING,
        min_st=6,
    )


def _punch() -> Weapon:
    return Weapon(
        name="punch",
        damage_dice="1d",
        damage_bonus=-2,
        damage_type=DamageType.CRUSHING,
        min_st=0,
    )


def _simple_attack(
    maneuver: str = "attack",
    target_location: str = "torso",
    weapon: Weapon | None = None,
    modifiers: list[Modifier] | None = None,
) -> AttackAction:
    return AttackAction(
        attacker_id="bjorn",
        target_id="goblin",
        weapon=weapon or _broadsword(),
        maneuver=maneuver,
        target_location=target_location,
        modifiers=modifiers or [],
    )


# ---------------------------------------------------------------------------
# AttackAction dataclass
# ---------------------------------------------------------------------------


class TestAttackAction:
    def test_creates_with_required_fields(self) -> None:
        action = _simple_attack()
        assert action.attacker_id == "bjorn"
        assert action.target_id == "goblin"
        assert action.maneuver == "attack"

    def test_default_target_location_torso(self) -> None:
        action = _simple_attack()
        assert action.target_location == "torso"


# ---------------------------------------------------------------------------
# Maneuver Registry
# ---------------------------------------------------------------------------


class TestManeuverRegistry:
    def test_attack_maneuver_exists(self) -> None:
        assert "attack" in MANEUVER_REGISTRY

    def test_all_out_attack_determined_exists(self) -> None:
        assert "all_out_attack_determined" in MANEUVER_REGISTRY

    def test_all_out_attack_strong_exists(self) -> None:
        assert "all_out_attack_strong" in MANEUVER_REGISTRY

    def test_all_out_attack_double_exists(self) -> None:
        assert "all_out_attack_double" in MANEUVER_REGISTRY

    def test_all_out_defense_dodge_exists(self) -> None:
        assert "all_out_defense_dodge" in MANEUVER_REGISTRY

    def test_all_out_defense_increased_exists(self) -> None:
        assert "all_out_defense_increased" in MANEUVER_REGISTRY

    def test_deceptive_attack_exists(self) -> None:
        assert "deceptive_attack" in MANEUVER_REGISTRY

    def test_move_and_attack_exists(self) -> None:
        assert "move_and_attack" in MANEUVER_REGISTRY

    def test_attack_has_no_skill_modifier(self) -> None:
        assert MANEUVER_REGISTRY["attack"].attack_modifier == 0

    def test_all_out_attack_determined_gives_plus4(self) -> None:
        assert MANEUVER_REGISTRY["all_out_attack_determined"].attack_modifier == 4

    def test_all_out_attack_strong_gives_no_skill_mod(self) -> None:
        """Strong gives +2 damage, not +skill."""
        reg = MANEUVER_REGISTRY["all_out_attack_strong"]
        assert reg.attack_modifier == 0
        assert reg.damage_bonus == 2

    def test_all_out_attack_no_active_defense(self) -> None:
        for name in ["all_out_attack_determined", "all_out_attack_strong", "all_out_attack_double"]:
            assert MANEUVER_REGISTRY[name].allows_defense is False

    def test_attack_allows_defense(self) -> None:
        assert MANEUVER_REGISTRY["attack"].allows_defense is True

    def test_move_and_attack_penalty(self) -> None:
        reg = MANEUVER_REGISTRY["move_and_attack"]
        assert reg.attack_modifier == -4

    def test_move_and_attack_caps_skill_at_9(self) -> None:
        reg = MANEUVER_REGISTRY["move_and_attack"]
        assert reg.max_effective_skill == 9

    def test_all_out_defense_dodge_defense_bonus(self) -> None:
        reg = MANEUVER_REGISTRY["all_out_defense_dodge"]
        assert reg.dodge_bonus == 2


# ---------------------------------------------------------------------------
# Step 1 — attack_roll
# ---------------------------------------------------------------------------


class TestAttackRoll:
    def test_returns_check_result(self) -> None:
        from engine.dice import CheckResult
        result = attack_roll(skill=12)
        assert isinstance(result, CheckResult)

    def test_forced_success(self) -> None:
        result = attack_roll(skill=12, _force_roll=8)
        assert result.success is True
        assert result.margin == 4

    def test_forced_failure(self) -> None:
        result = attack_roll(skill=10, _force_roll=13)
        assert result.success is False

    def test_modifier_applied(self) -> None:
        """Modifier adjusts effective skill before rolling."""
        result = attack_roll(skill=10, modifier=4, _force_roll=14)
        # effective skill = 14, roll 14 = success
        assert result.success is True

    def test_critical_success_on_3(self) -> None:
        result = attack_roll(skill=10, _force_roll=3)
        assert result.critical is True
        assert result.critical_type == "success"


# ---------------------------------------------------------------------------
# Step 2 — defense_roll
# ---------------------------------------------------------------------------


class TestDefenseRoll:
    def test_dodge_success(self) -> None:
        result = defense_roll(dodge=8, parry=None, block=None, _force_roll=6)
        assert result.success is True

    def test_dodge_failure(self) -> None:
        result = defense_roll(dodge=6, parry=None, block=None, _force_roll=10)
        assert result.success is False

    def test_parry_used_when_provided(self) -> None:
        result = defense_roll(dodge=None, parry=9, block=None, _force_roll=8)
        assert result.success is True

    def test_block_used_when_provided(self) -> None:
        result = defense_roll(dodge=None, parry=None, block=8, _force_roll=7)
        assert result.success is True

    def test_raises_when_no_defense_provided(self) -> None:
        with pytest.raises(ValueError):
            defense_roll(dodge=None, parry=None, block=None)

    def test_stunned_penalty(self) -> None:
        """Stunned defenders have -4 to all active defenses."""
        result = defense_roll(dodge=8, parry=None, block=None, stunned=True, _force_roll=8)
        # effective dodge = 8 - 4 = 4; roll 8 > 4 → failure
        assert result.success is False

    def test_all_out_attack_no_defense(self) -> None:
        """When attacker used All-Out Attack, defender gets no active defense."""
        result = defense_roll(
            dodge=10, parry=None, block=None,
            attacker_maneuver="all_out_attack_determined",
            _force_roll=5,
        )
        assert result.success is False
        assert "no defense" in result.target_description.lower()


# ---------------------------------------------------------------------------
# Step 3 — hit_location_roll
# ---------------------------------------------------------------------------


class TestHitLocationRoll:
    def test_returns_string_location(self) -> None:
        loc = hit_location_roll()
        assert isinstance(loc, str)
        assert len(loc) > 0

    def test_forced_roll_skull(self) -> None:
        loc = hit_location_roll(_force_roll=3)
        assert loc == "skull"

    def test_forced_roll_torso(self) -> None:
        loc = hit_location_roll(_force_roll=10)
        assert loc == "torso"

    def test_declared_location_used(self) -> None:
        """If attacker declared a location, that is returned directly."""
        loc = hit_location_roll(declared_location="face")
        assert loc == "face"


# ---------------------------------------------------------------------------
# Step 4 — damage_roll (via apply_dr and calculate_injury)
# Step 5 — apply_dr
# ---------------------------------------------------------------------------


class TestApplyDR:
    def test_dr_subtracted_from_damage(self) -> None:
        penetrating = apply_dr(raw_damage=10, dr=4)
        assert penetrating == 6

    def test_dr_greater_than_damage_no_penetration(self) -> None:
        penetrating = apply_dr(raw_damage=3, dr=5)
        assert penetrating == 0

    def test_dr_equal_to_damage_no_penetration(self) -> None:
        penetrating = apply_dr(raw_damage=4, dr=4)
        assert penetrating == 0

    def test_no_dr_full_damage_penetrates(self) -> None:
        penetrating = apply_dr(raw_damage=8, dr=0)
        assert penetrating == 8

    def test_skull_adds_extra_dr(self) -> None:
        """Skull has extra DR 2 on top of worn armour."""
        penetrating = apply_dr(raw_damage=8, dr=4, location="skull")
        # total DR = 4 + 2 = 6; penetrating = 8 - 6 = 2
        assert penetrating == 2

    def test_non_skull_no_extra_dr(self) -> None:
        penetrating = apply_dr(raw_damage=8, dr=4, location="torso")
        assert penetrating == 4


# ---------------------------------------------------------------------------
# Wound multipliers
# ---------------------------------------------------------------------------


class TestGetWoundMultiplier:
    def test_crushing_to_torso(self) -> None:
        assert get_wound_multiplier(DamageType.CRUSHING, "torso") == 1.0

    def test_cutting_to_torso(self) -> None:
        assert get_wound_multiplier(DamageType.CUTTING, "torso") == 1.5

    def test_impaling_to_torso(self) -> None:
        assert get_wound_multiplier(DamageType.IMPALING, "torso") == 2.0

    def test_small_piercing_to_torso(self) -> None:
        assert get_wound_multiplier(DamageType.SMALL_PIERCING, "torso") == 0.5

    def test_large_piercing_to_torso(self) -> None:
        assert get_wound_multiplier(DamageType.LARGE_PIERCING, "torso") == 1.5

    def test_skull_overrides_to_4x(self) -> None:
        """Skull uses ×4 for all damage types (except tox)."""
        for dtype in [DamageType.CUTTING, DamageType.IMPALING, DamageType.CRUSHING,
                      DamageType.PIERCING, DamageType.SMALL_PIERCING]:
            mult = get_wound_multiplier(dtype, "skull")
            assert mult == 4.0, f"Expected ×4 for {dtype} to skull, got {mult}"

    def test_skull_toxic_not_overridden(self) -> None:
        """Tox to skull uses normal ×1 (B553 exception)."""
        assert get_wound_multiplier(DamageType.TOXIC, "skull") == 1.0

    def test_burning_to_torso(self) -> None:
        assert get_wound_multiplier(DamageType.BURNING, "torso") == 1.0

    def test_corrosive_to_torso(self) -> None:
        assert get_wound_multiplier(DamageType.CORROSIVE, "torso") == 1.0


# ---------------------------------------------------------------------------
# Step 6 — calculate_injury
# ---------------------------------------------------------------------------


class TestCalculateInjury:
    def test_cutting_torso(self) -> None:
        # 6 penetrating × 1.5 = 9 injury
        injury = calculate_injury(penetrating=6, damage_type=DamageType.CUTTING, location="torso")
        assert injury == 9

    def test_impaling_torso(self) -> None:
        # 5 penetrating × 2 = 10 injury
        injury = calculate_injury(penetrating=5, damage_type=DamageType.IMPALING, location="torso")
        assert injury == 10

    def test_crushing_torso(self) -> None:
        # 4 penetrating × 1 = 4 injury
        injury = calculate_injury(penetrating=4, damage_type=DamageType.CRUSHING, location="torso")
        assert injury == 4

    def test_skull_crushing_x4(self) -> None:
        # 3 penetrating × 4 = 12 injury
        injury = calculate_injury(penetrating=3, damage_type=DamageType.CRUSHING, location="skull")
        assert injury == 12

    def test_skull_cutting_x4(self) -> None:
        # 5 penetrating × 4 = 20 injury
        injury = calculate_injury(penetrating=5, damage_type=DamageType.CUTTING, location="skull")
        assert injury == 20

    def test_fractions_rounded_down(self) -> None:
        # 3 penetrating cutting = 3 × 1.5 = 4.5 → rounds to 4
        injury = calculate_injury(penetrating=3, damage_type=DamageType.CUTTING, location="torso")
        assert injury == 4

    def test_minimum_1_if_any_penetration_non_crushing(self) -> None:
        """If any damage penetrates DR for non-crushing, injury >= 1."""
        injury = calculate_injury(penetrating=1, damage_type=DamageType.SMALL_PIERCING, location="torso")
        # 1 × 0.5 = 0.5 → rounds down to 0, but minimum is 1
        assert injury == 1

    def test_zero_penetrating_means_zero_injury(self) -> None:
        injury = calculate_injury(penetrating=0, damage_type=DamageType.CUTTING, location="torso")
        assert injury == 0

    def test_limb_injury_can_cripple(self) -> None:
        """High injury to a limb should be capped and flagged for crippling."""
        # For limbs, excess damage is lost; threshold is HP/2 (HP passed as param)
        # Just test that function returns the capped value when cripple_hp given
        injury, crippled = calculate_injury(
            penetrating=20, damage_type=DamageType.CUTTING, location="right arm",
            target_hp=10, return_cripple=True,
        )
        # Limb: raw injury = 20 * 1.5 = 30, capped at HP = 10 for limbs
        assert crippled is True
        assert injury <= 10  # excess damage lost


# ---------------------------------------------------------------------------
# Damage minimum helpers
# ---------------------------------------------------------------------------


class TestApplyDamageMinimum:
    def test_crushing_min_zero(self) -> None:
        """Crushing damage minimum is 0 (not 1)."""
        assert apply_damage_minimum(-3, DamageType.CRUSHING) == 0

    def test_cutting_min_one(self) -> None:
        assert apply_damage_minimum(-2, DamageType.CUTTING) == 1

    def test_impaling_min_one(self) -> None:
        assert apply_damage_minimum(0, DamageType.IMPALING) == 1

    def test_positive_value_unchanged(self) -> None:
        assert apply_damage_minimum(5, DamageType.CUTTING) == 5

    def test_crushing_zero_unchanged(self) -> None:
        assert apply_damage_minimum(0, DamageType.CRUSHING) == 0


# ---------------------------------------------------------------------------
# Step 7 — check_wound_effects
# ---------------------------------------------------------------------------


class TestCheckWoundEffects:
    def test_no_effects_for_light_wound(self) -> None:
        effects = check_wound_effects(injury=3, target_hp=12, target_current_hp=12)
        assert effects == []

    def test_major_wound_requires_knockdown_check(self) -> None:
        """Major wound = injury > HP/2 in one hit."""
        # HP 10, injury 6 > 5 → major wound
        effects = check_wound_effects(injury=6, target_hp=10, target_current_hp=10)
        assert "knockdown_check" in effects

    def test_no_major_wound_when_under_threshold(self) -> None:
        # HP 10, injury 5 = exactly HP/2 → NOT a major wound (must be GREATER)
        effects = check_wound_effects(injury=5, target_hp=10, target_current_hp=10)
        assert "knockdown_check" not in effects

    def test_death_check_at_negative_1x_hp(self) -> None:
        """Death check required when cumulative HP drops to -1×HP."""
        # HP 10, current was -5, injury 5 → now at -10 = -1×HP
        effects = check_wound_effects(
            injury=5, target_hp=10, target_current_hp=-5
        )
        assert "death_check" in effects

    def test_death_check_at_negative_2x_hp(self) -> None:
        # HP 10, current was -15, injury 5 → now at -20 = -2×HP
        effects = check_wound_effects(
            injury=5, target_hp=10, target_current_hp=-15
        )
        assert "death_check" in effects

    def test_instant_death_at_negative_5x_hp(self) -> None:
        """At -5×HP total, character dies immediately (B380)."""
        # HP 10, current was -49, injury 1 → now at -50 = -5×HP
        effects = check_wound_effects(
            injury=1, target_hp=10, target_current_hp=-49
        )
        assert "instant_death" in effects

    def test_unconsciousness_at_zero_hp(self) -> None:
        """At 0 HP, character risks unconsciousness each turn."""
        effects = check_wound_effects(
            injury=5, target_hp=10, target_current_hp=5
        )
        # goes to exactly 0 — add the 'check_consciousness' effect
        assert "check_consciousness" in effects

    def test_half_move_below_one_third_hp(self) -> None:
        """Below 1/3 HP, Move and Dodge are halved."""
        # HP 12, below 4 HP → half move
        effects = check_wound_effects(
            injury=5, target_hp=12, target_current_hp=6
        )
        # goes to 1 HP which is below 12/3=4 → half_move effect
        assert "half_move_dodge" in effects


# ---------------------------------------------------------------------------
# Full pipeline — resolve_attack
# ---------------------------------------------------------------------------


class TestResolveAttack:
    def test_returns_combat_result(self) -> None:
        action = _simple_attack()
        result = resolve_attack(
            action=action,
            attacker_skill=13,
            defender_dodge=8,
            defender_dr=2,
            defender_hp=10,
            defender_current_hp=10,
        )
        assert isinstance(result, CombatResult)

    def test_miss_gives_no_damage(self) -> None:
        """If the attack roll fails, no damage is applied."""
        action = _simple_attack()
        result = resolve_attack(
            action=action,
            attacker_skill=10,
            defender_dodge=8,
            defender_dr=0,
            defender_hp=10,
            defender_current_hp=10,
            _force_attack_roll=18,  # always misses
        )
        assert result.attack_roll.success is False
        assert result.injury == 0

    def test_successful_defense_gives_no_damage(self) -> None:
        action = _simple_attack()
        result = resolve_attack(
            action=action,
            attacker_skill=13,
            defender_dodge=10,
            defender_dr=0,
            defender_hp=10,
            defender_current_hp=10,
            _force_attack_roll=9,
            _force_defense_roll=5,  # dodge succeeds
        )
        assert result.defense_roll is not None
        assert result.defense_roll.success is True
        assert result.injury == 0

    def test_hit_calculates_injury(self) -> None:
        """Attack hits and defense fails → injury computed."""
        action = _simple_attack(weapon=_broadsword())
        result = resolve_attack(
            action=action,
            attacker_skill=13,
            defender_dodge=8,
            defender_dr=2,
            defender_hp=10,
            defender_current_hp=10,
            _force_attack_roll=9,
            _force_defense_roll=12,   # dodge fails
            _force_damage_dice=[4, 4],  # 2d+1 = 9 raw; -2 DR = 7 pen; ×1.5 cut = 10
        )
        assert result.attack_roll.success is True
        assert result.defense_roll.success is False
        assert result.raw_damage == 9
        assert result.penetrating_damage == 7
        assert result.injury == 10  # 7 × 1.5 = 10.5 → 10

    def test_dr_absorbs_all_damage(self) -> None:
        """High DR: no penetration, no injury."""
        action = _simple_attack(weapon=_punch())
        result = resolve_attack(
            action=action,
            attacker_skill=12,
            defender_dodge=5,  # low dodge
            defender_dr=10,
            defender_hp=10,
            defender_current_hp=10,
            _force_attack_roll=8,
            _force_defense_roll=14,
            _force_damage_dice=[2],  # 1d-2 with dice [2] = 0; cr min = 0
        )
        assert result.penetrating_damage == 0
        assert result.injury == 0

    def test_skull_hit_applies_x4(self) -> None:
        """Attack to skull uses ×4 wounding multiplier."""
        action = _simple_attack(target_location="skull", weapon=_broadsword())
        result = resolve_attack(
            action=action,
            attacker_skill=14,
            defender_dodge=5,
            defender_dr=0,
            defender_hp=10,
            defender_current_hp=10,
            _force_attack_roll=8,
            _force_defense_roll=14,
            _force_damage_dice=[3, 3],  # 2d+1 = 7; no DR; extra DR 2 → 5 pen; ×4 = 20
        )
        assert result.hit_location == "skull"
        # raw 7, extra DR 2 → pen 5, ×4 = 20
        assert result.injury == 20

    def test_death_check_triggered_on_high_damage(self) -> None:
        """Injury that drops target past -1×HP triggers death_check.

        HP 10. Character is already at 1 HP (nearly dead). Broadsword
        2d+1 with dice [5,5] = 11 raw; ×1.5 cut = 16 injury.
        1 - 16 = -15 HP, crossing the -10 (-1×HP) threshold → death_check.
        """
        action = _simple_attack(weapon=_broadsword())
        result = resolve_attack(
            action=action,
            attacker_skill=14,
            defender_dodge=4,
            defender_dr=0,
            defender_hp=10,
            defender_current_hp=1,   # already nearly dead
            _force_attack_roll=8,
            _force_defense_roll=15,
            _force_damage_dice=[5, 5],  # 2d+1=11; ×1.5 cut=16; 1-16=-15 < -10
        )
        assert "death_check" in result.effects

    def test_all_out_attack_strong_damage_bonus(self) -> None:
        """All-Out Attack (Strong) gives +2 damage to final result."""
        action = _simple_attack(maneuver="all_out_attack_strong", weapon=_broadsword())
        result = resolve_attack(
            action=action,
            attacker_skill=12,
            defender_dodge=4,  # will fail
            defender_dr=0,
            defender_hp=10,
            defender_current_hp=10,
            _force_attack_roll=9,
            _force_defense_roll=15,
            _force_damage_dice=[2, 2],  # 2d+1=5, +2 AoA = 7; ×1.5 cut = 10
        )
        assert result.raw_damage == 7  # 5 base + 2 AoA Strong bonus

    def test_critical_hit_bypasses_defense(self) -> None:
        """Critical hit: no defense roll."""
        action = _simple_attack()
        result = resolve_attack(
            action=action,
            attacker_skill=12,
            defender_dodge=12,  # would normally succeed
            defender_dr=0,
            defender_hp=10,
            defender_current_hp=10,
            _force_attack_roll=3,   # critical success
            _force_damage_dice=[3, 3],
        )
        assert result.attack_roll.critical is True
        assert result.defense_roll is None  # no defense on crit hit
        assert result.injury > 0

    def test_deceptive_attack_reduces_defense(self) -> None:
        """Deceptive attack applies penalty to defender's active defense."""
        action = _simple_attack(
            maneuver="deceptive_attack",
            modifiers=[Modifier(name="deceptive_penalty", value=-4)],
        )
        result = resolve_attack(
            action=action,
            attacker_skill=14,
            defender_dodge=8,
            defender_dr=0,
            defender_hp=10,
            defender_current_hp=10,
            _force_attack_roll=9,    # 14-4=10 effective, roll 9 = success
            _force_defense_roll=7,   # dodge 8 - 2 (half of 4) = 6; roll 7 > 6 = fail
            _force_damage_dice=[2, 2],
        )
        # The defense should have failed due to the -2 deceptive penalty on dodge
        assert result.defense_roll.success is False
