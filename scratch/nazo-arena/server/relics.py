"""Relics — persistent unlocks that tweak guild war draft/combat."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from battle_engine import DuelState

RELICS: dict[str, dict[str, Any]] = {
    "ember_sigil": {
        "id": "ember_sigil",
        "name": "Ember Sigil",
        "icon": "🔥",
        "rarity": "common",
        "desc": "Strikes have a 25% chance to Burn.",
        "effects": {"strike_burn_chance": 0.25},
    },
    "iron_ward": {
        "id": "iron_ward",
        "name": "Iron Ward",
        "icon": "🛡",
        "rarity": "common",
        "desc": "+6 max HP in duels.",
        "effects": {"max_hp": 6},
    },
    "swift_quill": {
        "id": "swift_quill",
        "name": "Swift Quill",
        "icon": "🪶",
        "rarity": "common",
        "desc": "+1 Speed in duels.",
        "effects": {"speed": 1},
    },
    "scout_lens": {
        "id": "scout_lens",
        "name": "Scout Lens",
        "icon": "🔍",
        "rarity": "uncommon",
        "desc": "Start each duel with Focus.",
        "effects": {"open_focus": True},
    },
    "viper_fang": {
        "id": "viper_fang",
        "name": "Viper Fang",
        "icon": "🐍",
        "rarity": "uncommon",
        "desc": "Successful Chaos always applies Burn.",
        "effects": {"chaos_burn_always": True},
    },
    "glass_heart": {
        "id": "glass_heart",
        "name": "Glass Heart",
        "icon": "💗",
        "rarity": "uncommon",
        "desc": "Guard also grants Regen (1 turn).",
        "effects": {"guard_regen": True},
    },
    "crown_shard": {
        "id": "crown_shard",
        "name": "Crown Shard",
        "icon": "👑",
        "rarity": "rare",
        "desc": "+1 Power and +1 Mind in duels.",
        "effects": {"power": 1, "mind": 1},
    },
    "hourglass": {
        "id": "hourglass",
        "name": "Hourglass Charm",
        "icon": "⏳",
        "rarity": "rare",
        "desc": "Guard cleanses one debuff.",
        "effects": {"guard_cleanse": True},
    },
    "ban_seal": {
        "id": "ban_seal",
        "name": "Ban Seal",
        "icon": "🔏",
        "rarity": "rare",
        "desc": "Your first pick in a war gains +5 HP.",
        "effects": {"first_pick_hp": 5},
    },
    "oracle_coin": {
        "id": "oracle_coin",
        "name": "Oracle Coin",
        "icon": "🪙",
        "rarity": "legendary",
        "desc": "+8% damage; start each duel with Regen (1).",
        "effects": {"damage_mult": 1.08, "open_regen_turns": 1},
    },
}

RARITY_WEIGHTS = {
    "common": 55,
    "uncommon": 30,
    "rare": 12,
    "legendary": 3,
}


def relic_public(relic_id: str, *, equipped: bool = False, owned: bool = True) -> dict | None:
    r = RELICS.get(relic_id)
    if not r:
        return None
    return {
        "id": r["id"],
        "name": r["name"],
        "icon": r["icon"],
        "rarity": r["rarity"],
        "desc": r["desc"],
        "equipped": equipped,
        "owned": owned,
    }


def catalog_public(owned_ids: set[str], equipped: str | None) -> list[dict]:
    out = []
    for rid, r in RELICS.items():
        out.append({
            "id": r["id"],
            "name": r["name"],
            "icon": r["icon"],
            "rarity": r["rarity"],
            "desc": r["desc"],
            "owned": rid in owned_ids,
            "equipped": rid == equipped,
        })
    rarity_order = {"legendary": 0, "rare": 1, "uncommon": 2, "common": 3}
    out.sort(key=lambda x: (0 if x["owned"] else 1, rarity_order.get(x["rarity"], 9), x["name"]))
    return out


def effects_for(relic_id: str | None) -> dict[str, Any]:
    if not relic_id or relic_id not in RELICS:
        return {}
    return dict(RELICS[relic_id]["effects"])


def apply_relic_to_fighter(fighter: dict, relic_id: str | None, *, first_pick: bool = False) -> dict | None:
    """Mutate fighter stats/HP from equipped relic. Returns public relic info."""
    eff = effects_for(relic_id)
    if not eff:
        return relic_public(relic_id) if relic_id else None

    stats = fighter.setdefault("stats", {})
    for key in ("power", "speed", "mind", "shield", "luck"):
        if key in eff:
            stats[key] = stats.get(key, 0) + int(eff[key])
    hp = int(eff.get("max_hp", 0))
    if first_pick:
        hp += int(eff.get("first_pick_hp", 0))
    if hp:
        fighter["maxHp"] = fighter.get("maxHp", 100) + hp
        fighter["currentHp"] = fighter["maxHp"]
    fighter["relicId"] = relic_id
    return relic_public(relic_id)


def apply_relic_duel_open(state: "DuelState", for_player: bool, relic_id: str | None, entries: list) -> None:
    """Start-of-duel relic procs (Focus / Regen)."""
    from status_effects import apply_status

    eff = effects_for(relic_id)
    if not eff:
        return
    if eff.get("open_focus"):
        apply_status(state, "focus", for_player, 1, entries, source="Relic")
    turns = int(eff.get("open_regen_turns", 0))
    if turns:
        apply_status(state, "regen", for_player, turns, entries, source="Relic")


def relic_damage_mult(relic_id: str | None) -> float:
    return float(effects_for(relic_id).get("damage_mult", 1.0))


def roll_relic_drop(owned: set[str]) -> str | None:
    """Roll a new relic the player doesn't own. None if inventory complete or miss."""
    missing = [rid for rid in RELICS if rid not in owned]
    if not missing:
        return None
    # 40% chance to drop something on a war win
    if random.random() > 0.40:
        return None
    weighted: list[str] = []
    for rid in missing:
        w = RARITY_WEIGHTS.get(RELICS[rid]["rarity"], 10)
        weighted.extend([rid] * w)
    return random.choice(weighted)


def system_relic_for_elo(elo: int) -> str | None:
    """Pick a plausible equipped relic for System rivals."""
    if elo < 980:
        return random.choice(["ember_sigil", "iron_ward", "swift_quill", None, None])
    if elo < 1080:
        return random.choice(["scout_lens", "viper_fang", "glass_heart", "ember_sigil"])
    if elo < 1180:
        return random.choice(["crown_shard", "hourglass", "ban_seal", "viper_fang"])
    return random.choice(["oracle_coin", "crown_shard", "hourglass", "ban_seal"])
