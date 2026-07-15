// Shared fighter data — base helpers; factions.js defines fighters
window.NazoData = {
  ARCHETYPES: [],
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
  cloneFighter(base) {
    return { ...base, stats: { ...base.stats }, currentHp: 100, maxHp: 100, alive: true };
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
