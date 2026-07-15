"""Alliance / co-op house bonds — scale with online same-house members."""

from __future__ import annotations

from typing import Any

# Bond tier keyed by online ally count (including yourself). 4+ uses tier 4.
ALLIANCE_BONDS: dict[int, dict[str, Any]] = {
    1: {
        "tier": 1,
        "name": "Lone Wolf",
        "icon": "🐺",
        "desc": "Fighting alone — no alliance bonus.",
        "effects": {},
    },
    2: {
        "tier": 2,
        "name": "Duo Bond",
        "icon": "🤝",
        "desc": "+3 HP · open Regen on duel 1.",
        "effects": {"max_hp": 3, "regen_open": True},
    },
    3: {
        "tier": 3,
        "name": "Trio Bond",
        "icon": "🔗",
        "desc": "+5 HP · +1 Shield · open Focus on duel 1.",
        "effects": {"max_hp": 5, "shield": 1, "focus_open": True},
    },
    4: {
        "tier": 4,
        "name": "House United",
        "icon": "🏛",
        "desc": "+8 HP · +1 Power · +6% damage · open Focus on duel 1.",
        "effects": {"max_hp": 8, "power": 1, "damage_mult": 1.06, "focus_open": True},
    },
}

ASSIST_HEAL = 6


def bond_for_count(n: int) -> dict[str, Any]:
    n = max(1, int(n or 1))
    if n >= 4:
        return dict(ALLIANCE_BONDS[4])
    return dict(ALLIANCE_BONDS.get(n, ALLIANCE_BONDS[1]))


def bond_public(n: int, member_names: list[str] | None = None) -> dict:
    b = bond_for_count(n)
    return {
        "tier": b["tier"],
        "name": b["name"],
        "icon": b["icon"],
        "desc": b["desc"],
        "count": max(1, int(n or 1)),
        "members": list(member_names or [])[:8],
    }


def apply_alliance_to_fighter(fighter: dict, bond: dict[str, Any]) -> None:
    eff = bond.get("effects") or {}
    stats = fighter.setdefault("stats", {})
    if eff.get("power"):
        stats["power"] = stats.get("power", 0) + int(eff["power"])
    if eff.get("shield"):
        stats["shield"] = stats.get("shield", 0) + int(eff["shield"])
    hp = int(eff.get("max_hp", 0))
    if hp:
        fighter["maxHp"] = fighter.get("maxHp", 100) + hp
        fighter["currentHp"] = fighter["maxHp"]


def alliance_damage_mult(bond: dict[str, Any] | None) -> float:
    if not bond:
        return 1.0
    return float((bond.get("effects") or {}).get("damage_mult", 1.0) or 1.0)


def apply_alliance_duel_open(
    state: Any,
    for_player: bool,
    bond: dict[str, Any] | None,
    entries: list,
    *,
    duel_index: int = 0,
) -> None:
    if not bond or duel_index != 0:
        return
    from status_effects import apply_status

    eff = bond.get("effects") or {}
    if eff.get("focus_open"):
        apply_status(state, "focus", for_player, 1, entries, source="Alliance")
    if eff.get("regen_open"):
        apply_status(state, "regen", for_player, 1, entries, source="Alliance")


def apply_assist_heal(state: Any, for_home: bool, entries: list, helper_name: str) -> int:
    """Heal the side's current fighter. Returns HP gained."""
    heal = ASSIST_HEAL
    if for_home:
        before = state.player_hp
        state.player_hp = min(state.player["maxHp"], state.player_hp + heal)
        gained = state.player_hp - before
        side = "player"
        name = state.player.get("name", "fighter")
    else:
        before = state.enemy_hp
        state.enemy_hp = min(state.enemy["maxHp"], state.enemy_hp + heal)
        gained = state.enemy_hp - before
        side = "enemy"
        name = state.enemy.get("name", "fighter")
    if gained > 0:
        entries.append(
            state.add_log(f"Alliance assist — {helper_name} cheers {name} (+{gained} HP)!", side)
        )
    else:
        entries.append(state.add_log(f"{helper_name}'s cheer finds {name} already full.", "system"))
    return gained
