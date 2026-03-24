"""Discord client for the GURPS AI Game Master bot.

This module is the Discord interface layer only — routing and event handling.
It does not contain any game logic, LLM calls, or rules engine code.
"""
import logging

import discord

from llm import LLMController

logger = logging.getLogger(__name__)

_FALLBACK_REPLY = (
    "The GM pauses to collect their thoughts... (not yet ready, please try again)"
)

# Maximum characters per Discord message.
_DISCORD_MAX_LENGTH = 2000


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

        self._game_channel: str = config["bot"]["main_channel"]
        self._config = config

        # Per-channel conversation history: channel_id -> list of message dicts.
        self._history: dict[int, list[dict]] = {}

        # Initialise the LLM controller; fall back gracefully if it errors.
        try:
            self._llm: LLMController | None = LLMController(config)
            logger.info("LLMController initialised successfully.")
        except Exception as exc:
            logger.error(f"Failed to initialise LLMController: {exc}")
            self._llm = None

    async def on_ready(self) -> None:
        """Log a confirmation message when the bot successfully connects."""
        logger.info(f"Bot online as {self.user} (id={self.user.id})")
        logger.info(f"Listening in channel: #{self._game_channel}")

    async def on_message(self, message: discord.Message) -> None:
        """Handle an incoming Discord message.

        Ignores:
        - Messages from the bot itself.
        - Messages outside the configured game channel.

        Passes all other messages through the LLM controller and sends the
        response back, splitting into multiple messages if needed.

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

        if message.channel.name != self._game_channel:
            return

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
