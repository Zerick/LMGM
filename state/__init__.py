"""State module — character models, scene tracking, and SQLite persistence."""

from state.campaign import CampaignManager
from state.character import ActiveEffect, Advantage, Character, Item, ParryEntry, SkillEntry
from state.db import Database
from state.scene import ActionRecord, CharacterSummary, CombatState, SceneState

__all__ = [
    "ActiveEffect",
    "Advantage",
    "ActionRecord",
    "CampaignManager",
    "Character",
    "CharacterSummary",
    "CombatState",
    "Database",
    "Item",
    "ParryEntry",
    "SceneState",
    "SkillEntry",
]
