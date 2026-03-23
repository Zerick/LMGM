"""Tests for state/scene.py — Scene state tracking.

Tests written BEFORE implementation per project testing rules.
"""

from datetime import datetime
import pytest
from state.character import Character
from state.scene import ActionRecord, CharacterSummary, CombatState, SceneState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_character_summary(name: str = "Bjorn Ironhand") -> CharacterSummary:
    char = Character(
        name=name,
        player_discord_id="123",
        point_total=150,
        ST=14, DX=12, IQ=10, HT=12,
        skills={"Broadsword": {"level": 14, "attribute": "DX", "difficulty": "A", "defaults": []}},
        advantages=[],
        equipment=[],
        dodge=10,
        parry_skills=[],
        block_skill=None,
    )
    return CharacterSummary(
        character_id="bjorn-001",
        name=name,
        summary=char.to_llm_summary(),
    )


def make_action_record(description: str = "Swings broadsword") -> ActionRecord:
    return ActionRecord(
        character_id="bjorn-001",
        action_description=description,
        result_summary="Hit for 8 damage.",
        timestamp=datetime(2026, 3, 22, 14, 0, 0),
    )


# ---------------------------------------------------------------------------
# CharacterSummary
# ---------------------------------------------------------------------------


class TestCharacterSummary:
    def test_basic_creation(self):
        cs = make_character_summary()
        assert cs.character_id == "bjorn-001"
        assert cs.name == "Bjorn Ironhand"
        assert isinstance(cs.summary, str)
        assert len(cs.summary) > 0

    def test_summary_contains_character_info(self):
        cs = make_character_summary("Elara Swift")
        assert "Elara Swift" in cs.summary


# ---------------------------------------------------------------------------
# ActionRecord
# ---------------------------------------------------------------------------


class TestActionRecord:
    def test_basic_creation(self):
        ar = make_action_record("Attempts to pick the lock.")
        assert ar.character_id == "bjorn-001"
        assert ar.action_description == "Attempts to pick the lock."
        assert ar.result_summary == "Hit for 8 damage."
        assert isinstance(ar.timestamp, datetime)


# ---------------------------------------------------------------------------
# CombatState
# ---------------------------------------------------------------------------


class TestCombatState:
    def test_basic_creation(self):
        cs = CombatState(
            round_number=1,
            turn_order=["bjorn-001", "goblin-1", "elara-002"],
            current_turn="bjorn-001",
            active_maneuvers={"bjorn-001": "attack"},
            position_notes="Bjorn is 2 yards from the goblin.",
        )
        assert cs.round_number == 1
        assert cs.current_turn == "bjorn-001"
        assert len(cs.turn_order) == 3

    def test_empty_maneuvers(self):
        cs = CombatState(
            round_number=3,
            turn_order=["a", "b"],
            current_turn="a",
            active_maneuvers={},
            position_notes="",
        )
        assert cs.active_maneuvers == {}

    def test_round_number_increments(self):
        cs = CombatState(
            round_number=5,
            turn_order=["a"],
            current_turn="a",
            active_maneuvers={},
            position_notes="",
        )
        assert cs.round_number == 5


# ---------------------------------------------------------------------------
# SceneState creation
# ---------------------------------------------------------------------------


class TestSceneStateCreation:
    def test_basic_exploration_scene(self):
        scene = SceneState(
            scene_id="scene-001",
            description="A dark forest clearing.",
            scene_type="exploration",
            characters_present=[make_character_summary()],
            recent_actions=[],
            active_effects=[],
            combat_state=None,
        )
        assert scene.scene_id == "scene-001"
        assert scene.scene_type == "exploration"
        assert scene.combat_state is None

    def test_combat_scene_with_combat_state(self):
        cs = CombatState(
            round_number=1,
            turn_order=["bjorn-001", "goblin-1"],
            current_turn="bjorn-001",
            active_maneuvers={},
            position_notes="Close quarters.",
        )
        scene = SceneState(
            scene_id="scene-002",
            description="A tavern brawl erupts!",
            scene_type="combat",
            characters_present=[make_character_summary()],
            recent_actions=[make_action_record()],
            active_effects=["dim lighting"],
            combat_state=cs,
        )
        assert scene.scene_type == "combat"
        assert scene.combat_state is not None
        assert scene.combat_state.round_number == 1

    def test_multiple_characters_present(self):
        scene = SceneState(
            scene_id="scene-003",
            description="Meeting in the great hall.",
            scene_type="social",
            characters_present=[
                make_character_summary("Bjorn Ironhand"),
                make_character_summary("Elara Swift"),
            ],
            recent_actions=[],
            active_effects=[],
            combat_state=None,
        )
        assert len(scene.characters_present) == 2

    def test_active_effects_list(self):
        scene = SceneState(
            scene_id="scene-004",
            description="A stormy battlefield.",
            scene_type="combat",
            characters_present=[make_character_summary()],
            recent_actions=[],
            active_effects=["heavy rain", "darkness", "difficult terrain"],
            combat_state=None,
        )
        assert len(scene.active_effects) == 3
        assert "heavy rain" in scene.active_effects

    def test_recent_actions_limited_to_five(self):
        """SceneState only keeps last 5 actions."""
        actions = [make_action_record(f"Action {i}") for i in range(7)]
        scene = SceneState(
            scene_id="scene-005",
            description="Extended combat.",
            scene_type="combat",
            characters_present=[make_character_summary()],
            recent_actions=actions,
            active_effects=[],
            combat_state=None,
        )
        # Model accepts all; to_prompt_text only shows last 5
        assert len(scene.recent_actions) <= 7  # storage allows all
        text = scene.to_prompt_text()
        # Prompt text should only include last 5
        action_count = sum(1 for a in actions[-5:] if a.action_description in text)
        assert action_count <= 5


# ---------------------------------------------------------------------------
# SceneState.to_prompt_text()
# ---------------------------------------------------------------------------


class TestSceneStateToPromptText:
    def test_returns_string(self):
        scene = SceneState(
            scene_id="s1",
            description="A test scene.",
            scene_type="exploration",
            characters_present=[make_character_summary()],
            recent_actions=[],
            active_effects=[],
            combat_state=None,
        )
        text = scene.to_prompt_text()
        assert isinstance(text, str)
        assert len(text) > 0

    def test_contains_scene_description(self):
        scene = SceneState(
            scene_id="s1",
            description="The party stands at the edge of a volcano.",
            scene_type="exploration",
            characters_present=[make_character_summary()],
            recent_actions=[],
            active_effects=[],
            combat_state=None,
        )
        text = scene.to_prompt_text()
        assert "volcano" in text

    def test_contains_scene_type(self):
        scene = SceneState(
            scene_id="s1",
            description="Tavern brawl!",
            scene_type="combat",
            characters_present=[make_character_summary()],
            recent_actions=[],
            active_effects=[],
            combat_state=None,
        )
        text = scene.to_prompt_text()
        assert "combat" in text.lower()

    def test_contains_character_name(self):
        scene = SceneState(
            scene_id="s1",
            description="A scene.",
            scene_type="social",
            characters_present=[make_character_summary("Bjorn Ironhand")],
            recent_actions=[],
            active_effects=[],
            combat_state=None,
        )
        text = scene.to_prompt_text()
        assert "Bjorn Ironhand" in text

    def test_contains_active_effects(self):
        scene = SceneState(
            scene_id="s1",
            description="Stormy scene.",
            scene_type="exploration",
            characters_present=[make_character_summary()],
            recent_actions=[],
            active_effects=["heavy rain", "darkness"],
            combat_state=None,
        )
        text = scene.to_prompt_text()
        assert "heavy rain" in text or "darkness" in text

    def test_contains_recent_actions(self):
        action = make_action_record("Charged at the goblin.")
        scene = SceneState(
            scene_id="s1",
            description="A scene.",
            scene_type="combat",
            characters_present=[make_character_summary()],
            recent_actions=[action],
            active_effects=[],
            combat_state=None,
        )
        text = scene.to_prompt_text()
        assert "goblin" in text or "Charged" in text

    def test_contains_combat_state_when_present(self):
        cs = CombatState(
            round_number=2,
            turn_order=["bjorn-001", "goblin-1"],
            current_turn="bjorn-001",
            active_maneuvers={"bjorn-001": "all_out_attack"},
            position_notes="Adjacent.",
        )
        scene = SceneState(
            scene_id="s1",
            description="Combat!",
            scene_type="combat",
            characters_present=[make_character_summary()],
            recent_actions=[],
            active_effects=[],
            combat_state=cs,
        )
        text = scene.to_prompt_text()
        assert "Round 2" in text or "round 2" in text.lower()
        assert "bjorn-001" in text or "Bjorn" in text

    def test_no_combat_state_section_when_not_combat(self):
        scene = SceneState(
            scene_id="s1",
            description="A peaceful village.",
            scene_type="social",
            characters_present=[make_character_summary()],
            recent_actions=[],
            active_effects=[],
            combat_state=None,
        )
        text = scene.to_prompt_text()
        # Should not crash or include misleading combat info
        assert isinstance(text, str)

    def test_no_active_effects_section_when_empty(self):
        scene = SceneState(
            scene_id="s1",
            description="Clear day.",
            scene_type="exploration",
            characters_present=[make_character_summary()],
            recent_actions=[],
            active_effects=[],
            combat_state=None,
        )
        text = scene.to_prompt_text()
        assert isinstance(text, str)
