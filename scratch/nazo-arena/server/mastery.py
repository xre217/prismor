"""Fighter mastery tiers — XP from wars/duels unlocks combat bonuses."""

from __future__ import annotations

from typing import Any

# XP thresholds (inclusive). War roster: +12W/+4L per fighter. Duel: +8W/+3L for the fighter used.
TIERS: list[dict[str, Any]] = [
    {
        "id": 0,
        "name": "Rookie",
        "minXp": 0,
        "bonuses": {},
        "desc": "No bonus",
    },
    {
        "id": 1,
        "name": "Adept",
        "minXp": 12,
        "bonuses": {"power": 1, "maxHp": 3},
        "desc": "+1 Power, +3 HP",
    },
    {
        "id": 2,
        "name": "Veteran",
        "minXp": 36,
        "bonuses": {"power": 1, "mind": 1, "maxHp": 5},
        "desc": "+1 Power, +1 Mind, +5 HP",
    },
    {
        "id": 3,
        "name": "Master",
        "minXp": 72,
        "bonuses": {"power": 2, "speed": 1, "mind": 1, "maxHp": 8},
        "desc": "+2 Power, +1 Speed, +1 Mind, +8 HP",
    },
    {
        "id": 4,
        "name": "Legend",
        "minXp": 120,
        "bonuses": {"power": 2, "speed": 1, "mind": 1, "luck": 1, "shield": 1, "maxHp": 12},
        "desc": "+2 Power, +1 Speed/Mind/Luck/Shield, +12 HP",
    },
]


def tier_for_xp(xp: int) -> dict[str, Any]:
    current = TIERS[0]
    for t in TIERS:
        if xp >= t["minXp"]:
            current = t
    return current


def mastery_public(xp: int, wins: int = 0, losses: int = 0) -> dict[str, Any]:
    t = tier_for_xp(max(0, int(xp)))
    return {
        "xp": max(0, int(xp)),
        "wins": wins,
        "losses": losses,
        "tier": t["id"],
        "tierName": t["name"],
        "bonusDesc": t["desc"],
        "bonuses": dict(t["bonuses"]),
    }


def apply_mastery(fighter: dict, xp: int) -> dict[str, Any]:
    """Mutate fighter stats/HP from mastery XP. Returns public mastery info."""
    info = mastery_public(xp)
    bonuses = info["bonuses"]
    stats = fighter.setdefault("stats", {})
    for key, val in bonuses.items():
        if key == "maxHp":
            continue
        stats[key] = stats.get(key, 0) + int(val)
    hp_bonus = int(bonuses.get("maxHp", 0))
    if hp_bonus:
        fighter["maxHp"] = fighter.get("maxHp", 100) + hp_bonus
        fighter["currentHp"] = fighter["maxHp"]
    fighter["mastery"] = info
    return info


def system_mastery_xp(elo: int) -> int:
    """Fake mastery for System rivals so they scale with house ELO."""
    import random
    base = max(0, (elo - 950) // 2)
    return max(0, min(140, base + random.randint(-8, 16)))
