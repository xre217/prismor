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

PORT = 8765
MATCH_WAIT_SEC = 4.0
THINK_MIN = 1.2
THINK_MAX = 4.8


def _invite_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def _json(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"))


# --- in-memory state ---

players: dict[str, dict] = {}  # player_id -> {ws, nickname, guild_id}
guilds: dict[str, dict] = {}  # guild_id -> guild
ws_to_player: dict[Any, str] = {}
queue: list[str] = []  # guild_ids waiting for war
wars: dict[str, dict] = {}
system_guild_pool: list[str] = []  # unused; kept for compat


def init_faction_guilds() -> None:
    """Four house guilds — players join one."""
    for fid, fac in FACTIONS.items():
        gid = f"faction-{fid}"
        guilds[gid] = {
            "id": gid,
            "name": fac["name"],
            "tag": fac["tag"],
            "crest": fac["crest"],
            "faction_id": fid,
            "elo": 1000,
            "wins": 0,
            "losses": 0,
            "members": [],
            "motd": fac.get("motd", ""),
            "is_system": False,
            "is_faction": True,
            "invite_code": None,
            "player_ids": [],
            "queued": False,
            "in_war": False,
        }


def factions_public() -> list[dict]:
    out = []
    for fid, fac in FACTIONS.items():
        g = guilds.get(f"faction-{fid}", {})
        out.append({
            "id": fid,
            "house": fac["house"],
            "lab": fac["lab"],
            "name": fac["name"],
            "tag": fac["tag"],
            "crest": fac["crest"],
            "motd": fac.get("motd", ""),
            "members": len(g.get("player_ids", [])),
            "elo": g.get("elo", 1000),
            "fighters": [f["name"] for f in fac["fighters"]],
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
    leave_guild(player_id)
    gid = f"faction-{faction_id}"
    g = guilds[gid]
    p = players[player_id]
    if player_id not in g["player_ids"]:
        g["player_ids"].append(player_id)
        g["members"].append({
            "name": p["nickname"], "role": "fighter", "lastSeen": "online", "playerId": player_id,
        })
    p["guild_id"] = gid
    return g


def leave_guild(player_id: str) -> None:
    gid = players[player_id].get("guild_id")
    if not gid or gid not in guilds:
        return
    g = guilds[gid]
    if g.get("is_faction"):
        g["player_ids"] = [x for x in g["player_ids"] if x != player_id]
        g["members"] = [m for m in g["members"] if m.get("playerId") != player_id]
    players[player_id]["guild_id"] = None


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
        available = [gid for gid in queue if gid in guilds and guilds[gid].get("is_faction")]
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
    war["duel"] = DuelState(player=home_f, enemy=away_f)
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
        else:
            war["away_score"] += 1
        await asyncio.sleep(1.0)
        war["duel_index"] += 1
        war["duel"] = None
        if war["duel_index"] >= 3:
            await finish_war(war_id)
        else:
            await start_duel(war_id)
        return


async def broadcast_duel_update(war_id: str, new_log: list) -> None:
    war = wars[war_id]
    d = war["duel"]

    for gid, you_are in ((war["home_id"], "home"), (war["away_id"], "away")):
        g = guilds[gid]
        if g.get("is_system"):
            continue
        if you_are == "home":
            state = d.snapshot()
            your_turn = war["turn"] == "home"
        else:
            state = {
                "playerHp": d.enemy_hp,
                "enemyHp": d.player_hp,
                "playerMax": d.enemy["maxHp"],
                "enemyMax": d.player["maxHp"],
                "guarding": {"player": d.guarding_enemy, "enemy": d.guarding_player},
            }
            your_turn = war["turn"] == "away"

        for pid in g["player_ids"]:
            await send_player(pid, {
                "type": "war.duel.update",
                "warId": war_id,
                "log": new_log,
                "state": state,
                "yourTurn": your_turn,
                "opponentThinking": not your_turn,
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

    for g, won in ((home, home_won), (away, away_won)):
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

    for gid, you_are in ((war["home_id"], "home"), (war["away_id"], "away")):
        g = guilds[gid]
        if g.get("is_system"):
            continue
        won = home_won if you_are == "home" else away_won
        opp = away if you_are == "home" else home
        for pid in g["player_ids"]:
            await send_player(pid, {
                "type": "war.end",
                "warId": war_id,
                "won": won,
                "homeScore": war["home_score"],
                "awayScore": war["away_score"],
                "guild": public_guild_profile(g),
                "opponent": public_guild_profile(opp),
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
        nickname = (msg.get("nickname") or "fighter")[:20].strip()
        pid = str(uuid.uuid4())
        players[pid] = {"ws": ws, "nickname": nickname, "guild_id": None}
        ws_to_player[ws] = pid
        guild = None
        gid = players[pid].get("guild_id")
        if gid and gid in guilds:
            guild = public_guild_profile(guilds[gid])
        await ws.send(_json({
            "type": "auth.ok",
            "playerId": pid,
            "nickname": nickname,
            "guild": guild,
            "factions": factions_public(),
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
        await ws.send(_json({
            "type": "guild.updated",
            "guild": public_guild_profile(g),
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
        leave_guild(pid)
        await ws.send(_json({"type": "guild.updated", "guild": None}))
        return

    if mtype == "war.queue":
        gid = players[pid].get("guild_id")
        if not gid or gid not in guilds:
            await ws.send(_json({"type": "error", "message": "Join a guild first"}))
            return
        g = guilds[gid]
        if g.get("is_system"):
            return
        if g.get("in_war"):
            await ws.send(_json({"type": "error", "message": "Already in a war"}))
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
            players[pid]["ws"] = None


async def main() -> None:
    init_faction_guilds()
    asyncio.create_task(matchmaking_tick())
    async with websockets.serve(ws_handler, "0.0.0.0", PORT):
        print(f"Nazo Arena server on ws://0.0.0.0:{PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
