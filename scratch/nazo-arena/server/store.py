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

SEASON_SCHEMA = """
CREATE TABLE IF NOT EXISTS seasons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ends_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    champion_faction TEXT,
    champion_elo INTEGER
);

CREATE TABLE IF NOT EXISTS season_factions (
    season_id INTEGER NOT NULL,
    faction_id TEXT NOT NULL,
    elo INTEGER NOT NULL DEFAULT 1000,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (season_id, faction_id)
);

CREATE TABLE IF NOT EXISTS season_players (
    season_id INTEGER NOT NULL,
    player_id TEXT NOT NULL,
    wars_won INTEGER NOT NULL DEFAULT 0,
    wars_lost INTEGER NOT NULL DEFAULT 0,
    duels_won INTEGER NOT NULL DEFAULT 0,
    duels_lost INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (season_id, player_id)
);

CREATE INDEX IF NOT EXISTS idx_season_players_season ON season_players(season_id);
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
        self.conn.executescript(SEASON_SCHEMA)
        self._migrate_war_log_season()
        self.conn.commit()

    def _migrate_war_log_season(self) -> None:
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(war_log)").fetchall()}
        if "season_id" not in cols:
            self.conn.execute("ALTER TABLE war_log ADD COLUMN season_id INTEGER")

    def close(self) -> None:
        self.conn.close()

    def ensure_season_schema(self) -> None:
        self.conn.executescript(SEASON_SCHEMA)
        self.conn.commit()

    # --- seasons ---

    def get_active_season(self) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM seasons WHERE status = 'active' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def create_season(self, number: int, length_days: float) -> dict:
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        ends = now + timedelta(days=length_days)
        cur = self.conn.execute(
            """
            INSERT INTO seasons (name, started_at, ends_at, status)
            VALUES (?, ?, ?, 'active')
            """,
            (f"Season {number}", now.isoformat(), ends.isoformat()),
        )
        self.conn.commit()
        sid = cur.lastrowid
        # seed season faction rows from current factions table
        for row in self.conn.execute("SELECT id FROM factions").fetchall():
            self.conn.execute(
                "INSERT OR IGNORE INTO season_factions (season_id, faction_id, elo, wins, losses) VALUES (?, ?, 1000, 0, 0)",
                (sid, row["id"]),
            )
        self.conn.commit()
        return self.get_season(sid)  # type: ignore

    def get_season(self, sid: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM seasons WHERE id = ?", (sid,)).fetchone()
        return dict(row) if row else None

    def rollover_season(self, active: dict, length_days: float) -> dict:
        """Close active season, archive standings, reset live faction ELO, open next."""
        sid = active["id"]
        # Snapshot live faction stats into season_factions
        for row in self.conn.execute("SELECT id, elo, wins, losses FROM factions").fetchall():
            self.conn.execute(
                """
                INSERT INTO season_factions (season_id, faction_id, elo, wins, losses)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(season_id, faction_id) DO UPDATE SET
                    elo = excluded.elo, wins = excluded.wins, losses = excluded.losses
                """,
                (sid, row["id"], row["elo"], row["wins"], row["losses"]),
            )

        champ = self.conn.execute(
            "SELECT faction_id, elo FROM season_factions WHERE season_id = ? ORDER BY elo DESC LIMIT 1",
            (sid,),
        ).fetchone()
        champ_f = champ["faction_id"] if champ else None
        champ_e = int(champ["elo"]) if champ else None

        self.conn.execute(
            """
            UPDATE seasons SET status = 'closed', champion_faction = ?, champion_elo = ?
            WHERE id = ?
            """,
            (champ_f, champ_e, sid),
        )

        # Soft-reset live faction ratings for the new season
        self.conn.execute("UPDATE factions SET elo = 1000, wins = 0, losses = 0")
        self.conn.commit()

        next_num = sid + 1
        return self.create_season(next_num, length_days)

    def sync_season_faction(self, season_id: int, fid: str, elo: int, wins: int, losses: int) -> None:
        self.conn.execute(
            """
            INSERT INTO season_factions (season_id, faction_id, elo, wins, losses)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(season_id, faction_id) DO UPDATE SET
                elo = excluded.elo, wins = excluded.wins, losses = excluded.losses
            """,
            (season_id, fid, elo, wins, losses),
        )
        self.conn.commit()

    def record_season_player_war(self, season_id: int, pid: str, won: bool) -> None:
        col = "wars_won" if won else "wars_lost"
        self.conn.execute(
            f"""
            INSERT INTO season_players (season_id, player_id, wars_won, wars_lost, duels_won, duels_lost)
            VALUES (?, ?, ?, ?, 0, 0)
            ON CONFLICT(season_id, player_id) DO UPDATE SET {col} = {col} + 1
            """,
            (season_id, pid, 1 if won else 0, 0 if won else 1),
        )
        self.conn.commit()

    def record_season_player_duel(self, season_id: int, pid: str, won: bool) -> None:
        col = "duels_won" if won else "duels_lost"
        self.conn.execute(
            f"""
            INSERT INTO season_players (season_id, player_id, wars_won, wars_lost, duels_won, duels_lost)
            VALUES (?, ?, 0, 0, ?, ?)
            ON CONFLICT(season_id, player_id) DO UPDATE SET {col} = {col} + 1
            """,
            (season_id, pid, 1 if won else 0, 0 if won else 1),
        )
        self.conn.commit()

    def season_player_board(self, season_id: int, limit: int = 10) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT sp.player_id, sp.wars_won, sp.wars_lost, sp.duels_won, sp.duels_lost,
                   p.nickname, p.faction_id
            FROM season_players sp
            JOIN players p ON p.id = sp.player_id
            WHERE sp.season_id = ?
            ORDER BY sp.wars_won DESC, sp.duels_won DESC, sp.wars_lost ASC
            LIMIT ?
            """,
            (season_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def season_history(self, limit: int = 5) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT id, name, started_at, ends_at, champion_faction, champion_elo
            FROM seasons WHERE status = 'closed'
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def player_season_stats(self, season_id: int, pid: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM season_players WHERE season_id = ? AND player_id = ?",
            (season_id, pid),
        ).fetchone()
        return dict(row) if row else None

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

    def record_player_duel(self, pid: str, won: bool) -> None:
        col = "duels_won" if won else "duels_lost"
        self.conn.execute(
            f"UPDATE players SET {col} = {col} + 1, last_seen = ? WHERE id = ?",
            (_now(), pid),
        )
        self.conn.commit()

    def add_mastery(self, pid: str, fighter_id: str, xp: int, won: bool, *, record: bool = True) -> None:
        if record:
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
        else:
            self.conn.execute(
                """
                INSERT INTO fighter_mastery (player_id, fighter_id, xp, wins, losses)
                VALUES (?, ?, ?, 0, 0)
                ON CONFLICT(player_id, fighter_id) DO UPDATE SET
                    xp = xp + excluded.xp
                """,
                (pid, fighter_id, xp),
            )
        self.conn.commit()

    def get_mastery(self, pid: str, fighter_id: str) -> dict | None:
        row = self.conn.execute(
            """
            SELECT fighter_id, xp, wins, losses
            FROM fighter_mastery WHERE player_id = ? AND fighter_id = ?
            """,
            (pid, fighter_id),
        ).fetchone()
        return dict(row) if row else None

    def player_mastery(self, pid: str, limit: int = 8) -> list[dict]:
        from mastery import mastery_public

        rows = self.conn.execute(
            """
            SELECT fighter_id, xp, wins, losses
            FROM fighter_mastery WHERE player_id = ?
            ORDER BY xp DESC LIMIT ?
            """,
            (pid, limit),
        ).fetchall()
        out = []
        for r in rows:
            info = mastery_public(r["xp"], r["wins"], r["losses"])
            info["fighter_id"] = r["fighter_id"]
            out.append(info)
        return out

    def player_public(self, pid: str, season_id: int | None = None) -> dict | None:
        p = self.get_player_by_id(pid)
        if not p:
            return None
        out = {
            "id": p["id"],
            "nickname": p["nickname"],
            "factionId": p["faction_id"],
            "warsWon": p["wars_won"],
            "warsLost": p["wars_lost"],
            "duelsWon": p["duels_won"],
            "duelsLost": p["duels_lost"],
            "mastery": self.player_mastery(pid),
        }
        if season_id is not None:
            sp = self.player_season_stats(season_id, pid)
            out["season"] = {
                "warsWon": sp["wars_won"] if sp else 0,
                "warsLost": sp["wars_lost"] if sp else 0,
                "duelsWon": sp["duels_won"] if sp else 0,
                "duelsLost": sp["duels_lost"] if sp else 0,
            }
        return out

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

    def save_faction_stats(self, fid: str, elo: int, wins: int, losses: int, season_id: int | None = None) -> None:
        self.conn.execute(
            """
            INSERT INTO factions (id, elo, wins, losses) VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET elo = excluded.elo, wins = excluded.wins, losses = excluded.losses
            """,
            (fid, elo, wins, losses),
        )
        if season_id is not None:
            self.sync_season_faction(season_id, fid, elo, wins, losses)
        else:
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
        season_id: int | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO war_log (id, home_faction, away_faction, home_score, away_score, winner_faction, created_at, season_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), home_faction, away_faction, home_score, away_score, winner_faction, _now(), season_id),
        )
        self.conn.commit()

    def recent_wars(self, limit: int = 10) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT home_faction, away_faction, home_score, away_score, winner_faction, created_at, season_id
            FROM war_log ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
