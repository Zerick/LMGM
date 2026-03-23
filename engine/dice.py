"""Deterministic GURPS dice rolling functions.

All randomness in GURPS flows through 3d6. This module provides every roll
type the rules engine needs. Return types are typed dataclasses — callers
never receive raw ints or tuples.

Critical success/failure thresholds follow GURPS B348 exactly:
  Critical success: roll 3 or 4 always; roll 5 if skill >= 15; roll 6 if skill >= 16.
  Critical failure: roll 18 always; roll 17 if skill <= 15; any roll failing by 10+.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class RollResult:
    """Raw 3d6 roll — no skill context."""

    total: int
    dice: list[int]
    is_critical_success: bool  # 3 or 4 (base thresholds, no skill)
    is_critical_failure: bool  # 17 or 18 (base thresholds, no skill)


@dataclass
class CheckResult:
    """Result of a success roll against an effective skill."""

    roll: int
    target: int        # effective skill used for the roll
    margin: int        # target - roll; positive = success, negative = failure
    success: bool
    critical: bool     # True when result is critical (either type)
    critical_type: str  # "success", "failure", or "none"


@dataclass
class ContestResult:
    """Result of a Quick Contest between two parties."""

    roll_a: int
    roll_b: int
    margin_a: int  # positive = succeeded by that much, negative = failed by that much
    margin_b: int
    winner: str    # "a", "b", or "tie"


@dataclass
class ReactionResult:
    """Result of a reaction roll (NPC attitude toward PCs)."""

    total: int
    level_name: str


@dataclass
class FrightResult:
    """Result of a fright check (Will roll to resist fear)."""

    roll: int
    margin: int        # effective_will - roll; positive = passed, negative = failed
    table_result: str  # description of effect


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _roll_dice(num_dice: int = 3, sides: int = 6) -> list[int]:
    """Roll num_dice d sides and return individual die values."""
    return [random.randint(1, sides) for _ in range(num_dice)]


def _is_critical_success(roll: int, skill: int) -> bool:
    """Return True if roll qualifies as a critical success at the given effective skill.

    Rules per GURPS B348:
      - Roll of 3 or 4: always critical success.
      - Roll of 5: critical success if skill >= 15.
      - Roll of 6: critical success if skill >= 16.
    """
    if roll <= 4:
        return True
    if roll == 5 and skill >= 15:
        return True
    if roll == 6 and skill >= 16:
        return True
    return False


def _is_critical_failure(roll: int, skill: int) -> bool:
    """Return True if roll qualifies as a critical failure at the given effective skill.

    Rules per GURPS B348:
      - Roll of 18: always critical failure.
      - Roll of 17: critical failure if skill <= 15.
      - Any roll that fails by 10 or more (i.e., roll >= skill + 10).
    """
    if roll == 18:
        return True
    if roll == 17 and skill <= 15:
        return True
    if roll >= skill + 10:
        return True
    return False


# ---------------------------------------------------------------------------
# Reaction level lookup
# ---------------------------------------------------------------------------

_REACTION_LEVELS: list[tuple[int, str]] = [
    # (max_total_inclusive, level_name) — GURPS Lite reaction table
    (3, "Very Bad"),
    (6, "Bad"),
    (9, "Poor"),
    (12, "Neutral"),
    (15, "Good"),
    (18, "Very Good"),
    (9999, "Excellent"),
]


def _reaction_level(total: int) -> str:
    """Return reaction level name for a given total (with modifiers applied).

    Per GURPS Lite: 0 or less = Disastrous, 1-3 = Very Bad, 4-6 = Bad,
    7-9 = Poor, 10-12 = Neutral, 13-15 = Good, 16-18 = Very Good, 19+ = Excellent.
    """
    if total <= 0:
        return "Disastrous"
    for threshold, name in _REACTION_LEVELS:
        if total <= threshold:
            return name
    return "Excellent"


# ---------------------------------------------------------------------------
# Fright check table (simplified from GURPS B360)
# ---------------------------------------------------------------------------

def _fright_table_result(margin: int, roll: int) -> str:
    """Return a fright check table result description.

    Args:
        margin: effective_will - roll (negative = failed, positive/0 = passed).
        roll: the actual 3d6 roll.
    """
    if margin >= 0:
        if roll <= 4:
            return "Critical success — no effect, iron nerves."
        return "Success — no fear effect."

    # Failed — severity scales with margin of failure
    fail_by = abs(margin)
    if fail_by <= 2:
        return f"Stunned for {fail_by + 1} second(s); roll HT to recover each turn."
    if fail_by <= 4:
        return "Stunned for 1d seconds; minor panic."
    if fail_by <= 6:
        return "Stunned for 2d seconds; flee in panic if possible."
    if fail_by <= 8:
        return "Stunned for 3d seconds; scream, drop held items."
    if fail_by <= 10:
        return "Faint for 1d minutes."
    return "Severe fright — faint for 1d minutes, possible lasting phobia (GM's discretion)."


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def roll_3d6(_force_roll: int | None = None) -> RollResult:
    """Roll 3d6 and return the result with individual die values.

    Args:
        _force_roll: Internal testing parameter — forces the total to a fixed
            value (dice list will be fabricated). Do not use in production.

    Returns:
        RollResult with total, individual dice, and base critical flags
        (using roll-only thresholds: crit success on 3-4, crit fail on 17-18).
    """
    if _force_roll is not None:
        # Fabricate a valid dice list that sums to _force_roll
        total = _force_roll
        dice = _fabricate_dice(total)
    else:
        dice = _roll_dice(3, 6)
        total = sum(dice)

    # Base critical flags use skill-agnostic thresholds
    is_crit_success = total <= 4
    is_crit_failure = total >= 17

    return RollResult(
        total=total,
        dice=dice,
        is_critical_success=is_crit_success,
        is_critical_failure=is_crit_failure,
    )


def _fabricate_dice(total: int) -> list[int]:
    """Produce a 3-element list of valid d6 values summing to total.

    Used only for testing — not part of the public API.
    """
    # Clamp to valid 3d6 range
    total = max(3, min(18, total))
    # Simple: put remainder in last die
    remaining = total
    dice: list[int] = []
    for i in range(3):
        slots_left = 3 - i
        low = max(1, remaining - 6 * (slots_left - 1))
        high = min(6, remaining - (slots_left - 1))
        val = max(low, min(high, remaining - (slots_left - 1)))
        dice.append(val)
        remaining -= val
    return dice


def success_check(
    skill_level: int,
    _force_roll: int | None = None,
) -> CheckResult:
    """Attempt a success roll against an effective skill level.

    The skill_level parameter should already incorporate all modifiers
    (base skill + situational bonuses/penalties = effective skill).

    Args:
        skill_level: The effective skill level to roll against.
        _force_roll: Testing parameter — forces the 3d6 total.

    Returns:
        CheckResult with roll, target, margin, success flag, and critical info.
    """
    if _force_roll is not None:
        roll = _force_roll
    else:
        roll = sum(_roll_dice(3, 6))

    margin = skill_level - roll
    success = roll <= skill_level

    # Rolls of 17-18 always fail regardless of skill
    if roll >= 17:
        success = False

    crit_success = _is_critical_success(roll, skill_level)
    crit_failure = _is_critical_failure(roll, skill_level)

    # Rolls of 3 or 4 are always a success (GURPS Lite p.2: "a roll of 3 or 4 is always a success")
    # This means critical success always implies success for those threshold rolls.
    if crit_success and roll <= 4:
        success = True

    # A critical success can only happen on an actual success
    # A critical failure can only happen on an actual failure
    if crit_success and crit_failure:
        # Edge case: fail by 10+ AND roll <= 4 (skill very low).
        # Critical failure takes precedence for rolls that also fail.
        if not success:
            crit_success = False
        else:
            crit_failure = False

    if crit_success:
        critical = True
        critical_type = "success"
    elif crit_failure:
        critical = True
        critical_type = "failure"
    else:
        critical = False
        critical_type = "none"

    return CheckResult(
        roll=roll,
        target=skill_level,
        margin=margin,
        success=success,
        critical=critical,
        critical_type=critical_type,
    )


def quick_contest(
    skill_a: int,
    skill_b: int,
    _force_rolls: tuple[int, int] | None = None,
) -> ContestResult:
    """Resolve a Quick Contest between two parties.

    Each party rolls against their effective skill. Ties in margin go to
    neither party (result is "tie"). Rules from GURPS Lite p. 2.

    Args:
        skill_a: Effective skill of party A.
        skill_b: Effective skill of party B.
        _force_rolls: Testing parameter — (roll_a, roll_b) tuple.

    Returns:
        ContestResult with rolls, margins, and winner identifier.
    """
    if _force_rolls is not None:
        roll_a, roll_b = _force_rolls
    else:
        roll_a = sum(_roll_dice(3, 6))
        roll_b = sum(_roll_dice(3, 6))

    check_a = success_check(skill_a, _force_roll=roll_a)
    check_b = success_check(skill_b, _force_roll=roll_b)

    margin_a = check_a.margin
    margin_b = check_b.margin

    # Determine winner per GURPS Quick Contest rules
    if check_a.success and not check_b.success:
        winner = "a"
    elif check_b.success and not check_a.success:
        winner = "b"
    elif check_a.success and check_b.success:
        # Both succeeded — larger margin wins; tie if equal
        if margin_a > margin_b:
            winner = "a"
        elif margin_b > margin_a:
            winner = "b"
        else:
            winner = "tie"
    else:
        # Both failed — smaller margin-of-failure wins (less negative margin)
        if margin_a > margin_b:
            winner = "a"
        elif margin_b > margin_a:
            winner = "b"
        else:
            winner = "tie"

    return ContestResult(
        roll_a=roll_a,
        roll_b=roll_b,
        margin_a=margin_a,
        margin_b=margin_b,
        winner=winner,
    )


def damage_roll(
    dice_str: str,
    _force_dice: list[int] | None = None,
) -> int:
    """Parse and roll a GURPS damage expression.

    Accepted formats: '2d6', '1d6+3', '2d+1', '1d-2', '3d'.
    In GURPS notation 'd' without a sides number means d6.

    Note on minimums: This function returns the raw total (which may be
    negative). Callers should enforce type-specific minimums:
      - Non-crushing damage: minimum 1 (if penetration occurs)
      - Crushing damage: minimum 0

    Args:
        dice_str: GURPS damage expression string.
        _force_dice: Testing parameter — individual die values to use instead
            of random rolls. Must match the number of dice in dice_str.

    Returns:
        Raw damage total before any type-specific clamping.

    Raises:
        ValueError: If dice_str cannot be parsed.
    """
    dice_str = dice_str.strip().lower().replace(" ", "")

    # Pattern: optional int, 'd', optional sides, optional +/- modifier
    pattern = r"^(\d*)d(\d*)?([+-]\d+)?$"
    m = re.match(pattern, dice_str)
    if not m:
        raise ValueError(f"Cannot parse damage expression: {dice_str!r}")

    num_str, sides_str, add_str = m.group(1), m.group(2), m.group(3)

    num_dice = int(num_str) if num_str else 1
    sides = int(sides_str) if sides_str else 6
    add = int(add_str) if add_str else 0

    if _force_dice is not None:
        if len(_force_dice) != num_dice:
            raise ValueError(
                f"_force_dice has {len(_force_dice)} values but expression "
                f"needs {num_dice} dice."
            )
        dice_values = _force_dice
    else:
        dice_values = _roll_dice(num_dice, sides)

    return sum(dice_values) + add


def reaction_roll(
    modifiers: list[int],
    _force_roll: int | None = None,
) -> ReactionResult:
    """Roll for NPC reaction to the party.

    Roll 3d6 and apply all modifiers. High totals are better.
    A roll of 19+ is "Excellent"; 0 or less is "Disastrous".

    Args:
        modifiers: List of integer bonuses/penalties to apply to the roll.
        _force_roll: Testing parameter — forces the base 3d6 total.

    Returns:
        ReactionResult with total (post-modifier) and level name.
    """
    if _force_roll is not None:
        base = _force_roll
    else:
        base = sum(_roll_dice(3, 6))

    total = base + sum(modifiers)
    return ReactionResult(total=total, level_name=_reaction_level(total))


def fright_check(
    will: int,
    modifier: int,
    _force_roll: int | None = None,
) -> FrightResult:
    """Resolve a Fright Check (Will roll to resist fear).

    Effective will = will + modifier. Roll 3d6 against effective will.

    Args:
        will: Base Will score of the character.
        modifier: Situational bonus (positive) or penalty (negative).
        _force_roll: Testing parameter — forces the 3d6 total.

    Returns:
        FrightResult with roll, margin, and table result description.
    """
    effective_will = will + modifier

    if _force_roll is not None:
        roll = _force_roll
    else:
        roll = sum(_roll_dice(3, 6))

    margin = effective_will - roll
    table_result = _fright_table_result(margin, roll)

    return FrightResult(roll=roll, margin=margin, table_result=table_result)
