"""Unit tests for engine/tables.py — Phase 2.

Verifies every lookup table against GURPS source material values.
Hit location, size/speed/range, fright check, reaction, critical hit/miss.
"""
import pytest

from engine.tables import (
    HitLocationEntry,
    CriticalHitEntry,
    CriticalMissEntry,
    get_hit_location,
    get_size_speed_range_modifier,
    get_reaction_level,
    get_critical_hit_effect,
    get_critical_miss_effect,
    HIT_LOCATION_TABLE,
    CRITICAL_HIT_TABLE,
    CRITICAL_MISS_TABLE,
    roll_hit_location,
)


# ---------------------------------------------------------------------------
# Hit Location Table (B552)
# ---------------------------------------------------------------------------


class TestHitLocationTable:
    def test_returns_hit_location_entry(self) -> None:
        entry = get_hit_location(10)
        assert isinstance(entry, HitLocationEntry)

    def test_roll_3_4_skull(self) -> None:
        for roll in [3, 4]:
            entry = get_hit_location(roll)
            assert entry.location == "skull"

    def test_roll_5_face(self) -> None:
        entry = get_hit_location(5)
        assert entry.location == "face"

    def test_roll_6_7_right_leg(self) -> None:
        for roll in [6, 7]:
            entry = get_hit_location(roll)
            assert entry.location == "right leg"

    def test_roll_8_right_arm(self) -> None:
        entry = get_hit_location(8)
        assert entry.location == "right arm"

    def test_roll_9_10_torso(self) -> None:
        for roll in [9, 10]:
            entry = get_hit_location(roll)
            assert entry.location == "torso"

    def test_roll_11_abdomen(self) -> None:
        entry = get_hit_location(11)
        assert entry.location == "abdomen"

    def test_roll_12_left_arm(self) -> None:
        entry = get_hit_location(12)
        assert entry.location == "left arm"

    def test_roll_13_14_left_leg(self) -> None:
        for roll in [13, 14]:
            entry = get_hit_location(roll)
            assert entry.location == "left leg"

    def test_roll_15_hand(self) -> None:
        entry = get_hit_location(15)
        assert entry.location == "hand"

    def test_roll_16_foot(self) -> None:
        entry = get_hit_location(16)
        assert entry.location == "foot"

    def test_roll_17_18_neck(self) -> None:
        for roll in [17, 18]:
            entry = get_hit_location(roll)
            assert entry.location == "neck"

    def test_skull_has_extra_dr_2(self) -> None:
        """Skull has an extra DR 2 vs. external attacks (B553)."""
        skull = get_hit_location(3)
        assert skull.extra_dr == 2

    def test_torso_has_no_extra_dr(self) -> None:
        torso = get_hit_location(9)
        assert torso.extra_dr == 0

    def test_skull_attack_penalty(self) -> None:
        """Skull has a -7 attack penalty (from the front) per B552."""
        skull = get_hit_location(3)
        assert skull.attack_penalty == -7

    def test_torso_attack_penalty_zero(self) -> None:
        torso = get_hit_location(9)
        assert torso.attack_penalty == 0

    def test_arm_attack_penalty(self) -> None:
        arm = get_hit_location(8)
        assert arm.attack_penalty == -2

    def test_all_rolls_3_to_18_covered(self) -> None:
        for roll in range(3, 19):
            entry = get_hit_location(roll)
            assert entry is not None
            assert entry.location  # non-empty string

    def test_invalid_roll_raises(self) -> None:
        with pytest.raises((ValueError, KeyError)):
            get_hit_location(2)

    def test_skull_wound_multiplier_all_types(self) -> None:
        """Skull uses x4 wounding multiplier for all damage types except tox."""
        skull = get_hit_location(3)
        assert skull.wound_multiplier_override == 4.0

    def test_torso_no_wound_multiplier_override(self) -> None:
        """Torso uses the standard type-based wound multiplier."""
        torso = get_hit_location(9)
        assert torso.wound_multiplier_override is None

    def test_roll_hit_location_returns_valid_entry(self) -> None:
        """roll_hit_location() should use dice and return a valid entry."""
        for _ in range(100):
            entry = roll_hit_location()
            assert isinstance(entry, HitLocationEntry)
            assert entry.location


# ---------------------------------------------------------------------------
# Size and Speed/Range Table (B550/Lite p.27)
# ---------------------------------------------------------------------------


class TestSizeSpeedRangeTable:
    def test_2_yards_zero_penalty(self) -> None:
        """2 yards = 0 speed/range modifier."""
        assert get_size_speed_range_modifier(2) == 0

    def test_1_yard_minus_1(self) -> None:
        assert get_size_speed_range_modifier(1) == -1

    def test_3_yards_minus_2(self) -> None:
        assert get_size_speed_range_modifier(3) == -2

    def test_5_yards_minus_3(self) -> None:
        assert get_size_speed_range_modifier(5) == -3

    def test_7_yards_minus_4(self) -> None:
        assert get_size_speed_range_modifier(7) == -4

    def test_10_yards_minus_5(self) -> None:
        assert get_size_speed_range_modifier(10) == -5

    def test_15_yards_minus_6(self) -> None:
        assert get_size_speed_range_modifier(15) == -6

    def test_20_yards_minus_7(self) -> None:
        assert get_size_speed_range_modifier(20) == -7

    def test_30_yards_minus_8(self) -> None:
        assert get_size_speed_range_modifier(30) == -8

    def test_50_yards_minus_9(self) -> None:
        assert get_size_speed_range_modifier(50) == -9

    def test_100_yards_minus_11(self) -> None:
        """Per the GURPS Lite table, 100 yards = -11."""
        # GURPS Lite p.27: 100 yards → -10 speed/range
        assert get_size_speed_range_modifier(100) == -10

    def test_between_values_uses_higher(self) -> None:
        """If a value falls between two entries, use the higher (worse) penalty."""
        # 8 yards is between 7 and 10 yards, so use 10-yard penalty (-5)
        assert get_size_speed_range_modifier(8) == -5

    def test_very_close_range_returns_small_penalty(self) -> None:
        """Point-blank range (< 2 yards) should not give positive bonus."""
        mod = get_size_speed_range_modifier(1)
        assert mod <= 0


# ---------------------------------------------------------------------------
# Reaction level lookup
# ---------------------------------------------------------------------------


class TestReactionLevel:
    def test_0_or_less_is_disastrous(self) -> None:
        assert get_reaction_level(0).lower() == "disastrous"
        assert get_reaction_level(-5).lower() == "disastrous"

    def test_1_to_3_very_bad(self) -> None:
        for total in [1, 2, 3]:
            assert get_reaction_level(total).lower() == "very bad"

    def test_4_to_6_bad(self) -> None:
        for total in [4, 5, 6]:
            assert get_reaction_level(total).lower() == "bad"

    def test_7_to_9_poor(self) -> None:
        for total in [7, 8, 9]:
            assert get_reaction_level(total).lower() == "poor"

    def test_10_to_12_neutral(self) -> None:
        for total in [10, 11, 12]:
            assert get_reaction_level(total).lower() == "neutral"

    def test_13_to_15_good(self) -> None:
        for total in [13, 14, 15]:
            assert get_reaction_level(total).lower() == "good"

    def test_16_to_18_very_good(self) -> None:
        for total in [16, 17, 18]:
            assert get_reaction_level(total).lower() == "very good"

    def test_19_plus_excellent(self) -> None:
        for total in [19, 20, 25, 30]:
            assert get_reaction_level(total).lower() == "excellent"


# ---------------------------------------------------------------------------
# Critical Hit Table (B556)
# ---------------------------------------------------------------------------


class TestCriticalHitTable:
    def test_returns_critical_hit_entry(self) -> None:
        entry = get_critical_hit_effect(9)
        assert isinstance(entry, CriticalHitEntry)

    def test_all_rolls_3_to_18_covered(self) -> None:
        for roll in range(3, 19):
            entry = get_critical_hit_effect(roll)
            assert entry is not None
            assert entry.description

    def test_roll_3_max_damage(self) -> None:
        """Roll 3 on critical hit table = max possible damage."""
        entry = get_critical_hit_effect(3)
        assert entry.max_damage is True or "max" in entry.description.lower()

    def test_roll_4_double_damage(self) -> None:
        entry = get_critical_hit_effect(4)
        assert entry.damage_multiplier == 2 or "double" in entry.description.lower()


# ---------------------------------------------------------------------------
# Critical Miss Table (B556)
# ---------------------------------------------------------------------------


class TestCriticalMissTable:
    def test_returns_critical_miss_entry(self) -> None:
        entry = get_critical_miss_effect(9)
        assert isinstance(entry, CriticalMissEntry)

    def test_all_rolls_3_to_18_covered(self) -> None:
        for roll in range(3, 19):
            entry = get_critical_miss_effect(roll)
            assert entry is not None
            assert entry.description

    def test_roll_3_weapon_breaks(self) -> None:
        entry = get_critical_miss_effect(3)
        assert "break" in entry.description.lower() or entry.weapon_breaks

    def test_roll_16_attacker_falls(self) -> None:
        entry = get_critical_miss_effect(16)
        assert "fall" in entry.description.lower() or entry.attacker_falls

    def test_roll_17_weapon_breaks(self) -> None:
        entry = get_critical_miss_effect(17)
        assert "break" in entry.description.lower() or entry.weapon_breaks

    def test_roll_18_weapon_breaks(self) -> None:
        entry = get_critical_miss_effect(18)
        assert "break" in entry.description.lower() or entry.weapon_breaks
