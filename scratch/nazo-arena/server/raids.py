"""Seasonal boss raids — PvE gauntlets using house fighters + relics."""

from __future__ import annotations

from typing import Any

# Three-phase bosses. Active boss rotates by season id.
RAID_BOSSES: dict[str, dict[str, Any]] = {
    "chamber_basilisk": {
        "id": "chamber_basilisk",
        "name": "Chamber Basilisk",
        "icon": "🐍",
        "flavor": "Eyes that stun. Fangs that burn.",
        "phases": [
            {
                "name": "Basilisk Hatchling",
                "icon": "🥚",
                "type": "Beast",
                "skill": "Phase",
                "skillDesc": "Slip past defenses.",
                "stats": {"power": 6, "speed": 8, "mind": 5, "shield": 4, "luck": 6},
                "maxHp": 115,
            },
            {
                "name": "Basilisk",
                "icon": "🐍",
                "type": "Predator",
                "skill": "Deep Scan",
                "skillDesc": "Find a weak point.",
                "stats": {"power": 8, "speed": 6, "mind": 7, "shield": 6, "luck": 5},
                "maxHp": 135,
            },
            {
                "name": "Elder Basilisk",
                "icon": "👁",
                "type": "Horror",
                "skill": "Foresight",
                "skillDesc": "See the next strike.",
                "stats": {"power": 9, "speed": 5, "mind": 9, "shield": 7, "luck": 4},
                "maxHp": 148,
            },
        ],
        "rewards": {"qp": 45, "mastery_xp": 10, "relic_roll": 0.40},
        "rewardDesc": "+45 QP · +10 mastery · 40% relic",
    },
    "forbidden_sphinx": {
        "id": "forbidden_sphinx",
        "name": "Forbidden Sphinx",
        "icon": "🦁",
        "flavor": "Riddles in the dark. Wrong answers hurt.",
        "phases": [
            {
                "name": "Sphinx Cub",
                "icon": "🐱",
                "type": "Riddler",
                "skill": "Bloom",
                "skillDesc": "Recover and reweave.",
                "stats": {"power": 5, "speed": 7, "mind": 8, "shield": 5, "luck": 7},
                "maxHp": 110,
            },
            {
                "name": "Sphinx",
                "icon": "🦁",
                "type": "Oracle",
                "skill": "Reflect",
                "skillDesc": "Turn force aside.",
                "stats": {"power": 7, "speed": 6, "mind": 9, "shield": 8, "luck": 5},
                "maxHp": 140,
            },
            {
                "name": "Sphinx Ascendant",
                "icon": "✨",
                "type": "Myth",
                "skill": "Wild Card",
                "skillDesc": "Chaos with intent.",
                "stats": {"power": 8, "speed": 8, "mind": 10, "shield": 6, "luck": 8},
                "maxHp": 152,
            },
        ],
        "rewards": {"qp": 50, "mastery_xp": 12, "relic_roll": 0.35},
        "rewardDesc": "+50 QP · +12 mastery · 35% relic",
    },
    "owlery_storm": {
        "id": "owlery_storm",
        "name": "Owlery Storm",
        "icon": "⛈",
        "flavor": "A living squall of post and prophecy.",
        "phases": [
            {
                "name": "Gale Wisp",
                "icon": "💨",
                "type": "Spirit",
                "skill": "Overclock",
                "skillDesc": "Strike twice as fast.",
                "stats": {"power": 6, "speed": 10, "mind": 5, "shield": 3, "luck": 8},
                "maxHp": 105,
            },
            {
                "name": "Storm Herald",
                "icon": "🦉",
                "type": "Herald",
                "skill": "Split",
                "skillDesc": "Divide the field.",
                "stats": {"power": 7, "speed": 9, "mind": 6, "shield": 5, "luck": 7},
                "maxHp": 130,
            },
            {
                "name": "Tempest Nest",
                "icon": "⛈",
                "type": "Calamity",
                "skill": "Constitution",
                "skillDesc": "Weather the worst.",
                "stats": {"power": 9, "speed": 7, "mind": 7, "shield": 8, "luck": 6},
                "maxHp": 145,
            },
        ],
        "rewards": {"qp": 40, "mastery_xp": 10, "relic_roll": 0.45},
        "rewardDesc": "+40 QP · +10 mastery · 45% relic",
    },
}

BOSS_ORDER = list(RAID_BOSSES.keys())
DAILY_RAID_ATTEMPTS = 3


def boss_for_season(season_id: int) -> dict:
    idx = (max(1, int(season_id)) - 1) % len(BOSS_ORDER)
    return RAID_BOSSES[BOSS_ORDER[idx]]


def boss_public(boss: dict, *, attempts_left: int, clears: int) -> dict:
    return {
        "id": boss["id"],
        "name": boss["name"],
        "icon": boss["icon"],
        "flavor": boss["flavor"],
        "phases": len(boss["phases"]),
        "rewardDesc": boss["rewardDesc"],
        "attemptsLeft": attempts_left,
        "dailyAttempts": DAILY_RAID_ATTEMPTS,
        "clears": clears,
        "phasePreview": [
            {"name": p["name"], "icon": p["icon"], "maxHp": p["maxHp"]}
            for p in boss["phases"]
        ],
    }


def phase_as_fighter(phase: dict) -> dict:
    """Build a battle_engine-compatible fighter from a boss phase."""
    return {
        "id": f"raid-{phase['name'].lower().replace(' ', '-')}",
        "name": phase["name"],
        "icon": phase["icon"],
        "type": phase["type"],
        "skill": phase["skill"],
        "skillDesc": phase.get("skillDesc", ""),
        "stats": dict(phase["stats"]),
        "maxHp": int(phase["maxHp"]),
        "currentHp": int(phase["maxHp"]),
        "alive": True,
    }
