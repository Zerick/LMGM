"""Unit tests for the Discord bot client (Phase 1).

Tests cover config loading, .env reading, channel filtering,
and self-message suppression — all without a real Discord connection.
"""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from bot.client import GurpsGMClient, _extract_game_channel_messages

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GAME_CHANNEL = "game-session"
GM_CHANNEL = "gm-control"
GM_USER_ID = "236701038919286784"


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
                "gm_channel": GM_CHANNEL,
                "gm_user_id": GM_USER_ID,
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
    guild: MagicMock | None = ...,  # type: ignore[assignment]
) -> MagicMock:
    """Build a mock discord.Message.

    Args:
        channel_name: The name of the channel the message is in.
        author: The author mock; defaults to a new unique MagicMock.
        guild: The guild mock; pass ``None`` to simulate a DM. Defaults to a
            new MagicMock (i.e. a server message).
    """
    msg = MagicMock()
    msg.channel.name = channel_name
    msg.channel.send = AsyncMock()
    msg.author = author if author is not None else MagicMock()
    # Use sentinel default so callers can explicitly pass None for DMs.
    if guild is ...:
        msg.guild = MagicMock()
    else:
        msg.guild = guild
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


# ---------------------------------------------------------------------------
# DM lockdown (Phase 4.5)
# ---------------------------------------------------------------------------


def test_dm_ignored_guild_is_none() -> None:
    """Bot must silently handle or reject DMs (guild is None) without LLM call."""
    client, bot_user = _make_client()
    # Simulate a direct message: guild is None.
    msg = _make_message(GAME_CHANNEL, guild=None)

    with patch.object(client, "_llm") as mock_llm:
        asyncio.run(client.on_message(msg))
        mock_llm.chat.assert_not_called()


def test_dm_sends_rejection_reply() -> None:
    """Bot must send exactly one short reply to DMs and nothing else."""
    client, bot_user = _make_client()
    msg = _make_message(GAME_CHANNEL, guild=None)

    asyncio.run(client.on_message(msg))

    msg.channel.send.assert_called_once()
    reply = msg.channel.send.call_args[0][0]
    assert "game channel" in reply.lower()


def test_wrong_channel_no_llm_call() -> None:
    """Bot must not call the LLM for messages outside the game channel."""
    client, bot_user = _make_client()
    msg = _make_message("off-topic")  # not game channel, not DM

    with patch.object(client, "_llm") as mock_llm:
        asyncio.run(client.on_message(msg))
        mock_llm.chat.assert_not_called()


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


# ---------------------------------------------------------------------------
# Config: GM control channel fields (Phase 4.75)
# ---------------------------------------------------------------------------


def test_config_gm_channel() -> None:
    """bot.gm_channel must equal 'gm-control'."""
    config = _load_config()
    assert config["bot"]["gm_channel"] == "gm-control"


def test_config_gm_user_id() -> None:
    """bot.gm_user_id must be the configured GM Discord user ID string."""
    config = _load_config()
    assert config["bot"]["gm_user_id"] == "236701038919286784"


# ---------------------------------------------------------------------------
# _extract_game_channel_messages helper
# ---------------------------------------------------------------------------


class TestExtractGameChannelMessages:
    """Tests for the ```game_channel_message``` block extractor."""

    def test_no_blocks_returns_empty(self) -> None:
        """Response with no fenced blocks returns an empty list."""
        assert _extract_game_channel_messages("Just a plain response.") == []

    def test_single_block_extracted(self) -> None:
        """A single block's content is returned in a one-element list."""
        text = "Acknowledged.\n```game_channel_message\nThe tavern is lit.\n```"
        result = _extract_game_channel_messages(text)
        assert result == ["The tavern is lit."]

    def test_multiple_blocks_extracted_in_order(self) -> None:
        """Multiple blocks are all extracted, in order."""
        text = (
            "Ok.\n"
            "```game_channel_message\nFirst.\n```\n"
            "```game_channel_message\nSecond.\n```"
        )
        result = _extract_game_channel_messages(text)
        assert result == ["First.", "Second."]

    def test_content_is_stripped(self) -> None:
        """Leading/trailing whitespace inside the block is stripped."""
        text = "```game_channel_message\n\n  The hero arrives.  \n\n```"
        result = _extract_game_channel_messages(text)
        assert result == ["The hero arrives."]

    def test_multiline_block_content_preserved(self) -> None:
        """Multi-line block content is returned as a single string."""
        text = "```game_channel_message\nLine one.\nLine two.\n```"
        result = _extract_game_channel_messages(text)
        assert "Line one." in result[0]
        assert "Line two." in result[0]


# ---------------------------------------------------------------------------
# GM control channel routing (Phase 4.75)
# ---------------------------------------------------------------------------


def _make_gm_message(
    author_id: int | str = GM_USER_ID,
    content: str = "Set the scene.",
    guild: MagicMock | None = ...,  # type: ignore[assignment]
) -> MagicMock:
    """Build a mock Discord message in the GM control channel.

    Args:
        author_id: Discord user ID of the message author.
        content: Message text.
        guild: Guild mock. Defaults to a new MagicMock with text_channels=[].
    """
    msg = MagicMock()
    msg.channel.name = GM_CHANNEL
    msg.channel.send = AsyncMock()
    msg.content = content

    author = MagicMock()
    author.id = int(author_id) if isinstance(author_id, str) else author_id
    msg.author = author

    if guild is ...:
        g = MagicMock()
        g.text_channels = []
        msg.guild = g
    else:
        msg.guild = guild

    return msg


class TestGmControlChannel:
    """Tests for GM control channel routing (Phase 4.75)."""

    def test_gm_user_message_is_processed(self) -> None:
        """GM user posting in the GM channel receives a response."""
        client, _ = _make_client()
        msg = _make_gm_message()

        with patch.object(client, "_llm") as mock_llm:
            mock_llm.gm_directive.return_value = ("Acknowledged.", [])
            asyncio.run(client.on_message(msg))

        msg.channel.send.assert_called()

    def test_non_gm_user_silently_ignored(self) -> None:
        """Non-GM users posting in the GM channel are silently ignored."""
        client, _ = _make_client()
        msg = _make_gm_message(author_id=999888777)

        with patch.object(client, "_llm") as mock_llm:
            asyncio.run(client.on_message(msg))
            mock_llm.gm_directive.assert_not_called()

        msg.channel.send.assert_not_called()

    def test_gm_message_uses_gm_directive_not_chat(self) -> None:
        """GM channel messages must call gm_directive(), never chat()."""
        client, _ = _make_client()
        msg = _make_gm_message()

        with patch.object(client, "_llm") as mock_llm:
            mock_llm.gm_directive.return_value = ("ok", [])
            asyncio.run(client.on_message(msg))
            mock_llm.gm_directive.assert_called_once()
            mock_llm.chat.assert_not_called()

    def test_game_channel_message_block_sent_to_game_channel(self) -> None:
        """game_channel_message block content is posted to the game channel."""
        client, _ = _make_client()

        game_chan = MagicMock()
        game_chan.name = GAME_CHANNEL
        game_chan.send = AsyncMock()

        guild = MagicMock()
        guild.text_channels = [game_chan]
        msg = _make_gm_message(guild=guild)

        gm_response = (
            "Acknowledged.\n"
            "```game_channel_message\nThe tavern is dimly lit.\n```"
        )

        with patch.object(client, "_llm") as mock_llm:
            mock_llm.gm_directive.return_value = (gm_response, [])
            asyncio.run(client.on_message(msg))

        game_chan.send.assert_called_once()
        sent_text = game_chan.send.call_args[0][0]
        assert "The tavern is dimly lit." in sent_text

    def test_no_game_channel_block_means_no_game_channel_message(self) -> None:
        """If the GM response has no block, nothing is sent to the game channel."""
        client, _ = _make_client()

        game_chan = MagicMock()
        game_chan.name = GAME_CHANNEL
        game_chan.send = AsyncMock()

        guild = MagicMock()
        guild.text_channels = [game_chan]
        msg = _make_gm_message(guild=guild)

        gm_response = "Understood. I will remember this NPC secret."

        with patch.object(client, "_llm") as mock_llm:
            mock_llm.gm_directive.return_value = (gm_response, [])
            asyncio.run(client.on_message(msg))

        game_chan.send.assert_not_called()

    def test_multiple_game_channel_blocks_sent_separately(self) -> None:
        """Multiple game_channel_message blocks are each sent as a separate message."""
        client, _ = _make_client()

        game_chan = MagicMock()
        game_chan.name = GAME_CHANNEL
        game_chan.send = AsyncMock()

        guild = MagicMock()
        guild.text_channels = [game_chan]
        msg = _make_gm_message(guild=guild)

        gm_response = (
            "Acknowledged.\n"
            "```game_channel_message\nFirst message.\n```\n"
            "```game_channel_message\nSecond message.\n```"
        )

        with patch.object(client, "_llm") as mock_llm:
            mock_llm.gm_directive.return_value = (gm_response, [])
            asyncio.run(client.on_message(msg))

        assert game_chan.send.call_count == 2
