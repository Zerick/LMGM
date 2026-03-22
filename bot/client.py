"""Discord client for the GURPS AI Game Master bot.

This module is the Discord interface layer only — routing and event handling.
It does not contain any game logic, LLM calls, or rules engine code.
"""
import logging

import discord

logger = logging.getLogger(__name__)

_PHASE1_REPLY = (
    "⚔️ The GURPS GM is online but not yet awakened. Phase 1 skeleton active."
)


class GurpsGMClient(discord.Client):
    """Minimal Discord client for the GURPS GM bot.

    Listens for messages in the configured game channel and replies
    with a hardcoded acknowledgement. All game logic lives in later phases.

    Args:
        config: Parsed config.yaml dictionary.
    """

    def __init__(self, config: dict) -> None:
        """Initialise with message-content intents enabled.

        Args:
            config: Full parsed config.yaml. Only the bot section is used here.
        """
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self._game_channel: str = config["bot"]["main_channel"]

    async def on_ready(self) -> None:
        """Log a confirmation message when the bot successfully connects."""
        logger.info(f"Bot online as {self.user} (id={self.user.id})")
        logger.info(f"Listening in channel: #{self._game_channel}")

    async def on_message(self, message: discord.Message) -> None:
        """Handle an incoming Discord message.

        Ignores:
        - Messages from the bot itself.
        - Messages outside the configured game channel.

        Replies with a hardcoded Phase 1 acknowledgement for all other messages.

        Args:
            message: The incoming Discord message object.
        """
        if message.author == self.user:
            return

        if message.channel.name != self._game_channel:
            return

        logger.info(
            f"Message from {message.author} in #{message.channel.name}: "
            f"{message.content[:80]!r}"
        )
        await message.channel.send(_PHASE1_REPLY)
