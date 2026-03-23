"""Tests for state/character.py — GURPS character data model.

Tests written BEFORE implementation per project testing rules.
"""

import json
import pytest
from state.character import (
    ActiveEffect,
    Advantage,
    Character,
    Item,
    SkillEntry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def bjorn_data() -> dict:
    """Return a full character dict for Bjorn Ironhand."""
    return {
        "name": "Bjorn Ironhand",
        "player_discord_id": "123456789",
        "point_total": 150,
        "ST": 14,
        "DX": 12,
        "IQ": 10,
        "HT": 12,
        "skills": {
            "Broadsword": {"level": 14, "attribute": "DX", "difficulty": "A", "defaults": ["DX-5", "Shortsword-2"]},
            "Shield": {"level": 13, "attribute": "DX", "difficulty": "E", "defaults": ["DX-4"]},
            "Brawling": {"level": 13, "attribute": "DX", "difficulty": "E", "defaults": ["DX-4"]},
            "Stealth": {"level": 11, "attribute": "DX", "difficulty": "A", "defaults": ["DX-5"]},
        },
        "advantages": [
            {"name": "Combat Reflexes", "level": 1, "point_cost": 15, "mechanical_effects": {"defense_bonus": 1, "initiative_bonus": 2}},
            {"name": "High Pain Threshold", "level": 1, "point_cost": 10, "mechanical_effects": {"stun_roll_bonus": 3}},
        ],
        "equipment": [
            {"name": "Broadsword", "weight": 3.0, "dr": None, "damage": "2d+1 cut / 1d+2 cr", "location": "hand"},
            {"name": "Medium Shield", "weight": 8.0, "dr": None, "damage": None, "location": "arm"},
            {"name": "Chain Mail", "weight": 30.0, "dr": 4, "damage": None, "location": "torso"},
        ],
        "dodge": 10,
        "parry_skills": [{"weapon": "Broadsword", "score": 11}],
        "block_skill": 11,
    }


def elara_data() -> dict:
    """Return a full character dict for Elara Swift."""
    return {
        "name": "Elara Swift",
        "player_discord_id": "987654321",
        "point_total": 150,
        "ST": 10,
        "DX": 14,
        "IQ": 12,
        "HT": 11,
        "skills": {
            "Bow": {"level": 15, "attribute": "DX", "difficulty": "A", "defaults": ["DX-5"]},
            "Stealth": {"level": 14, "attribute": "DX", "difficulty": "A", "defaults": ["DX-5"]},
            "Tracking": {"level": 13, "attribute": "IQ", "difficulty": "A", "defaults": ["Per-5"]},
        },
        "advantages": [
            {"name": "Acute Vision", "level": 2, "point_cost": 4, "mechanical_effects": {"per_vision_bonus": 2}},
        ],
        "equipment": [
            {"name": "Longbow", "weight": 3.0, "dr": None, "damage": "1d+2 imp", "location": "hand"},
            {"name": "Leather Armor", "weight": 12.0, "dr": 2, "damage": None, "location": "torso"},
        ],
        "dodge": 10,
        "parry_skills": [],
        "block_skill": None,
    }


# ---------------------------------------------------------------------------
# Sub-model tests
# ---------------------------------------------------------------------------


class TestSkillEntry:
    def test_basic_creation(self):
        s = SkillEntry(level=14, attribute="DX", difficulty="A", defaults=["DX-5"])
        assert s.level == 14
        assert s.attribute == "DX"
        assert s.difficulty == "A"
        assert s.defaults == ["DX-5"]

    def test_empty_defaults(self):
        s = SkillEntry(level=10, attribute="IQ", difficulty="H", defaults=[])
        assert s.defaults == []

    def test_multiple_defaults(self):
        s = SkillEntry(level=14, attribute="DX", difficulty="A", defaults=["DX-5", "Shortsword-2", "Axe/Mace-4"])
        assert len(s.defaults) == 3


class TestAdvantage:
    def test_basic_creation(self):
        a = Advantage(name="Combat Reflexes", level=1, point_cost=15, mechanical_effects={"defense_bonus": 1})
        assert a.name == "Combat Reflexes"
        assert a.level == 1
        assert a.point_cost == 15
        assert a.mechanical_effects["defense_bonus"] == 1

    def test_empty_mechanical_effects(self):
        a = Advantage(name="Appearance (Attractive)", level=1, point_cost=4, mechanical_effects={})
        assert a.mechanical_effects == {}

    def test_negative_point_cost_disadvantage(self):
        a = Advantage(name="Cowardice", level=1, point_cost=-10, mechanical_effects={"fright_check_penalty": -2})
        assert a.point_cost == -10


class TestItem:
    def test_weapon(self):
        item = Item(name="Broadsword", weight=3.0, dr=None, damage="2d+1 cut", location="hand")
        assert item.name == "Broadsword"
        assert item.damage == "2d+1 cut"
        assert item.dr is None

    def test_armor(self):
        item = Item(name="Chain Mail", weight=30.0, dr=4, damage=None, location="torso")
        assert item.dr == 4
        assert item.damage is None

    def test_mundane_item(self):
        item = Item(name="Rope (10m)", weight=2.0, dr=None, damage=None, location="pack")
        assert item.dr is None
        assert item.damage is None


class TestActiveEffect:
    def test_basic_creation(self):
        eff = ActiveEffect(name="All-Out Attack", duration=1, mechanical_effects={"no_active_defense": True})
        assert eff.name == "All-Out Attack"
        assert eff.duration == 1
        assert eff.mechanical_effects["no_active_defense"] is True

    def test_no_duration(self):
        eff = ActiveEffect(name="Stunned", duration=None, mechanical_effects={"defense_penalty": -4})
        assert eff.duration is None


# ---------------------------------------------------------------------------
# Character creation and derived attributes
# ---------------------------------------------------------------------------


class TestCharacterCreation:
    def test_full_creation(self):
        c = Character(**bjorn_data())
        assert c.name == "Bjorn Ironhand"
        assert c.ST == 14
        assert c.DX == 12
        assert c.IQ == 10
        assert c.HT == 12

    def test_derived_hp_defaults_to_st(self):
        data = bjorn_data()
        # No HP override → defaults to ST
        c = Character(**data)
        assert c.HP == 14  # ST 14

    def test_derived_fp_defaults_to_ht(self):
        c = Character(**bjorn_data())
        assert c.FP == 12  # HT 12

    def test_derived_will_defaults_to_iq(self):
        c = Character(**bjorn_data())
        assert c.Will == 10  # IQ 10

    def test_derived_per_defaults_to_iq(self):
        c = Character(**bjorn_data())
        assert c.Per == 10  # IQ 10

    def test_derived_basic_speed(self):
        c = Character(**bjorn_data())
        # (HT 12 + DX 12) / 4 = 6.0
        assert c.Basic_Speed == pytest.approx(6.0)

    def test_derived_basic_move(self):
        c = Character(**bjorn_data())
        # floor(6.0) = 6
        assert c.Basic_Move == 6

    def test_derived_current_hp_defaults_to_hp(self):
        c = Character(**bjorn_data())
        assert c.current_hp == c.HP

    def test_derived_current_fp_defaults_to_fp(self):
        c = Character(**bjorn_data())
        assert c.current_fp == c.FP

    def test_override_secondary_attributes(self):
        data = bjorn_data()
        data["HP"] = 16  # bought up
        data["Will"] = 12  # bought up
        c = Character(**data)
        assert c.HP == 16
        assert c.Will == 12

    def test_override_current_hp(self):
        data = bjorn_data()
        data["current_hp"] = 8  # damaged
        c = Character(**data)
        assert c.current_hp == 8

    def test_override_basic_speed(self):
        data = bjorn_data()
        data["Basic_Speed"] = 6.5  # bought up
        c = Character(**data)
        assert c.Basic_Speed == pytest.approx(6.5)

    def test_override_basic_move(self):
        data = bjorn_data()
        data["Basic_Move"] = 7  # bought up
        c = Character(**data)
        assert c.Basic_Move == 7

    def test_empty_skills(self):
        data = bjorn_data()
        data["skills"] = {}
        c = Character(**data)
        assert c.skills == {}

    def test_empty_advantages(self):
        data = bjorn_data()
        data["advantages"] = []
        c = Character(**data)
        assert c.advantages == []

    def test_empty_equipment(self):
        data = bjorn_data()
        data["equipment"] = []
        c = Character(**data)
        assert c.equipment == []

    def test_no_block_skill(self):
        c = Character(**elara_data())
        assert c.block_skill is None

    def test_no_parry_skills(self):
        c = Character(**elara_data())
        assert c.parry_skills == []

    def test_conditions_default_empty(self):
        c = Character(**bjorn_data())
        assert c.conditions == []

    def test_active_effects_default_empty(self):
        c = Character(**bjorn_data())
        assert c.active_effects == []


# ---------------------------------------------------------------------------
# Serialization: to_json / from_json round-trip
# ---------------------------------------------------------------------------


class TestCharacterSerialization:
    def test_to_json_returns_string(self):
        c = Character(**bjorn_data())
        result = c.to_json()
        assert isinstance(result, str)

    def test_json_is_valid(self):
        c = Character(**bjorn_data())
        parsed = json.loads(c.to_json())
        assert parsed["name"] == "Bjorn Ironhand"

    def test_json_round_trip(self):
        c = Character(**bjorn_data())
        json_str = c.to_json()
        c2 = Character.model_validate_json(json_str)
        assert c2.name == c.name
        assert c2.ST == c.ST
        assert c2.DX == c.DX
        assert c2.HP == c.HP
        assert len(c2.skills) == len(c.skills)
        assert len(c2.advantages) == len(c.advantages)
        assert len(c2.equipment) == len(c.equipment)

    def test_json_round_trip_derived_preserved(self):
        """Derived fields stored explicitly survive round-trip."""
        c = Character(**bjorn_data())
        c2 = Character.model_validate_json(c.to_json())
        assert c2.Basic_Speed == pytest.approx(c.Basic_Speed)
        assert c2.Basic_Move == c.Basic_Move
        assert c2.current_hp == c.current_hp
        assert c2.current_fp == c.current_fp

    def test_json_round_trip_with_active_effects(self):
        data = bjorn_data()
        data["active_effects"] = [{"name": "Stunned", "duration": 1, "mechanical_effects": {"defense_penalty": -4}}]
        c = Character(**data)
        c2 = Character.model_validate_json(c.to_json())
        assert len(c2.active_effects) == 1
        assert c2.active_effects[0].name == "Stunned"

    def test_json_round_trip_with_conditions(self):
        data = bjorn_data()
        data["conditions"] = ["prone", "stunned"]
        c = Character(**data)
        c2 = Character.model_validate_json(c.to_json())
        assert c2.conditions == ["prone", "stunned"]


# ---------------------------------------------------------------------------
# LLM summary format
# ---------------------------------------------------------------------------


class TestCharacterLLMSummary:
    def test_summary_contains_name(self):
        c = Character(**bjorn_data())
        summary = c.to_llm_summary()
        assert "Bjorn Ironhand" in summary

    def test_summary_contains_primary_attributes(self):
        c = Character(**bjorn_data())
        summary = c.to_llm_summary()
        assert "ST 14" in summary
        assert "DX 12" in summary
        assert "IQ 10" in summary
        assert "HT 12" in summary

    def test_summary_contains_hp_fp_current(self):
        data = bjorn_data()
        data["current_hp"] = 8
        c = Character(**data)
        summary = c.to_llm_summary()
        assert "HP 8/14" in summary

    def test_summary_contains_full_hp_when_undamaged(self):
        c = Character(**bjorn_data())
        summary = c.to_llm_summary()
        assert "HP 14/14" in summary
        assert "FP 12/12" in summary

    def test_summary_contains_skills(self):
        c = Character(**bjorn_data())
        summary = c.to_llm_summary()
        assert "Broadsword-14" in summary
        assert "Shield-13" in summary

    def test_summary_contains_advantages(self):
        c = Character(**bjorn_data())
        summary = c.to_llm_summary()
        assert "Combat Reflexes" in summary
        assert "High Pain Threshold" in summary

    def test_summary_contains_equipment(self):
        c = Character(**bjorn_data())
        summary = c.to_llm_summary()
        assert "Broadsword" in summary
        assert "Chain Mail" in summary

    def test_summary_contains_combat_stats(self):
        c = Character(**bjorn_data())
        summary = c.to_llm_summary()
        assert "Dodge 10" in summary
        assert "Block 11" in summary

    def test_summary_healthy_status(self):
        c = Character(**bjorn_data())
        summary = c.to_llm_summary()
        assert "healthy" in summary.lower()

    def test_summary_shows_conditions(self):
        data = bjorn_data()
        data["conditions"] = ["stunned", "prone"]
        c = Character(**data)
        summary = c.to_llm_summary()
        assert "stunned" in summary
        assert "prone" in summary

    def test_summary_no_equipment(self):
        data = bjorn_data()
        data["equipment"] = []
        c = Character(**data)
        summary = c.to_llm_summary()
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_summary_no_advantages(self):
        data = bjorn_data()
        data["advantages"] = []
        c = Character(**data)
        summary = c.to_llm_summary()
        assert isinstance(summary, str)

    def test_summary_no_skills(self):
        data = bjorn_data()
        data["skills"] = {}
        c = Character(**data)
        summary = c.to_llm_summary()
        assert isinstance(summary, str)

    def test_summary_multiline(self):
        c = Character(**bjorn_data())
        summary = c.to_llm_summary()
        lines = summary.strip().split("\n")
        assert len(lines) >= 4  # At least 4 lines per blueprint format
