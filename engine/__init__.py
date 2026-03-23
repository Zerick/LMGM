"""GURPS rules engine — deterministic mechanical resolution.

Public API exports for use by the orchestrator and other modules.
Never import internal functions directly; use only what is exported here.

Modules:
    dice    — All dice rolling functions and result dataclasses.
    tables  — GURPS lookup tables (hit location, critical, reaction, etc.).
    combat  — Full attack-defense-damage-wound pipeline.
"""
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
from engine.tables import (
    CriticalHitEntry,
    CriticalMissEntry,
    HitLocationEntry,
    get_critical_hit_effect,
    get_critical_miss_effect,
    get_hit_location,
    get_reaction_level,
    get_size_speed_range_modifier,
    roll_hit_location,
)
from engine.combat import (
    AttackAction,
    CombatResult,
    DamageType,
    Maneuver,
    Modifier,
    Weapon,
    MANEUVER_REGISTRY,
    apply_damage_minimum,
    apply_dr,
    attack_roll,
    calculate_injury,
    check_wound_effects,
    defense_roll,
    get_wound_multiplier,
    hit_location_roll,
    resolve_attack,
)

__all__ = [
    # dice
    "CheckResult",
    "ContestResult",
    "FrightResult",
    "ReactionResult",
    "RollResult",
    "damage_roll",
    "fright_check",
    "quick_contest",
    "reaction_roll",
    "roll_3d6",
    "success_check",
    # tables
    "CriticalHitEntry",
    "CriticalMissEntry",
    "HitLocationEntry",
    "get_critical_hit_effect",
    "get_critical_miss_effect",
    "get_hit_location",
    "get_reaction_level",
    "get_size_speed_range_modifier",
    "roll_hit_location",
    # combat
    "AttackAction",
    "CombatResult",
    "DamageType",
    "Maneuver",
    "Modifier",
    "Weapon",
    "MANEUVER_REGISTRY",
    "apply_damage_minimum",
    "apply_dr",
    "attack_roll",
    "calculate_injury",
    "check_wound_effects",
    "defense_roll",
    "get_wound_multiplier",
    "hit_location_roll",
    "resolve_attack",
]
