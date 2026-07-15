"""War replay payloads — finished best-of-3 archives."""

from __future__ import annotations

from typing import Any


def fighter_snap(fighter: dict | None) -> dict | None:
    if not fighter:
        return None
    return {
        "id": fighter.get("id"),
        "name": fighter.get("name"),
        "icon": fighter.get("icon", "◈"),
        "type": fighter.get("type"),
        "skill": fighter.get("skill"),
        "maxHp": fighter.get("maxHp", 100),
    }


def draft_snap(war: dict) -> dict:
    d = war.get("draft") or {}
    return {
        "homeBans": list(d.get("home_bans") or d.get("homeBans") or []),
        "awayBans": list(d.get("away_bans") or d.get("awayBans") or []),
        "homePicks": list(war.get("home_picks") or []),
        "awayPicks": list(war.get("away_picks") or []),
    }


def empty_replay_state() -> dict:
    return {
        "duels": [],
        "current": None,
    }


def begin_duel_capture(war: dict, home_f: dict, away_f: dict, open_log: list) -> None:
    replay = war.setdefault("replay", empty_replay_state())
    replay["current"] = {
        "index": int(war.get("duel_index", 0)) + 1,
        "homeFighter": fighter_snap(home_f),
        "awayFighter": fighter_snap(away_f),
        "log": [dict(e) for e in (open_log or [])],
        "homeWon": None,
        "finalHomeHp": home_f.get("maxHp", 100),
        "finalAwayHp": away_f.get("maxHp", 100),
    }


def append_duel_log(war: dict, entries: list) -> None:
    replay = war.get("replay") or {}
    cur = replay.get("current")
    if not cur:
        return
    for e in entries or []:
        cur["log"].append({"msg": e.get("msg", ""), "cls": e.get("cls", "system")})


def finish_duel_capture(war: dict, home_won: bool, duel_state: Any) -> None:
    replay = war.setdefault("replay", empty_replay_state())
    cur = replay.get("current")
    if not cur:
        return
    cur["homeWon"] = bool(home_won)
    if duel_state is not None:
        cur["finalHomeHp"] = max(0, int(getattr(duel_state, "player_hp", 0)))
        cur["finalAwayHp"] = max(0, int(getattr(duel_state, "enemy_hp", 0)))
    replay["duels"].append(cur)
    replay["current"] = None


def build_replay_payload(
    war: dict,
    *,
    home_faction: str,
    away_faction: str,
    winner_faction: str | None,
    season_id: int | None,
) -> dict:
    return {
        "id": war["id"],
        "seasonId": season_id,
        "homeFaction": home_faction,
        "awayFaction": away_faction,
        "homeScore": int(war.get("home_score", 0)),
        "awayScore": int(war.get("away_score", 0)),
        "winnerFaction": winner_faction,
        "territory": war.get("territory"),
        "draft": draft_snap(war),
        "duels": list((war.get("replay") or {}).get("duels") or []),
    }


def replay_summary(row: dict, factions: dict) -> dict:
    """List-card payload for guild hall."""
    home = factions.get(row.get("home_faction") or "", {})
    away = factions.get(row.get("away_faction") or "", {})
    winner = row.get("winner_faction")
    return {
        "id": row["id"],
        "createdAt": row.get("created_at"),
        "homeFaction": row.get("home_faction"),
        "awayFaction": row.get("away_faction"),
        "homeHouse": home.get("house", row.get("home_faction")),
        "awayHouse": away.get("house", row.get("away_faction")),
        "homeCrest": home.get("crest", "◈"),
        "awayCrest": away.get("crest", "◈"),
        "homeScore": row.get("home_score"),
        "awayScore": row.get("away_score"),
        "winnerFaction": winner,
        "territoryId": row.get("territory_id"),
        "seasonId": row.get("season_id"),
    }
