"""Campaign-level operations — public interface for the state module.

This is a thin wrapper around db.py. Other modules interact with campaign
state through this interface rather than directly calling the Database class.
"""

from typing import Any, Optional

from state.character import Character
from state.db import Database


class CampaignManager:
    """Manages campaign lifecycle and provides access to campaign data."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create_campaign(
        self, name: str, setting: str, gm_discord_id: str
    ) -> str:
        """Create a new campaign and return its ID."""
        return self._db.create_campaign(name, setting, gm_discord_id)

    def load_campaign(self, campaign_id: str) -> Optional[dict[str, Any]]:
        """Load campaign metadata by ID. Returns None if not found."""
        return self._db.get_campaign(campaign_id)

    def get_active_characters(self, campaign_id: str) -> list[Character]:
        """Return all characters registered in a campaign."""
        return self._db.load_characters_by_campaign(campaign_id)

    def get_recent_scenes(
        self, campaign_id: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Return the N most recently created scenes for a campaign."""
        return self._db.get_recent_scenes(campaign_id, limit=limit)
