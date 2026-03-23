"""Tests for state/db.py — SQLite persistence layer.

Tests written BEFORE implementation per project testing rules.
"""

import json
import os
import tempfile
import pytest
from pathlib import Path
from state.character import Character
from state.db import Database


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    """Provide a fresh in-memory/temp database for each test."""
    db_path = str(tmp_path / "test_campaign.db")
    database = Database(db_path)
    yield database
    database.close()


def bjorn_character() -> Character:
    return Character(
        name="Bjorn Ironhand",
        player_discord_id="123456789",
        point_total=150,
        ST=14, DX=12, IQ=10, HT=12,
        skills={
            "Broadsword": {"level": 14, "attribute": "DX", "difficulty": "A", "defaults": ["DX-5"]},
            "Shield": {"level": 13, "attribute": "DX", "difficulty": "E", "defaults": ["DX-4"]},
        },
        advantages=[
            {"name": "Combat Reflexes", "level": 1, "point_cost": 15, "mechanical_effects": {"defense_bonus": 1}},
        ],
        equipment=[
            {"name": "Broadsword", "weight": 3.0, "dr": None, "damage": "2d+1 cut", "location": "hand"},
            {"name": "Chain Mail", "weight": 30.0, "dr": 4, "damage": None, "location": "torso"},
        ],
        dodge=10,
        parry_skills=[{"weapon": "Broadsword", "score": 11}],
        block_skill=11,
    )


def elara_character() -> Character:
    return Character(
        name="Elara Swift",
        player_discord_id="987654321",
        point_total=150,
        ST=10, DX=14, IQ=12, HT=11,
        skills={
            "Bow": {"level": 15, "attribute": "DX", "difficulty": "A", "defaults": ["DX-5"]},
        },
        advantages=[],
        equipment=[
            {"name": "Longbow", "weight": 3.0, "dr": None, "damage": "1d+2 imp", "location": "hand"},
        ],
        dodge=10,
        parry_skills=[],
        block_skill=None,
    )


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------


class TestDatabaseInit:
    def test_creates_characters_table(self, db):
        result = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='characters'").fetchone()
        assert result is not None

    def test_creates_campaigns_table(self, db):
        result = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='campaigns'").fetchone()
        assert result is not None

    def test_creates_scenes_table(self, db):
        result = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scenes'").fetchone()
        assert result is not None

    def test_creates_action_log_table(self, db):
        result = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='action_log'").fetchone()
        assert result is not None

    def test_creates_session_summaries_table(self, db):
        result = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='session_summaries'").fetchone()
        assert result is not None

    def test_creates_custom_rules_table(self, db):
        result = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='custom_rules'").fetchone()
        assert result is not None

    def test_wal_mode_enabled(self, db):
        result = db.execute("PRAGMA journal_mode").fetchone()
        assert result[0] == "wal"


# ---------------------------------------------------------------------------
# Campaign CRUD
# ---------------------------------------------------------------------------


class TestCampaignCRUD:
    def test_create_campaign(self, db):
        campaign_id = db.create_campaign(
            name="The Iron Throne Campaign",
            setting="generic_fantasy",
            gm_discord_id="111222333",
        )
        assert campaign_id is not None
        assert len(campaign_id) > 0

    def test_create_campaign_returns_id(self, db):
        cid1 = db.create_campaign("Campaign A", "fantasy", "111")
        cid2 = db.create_campaign("Campaign B", "fantasy", "222")
        assert cid1 != cid2

    def test_read_campaign(self, db):
        cid = db.create_campaign("Test Campaign", "sci-fi", "999")
        campaign = db.get_campaign(cid)
        assert campaign is not None
        assert campaign["name"] == "Test Campaign"
        assert campaign["setting"] == "sci-fi"
        assert campaign["gm_discord_id"] == "999"

    def test_read_nonexistent_campaign_returns_none(self, db):
        result = db.get_campaign("nonexistent-id")
        assert result is None


# ---------------------------------------------------------------------------
# Character CRUD
# ---------------------------------------------------------------------------


class TestCharacterCRUD:
    def test_save_character(self, db):
        cid = db.create_campaign("Test", "fantasy", "000")
        bjorn = bjorn_character()
        char_id = db.save_character(bjorn, campaign_id=cid)
        assert char_id is not None

    def test_load_character_by_id(self, db):
        cid = db.create_campaign("Test", "fantasy", "000")
        bjorn = bjorn_character()
        char_id = db.save_character(bjorn, campaign_id=cid)

        loaded = db.load_character(char_id)
        assert loaded is not None
        assert isinstance(loaded, Character)
        assert loaded.name == "Bjorn Ironhand"

    def test_character_full_field_round_trip(self, db):
        cid = db.create_campaign("Test", "fantasy", "000")
        bjorn = bjorn_character()
        char_id = db.save_character(bjorn, campaign_id=cid)
        loaded = db.load_character(char_id)

        assert loaded.ST == bjorn.ST
        assert loaded.DX == bjorn.DX
        assert loaded.IQ == bjorn.IQ
        assert loaded.HT == bjorn.HT
        assert loaded.HP == bjorn.HP
        assert loaded.FP == bjorn.FP
        assert loaded.dodge == bjorn.dodge
        assert loaded.block_skill == bjorn.block_skill
        assert len(loaded.skills) == len(bjorn.skills)
        assert len(loaded.advantages) == len(bjorn.advantages)
        assert len(loaded.equipment) == len(bjorn.equipment)

    def test_update_character(self, db):
        cid = db.create_campaign("Test", "fantasy", "000")
        bjorn = bjorn_character()
        char_id = db.save_character(bjorn, campaign_id=cid)

        bjorn.current_hp = 7
        bjorn.conditions = ["stunned"]
        db.update_character(char_id, bjorn)

        loaded = db.load_character(char_id)
        assert loaded.current_hp == 7
        assert "stunned" in loaded.conditions

    def test_delete_character(self, db):
        cid = db.create_campaign("Test", "fantasy", "000")
        bjorn = bjorn_character()
        char_id = db.save_character(bjorn, campaign_id=cid)

        db.delete_character(char_id)
        loaded = db.load_character(char_id)
        assert loaded is None

    def test_load_nonexistent_character_returns_none(self, db):
        result = db.load_character("no-such-id")
        assert result is None

    def test_load_characters_by_campaign(self, db):
        cid = db.create_campaign("Test", "fantasy", "000")
        db.save_character(bjorn_character(), campaign_id=cid)
        db.save_character(elara_character(), campaign_id=cid)

        chars = db.load_characters_by_campaign(cid)
        assert len(chars) == 2
        names = {c.name for c in chars}
        assert "Bjorn Ironhand" in names
        assert "Elara Swift" in names

    def test_load_characters_by_discord_user(self, db):
        cid = db.create_campaign("Test", "fantasy", "000")
        db.save_character(bjorn_character(), campaign_id=cid)
        db.save_character(elara_character(), campaign_id=cid)

        chars = db.load_characters_by_discord_user("123456789", cid)
        assert len(chars) == 1
        assert chars[0].name == "Bjorn Ironhand"


# ---------------------------------------------------------------------------
# Scene CRUD
# ---------------------------------------------------------------------------


class TestSceneCRUD:
    def test_create_scene(self, db):
        cid = db.create_campaign("Test", "fantasy", "000")
        scene_id = db.create_scene(
            campaign_id=cid,
            description="The party enters a dark tavern.",
            scene_type="social",
        )
        assert scene_id is not None

    def test_get_scene(self, db):
        cid = db.create_campaign("Test", "fantasy", "000")
        sid = db.create_scene(cid, "A dark forest clearing.", "exploration")

        scene = db.get_scene(sid)
        assert scene is not None
        assert scene["description"] == "A dark forest clearing."
        assert scene["scene_type"] == "exploration"

    def test_get_recent_scenes(self, db):
        cid = db.create_campaign("Test", "fantasy", "000")
        db.create_scene(cid, "Scene 1", "exploration")
        db.create_scene(cid, "Scene 2", "combat")
        db.create_scene(cid, "Scene 3", "social")

        scenes = db.get_recent_scenes(cid, limit=2)
        assert len(scenes) == 2

    def test_get_nonexistent_scene_returns_none(self, db):
        result = db.get_scene("no-such-scene")
        assert result is None


# ---------------------------------------------------------------------------
# Action log
# ---------------------------------------------------------------------------


class TestActionLog:
    def test_append_action(self, db):
        cid = db.create_campaign("Test", "fantasy", "000")
        bjorn = bjorn_character()
        char_id = db.save_character(bjorn, campaign_id=cid)
        sid = db.create_scene(cid, "Battle!", "combat")

        action_id = db.append_action(
            scene_id=sid,
            character_id=char_id,
            action_json=json.dumps({"action": "attack", "target": "goblin"}),
            result_json=json.dumps({"hit": True, "damage": 12}),
        )
        assert action_id is not None

    def test_get_actions_for_scene(self, db):
        cid = db.create_campaign("Test", "fantasy", "000")
        bjorn = bjorn_character()
        char_id = db.save_character(bjorn, campaign_id=cid)
        sid = db.create_scene(cid, "Battle!", "combat")

        db.append_action(sid, char_id, json.dumps({"action": "attack"}), json.dumps({"hit": True}))
        db.append_action(sid, char_id, json.dumps({"action": "defend"}), json.dumps({"success": True}))

        actions = db.get_actions_for_scene(sid)
        assert len(actions) == 2


# ---------------------------------------------------------------------------
# Session summaries
# ---------------------------------------------------------------------------


class TestSessionSummaries:
    def test_create_summary(self, db):
        cid = db.create_campaign("Test", "fantasy", "000")
        summary_id = db.create_session_summary(
            campaign_id=cid,
            summary_text="The party fought goblins and found a treasure chest.",
            message_range="1-20",
        )
        assert summary_id is not None

    def test_get_latest_summary(self, db):
        cid = db.create_campaign("Test", "fantasy", "000")
        db.create_session_summary(cid, "First summary.", "1-20")
        db.create_session_summary(cid, "Second summary.", "21-40")

        latest = db.get_latest_summary(cid)
        assert latest is not None
        assert latest["summary_text"] == "Second summary."

    def test_get_latest_summary_no_summaries_returns_none(self, db):
        cid = db.create_campaign("Test", "fantasy", "000")
        result = db.get_latest_summary(cid)
        assert result is None


# ---------------------------------------------------------------------------
# Custom rules
# ---------------------------------------------------------------------------


class TestCustomRules:
    def test_create_rule(self, db):
        cid = db.create_campaign("Test", "fantasy", "000")
        rule_id = db.create_custom_rule(
            campaign_id=cid,
            rule_name="Double FP Magic",
            rule_text="All spells cost double FP in this campaign.",
        )
        assert rule_id is not None

    def test_get_rules_for_campaign(self, db):
        cid = db.create_campaign("Test", "fantasy", "000")
        db.create_custom_rule(cid, "Rule 1", "Text 1")
        db.create_custom_rule(cid, "Rule 2", "Text 2")

        rules = db.get_custom_rules(cid)
        assert len(rules) == 2
        names = {r["rule_name"] for r in rules}
        assert "Rule 1" in names

    def test_delete_rule(self, db):
        cid = db.create_campaign("Test", "fantasy", "000")
        rid = db.create_custom_rule(cid, "Temp Rule", "Will be deleted")
        db.delete_custom_rule(rid)

        rules = db.get_custom_rules(cid)
        assert all(r["id"] != rid for r in rules)

    def test_no_rules_returns_empty_list(self, db):
        cid = db.create_campaign("Test", "fantasy", "000")
        rules = db.get_custom_rules(cid)
        assert rules == []


# ---------------------------------------------------------------------------
# Fixture round-trip: JSON files → Character → DB → Character
# ---------------------------------------------------------------------------


class TestFixtureRoundTrip:
    def test_bjorn_fixture_loads_and_saves(self, db, tmp_path):
        fixture_path = Path(__file__).parent / "fixtures" / "bjorn_ironhand.json"
        with open(fixture_path) as f:
            data = json.load(f)

        bjorn = Character(**data)
        cid = db.create_campaign("Fixture Test", "fantasy", "000")
        char_id = db.save_character(bjorn, campaign_id=cid)
        loaded = db.load_character(char_id)

        assert loaded.name == bjorn.name
        assert loaded.ST == bjorn.ST
        assert loaded.point_total == bjorn.point_total

    def test_elara_fixture_loads_and_saves(self, db):
        fixture_path = Path(__file__).parent / "fixtures" / "elara_swift.json"
        with open(fixture_path) as f:
            data = json.load(f)

        elara = Character(**data)
        cid = db.create_campaign("Fixture Test", "fantasy", "000")
        char_id = db.save_character(elara, campaign_id=cid)
        loaded = db.load_character(char_id)

        assert loaded.name == elara.name
        assert loaded.DX == elara.DX

    def test_grimm_fixture_loads_and_saves(self, db):
        fixture_path = Path(__file__).parent / "fixtures" / "grimm_the_wise.json"
        with open(fixture_path) as f:
            data = json.load(f)

        grimm = Character(**data)
        cid = db.create_campaign("Fixture Test", "fantasy", "000")
        char_id = db.save_character(grimm, campaign_id=cid)
        loaded = db.load_character(char_id)

        assert loaded.name == grimm.name
        assert loaded.IQ == grimm.IQ
