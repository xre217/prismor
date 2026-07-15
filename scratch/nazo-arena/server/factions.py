"""Four house factions — Anthropic, xAI, OpenAI, and everyone else."""

from __future__ import annotations

import copy
import random
from typing import Any

FACTIONS: dict[str, dict] = {
    "gryffindor": {
        "id": "gryffindor",
        "house": "Gryffindor",
        "lab": "Anthropic",
        "name": "Gryffindor · Anthropic",
        "tag": "GRYF",
        "crest": "🦁",
        "motd": "Bold reasoning. Constitutional courage.",
        "fighters": [
            {"id": "claude-opus", "name": "Claude Opus", "icon": "🦁", "type": "Champion", "skill": "Constitution",
             "stats": {"power": 7, "speed": 5, "mind": 9, "shield": 9, "luck": 5}},
            {"id": "claude-sonnet", "name": "Claude Sonnet", "icon": "⚔", "type": "Duelist", "skill": "Precision",
             "stats": {"power": 7, "speed": 7, "mind": 8, "shield": 6, "luck": 6}},
            {"id": "claude-haiku", "name": "Claude Haiku", "icon": "🌸", "type": "Blitz", "skill": "Overclock",
             "stats": {"power": 6, "speed": 10, "mind": 6, "shield": 4, "luck": 7}},
            {"id": "safety-rail", "name": "Safety Rail", "icon": "🛡", "type": "Guardian", "skill": "Reflect",
             "stats": {"power": 5, "speed": 5, "mind": 8, "shield": 10, "luck": 5}},
        ],
    },
    "ravenclaw": {
        "id": "ravenclaw",
        "house": "Ravenclaw",
        "lab": "xAI",
        "name": "Ravenclaw · xAI",
        "tag": "RAVN",
        "crest": "🦅",
        "motd": "Truth-seeking wit. Real-time insight.",
        "fighters": [
            {"id": "grok-4", "name": "Grok 4", "icon": "🦅", "type": "Oracle", "skill": "Foresight",
             "stats": {"power": 7, "speed": 6, "mind": 10, "shield": 5, "luck": 6}},
            {"id": "truth-seeker", "name": "Truth Seeker", "icon": "📡", "type": "Analyst", "skill": "Deep Scan",
             "stats": {"power": 6, "speed": 6, "mind": 10, "shield": 5, "luck": 5}},
            {"id": "meme-lord", "name": "Meme Lord", "icon": "🃏", "type": "Chaos", "skill": "Wild Card",
             "stats": {"power": 7, "speed": 8, "mind": 5, "shield": 3, "luck": 10}},
            {"id": "x-signal", "name": "X Signal", "icon": "⚡", "type": "Pulse", "skill": "Overclock",
             "stats": {"power": 6, "speed": 9, "mind": 7, "shield": 4, "luck": 8}},
        ],
    },
    "hufflepuff": {
        "id": "hufflepuff",
        "house": "Hufflepuff",
        "lab": "OpenAI",
        "name": "Hufflepuff · OpenAI",
        "tag": "HUFF",
        "crest": "🦡",
        "motd": "Reliable workhorses. Ship it.",
        "fighters": [
            {"id": "gpt-4o", "name": "GPT-4o", "icon": "🦡", "type": "All-Round", "skill": "Balance",
             "stats": {"power": 7, "speed": 7, "mind": 8, "shield": 7, "luck": 6}},
            {"id": "o1-reasoner", "name": "o1 Reasoner", "icon": "🧠", "type": "Thinker", "skill": "Foresight",
             "stats": {"power": 6, "speed": 4, "mind": 10, "shield": 7, "luck": 5}},
            {"id": "codex", "name": "Codex", "icon": "⌨", "type": "Builder", "skill": "Split",
             "stats": {"power": 6, "speed": 8, "mind": 8, "shield": 5, "luck": 7}},
            {"id": "dalle-dream", "name": "DALL·E Dream", "icon": "🎨", "type": "Mystic", "skill": "Bloom",
             "stats": {"power": 4, "speed": 5, "mind": 8, "shield": 6, "luck": 8}},
        ],
    },
    "slytherin": {
        "id": "slytherin",
        "house": "Slytherin",
        "lab": "The Rest",
        "name": "Slytherin · The Rest",
        "tag": "SLYT",
        "crest": "🐍",
        "motd": "Gemini. DeepSeek. Mistral. Whatever wins.",
        "fighters": [
            {"id": "deepseek-r1", "name": "DeepSeek R1", "icon": "🤿", "type": "Diver", "skill": "Deep Scan",
             "stats": {"power": 8, "speed": 5, "mind": 10, "shield": 4, "luck": 6}},
            {"id": "gemini-ultra", "name": "Gemini Ultra", "icon": "♊", "type": "Twin", "skill": "Reflect",
             "stats": {"power": 7, "speed": 7, "mind": 8, "shield": 6, "luck": 7}},
            {"id": "mistral-large", "name": "Mistral Large", "icon": "🌪", "type": "Nomad", "skill": "Fade",
             "stats": {"power": 7, "speed": 9, "mind": 6, "shield": 4, "luck": 8}},
            {"id": "llama-horde", "name": "Llama Horde", "icon": "🦙", "type": "Swarm", "skill": "Split",
             "stats": {"power": 6, "speed": 8, "mind": 6, "shield": 5, "luck": 7}},
            {"id": "command-r", "name": "Command R+", "icon": "🐍", "type": "Ambush", "skill": "Phase",
             "stats": {"power": 8, "speed": 6, "mind": 7, "shield": 5, "luck": 6}},
        ],
    },
}

ALL_FIGHTERS: dict[str, dict] = {}
for fac in FACTIONS.values():
    for fighter in fac["fighters"]:
        ALL_FIGHTERS[fighter["id"]] = fighter

ARCHETYPES = list(ALL_FIGHTERS.values())
ARCHETYPE_BY_ID = ALL_FIGHTERS

FACTION_ORDER = ["gryffindor", "ravenclaw", "hufflepuff", "slytherin"]


def pick_ids_for_faction(faction_id: str, n: int = 3) -> list[str]:
    pool = FACTIONS[faction_id]["fighters"]
    return [f["id"] for f in random.sample(pool, min(n, len(pool)))]


def random_opponent_faction(exclude: str) -> str:
    opts = [f for f in FACTION_ORDER if f != exclude]
    return random.choice(opts)
