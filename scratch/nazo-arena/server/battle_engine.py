"""Battle engine — mirrors client logic for server-side duels."""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from typing import Any

from factions import ALL_FIGHTERS, ARCHETYPES, ARCHETYPE_BY_ID  # noqa: E402


def clone_fighter(base: dict) -> dict:
    f = copy.deepcopy(base)
    f["stats"] = dict(base["stats"])
    f["currentHp"] = 100
    f["maxHp"] = 100
    f["alive"] = True
    return f


def fighter_from_id(fid: str) -> dict:
    base = ARCHETYPE_BY_ID[fid]
    return clone_fighter(base)


def roll(luck: int) -> float:
    return random.random() * 10 + luck * 0.5


def calc_damage(attacker: dict, defender_stats: dict, guarding: bool, mult: float = 1, ignore_shield: float = 0) -> int:
    atk = attacker["stats"]["power"] + roll(attacker["stats"]["luck"]) * 0.3
    shield = defender_stats["shield"] * (1.5 if guarding else 1) * (1 - ignore_shield)
    spd = defender_stats.get("_speed", defender_stats.get("speed", 0))
    if "speed" in defender_stats:
        spd = defender_stats["speed"]
    atk_spd = attacker["stats"]["speed"]
    dmg = (atk - shield * 0.4 + atk_spd * 0.2) * mult
    return max(3, int(dmg))


@dataclass
class DuelState:
    player: dict
    enemy: dict
    player_hp: int = 100
    enemy_hp: int = 100
    guarding_player: bool = False
    guarding_enemy: bool = False
    foresight: bool = False
    reflect: int = 0
    dodge: bool = False
    deep_scan: bool = False
    log: list = field(default_factory=list)
    home_faction: str | None = None
    away_faction: str | None = None
    last_home_action: str | None = None
    last_away_action: str | None = None

    def snapshot(self) -> dict:
        return {
            "playerHp": self.player_hp,
            "enemyHp": self.enemy_hp,
            "playerMax": self.player["maxHp"],
            "enemyMax": self.enemy["maxHp"],
            "guarding": {"player": self.guarding_player, "enemy": self.guarding_enemy},
        }

    def add_log(self, msg: str, cls: str = "system") -> dict:
        entry = {"msg": msg, "cls": cls}
        self.log.append(entry)
        return entry


def ai_choose_action(state: DuelState, is_enemy: bool) -> str:
    """Pick action for AI-controlled fighter."""
    hp_self = state.enemy_hp if is_enemy else state.player_hp
    hp_opp = state.player_hp if is_enemy else state.enemy_hp
    r = random.random()
    if hp_opp < 30 and r < 0.35:
        return "strike"
    if hp_self < 25 and r < 0.4:
        return "guard"
    if r < 0.15:
        return "chaos"
    if r < 0.35:
        return "skill"
    if r < 0.55:
        return "guard"
    return "strike"


def apply_player_action(state: DuelState, action: str, is_player_turn: bool) -> list[dict]:
    """Resolve one action. is_player_turn=True means home/player-side acts."""
    from house_passives import (
        apply_hufflepuff_guard_heal,
        gryffindor_damage_mult,
        passive_log_for_action,
        record_action,
        try_slytherin_chaos_steal,
    )

    entries: list[dict] = []
    self_f = state.player if is_player_turn else state.enemy
    name = self_f["name"]

    if is_player_turn:
        state.guarding_player = False
    else:
        state.guarding_enemy = False

    if action == "guard":
        if is_player_turn:
            state.guarding_player = True
        else:
            state.guarding_enemy = True
        entries.append(state.add_log(f"{name} guards.", "player" if is_player_turn else "enemy"))
        apply_hufflepuff_guard_heal(state, is_player_turn, entries)
        record_action(state, action, is_player_turn)
        return entries

    if action == "strike":
        ignore = 0.5 if (is_player_turn and state.deep_scan) else 0
        if is_player_turn and state.deep_scan:
            state.deep_scan = False
        if is_player_turn:
            defender_stats = state.enemy["stats"]
            guarding = state.guarding_enemy
        else:
            defender_stats = state.player["stats"]
            guarding = state.guarding_player
        dmg = calc_damage(self_f, defender_stats, guarding, 1, ignore)
        if gryffindor_damage_mult(state, is_player_turn) > 1.0:
            passive_log_for_action(state, is_player_turn, entries)
        entries.extend(_apply_damage(state, "enemy" if is_player_turn else "player", dmg, name, is_player_turn))
        record_action(state, action, is_player_turn)
        return entries

    if action == "skill":
        entries.append(state.add_log(f"{name} uses {self_f['skill']}!", "player" if is_player_turn else "enemy"))
        entries.extend(_run_skill(state, self_f, is_player_turn))
        record_action(state, action, is_player_turn)
        return entries

    if action == "chaos":
        outcome = random.random()
        if outcome < 0.4:
            tgt_stats = state.enemy["stats"] if is_player_turn else state.player["stats"]
            dmg = calc_damage(self_f, tgt_stats, False, 1.8)
            if gryffindor_damage_mult(state, is_player_turn) > 1.0:
                passive_log_for_action(state, is_player_turn, entries)
            if try_slytherin_chaos_steal(state, is_player_turn, entries):
                if is_player_turn:
                    state.player_hp = max(0, state.player_hp - dmg)
                    entries.append(state.add_log(f"Chaos backfires for {dmg}!", "enemy"))
                else:
                    state.enemy_hp = max(0, state.enemy_hp - dmg)
                    entries.append(state.add_log(f"Stolen chaos hits them for {dmg}!", "player"))
            else:
                entries.extend(_apply_damage(state, "enemy" if is_player_turn else "player", dmg, name, is_player_turn))
        elif outcome < 0.7:
            d = random.randint(8, 22)
            if is_player_turn:
                state.player_hp -= d
                entries.append(state.add_log(f"Chaos backfire! {d} self-damage", "enemy"))
            else:
                state.enemy_hp -= d
                entries.append(state.add_log(f"Enemy chaos implodes for {d}!", "player"))
        else:
            entries.append(state.add_log("Chaos fizzles.", "system"))
        record_action(state, action, is_player_turn)
        return entries

    return entries


def _apply_damage(state: DuelState, target: str, amount: int, source: str, from_player: bool) -> list[dict]:
    from house_passives import gryffindor_damage_mult
    if target == "enemy":
        amount = max(3, int(amount * gryffindor_damage_mult(state, True)))
    else:
        amount = max(3, int(amount * gryffindor_damage_mult(state, False)))
    entries = []
    if target == "player":
        if state.dodge:
            state.dodge = False
            entries.append(state.add_log(f"{state.player['name']} dodges!", "player"))
            counter = calc_damage(state.player, state.enemy["stats"], state.guarding_enemy, 0.8)
            state.enemy_hp -= counter
            entries.append(state.add_log(f"Counter hits for {counter}!", "player"))
            return entries
        if state.reflect > 0:
            ref = int(amount * 1.5)
            state.enemy_hp -= ref
            entries.append(state.add_log(f"Reflect! {ref} damage back!", "crit"))
            state.reflect = 0
        dmg = amount
        state.player_hp -= dmg
        entries.append(state.add_log(f"{source} hits for {dmg}", "enemy"))
    else:
        dmg = amount
        if state.foresight:
            dmg *= 2
            state.foresight = False
            entries.append(state.add_log("Foresight! Double damage!", "crit"))
        state.enemy_hp -= dmg
        entries.append(state.add_log(f"{source} deals {dmg}", "player"))
    return entries


def _run_skill(state: DuelState, self_f: dict, is_player: bool) -> list[dict]:
    skill = self_f.get("skill", "")
    entries: list[dict] = []

    if skill == "Foresight":
        if is_player:
            state.foresight = True
        else:
            dmg = calc_damage(self_f, state.player["stats"], state.guarding_player, 1.2)
            entries.extend(_apply_damage(state, "player", dmg, self_f["name"], False))
    elif skill == "Overclock":
        for _ in range(2):
            stats = state.enemy["stats"] if is_player else state.player["stats"]
            guard = state.guarding_enemy if is_player else state.guarding_player
            dmg = calc_damage(self_f, stats, guard, 0.65)
            entries.extend(_apply_damage(state, "enemy" if is_player else "player", dmg, self_f["name"], is_player))
    elif skill in ("Constitution", "Bulwark"):
        if is_player:
            state.player_hp = min(state.player["maxHp"], state.player_hp + 15)
            state.guarding_player = True
            entries.append(state.add_log("Bulwark: +15 HP", "player"))
        else:
            dmg = calc_damage(self_f, state.player["stats"], state.guarding_player, 1)
            entries.extend(_apply_damage(state, "player", dmg, self_f["name"], False))
    elif skill == "Reflect":
        if is_player:
            state.reflect = 1
        else:
            dmg = calc_damage(self_f, state.player["stats"], state.guarding_player, 1)
            entries.extend(_apply_damage(state, "player", dmg, self_f["name"], False))
    elif skill == "Fade":
        if is_player:
            state.dodge = True
        else:
            dmg = calc_damage(self_f, state.player["stats"], state.guarding_player, 1.1)
            entries.extend(_apply_damage(state, "player", dmg, self_f["name"], False))
    elif skill in ("Deep Scan", "Precision"):
        if is_player:
            state.deep_scan = True
        else:
            dmg = calc_damage(self_f, state.player["stats"], False, 0.9)
            entries.extend(_apply_damage(state, "player", dmg, self_f["name"], False))
    elif skill == "Wild Card":
        if random.random() < 0.5:
            stats = {"power": 10, "speed": 8, "mind": 5, "shield": 0, "luck": 10}
            dmg = calc_damage(self_f, stats, False, 1.5)
            entries.extend(_apply_damage(state, "enemy" if is_player else "player", dmg, self_f["name"], is_player))
        else:
            d = 12
            if is_player:
                state.player_hp -= d
                entries.append(state.add_log(f"Wild Card fumbles for {d}", "enemy"))
            else:
                state.enemy_hp -= d
                entries.append(state.add_log(f"Enemy fumbles for {d}!", "player"))
    elif skill == "Split":
        for _ in range(3):
            stats = state.enemy["stats"] if is_player else state.player["stats"]
            guard = state.guarding_enemy if is_player else state.guarding_player
            dmg = calc_damage(self_f, stats, guard, 0.4)
            if random.random() < self_f["stats"]["luck"] * 0.08:
                dmg *= 2
                entries.append(state.add_log("Micro-crit!", "crit"))
            entries.extend(_apply_damage(state, "enemy" if is_player else "player", dmg, self_f["name"], is_player))
    elif skill == "Balance":
        if is_player:
            state.player_hp = min(state.player["maxHp"], state.player_hp + 10)
            entries.append(state.add_log("Balance: +10 HP", "player"))
        else:
            dmg = calc_damage(self_f, state.player["stats"], state.guarding_player, 1)
            entries.extend(_apply_damage(state, "player", dmg, self_f["name"], False))
    elif skill == "Phase":
        stats = state.enemy["stats"] if is_player else state.player["stats"]
        guard = state.guarding_enemy if is_player else state.guarding_player
        dmg = calc_damage(self_f, stats, guard, 1.2, 0.5)
        entries.extend(_apply_damage(state, "enemy" if is_player else "player", dmg, self_f["name"], is_player))
    elif skill == "Bloom":
        if is_player:
            state.player_hp = min(state.player["maxHp"], state.player_hp + 20)
            entries.append(state.add_log("Bloom: +20 HP", "player"))
        else:
            dmg = calc_damage(self_f, state.player["stats"], state.guarding_player, 0.8)
            entries.extend(_apply_damage(state, "player", dmg, self_f["name"], False))
    else:
        stats = state.enemy["stats"] if is_player else state.player["stats"]
        guard = state.guarding_enemy if is_player else state.guarding_player
        dmg = calc_damage(self_f, stats, guard, 1.2)
        entries.extend(_apply_damage(state, "enemy" if is_player else "player", dmg, self_f["name"], is_player))

    return entries


def duel_winner(state: DuelState) -> str | None:
    if state.enemy_hp <= 0:
        return "player"
    if state.player_hp <= 0:
        return "enemy"
    return None
