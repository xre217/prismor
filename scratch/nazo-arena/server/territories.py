"""Territory map — houses contest regions for control and mild war bonuses."""

from __future__ import annotations

from typing import Any

# Static map layout: row/col for CSS grid placement (1-indexed)
TERRITORIES: dict[str, dict[str, Any]] = {
    "astronomy_tower": {
        "id": "astronomy_tower",
        "name": "Astronomy Tower",
        "icon": "🔭",
        "flavor": "Truth-seeking heights.",
        "row": 1, "col": 2,
        "home": "ravenclaw",
        "bonus": {"mind": 1},
        "bonusDesc": "+1 Mind in wars",
    },
    "owlery": {
        "id": "owlery",
        "name": "Owlery",
        "icon": "🦉",
        "flavor": "Signals in flight.",
        "row": 1, "col": 3,
        "home": None,
        "bonus": {"speed": 1},
        "bonusDesc": "+1 Speed in wars",
    },
    "north_tower": {
        "id": "north_tower",
        "name": "North Tower",
        "icon": "🦅",
        "flavor": "Ravenclaw roost.",
        "row": 1, "col": 4,
        "home": "ravenclaw",
        "bonus": {"max_hp": 3},
        "bonusDesc": "+3 HP in wars",
    },
    "library": {
        "id": "library",
        "name": "Library",
        "icon": "📚",
        "flavor": "Restricted section optional.",
        "row": 2, "col": 1,
        "home": None,
        "bonus": {"focus_open": True},
        "bonusDesc": "Open Focus in duel 1",
    },
    "great_hall": {
        "id": "great_hall",
        "name": "Great Hall",
        "icon": "🏛",
        "flavor": "The prize of every house.",
        "row": 2, "col": 3,
        "home": None,
        "bonus": {"power": 1, "max_hp": 2},
        "bonusDesc": "+1 Power, +2 HP",
    },
    "gryffindor_tower": {
        "id": "gryffindor_tower",
        "name": "Gryffindor Tower",
        "icon": "🦁",
        "flavor": "Courage under fire.",
        "row": 2, "col": 5,
        "home": "gryffindor",
        "bonus": {"power": 1},
        "bonusDesc": "+1 Power in wars",
    },
    "greenhouse": {
        "id": "greenhouse",
        "name": "Greenhouse",
        "icon": "🌿",
        "flavor": "Steady growth.",
        "row": 3, "col": 1,
        "home": "hufflepuff",
        "bonus": {"regen_open": True},
        "bonusDesc": "Open Regen (1) each duel",
    },
    "quidditch_pitch": {
        "id": "quidditch_pitch",
        "name": "Quidditch Pitch",
        "icon": "🏆",
        "flavor": "Public spectacle.",
        "row": 3, "col": 3,
        "home": None,
        "bonus": {"luck": 1},
        "bonusDesc": "+1 Luck in wars",
    },
    "dungeons": {
        "id": "dungeons",
        "name": "Dungeons",
        "icon": "🐍",
        "flavor": "Ambush corridors.",
        "row": 3, "col": 5,
        "home": "slytherin",
        "bonus": {"chaos_burn_boost": True},
        "bonusDesc": "Chaos burn chance +20%",
    },
    "potions_lab": {
        "id": "potions_lab",
        "name": "Potions Lab",
        "icon": "⚗",
        "flavor": "Brew or break.",
        "row": 4, "col": 2,
        "home": None,
        "bonus": {"shield": 1},
        "bonusDesc": "+1 Shield in wars",
    },
    "forbidden_forest": {
        "id": "forbidden_forest",
        "name": "Forbidden Forest",
        "icon": "🌲",
        "flavor": "Wild models roam.",
        "row": 4, "col": 4,
        "home": "slytherin",
        "bonus": {"strike_burn_chance": 0.10},
        "bonusDesc": "10% strike Burn",
    },
    "room_of_requirement": {
        "id": "room_of_requirement",
        "name": "Room of Requirement",
        "icon": "✨",
        "flavor": "Appears when needed.",
        "row": 4, "col": 3,
        "home": None,
        "bonus": {"damage_mult": 1.05, "max_hp": 4},
        "bonusDesc": "+5% damage, +4 HP",
    },
}

TERRITORY_ORDER = list(TERRITORIES.keys())
MAX_STACKED_TERRITORIES = 3  # combat bonuses from at most 3 owned regions


def territory_public(tid: str, owner: str | None) -> dict:
    t = TERRITORIES[tid]
    return {
        "id": t["id"],
        "name": t["name"],
        "icon": t["icon"],
        "flavor": t["flavor"],
        "row": t["row"],
        "col": t["col"],
        "home": t["home"],
        "bonusDesc": t["bonusDesc"],
        "ownerFaction": owner,
    }


def merge_territory_bonuses(owned_ids: list[str]) -> dict[str, Any]:
    """Stack mild bonuses from owned territories (capped)."""
    merged: dict[str, Any] = {
        "power": 0, "speed": 0, "mind": 0, "shield": 0, "luck": 0, "max_hp": 0,
        "damage_mult": 1.0,
        "strike_burn_chance": 0.0,
        "focus_open": False,
        "regen_open": False,
        "chaos_burn_boost": False,
    }
    for tid in owned_ids[:MAX_STACKED_TERRITORIES]:
        t = TERRITORIES.get(tid)
        if not t:
            continue
        b = t["bonus"]
        for k in ("power", "speed", "mind", "shield", "luck", "max_hp"):
            merged[k] += int(b.get(k, 0))
        if "damage_mult" in b:
            merged["damage_mult"] *= float(b["damage_mult"])
        if "strike_burn_chance" in b:
            merged["strike_burn_chance"] += float(b["strike_burn_chance"])
        if b.get("focus_open"):
            merged["focus_open"] = True
        if b.get("regen_open"):
            merged["regen_open"] = True
        if b.get("chaos_burn_boost"):
            merged["chaos_burn_boost"] = True
    return merged


def apply_territory_bonuses(fighter: dict, bonuses: dict[str, Any]) -> None:
    stats = fighter.setdefault("stats", {})
    for k in ("power", "speed", "mind", "shield", "luck"):
        if bonuses.get(k):
            stats[k] = stats.get(k, 0) + int(bonuses[k])
    hp = int(bonuses.get("max_hp", 0))
    if hp:
        fighter["maxHp"] = fighter.get("maxHp", 100) + hp
        fighter["currentHp"] = fighter["maxHp"]


def territory_damage_mult(bonuses: dict[str, Any] | None) -> float:
    if not bonuses:
        return 1.0
    return float(bonuses.get("damage_mult", 1.0) or 1.0)


def apply_territory_duel_open(
    state: Any,
    for_player: bool,
    bonuses: dict[str, Any] | None,
    entries: list,
    *,
    duel_index: int = 0,
) -> None:
    """Start-of-duel territory procs (Focus on duel 1 / Regen each duel)."""
    if not bonuses:
        return
    from status_effects import apply_status

    if bonuses.get("focus_open") and duel_index == 0:
        apply_status(state, "focus", for_player, 1, entries, source="Territory")
    if bonuses.get("regen_open"):
        apply_status(state, "regen", for_player, 1, entries, source="Territory")


def map_public(owners: dict[str, str | None]) -> list[dict]:
    """Full map snapshot for clients."""
    return [territory_public(tid, owners.get(tid)) for tid in TERRITORY_ORDER]


def bonuses_for_faction(owned_ids: list[str]) -> dict[str, Any]:
    return merge_territory_bonuses(owned_ids)
