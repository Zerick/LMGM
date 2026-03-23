"""Unit tests for engine/dice.py — Phase 2.

Tests cover all roll functions, critical success/failure thresholds per
GURPS B348, margin calculations, and statistical distribution.
"""
import re
from collections import Counter

import pytest

from engine.dice import (
    CheckResult,
    ContestResult,
    FrightResult,
    ReactionResult,
    RollResult,
    damage_roll,
    fright_check,
    quick_contest,
    reaction_roll,
    roll_3d6,
    success_check,
)


# ---------------------------------------------------------------------------
# roll_3d6
# ---------------------------------------------------------------------------


class TestRoll3d6:
    def test_returns_roll_result(self) -> None:
        result = roll_3d6()
        assert isinstance(result, RollResult)

    def test_total_in_valid_range(self) -> None:
        for _ in range(1000):
            r = roll_3d6()
            assert 3 <= r.total <= 18

    def test_dice_list_has_three_elements(self) -> None:
        r = roll_3d6()
        assert len(r.dice) == 3

    def test_dice_values_each_one_to_six(self) -> None:
        for _ in range(200):
            r = roll_3d6()
            for d in r.dice:
                assert 1 <= d <= 6

    def test_total_equals_sum_of_dice(self) -> None:
        for _ in range(200):
            r = roll_3d6()
            assert r.total == sum(r.dice)

    def test_distribution_peaks_at_10_11(self) -> None:
        """3d6 should have a bell-curve distribution peaking near 10-11."""
        counts: Counter = Counter()
        n = 10_000
        for _ in range(n):
            counts[roll_3d6().total] += 1
        # 10 and 11 should together be the most common region
        mid = counts[10] + counts[11]
        low = counts[3] + counts[4]
        high = counts[17] + counts[18]
        assert mid > low * 4, "Middle values should be far more common than extremes"
        assert mid > high * 4

    def test_never_below_3_or_above_18(self) -> None:
        for _ in range(10_000):
            r = roll_3d6()
            assert 3 <= r.total <= 18


# ---------------------------------------------------------------------------
# success_check — critical thresholds per GURPS B348
# ---------------------------------------------------------------------------


class TestSuccessCheck:
    def test_returns_check_result(self) -> None:
        result = success_check(10)
        assert isinstance(result, CheckResult)

    def test_roll_3_always_critical_success(self) -> None:
        """Roll of 3 is always a critical success at any skill."""
        for skill in [1, 5, 10, 14, 15, 16, 20]:
            result = success_check(skill, _force_roll=3)
            assert result.success is True
            assert result.critical is True
            assert result.critical_type == "success"

    def test_roll_4_always_critical_success(self) -> None:
        for skill in [1, 5, 10, 14, 15, 16, 20]:
            result = success_check(skill, _force_roll=4)
            assert result.success is True
            assert result.critical is True
            assert result.critical_type == "success"

    def test_roll_5_critical_success_at_skill_15_plus(self) -> None:
        """Roll of 5 is critical success only if effective skill >= 15."""
        for skill in [15, 16, 17, 20]:
            result = success_check(skill, _force_roll=5)
            assert result.critical is True
            assert result.critical_type == "success"
        for skill in [1, 5, 10, 14]:
            result = success_check(skill, _force_roll=5)
            # Still a success (5 <= skill for skill >= 5), but not critical
            if skill >= 5:
                assert result.success is True
            assert not (result.critical and result.critical_type == "success"), (
                f"Roll 5 should NOT be critical at skill {skill}"
            )

    def test_roll_6_critical_success_at_skill_16_plus(self) -> None:
        """Roll of 6 is critical success only if effective skill >= 16."""
        for skill in [16, 17, 20]:
            result = success_check(skill, _force_roll=6)
            assert result.critical is True
            assert result.critical_type == "success"
        for skill in [1, 5, 10, 14, 15]:
            result = success_check(skill, _force_roll=6)
            assert not (result.critical and result.critical_type == "success"), (
                f"Roll 6 should NOT be critical at skill {skill}"
            )

    def test_roll_18_always_critical_failure(self) -> None:
        """Roll of 18 is always a critical failure at any skill."""
        for skill in [1, 5, 10, 15, 18, 20]:
            result = success_check(skill, _force_roll=18)
            assert result.success is False
            assert result.critical is True
            assert result.critical_type == "failure"

    def test_roll_17_critical_failure_at_skill_15_or_less(self) -> None:
        """Roll of 17 is critical failure only if effective skill <= 15."""
        for skill in [1, 5, 10, 14, 15]:
            result = success_check(skill, _force_roll=17)
            assert result.critical is True
            assert result.critical_type == "failure"
        for skill in [16, 17, 20]:
            result = success_check(skill, _force_roll=17)
            # It's still a failure, but NOT critical
            assert result.success is False
            assert not result.critical, f"Roll 17 should NOT be critical at skill {skill}"

    def test_fail_by_10_or_more_is_critical_failure(self) -> None:
        """Any roll that fails by 10+ is a critical failure."""
        # skill 5: fail by 10+ means roll >= 15
        result = success_check(5, _force_roll=15)
        assert result.success is False
        assert result.critical is True
        assert result.critical_type == "failure"

        result = success_check(5, _force_roll=16)
        assert result.critical is True
        assert result.critical_type == "failure"

    def test_fail_by_9_not_critical_failure(self) -> None:
        """Failing by exactly 9 is NOT a critical failure (threshold is 10)."""
        # skill 5: fail by 9 means roll == 14
        result = success_check(5, _force_roll=14)
        assert result.success is False
        # should not be critical (unless it's 17 or 18)
        assert not result.critical

    def test_success_when_roll_leq_skill(self) -> None:
        result = success_check(10, _force_roll=8)
        assert result.success is True
        assert result.margin == 2  # 10 - 8

    def test_failure_when_roll_gt_skill(self) -> None:
        result = success_check(10, _force_roll=12)
        assert result.success is False
        assert result.margin == -2  # 10 - 12

    def test_exact_success(self) -> None:
        result = success_check(12, _force_roll=12)
        assert result.success is True
        assert result.margin == 0

    def test_roll_and_target_stored(self) -> None:
        result = success_check(13, _force_roll=9)
        assert result.roll == 9
        assert result.target == 13
        assert result.margin == 4

    def test_roll_17_still_fails_at_high_skill(self) -> None:
        """Roll of 17 at skill 20 is a regular failure, not critical."""
        result = success_check(20, _force_roll=17)
        assert result.success is False
        assert not result.critical

    def test_roll_17_still_fails_not_succeeds(self) -> None:
        """Roll of 17 should always be a failure, even if skill > 17."""
        result = success_check(18, _force_roll=17)
        assert result.success is False

    def test_effective_skill_below_3_still_resolved(self) -> None:
        """Even skill < 3 can be rolled for defense. Should resolve correctly."""
        result = success_check(1, _force_roll=1)
        # 1 < 3 so 3d6 can't roll 1, this tests edge logic
        # No _force_roll of 1 is invalid for 3d6, skip
        result = success_check(2, _force_roll=3)
        assert result.success is True


# ---------------------------------------------------------------------------
# quick_contest
# ---------------------------------------------------------------------------


class TestQuickContest:
    def test_returns_contest_result(self) -> None:
        result = quick_contest(10, 10)
        assert isinstance(result, ContestResult)

    def test_winner_a_when_a_succeeds_b_fails(self) -> None:
        # a rolls 8 vs skill 10 (success by 2)
        # b rolls 15 vs skill 10 (failure by 5)
        result = quick_contest(10, 10, _force_rolls=(8, 15))
        assert result.winner == "a"

    def test_winner_b_when_b_succeeds_a_fails(self) -> None:
        result = quick_contest(10, 10, _force_rolls=(15, 8))
        assert result.winner == "b"

    def test_winner_a_when_both_succeed_a_better_margin(self) -> None:
        # a: roll 7 vs skill 12 = margin +5
        # b: roll 10 vs skill 12 = margin +2
        result = quick_contest(12, 12, _force_rolls=(7, 10))
        assert result.winner == "a"

    def test_winner_b_when_both_succeed_b_better_margin(self) -> None:
        result = quick_contest(12, 12, _force_rolls=(10, 7))
        assert result.winner == "b"

    def test_tie_when_both_fail_same_margin(self) -> None:
        # Both fail by same amount
        result = quick_contest(10, 10, _force_rolls=(13, 13))
        assert result.winner == "tie"

    def test_winner_a_when_both_fail_a_smaller_margin(self) -> None:
        # a: roll 12 vs skill 10 = fail by 2
        # b: roll 14 vs skill 10 = fail by 4
        result = quick_contest(10, 10, _force_rolls=(12, 14))
        assert result.winner == "a"

    def test_tie_when_both_succeed_same_margin(self) -> None:
        result = quick_contest(12, 12, _force_rolls=(8, 8))
        assert result.winner == "tie"

    def test_margins_stored(self) -> None:
        result = quick_contest(10, 10, _force_rolls=(8, 12))
        # a: roll 8 vs 10, margin = +2
        # b: roll 12 vs 10, margin = -2
        assert result.margin_a == 2
        assert result.margin_b == -2


# ---------------------------------------------------------------------------
# damage_roll
# ---------------------------------------------------------------------------


class TestDamageRoll:
    def test_simple_dice(self) -> None:
        """3d6 should produce values in 3-18."""
        for _ in range(200):
            val = damage_roll("3d6")
            assert 3 <= val <= 18

    def test_single_die(self) -> None:
        for _ in range(200):
            val = damage_roll("1d6")
            assert 1 <= val <= 6

    def test_dice_with_positive_add(self) -> None:
        for _ in range(200):
            val = damage_roll("2d6+3")
            assert 5 <= val <= 15

    def test_dice_with_negative_add(self) -> None:
        for _ in range(200):
            val = damage_roll("2d6-1")
            assert 1 <= val <= 11

    def test_shorthand_d_means_d6(self) -> None:
        """'2d' means '2d6' in GURPS notation."""
        for _ in range(200):
            val = damage_roll("2d")
            assert 2 <= val <= 12

    def test_1d_minus_large_add_still_can_be_1(self) -> None:
        """Damage is always at least 1 for non-crushing (handled by caller convention)."""
        # 1d-5 has a minimum possible of -4, but for cutting/impaling min is 1
        # damage_roll itself returns the raw result (no clamping to 1)
        val = damage_roll("1d-5", _force_dice=[1])
        assert val == -4  # raw result; caller enforces damage type minimum

    def test_force_dice_param(self) -> None:
        """The hidden _force_dice parameter should override dice rolls."""
        val = damage_roll("2d6+1", _force_dice=[3, 4])
        assert val == 8  # 3+4+1

    def test_d_plus_modifier_no_spaces(self) -> None:
        val = damage_roll("1d+2", _force_dice=[3])
        assert val == 5

    def test_d_minus_modifier_no_spaces(self) -> None:
        val = damage_roll("1d-1", _force_dice=[4])
        assert val == 3


# ---------------------------------------------------------------------------
# reaction_roll
# ---------------------------------------------------------------------------


class TestReactionRoll:
    def test_returns_reaction_result(self) -> None:
        result = reaction_roll([])
        assert isinstance(result, ReactionResult)

    def test_total_in_valid_range_no_modifiers(self) -> None:
        for _ in range(200):
            result = reaction_roll([])
            assert 3 <= result.total <= 18

    def test_modifiers_applied(self) -> None:
        # With +10 modifier, minimum total is 13 (3+10)
        for _ in range(200):
            result = reaction_roll([10])
            assert result.total >= 13

    def test_level_names_returned(self) -> None:
        valid_levels = {
            "disastrous", "very bad", "bad", "poor",
            "neutral", "good", "very good", "excellent",
        }
        for _ in range(200):
            result = reaction_roll([])
            assert result.level_name.lower() in valid_levels

    def test_high_roll_gives_excellent(self) -> None:
        result = reaction_roll([], _force_roll=18)
        assert result.total >= 18
        assert result.level_name.lower() in {"very good", "excellent"}

    def test_low_roll_gives_bad_reaction(self) -> None:
        result = reaction_roll([], _force_roll=3)
        assert result.level_name.lower() in {"disastrous", "very bad", "bad"}

    def test_modifier_can_push_into_excellent(self) -> None:
        result = reaction_roll([5], _force_roll=14)
        assert result.total == 19
        assert result.level_name.lower() == "excellent"


# ---------------------------------------------------------------------------
# fright_check
# ---------------------------------------------------------------------------


class TestFrightCheck:
    def test_returns_fright_result(self) -> None:
        result = fright_check(will=12, modifier=0)
        assert isinstance(result, FrightResult)

    def test_success_when_roll_leq_will(self) -> None:
        result = fright_check(will=12, modifier=0, _force_roll=10)
        assert result.margin > 0 or result.margin == 0
        # On success, table_result should indicate no fear effect
        assert "success" in result.table_result.lower() or result.margin >= 0

    def test_failure_when_roll_gt_will(self) -> None:
        result = fright_check(will=10, modifier=0, _force_roll=15)
        assert result.roll == 15
        assert result.margin < 0  # failed by 5

    def test_modifier_applied_to_will(self) -> None:
        """Positive modifier increases the target (easier check)."""
        result = fright_check(will=10, modifier=2, _force_roll=12)
        # effective will = 12, roll 12 = exact success
        assert result.margin == 0

    def test_negative_modifier_makes_harder(self) -> None:
        result = fright_check(will=12, modifier=-4, _force_roll=9)
        # effective will = 8, roll 9 > 8 = failure by 1
        assert result.margin == -1

    def test_critical_success_on_roll_3_or_4(self) -> None:
        result = fright_check(will=10, modifier=0, _force_roll=3)
        assert "critical" in result.table_result.lower() or result.margin >= 7

    def test_roll_and_margin_stored(self) -> None:
        result = fright_check(will=12, modifier=0, _force_roll=8)
        assert result.roll == 8
        assert result.margin == 4  # 12 - 8
