"""Status effects for guild war duels."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from battle_engine import DuelState

STATUSES: dict[str, dict[str, Any]] = {
    "burn": {
        "name": "Burn",
        "icon": "🔥",
        "desc": "Take 5 damage at the start of your turn.",
        "kind": "debuff",
    },
    "stun": {
        "name": "Stun",
        "icon": "💫",
        "desc": "Skip your next action.",
        "kind": "debuff",
    },
    "weaken": {
        "name": "Weaken",
        "icon": "💔",
        "desc": "Shield is halved for damage calc.",
        "kind": "debuff",
    },
    "focus": {
        "name": "Focus",
        "icon": "🎯",
        "desc": "+30% damage on your next attack.",
        "kind": "buff",
    },
    "regen": {
        "name": "Regen",
        "icon": "💚",
        "desc": "Recover 5 HP at the start of your turn.",
        "kind": "buff",
    },
}


def _bucket(state: "DuelState", for_player: bool) -> list[dict]:
    if for_player:
        return state.player_statuses
    return state.enemy_statuses


def has_status(state: "DuelState", status_id: str, for_player: bool) -> bool:
    return any(s["id"] == status_id for s in _bucket(state, for_player))


def apply_status(
    state: "DuelState",
    status_id: str,
    for_player: bool,
    turns: int,
    entries: list,
    *,
    source: str = "",
) -> bool:
    """Apply or refresh a status. Returns True if applied."""
    meta = STATUSES.get(status_id)
    if not meta:
        return False
    bucket = _bucket(state, for_player)
    existing = next((s for s in bucket if s["id"] == status_id), None)
    if existing:
        existing["turns"] = max(existing["turns"], turns)
    else:
        bucket.append({
            "id": status_id,
            "name": meta["name"],
            "icon": meta["icon"],
            "turns": turns,
            "kind": meta["kind"],
        })
    who = state.player["name"] if for_player else state.enemy["name"]
    cls = "player" if for_player else "enemy"
    prefix = f"{source}: " if source else ""
    entries.append(state.add_log(f"{prefix}{who} gains {meta['icon']} {meta['name']} ({turns})", cls))
    return True


def cleanse(state: "DuelState", for_player: bool, entries: list, *, count: int = 1) -> int:
    """Remove up to `count` debuffs. Returns how many removed."""
    bucket = _bucket(state, for_player)
    removed = 0
    keep: list[dict] = []
    for s in bucket:
        if removed < count and s.get("kind") == "debuff":
            removed += 1
            who = state.player["name"] if for_player else state.enemy["name"]
            cls = "player" if for_player else "enemy"
            entries.append(state.add_log(f"{who} cleanses {s['icon']} {s['name']}", cls))
        else:
            keep.append(s)
    if for_player:
        state.player_statuses = keep
    else:
        state.enemy_statuses = keep
    return removed


def consume_status(state: "DuelState", status_id: str, for_player: bool) -> bool:
    bucket = _bucket(state, for_player)
    for i, s in enumerate(bucket):
        if s["id"] == status_id:
            bucket.pop(i)
            return True
    return False


def tick_start_of_turn(state: "DuelState", for_player: bool, entries: list) -> bool:
    """
    Process DOTs/HOTs and turn countdowns at start of a side's turn.
    Returns True if the fighter is stunned and should skip their action.
    """
    bucket = _bucket(state, for_player)
    who = state.player["name"] if for_player else state.enemy["name"]
    cls = "player" if for_player else "enemy"
    stunned = False
    remaining: list[dict] = []

    for s in list(bucket):
        sid = s["id"]

        if sid == "focus":
            # Focus lasts until spent on an attack — no turn decay
            remaining.append(s)
            continue

        if sid == "burn":
            dmg = 5
            if for_player:
                state.player_hp = max(0, state.player_hp - dmg)
            else:
                state.enemy_hp = max(0, state.enemy_hp - dmg)
            entries.append(state.add_log(f"🔥 Burn scorches {who} for {dmg}", "enemy" if for_player else "player"))
        elif sid == "regen":
            heal = 5
            if for_player:
                state.player_hp = min(state.player["maxHp"], state.player_hp + heal)
            else:
                state.enemy_hp = min(state.enemy["maxHp"], state.enemy_hp + heal)
            entries.append(state.add_log(f"💚 Regen heals {who} for {heal}", cls))
        elif sid == "stun":
            stunned = True
            entries.append(state.add_log(f"💫 {who} is stunned and skips the turn!", "system"))
            continue  # consume stun immediately

        s["turns"] -= 1
        if s["turns"] > 0:
            remaining.append(s)

    if for_player:
        state.player_statuses = remaining
    else:
        state.enemy_statuses = remaining
    return stunned


def statuses_public(state: "DuelState") -> dict:
    return {
        "player": [dict(s) for s in state.player_statuses],
        "enemy": [dict(s) for s in state.enemy_statuses],
    }


def shield_mult(state: "DuelState", for_defender_player: bool) -> float:
    """Weaken halves shield contribution."""
    if has_status(state, "weaken", for_defender_player):
        return 0.5
    return 1.0


def focus_mult(state: "DuelState", for_attacker_player: bool) -> float:
    if has_status(state, "focus", for_attacker_player):
        return 1.30
    return 1.0


def maybe_consume_focus(state: "DuelState", for_attacker_player: bool, entries: list) -> None:
    if consume_status(state, "focus", for_attacker_player):
        who = state.player["name"] if for_attacker_player else state.enemy["name"]
        cls = "player" if for_attacker_player else "enemy"
        entries.append(state.add_log(f"🎯 {who} spends Focus!", cls))
