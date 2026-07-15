"""Ban/pick draft for guild wars.

Sequence (home first):
  1. Home bans 1 from Away pool
  2. Away bans 1 from Home pool
  3–8. Snake picks into duel order: H A A H H A
"""

from __future__ import annotations

import random
from typing import Any

from factions import FACTIONS, ALL_FIGHTERS

# (action, side) — ban targets the opponent's pool; pick from own remaining
DRAFT_STEPS: list[tuple[str, str]] = [
    ("ban", "home"),
    ("ban", "away"),
    ("pick", "home"),
    ("pick", "away"),
    ("pick", "away"),
    ("pick", "home"),
    ("pick", "home"),
    ("pick", "away"),
]

STEP_TIMEOUT_SEC = 22.0


def fighter_card(fid: str) -> dict:
    f = ALL_FIGHTERS[fid]
    return {
        "id": f["id"],
        "name": f["name"],
        "icon": f["icon"],
        "type": f["type"],
        "skill": f["skill"],
        "stats": dict(f["stats"]),
    }


def pool_ids(faction_id: str) -> list[str]:
    return [f["id"] for f in FACTIONS[faction_id]["fighters"]]


def init_draft(home_faction: str, away_faction: str) -> dict[str, Any]:
    return {
        "step": 0,
        "home_pool": pool_ids(home_faction),
        "away_pool": pool_ids(away_faction),
        "home_bans": [],  # banned from home pool (by away)
        "away_bans": [],  # banned from away pool (by home)
        "home_picks": [],
        "away_picks": [],
    }


def current_step(war: dict) -> tuple[str, str] | None:
    d = war.get("draft")
    if not d:
        return None
    if d["step"] >= len(DRAFT_STEPS):
        return None
    return DRAFT_STEPS[d["step"]]


def available_for_ban(war: dict, acting_side: str) -> list[str]:
    """Acting side bans from the opponent's remaining pool."""
    d = war["draft"]
    if acting_side == "home":
        banned = set(d["away_bans"])
        return [fid for fid in d["away_pool"] if fid not in banned]
    banned = set(d["home_bans"])
    return [fid for fid in d["home_pool"] if fid not in banned]


def available_for_pick(war: dict, side: str) -> list[str]:
    d = war["draft"]
    if side == "home":
        banned = set(d["home_bans"])
        picked = set(d["home_picks"])
        return [fid for fid in d["home_pool"] if fid not in banned and fid not in picked]
    banned = set(d["away_bans"])
    picked = set(d["away_picks"])
    return [fid for fid in d["away_pool"] if fid not in banned and fid not in picked]


def apply_draft_action(war: dict, side: str, fighter_id: str) -> str | None:
    """Apply ban/pick. Returns error message or None on success."""
    step = current_step(war)
    if not step:
        return "Draft is over"
    action, expected = step
    if side != expected:
        return "Not your turn"
    d = war["draft"]

    if action == "ban":
        opts = available_for_ban(war, side)
        if fighter_id not in opts:
            return "Cannot ban that fighter"
        if side == "home":
            d["away_bans"].append(fighter_id)
        else:
            d["home_bans"].append(fighter_id)
    else:
        opts = available_for_pick(war, side)
        if fighter_id not in opts:
            return "Cannot pick that fighter"
        d[f"{side}_picks"].append(fighter_id)

    d["step"] += 1
    return None


def draft_complete(war: dict) -> bool:
    d = war.get("draft")
    if not d:
        return False
    return len(d["home_picks"]) >= 3 and len(d["away_picks"]) >= 3


def auto_choose(war: dict, side: str) -> str | None:
    """System/timeout pick: ban strongest opponent mind+power, pick best remaining."""
    step = current_step(war)
    if not step:
        return None
    action, expected = step
    if side != expected:
        return None

    if action == "ban":
        opts = available_for_ban(war, side)
        if not opts:
            return None
        # Ban high threat (power + mind)
        return max(opts, key=lambda fid: ALL_FIGHTERS[fid]["stats"]["power"] + ALL_FIGHTERS[fid]["stats"]["mind"])

    opts = available_for_pick(war, side)
    if not opts:
        return None
    return max(opts, key=lambda fid: sum(ALL_FIGHTERS[fid]["stats"].values()))


def finalize_picks(war: dict) -> None:
    """Ensure both sides have 3 picks (fill from remaining if needed)."""
    d = war["draft"]
    for side in ("home", "away"):
        while len(d[f"{side}_picks"]) < 3:
            opts = available_for_pick(war, side)
            if not opts:
                break
            d[f"{side}_picks"].append(random.choice(opts))
    war["home_picks"] = list(d["home_picks"][:3])
    war["away_picks"] = list(d["away_picks"][:3])


def draft_public(war: dict, you_are: str) -> dict:
    """Client-facing draft snapshot from a side's perspective."""
    d = war["draft"]
    step = current_step(war)
    action, turn_side = step if step else (None, None)

    your_pool = d["home_pool"] if you_are == "home" else d["away_pool"]
    their_pool = d["away_pool"] if you_are == "home" else d["home_pool"]
    your_bans = d["home_bans"] if you_are == "home" else d["away_bans"]
    their_bans = d["away_bans"] if you_are == "home" else d["home_bans"]
    your_picks = d["home_picks"] if you_are == "home" else d["away_picks"]
    their_picks = d["away_picks"] if you_are == "home" else d["home_picks"]

    your_turn = turn_side == you_are
    selectable: list[str] = []
    if your_turn and action == "ban":
        selectable = available_for_ban(war, you_are)
    elif your_turn and action == "pick":
        selectable = available_for_pick(war, you_are)

    prompt = "Draft complete"
    if action == "ban" and your_turn:
        prompt = "Ban 1 fighter from their house"
    elif action == "ban":
        prompt = "Opponent is banning..."
    elif action == "pick" and your_turn:
        prompt = f"Pick fighter {len(your_picks) + 1} / 3 (duel order)"
    elif action == "pick":
        prompt = "Opponent is picking..."

    return {
        "step": d["step"],
        "totalSteps": len(DRAFT_STEPS),
        "phase": action or "done",
        "yourTurn": your_turn,
        "prompt": prompt,
        "yourPool": [fighter_card(fid) for fid in your_pool],
        "theirPool": [fighter_card(fid) for fid in their_pool],
        "yourBans": your_bans,
        "theirBans": their_bans,
        "yourPicks": your_picks,
        "theirPicks": their_picks,
        "selectable": selectable,
    }
