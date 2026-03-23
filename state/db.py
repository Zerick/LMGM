"""SQLite persistence layer for the GURPS GM bot.

All six tables from the blueprint schema are created here. WAL mode is
enabled for better concurrent read performance on the Raspberry Pi.

All SQL uses parameterized queries — no f-string interpolation in SQL text.
"""

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from state.character import Character


def _new_id() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Thin wrapper around a SQLite connection providing CRUD for all tables."""

    def __init__(self, db_path: str) -> None:
        self._path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_schema()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a SQL statement and return the cursor."""
        return self._conn.execute(sql, params)

    def _create_schema(self) -> None:
        """Create all tables if they do not already exist."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS campaigns (
                id              TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                setting         TEXT NOT NULL,
                created_at      TEXT NOT NULL,
                gm_discord_id   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS characters (
                id              TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                discord_user_id TEXT NOT NULL,
                data_json       TEXT NOT NULL,
                campaign_id     TEXT NOT NULL REFERENCES campaigns(id)
            );

            CREATE TABLE IF NOT EXISTS scenes (
                id              TEXT PRIMARY KEY,
                campaign_id     TEXT NOT NULL REFERENCES campaigns(id),
                description     TEXT NOT NULL,
                scene_type      TEXT NOT NULL,
                created_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS action_log (
                id              TEXT PRIMARY KEY,
                scene_id        TEXT NOT NULL REFERENCES scenes(id),
                character_id    TEXT NOT NULL REFERENCES characters(id),
                action_json     TEXT NOT NULL,
                result_json     TEXT NOT NULL,
                timestamp       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS session_summaries (
                id              TEXT PRIMARY KEY,
                campaign_id     TEXT NOT NULL REFERENCES campaigns(id),
                summary_text    TEXT NOT NULL,
                message_range   TEXT NOT NULL,
                created_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS custom_rules (
                id              TEXT PRIMARY KEY,
                campaign_id     TEXT NOT NULL REFERENCES campaigns(id),
                rule_name       TEXT NOT NULL,
                rule_text       TEXT NOT NULL
            );
        """)
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    # ------------------------------------------------------------------
    # Campaign CRUD
    # ------------------------------------------------------------------

    def create_campaign(self, name: str, setting: str, gm_discord_id: str) -> str:
        """Insert a new campaign and return its generated ID."""
        cid = _new_id()
        self._conn.execute(
            "INSERT INTO campaigns (id, name, setting, created_at, gm_discord_id) VALUES (?, ?, ?, ?, ?)",
            (cid, name, setting, _now_iso(), gm_discord_id),
        )
        self._conn.commit()
        return cid

    def get_campaign(self, campaign_id: str) -> Optional[dict[str, Any]]:
        """Return campaign row as a dict, or None if not found."""
        row = self._conn.execute(
            "SELECT * FROM campaigns WHERE id = ?", (campaign_id,)
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Character CRUD
    # ------------------------------------------------------------------

    def save_character(self, character: Character, campaign_id: str) -> str:
        """Insert a new character record and return its generated ID."""
        char_id = _new_id()
        self._conn.execute(
            "INSERT INTO characters (id, name, discord_user_id, data_json, campaign_id) VALUES (?, ?, ?, ?, ?)",
            (char_id, character.name, character.player_discord_id, character.to_json(), campaign_id),
        )
        self._conn.commit()
        return char_id

    def load_character(self, character_id: str) -> Optional[Character]:
        """Return a Character object by ID, or None if not found."""
        row = self._conn.execute(
            "SELECT data_json FROM characters WHERE id = ?", (character_id,)
        ).fetchone()
        if row is None:
            return None
        return Character.model_validate_json(row["data_json"])

    def update_character(self, character_id: str, character: Character) -> None:
        """Overwrite the stored JSON for an existing character."""
        self._conn.execute(
            "UPDATE characters SET name = ?, discord_user_id = ?, data_json = ? WHERE id = ?",
            (character.name, character.player_discord_id, character.to_json(), character_id),
        )
        self._conn.commit()

    def delete_character(self, character_id: str) -> None:
        """Delete a character record by ID."""
        self._conn.execute("DELETE FROM characters WHERE id = ?", (character_id,))
        self._conn.commit()

    def load_characters_by_campaign(self, campaign_id: str) -> list[Character]:
        """Return all characters in a campaign."""
        rows = self._conn.execute(
            "SELECT data_json FROM characters WHERE campaign_id = ?", (campaign_id,)
        ).fetchall()
        return [Character.model_validate_json(row["data_json"]) for row in rows]

    def load_characters_by_discord_user(self, discord_user_id: str, campaign_id: str) -> list[Character]:
        """Return all characters belonging to a specific Discord user in a campaign."""
        rows = self._conn.execute(
            "SELECT data_json FROM characters WHERE discord_user_id = ? AND campaign_id = ?",
            (discord_user_id, campaign_id),
        ).fetchall()
        return [Character.model_validate_json(row["data_json"]) for row in rows]

    # ------------------------------------------------------------------
    # Scene CRUD
    # ------------------------------------------------------------------

    def create_scene(self, campaign_id: str, description: str, scene_type: str) -> str:
        """Insert a new scene and return its generated ID."""
        sid = _new_id()
        self._conn.execute(
            "INSERT INTO scenes (id, campaign_id, description, scene_type, created_at) VALUES (?, ?, ?, ?, ?)",
            (sid, campaign_id, description, scene_type, _now_iso()),
        )
        self._conn.commit()
        return sid

    def get_scene(self, scene_id: str) -> Optional[dict[str, Any]]:
        """Return a scene row as a dict, or None if not found."""
        row = self._conn.execute(
            "SELECT * FROM scenes WHERE id = ?", (scene_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_recent_scenes(self, campaign_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """Return the N most recent scenes for a campaign."""
        rows = self._conn.execute(
            "SELECT * FROM scenes WHERE campaign_id = ? ORDER BY created_at DESC LIMIT ?",
            (campaign_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Action log
    # ------------------------------------------------------------------

    def append_action(
        self,
        scene_id: str,
        character_id: str,
        action_json: str,
        result_json: str,
    ) -> str:
        """Append an action to the log and return its generated ID."""
        action_id = _new_id()
        self._conn.execute(
            "INSERT INTO action_log (id, scene_id, character_id, action_json, result_json, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (action_id, scene_id, character_id, action_json, result_json, _now_iso()),
        )
        self._conn.commit()
        return action_id

    def get_actions_for_scene(self, scene_id: str) -> list[dict[str, Any]]:
        """Return all action log entries for a scene, ordered by timestamp."""
        rows = self._conn.execute(
            "SELECT * FROM action_log WHERE scene_id = ? ORDER BY timestamp ASC",
            (scene_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Session summaries
    # ------------------------------------------------------------------

    def create_session_summary(
        self, campaign_id: str, summary_text: str, message_range: str
    ) -> str:
        """Insert a session summary and return its generated ID."""
        sid = _new_id()
        self._conn.execute(
            "INSERT INTO session_summaries (id, campaign_id, summary_text, message_range, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (sid, campaign_id, summary_text, message_range, _now_iso()),
        )
        self._conn.commit()
        return sid

    def get_latest_summary(self, campaign_id: str) -> Optional[dict[str, Any]]:
        """Return the most recent session summary for a campaign, or None."""
        row = self._conn.execute(
            "SELECT * FROM session_summaries WHERE campaign_id = ? ORDER BY created_at DESC LIMIT 1",
            (campaign_id,),
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Custom rules
    # ------------------------------------------------------------------

    def create_custom_rule(self, campaign_id: str, rule_name: str, rule_text: str) -> str:
        """Insert a custom rule and return its generated ID."""
        rid = _new_id()
        self._conn.execute(
            "INSERT INTO custom_rules (id, campaign_id, rule_name, rule_text) VALUES (?, ?, ?, ?)",
            (rid, campaign_id, rule_name, rule_text),
        )
        self._conn.commit()
        return rid

    def get_custom_rules(self, campaign_id: str) -> list[dict[str, Any]]:
        """Return all custom rules for a campaign."""
        rows = self._conn.execute(
            "SELECT * FROM custom_rules WHERE campaign_id = ?", (campaign_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def delete_custom_rule(self, rule_id: str) -> None:
        """Delete a custom rule by ID."""
        self._conn.execute("DELETE FROM custom_rules WHERE id = ?", (rule_id,))
        self._conn.commit()
