"""Daily quests + quest-point rewards for Nazo Arena."""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any

from relics import RELICS

# Fixed daily slate (UTC). Progress metrics match store increments.
DAILY_QUESTS: list[dict[str, Any]] = [
    {
        "id": "war_play",
        "title": "House Duty",
        "icon": "⚔",
        "desc": "Finish 1 house war",
        "metric": "wars_played",
        "target": 1,
        "reward": {"qp": 20},
        "rewardDesc": "+20 quest points",
    },
    {
        "id": "war_win",
        "title": "Claim Glory",
        "icon": "🏆",
        "desc": "Win 1 house war",
        "metric": "wars_won",
        "target": 1,
        "reward": {"qp": 35, "relic_roll": 0.30},
        "rewardDesc": "+35 QP · 30% common relic",
    },
    {
        "id": "duel_win",
        "title": "Sparring",
        "icon": "💫",
        "desc": "Win 2 duels",
        "metric": "duels_won",
        "target": 2,
        "reward": {"qp": 25, "mastery_xp": 8},
        "rewardDesc": "+25 QP · +8 mastery XP",
    },
]

QUEST_BY_ID = {q["id"]: q for q in DAILY_QUESTS}

# Spend quest points in the guild hall
QUEST_SHOP: list[dict[str, Any]] = [
    {
        "id": "mastery_tome",
        "name": "Mastery Tome",
        "icon": "📖",
        "cost": 30,
        "desc": "+10 XP to one of your drafted fighters (or a house starter).",
        "kind": "mastery_xp",
        "amount": 10,
    },
    {
        "id": "relic_cache",
        "name": "Relic Cache",
        "icon": "📦",
        "cost": 55,
        "desc": "Unlock a random common relic you don't own.",
        "kind": "relic_common",
    },
    {
        "id": "fortune_draw",
        "name": "Fortune Draw",
        "icon": "🎲",
        "cost": 80,
        "desc": "40% uncommon / 50% common / 10% rare unlock (if missing).",
        "kind": "relic_fortune",
    },
]

SHOP_BY_ID = {s["id"]: s for s in QUEST_SHOP}

METRIC_QUESTS: dict[str, list[str]] = {}
for _q in DAILY_QUESTS:
    METRIC_QUESTS.setdefault(_q["metric"], []).append(_q["id"])


def utc_day_key(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d")


def seconds_until_utc_midnight(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    tomorrow = tomorrow + timedelta(days=1)
    return max(0, int((tomorrow - now).total_seconds()))


def quest_public(q: dict, progress: int, claimed: bool) -> dict:
    target = int(q["target"])
    prog = min(int(progress), target)
    return {
        "id": q["id"],
        "title": q["title"],
        "icon": q["icon"],
        "desc": q["desc"],
        "target": target,
        "progress": prog,
        "complete": prog >= target,
        "claimed": bool(claimed),
        "rewardDesc": q["rewardDesc"],
        "claimable": prog >= target and not claimed,
    }


def shop_public(qp: int) -> list[dict]:
    out = []
    for s in QUEST_SHOP:
        out.append({
            "id": s["id"],
            "name": s["name"],
            "icon": s["icon"],
            "cost": s["cost"],
            "desc": s["desc"],
            "affordable": qp >= s["cost"],
        })
    return out


def common_relic_ids() -> list[str]:
    return [rid for rid, r in RELICS.items() if r["rarity"] == "common"]


def roll_common_relic(owned: set[str]) -> str | None:
    missing = [rid for rid in common_relic_ids() if rid not in owned]
    return random.choice(missing) if missing else None


def roll_fortune_relic(owned: set[str]) -> str | None:
    """Weighted rarity draw among missing relics."""
    buckets = {"common": [], "uncommon": [], "rare": [], "legendary": []}
    for rid, r in RELICS.items():
        if rid not in owned:
            buckets[r["rarity"]].append(rid)
    roll = random.random()
    if roll < 0.40 and buckets["uncommon"]:
        return random.choice(buckets["uncommon"])
    if roll < 0.50 and buckets["rare"]:
        return random.choice(buckets["rare"])
    if buckets["common"]:
        return random.choice(buckets["common"])
    # fallback any missing
    for rarity in ("uncommon", "rare", "legendary", "common"):
        if buckets[rarity]:
            return random.choice(buckets[rarity])
    return None


def dailies_payload(rows: list[dict], qp: int) -> dict:
    """Build client payload from store rows for today."""
    by_id = {r["quest_id"]: r for r in rows}
    quests = []
    for q in DAILY_QUESTS:
        row = by_id.get(q["id"], {})
        quests.append(quest_public(q, row.get("progress", 0), bool(row.get("claimed"))))
    claimed_n = sum(1 for q in quests if q["claimed"])
    return {
        "dayKey": utc_day_key(),
        "resetsInSec": seconds_until_utc_midnight(),
        "questPoints": qp,
        "quests": quests,
        "allClaimed": claimed_n == len(DAILY_QUESTS),
        "shop": shop_public(qp),
    }
