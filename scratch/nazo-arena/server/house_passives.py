"""House passive abilities — applied during guild war duels."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from battle_engine import DuelState

PASSIVES = {
    "gryffindor": {
        "name": "Courage",
        "desc": "+10% damage when your fighter is below 30% HP.",
    },
    "ravenclaw": {
        "name": "Insight",
        "desc": "See the opponent's last action each turn.",
    },
    "hufflepuff": {
        "name": "Dedication",
        "desc": "Recover 5 HP when you Guard.",
    },
    "slytherin": {
        "name": "Cunning",
        "desc": "15% chance to steal a successful Chaos hit.",
    },
}

ACTION_LABELS = {
    "strike": "Strike",
    "guard": "Guard",
    "skill": "Skill",
    "chaos": "Chaos",
}


def _acting_faction(state: "DuelState", is_player_turn: bool) -> str | None:
    return state.home_faction if is_player_turn else state.away_faction


def _defending_faction(state: "DuelState", is_player_turn: bool) -> str | None:
    return state.away_faction if is_player_turn else state.home_faction


def gryffindor_damage_mult(state: "DuelState", is_player_attacking: bool) -> float:
    fac = state.home_faction if is_player_attacking else state.away_faction
    if fac != "gryffindor":
        return 1.0
    hp = state.player_hp if is_player_attacking else state.enemy_hp
    mx = state.player["maxHp"] if is_player_attacking else state.enemy["maxHp"]
    if mx and hp / mx <= 0.30:
        return 1.10
    return 1.0


def apply_hufflepuff_guard_heal(state: "DuelState", is_player_turn: bool, entries: list) -> None:
    fac = _acting_faction(state, is_player_turn)
    if fac != "hufflepuff":
        return
    if is_player_turn:
        state.player_hp = min(state.player["maxHp"], state.player_hp + 5)
        entries.append(state.add_log("Hufflepuff Dedication: +5 HP", "player"))
    else:
        state.enemy_hp = min(state.enemy["maxHp"], state.enemy_hp + 5)
        entries.append(state.add_log("Opponent dedication: +5 HP", "enemy"))


def try_slytherin_chaos_steal(state: "DuelState", is_player_turn: bool, entries: list) -> bool:
    """If defender is Slytherin, 15% chance to steal chaos damage. Returns True if stolen."""
    fac = _defending_faction(state, is_player_turn)
    if fac != "slytherin" or random.random() >= 0.15:
        return False
    entries.append(state.add_log("Slytherin Cunning steals the chaos!", "crit"))
    return True


def record_action(state: "DuelState", action: str, is_player_turn: bool) -> None:
    if is_player_turn:
        state.last_home_action = action
    else:
        state.last_away_action = action


def ravenclaw_intel(state: "DuelState", for_home_player: bool) -> str | None:
    """Last action the opponent took, visible to Ravenclaw on that side."""
    fac = state.home_faction if for_home_player else state.away_faction
    if fac != "ravenclaw":
        return None
    opp = state.last_away_action if for_home_player else state.last_home_action
    if not opp:
        return None
    return ACTION_LABELS.get(opp, opp)


def passive_log_for_action(state: "DuelState", is_player_turn: bool, entries: list) -> None:
    """Gryffindor bonus message when attacking low."""
    mult = gryffindor_damage_mult(state, is_player_turn)
    if mult > 1.0:
        side = "player" if is_player_turn else "enemy"
        entries.append(state.add_log("Gryffindor Courage! +10% damage", side))
