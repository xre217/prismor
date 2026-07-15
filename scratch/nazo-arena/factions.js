// Four houses — AI lab factions for guild wars

window.NazoData.FACTIONS = {
  gryffindor: {
    id: "gryffindor",
    house: "Gryffindor",
    lab: "Anthropic",
    tag: "GRYF",
    crest: "🦁",
    color: "#ae0001",
    accent: "#d3a625",
    motto: "Bold reasoning. Constitutional courage.",
    passiveName: "Courage",
    passiveDesc: "+10% damage when your fighter is below 30% HP.",
    fighters: [
      { id: "claude-opus", name: "Claude Opus", icon: "🦁", type: "Champion", skill: "Constitution", skillDesc: "Heal 15 HP and guard — safety first.",
        stats: { power: 7, speed: 5, mind: 9, shield: 9, luck: 5 } },
      { id: "claude-sonnet", name: "Claude Sonnet", icon: "⚔", type: "Duelist", skill: "Precision", skillDesc: "Next strike pierces 50% shield.",
        stats: { power: 7, speed: 7, mind: 8, shield: 6, luck: 6 } },
      { id: "claude-haiku", name: "Claude Haiku", icon: "🌸", type: "Blitz", skill: "Overclock", skillDesc: "Two quick strikes.",
        stats: { power: 6, speed: 10, mind: 6, shield: 4, luck: 7 } },
      { id: "safety-rail", name: "Safety Rail", icon: "🛡", type: "Guardian", skill: "Reflect", skillDesc: "Return last damage ×1.5.",
        stats: { power: 5, speed: 5, mind: 8, shield: 10, luck: 5 } },
    ],
  },
  ravenclaw: {
    id: "ravenclaw",
    house: "Ravenclaw",
    lab: "xAI",
    tag: "RAVN",
    crest: "🦅",
    color: "#0e1a40",
    accent: "#946b2d",
    motto: "Truth-seeking wit. Real-time insight.",
    passiveName: "Insight",
    passiveDesc: "See the opponent's last action each turn.",
    fighters: [
      { id: "grok-4", name: "Grok 4", icon: "🦅", type: "Oracle", skill: "Foresight", skillDesc: "Next hit deals double damage.",
        stats: { power: 7, speed: 6, mind: 10, shield: 5, luck: 6 } },
      { id: "truth-seeker", name: "Truth Seeker", icon: "📡", type: "Analyst", skill: "Deep Scan", skillDesc: "Ignore enemy guard this turn.",
        stats: { power: 6, speed: 6, mind: 10, shield: 5, luck: 5 } },
      { id: "meme-lord", name: "Meme Lord", icon: "🃏", type: "Chaos", skill: "Wild Card", skillDesc: "Huge hit or self-damage.",
        stats: { power: 7, speed: 8, mind: 5, shield: 3, luck: 10 } },
      { id: "x-signal", name: "X Signal", icon: "⚡", type: "Pulse", skill: "Overclock", skillDesc: "Two quick strikes.",
        stats: { power: 6, speed: 9, mind: 7, shield: 4, luck: 8 } },
    ],
  },
  hufflepuff: {
    id: "hufflepuff",
    house: "Hufflepuff",
    lab: "OpenAI",
    tag: "HUFF",
    crest: "🦡",
    color: "#372e29",
    accent: "#ecb939",
    motto: "Reliable workhorses. Ship it.",
    passiveName: "Dedication",
    passiveDesc: "Recover 5 HP when you Guard.",
    fighters: [
      { id: "gpt-4o", name: "GPT-4o", icon: "🦡", type: "All-Round", skill: "Balance", skillDesc: "Heal 10 HP.",
        stats: { power: 7, speed: 7, mind: 8, shield: 7, luck: 6 } },
      { id: "o1-reasoner", name: "o1 Reasoner", icon: "🧠", type: "Thinker", skill: "Foresight", skillDesc: "Next hit ×2 damage.",
        stats: { power: 6, speed: 4, mind: 10, shield: 7, luck: 5 } },
      { id: "codex", name: "Codex", icon: "⌨", type: "Builder", skill: "Split", skillDesc: "Three micro-hits.",
        stats: { power: 6, speed: 8, mind: 8, shield: 5, luck: 7 } },
      { id: "dalle-dream", name: "DALL·E Dream", icon: "🎨", type: "Mystic", skill: "Bloom", skillDesc: "Heal 20 HP.",
        stats: { power: 4, speed: 5, mind: 8, shield: 6, luck: 8 } },
    ],
  },
  slytherin: {
    id: "slytherin",
    house: "Slytherin",
    lab: "The Rest",
    tag: "SLYT",
    crest: "🐍",
    color: "#1a472a",
    accent: "#aaaaaa",
    motto: "Gemini. DeepSeek. Mistral. Whatever wins.",
    passiveName: "Cunning",
    passiveDesc: "15% chance to steal a successful Chaos hit.",
    fighters: [
      { id: "deepseek-r1", name: "DeepSeek R1", icon: "🤿", type: "Diver", skill: "Deep Scan", skillDesc: "Pierce guard.",
        stats: { power: 8, speed: 5, mind: 10, shield: 4, luck: 6 } },
      { id: "gemini-ultra", name: "Gemini Ultra", icon: "♊", type: "Twin", skill: "Reflect", skillDesc: "Return damage ×1.5.",
        stats: { power: 7, speed: 7, mind: 8, shield: 6, luck: 7 } },
      { id: "mistral-large", name: "Mistral Large", icon: "🌪", type: "Nomad", skill: "Fade", skillDesc: "Dodge then counter.",
        stats: { power: 7, speed: 9, mind: 6, shield: 4, luck: 8 } },
      { id: "llama-horde", name: "Llama Horde", icon: "🦙", type: "Swarm", skill: "Split", skillDesc: "Triple micro-hits.",
        stats: { power: 6, speed: 8, mind: 6, shield: 5, luck: 7 } },
      { id: "command-r", name: "Command R+", icon: "🐍", type: "Ambush", skill: "Phase", skillDesc: "Pierce 50% shield on strike.",
        stats: { power: 8, speed: 6, mind: 7, shield: 5, luck: 6 } },
    ],
  },
};

// Flat lookup for server parity + solo fallback
window.NazoData.ALL_FIGHTERS = Object.values(window.NazoData.FACTIONS)
  .flatMap((f) => f.fighters);

window.NazoData.ARCHETYPES = window.NazoData.ALL_FIGHTERS;

window.NazoData.factionById = function (id) {
  return Object.values(this.FACTIONS).find((f) => f.id === id);
};

window.NazoData.fightersForFaction = function (factionId) {
  const f = this.FACTIONS[factionId];
  return f ? f.fighters : this.ALL_FIGHTERS;
};

window.NazoData.byId = function (id) {
  return this.ALL_FIGHTERS.find((a) => a.id === id);
};
