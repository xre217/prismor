#!/usr/bin/env python3
"""Nazo Arena multiplayer — guild wars with hidden System opponents."""

from __future__ import annotations

import asyncio
import json
import random
import string
import uuid
from dataclasses import dataclass, field
from typing import Any

import websockets
from websockets.server import WebSocketServerProtocol

from battle_engine import DuelState, ai_choose_action, apply_player_action, duel_winner, fighter_from_id
from draft import (
    STEP_TIMEOUT_SEC,
    apply_draft_action,
    auto_choose,
    current_step,
    draft_complete,
    draft_public,
    finalize_picks,
    init_draft,
)
from factions import FACTIONS, random_opponent_faction
from system_guilds import (
    pick_ids_from_roster,
    public_guild_profile,
    spawn_system_guild,
)
from store import ArenaStore
from mastery import apply_mastery, mastery_public, system_mastery_xp
from season import ensure_season, season_public
from relics import (
    apply_relic_duel_open,
    apply_relic_to_fighter,
    relic_public,
    roll_relic_drop,
    system_relic_for_elo,
)
from territories import (
    TERRITORIES,
    apply_territory_bonuses,
    apply_territory_duel_open,
    bonuses_for_faction,
    map_public,
    territory_public,
)
from quests import (
    DAILY_QUESTS,
    METRIC_QUESTS,
    QUEST_BY_ID,
    SHOP_BY_ID,
    roll_common_relic,
    roll_fortune_relic,
    utc_day_key,
)
from replays import (
    append_duel_log,
    begin_duel_capture,
    build_replay_payload,
    empty_replay_state,
    finish_duel_capture,
    replay_summary,
)

PORT = 8765
MATCH_WAIT_SEC = 4.0
THINK_MIN = 1.2
THINK_MAX = 4.8
_last_season_id: int | None = None


def current_season() -> dict:
    """Ensure active season; reset in-memory house ELO if a rollover just happened."""
    global _last_season_id
    row = ensure_season(store)
    sid = row["id"]
    store.ensure_territories(sid, TERRITORIES)
    if _last_season_id is not None and sid != _last_season_id:
        for g in guilds.values():
            if g.get("is_faction"):
                g["elo"] = 1000
                g["wins"] = 0
                g["losses"] = 0
    _last_season_id = sid
    return row


def territories_payload() -> list[dict]:
    season = current_season()
    owners = {r["id"]: r.get("owner_faction") for r in store.all_territories()}
    return map_public(owners)


def bump_quest_metric(pid: str, metric: str, amount: int = 1) -> None:
    """Advance today's daily quests that use this metric."""
    qids = METRIC_QUESTS.get(metric) or []
    if not qids:
        return
    day = utc_day_key()
    store.ensure_daily_quests(pid, day, [q["id"] for q in DAILY_QUESTS])
    store.bump_daily_metric(pid, day, qids, amount)


def apply_quest_reward(pid: str, reward: dict) -> dict:
    """Grant quest claim rewards. Returns extras for the client."""
    extras: dict = {"qpGained": 0, "relic": None, "mastery": None}
    qp = int(reward.get("qp", 0))
    if qp:
        store.add_quest_points(pid, qp)
        extras["qpGained"] = qp

    chance = float(reward.get("relic_roll", 0) or 0)
    if chance and random.random() < chance:
        drop = roll_common_relic(store.player_relic_ids(pid))
        if drop and store.unlock_relic(pid, drop):
            extras["relic"] = relic_public(drop)

    mxp = int(reward.get("mastery_xp", 0) or 0)
    if mxp:
        fighter_id = _pick_mastery_target(pid)
        if fighter_id:
            store.add_mastery(pid, fighter_id, xp=mxp, won=True, record=False)
            extras["mastery"] = {"fighterId": fighter_id, "xp": mxp}
    return extras


def _pick_mastery_target(pid: str) -> str | None:
    rows = store.player_mastery(pid, limit=8)
    if rows:
        return rows[0]["fighter_id"]
    p = store.get_player_by_id(pid)
    fid = (p or {}).get("faction_id")
    if fid and fid in FACTIONS:
        fighters = FACTIONS[fid].get("fighters") or []
        if fighters:
            return fighters[0]["id"]
    return None


def leaderboard_payload() -> dict:
    season = current_season()
    sid = season["id"]
    history = []
    for h in store.season_history(5):
        fac = FACTIONS.get(h.get("champion_faction") or "", {})
        history.append({
            "id": h["id"],
            "name": h["name"],
            "championFaction": h.get("champion_faction"),
            "championHouse": fac.get("house"),
            "championCrest": fac.get("crest", ""),
            "championElo": h.get("champion_elo"),
            "endedAt": h["ends_at"],
        })
    players = []
    for i, row in enumerate(store.season_player_board(sid, 10)):
        fac = FACTIONS.get(row.get("faction_id") or "", {})
        players.append({
            "rank": i + 1,
            "nickname": row["nickname"],
            "factionId": row.get("faction_id"),
            "house": fac.get("house"),
            "crest": fac.get("crest", ""),
            "warsWon": row["wars_won"],
            "warsLost": row["wars_lost"],
            "duelsWon": row["duels_won"],
            "duelsLost": row["duels_lost"],
        })
    return {
        "season": season_public(season),
        "standings": standings_public(),
        "playerBoard": players,
        "history": history,
        "territories": territories_payload(),
        "replays": replays_payload(),
        "liveWars": live_wars_payload(),
    }


def replays_payload(limit: int = 10, faction_id: str | None = None) -> list[dict]:
    return [replay_summary(r, FACTIONS) for r in store.list_war_replays(limit, faction_id)]


def live_wars_payload() -> list[dict]:
    out = []
    for war in wars.values():
        if war.get("phase") == "done":
            continue
        home = guilds.get(war["home_id"], {})
        away = guilds.get(war["away_id"], {})
        home_f = home.get("faction_id")
        away_f = away.get("faction_id")
        hf = FACTIONS.get(home_f or "", {})
        af = FACTIONS.get(away_f or "", {})
        out.append({
            "warId": war["id"],
            "phase": war.get("phase"),
            "homeFaction": home_f,
            "awayFaction": away_f,
            "homeHouse": hf.get("house", home_f),
            "awayHouse": af.get("house", away_f),
            "homeCrest": hf.get("crest", "◈"),
            "awayCrest": af.get("crest", "◈"),
            "homeScore": war.get("home_score", 0),
            "awayScore": war.get("away_score", 0),
            "duelIndex": int(war.get("duel_index", 0)) + (1 if war.get("phase") == "duel" else 0),
            "territory": war.get("territory"),
        })
    return out


def _invite_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def _json(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"))


# --- in-memory state ---

store: ArenaStore
players: dict[str, dict] = {}  # account_id -> {ws, nickname, guild_id, token}
guilds: dict[str, dict] = {}  # guild_id -> guild
ws_to_player: dict[Any, str] = {}
queue: list[str] = []  # guild_ids waiting for war
wars: dict[str, dict] = {}
system_guild_pool: list[str] = []  # unused; kept for compat


def init_faction_guilds() -> None:
    """Four house guilds — load ELO/wins/losses from SQLite."""
    store.ensure_factions(list(FACTIONS.keys()))
    current_season()  # create Season 1 if needed
    for fid, fac in FACTIONS.items():
        row = store.get_faction(fid) or {"elo": 1000, "wins": 0, "losses": 0}
        gid = f"faction-{fid}"
        guilds[gid] = {
            "id": gid,
            "name": fac["name"],
            "tag": fac["tag"],
            "crest": fac["crest"],
            "faction_id": fid,
            "elo": row["elo"],
            "wins": row["wins"],
            "losses": row["losses"],
            "members": [],
            "motd": fac.get("motd", ""),
            "is_system": False,
            "is_faction": True,
            "invite_code": None,
            "player_ids": [],
            "queued": False,
            "in_war": False,
        }


def _faction_member_count(fid: str) -> int:
    row = store.conn.execute(
        "SELECT COUNT(*) AS c FROM players WHERE faction_id = ?", (fid,)
    ).fetchone()
    return int(row["c"]) if row else 0


def standings_public() -> list[dict]:
    rows = store.faction_standings()
    counts = store.territory_counts()
    out = []
    for i, row in enumerate(rows):
        fac = FACTIONS.get(row["id"], {})
        out.append({
            "rank": i + 1,
            "factionId": row["id"],
            "house": fac.get("house", row["id"]),
            "crest": fac.get("crest", ""),
            "elo": row["elo"],
            "wins": row["wins"],
            "losses": row["losses"],
            "members": _faction_member_count(row["id"]),
            "territories": counts.get(row["id"], 0),
        })
    return out


def factions_public() -> list[dict]:
    from house_passives import PASSIVES
    out = []
    for fid, fac in FACTIONS.items():
        g = guilds.get(f"faction-{fid}", {})
        pas = PASSIVES.get(fid, {})
        out.append({
            "id": fid,
            "house": fac["house"],
            "lab": fac["lab"],
            "name": fac["name"],
            "tag": fac["tag"],
            "crest": fac["crest"],
            "motd": fac.get("motd", ""),
            "members": _faction_member_count(fid),
            "elo": g.get("elo", row["elo"] if (row := store.get_faction(fid)) else 1000),
            "fighters": [f["name"] for f in fac["fighters"]],
            "passiveName": pas.get("name", ""),
            "passiveDesc": pas.get("desc", ""),
        })
    return out


async def send_player(player_id: str, msg: dict) -> None:
    p = players.get(player_id)
    if p and p.get("ws"):
        try:
            await p["ws"].send(_json(msg))
        except Exception:
            pass


async def notify_spectators(war_id: str, msg: dict) -> None:
    war = wars.get(war_id)
    if not war:
        return
    for pid in list(war.get("spectators") or []):
        # Drop if they joined a fighting side
        p = players.get(pid)
        if not p:
            war["spectators"].discard(pid)
            continue
        gid = p.get("guild_id")
        if gid in (war["home_id"], war["away_id"]):
            war["spectators"].discard(pid)
            continue
        await send_player(pid, {**msg, "spectator": True})


async def broadcast_guild(guild_id: str, msg: dict) -> None:
    g = guilds.get(guild_id)
    if not g:
        return
    for pid in g.get("player_ids", []):
        await send_player(pid, msg)


def player_public(pid: str) -> dict | None:
    p = players.get(pid)
    if not p:
        return None
    return {"id": pid, "nickname": p["nickname"]}


# --- guild ops ---

def join_faction(player_id: str, faction_id: str) -> dict | None:
    if faction_id not in FACTIONS:
        return None
    leave_guild(player_id, persist=False)
    gid = f"faction-{faction_id}"
    g = guilds[gid]
    p = players[player_id]
    if player_id not in g["player_ids"]:
        g["player_ids"].append(player_id)
        g["members"].append({
            "name": p["nickname"], "role": "fighter", "lastSeen": "online", "playerId": player_id,
        })
    p["guild_id"] = gid
    p["faction_id"] = faction_id
    store.set_player_faction(player_id, faction_id)
    return g


def leave_guild(player_id: str, *, persist: bool = True) -> None:
    gid = players[player_id].get("guild_id")
    if not gid or gid not in guilds:
        return
    g = guilds[gid]
    if gid in queue:
        queue.remove(gid)
        g["queued"] = False
        g["contest_territory"] = None
    if g.get("is_faction"):
        g["player_ids"] = [x for x in g["player_ids"] if x != player_id]
        g["members"] = [m for m in g["members"] if m.get("playerId") != player_id]
        if persist:
            store.set_player_faction(player_id, None)
    players[player_id]["guild_id"] = None
    players[player_id]["faction_id"] = None


def find_war_for_guild(gid: str) -> str | None:
    for war_id, war in wars.items():
        if war["phase"] == "done":
            continue
        if gid in (war["home_id"], war["away_id"]):
            return war_id
    return None


def online_member_ids(gid: str) -> list[str]:
    g = guilds.get(gid, {})
    out = []
    for pid in g.get("player_ids", []):
        p = players.get(pid)
        if p and p.get("ws"):
            out.append(pid)
    return out


async def forfeit_war(war_id: str, forfeiting_gid: str) -> None:
    """End a war because the human side abandoned it."""
    war = wars.get(war_id)
    if not war or war["phase"] == "done":
        return
    if forfeiting_gid == war["home_id"]:
        war["away_score"] = max(war["away_score"], 2)
        war["home_score"] = min(war["home_score"], 1)
    else:
        war["home_score"] = max(war["home_score"], 2)
        war["away_score"] = min(war["away_score"], 1)
    await finish_war(war_id)


async def handle_player_disconnect(pid: str) -> None:
    """Clear queue membership; forfeit war if no humans left on that side."""
    p = players.get(pid)
    if not p:
        return
    gid = p.get("guild_id")
    players[pid]["ws"] = None
    if not gid or gid not in guilds:
        return

    g = guilds[gid]
    if gid in queue:
        queue.remove(gid)
        g["queued"] = False

    war_id = find_war_for_guild(gid)
    remaining = [x for x in online_member_ids(gid) if x != pid]

    if war_id and not remaining:
        # Keep pid in player_ids so finish_war records their loss
        await forfeit_war(war_id, gid)

    if g.get("is_faction"):
        g["player_ids"] = [x for x in g["player_ids"] if x != pid]
        g["members"] = [m for m in g["members"] if m.get("playerId") != pid]

    players[pid]["guild_id"] = None

    if not online_member_ids(gid) and not find_war_for_guild(gid):
        g["in_war"] = False
        g["queued"] = False


def create_guild(player_id: str, name: str, tag: str) -> dict:
    gid = str(uuid.uuid4())
    p = players[player_id]
    guild = {
        "id": gid,
        "name": name[:32],
        "tag": (tag or name[:4])[:6].upper(),
        "crest": random.choice(["🜂", "◈", "⬡", "✦", "◆"]),
        "elo": 1000,
        "wins": 0,
        "losses": 0,
        "members": [{"name": p["nickname"], "role": "captain", "lastSeen": "online", "playerId": player_id}],
        "motd": "",
        "is_system": False,
        "invite_code": _invite_code(),
        "player_ids": [player_id],
        "queued": False,
        "in_war": False,
    }
    guilds[gid] = guild
    p["guild_id"] = gid
    return guild


def join_guild(player_id: str, code: str) -> dict | None:
    for g in guilds.values():
        if g.get("invite_code") == code.upper() and not g.get("is_system"):
            if player_id not in g["player_ids"]:
                g["player_ids"].append(player_id)
                p = players[player_id]
                g["members"].append({
                    "name": p["nickname"], "role": "recruit", "lastSeen": "online", "playerId": player_id,
                })
            players[player_id]["guild_id"] = g["id"]
            return g
    return None


# --- war matchmaking ---

async def matchmaking_tick() -> None:
    while True:
        await asyncio.sleep(1.0)
        current_season()  # rollover check
        now = asyncio.get_event_loop().time()

        available = [
            gid for gid in queue
            if gid in guilds
            and guilds[gid].get("is_faction")
            and online_member_ids(gid)
        ]
        matched: set[str] = set()

        # Contesters → match against the territory's owning house when queued
        for gid in list(available):
            if gid in matched:
                continue
            g = guilds[gid]
            tid = g.get("contest_territory")
            if not tid:
                continue
            owner = store.get_territory_owner(tid)
            home_f = g.get("faction_id")
            if not owner or owner == home_f:
                continue
            owner_gid = f"faction-{owner}"
            if owner_gid not in available or owner_gid in matched:
                continue
            if gid in queue:
                queue.remove(gid)
            if owner_gid in queue:
                queue.remove(owner_gid)
            matched.add(gid)
            matched.add(owner_gid)
            await start_war(gid, owner_gid, system_side=None, territory_id=tid)

        # Open queue (no territory) — human vs human, different houses
        by_faction: dict[str, list[str]] = {}
        for gid in available:
            if gid in matched:
                continue
            if guilds[gid].get("contest_territory"):
                continue
            fid = guilds[gid].get("faction_id")
            if fid:
                by_faction.setdefault(fid, []).append(gid)

        fids = list(by_faction.keys())
        for i, f1 in enumerate(fids):
            for f2 in fids[i + 1:]:
                if by_faction[f1] and by_faction[f2]:
                    a = by_faction[f1].pop(0)
                    b = by_faction[f2].pop(0)
                    if a in matched or b in matched:
                        continue
                    if a in queue:
                        queue.remove(a)
                    if b in queue:
                        queue.remove(b)
                    matched.add(a)
                    matched.add(b)
                    await start_war(a, b, system_side=None, territory_id=None)

        # Timed-out queue → disguised System rival (still contests territory if set)
        for gid in list(queue):
            if gid in matched:
                continue
            g = guilds.get(gid)
            if not g or not g.get("is_faction"):
                continue
            if not online_member_ids(gid):
                if gid in queue:
                    queue.remove(gid)
                g["queued"] = False
                g["contest_territory"] = None
                continue
            waited = now - g.get("queued_at", now)
            if waited >= MATCH_WAIT_SEC:
                queue.remove(gid)
                home_f = g["faction_id"]
                tid = g.get("contest_territory")
                owner = store.get_territory_owner(tid) if tid else None
                if tid and owner and owner != home_f:
                    opp_f = owner
                else:
                    opp_f = random_opponent_faction(home_f)
                sys_g = spawn_system_guild(g["elo"], opp_f)
                guilds[sys_g["id"]] = sys_g
                await start_war(gid, sys_g["id"], system_side=sys_g["id"], territory_id=tid)


async def start_war(
    home_gid: str,
    away_gid: str,
    system_side: str | None,
    territory_id: str | None = None,
) -> None:
    home = guilds[home_gid]
    away = guilds[away_gid]
    home["queued"] = False
    away["queued"] = False
    home["in_war"] = True
    away["in_war"] = True
    contested = territory_id or home.get("contest_territory") or away.get("contest_territory")
    home["contest_territory"] = None
    away["contest_territory"] = None

    home_fid = home.get("faction_id")
    away_fid = away.get("faction_id")
    if not home_fid or not away_fid:
        return

    war_id = str(uuid.uuid4())
    territory_info = None
    if contested and contested in TERRITORIES:
        owner = store.get_territory_owner(contested)
        territory_info = territory_public(contested, owner)

    war = {
        "id": war_id,
        "home_id": home_gid,
        "away_id": away_gid,
        "system_side": system_side or (away_gid if away.get("is_system") else (home_gid if home.get("is_system") else None)),
        "phase": "draft",
        "draft": init_draft(home_fid, away_fid),
        "home_picks": None,
        "away_picks": None,
        "home_picker_pid": None,
        "away_picker_pid": None,
        "home_score": 0,
        "away_score": 0,
        "duel_index": 0,
        "duel": None,
        "turn": "home",
        "waiting_action": False,
        "draft_deadline": asyncio.get_event_loop().time() + STEP_TIMEOUT_SEC,
        "territory_id": contested if contested in TERRITORIES else None,
        "territory": territory_info,
        "replay": empty_replay_state(),
        "spectators": set(),
    }
    wars[war_id] = war

    payload = {
        "type": "war.matched",
        "warId": war_id,
        "opponent": None,
        "youAre": "home",
        "territory": territory_info,
    }
    for pid in home["player_ids"]:
        msg = {
            **payload,
            "opponent": public_guild_profile(away),
            "youAre": "home",
            "draft": draft_public(war, "home"),
        }
        await send_player(pid, msg)

    if not away.get("is_system"):
        for pid in away["player_ids"]:
            msg = {
                **payload,
                "opponent": public_guild_profile(home),
                "youAre": "away",
                "draft": draft_public(war, "away"),
            }
            await send_player(pid, msg)

    asyncio.create_task(draft_tick(war_id))


async def broadcast_draft(war_id: str, line: str = "") -> None:
    war = wars.get(war_id)
    if not war or war["phase"] != "draft":
        return
    for gid, you_are in ((war["home_id"], "home"), (war["away_id"], "away")):
        g = guilds[gid]
        if g.get("is_system"):
            continue
        for pid in g["player_ids"]:
            await send_player(pid, {
                "type": "war.draft.update",
                "warId": war_id,
                "line": line,
                "draft": draft_public(war, you_are),
            })


async def advance_after_draft_action(war_id: str, line: str = "") -> None:
    war = wars.get(war_id)
    if not war or war["phase"] != "draft":
        return
    war["draft_deadline"] = asyncio.get_event_loop().time() + STEP_TIMEOUT_SEC
    await broadcast_draft(war_id, line)
    if draft_complete(war) or current_step(war) is None:
        if war.get("_starting_duels"):
            return
        war["_starting_duels"] = True
        finalize_picks(war)
        await broadcast_draft(war_id, "Draft locked — duels begin")
        war["phase"] = "duel"
        war["duel_index"] = 0
        await asyncio.sleep(0.8)
        await start_duel(war_id)


async def handle_draft_action(war_id: str, side: str, fighter_id: str, pid: str | None = None) -> str | None:
    war = wars.get(war_id)
    if not war or war["phase"] != "draft":
        return "Not in draft"
    err = apply_draft_action(war, side, fighter_id)
    if err:
        return err

    from draft import DRAFT_STEPS
    from factions import ALL_FIGHTERS

    prev = war["draft"]["step"] - 1
    action, _ = DRAFT_STEPS[prev]
    name = ALL_FIGHTERS.get(fighter_id, {}).get("name", fighter_id)
    if pid and pid in players:
        actor = players[pid]["nickname"]
        war[f"{side}_picker_pid"] = pid
    else:
        actor = guilds[war[f"{side}_id"]].get("captain_name", "Rival")
        members = online_member_ids(war[f"{side}_id"])
        if members and not war.get(f"{side}_picker_pid") and action == "pick":
            war[f"{side}_picker_pid"] = members[0]

    verb = "banned" if action == "ban" else "picked"
    await advance_after_draft_action(war_id, f"{actor} {verb} {name}")
    return None


async def draft_tick(war_id: str) -> None:
    """Drive system turns and per-step timeouts until draft completes."""
    while True:
        await asyncio.sleep(0.25)
        war = wars.get(war_id)
        if not war or war["phase"] != "draft":
            return

        step = current_step(war)
        if not step:
            if not war.get("_starting_duels"):
                war["_starting_duels"] = True
                finalize_picks(war)
                war["phase"] = "duel"
                war["duel_index"] = 0
                await start_duel(war_id)
            return

        _action, side = step
        gid = war[f"{side}_id"]
        g = guilds[gid]
        now = asyncio.get_event_loop().time()
        is_system = g.get("is_system", False)
        timed_out = now >= war.get("draft_deadline", now + 999)

        if is_system:
            await asyncio.sleep(random.uniform(1.4, 3.2))
            war = wars.get(war_id)
            if not war or war["phase"] != "draft":
                return
            step = current_step(war)
            if not step or step[1] != side:
                continue
            fid = auto_choose(war, side)
            if fid:
                await handle_draft_action(war_id, side, fid, pid=None)
            continue

        if timed_out:
            fid = auto_choose(war, side)
            if fid:
                members = online_member_ids(gid)
                pid = members[0] if members else None
                await handle_draft_action(war_id, side, fid, pid=pid)
            continue


async def maybe_start_duels(war_id: str) -> None:
    war = wars.get(war_id)
    if not war or war.get("_starting_duels"):
        return
    if war["phase"] == "draft" and (draft_complete(war) or current_step(war) is None):
        war["_starting_duels"] = True
        finalize_picks(war)
        war["phase"] = "duel"
        war["duel_index"] = 0
        await start_duel(war_id)


def relic_for_side(war: dict, side: str) -> str | None:
    """Equipped relic for the side's picker, or System fake relic."""
    key = f"{side}_relic"
    if key in war:
        return war[key]
    gid = war[f"{side}_id"]
    g = guilds.get(gid, {})
    if g.get("is_system"):
        rid = system_relic_for_elo(g.get("elo", 1000))
        war[key] = rid
        return rid
    picker = war.get(f"{side}_picker_pid")
    if picker:
        rid = store.get_equipped_relic(picker)
        war[key] = rid
        return rid
    members = online_member_ids(gid)
    if members:
        rid = store.get_equipped_relic(members[0])
        war[key] = rid
        return rid
    war[key] = None
    return None


def mastery_xp_for_side(war: dict, side: str, fighter_id: str) -> int:
    """XP for the picker (or best online member) for this fighter; System gets ELO-scaled fake XP."""
    gid = war[f"{side}_id"]
    g = guilds.get(gid, {})
    if g.get("is_system"):
        return system_mastery_xp(g.get("elo", 1000))

    picker = war.get(f"{side}_picker_pid")
    if picker:
        row = store.get_mastery(picker, fighter_id)
        if row:
            return int(row["xp"])

    best = 0
    for pid in g.get("player_ids", []):
        row = store.get_mastery(pid, fighter_id)
        if row:
            best = max(best, int(row["xp"]))
    return best


async def start_duel(war_id: str) -> None:
    war = wars[war_id]
    idx = war["duel_index"]
    if idx >= 3:
        await finish_war(war_id)
        return

    home_id = war["home_picks"][idx]
    away_id = war["away_picks"][idx]
    home_f = pick_ids_from_roster([home_id])[0]
    away_f = pick_ids_from_roster([away_id])[0]

    home_xp = mastery_xp_for_side(war, "home", home_id)
    away_xp = mastery_xp_for_side(war, "away", away_id)
    home_m = apply_mastery(home_f, home_xp)
    away_m = apply_mastery(away_f, away_xp)

    home_relic = relic_for_side(war, "home")
    away_relic = relic_for_side(war, "away")
    home_r = apply_relic_to_fighter(home_f, home_relic, first_pick=(idx == 0))
    away_r = apply_relic_to_fighter(away_f, away_relic, first_pick=(idx == 0))

    home_g = guilds[war["home_id"]]
    away_g = guilds[war["away_id"]]
    home_owned = store.territories_owned_by(home_g.get("faction_id") or "")
    away_owned = store.territories_owned_by(away_g.get("faction_id") or "")
    home_tb = bonuses_for_faction(home_owned)
    away_tb = bonuses_for_faction(away_owned)
    apply_territory_bonuses(home_f, home_tb)
    apply_territory_bonuses(away_f, away_tb)

    duel = DuelState(player=home_f, enemy=away_f)
    duel.player_hp = home_f["maxHp"]
    duel.enemy_hp = away_f["maxHp"]
    duel.home_faction = home_g.get("faction_id")
    duel.away_faction = away_g.get("faction_id")
    duel.home_relic = home_relic
    duel.away_relic = away_relic
    duel.home_territory = home_tb
    duel.away_territory = away_tb

    open_log: list = []
    apply_relic_duel_open(duel, True, home_relic, open_log)
    apply_relic_duel_open(duel, False, away_relic, open_log)
    apply_territory_duel_open(duel, True, home_tb, open_log, duel_index=idx)
    apply_territory_duel_open(duel, False, away_tb, open_log, duel_index=idx)

    begin_duel_capture(war, home_f, away_f, open_log)

    war["duel"] = duel
    war["phase"] = "duel"
    war["turn"] = "home"
    war["waiting_action"] = False
    war["home_duel_fighter"] = home_id
    war["away_duel_fighter"] = away_id

    msg = {
        "type": "war.duel.start",
        "warId": war_id,
        "duelIndex": idx + 1,
        "homeScore": war["home_score"],
        "awayScore": war["away_score"],
        "yourFighter": None,
        "theirFighter": None,
        "yourMastery": None,
        "theirMastery": None,
        "yourRelic": None,
        "theirRelic": None,
        "territory": war.get("territory"),
        "state": duel.snapshot(),
        "log": open_log,
    }

    for gid, you_are in ((war["home_id"], "home"), (war["away_id"], "away")):
        g = guilds[gid]
        if g.get("is_system"):
            continue
        m = {**msg, "youAre": you_are, "yourTurn": you_are == "home"}
        if you_are == "home":
            m["yourFighter"] = home_f
            m["theirFighter"] = away_f
            m["yourMastery"] = home_m
            m["theirMastery"] = away_m
            m["yourRelic"] = home_r
            m["theirRelic"] = away_r
            m["log"] = open_log
        else:
            m["yourFighter"] = away_f
            m["theirFighter"] = home_f
            m["yourMastery"] = away_m
            m["theirMastery"] = home_m
            m["yourRelic"] = away_r
            m["theirRelic"] = home_r
            flipped = []
            for e in open_log:
                cls = e.get("cls", "system")
                if cls == "player":
                    cls = "enemy"
                elif cls == "enemy":
                    cls = "player"
                flipped.append({**e, "cls": cls})
            m["log"] = flipped
            snap = duel.snapshot()
            m["state"] = {
                "playerHp": duel.enemy_hp,
                "enemyHp": duel.player_hp,
                "playerMax": duel.enemy["maxHp"],
                "enemyMax": duel.player["maxHp"],
                "guarding": {"player": duel.guarding_enemy, "enemy": duel.guarding_player},
                "statuses": {
                    "player": snap["statuses"]["enemy"],
                    "enemy": snap["statuses"]["player"],
                },
            }
        for pid in g["player_ids"]:
            await send_player(pid, m)

    # Spectators always see home POV
    spec_msg = {
        **msg,
        "youAre": "home",
        "yourTurn": False,
        "spectator": True,
        "yourFighter": home_f,
        "theirFighter": away_f,
        "yourMastery": home_m,
        "theirMastery": away_m,
        "yourRelic": home_r,
        "theirRelic": away_r,
        "log": open_log,
    }
    await notify_spectators(war_id, spec_msg)

    if war["system_side"]:
        asyncio.create_task(system_turn_loop(war_id))


async def system_turn_loop(war_id: str) -> None:
    """When it's the system's turn, act with human-like delay."""
    await asyncio.sleep(0.3)
    while True:
        war = wars.get(war_id)
        if not war or war["phase"] != "duel" or not war["duel"]:
            return
        sys_gid = war["system_side"]
        turn = war["turn"]
        sys_is_home = sys_gid == war["home_id"]
        sys_turn = (turn == "home" and sys_is_home) or (turn == "away" and not sys_is_home)
        if not sys_turn:
            await asyncio.sleep(0.2)
            continue
        if war["waiting_action"]:
            await asyncio.sleep(0.2)
            continue

        await asyncio.sleep(random.uniform(THINK_MIN, THINK_MAX))
        war = wars.get(war_id)
        if not war or war["phase"] != "duel":
            return
        action = ai_choose_action(war["duel"], is_enemy=not sys_is_home)
        await handle_war_action(war_id, sys_gid, action, from_system=True)
        await asyncio.sleep(0.2)


async def handle_war_action(war_id: str, guild_id: str, action: str, from_system: bool = False) -> None:
    war = wars.get(war_id)
    if not war or war["phase"] != "duel" or not war["duel"]:
        return

    is_home = guild_id == war["home_id"]
    expected = war["turn"]
    if (expected == "home" and not is_home) or (expected == "away" and is_home):
        return

    war["waiting_action"] = True
    d = war["duel"]
    is_player_turn = is_home
    entries = apply_player_action(d, action, is_player_turn=is_player_turn)
    append_duel_log(war, entries)

    war["turn"] = "away" if expected == "home" else "home"
    war["waiting_action"] = False

    await broadcast_duel_update(war_id, entries)

    winner = duel_winner(d)
    if winner:
        if winner == "player":
            war["home_score"] += 1
            home_duel_won = True
        else:
            war["away_score"] += 1
            home_duel_won = False

        finish_duel_capture(war, home_duel_won, d)

        for side, won in (("home", home_duel_won), ("away", not home_duel_won)):
            gid = war[f"{side}_id"]
            g = guilds.get(gid, {})
            if g.get("is_system"):
                continue
            season = current_season()
            for pid in g.get("player_ids", []):
                store.record_player_duel(pid, won)
                store.record_season_player_duel(season["id"], pid, won)
                if won:
                    bump_quest_metric(pid, "duels_won")
            # Award mastery XP to the fighter that just fought
            fighter_id = war.get(f"{side}_duel_fighter")
            picker = war.get(f"{side}_picker_pid")
            if fighter_id and picker:
                store.add_mastery(picker, fighter_id, xp=8 if won else 3, won=won)
            elif fighter_id:
                members = online_member_ids(gid)
                if members:
                    store.add_mastery(members[0], fighter_id, xp=8 if won else 3, won=won)

        await broadcast_duel_end(war_id, home_duel_won)
        await asyncio.sleep(1.2)
        war["duel_index"] += 1
        war["duel"] = None
        if war["duel_index"] >= 3:
            await finish_war(war_id)
        else:
            await start_duel(war_id)
        return


async def broadcast_duel_end(war_id: str, home_won: bool) -> None:
    war = wars[war_id]
    for gid, you_are in ((war["home_id"], "home"), (war["away_id"], "away")):
        g = guilds[gid]
        if g.get("is_system"):
            continue
        won = home_won if you_are == "home" else not home_won
        for pid in g["player_ids"]:
            await send_player(pid, {
                "type": "war.duel.end",
                "warId": war_id,
                "won": won,
                "homeScore": war["home_score"],
                "awayScore": war["away_score"],
                "yourScore": war["home_score"] if you_are == "home" else war["away_score"],
                "theirScore": war["away_score"] if you_are == "home" else war["home_score"],
                "duelIndex": war["duel_index"] + 1,
            })
    await notify_spectators(war_id, {
        "type": "war.duel.end",
        "warId": war_id,
        "won": home_won,
        "homeScore": war["home_score"],
        "awayScore": war["away_score"],
        "yourScore": war["home_score"],
        "theirScore": war["away_score"],
        "duelIndex": war["duel_index"] + 1,
        "spectator": True,
    })


async def broadcast_duel_update(war_id: str, new_log: list) -> None:
    from house_passives import PASSIVES, ravenclaw_intel

    war = wars[war_id]
    d = war["duel"]

    for gid, you_are in ((war["home_id"], "home"), (war["away_id"], "away")):
        g = guilds[gid]
        if g.get("is_system"):
            continue
        if you_are == "home":
            state = d.snapshot()
            your_turn = war["turn"] == "home"
            your_faction = d.home_faction
            log_entries = new_log
        else:
            snap = d.snapshot()
            state = {
                "playerHp": d.enemy_hp,
                "enemyHp": d.player_hp,
                "playerMax": d.enemy["maxHp"],
                "enemyMax": d.player["maxHp"],
                "guarding": {"player": d.guarding_enemy, "enemy": d.guarding_player},
                "statuses": {
                    "player": snap["statuses"]["enemy"],
                    "enemy": snap["statuses"]["player"],
                },
            }
            your_turn = war["turn"] == "away"
            your_faction = d.away_faction
            log_entries = []
            for e in new_log:
                cls = e.get("cls", "system")
                if cls == "player":
                    cls = "enemy"
                elif cls == "enemy":
                    cls = "player"
                log_entries.append({**e, "cls": cls})

        intel = ravenclaw_intel(d, you_are == "home")
        passive = PASSIVES.get(your_faction or "", {})

        for pid in g["player_ids"]:
            await send_player(pid, {
                "type": "war.duel.update",
                "warId": war_id,
                "log": log_entries,
                "state": state,
                "yourTurn": your_turn,
                "opponentThinking": not your_turn,
                "opponentLastAction": intel,
                "housePassive": passive.get("name"),
            })

    # Spectators — home POV
    from house_passives import PASSIVES, ravenclaw_intel
    await notify_spectators(war_id, {
        "type": "war.duel.update",
        "warId": war_id,
        "log": new_log,
        "state": d.snapshot(),
        "yourTurn": False,
        "opponentThinking": True,
        "opponentLastAction": ravenclaw_intel(d, True),
        "housePassive": PASSIVES.get(d.home_faction or "", {}).get("name"),
        "spectator": True,
    })


async def finish_war(war_id: str) -> None:
    war = wars.get(war_id)
    if not war:
        return
    war["phase"] = "done"
    home = guilds[war["home_id"]]
    away = guilds[war["away_id"]]
    home_won = war["home_score"] > war["away_score"]
    away_won = war["away_score"] > war["home_score"]
    if war["home_score"] == war["away_score"]:
        home_won = random.choice([True, False])
        away_won = not home_won

    season = current_season()
    sid = season["id"]

    for g, won, fid in (
        (home, home_won, home.get("faction_id")),
        (away, away_won, away.get("faction_id")),
    ):
        g["in_war"] = False
        g["queued"] = False
        if g.get("is_system"):
            continue
        if won:
            g["wins"] += 1
            g["elo"] += random.randint(12, 28)
        else:
            g["losses"] += 1
            g["elo"] = max(800, g["elo"] - random.randint(8, 22))
        if fid:
            store.save_faction_stats(fid, g["elo"], g["wins"], g["losses"], season_id=sid)

    winner_faction = None
    if home.get("faction_id") and not home.get("is_system"):
        if home_won:
            winner_faction = home["faction_id"]
    if away.get("faction_id") and not away.get("is_system") and away_won:
        winner_faction = away["faction_id"]

    home_fid = home.get("faction_id") or "unknown"
    away_fid = away.get("faction_id") or "unknown"
    if away.get("is_system"):
        away_fid = away.get("faction_id") or away_fid
    store.log_war(home_fid, away_fid, war["home_score"], war["away_score"], winner_faction, season_id=sid)

    # Persist replay archive (completed duels)
    if war.get("replay", {}).get("current"):
        # Abandoned mid-duel — drop incomplete capture
        war["replay"]["current"] = None
    replay_payload = build_replay_payload(
        war,
        home_faction=home_fid,
        away_faction=away_fid,
        winner_faction=winner_faction,
        season_id=sid,
    )
    store.save_war_replay(replay_payload)
    war["replay_id"] = replay_payload["id"]

    seized = None
    tid = war.get("territory_id")
    if tid and winner_faction:
        store.set_territory_owner(tid, winner_faction, sid)
        seized = territory_public(tid, winner_faction)
        war["territory"] = seized

    for side, won, picker_pid, picks in (
        ("home", home_won, war.get("home_picker_pid"), war.get("home_picks")),
        ("away", away_won, war.get("away_picker_pid"), war.get("away_picks")),
    ):
        gid = war[f"{side}_id"]
        g = guilds.get(gid, {})
        if g.get("is_system"):
            continue
        for pid in g.get("player_ids", []):
            store.record_player_war(pid, won)
            store.record_season_player_war(sid, pid, won)
            bump_quest_metric(pid, "wars_played")
            if won:
                bump_quest_metric(pid, "wars_won")
                drop = roll_relic_drop(store.player_relic_ids(pid))
                if drop and store.unlock_relic(pid, drop):
                    war.setdefault("relic_drops", {})[pid] = drop
        if picker_pid and picks:
            for fighter_id in picks:
                store.add_mastery(picker_pid, fighter_id, xp=4 if won else 1, won=won, record=False)

    board = leaderboard_payload()
    drops = war.get("relic_drops", {})

    for gid, you_are in ((war["home_id"], "home"), (war["away_id"], "away")):
        g = guilds[gid]
        if g.get("is_system"):
            continue
        won = home_won if you_are == "home" else away_won
        opp = away if you_are == "home" else home
        for pid in g["player_ids"]:
            stats = store.player_public(pid, season_id=sid)
            your_score = war["home_score"] if you_are == "home" else war["away_score"]
            their_score = war["away_score"] if you_are == "home" else war["home_score"]
            drop_info = relic_public(drops[pid]) if pid in drops else None
            await send_player(pid, {
                "type": "war.end",
                "warId": war_id,
                "won": won,
                "youAre": you_are,
                "homeScore": war["home_score"],
                "awayScore": war["away_score"],
                "yourScore": your_score,
                "theirScore": their_score,
                "guild": public_guild_profile(g),
                "opponent": public_guild_profile(opp),
                "stats": stats,
                "standings": board["standings"],
                "season": board["season"],
                "playerBoard": board["playerBoard"],
                "history": board["history"],
                "territories": board["territories"],
                "replays": board["replays"],
                "liveWars": board["liveWars"],
                "territory": seized or war.get("territory"),
                "replayId": war.get("replay_id"),
                "relicDrop": drop_info,
            })

    # Tell spectators the war ended, then clear
    await notify_spectators(war_id, {
        "type": "war.end",
        "warId": war_id,
        "won": home_won,
        "spectator": True,
        "homeScore": war["home_score"],
        "awayScore": war["away_score"],
        "yourScore": war["home_score"],
        "theirScore": war["away_score"],
        "replayId": war.get("replay_id"),
        "replays": board["replays"],
        "liveWars": board["liveWars"],
        "standings": board["standings"],
        "season": board["season"],
        "playerBoard": board["playerBoard"],
        "history": board["history"],
        "territories": board["territories"],
    })
    war.get("spectators", set()).clear()

    home_id, away_id = war["home_id"], war["away_id"]
    del wars[war_id]

    for gid in (home_id, away_id):
        g = guilds.get(gid)
        if g and g.get("is_system") and not g.get("is_faction"):
            del guilds[gid]


# --- websocket handler ---

async def handle_message(ws: WebSocketServerProtocol, raw: str) -> None:
    msg = json.loads(raw)
    mtype = msg.get("type")
    pid = ws_to_player.get(ws)

    if mtype == "auth":
        nickname = (msg.get("nickname") or "fighter")[:20].strip() or "fighter"
        token = msg.get("token")
        row = store.get_player_by_token(token) if token else None

        if row:
            pid = row["id"]
            store.touch_player(pid, nickname)
            players[pid] = {
                "ws": ws,
                "nickname": nickname,
                "guild_id": None,
                "faction_id": row["faction_id"],
                "token": row["token"],
            }
            ws_to_player[ws] = pid
            guild = None
            if row["faction_id"]:
                g = join_faction(pid, row["faction_id"])
                if g:
                    guild = public_guild_profile(g)
            board = leaderboard_payload()
            stats = store.player_public(pid, season_id=board["season"]["id"])
            await ws.send(_json({
                "type": "auth.ok",
                "playerId": pid,
                "token": row["token"],
                "nickname": nickname,
                "guild": guild,
                "stats": stats,
                "factions": factions_public(),
                "standings": board["standings"],
                "season": board["season"],
                "playerBoard": board["playerBoard"],
                "history": board["history"],
                "territories": board["territories"],
                "replays": board["replays"],
                "liveWars": board["liveWars"],
                "restored": True,
            }))
            return

        row = store.create_player(nickname)
        pid = row["id"]
        # Starter relic
        store.unlock_relic(pid, "iron_ward")
        players[pid] = {
            "ws": ws,
            "nickname": nickname,
            "guild_id": None,
            "faction_id": None,
            "token": row["token"],
        }
        ws_to_player[ws] = pid
        board = leaderboard_payload()
        stats = store.player_public(pid, season_id=board["season"]["id"])
        await ws.send(_json({
            "type": "auth.ok",
            "playerId": pid,
            "token": row["token"],
            "nickname": nickname,
            "guild": None,
            "stats": stats,
            "factions": factions_public(),
            "standings": board["standings"],
            "season": board["season"],
            "playerBoard": board["playerBoard"],
            "history": board["history"],
            "territories": board["territories"],
            "replays": board["replays"],
            "liveWars": board["liveWars"],
            "restored": False,
        }))
        return

    if not pid:
        await ws.send(_json({"type": "error", "message": "Not authenticated"}))
        return

    if mtype == "guild.join_faction":
        faction_id = msg.get("factionId", "")
        g = join_faction(pid, faction_id)
        if not g:
            await ws.send(_json({"type": "error", "message": "Unknown house"}))
            return
        board = leaderboard_payload()
        stats = store.player_public(pid, season_id=board["season"]["id"])
        await ws.send(_json({
            "type": "guild.updated",
            "guild": public_guild_profile(g),
            "stats": stats,
            "standings": board["standings"],
            "season": board["season"],
            "playerBoard": board["playerBoard"],
            "history": board["history"],
            "territories": board["territories"],
            "replays": board["replays"],
            "liveWars": board["liveWars"],
        }))
        return

    if mtype == "guild.create":
        name = msg.get("name", "New Guild")
        tag = msg.get("tag", "")
        if players[pid].get("guild_id"):
            await ws.send(_json({"type": "error", "message": "Already in a guild"}))
            return
        g = create_guild(pid, name, tag)
        await ws.send(_json({
            "type": "guild.updated",
            "guild": public_guild_profile(g),
            "inviteCode": g["invite_code"],
        }))
        return

    if mtype == "guild.join":
        code = (msg.get("inviteCode") or "").strip().upper()
        g = join_guild(pid, code)
        if not g:
            await ws.send(_json({"type": "error", "message": "Invalid invite code"}))
            return
        await broadcast_guild(g["id"], {"type": "guild.updated", "guild": public_guild_profile(g), "inviteCode": g["invite_code"]})
        return

    if mtype == "guild.leave":
        gid = players[pid].get("guild_id")
        if gid and gid in queue:
            queue.remove(gid)
            guilds[gid]["queued"] = False
            guilds[gid]["contest_territory"] = None
        leave_guild(pid, persist=True)
        board = leaderboard_payload()
        await ws.send(_json({
            "type": "guild.updated",
            "guild": None,
            "stats": store.player_public(pid, season_id=board["season"]["id"]),
            "standings": board["standings"],
            "season": board["season"],
            "playerBoard": board["playerBoard"],
            "history": board["history"],
            "territories": board["territories"],
            "replays": board["replays"],
            "liveWars": board["liveWars"],
        }))
        return

    if mtype == "relic.equip":
        relic_id = msg.get("relicId")
        if relic_id == "" or relic_id is False:
            relic_id = None
        if not store.set_equipped_relic(pid, relic_id):
            await ws.send(_json({"type": "error", "message": "Cannot equip that relic"}))
            return
        board = leaderboard_payload()
        await ws.send(_json({
            "type": "relic.updated",
            "stats": store.player_public(pid, season_id=board["season"]["id"]),
        }))
        return

    if mtype == "quest.claim":
        quest_id = msg.get("questId")
        qdef = QUEST_BY_ID.get(quest_id or "")
        if not qdef:
            await ws.send(_json({"type": "error", "message": "Unknown quest"}))
            return
        day = utc_day_key()
        store.ensure_daily_quests(pid, day, [q["id"] for q in DAILY_QUESTS])
        row = store.get_daily_quest_row(pid, day, quest_id)
        if not row:
            await ws.send(_json({"type": "error", "message": "Quest not found"}))
            return
        if row.get("claimed"):
            await ws.send(_json({"type": "error", "message": "Already claimed"}))
            return
        if int(row.get("progress") or 0) < int(qdef["target"]):
            await ws.send(_json({"type": "error", "message": "Quest not complete"}))
            return
        if not store.claim_daily_quest(pid, day, quest_id):
            await ws.send(_json({"type": "error", "message": "Could not claim"}))
            return
        extras = apply_quest_reward(pid, qdef.get("reward") or {})
        board = leaderboard_payload()
        await ws.send(_json({
            "type": "quest.updated",
            "stats": store.player_public(pid, season_id=board["season"]["id"]),
            "claimed": quest_id,
            "reward": extras,
        }))
        return

    if mtype == "quest.shop":
        item_id = msg.get("itemId")
        item = SHOP_BY_ID.get(item_id or "")
        if not item:
            await ws.send(_json({"type": "error", "message": "Unknown shop item"}))
            return
        if not store.spend_quest_points(pid, item["cost"]):
            await ws.send(_json({"type": "error", "message": "Not enough quest points"}))
            return
        result: dict = {"itemId": item_id, "relic": None, "mastery": None}
        kind = item["kind"]
        if kind == "mastery_xp":
            fighter_id = _pick_mastery_target(pid)
            amount = int(item.get("amount", 10))
            if fighter_id:
                store.add_mastery(pid, fighter_id, xp=amount, won=True, record=False)
                result["mastery"] = {"fighterId": fighter_id, "xp": amount}
            else:
                # refund if nothing to boost
                store.add_quest_points(pid, item["cost"])
                await ws.send(_json({"type": "error", "message": "No fighter to train yet"}))
                return
        elif kind == "relic_common":
            drop = roll_common_relic(store.player_relic_ids(pid))
            if not drop:
                store.add_quest_points(pid, item["cost"])
                await ws.send(_json({"type": "error", "message": "You already own all common relics"}))
                return
            store.unlock_relic(pid, drop)
            result["relic"] = relic_public(drop)
        elif kind == "relic_fortune":
            drop = roll_fortune_relic(store.player_relic_ids(pid))
            if not drop:
                store.add_quest_points(pid, item["cost"])
                await ws.send(_json({"type": "error", "message": "Relic collection complete"}))
                return
            store.unlock_relic(pid, drop)
            result["relic"] = relic_public(drop)
        board = leaderboard_payload()
        await ws.send(_json({
            "type": "quest.updated",
            "stats": store.player_public(pid, season_id=board["season"]["id"]),
            "shopPurchase": result,
        }))
        return

    if mtype == "replay.get":
        rid = msg.get("replayId")
        payload = store.get_war_replay(rid) if rid else None
        if not payload:
            await ws.send(_json({"type": "error", "message": "Replay not found"}))
            return
        await ws.send(_json({"type": "replay.data", "replay": payload}))
        return

    if mtype == "war.spectate":
        war_id = msg.get("warId")
        war = wars.get(war_id)
        if not war or war.get("phase") == "done":
            await ws.send(_json({"type": "error", "message": "War not available"}))
            return
        gid = players[pid].get("guild_id")
        if gid in (war["home_id"], war["away_id"]):
            await ws.send(_json({"type": "error", "message": "You are already in this war"}))
            return
        # leave other spectator seats
        for w in wars.values():
            specs = w.get("spectators")
            if specs and pid in specs:
                specs.discard(pid)
        war.setdefault("spectators", set()).add(pid)
        home = guilds[war["home_id"]]
        away = guilds[war["away_id"]]
        snap = {
            "type": "war.spectate.ok",
            "warId": war_id,
            "phase": war["phase"],
            "homeScore": war["home_score"],
            "awayScore": war["away_score"],
            "duelIndex": war["duel_index"] + (1 if war.get("duel") else 0),
            "opponent": public_guild_profile(away),
            "home": public_guild_profile(home),
            "territory": war.get("territory"),
            "spectator": True,
        }
        if war.get("phase") == "duel" and war.get("duel"):
            d = war["duel"]
            snap.update({
                "type": "war.duel.start",
                "youAre": "home",
                "yourTurn": False,
                "yourFighter": d.player,
                "theirFighter": d.enemy,
                "state": d.snapshot(),
                "log": list(d.log[-12:]),
                "spectator": True,
            })
        await ws.send(_json(snap))
        return

    if mtype == "war.unspectate":
        for w in wars.values():
            specs = w.get("spectators")
            if specs and pid in specs:
                specs.discard(pid)
        await ws.send(_json({"type": "war.unspectate.ok"}))
        return

    if mtype == "war.queue":
        gid = players[pid].get("guild_id")
        if not gid or gid not in guilds:
            await ws.send(_json({"type": "error", "message": "Join a guild first"}))
            return
        g = guilds[gid]
        if g.get("is_system"):
            return
        # Clear stale in_war if no active war exists
        if g.get("in_war") and not find_war_for_guild(gid):
            g["in_war"] = False
        if g.get("in_war"):
            await ws.send(_json({"type": "error", "message": "Already in a war"}))
            return
        if not online_member_ids(gid) and pid not in g.get("player_ids", []):
            await ws.send(_json({"type": "error", "message": "Rejoin your house first"}))
            return

        territory_id = msg.get("territoryId") or None
        if territory_id:
            if territory_id not in TERRITORIES:
                await ws.send(_json({"type": "error", "message": "Unknown territory"}))
                return
            owner = store.get_territory_owner(territory_id)
            if owner and owner == g.get("faction_id"):
                await ws.send(_json({"type": "error", "message": "Your house already holds that region"}))
                return

        g["queued"] = True
        g["queued_at"] = asyncio.get_event_loop().time()
        g["contest_territory"] = territory_id
        if gid not in queue:
            queue.append(gid)
        if territory_id:
            t = TERRITORIES[territory_id]
            line = f"Contesting {t['icon']} {t['name']}..."
        else:
            line = "Searching for a rival guild..."
        await broadcast_guild(gid, {
            "type": "war.queued",
            "message": line,
            "territoryId": territory_id,
        })
        return

    if mtype == "war.unqueue":
        gid = players[pid].get("guild_id")
        if gid and gid in queue:
            queue.remove(gid)
            guilds[gid]["queued"] = False
            guilds[gid]["contest_territory"] = None
        await ws.send(_json({"type": "war.unqueued"}))
        return

    if mtype == "war.draft":
        war_id = msg.get("warId")
        fighter_id = msg.get("fighterId")
        war = wars.get(war_id)
        if not war or war["phase"] != "draft" or not fighter_id:
            return
        gid = players[pid].get("guild_id")
        side = None
        if gid == war["home_id"]:
            side = "home"
        elif gid == war["away_id"]:
            side = "away"
        if not side:
            return
        err = await handle_draft_action(war_id, side, fighter_id, pid=pid)
        if err:
            await ws.send(_json({"type": "error", "message": err}))
        return

    if mtype == "war.action":
        war_id = msg.get("warId")
        action = msg.get("action")
        if action not in ("strike", "guard", "skill", "chaos"):
            return
        war = wars.get(war_id)
        if not war:
            return
        gid = players[pid].get("guild_id")
        if gid not in (war["home_id"], war["away_id"]):
            return
        await handle_war_action(war_id, gid, action)


async def ws_handler(ws: WebSocketServerProtocol) -> None:
    try:
        async for raw in ws:
            await handle_message(ws, raw)
    finally:
        pid = ws_to_player.pop(ws, None)
        if pid and pid in players:
            await handle_player_disconnect(pid)


async def main() -> None:
    global store
    store = ArenaStore()
    init_faction_guilds()
    asyncio.create_task(matchmaking_tick())
    async with websockets.serve(ws_handler, "0.0.0.0", PORT):
        print(f"Nazo Arena server on ws://0.0.0.0:{PORT}")
        print(f"Persistence: {store.path}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
