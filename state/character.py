"""GURPS character data model.

All character data is represented as Pydantic models for validation and
serialization. Two output formats are supported:
- Full JSON (to_json): for SQLite storage and round-tripping.
- LLM summary (to_llm_summary): condensed text for prompt injection.
"""

import math
from typing import Any, Optional
from pydantic import BaseModel, Field, model_validator


class SkillEntry(BaseModel):
    """A single skill with its effective level and metadata."""

    level: int
    attribute: str  # "DX", "IQ", "HT", etc.
    difficulty: str  # "E", "A", "H", "VH"
    defaults: list[str] = Field(default_factory=list)


class Advantage(BaseModel):
    """An advantage or disadvantage (negative point_cost = disadvantage)."""

    name: str
    level: int
    point_cost: int
    mechanical_effects: dict[str, Any] = Field(default_factory=dict)


class Item(BaseModel):
    """A piece of equipment — weapon, armor, or mundane item."""

    name: str
    weight: float
    dr: Optional[int] = None       # Damage resistance (armor only)
    damage: Optional[str] = None   # Damage expression (weapon only), e.g. "2d+1 cut"
    location: str                  # Worn/carried location: "hand", "torso", "arm", "pack"


class ParryEntry(BaseModel):
    """Parry score for a specific weapon."""

    weapon: str
    score: int


class ActiveEffect(BaseModel):
    """A temporary mechanical effect on the character."""

    name: str
    duration: Optional[int] = None  # Turns remaining; None = indefinite
    mechanical_effects: dict[str, Any] = Field(default_factory=dict)


class Character(BaseModel):
    """Full GURPS 4th Edition character data model.

    Secondary attributes (HP, FP, Will, Per, Basic_Speed, Basic_Move) default
    to their standard derived values if not supplied, but can be overridden
    for characters who have bought them up or down.

    current_hp and current_fp default to the character's HP and FP maximums.
    """

    # --- Identity ---
    name: str
    player_discord_id: str
    point_total: int
    notes: str = ""

    # --- Primary Attributes ---
    ST: int
    DX: int
    IQ: int
    HT: int

    # --- Secondary Attributes (with derived defaults) ---
    HP: Optional[int] = None
    FP: Optional[int] = None
    Will: Optional[int] = None
    Per: Optional[int] = None
    Basic_Speed: Optional[float] = None
    Basic_Move: Optional[int] = None

    # --- Current State ---
    current_hp: Optional[int] = None
    current_fp: Optional[int] = None
    conditions: list[str] = Field(default_factory=list)

    # --- Skills ---
    skills: dict[str, SkillEntry] = Field(default_factory=dict)

    # --- Advantages / Disadvantages ---
    advantages: list[Advantage] = Field(default_factory=list)

    # --- Equipment ---
    equipment: list[Item] = Field(default_factory=list)

    # --- Combat Stats ---
    dodge: int
    parry_skills: list[ParryEntry] = Field(default_factory=list)
    block_skill: Optional[int] = None

    # --- Active Effects ---
    active_effects: list[ActiveEffect] = Field(default_factory=list)

    @model_validator(mode="after")
    def _fill_derived_attributes(self) -> "Character":
        """Compute secondary attributes if not explicitly set."""
        if self.HP is None:
            self.HP = self.ST
        if self.FP is None:
            self.FP = self.HT
        if self.Will is None:
            self.Will = self.IQ
        if self.Per is None:
            self.Per = self.IQ
        if self.Basic_Speed is None:
            self.Basic_Speed = (self.HT + self.DX) / 4.0
        if self.Basic_Move is None:
            self.Basic_Move = math.floor(self.Basic_Speed)
        if self.current_hp is None:
            self.current_hp = self.HP
        if self.current_fp is None:
            self.current_fp = self.FP
        return self

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_json(self) -> str:
        """Return full JSON string for SQLite storage."""
        return self.model_dump_json()

    def to_llm_summary(self) -> str:
        """Return a condensed text block for LLM prompt injection.

        Format mirrors the blueprint example:
            [Name] ST N DX N IQ N HT N | HP N/N FP N/N
            Skills: Skill-N, Skill-N
            Advantages: Adv1, Adv2
            Equipment: Item (details), Item (details)
            Dodge N, Parry N (Weapon), Block N
            Status: <conditions or 'healthy, no active effects'>
        """
        lines: list[str] = []

        # Line 1: attributes + HP/FP
        lines.append(
            f"[{self.name}] ST {self.ST} DX {self.DX} IQ {self.IQ} HT {self.HT}"
            f" | HP {self.current_hp}/{self.HP} FP {self.current_fp}/{self.FP}"
        )

        # Line 2: Skills
        if self.skills:
            skill_parts = [f"{name}-{entry.level}" for name, entry in self.skills.items()]
            lines.append(f"Skills: {', '.join(skill_parts)}")
        else:
            lines.append("Skills: none")

        # Line 3: Advantages
        if self.advantages:
            adv_parts = [adv.name for adv in self.advantages]
            lines.append(f"Advantages: {', '.join(adv_parts)}")
        else:
            lines.append("Advantages: none")

        # Line 4: Equipment
        if self.equipment:
            eq_parts: list[str] = []
            for item in self.equipment:
                desc = item.name
                extras: list[str] = []
                if item.damage:
                    extras.append(item.damage)
                if item.dr is not None:
                    extras.append(f"DR {item.dr}")
                if extras:
                    desc += f" ({', '.join(extras)})"
                eq_parts.append(desc)
            lines.append(f"Equipment: {', '.join(eq_parts)}")
        else:
            lines.append("Equipment: none")

        # Line 5: Combat stats
        combat_parts = [f"Dodge {self.dodge}"]
        for parry in self.parry_skills:
            combat_parts.append(f"Parry {parry.score} ({parry.weapon})")
        if self.block_skill is not None:
            combat_parts.append(f"Block {self.block_skill}")
        lines.append(", ".join(combat_parts))

        # Line 6: Status
        all_status: list[str] = list(self.conditions)
        for eff in self.active_effects:
            all_status.append(eff.name.lower())
        if all_status:
            lines.append(f"Status: {', '.join(all_status)}")
        else:
            lines.append("Status: healthy, no active effects")

        # Notes (GM-written personality/relationship text — only injected if present)
        if self.notes:
            lines.append(f"Notes: {self.notes}")

        return "\n".join(lines)
