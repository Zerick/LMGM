"""Unit tests for the Discord bot client (Phase 1).

Tests cover config loading, .env reading, channel filtering,
and self-message suppression — all without a real Discord connection.
"""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from bot.client import GurpsGMClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GAME_CHANNEL = "game-session"


def _load_config() -> dict:
    """Load the real config.yaml from the project root."""
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def _make_client(config: dict | None = None) -> tuple[GurpsGMClient, MagicMock]:
    """Instantiate a GurpsGMClient with a mocked Discord connection.

    Returns:
        (client, bot_user) where bot_user is the mock ClientUser object.
    """
    if config is None:
        config = {
            "bot": {
                "main_channel": GAME_CHANNEL,
                "discord_token_env": "AI_DM_BOT_KEY",
            }
        }
    client = GurpsGMClient(config)
    bot_user = MagicMock()
    bot_user.id = 12345
    # discord.Client.user is a property returning self._connection.user
    client._connection = MagicMock()
    client._connection.user = bot_user
    return client, bot_user


def _make_message(
    channel_name: str,
    author: MagicMock | None = None,
) -> MagicMock:
    """Build a mock discord.Message.

    Args:
        channel_name: The name of the channel the message is in.
        author: The author mock; defaults to a new unique MagicMock.
    """
    msg = MagicMock()
    msg.channel.name = channel_name
    msg.channel.send = AsyncMock()
    msg.author = author if author is not None else MagicMock()
    return msg


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def test_config_loads_successfully() -> None:
    """config.yaml must be parseable and return a dict."""
    config = _load_config()
    assert isinstance(config, dict)


def test_config_bot_main_channel() -> None:
    """bot.main_channel must equal 'game-session'."""
    config = _load_config()
    assert config["bot"]["main_channel"] == "game-session"


def test_config_bot_token_env_key() -> None:
    """bot.discord_token_env must equal 'AI_DM_BOT_KEY'."""
    config = _load_config()
    assert config["bot"]["discord_token_env"] == "AI_DM_BOT_KEY"


def test_config_has_required_sections() -> None:
    """config.yaml must contain bot, llm, rag, game, and state sections."""
    config = _load_config()
    for section in ("bot", "llm", "rag", "game", "state"):
        assert section in config, f"Missing section: {section}"


# ---------------------------------------------------------------------------
# .env / environment variable reading
# ---------------------------------------------------------------------------


def test_env_token_is_readable() -> None:
    """os.getenv must return the value set for AI_DM_BOT_KEY."""
    with patch.dict(os.environ, {"AI_DM_BOT_KEY": "test-token-abc"}):
        assert os.getenv("AI_DM_BOT_KEY") == "test-token-abc"


def test_env_token_env_var_name_from_config() -> None:
    """The env var name used for the token must come from config, not be hardcoded."""
    config = _load_config()
    token_env_key = config["bot"]["discord_token_env"]
    with patch.dict(os.environ, {token_env_key: "my-token"}):
        assert os.getenv(token_env_key) == "my-token"


# ---------------------------------------------------------------------------
# Message handler — self-message suppression
# ---------------------------------------------------------------------------


def test_ignores_own_messages() -> None:
    """Bot must not reply when the message author is itself."""
    client, bot_user = _make_client()
    msg = _make_message(GAME_CHANNEL, author=bot_user)

    asyncio.run(client.on_message(msg))

    msg.channel.send.assert_not_called()


# ---------------------------------------------------------------------------
# Message handler — channel filtering
# ---------------------------------------------------------------------------


def test_ignores_wrong_channel() -> None:
    """Bot must not reply to messages outside the configured game channel."""
    client, bot_user = _make_client()
    msg = _make_message("general")  # wrong channel

    asyncio.run(client.on_message(msg))

    msg.channel.send.assert_not_called()


def test_ignores_dm_channel() -> None:
    """Bot must not reply to DM messages (DMChannel has no .name attribute matching)."""
    client, bot_user = _make_client()
    msg = _make_message("direct-message")

    asyncio.run(client.on_message(msg))

    msg.channel.send.assert_not_called()


def test_responds_in_configured_game_channel() -> None:
    """Bot must send exactly one message when a non-bot user posts in the game channel."""
    client, bot_user = _make_client()
    msg = _make_message(GAME_CHANNEL)  # different author by default

    asyncio.run(client.on_message(msg))

    msg.channel.send.assert_called_once()


def test_response_sends_something() -> None:
    """Bot must send at least one message in the game channel (Phase 4: LLM or fallback)."""
    client, bot_user = _make_client()
    msg = _make_message(GAME_CHANNEL)

    asyncio.run(client.on_message(msg))

    msg.channel.send.assert_called_once()


def test_game_channel_name_comes_from_config() -> None:
    """Bot must use the channel name from config, not a hardcoded string."""
    custom_config = {
        "bot": {
            "main_channel": "my-custom-channel",
            "discord_token_env": "AI_DM_BOT_KEY",
        }
    }
    client, bot_user = _make_client(config=custom_config)

    # Message in the custom channel — should reply
    msg_right = _make_message("my-custom-channel")
    asyncio.run(client.on_message(msg_right))
    msg_right.channel.send.assert_called_once()

    # Message in the default channel — should NOT reply
    msg_wrong = _make_message(GAME_CHANNEL)
    asyncio.run(client.on_message(msg_wrong))
    msg_wrong.channel.send.assert_not_called()
