"""Discord client for the GURPS AI Game Master bot.

This module is the Discord interface layer only — routing and event handling.
It does not contain any game logic, LLM calls, or rules engine code.
"""
import asyncio
import logging
import re
from typing import Optional

import discord

from llm import LLMController

logger = logging.getLogger(__name__)

_FALLBACK_REPLY = (
    "The GM pauses to collect their thoughts... (not yet ready, please try again)"
)

# Maximum characters per Discord message.
_DISCORD_MAX_LENGTH = 2000


def _extract_game_channel_messages(text: str) -> list[str]:
    """Extract content from all ```game_channel_message``` fenced blocks.

    Args:
        text: The full LLM response text.

    Returns:
        A list of extracted message strings (stripped), one per block found.
        Returns an empty list if no such blocks are present.
    """
    pattern = r"```game_channel_message\s*(.*?)```"
    return [m.strip() for m in re.findall(pattern, text, re.DOTALL)]


def _split_message(text: str, limit: int = _DISCORD_MAX_LENGTH) -> list[str]:
    """Split a long response into chunks that fit within Discord's message limit.

    Splits at paragraph boundaries (double newline) where possible, then at
    single newlines, then at the hard limit as a last resort.

    Args:
        text: The full response text.
        limit: Maximum characters per chunk (default: Discord's 2000-char limit).

    Returns:
        A list of strings each no longer than ``limit`` characters.
    """
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text

    while len(remaining) > limit:
        # Try to split at a paragraph boundary within the limit window.
        split_at = remaining.rfind("\n\n", 0, limit)
        if split_at == -1:
            # Fall back to single newline.
            split_at = remaining.rfind("\n", 0, limit)
        if split_at == -1:
            # Hard split at the limit.
            split_at = limit

        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()

    if remaining:
        chunks.append(remaining)

    return chunks


class GurpsGMClient(discord.Client):
    """Discord client that routes messages through the LLM controller.

    Listens for messages in the configured game channel and passes them
    through the LLMController. Maintains per-channel conversation history.

    Args:
        config: Parsed config.yaml dictionary.
    """

    def __init__(self, config: dict) -> None:
        """Initialise with message-content intents and the LLM controller.

        Args:
            config: Full parsed config.yaml. The bot, llm, and game sections
                are all used.
        """
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)

        bot_cfg = config["bot"]
        self._game_channel: str = bot_cfg["main_channel"]
        self._gm_channel: str = bot_cfg.get("gm_channel", "gm-control")
        # Store as string — Discord IDs can exceed JavaScript's safe integer range.
        self._gm_user_id: str = str(bot_cfg.get("gm_user_id", ""))
        self._config = config

        # Per-channel conversation history: channel_id -> list of message dicts.
        self._history: dict[int, list[dict]] = {}

        # Separate GM directive history: channel_id -> list of message dicts.
        self._gm_history: dict[int, list[dict]] = {}

        # Initialise the LLM controller; fall back gracefully if it errors.
        try:
            self._llm: LLMController | None = LLMController(
                config,
                on_key_rotation=self._key_rotation_callback,
            )
            logger.info("LLMController initialised successfully.")
        except Exception as exc:
            logger.error(f"Failed to initialise LLMController: {exc}")
            self._llm = None

    async def on_ready(self) -> None:
        """Log a confirmation message when the bot successfully connects."""
        logger.info(f"Bot online as {self.user} (id={self.user.id})")
        logger.info(f"Listening in channel: #{self._game_channel}")
        logger.info(f"GM control channel: #{self._gm_channel}")

    async def on_message(self, message: discord.Message) -> None:
        """Handle an incoming Discord message.

        Routes to one of three handlers based on channel context:
        - DM (guild is None): rejected with a short reply.
        - GM control channel: processed via gm_directive() if author matches
          gm_user_id; silently ignored otherwise.
        - Game channel: processed via chat() as a player message.
        - Any other channel: silently ignored.

        Args:
            message: The incoming Discord message object.
        """
        if message.author == self.user:
            return

        # Security: never process DMs. Unmonitored DM channels allow prompt
        # injection attempts that the GM and other players cannot see.
        if message.guild is None:
            await message.channel.send("I only respond in the game channel.")
            return

        channel_name = message.channel.name

        if channel_name == self._gm_channel:
            # Only the configured GM user may issue directives.
            if str(message.author.id) != self._gm_user_id:
                return  # silently ignore non-GM users
            await self._handle_gm_directive(message)
            return

        if channel_name != self._game_channel:
            return  # silently ignore all other channels

        logger.info(
            f"Message from {message.author} in #{message.channel.name}: "
            f"{message.content[:80]!r}"
        )

        if self._llm is None:
            await message.channel.send(_FALLBACK_REPLY)
            return

        channel_id = message.channel.id
        history = self._history.get(channel_id, [])

        reply_text, updated_history = self._llm.chat(message.content, history)
        self._history[channel_id] = updated_history

        for chunk in _split_message(reply_text):
            await message.channel.send(chunk)

    async def _handle_gm_directive(self, message: discord.Message) -> None:
        """Process a directive from the human GM posted in the GM control channel.

        Sends the directive through ``gm_directive()``, replies in the GM
        channel, and forwards any ``game_channel_message`` blocks to the game
        channel as separate messages.

        Args:
            message: The Discord message from the GM in the GM control channel.
        """
        logger.info(
            f"GM directive from {message.author}: {message.content[:80]!r}"
        )

        if self._llm is None:
            await message.channel.send(_FALLBACK_REPLY)
            return

        gm_channel_id = message.channel.id
        gm_history = self._gm_history.get(gm_channel_id, [])

        # Provide game channel history as read-only context for the LLM.
        game_history = self._get_game_channel_history(message.guild)

        reply_text, updated_gm_history = self._llm.gm_directive(
            message.content, gm_history, game_history
        )
        self._gm_history[gm_channel_id] = updated_gm_history

        # Reply to GM in the GM control channel.
        for chunk in _split_message(reply_text):
            await message.channel.send(chunk)

        # Extract and forward any game_channel_message blocks.
        game_msgs = _extract_game_channel_messages(reply_text)
        if game_msgs:
            game_channel = self._find_game_channel(message.guild)
            if game_channel is not None:
                for gm_msg in game_msgs:
                    for chunk in _split_message(gm_msg):
                        await game_channel.send(chunk)

    def _get_game_channel_history(self, guild: discord.Guild) -> list[dict]:
        """Return the stored conversation history for the game channel.

        Args:
            guild: The Discord guild to search for the game channel.

        Returns:
            The history list, or an empty list if not found.
        """
        channel = discord.utils.get(guild.text_channels, name=self._game_channel)
        if channel is None:
            return []
        return self._history.get(channel.id, [])

    def _find_game_channel(
        self, guild: discord.Guild
    ) -> Optional[discord.TextChannel]:
        """Find the game channel object in a guild.

        Args:
            guild: The Discord guild to search.

        Returns:
            The TextChannel, or None if not found.
        """
        return discord.utils.get(guild.text_channels, name=self._game_channel)

    def _key_rotation_callback(self, message: str) -> None:
        """Schedule a notification to the GM control channel on key rotation.

        Called synchronously from within ``_call_with_rotation`` while the
        event loop is blocking on the LiteLLM API call. Schedules the async
        send as a task; it runs after the blocking call returns.

        Args:
            message: Human-readable rotation or exhaustion notice.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._notify_gm_channel(message))
        except Exception as exc:
            logger.warning(f"Could not schedule GM key-rotation notification: {exc}")

    async def _notify_gm_channel(self, message: str) -> None:
        """Send a message to the GM control channel across all guilds.

        Args:
            message: The notification text to send.
        """
        for guild in self.guilds:
            channel = discord.utils.get(
                guild.text_channels, name=self._gm_channel
            )
            if channel is not None:
                await channel.send(message)
                return
