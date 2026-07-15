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
from factions import FACTIONS, pick_ids_for_faction, random_opponent_faction
from system_guilds import (
    pick_ids_from_roster,
    public_guild_profile,
    spawn_system_guild,
    system_pick_fighter_ids,
)
from store import ArenaStore

PORT = 8765
MATCH_WAIT_SEC = 4.0
THINK_MIN = 1.2
THINK_MAX = 4.8


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
        now = asyncio.get_event_loop().time()

        # human vs human — different houses only
        available = [
            gid for gid in queue
            if gid in guilds
            and guilds[gid].get("is_faction")
            and online_member_ids(gid)
        ]
        by_faction: dict[str, list[str]] = {}
        for gid in available:
            fid = guilds[gid].get("faction_id")
            if fid:
                by_faction.setdefault(fid, []).append(gid)

        fids = list(by_faction.keys())
        matched = set()
        for i, f1 in enumerate(fids):
            for f2 in fids[i + 1:]:
                if by_faction[f1] and by_faction[f2]:
                    a = by_faction[f1].pop(0)
                    b = by_faction[f2].pop(0)
                    if a in queue:
                        queue.remove(a)
                    if b in queue:
                        queue.remove(b)
                    await start_war(a, b, system_side=None)

        # human vs disguised rival house
        for gid in list(queue):
            g = guilds.get(gid)
            if not g or not g.get("is_faction"):
                continue
            if not online_member_ids(gid):
                if gid in queue:
                    queue.remove(gid)
                g["queued"] = False
                continue
            waited = now - g.get("queued_at", now)
            if waited >= MATCH_WAIT_SEC:
                queue.remove(gid)
                home_f = g["faction_id"]
                opp_f = random_opponent_faction(home_f)
                sys_g = spawn_system_guild(g["elo"], opp_f)
                guilds[sys_g["id"]] = sys_g
                await start_war(gid, sys_g["id"], system_side=sys_g["id"])


async def start_war(home_gid: str, away_gid: str, system_side: str | None) -> None:
    home = guilds[home_gid]
    away = guilds[away_gid]
    home["queued"] = False
    away["queued"] = True  # system guilds show as "in match" briefly
    home["in_war"] = True
    away["in_war"] = True

    war_id = str(uuid.uuid4())
    war = {
        "id": war_id,
        "home_id": home_gid,
        "away_id": away_gid,
        "system_side": system_side or (away_gid if away.get("is_system") else (home_gid if home.get("is_system") else None)),
        "phase": "pick",
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
    }
    wars[war_id] = war

    payload = {
        "type": "war.matched",
        "warId": war_id,
        "opponent": None,
        "youAre": "home",
    }
    for pid in home["player_ids"]:
        msg = {**payload, "opponent": public_guild_profile(away), "youAre": "home"}
        await send_player(pid, msg)

    if not away.get("is_system"):
        for pid in away["player_ids"]:
            msg = {**payload, "opponent": public_guild_profile(home), "youAre": "away"}
            await send_player(pid, msg)
    else:
        # system picks after human delay
        asyncio.create_task(system_auto_pick(war_id))

    asyncio.create_task(pick_timeout(war_id))


async def system_auto_pick(war_id: str) -> None:
    await asyncio.sleep(random.uniform(2.5, 6.0))
    war = wars.get(war_id)
    if not war or war["phase"] != "pick":
        return
    away = guilds[war["away_id"]]
    home = guilds[war["home_id"]]
    sys_g = away if away.get("is_system") else home
    if not sys_g.get("is_system"):
        return
    picks = system_pick_fighter_ids(sys_g)
    side = "away" if war["away_id"] == sys_g["id"] else "home"
    war[f"{side}_picks"] = picks
    captain = sys_g.get("captain_name", "captain")
    await notify_pick_progress(war_id, f"{captain} locked in their roster")
    await maybe_start_duels(war_id)


async def pick_timeout(war_id: str) -> None:
    await asyncio.sleep(45)
    war = wars.get(war_id)
    if not war or war["phase"] != "pick":
        return
    for side in ("home", "away"):
        if war[f"{side}_picks"] is None:
            g = guilds[war[f"{side}_id"]]
            if g.get("is_system") or g.get("is_faction"):
                fid = g.get("faction_id")
                if fid:
                    war[f"{side}_picks"] = pick_ids_for_faction(fid, 3)
                else:
                    war[f"{side}_picks"] = system_pick_fighter_ids(g)
            else:
                from factions import FACTION_ORDER
                war[f"{side}_picks"] = pick_ids_for_faction(random.choice(FACTION_ORDER), 3)
            # Attribute auto-pick mastery to an online member when possible
            if not g.get("is_system") and not war.get(f"{side}_picker_pid"):
                members = online_member_ids(war[f"{side}_id"])
                if members:
                    war[f"{side}_picker_pid"] = members[0]
    await maybe_start_duels(war_id)


async def notify_pick_progress(war_id: str, line: str) -> None:
    war = wars[war_id]
    for gid in (war["home_id"], war["away_id"]):
        g = guilds[gid]
        if g.get("is_system"):
            continue
        for pid in g["player_ids"]:
            await send_player(pid, {
                "type": "war.pick.status",
                "warId": war_id,
                "line": line,
                "homeReady": war["home_picks"] is not None,
                "awayReady": war["away_picks"] is not None,
            })


async def maybe_start_duels(war_id: str) -> None:
    war = wars.get(war_id)
    if not war or war["phase"] != "pick":
        return
    if war["home_picks"] is None or war["away_picks"] is None:
        return
    war["phase"] = "duel"
    war["duel_index"] = 0
    await start_duel(war_id)


async def start_duel(war_id: str) -> None:
    war = wars[war_id]
    idx = war["duel_index"]
    if idx >= 3:
        await finish_war(war_id)
        return

    home_f = pick_ids_from_roster(war["home_picks"])[idx]
    away_f = pick_ids_from_roster(war["away_picks"])[idx]
    home_g = guilds[war["home_id"]]
    away_g = guilds[war["away_id"]]
    war["duel"] = DuelState(player=home_f, enemy=away_f)
    war["duel"].home_faction = home_g.get("faction_id")
    war["duel"].away_faction = away_g.get("faction_id")
    war["turn"] = "home"
    war["waiting_action"] = False

    msg = {
        "type": "war.duel.start",
        "warId": war_id,
        "duelIndex": idx + 1,
        "homeScore": war["home_score"],
        "awayScore": war["away_score"],
        "yourFighter": None,
        "theirFighter": None,
        "state": war["duel"].snapshot(),
        "log": [],
    }

    for gid, you_are in ((war["home_id"], "home"), (war["away_id"], "away")):
        g = guilds[gid]
        if g.get("is_system"):
            continue
        m = {**msg, "youAre": you_are, "yourTurn": you_are == "home"}
        if you_are == "home":
            m["yourFighter"] = home_f
            m["theirFighter"] = away_f
        else:
            m["yourFighter"] = away_f
            m["theirFighter"] = home_f
            # flip perspective for away player's UI
            d = war["duel"]
            m["state"] = {
                "playerHp": d.enemy_hp,
                "enemyHp": d.player_hp,
                "playerMax": d.enemy["maxHp"],
                "enemyMax": d.player["maxHp"],
                "guarding": {"player": d.guarding_enemy, "enemy": d.guarding_player},
            }
        for pid in g["player_ids"]:
            await send_player(pid, m)

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

        for side, won in (("home", home_duel_won), ("away", not home_duel_won)):
            gid = war[f"{side}_id"]
            g = guilds.get(gid, {})
            if g.get("is_system"):
                continue
            for pid in g.get("player_ids", []):
                store.record_player_duel(pid, won)

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
            state = {
                "playerHp": d.enemy_hp,
                "enemyHp": d.player_hp,
                "playerMax": d.enemy["maxHp"],
                "enemyMax": d.player["maxHp"],
                "guarding": {"player": d.guarding_enemy, "enemy": d.guarding_player},
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
            store.save_faction_stats(fid, g["elo"], g["wins"], g["losses"])

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
    store.log_war(home_fid, away_fid, war["home_score"], war["away_score"], winner_faction)

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
        if picker_pid and picks:
            for fighter_id in picks:
                store.add_mastery(picker_pid, fighter_id, xp=12 if won else 4, won=won)

    standings = standings_public()

    for gid, you_are in ((war["home_id"], "home"), (war["away_id"], "away")):
        g = guilds[gid]
        if g.get("is_system"):
            continue
        won = home_won if you_are == "home" else away_won
        opp = away if you_are == "home" else home
        for pid in g["player_ids"]:
            stats = store.player_public(pid)
            your_score = war["home_score"] if you_are == "home" else war["away_score"]
            their_score = war["away_score"] if you_are == "home" else war["home_score"]
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
                "standings": standings,
            })

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
            stats = store.player_public(pid)
            await ws.send(_json({
                "type": "auth.ok",
                "playerId": pid,
                "token": row["token"],
                "nickname": nickname,
                "guild": guild,
                "stats": stats,
                "factions": factions_public(),
                "standings": standings_public(),
                "restored": True,
            }))
            return

        row = store.create_player(nickname)
        pid = row["id"]
        players[pid] = {
            "ws": ws,
            "nickname": nickname,
            "guild_id": None,
            "faction_id": None,
            "token": row["token"],
        }
        ws_to_player[ws] = pid
        stats = store.player_public(pid)
        await ws.send(_json({
            "type": "auth.ok",
            "playerId": pid,
            "token": row["token"],
            "nickname": nickname,
            "guild": None,
            "stats": stats,
            "factions": factions_public(),
            "standings": standings_public(),
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
        stats = store.player_public(pid)
        await ws.send(_json({
            "type": "guild.updated",
            "guild": public_guild_profile(g),
            "stats": stats,
            "standings": standings_public(),
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
        leave_guild(pid, persist=True)
        await ws.send(_json({
            "type": "guild.updated",
            "guild": None,
            "stats": store.player_public(pid),
            "standings": standings_public(),
        }))
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
        g["queued"] = True
        g["queued_at"] = asyncio.get_event_loop().time()
        if gid not in queue:
            queue.append(gid)
        await broadcast_guild(gid, {"type": "war.queued", "message": "Searching for a rival guild..."})
        return

    if mtype == "war.unqueue":
        gid = players[pid].get("guild_id")
        if gid and gid in queue:
            queue.remove(gid)
            guilds[gid]["queued"] = False
        await ws.send(_json({"type": "war.unqueued"}))
        return

    if mtype == "war.pick":
        war_id = msg.get("warId")
        picks = msg.get("fighters", [])[:3]
        war = wars.get(war_id)
        if not war or war["phase"] != "pick" or len(picks) != 3:
            return
        gid = players[pid].get("guild_id")
        side = None
        if gid == war["home_id"]:
            side = "home"
        elif gid == war["away_id"]:
            side = "away"
        if not side:
            return
        war[f"{side}_picks"] = picks
        war[f"{side}_picker_pid"] = pid
        p = players[pid]
        await notify_pick_progress(war_id, f"{p['nickname']} locked in their roster")
        await maybe_start_duels(war_id)
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
