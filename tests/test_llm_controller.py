"""Tests for llm/controller.py — Phase 4 LLM integration.

All LiteLLM calls are mocked. No real API calls are made.
"""
import os
from unittest.mock import MagicMock, patch

import pytest

from llm.controller import LLMController
from state.character import Character


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def base_config() -> dict:
    """Minimal config.yaml structure for testing."""
    return {
        "llm": {
            "provider": "gemini",
            "model": "gemini/gemini-2.0-flash",
            "api_key_env": "GOOGLE_API_KEY",
            "max_tokens": 500,
            "temperature": 0.7,
        },
        "game": {
            "setting": "generic_fantasy",
            "max_recent_messages": 8,
        },
    }


@pytest.fixture()
def controller(base_config: dict, monkeypatch: pytest.MonkeyPatch) -> LLMController:
    """LLMController with a fake API key set."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-fake")
    return LLMController(base_config)


@pytest.fixture()
def minimal_character() -> Character:
    """A simple test character."""
    return Character(
        name="Bjorn Ironhand",
        player_discord_id="123456789",
        point_total=100,
        ST=14,
        DX=12,
        IQ=10,
        HT=12,
        dodge=9,
    )


# ---------------------------------------------------------------------------
# build_system_prompt tests
# ---------------------------------------------------------------------------

class TestBuildSystemPrompt:
    def test_contains_base_gm_content(self, controller: LLMController) -> None:
        """System prompt must include the base GM personality text."""
        prompt = controller.build_system_prompt()
        assert "Game Master" in prompt
        assert "NARRATION" in prompt
        assert "MECHANICAL HONESTY" in prompt

    def test_contains_setting(self, controller: LLMController) -> None:
        """Setting name from config must appear in the prompt."""
        prompt = controller.build_system_prompt()
        assert "generic_fantasy" in prompt

    def test_rag_context_included_when_provided(
        self, controller: LLMController
    ) -> None:
        """RAG context should appear in the prompt when non-empty."""
        prompt = controller.build_system_prompt(rag_context="Deceptive Attack rules...")
        assert "Deceptive Attack rules" in prompt
        assert "RULES CONTEXT" in prompt

    def test_rag_context_absent_when_empty(self, controller: LLMController) -> None:
        """RULES CONTEXT section must not appear when rag_context is empty."""
        prompt = controller.build_system_prompt(rag_context="")
        assert "RULES CONTEXT" not in prompt

    def test_scene_state_included_when_provided(
        self, controller: LLMController
    ) -> None:
        """Scene state text should appear when non-empty."""
        prompt = controller.build_system_prompt(
            scene_state_text="The tavern is dark and smoky."
        )
        assert "tavern is dark" in prompt
        assert "CURRENT SCENE" in prompt

    def test_scene_state_absent_when_empty(self, controller: LLMController) -> None:
        """CURRENT SCENE section must not appear when scene_state_text is empty."""
        prompt = controller.build_system_prompt(scene_state_text="")
        assert "CURRENT SCENE" not in prompt

    def test_character_summaries_included(
        self,
        base_config: dict,
        minimal_character: Character,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Character summaries from the state system must appear in the prompt."""
        monkeypatch.setenv("GOOGLE_API_KEY", "fake")
        ctrl = LLMController(base_config, characters=[minimal_character])
        prompt = ctrl.build_system_prompt()
        assert "Bjorn Ironhand" in prompt
        assert "ACTIVE CHARACTERS" in prompt

    def test_no_characters_section_when_empty(
        self, controller: LLMController
    ) -> None:
        """ACTIVE CHARACTERS section must not appear with no characters."""
        prompt = controller.build_system_prompt()
        assert "ACTIVE CHARACTERS" not in prompt

    def test_session_summary_included_when_provided(
        self, controller: LLMController
    ) -> None:
        """Session summary text should appear when non-empty."""
        prompt = controller.build_system_prompt(
            session_summary="Last session: the party cleared the dungeon."
        )
        assert "party cleared the dungeon" in prompt
        assert "SESSION SUMMARY" in prompt


# ---------------------------------------------------------------------------
# Conversation history tests
# ---------------------------------------------------------------------------

class TestConversationHistory:
    def _make_history(self, n: int) -> list[dict]:
        """Build a fake history of n alternating user/assistant turns."""
        history = []
        for i in range(n):
            role = "user" if i % 2 == 0 else "assistant"
            history.append({"role": role, "content": f"message {i}"})
        return history

    def _mock_completion_response(self, text: str = "GM reply") -> MagicMock:
        msg = MagicMock()
        msg.content = text
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    def test_history_trimmed_to_max(
        self, controller: LLMController
    ) -> None:
        """If history exceeds max_recent_messages, only the most recent are kept."""
        long_history = self._make_history(20)  # way more than max=8

        with patch("litellm.completion", return_value=self._mock_completion_response()):
            _, updated = controller.chat("new message", long_history)

        # Updated history = trimmed prior + new user turn + assistant reply.
        assert len(updated) <= controller._max_history

    def test_history_grows_with_each_turn(
        self, controller: LLMController
    ) -> None:
        """Each chat() call appends a user + assistant turn to the history."""
        with patch("litellm.completion", return_value=self._mock_completion_response()):
            _, h1 = controller.chat("first", [])
            _, h2 = controller.chat("second", h1)

        assert len(h2) == 4  # first user + first assistant + second user + second assistant

    def test_history_not_mutated(self, controller: LLMController) -> None:
        """The original history list passed to chat() must not be mutated."""
        original = [{"role": "user", "content": "old"}]
        original_copy = list(original)

        with patch("litellm.completion", return_value=self._mock_completion_response()):
            controller.chat("new", original)

        assert original == original_copy

    def test_history_window_caps_at_max(self, controller: LLMController) -> None:
        """After many turns, stored history never exceeds max_recent_messages."""
        history: list[dict] = []

        with patch("litellm.completion", return_value=self._mock_completion_response()):
            for i in range(20):
                _, history = controller.chat(f"message {i}", history)

        assert len(history) <= controller._max_history


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_graceful_fallback_on_api_exception(
        self, controller: LLMController
    ) -> None:
        """On API error, chat() returns the graceful fallback message."""
        with patch("litellm.completion", side_effect=Exception("API down")):
            reply, _ = controller.chat("hello", [])

        assert "please try again" in reply.lower() or "api error" in reply.lower()

    def test_missing_api_key_logs_warning(
        self, base_config: dict, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When the API key env var is unset, a warning should be logged."""
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        import logging
        with caplog.at_level(logging.WARNING, logger="llm.controller"):
            LLMController(base_config)
        assert any("GOOGLE_API_KEY" in r.message for r in caplog.records)

    def test_api_key_env_mapping_gemini(
        self, base_config: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """For gemini provider, GOOGLE_API_KEY should be mapped to GEMINI_API_KEY."""
        monkeypatch.setenv("GOOGLE_API_KEY", "my-gemini-key")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        LLMController(base_config)

        assert os.environ.get("GEMINI_API_KEY") == "my-gemini-key"

    def test_graceful_fallback_when_all_keys_rate_limited(
        self, base_config: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When all keys hit rate limits, the fallback message is returned."""
        import litellm

        two_key_config = dict(base_config)
        two_key_config["llm"] = dict(base_config["llm"])
        two_key_config["llm"]["api_key_env_fallbacks"] = ["GOOGLE_API_KEY_2"]

        monkeypatch.setenv("GOOGLE_API_KEY", "key-1")
        monkeypatch.setenv("GOOGLE_API_KEY_2", "key-2")

        ctrl = LLMController(two_key_config)

        rate_limit_exc = litellm.RateLimitError("rate limited", 429, None)

        with patch("litellm.completion", side_effect=rate_limit_exc):
            reply, _ = ctrl.chat("hello", [])

        assert "please try again" in reply.lower() or "api error" in reply.lower()

    def test_api_key_env_mapping_anthropic(
        self, base_config: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """For anthropic provider, ANTHROPIC_API_KEY passes through unchanged."""
        anthropic_config = dict(base_config)
        anthropic_config["llm"] = {
            "provider": "anthropic",
            "model": "claude-sonnet-4-20250514",
            "api_key_env": "ANTHROPIC_API_KEY",
            "max_tokens": 500,
            "temperature": 0.7,
        }
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

        ctrl = LLMController(anthropic_config)

        assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-test"
        assert ctrl._model == "claude-sonnet-4-20250514"


# ---------------------------------------------------------------------------
# API key rotation tests (Phase 4.5)
# ---------------------------------------------------------------------------


class TestApiKeyRotation:
    """Tests for the key rotation behaviour added in Phase 4.5."""

    def _two_key_config(self, base_config: dict) -> dict:
        """Return a config that has a primary and one fallback key env var."""
        cfg = dict(base_config)
        cfg["llm"] = dict(base_config["llm"])
        cfg["llm"]["api_key_env_fallbacks"] = ["GOOGLE_API_KEY_2"]
        return cfg

    def _mock_response(self, text: str = "GM reply") -> MagicMock:
        msg = MagicMock()
        msg.content = text
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    def test_rotates_to_second_key_on_rate_limit(
        self, base_config: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """First key raises RateLimitError; second key succeeds; valid reply returned."""
        import litellm

        cfg = self._two_key_config(base_config)
        monkeypatch.setenv("GOOGLE_API_KEY", "key-primary")
        monkeypatch.setenv("GOOGLE_API_KEY_2", "key-fallback")

        ctrl = LLMController(cfg)
        assert ctrl._api_keys == ["key-primary", "key-fallback"]

        rate_err = litellm.RateLimitError("rate limited", 429, None)
        success_resp = self._mock_response("Here is the GM reply.")

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise rate_err
            return success_resp

        with patch("litellm.completion", side_effect=side_effect):
            reply, _ = ctrl.chat("attack the goblin", [])

        assert reply == "Here is the GM reply."
        assert call_count == 2

    def test_rotation_uses_correct_key_in_api_key_param(
        self, base_config: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The api_key kwarg passed to litellm must switch to the fallback key."""
        import litellm

        cfg = self._two_key_config(base_config)
        monkeypatch.setenv("GOOGLE_API_KEY", "key-primary")
        monkeypatch.setenv("GOOGLE_API_KEY_2", "key-fallback")

        ctrl = LLMController(cfg)
        rate_err = litellm.RateLimitError("rate limited", 429, None)
        success_resp = self._mock_response("ok")

        seen_keys: list[str] = []
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            seen_keys.append(kwargs.get("api_key", ""))
            if call_count == 1:
                raise rate_err
            return success_resp

        with patch("litellm.completion", side_effect=side_effect):
            ctrl.chat("hello", [])

        assert seen_keys[0] == "key-primary"
        assert seen_keys[1] == "key-fallback"

    def test_rotation_logs_warning(
        self,
        base_config: dict,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A WARNING must be logged when rotating to a fallback key."""
        import logging
        import litellm

        cfg = self._two_key_config(base_config)
        monkeypatch.setenv("GOOGLE_API_KEY", "key-primary")
        monkeypatch.setenv("GOOGLE_API_KEY_2", "key-fallback")

        ctrl = LLMController(cfg)
        rate_err = litellm.RateLimitError("rate limited", 429, None)

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise rate_err
            return self._mock_response("ok")

        with caplog.at_level(logging.WARNING, logger="llm.controller"):
            with patch("litellm.completion", side_effect=side_effect):
                ctrl.chat("hello", [])

        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("rotating" in m.lower() for m in warning_messages)

    def test_warning_does_not_log_key_values(
        self,
        base_config: dict,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Actual API key strings must never appear in log output."""
        import logging
        import litellm

        cfg = self._two_key_config(base_config)
        monkeypatch.setenv("GOOGLE_API_KEY", "secret-primary-key-abc123")
        monkeypatch.setenv("GOOGLE_API_KEY_2", "secret-fallback-key-xyz789")

        ctrl = LLMController(cfg)
        rate_err = litellm.RateLimitError("rate limited", 429, None)

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise rate_err
            return self._mock_response("ok")

        with caplog.at_level(logging.DEBUG, logger="llm.controller"):
            with patch("litellm.completion", side_effect=side_effect):
                ctrl.chat("hello", [])

        all_log_text = " ".join(r.message for r in caplog.records)
        assert "secret-primary-key-abc123" not in all_log_text
        assert "secret-fallback-key-xyz789" not in all_log_text

    def test_all_keys_exhausted_returns_fallback_message(
        self, base_config: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If every key raises RateLimitError, the graceful fallback is returned."""
        import litellm

        cfg = self._two_key_config(base_config)
        monkeypatch.setenv("GOOGLE_API_KEY", "key-primary")
        monkeypatch.setenv("GOOGLE_API_KEY_2", "key-fallback")

        ctrl = LLMController(cfg)
        rate_err = litellm.RateLimitError("rate limited", 429, None)

        with patch("litellm.completion", side_effect=rate_err):
            reply, _ = ctrl.chat("hello", [])

        assert "please try again" in reply.lower() or "api error" in reply.lower()

    def test_loads_both_keys_from_env(
        self, base_config: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Controller must populate _api_keys with primary and fallback values."""
        cfg = self._two_key_config(base_config)
        monkeypatch.setenv("GOOGLE_API_KEY", "primary-val")
        monkeypatch.setenv("GOOGLE_API_KEY_2", "fallback-val")

        ctrl = LLMController(cfg)

        assert ctrl._api_keys == ["primary-val", "fallback-val"]

    def test_missing_fallback_env_var_skipped(
        self, base_config: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the fallback env var is not set, it is silently skipped."""
        cfg = self._two_key_config(base_config)
        monkeypatch.setenv("GOOGLE_API_KEY", "primary-val")
        monkeypatch.delenv("GOOGLE_API_KEY_2", raising=False)

        ctrl = LLMController(cfg)

        assert ctrl._api_keys == ["primary-val"]
