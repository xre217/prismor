"""SQLite persistence for Nazo Arena."""

from __future__ import annotations

import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "nazo-arena.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    id TEXT PRIMARY KEY,
    token TEXT UNIQUE NOT NULL,
    nickname TEXT NOT NULL,
    faction_id TEXT,
    wars_won INTEGER NOT NULL DEFAULT 0,
    wars_lost INTEGER NOT NULL DEFAULT 0,
    duels_won INTEGER NOT NULL DEFAULT 0,
    duels_lost INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS factions (
    id TEXT PRIMARY KEY,
    elo INTEGER NOT NULL DEFAULT 1000,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS fighter_mastery (
    player_id TEXT NOT NULL,
    fighter_id TEXT NOT NULL,
    xp INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, fighter_id),
    FOREIGN KEY (player_id) REFERENCES players(id)
);

CREATE TABLE IF NOT EXISTS war_log (
    id TEXT PRIMARY KEY,
    home_faction TEXT NOT NULL,
    away_faction TEXT NOT NULL,
    home_score INTEGER NOT NULL,
    away_score INTEGER NOT NULL,
    winner_faction TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_players_token ON players(token);
CREATE INDEX IF NOT EXISTS idx_mastery_player ON fighter_mastery(player_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ArenaStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.environ.get("NAZO_ARENA_DB", DEFAULT_DB))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def create_player(self, nickname: str) -> dict:
        pid = str(uuid.uuid4())
        token = secrets.token_urlsafe(24)
        now = _now()
        self.conn.execute(
            "INSERT INTO players (id, token, nickname, created_at, last_seen) VALUES (?, ?, ?, ?, ?)",
            (pid, token, nickname, now, now),
        )
        self.conn.commit()
        return self.get_player_by_id(pid)  # type: ignore

    def get_player_by_token(self, token: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM players WHERE token = ?", (token,)).fetchone()
        return dict(row) if row else None

    def get_player_by_id(self, pid: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM players WHERE id = ?", (pid,)).fetchone()
        return dict(row) if row else None

    def touch_player(self, pid: str, nickname: str | None = None) -> None:
        if nickname:
            self.conn.execute(
                "UPDATE players SET last_seen = ?, nickname = ? WHERE id = ?",
                (_now(), nickname[:20], pid),
            )
        else:
            self.conn.execute("UPDATE players SET last_seen = ? WHERE id = ?", (_now(), pid))
        self.conn.commit()

    def set_player_faction(self, pid: str, faction_id: str | None) -> None:
        self.conn.execute(
            "UPDATE players SET faction_id = ?, last_seen = ? WHERE id = ?",
            (faction_id, _now(), pid),
        )
        self.conn.commit()

    def record_player_war(self, pid: str, won: bool) -> None:
        col = "wars_won" if won else "wars_lost"
        self.conn.execute(
            f"UPDATE players SET {col} = {col} + 1, last_seen = ? WHERE id = ?",
            (_now(), pid),
        )
        self.conn.commit()

    def add_mastery(self, pid: str, fighter_id: str, xp: int, won: bool) -> None:
        col = "wins" if won else "losses"
        self.conn.execute(
            f"""
            INSERT INTO fighter_mastery (player_id, fighter_id, xp, wins, losses)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(player_id, fighter_id) DO UPDATE SET
                xp = xp + excluded.xp,
                {col} = {col} + 1
            """,
            (pid, fighter_id, xp, 1 if won else 0, 0 if won else 1),
        )
        self.conn.commit()

    def player_mastery(self, pid: str, limit: int = 8) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT fighter_id, xp, wins, losses
            FROM fighter_mastery WHERE player_id = ?
            ORDER BY xp DESC LIMIT ?
            """,
            (pid, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def player_public(self, pid: str) -> dict | None:
        p = self.get_player_by_id(pid)
        if not p:
            return None
        return {
            "id": p["id"],
            "nickname": p["nickname"],
            "factionId": p["faction_id"],
            "warsWon": p["wars_won"],
            "warsLost": p["wars_lost"],
            "duelsWon": p["duels_won"],
            "duelsLost": p["duels_lost"],
            "mastery": self.player_mastery(pid),
        }

    def ensure_factions(self, faction_ids: list[str]) -> None:
        for fid in faction_ids:
            self.conn.execute(
                "INSERT OR IGNORE INTO factions (id, elo, wins, losses) VALUES (?, 1000, 0, 0)",
                (fid,),
            )
        self.conn.commit()

    def get_faction(self, fid: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM factions WHERE id = ?", (fid,)).fetchone()
        return dict(row) if row else None

    def save_faction_stats(self, fid: str, elo: int, wins: int, losses: int) -> None:
        self.conn.execute(
            """
            INSERT INTO factions (id, elo, wins, losses) VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET elo = excluded.elo, wins = excluded.wins, losses = excluded.losses
            """,
            (fid, elo, wins, losses),
        )
        self.conn.commit()

    def faction_standings(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, elo, wins, losses FROM factions ORDER BY elo DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def log_war(
        self,
        home_faction: str,
        away_faction: str,
        home_score: int,
        away_score: int,
        winner_faction: str | None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO war_log (id, home_faction, away_faction, home_score, away_score, winner_faction, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), home_faction, away_faction, home_score, away_score, winner_faction, _now()),
        )
        self.conn.commit()

    def recent_wars(self, limit: int = 10) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT home_faction, away_faction, home_score, away_score, winner_faction, created_at
            FROM war_log ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
