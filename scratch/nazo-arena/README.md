# Nazo Arena

Browser roguelite battler with **four house guilds** and hidden System opponents.

## The four houses

| House | Lab | Fighters |
|-------|-----|----------|
| **Gryffindor** | Anthropic | Claude Opus, Sonnet, Haiku, Safety Rail |
| **Ravenclaw** | xAI | Grok 4, Truth Seeker, Meme Lord, X Signal |
| **Hufflepuff** | OpenAI | GPT-4o, o1 Reasoner, Codex, DALL·E Dream |
| **Slytherin** | The Rest | DeepSeek R1, Gemini Ultra, Mistral, Llama Horde, Command R+ |

## Ban / Pick draft

Guild wars use a short draft before duels:

1. **Ban** — each side bans 1 fighter from the opponent's house pool  
2. **Snake pick** — home / away / away / home / home / away into duel order (1→2→3)

System rivals draft with human-like delays. Idle ~22s auto-acts.

## House passives (guild wars)

| House | Passive | Effect |
|-------|---------|--------|
| **Gryffindor** | Courage | +10% damage when your fighter is below 30% HP |
| **Ravenclaw** | Insight | See opponent's last action each turn |
| **Hufflepuff** | Dedication | +5 HP when you Guard |
| **Slytherin** | Cunning | 15% chance to steal a successful Chaos hit |

Passives apply server-side in guild war duels. Your house passive shows above the battle UI.

## Play solo

```bash
cd scratch/nazo-arena
python3 -m http.server 8080
```

## Play multiplayer

```bash
pip install -r requirements.txt
python3 server/server.py          # terminal 1 — ws://localhost:8765
python3 -m http.server 8080         # terminal 2
```

**Guild Wars → Connect → Choose your house → Queue House War**

- Match another house when both are queued
- Wait ~4s alone → a **rival house** appears (may be the hidden System — never labeled)
- Draft 3 fighters from your house pool, best-of-3 duels

## Hidden System

When no rival house is online, the server spawns an opponent that **looks exactly like a real house guild** — same name, crest, member list, captain locking in rosters with delays. Players never see `is_system`.

## Relics

Unlock relics by winning house wars (40% drop chance for a new relic). Equip one at a time in the guild hall.

| Rarity | Examples |
|--------|----------|
| Common | Ember Sigil (strike burn), Iron Ward (+HP), Swift Quill (+Speed) |
| Uncommon | Scout Lens (open Focus), Viper Fang (chaos burn), Glass Heart (guard regen) |
| Rare | Crown Shard (+Power/Mind), Hourglass (guard cleanse), Ban Seal (first-pick HP) |
| Legendary | Oracle Coin (+8% damage + open Regen) |

New accounts start with **Iron Ward**. System rivals equip scaled relics by ELO.

## Territory map

Twelve regions on the castle grounds. Click a **rival or neutral** region in the guild hall, then queue — winner takes control.

| Region | Default | Bonus (wars) |
|--------|---------|--------------|
| Astronomy Tower / North Tower | Ravenclaw | +Mind / +HP |
| Gryffindor Tower | Gryffindor | +Power |
| Greenhouse | Hufflepuff | Open Regen each duel |
| Dungeons / Forbidden Forest | Slytherin | Chaos burn boost / strike Burn |
| Great Hall, Library, Owlery, … | Neutral | Mixed combat perks |

Owned lands stack mild bonuses in guild wars (**max 3**). Season rollover restores home defaults and clears neutrals.

## Seasons & leaderboard

Seasons last **7 days** by default (`NAZO_ARENA_SEASON_DAYS` to override).

On rollover:
- House ELO / W-L reset to 1000 / 0–0
- Champion house is archived
- Career stats and fighter mastery are kept

Guild hall board tabs:
- **Houses** — current season ELO standings
- **Captains** — top players by season war wins
- **Past** — closed season champions

## Status effects (guild wars)

| Status | Icon | Effect |
|--------|------|--------|
| **Burn** | 🔥 | 5 damage at turn start (2 turns) |
| **Stun** | 💫 | Skip next action |
| **Weaken** | 💔 | Shield halved (2 turns) |
| **Focus** | 🎯 | +30% damage on next attack |
| **Regen** | 💚 | +5 HP at turn start (2 turns) |

Sources include Chaos (burn), Phase/Deep Scan (weaken), Precision/Deep Scan/Foresight (focus), Bloom/Balance (regen), Reflect (stun chance), Constitution/Bloom (cleanse).

## Fighter mastery

XP on each fighter unlocks combat bonuses in guild wars:

| Tier | XP | Bonus |
|------|-----|-------|
| Rookie | 0 | — |
| Adept | 12 | +1 Power, +3 HP |
| Veteran | 36 | +1 Power, +1 Mind, +5 HP |
| Master | 72 | +2 Power, +1 Speed, +1 Mind, +8 HP |
| Legend | 120 | +2 Power, +1 Speed/Mind/Luck/Shield, +12 HP |

Earn XP by drafting and winning duels (+8 per duel win, +3 loss) plus a small war roster bonus. System rivals scale fake mastery with ELO.

## Persistence

Guild war results, house ELO, player records, and fighter mastery are stored in SQLite at `data/nazo-arena.db` (override with `NAZO_ARENA_DB`).

On connect, your account token is saved in browser `localStorage` so wars won and house allegiance survive refresh.

## Layout

```
scratch/nazo-arena/
├── data/                # SQLite (gitignored)
├── factions.js          # House data + fighters (client)
├── server/factions.py   # Same four houses (server)
├── server/store.py      # SQLite persistence
├── server/server.py     # WebSocket + matchmaking
└── ...
```

Pure fiction / parody. Not affiliated with HP, Anthropic, OpenAI, xAI, or anyone else.
