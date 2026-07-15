"""Believable guild profiles — server-only; never expose is_system to clients."""

from __future__ import annotations

import random
import string
import uuid
from typing import Any

from battle_engine import ARCHETYPES, clone_fighter, fighter_from_id

GUILD_NAMES = [
    "Northwind Collective", "Crimson Parse", "Static Bloom", "Velvet Circuit",
    "Iron Orchard", "Lakeview Labs", "Greyhat Union", "Null Harbor",
    "Midnight Stack", "Copper Signal", "Pale Nomads", "Deep Current",
    "Glass Meridian", "Rust & Reason", "Quiet Voltage", "Obsidian Fold",
]

TAGS = ["NWND", "CRPS", "STBL", "VLVT", "IROR", "LKLV", "GRYT", "NLHB", "MNST", "CPSG"]

CRESTS = ["🜂", "◈", "⬡", "✦", "◆", "▣", "⟁", "⎔", "◉", "⊕"]

MEMBER_NAMES = [
    "jaxk_", "mara.lo", "undead_pizza", "voxel_rye", "quiet_storm",
    "parse_king", "0xdelilah", "tensor_tim", "luna_wright", "chip_mason",
    "ghostbyte", "nova_k", "riftwalker", "coldstart", "hex_apple",
    "sable_arc", "nettle_d", "orbital_j", "fractal_eve", "dim_summer",
]

LAST_SEEN = ["just now", "1m ago", "2m ago", "4m ago", "8m ago", "12m ago", "online"]


def _rand_tag(name: str) -> str:
    words = name.upper().split()
    if len(words) >= 2:
        return (words[0][:2] + words[1][:2])[:4]
    return name[:4].upper()


def public_guild_profile(guild: dict) -> dict:
    """Strip server-only fields before sending to any client."""
    return {
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


def spawn_system_guild(elo: int | None = None) -> dict:
    """Create a guild that looks like humans run it. is_system stays server-side."""
    name = random.choice(GUILD_NAMES)
    member_count = random.randint(4, 12)
    names = random.sample(MEMBER_NAMES, min(member_count, len(MEMBER_NAMES)))
    captain = names[0]
    members = []
    for i, n in enumerate(names):
        members.append({
            "name": n,
            "role": "captain" if i == 0 else random.choice(["officer", "fighter", "fighter", "recruit"]),
            "lastSeen": random.choice(LAST_SEEN),
        })

    target_elo = elo or random.randint(920, 1180)
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "tag": _rand_tag(name),
        "crest": random.choice(CRESTS),
        "elo": target_elo,
        "wins": random.randint(5, 40),
        "losses": random.randint(3, 30),
        "members": members,
        "motd": random.choice([
            "ranked tonight. be there.",
            "new recruits welcome — dm captain",
            "three wins from diamond bracket",
            "running strats in voice after reset",
            "",
        ]),
        "is_system": True,
        "captain_name": captain,
        "invite_code": None,
        "player_ids": [],
        "queued": False,
    }


def system_pick_fighters(guild: dict) -> list[dict]:
    """System guild selects 3 fighters — biased slightly by elo."""
    elo = guild.get("elo", 1000)
    picks = random.sample(ARCHETYPES, 3)
    fighters = []
    for base in picks:
        f = clone_fighter(base)
        scale = 1 + (elo - 1000) / 2000
        for k in f["stats"]:
            f["stats"][k] = min(10, max(3, int(f["stats"][k] * scale)))
        fighters.append(f)
    return fighters


def system_pick_fighter_ids(guild: dict) -> list[str]:
    return [f["id"] for f in system_pick_fighters(guild)]


def pick_ids_from_roster(ids: list[str]) -> list[dict]:
    return [fighter_from_id(i) for i in ids[:3]]
