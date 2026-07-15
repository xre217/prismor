# Nazo Arena

Browser roguelite battler — pull AI fighters from the mystery box and fight through 8 arena tiers.

## Play

Open `index.html` in a browser, or:

```bash
cd scratch/nazo-arena
python3 -m http.server 8080
# → http://localhost:8080
```

## Loop

1. **Draft** — 3 mystery pulls, pick one fighter each time (12 archetypes).
2. **Fight** — turn-based: Strike, Guard, Skill, or Chaos.
3. **Survive** — 8 tiers, scaling enemies. Swap bench fighters when one falls.

## Fighters

| Name | Type | Skill |
|------|------|-------|
| The Oracle | Seer | Foresight — next hit ×2 |
| The Spark | Blitz | Overclock — double tap |
| The Titan | Fortress | Bulwark — heal + guard |
| The Mirror | Copycat | Reflect — return damage |
| The Nomad | Rogue | Fade — dodge + counter |
| The Diver | Analyst | Deep Scan — pierce guard |
| The Jester | Chaos | Wild Card — boom or bust |
| The Atom | Swarm | Split — triple micro-hits |
| The Sage | Harmony | Balance — heal |
| The Wraith | Phantom | Phase — shield pierce |
| The Forge | Berserker | Meltdown — huge hit, recoil |
| The Lotus | Mystic | Bloom — big heal |

Pure fiction. No real models, no geopolitics — just arena nonsense.
