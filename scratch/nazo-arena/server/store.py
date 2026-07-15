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

RELIC_SCHEMA = """
CREATE TABLE IF NOT EXISTS player_relics (
    player_id TEXT NOT NULL,
    relic_id TEXT NOT NULL,
    unlocked_at TEXT NOT NULL,
    PRIMARY KEY (player_id, relic_id)
);
"""

TERRITORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS territories (
    id TEXT PRIMARY KEY,
    owner_faction TEXT,
    held_since TEXT,
    season_id INTEGER
);
"""

QUEST_SCHEMA = """
CREATE TABLE IF NOT EXISTS player_daily_quests (
    player_id TEXT NOT NULL,
    day_key TEXT NOT NULL,
    quest_id TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    claimed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, day_key, quest_id)
);

CREATE INDEX IF NOT EXISTS idx_daily_quests_player_day
    ON player_daily_quests(player_id, day_key);
"""

REPLAY_SCHEMA = """
CREATE TABLE IF NOT EXISTS war_replays (
    id TEXT PRIMARY KEY,
    season_id INTEGER,
    home_faction TEXT NOT NULL,
    away_faction TEXT NOT NULL,
    home_score INTEGER NOT NULL,
    away_score INTEGER NOT NULL,
    winner_faction TEXT,
    territory_id TEXT,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_war_replays_created ON war_replays(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_war_replays_season ON war_replays(season_id);
"""

RAID_SCHEMA = """
CREATE TABLE IF NOT EXISTS player_raids (
    player_id TEXT NOT NULL,
    day_key TEXT NOT NULL,
    boss_id TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    clears INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, day_key, boss_id)
);

CREATE TABLE IF NOT EXISTS player_raid_clears (
    player_id TEXT NOT NULL,
    season_id INTEGER NOT NULL,
    boss_id TEXT NOT NULL,
    clears INTEGER NOT NULL DEFAULT 0,
    last_clear_at TEXT,
    PRIMARY KEY (player_id, season_id, boss_id)
);
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
        self.conn.executescript(RELIC_SCHEMA)
        self.conn.executescript(TERRITORY_SCHEMA)
        self.conn.executescript(QUEST_SCHEMA)
        self.conn.executescript(REPLAY_SCHEMA)
        self.conn.executescript(RAID_SCHEMA)
        self._migrate_war_log_season()
        self._migrate_equipped_relic()
        self._migrate_quest_points()
        self.conn.commit()

    def _migrate_war_log_season(self) -> None:
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(war_log)").fetchall()}
        if "season_id" not in cols:
            self.conn.execute("ALTER TABLE war_log ADD COLUMN season_id INTEGER")

    def _migrate_equipped_relic(self) -> None:
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(players)").fetchall()}
        if "equipped_relic" not in cols:
            self.conn.execute("ALTER TABLE players ADD COLUMN equipped_relic TEXT")

    def _migrate_quest_points(self) -> None:
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(players)").fetchall()}
        if "quest_points" not in cols:
            self.conn.execute(
                "ALTER TABLE players ADD COLUMN quest_points INTEGER NOT NULL DEFAULT 0"
            )

    def close(self) -> None:
        self.conn.close()

    def ensure_season_schema(self) -> None:
        self.conn.executescript(SEASON_SCHEMA)
        self.conn.commit()

    # --- relics ---

    def unlock_relic(self, pid: str, relic_id: str) -> bool:
        """Unlock a relic. Returns True if newly unlocked."""
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO player_relics (player_id, relic_id, unlocked_at)
            VALUES (?, ?, ?)
            """,
            (pid, relic_id, _now()),
        )
        self.conn.commit()
        if cur.rowcount:
            # Auto-equip if nothing equipped
            row = self.get_player_by_id(pid)
            if row and not row.get("equipped_relic"):
                self.set_equipped_relic(pid, relic_id)
            return True
        return False

    def player_relic_ids(self, pid: str) -> set[str]:
        rows = self.conn.execute(
            "SELECT relic_id FROM player_relics WHERE player_id = ?", (pid,)
        ).fetchall()
        return {r["relic_id"] for r in rows}

    def set_equipped_relic(self, pid: str, relic_id: str | None) -> bool:
        if relic_id is not None:
            owned = self.player_relic_ids(pid)
            if relic_id not in owned:
                return False
        self.conn.execute(
            "UPDATE players SET equipped_relic = ?, last_seen = ? WHERE id = ?",
            (relic_id, _now(), pid),
        )
        self.conn.commit()
        return True

    def get_equipped_relic(self, pid: str) -> str | None:
        row = self.get_player_by_id(pid)
        return row.get("equipped_relic") if row else None

    # --- territories ---

    def ensure_territories(self, season_id: int, defs: dict) -> None:
        """Seed map; home regions default to their house if unset."""
        for tid, meta in defs.items():
            row = self.conn.execute("SELECT id FROM territories WHERE id = ?", (tid,)).fetchone()
            if row:
                continue
            owner = meta.get("home")
            self.conn.execute(
                """
                INSERT INTO territories (id, owner_faction, held_since, season_id)
                VALUES (?, ?, ?, ?)
                """,
                (tid, owner, _now() if owner else None, season_id),
            )
        self.conn.commit()

    def reset_territories_for_season(self, season_id: int, defs: dict) -> None:
        """On season rollover: restore home defaults, clear neutrals."""
        for tid, meta in defs.items():
            owner = meta.get("home")
            self.conn.execute(
                """
                INSERT INTO territories (id, owner_faction, held_since, season_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    owner_faction = excluded.owner_faction,
                    held_since = excluded.held_since,
                    season_id = excluded.season_id
                """,
                (tid, owner, _now() if owner else None, season_id),
            )
        self.conn.commit()

    def get_territory_owner(self, tid: str) -> str | None:
        row = self.conn.execute(
            "SELECT owner_faction FROM territories WHERE id = ?", (tid,)
        ).fetchone()
        return row["owner_faction"] if row else None

    def set_territory_owner(self, tid: str, faction_id: str | None, season_id: int) -> None:
        self.conn.execute(
            """
            INSERT INTO territories (id, owner_faction, held_since, season_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                owner_faction = excluded.owner_faction,
                held_since = excluded.held_since,
                season_id = excluded.season_id
            """,
            (tid, faction_id, _now() if faction_id else None, season_id),
        )
        self.conn.commit()

    def all_territories(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, owner_faction, held_since, season_id FROM territories"
        ).fetchall()
        return [dict(r) for r in rows]

    def territories_owned_by(self, faction_id: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT id FROM territories WHERE owner_faction = ?", (faction_id,)
        ).fetchall()
        return [r["id"] for r in rows]

    def territory_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            """
            SELECT owner_faction, COUNT(*) AS c FROM territories
            WHERE owner_faction IS NOT NULL
            GROUP BY owner_faction
            """
        ).fetchall()
        return {r["owner_faction"]: int(r["c"]) for r in rows}

    # --- daily quests ---

    def get_quest_points(self, pid: str) -> int:
        row = self.get_player_by_id(pid)
        return int(row.get("quest_points") or 0) if row else 0

    def add_quest_points(self, pid: str, amount: int) -> int:
        self.conn.execute(
            "UPDATE players SET quest_points = COALESCE(quest_points, 0) + ?, last_seen = ? WHERE id = ?",
            (int(amount), _now(), pid),
        )
        self.conn.commit()
        return self.get_quest_points(pid)

    def spend_quest_points(self, pid: str, amount: int) -> bool:
        amount = int(amount)
        if amount <= 0:
            return False
        cur = self.conn.execute(
            """
            UPDATE players SET quest_points = quest_points - ?, last_seen = ?
            WHERE id = ? AND COALESCE(quest_points, 0) >= ?
            """,
            (amount, _now(), pid, amount),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def ensure_daily_quests(self, pid: str, day_key: str, quest_ids: list[str]) -> list[dict]:
        for qid in quest_ids:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO player_daily_quests
                    (player_id, day_key, quest_id, progress, claimed)
                VALUES (?, ?, ?, 0, 0)
                """,
                (pid, day_key, qid),
            )
        self.conn.commit()
        return self.get_daily_quests(pid, day_key)

    def get_daily_quests(self, pid: str, day_key: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT quest_id, progress, claimed
            FROM player_daily_quests
            WHERE player_id = ? AND day_key = ?
            """,
            (pid, day_key),
        ).fetchall()
        return [dict(r) for r in rows]

    def bump_daily_metric(self, pid: str, day_key: str, quest_ids: list[str], amount: int = 1) -> None:
        """Increment progress for given quest ids (capped later by client/defs)."""
        for qid in quest_ids:
            self.conn.execute(
                """
                INSERT INTO player_daily_quests (player_id, day_key, quest_id, progress, claimed)
                VALUES (?, ?, ?, ?, 0)
                ON CONFLICT(player_id, day_key, quest_id) DO UPDATE SET
                    progress = progress + excluded.progress
                """,
                (pid, day_key, qid, int(amount)),
            )
        self.conn.commit()

    def claim_daily_quest(self, pid: str, day_key: str, quest_id: str) -> bool:
        """Mark claimed if complete enough. Caller validates target."""
        cur = self.conn.execute(
            """
            UPDATE player_daily_quests SET claimed = 1
            WHERE player_id = ? AND day_key = ? AND quest_id = ? AND claimed = 0
            """,
            (pid, day_key, quest_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def get_daily_quest_row(self, pid: str, day_key: str, quest_id: str) -> dict | None:
        row = self.conn.execute(
            """
            SELECT quest_id, progress, claimed FROM player_daily_quests
            WHERE player_id = ? AND day_key = ? AND quest_id = ?
            """,
            (pid, day_key, quest_id),
        ).fetchone()
        return dict(row) if row else None

    # --- war replays ---

    def save_war_replay(self, payload: dict) -> None:
        import json

        self.conn.execute(
            """
            INSERT OR REPLACE INTO war_replays (
                id, season_id, home_faction, away_faction,
                home_score, away_score, winner_faction, territory_id,
                payload, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["id"],
                payload.get("seasonId"),
                payload["homeFaction"],
                payload["awayFaction"],
                payload["homeScore"],
                payload["awayScore"],
                payload.get("winnerFaction"),
                (payload.get("territory") or {}).get("id") if payload.get("territory") else None,
                json.dumps(payload, separators=(",", ":")),
                _now(),
            ),
        )
        self.conn.commit()

    def list_war_replays(self, limit: int = 12, faction_id: str | None = None) -> list[dict]:
        if faction_id:
            rows = self.conn.execute(
                """
                SELECT id, season_id, home_faction, away_faction, home_score, away_score,
                       winner_faction, territory_id, created_at
                FROM war_replays
                WHERE home_faction = ? OR away_faction = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (faction_id, faction_id, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT id, season_id, home_faction, away_faction, home_score, away_score,
                       winner_faction, territory_id, created_at
                FROM war_replays
                ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_war_replay(self, replay_id: str) -> dict | None:
        import json

        row = self.conn.execute(
            "SELECT payload FROM war_replays WHERE id = ?", (replay_id,)
        ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["payload"])
        except json.JSONDecodeError:
            return None

    # --- raids ---

    def get_raid_day(self, pid: str, day_key: str, boss_id: str) -> dict:
        row = self.conn.execute(
            """
            SELECT attempts, clears FROM player_raids
            WHERE player_id = ? AND day_key = ? AND boss_id = ?
            """,
            (pid, day_key, boss_id),
        ).fetchone()
        if not row:
            return {"attempts": 0, "clears": 0}
        return {"attempts": int(row["attempts"]), "clears": int(row["clears"])}

    def record_raid_attempt(self, pid: str, day_key: str, boss_id: str) -> None:
        self.conn.execute(
            """
            INSERT INTO player_raids (player_id, day_key, boss_id, attempts, clears)
            VALUES (?, ?, ?, 1, 0)
            ON CONFLICT(player_id, day_key, boss_id) DO UPDATE SET
                attempts = attempts + 1
            """,
            (pid, day_key, boss_id),
        )
        self.conn.commit()

    def record_raid_clear(self, pid: str, day_key: str, boss_id: str, season_id: int) -> None:
        self.conn.execute(
            """
            INSERT INTO player_raids (player_id, day_key, boss_id, attempts, clears)
            VALUES (?, ?, ?, 0, 1)
            ON CONFLICT(player_id, day_key, boss_id) DO UPDATE SET
                clears = clears + 1
            """,
            (pid, day_key, boss_id),
        )
        self.conn.execute(
            """
            INSERT INTO player_raid_clears (player_id, season_id, boss_id, clears, last_clear_at)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(player_id, season_id, boss_id) DO UPDATE SET
                clears = clears + 1,
                last_clear_at = excluded.last_clear_at
            """,
            (pid, season_id, boss_id, _now()),
        )
        self.conn.commit()

    def season_raid_clears(self, pid: str, season_id: int, boss_id: str) -> int:
        row = self.conn.execute(
            """
            SELECT clears FROM player_raid_clears
            WHERE player_id = ? AND season_id = ? AND boss_id = ?
            """,
            (pid, season_id, boss_id),
        ).fetchone()
        return int(row["clears"]) if row else 0

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
        new_season = self.create_season(next_num, length_days)
        from territories import TERRITORIES
        self.reset_territories_for_season(new_season["id"], TERRITORIES)
        return new_season

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
        from relics import catalog_public, relic_public
        from quests import DAILY_QUESTS, dailies_payload, utc_day_key
        from raids import DAILY_RAID_ATTEMPTS, boss_for_season, boss_public

        p = self.get_player_by_id(pid)
        if not p:
            return None
        owned = self.player_relic_ids(pid)
        equipped = p.get("equipped_relic")
        day = utc_day_key()
        rows = self.ensure_daily_quests(pid, day, [q["id"] for q in DAILY_QUESTS])
        qp = int(p.get("quest_points") or 0)
        # Seasonal raid card
        sid = season_id
        if sid is None:
            active = self.get_active_season()
            sid = active["id"] if active else 1
        boss = boss_for_season(sid)
        day_row = self.get_raid_day(pid, day, boss["id"])
        attempts_left = max(0, DAILY_RAID_ATTEMPTS - int(day_row["attempts"]))
        clears = self.season_raid_clears(pid, sid, boss["id"])
        out = {
            "id": p["id"],
            "nickname": p["nickname"],
            "factionId": p["faction_id"],
            "warsWon": p["wars_won"],
            "warsLost": p["wars_lost"],
            "duelsWon": p["duels_won"],
            "duelsLost": p["duels_lost"],
            "mastery": self.player_mastery(pid),
            "equippedRelic": relic_public(equipped, equipped=True) if equipped else None,
            "relics": catalog_public(owned, equipped),
            "questPoints": qp,
            "dailies": dailies_payload(rows, qp),
            "raid": boss_public(boss, attempts_left=attempts_left, clears=clears),
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
