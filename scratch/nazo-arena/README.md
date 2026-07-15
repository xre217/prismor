# Nazo Arena

Browser roguelite battler with **guild wars multiplayer**. Rivals look like real guilds — member lists, captains, ELO. Some of them aren't what they seem (the server never tells).

## Play solo

Open `index.html` or:

```bash
cd scratch/nazo-arena
python3 -m http.server 8080
# → http://localhost:8080
```

## Play multiplayer

Terminal 1 — arena server:

```bash
cd scratch/nazo-arena
pip install -r requirements.txt
python3 server/server.py
# ws://localhost:8765
```

Terminal 2 — static files:

```bash
cd scratch/nazo-arena
python3 -m http.server 8080
```

Then **Guild Wars → Connect → Create guild → Queue Guild War**.

Open a second browser tab/window to test human-vs-human, or queue alone and a "rival guild" appears after ~4 seconds.

## Guild war flow

1. Pick a callsign and connect
2. Create or join a guild (share invite code)
3. Queue for war — matchmaking finds another guild or fills with an opponent that looks human
4. Draft 3 fighters (same mystery pulls as solo)
5. Best-of-3 duels — turn-based Strike / Guard / Skill / Chaos
6. ELO updates; back to guild hall

## The hidden layer

Server-side only (`server/system_guilds.py`):

- Synthetic guilds with believable names, tags, member rosters, and "last seen" timestamps
- Captains lock rosters after human-like delays
- Turns use think-time jitter before acting
- **Clients never receive `is_system`** — opponents always look like player guilds

Real human guilds can match each other when two are queued.

## Layout

```
scratch/nazo-arena/
├── index.html       # UI
├── data.js          # Fighter archetypes
├── game.js          # Solo campaign
├── multiplayer.js   # Guild client
├── server/
│   ├── server.py           # WebSocket + matchmaking
│   ├── battle_engine.py    # Server-side duels
│   └── system_guilds.py    # Hidden opponent profiles
└── requirements.txt
```

## Fighters

12 archetypes — The Oracle, The Spark, The Titan, The Mirror, The Nomad, The Diver, The Jester, The Atom, The Sage, The Wraith, The Forge, The Lotus. Pure fiction.
