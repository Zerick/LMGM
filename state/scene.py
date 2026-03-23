"""Scene state tracking for the GURPS GM bot.

SceneState is the LLM's primary source of truth about the current game
situation. It is assembled fresh each turn and injected into the prompt
via to_prompt_text().
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CharacterSummary(BaseModel):
    """Lightweight character reference for use within a scene."""

    character_id: str
    name: str
    summary: str  # Output of Character.to_llm_summary()


class ActionRecord(BaseModel):
    """Record of a single action taken during a scene."""

    character_id: str
    action_description: str
    result_summary: str
    timestamp: datetime


class CombatState(BaseModel):
    """Tracks the mechanical state of an active combat encounter."""

    round_number: int
    turn_order: list[str]           # Character IDs sorted by Basic Speed
    current_turn: str               # ID of the character acting now
    active_maneuvers: dict[str, str]  # character_id → declared maneuver
    position_notes: str             # Narrative relative positions


class SceneState(BaseModel):
    """Complete state of the current game scene for LLM injection."""

    scene_id: str
    description: str
    scene_type: str  # 'combat', 'exploration', 'social', 'downtime'
    characters_present: list[CharacterSummary]
    recent_actions: list[ActionRecord]  # Full list stored; prompt shows last 5
    active_effects: list[str] = Field(default_factory=list)
    combat_state: Optional[CombatState] = None

    def to_prompt_text(self) -> str:
        """Format the scene state as a text block for LLM prompt injection.

        Includes: scene type, description, characters, active effects,
        recent actions (last 5), and combat state when applicable.
        """
        parts: list[str] = []

        # Scene header
        parts.append(f"SCENE [{self.scene_type.upper()}]: {self.description}")

        # Characters present
        if self.characters_present:
            parts.append("\nCHARACTERS PRESENT:")
            for cs in self.characters_present:
                parts.append(cs.summary)

        # Active environmental effects
        if self.active_effects:
            parts.append(f"\nACTIVE CONDITIONS: {', '.join(self.active_effects)}")

        # Recent actions (last 5)
        last_five = self.recent_actions[-5:] if len(self.recent_actions) > 5 else self.recent_actions
        if last_five:
            parts.append("\nRECENT ACTIONS:")
            for action in last_five:
                ts = action.timestamp.strftime("%H:%M")
                parts.append(f"  [{ts}] {action.action_description} → {action.result_summary}")

        # Combat state block
        if self.combat_state is not None:
            cs = self.combat_state
            parts.append(f"\nCOMBAT — Round {cs.round_number}")
            parts.append(f"  Turn order: {', '.join(cs.turn_order)}")
            parts.append(f"  Current turn: {cs.current_turn}")
            if cs.active_maneuvers:
                maneuvers = ", ".join(f"{cid}: {m}" for cid, m in cs.active_maneuvers.items())
                parts.append(f"  Declared maneuvers: {maneuvers}")
            if cs.position_notes:
                parts.append(f"  Positions: {cs.position_notes}")

        return "\n".join(parts)
