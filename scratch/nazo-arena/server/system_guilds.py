"""Believable guild profiles — server-only; never expose is_system to clients."""

from __future__ import annotations

import random
import uuid
from typing import Any

from battle_engine import clone_fighter, fighter_from_id
from factions import FACTIONS, pick_ids_for_faction, random_opponent_faction

MEMBER_NAMES = [
    "jaxk_", "mara.lo", "undead_pizza", "voxel_rye", "quiet_storm",
    "parse_king", "0xdelilah", "tensor_tim", "luna_wright", "chip_mason",
    "ghostbyte", "nova_k", "riftwalker", "coldstart", "hex_apple",
    "sable_arc", "nettle_d", "orbital_j", "fractal_eve", "dim_summer",
]

LAST_SEEN = ["just now", "1m ago", "2m ago", "4m ago", "8m ago", "12m ago", "online"]


def public_guild_profile(guild: dict) -> dict:
    """Strip server-only fields before sending to any client."""
    prof = {
        "id": guild["id"],
        "name": guild["name"],
        "tag": guild["tag"],
        "crest": guild["crest"],
        "elo": guild["elo"],
        "wins": guild["wins"],
        "losses": guild["losses"],
        "members": guild["members"],
        "motd": guild.get("motd", ""),
        "queued": guild.get("queued", False),
    }
    if guild.get("faction_id"):
        fac = FACTIONS[guild["faction_id"]]
        prof["factionId"] = fac["id"]
        prof["house"] = fac["house"]
        prof["lab"] = fac["lab"]
    return prof


def spawn_system_guild(near_elo: int, opponent_faction_id: str) -> dict:
    """System opponent disguised as a rival house guild."""
    fac = FACTIONS[opponent_faction_id]
    member_count = random.randint(5, 14)
    names = random.sample(MEMBER_NAMES, min(member_count, len(MEMBER_NAMES)))
    captain = names[0]
    members = []
    for i, n in enumerate(names):
        members.append({
            "name": n,
            "role": "captain" if i == 0 else random.choice(["officer", "fighter", "fighter", "recruit"]),
            "lastSeen": random.choice(LAST_SEEN),
        })

    return {
        "id": str(uuid.uuid4()),
        "name": fac["name"],
        "tag": fac["tag"],
        "crest": fac["crest"],
        "faction_id": opponent_faction_id,
        "elo": near_elo + random.randint(-60, 60),
        "wins": random.randint(8, 55),
        "losses": random.randint(4, 35),
        "members": members,
        "motd": fac.get("motd", ""),
        "is_system": True,
        "captain_name": captain,
        "invite_code": None,
        "player_ids": [],
        "queued": False,
        "in_war": False,
    }


def system_pick_fighter_ids(guild: dict) -> list[str]:
    fid = guild.get("faction_id")
    if fid:
        return pick_ids_for_faction(fid, 3)
    return pick_ids_for_faction(random.choice(list(FACTIONS.keys())), 3)


def pick_ids_from_roster(ids: list[str]) -> list[dict]:
    return [fighter_from_id(i) for i in ids[:3]]
