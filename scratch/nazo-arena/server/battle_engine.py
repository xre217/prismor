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


def calc_damage(
    attacker: dict,
    defender_stats: dict,
    guarding: bool,
    mult: float = 1,
    ignore_shield: float = 0,
    shield_factor: float = 1.0,
) -> int:
    atk = attacker["stats"]["power"] + roll(attacker["stats"]["luck"]) * 0.3
    shield = defender_stats["shield"] * (1.5 if guarding else 1) * (1 - ignore_shield) * shield_factor
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
    enemy_deep_scan: bool = False
    log: list = field(default_factory=list)
    home_faction: str | None = None
    away_faction: str | None = None
    last_home_action: str | None = None
    last_away_action: str | None = None
    player_statuses: list = field(default_factory=list)
    enemy_statuses: list = field(default_factory=list)

    def snapshot(self) -> dict:
        from status_effects import statuses_public
        return {
            "playerHp": self.player_hp,
            "enemyHp": self.enemy_hp,
            "playerMax": self.player["maxHp"],
            "enemyMax": self.enemy["maxHp"],
            "guarding": {"player": self.guarding_player, "enemy": self.guarding_enemy},
            "statuses": statuses_public(self),
        }

    def add_log(self, msg: str, cls: str = "system") -> dict:
        entry = {"msg": msg, "cls": cls}
        self.log.append(entry)
        return entry


def _hit_damage(state: DuelState, attacker: dict, is_attacker_player: bool, mult: float = 1, ignore_shield: float = 0) -> int:
    from status_effects import focus_mult, shield_mult

    if is_attacker_player:
        defender_stats = state.enemy["stats"]
        guarding = state.guarding_enemy
    else:
        defender_stats = state.player["stats"]
        guarding = state.guarding_player
    sf = shield_mult(state, not is_attacker_player)
    dmg = calc_damage(attacker, defender_stats, guarding, mult, ignore_shield, shield_factor=sf)
    dmg = max(3, int(dmg * focus_mult(state, is_attacker_player)))
    return dmg


def ai_choose_action(state: DuelState, is_enemy: bool) -> str:
    """Pick action for AI-controlled fighter."""
    from status_effects import has_status

    for_player = not is_enemy
    if has_status(state, "stun", for_player):
        return "guard"  # will be skipped by stun tick anyway
    hp_self = state.enemy_hp if is_enemy else state.player_hp
    hp_opp = state.player_hp if is_enemy else state.enemy_hp
    r = random.random()
    if has_status(state, "focus", for_player) and r < 0.55:
        return "strike"
    if has_status(state, "burn", for_player) and hp_self < 40 and r < 0.35:
        return "guard"
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
    from status_effects import (
        apply_status,
        maybe_consume_focus,
        tick_start_of_turn,
    )

    entries: list[dict] = []
    self_f = state.player if is_player_turn else state.enemy
    name = self_f["name"]

    # Start-of-turn ticks (burn/regen/stun)
    if tick_start_of_turn(state, is_player_turn, entries):
        record_action(state, "stun", is_player_turn)
        return entries
    if duel_winner(state):
        return entries

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
        ignore = 0.0
        if is_player_turn and state.deep_scan:
            ignore = 0.5
            state.deep_scan = False
        elif not is_player_turn and state.enemy_deep_scan:
            ignore = 0.5
            state.enemy_deep_scan = False
        dmg = _hit_damage(state, self_f, is_player_turn, 1, ignore)
        maybe_consume_focus(state, is_player_turn, entries)
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
            dmg = _hit_damage(state, self_f, is_player_turn, 1.8, 0)
            maybe_consume_focus(state, is_player_turn, entries)
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
                if random.random() < 0.40:
                    apply_status(state, "burn", not is_player_turn, 2, entries, source="Chaos")
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
    from status_effects import apply_status

    if target == "enemy":
        amount = max(3, int(amount * gryffindor_damage_mult(state, True)))
    else:
        amount = max(3, int(amount * gryffindor_damage_mult(state, False)))
    entries: list[dict] = []
    if target == "player":
        if state.dodge:
            state.dodge = False
            entries.append(state.add_log(f"{state.player['name']} dodges!", "player"))
            counter = _hit_damage(state, state.player, True, 0.8)
            state.enemy_hp -= counter
            entries.append(state.add_log(f"Counter hits for {counter}!", "player"))
            return entries
        if state.reflect > 0:
            ref = int(amount * 1.5)
            state.enemy_hp -= ref
            entries.append(state.add_log(f"Reflect! {ref} damage back!", "crit"))
            state.reflect = 0
            if random.random() < 0.25:
                apply_status(state, "stun", False, 1, entries, source="Reflect")
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
    from status_effects import apply_status, cleanse, maybe_consume_focus

    skill = self_f.get("skill", "")
    entries: list[dict] = []

    if skill == "Foresight":
        if is_player:
            state.foresight = True
            apply_status(state, "focus", True, 1, entries, source="Foresight")
        else:
            dmg = _hit_damage(state, self_f, False, 1.2)
            maybe_consume_focus(state, False, entries)
            entries.extend(_apply_damage(state, "player", dmg, self_f["name"], False))
    elif skill == "Overclock":
        for _ in range(2):
            dmg = _hit_damage(state, self_f, is_player, 0.65)
            entries.extend(_apply_damage(state, "enemy" if is_player else "player", dmg, self_f["name"], is_player))
            if random.random() < 0.22:
                apply_status(state, "burn", not is_player, 2, entries, source="Overclock")
        maybe_consume_focus(state, is_player, entries)
    elif skill in ("Constitution", "Bulwark"):
        if is_player:
            state.player_hp = min(state.player["maxHp"], state.player_hp + 15)
            state.guarding_player = True
            entries.append(state.add_log("Bulwark: +15 HP", "player"))
            cleanse(state, True, entries, count=1)
        else:
            state.enemy_hp = min(state.enemy["maxHp"], state.enemy_hp + 15)
            state.guarding_enemy = True
            entries.append(state.add_log("Bulwark: +15 HP", "enemy"))
            cleanse(state, False, entries, count=1)
    elif skill == "Reflect":
        if is_player:
            state.reflect = 1
        else:
            # Away Reflect still sets a one-shot reflect via stun chance on next hit — deal damage + chance stun
            dmg = _hit_damage(state, self_f, False, 1)
            entries.extend(_apply_damage(state, "player", dmg, self_f["name"], False))
            if random.random() < 0.30:
                apply_status(state, "stun", True, 1, entries, source="Reflect")
    elif skill == "Fade":
        if is_player:
            state.dodge = True
            cleanse(state, True, entries, count=1)
        else:
            dmg = _hit_damage(state, self_f, False, 1.1)
            entries.extend(_apply_damage(state, "player", dmg, self_f["name"], False))
    elif skill in ("Deep Scan", "Precision"):
        apply_status(state, "focus", is_player, 1, entries, source=skill)
        if skill == "Deep Scan":
            apply_status(state, "weaken", not is_player, 2, entries, source="Deep Scan")
        if is_player:
            state.deep_scan = True
        else:
            state.enemy_deep_scan = True
    elif skill == "Wild Card":
        if random.random() < 0.5:
            stats = {"power": 10, "speed": 8, "mind": 5, "shield": 0, "luck": 10}
            from status_effects import shield_mult, focus_mult
            sf = shield_mult(state, not is_player)
            dmg = calc_damage(self_f, stats, False, 1.5, shield_factor=sf)
            dmg = max(3, int(dmg * focus_mult(state, is_player)))
            maybe_consume_focus(state, is_player, entries)
            entries.extend(_apply_damage(state, "enemy" if is_player else "player", dmg, self_f["name"], is_player))
            roll_s = random.random()
            if roll_s < 0.35:
                apply_status(state, "burn", not is_player, 2, entries, source="Wild Card")
            elif roll_s < 0.55:
                apply_status(state, "weaken", not is_player, 2, entries, source="Wild Card")
            elif roll_s < 0.70:
                apply_status(state, "stun", not is_player, 1, entries, source="Wild Card")
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
            dmg = _hit_damage(state, self_f, is_player, 0.4)
            if random.random() < self_f["stats"]["luck"] * 0.08:
                dmg *= 2
                entries.append(state.add_log("Micro-crit!", "crit"))
            entries.extend(_apply_damage(state, "enemy" if is_player else "player", dmg, self_f["name"], is_player))
            if random.random() < 0.18:
                apply_status(state, "burn", not is_player, 2, entries, source="Split")
        maybe_consume_focus(state, is_player, entries)
    elif skill == "Balance":
        if is_player:
            state.player_hp = min(state.player["maxHp"], state.player_hp + 10)
            entries.append(state.add_log("Balance: +10 HP", "player"))
        else:
            state.enemy_hp = min(state.enemy["maxHp"], state.enemy_hp + 10)
            entries.append(state.add_log("Balance: +10 HP", "enemy"))
        apply_status(state, "regen", is_player, 2, entries, source="Balance")
    elif skill == "Phase":
        dmg = _hit_damage(state, self_f, is_player, 1.2, 0.5)
        maybe_consume_focus(state, is_player, entries)
        entries.extend(_apply_damage(state, "enemy" if is_player else "player", dmg, self_f["name"], is_player))
        apply_status(state, "weaken", not is_player, 2, entries, source="Phase")
    elif skill == "Bloom":
        if is_player:
            state.player_hp = min(state.player["maxHp"], state.player_hp + 20)
            entries.append(state.add_log("Bloom: +20 HP", "player"))
        else:
            state.enemy_hp = min(state.enemy["maxHp"], state.enemy_hp + 20)
            entries.append(state.add_log("Bloom: +20 HP", "enemy"))
        apply_status(state, "regen", is_player, 2, entries, source="Bloom")
        cleanse(state, is_player, entries, count=1)
    else:
        dmg = _hit_damage(state, self_f, is_player, 1.2)
        maybe_consume_focus(state, is_player, entries)
        entries.extend(_apply_damage(state, "enemy" if is_player else "player", dmg, self_f["name"], is_player))

    return entries


def duel_winner(state: DuelState) -> str | None:
    if state.enemy_hp <= 0:
        return "player"
    if state.player_hp <= 0:
        return "enemy"
    return None
