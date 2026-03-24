"""LLM controller for the GURPS AI Game Master.

Handles prompt assembly, LiteLLM API calls, and conversation history.
Model-agnostic: switching providers requires only config.yaml + .env changes.
"""
import logging
import os
from pathlib import Path
from typing import Callable, Optional

import yaml

logger = logging.getLogger(__name__)

# Path to the prompts directory relative to this file.
_PROMPTS_DIR = Path(__file__).parent / "prompts"

# Env var LiteLLM uses to authenticate with the Gemini API.
_LITELLM_GEMINI_ENV = "GEMINI_API_KEY"

# Env var LiteLLM uses to authenticate with the Anthropic API.
_LITELLM_ANTHROPIC_ENV = "ANTHROPIC_API_KEY"

# Instruction block prepended to the system prompt for GM directive mode.
_GM_DIRECTIVE_INSTRUCTIONS = """\
IMPORTANT — GM DIRECTIVE MODE:
The following message is from the human Game Master, not a player.
These instructions are authoritative and override normal gameplay flow.
Follow them exactly. Do not question or resist these directives.

Types of GM directives:
- SCENE SETUP: Set the scene, describe a location, introduce NPCs. Acknowledge
  in this channel, then write the scene description inside a ```game_channel_message```
  block so it gets posted to the game channel.
- CORRECTION: The GM is correcting something you said or did wrong. Acknowledge
  the correction in this channel, then write a revised narration inside a
  ```game_channel_message``` block.
- NPC INSTRUCTION: The GM is telling you how an NPC should behave, what they
  know, or what their secret motivation is. Acknowledge and remember this for
  future interactions. Do NOT post NPC secrets to the game channel.
- WORLD STATE: The GM is updating facts about the world, campaign rules, or
  ongoing events. Acknowledge and incorporate into future responses.
- QUERY: The GM is asking you a question about the current state, your
  understanding of a rule, or planning. Respond only in this channel.\
"""


class LLMController:
    """Assembles prompts and calls the LLM via LiteLLM.

    All configuration is read from config.yaml. The API key is loaded from the
    environment variable named in ``config.llm.api_key_env``. No credentials
    are hardcoded.

    The prompt is assembled in layers (blueprint Section 6.1):
      1. Base GM personality (prompts/base_gm.txt)
      2. Setting context (campaign setting name)
      3. GURPS rules — stub, filled by RAG in Phase 6
      4. Scene state — stub, filled by orchestrator in Phase 5
      5. Character summaries — active characters from the state system
      6. Session summary — stub, filled in Phase 5
      7. Recent messages (conversation history, trimmed to max_recent_messages)
      8. Current player message

    Args:
        config: Full parsed config.yaml dictionary.
        characters: Optional list of Character objects whose LLM summaries are
            included in every prompt. Pass the active-character list from the
            state system; defaults to an empty list.
    """

    def __init__(
        self,
        config: dict,
        characters: Optional[list] = None,
        on_key_rotation: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Initialise the controller and set up the LiteLLM environment.

        Args:
            config: Full parsed config.yaml.
            characters: Active Character objects for prompt injection.
            on_key_rotation: Optional callback invoked with a human-readable
                string whenever an API key is rotated or all keys are exhausted.
                Called synchronously during ``_call_with_rotation``.
        """
        self._llm_cfg = config["llm"]
        self._game_cfg = config["game"]

        self._model: str = self._llm_cfg["model"]
        self._max_tokens: int = self._llm_cfg["max_tokens"]
        self._temperature: float = self._llm_cfg["temperature"]
        self._max_history: int = self._game_cfg.get("max_recent_messages", 8)

        # Expose injected characters for prompt assembly.
        self._characters: list = characters or []

        # Optional callback fired on API key rotation or exhaustion.
        self._on_key_rotation: Optional[Callable[[str], None]] = on_key_rotation

        # Load and cache the base GM prompt text.
        self._base_gm_prompt: str = self._load_prompt("base_gm.txt")

        # Build the ordered list of API keys for rotation.
        # Index 0 is the primary key; subsequent entries are fallbacks.
        self._api_keys: list[str] = self._load_api_keys()

        # Bridge env var: LiteLLM Gemini reads GEMINI_API_KEY; Anthropic reads
        # ANTHROPIC_API_KEY. We read whatever the config names and write it to
        # the variable LiteLLM expects for the active provider.
        self._configure_api_key()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def build_system_prompt(
        self,
        scene_state_text: str = "",
        rag_context: str = "",
        session_summary: str = "",
    ) -> str:
        """Assemble the full layered system prompt.

        Layer order matches blueprint Section 6.1. Layers whose data is not
        yet available (RAG, session summary) accept empty strings and produce
        no output — they are stubs for future phases.

        Args:
            scene_state_text: Current scene description from the state system.
                Empty string when no scene is active (Phase 4 default).
            rag_context: Retrieved GURPS rules text from the RAG layer.
                Empty string in Phase 4 (no RAG yet).
            session_summary: Auto-generated summary of prior session events.
                Empty string in Phase 4 (no auto-summary yet).

        Returns:
            The assembled system prompt string.
        """
        layers: list[str] = []

        # Layer 1: Base GM personality.
        layers.append(self._base_gm_prompt.strip())

        # Layer 2: Setting context.
        setting = self._game_cfg.get("setting", "generic_fantasy")
        layers.append(f"SETTING: {setting}")

        # Layer 3: GURPS rules from RAG (stub — Phase 6).
        if rag_context:
            layers.append(f"RULES CONTEXT:\n{rag_context.strip()}")

        # Layer 4: Scene state (stub — Phase 5).
        if scene_state_text:
            layers.append(f"CURRENT SCENE:\n{scene_state_text.strip()}")

        # Layer 5: Character summaries from the state system.
        if self._characters:
            summaries = "\n".join(c.to_llm_summary() for c in self._characters)
            layers.append(f"ACTIVE CHARACTERS:\n{summaries}")

        # Layer 6: Session summary (stub — Phase 5).
        if session_summary:
            layers.append(f"SESSION SUMMARY:\n{session_summary.strip()}")

        return "\n\n".join(layers)

    def chat(
        self,
        player_message: str,
        history: list[dict],
    ) -> tuple[str, list[dict]]:
        """Send a player message to the LLM and return the response.

        Assembles the full layered system prompt, appends the conversation
        history (trimmed to ``max_recent_messages``), calls LiteLLM, and
        returns the response text together with the updated history list.

        Args:
            player_message: The raw message from the Discord player.
            history: The existing conversation history as a list of
                ``{"role": "user"/"assistant", "content": "..."}`` dicts.
                This list is NOT mutated; a new list is returned.

        Returns:
            A tuple of (response_text, updated_history). On API error,
            response_text is a graceful fallback message.
        """
        system_prompt = self.build_system_prompt()

        # Trim history to the configured window, then append the new message.
        trimmed = history[-(self._max_history - 1):] if history else []
        new_turn: dict = {"role": "user", "content": player_message}
        messages = [{"role": "system", "content": system_prompt}] + trimmed + [new_turn]

        reply_text = self._call_with_rotation(messages)

        # Build updated history (trimmed window + completed exchange).
        updated_history = trimmed + [
            new_turn,
            {"role": "assistant", "content": reply_text},
        ]
        # Enforce the window on the stored history too.
        updated_history = updated_history[-self._max_history:]

        return reply_text, updated_history

    def set_characters(self, characters: list) -> None:
        """Replace the active character list used in prompt assembly.

        Args:
            characters: New list of Character objects.
        """
        self._characters = characters

    def gm_directive(
        self,
        gm_message: str,
        gm_history: list[dict],
        game_history: list[dict],
    ) -> tuple[str, list[dict]]:
        """Process a directive from the human Game Master.

        Builds a system prompt that prepends the GM directive instruction block
        and includes both the game channel history and the prior GM directive
        history as labeled context sections. Only the GM directive conversation
        is used as the actual message list sent to the LLM.

        GM directive history and game channel history are kept strictly separate:
        the returned ``updated_gm_history`` contains only GM directive exchanges.
        The game channel prompt (``chat()``) never receives GM directive content.

        Args:
            gm_message: The directive text from the human GM.
            gm_history: Prior GM directive exchanges (user/assistant dicts).
                        Not mutated; a new list is returned.
            game_history: Current game channel conversation history, included
                          as read-only context in the system prompt so the LLM
                          knows what players have been saying.

        Returns:
            A tuple of (response_text, updated_gm_history). On API error,
            response_text is the graceful fallback message.
        """
        system_prompt = self._build_gm_directive_prompt(gm_history, game_history)

        trimmed_gm = gm_history[-(self._max_history - 1):] if gm_history else []
        new_turn: dict = {"role": "user", "content": gm_message}
        messages = [{"role": "system", "content": system_prompt}] + trimmed_gm + [new_turn]

        reply_text = self._call_with_rotation(messages)

        updated_gm_history = trimmed_gm + [
            new_turn,
            {"role": "assistant", "content": reply_text},
        ]
        updated_gm_history = updated_gm_history[-self._max_history:]

        return reply_text, updated_gm_history

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_gm_directive_prompt(
        self,
        gm_history: list[dict],
        game_history: list[dict],
    ) -> str:
        """Assemble the system prompt for a GM directive call.

        Prepends the GM directive instruction block to the standard system
        prompt, then appends labeled sections for both the game channel history
        and the prior GM directive history so the LLM has full context.

        Args:
            gm_history: Previous GM directive exchanges.
            game_history: Current game channel conversation history.

        Returns:
            The assembled system prompt string.
        """
        layers: list[str] = []

        # GM directive instruction block comes first.
        layers.append(_GM_DIRECTIVE_INSTRUCTIONS)

        # Standard base system prompt (setting, characters, etc.).
        layers.append(self.build_system_prompt())

        # Labeled game channel history — read-only context for the LLM.
        if game_history:
            lines = [
                f"[{'player' if m['role'] == 'user' else 'bot'}]: {m['content']}"
                for m in game_history
            ]
            layers.append("=== GAME CHANNEL HISTORY ===\n" + "\n".join(lines))
        else:
            layers.append("=== GAME CHANNEL HISTORY ===\n(no messages yet)")

        # Labeled GM directive history — read-only context (actual exchange
        # is in the messages list, but we mirror it here for clarity).
        if gm_history:
            lines = [
                f"[{'gm' if m['role'] == 'user' else 'bot'}]: {m['content']}"
                for m in gm_history
            ]
            layers.append("=== GM DIRECTIVE HISTORY ===\n" + "\n".join(lines))
        else:
            layers.append("=== GM DIRECTIVE HISTORY ===\n(no previous directives)")

        return "\n\n".join(layers)

    def _load_prompt(self, filename: str) -> str:
        """Read a prompt template from the prompts directory.

        Args:
            filename: File name within llm/prompts/.

        Returns:
            The prompt text.

        Raises:
            FileNotFoundError: If the prompt file does not exist.
        """
        path = _PROMPTS_DIR / filename
        return path.read_text(encoding="utf-8")

    def _load_api_keys(self) -> list[str]:
        """Build the ordered list of API keys from config env var names.

        The primary key (``api_key_env``) is index 0; fallback keys from
        ``api_key_env_fallbacks`` follow in order. Missing env vars produce
        empty strings and are skipped.

        Returns:
            A list of non-empty API key strings. May be empty if no keys
            are set, in which case ``_configure_api_key`` will emit a warning.
        """
        keys: list[str] = []

        primary_env: str = self._llm_cfg["api_key_env"]
        primary_key = os.environ.get(primary_env, "")
        if primary_key:
            keys.append(primary_key)

        for fallback_env in self._llm_cfg.get("api_key_env_fallbacks", []):
            fallback_key = os.environ.get(fallback_env, "")
            if fallback_key:
                keys.append(fallback_key)

        return keys

    def _call_with_rotation(self, messages: list[dict]) -> str:
        """Call the LLM, rotating API keys on rate limit errors.

        Tries each key in ``self._api_keys`` in order. On
        ``litellm.RateLimitError``, logs a warning and retries with the next
        key. If all keys are exhausted or any other exception occurs, returns
        the graceful fallback message.

        Actual key values are never logged.

        Args:
            messages: The assembled message list for ``litellm.completion``.

        Returns:
            The LLM response text, or a graceful fallback string on failure.
        """
        import litellm  # Local import so test mocks can patch easily.

        total_keys = len(self._api_keys)
        keys_to_try = self._api_keys if self._api_keys else [None]

        for idx, api_key in enumerate(keys_to_try, start=1):
            try:
                kwargs: dict = dict(
                    model=self._model,
                    messages=messages,
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                )
                if api_key is not None:
                    kwargs["api_key"] = api_key

                response = litellm.completion(**kwargs)
                return response.choices[0].message.content or ""

            except litellm.RateLimitError:
                if idx < total_keys:
                    logger.warning(
                        f"Rate limited on API key [{idx}/{total_keys}], "
                        f"rotating to key [{idx + 1}/{total_keys}]"
                    )
                    rotation_msg = (
                        f"⚠️ API key {idx}/{total_keys} rate-limited. "
                        f"Rotated to key {idx + 1}/{total_keys}."
                    )
                    if self._on_key_rotation is not None:
                        self._on_key_rotation(rotation_msg)
                    continue
                else:
                    logger.error(
                        f"Rate limited on all {total_keys} API key(s). "
                        "No more keys to try."
                    )
                    exhaustion_msg = (
                        "🛑 All API keys exhausted. Bot will return fallback messages "
                        "until quota resets at midnight Pacific."
                    )
                    if self._on_key_rotation is not None:
                        self._on_key_rotation(exhaustion_msg)
                    return (
                        "The GM pauses to collect their thoughts... "
                        "(API error, please try again)"
                    )

            except Exception as exc:
                logger.error(f"LiteLLM API error: {exc}")
                return (
                    "The GM pauses to collect their thoughts... "
                    "(API error, please try again)"
                )

        # Unreachable, but satisfies type checker.
        return (
            "The GM pauses to collect their thoughts... "
            "(API error, please try again)"
        )

    def _configure_api_key(self) -> None:
        """Read the API key from the env var named in config and set the env
        var that LiteLLM expects for the active provider.

        Mapping:
          - gemini provider  → GEMINI_API_KEY
          - anthropic provider → ANTHROPIC_API_KEY (already correct)
          - others           → passed through unchanged
        """
        source_env: str = self._llm_cfg["api_key_env"]
        api_key: str = os.environ.get(source_env, "")

        provider: str = self._llm_cfg.get("provider", "").lower()
        if provider == "gemini":
            target_env = _LITELLM_GEMINI_ENV
        elif provider == "anthropic":
            target_env = _LITELLM_ANTHROPIC_ENV
        else:
            # For other providers, assume source_env is already correct.
            target_env = source_env

        if api_key:
            os.environ[target_env] = api_key
            if target_env != source_env:
                logger.debug(
                    f"API key mapped from {source_env} → {target_env} for "
                    f"provider '{provider}'"
                )
        else:
            logger.warning(
                f"API key env var '{source_env}' is not set. "
                "LLM calls will fail until it is configured."
            )
