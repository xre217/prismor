// Shared fighter data for solo + multiplayer
window.NazoData = {
  ARCHETYPES: [
    { id: "oracle", name: "The Oracle", icon: "🔮", type: "Seer", skill: "Foresight", skillDesc: "Next hit deals double damage.",
      stats: { power: 6, speed: 5, mind: 9, shield: 6, luck: 5 } },
    { id: "spark", name: "The Spark", icon: "⚡", type: "Blitz", skill: "Overclock", skillDesc: "Two quick strikes.",
      stats: { power: 7, speed: 10, mind: 4, shield: 3, luck: 6 } },
    { id: "titan", name: "The Titan", icon: "🗿", type: "Fortress", skill: "Bulwark", skillDesc: "Heal 15 HP and gain guard.",
      stats: { power: 8, speed: 3, mind: 5, shield: 10, luck: 4 } },
    { id: "mirror", name: "The Mirror", icon: "🪞", type: "Copycat", skill: "Reflect", skillDesc: "Return last damage taken ×1.5.",
      stats: { power: 5, speed: 6, mind: 8, shield: 7, luck: 7 } },
    { id: "nomad", name: "The Nomad", icon: "🏜", type: "Rogue", skill: "Fade", skillDesc: "Dodge next attack, then counter.",
      stats: { power: 6, speed: 9, mind: 6, shield: 4, luck: 8 } },
    { id: "diver", name: "The Diver", icon: "🤿", type: "Analyst", skill: "Deep Scan", skillDesc: "Ignore enemy guard this turn.",
      stats: { power: 7, speed: 5, mind: 10, shield: 5, luck: 4 } },
    { id: "jester", name: "The Jester", icon: "🃏", type: "Chaos", skill: "Wild Card", skillDesc: "Random huge buff or self-hit.",
      stats: { power: 6, speed: 7, mind: 5, shield: 4, luck: 10 } },
    { id: "atom", name: "The Atom", icon: "⚛", type: "Swarm", skill: "Split", skillDesc: "Three micro-hits, each can crit.",
      stats: { power: 4, speed: 8, mind: 7, shield: 5, luck: 9 } },
    { id: "sage", name: "The Sage", icon: "📜", type: "Harmony", skill: "Balance", skillDesc: "Heal and stabilize.",
      stats: { power: 6, speed: 6, mind: 8, shield: 8, luck: 5 } },
    { id: "wraith", name: "The Wraith", icon: "👻", type: "Phantom", skill: "Phase", skillDesc: "Strike ignores 50% of shield.",
      stats: { power: 8, speed: 7, mind: 6, shield: 3, luck: 6 } },
    { id: "forge", name: "The Forge", icon: "🔥", type: "Berserker", skill: "Meltdown", skillDesc: "Massive hit but lose 10 HP.",
      stats: { power: 10, speed: 4, mind: 3, shield: 6, luck: 5 } },
    { id: "lotus", name: "The Lotus", icon: "🪷", type: "Mystic", skill: "Bloom", skillDesc: "Heal 20 HP; skip attack.",
      stats: { power: 4, speed: 5, mind: 9, shield: 7, luck: 8 } },
  ],

  ENEMY_NAMES: [
    "Rust Bot", "Paperclip MAX", "Hallucination Engine", "Context Window Ghoul",
    "Prompt Leak Drone", "Benchmark Farmer", "Token Burner", "Alignment Theater",
  ],

  FLAVOR: {
    strike: ["slams a logits haymaker", "drops a gradient on your head", "fine-tunes your face off"],
    guard: ["raises a safety rail", "enters RLHF turtle mode", "deploys constitutional armor"],
    skill: ["unleashes signature move", "activates hidden weights", "runs the special forward pass"],
    chaos: ["rolls the dice on alignment", "prompts with zero shot discipline", "YOLOs the inference"],
  },

  byId(id) {
    return this.ARCHETYPES.find((a) => a.id === id);
  },

  cloneFighter(base) {
    return {
      ...base,
      stats: { ...base.stats },
      currentHp: 100,
      maxHp: 100,
      alive: true,
    };
  },

  randomPick(arr, n) {
    const copy = [...arr];
    const out = [];
    while (out.length < n && copy.length) {
      const i = Math.floor(Math.random() * copy.length);
      out.push(copy.splice(i, 1)[0]);
    }
    return out;
  },
};
