"""Season lifecycle for Nazo Arena — timed house + player leaderboards."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from store import ArenaStore

# Default season length (override with NAZO_ARENA_SEASON_DAYS)
DEFAULT_SEASON_DAYS = float(os.environ.get("NAZO_ARENA_SEASON_DAYS", "7"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def season_name(num: int) -> str:
    return f"Season {num}"


def ensure_season(store: "ArenaStore") -> dict[str, Any]:
    """Return the active season, rolling over if expired."""
    store.ensure_season_schema()
    active = store.get_active_season()
    if not active:
        return store.create_season(1, DEFAULT_SEASON_DAYS)

    ends = _parse(active["ends_at"])
    if _now() >= ends:
        return store.rollover_season(active, DEFAULT_SEASON_DAYS)
    return active


def season_public(row: dict) -> dict[str, Any]:
    ends = _parse(row["ends_at"])
    starts = _parse(row["started_at"])
    now = _now()
    secs_left = max(0, (ends - now).total_seconds())
    return {
        "id": row["id"],
        "name": row["name"],
        "startedAt": row["started_at"],
        "endsAt": row["ends_at"],
        "status": row["status"],
        "daysLeft": round(secs_left / 86400, 2),
        "hoursLeft": round(secs_left / 3600, 1),
        "lengthDays": round((ends - starts).total_seconds() / 86400, 1),
        "championFaction": row.get("champion_faction"),
        "championElo": row.get("champion_elo"),
    }
