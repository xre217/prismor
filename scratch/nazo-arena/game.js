// Nazo Arena — mystery-box AI fighter battler

const ARCHETYPES = [
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
  { id: "sage", name: "The Sage", icon: "📜", type: "Harmony", skill: "Balance", skillDesc: "Swap your lowest & highest stat for 2 turns.",
    stats: { power: 6, speed: 6, mind: 8, shield: 8, luck: 5 } },
  { id: "wraith", name: "The Wraith", icon: "👻", type: "Phantom", skill: "Phase", skillDesc: "Strike ignores 50% of shield.",
    stats: { power: 8, speed: 7, mind: 6, shield: 3, luck: 6 } },
  { id: "forge", name: "The Forge", icon: "🔥", type: "Berserker", skill: "Meltdown", skillDesc: "Massive hit but lose 10 HP.",
    stats: { power: 10, speed: 4, mind: 3, shield: 6, luck: 5 } },
  { id: "lotus", name: "The Lotus", icon: "🪷", type: "Mystic", skill: "Bloom", skillDesc: "Heal 20 HP; skip attack.",
    stats: { power: 4, speed: 5, mind: 9, shield: 7, luck: 8 } },
];

const ENEMY_NAMES = [
  "Rust Bot", "Paperclip MAX", "Hallucination Engine", "Context Window Ghoul",
  "Prompt Leak Drone", "Benchmark Farmer", "Token Burner", "Alignment Theater",
  "Slop Generator", "Fine-Tune Fraud", "GPU Gremlin", "Latency Lord",
];

const FLAVOR = {
  strike: ["slams a logits haymaker", "drops a gradient on your head", "fine-tunes your face off"],
  guard: ["raises a safety rail", "enters RLHF turtle mode", "deploys constitutional armor"],
  skill: ["unleashes signature move", "activates hidden weights", "runs the special forward pass"],
  chaos: ["rolls the dice on alignment", "prompts with zero shot discipline", "YOLOs the inference"],
};

const state = {
  roster: [],
  bench: [],
  active: null,
  enemy: null,
  tier: 1,
  wins: 0,
  pullIndex: 0,
  playerHp: 100,
  enemyHp: 100,
  maxHp: 100,
  guarding: { player: false, enemy: false },
  flags: { foresight: false, reflect: 0, dodge: false, deepScan: false },
  lastDamageToPlayer: 0,
  gameOver: false,
};

// --- UI helpers ---

function $(id) { return document.getElementById(id); }

function showScreen(id) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.remove("active"));
  $(id).classList.add("active");
}

function log(msg, cls = "system") {
  const el = $("battle-log");
  const line = document.createElement("div");
  line.className = cls;
  line.textContent = msg;
  el.appendChild(line);
  el.scrollTop = el.scrollHeight;
}

function statLine(s) {
  return `PWR ${s.power} · SPD ${s.speed} · MND ${s.mind} · SHD ${s.shield} · LCK ${s.luck}`;
}

function cloneFighter(base) {
  return {
    ...base,
    stats: { ...base.stats },
    currentHp: 100,
    maxHp: 100,
    alive: true,
  };
}

function randomPick(arr, n) {
  const copy = [...arr];
  const out = [];
  while (out.length < n && copy.length) {
    const i = Math.floor(Math.random() * copy.length);
    out.push(copy.splice(i, 1)[0]);
  }
  return out;
}

function roll(luck) {
  return Math.random() * 10 + luck * 0.5;
}

function calcDamage(attacker, defender, mult = 1, ignoreShield = 0) {
  const atk = attacker.stats.power + roll(attacker.stats.luck) * 0.3;
  const def = defender.stats.shield * (defender.guarding ? 1.5 : 1) * (1 - ignoreShield);
  return Math.max(3, Math.floor((atk - def * 0.4 + attacker.stats.speed * 0.2) * mult));
}

function renderFighterCard(f, onClick) {
  const card = document.createElement("div");
  card.className = "fighter-card";
  card.innerHTML = `
    <div class="icon">${f.icon}</div>
    <div class="cname">${f.name}</div>
    <div class="ctype">${f.type} · ${f.skill}</div>
    <div class="stats">${statLine(f.stats)}<br>${f.skillDesc}</div>
  `;
  card.addEventListener("click", () => onClick(f, card));
  return card;
}

// --- Draft ---

function startDraft() {
  state.roster = [];
  state.pullIndex = 0;
  state.bench = [];
  showScreen("screen-draft");
  nextPull();
}

function nextPull() {
  $("pull-count").textContent = `${state.pullIndex + 1} / 3`;
  const options = randomPick(ARCHETYPES, 3);
  const container = $("draft-options");
  container.innerHTML = "";

  options.forEach((base) => {
    const card = renderFighterCard(base, (f) => {
      state.roster.push(cloneFighter(f));
      state.pullIndex++;
      if (state.pullIndex >= 3) {
        finishDraft();
      } else {
        nextPull();
      }
    });
    container.appendChild(card);
  });

  renderRosterPreview();
}

function renderRosterPreview() {
  const el = $("roster-preview");
  if (!state.roster.length) {
    el.innerHTML = "";
    return;
  }
  el.innerHTML = `<h3>Your roster</h3><div class="roster-tags">${state.roster
    .map((f) => `<span class="roster-tag">${f.icon} ${f.name}</span>`)
    .join("")}</div>`;
}

function finishDraft() {
  state.bench = [...state.roster];
  state.tier = 1;
  state.wins = 0;
  startBattle();
}

// --- Battle ---

function makeEnemy(tier) {
  const base = cloneFighter(randomPick(ARCHETYPES, 1)[0]);
  const scale = 1 + (tier - 1) * 0.12;
  for (const k of Object.keys(base.stats)) {
    base.stats[k] = Math.min(10, Math.floor(base.stats[k] * scale));
  }
  base.name = ENEMY_NAMES[(tier - 1) % ENEMY_NAMES.length];
  base.icon = ["💀", "👾", "🤖", "☠", "🎭", "🧟", "👹", "🦾"][(tier - 1) % 8];
  base.currentHp = 100 + (tier - 1) * 8;
  base.maxHp = base.currentHp;
  return base;
}

function startBattle() {
  if (!state.active || !state.active.alive) {
    state.active = state.bench.find((f) => f.alive) || null;
  }
  if (!state.active) {
    endGame(false);
    return;
  }

  state.enemy = makeEnemy(state.tier);
  state.playerHp = state.active.currentHp;
  state.enemyHp = state.enemy.currentHp;
  state.maxHp = state.active.maxHp;
  state.guarding = { player: false, enemy: false };
  state.flags = { foresight: false, reflect: 0, dodge: false, deepScan: false };
  state.lastDamageToPlayer = 0;
  state.gameOver = false;

  $("tier-label").textContent = `Tier ${state.tier}`;
  $("score-label").textContent = `Wins: ${state.wins}`;
  $("battle-log").innerHTML = "";
  $("swap-bar").classList.add("hidden");
  $("action-bar").style.display = "grid";

  updateBattleUI();
  log(`— Tier ${state.tier}: ${state.active.name} vs ${state.enemy.name} —`);
  setActionsEnabled(true);
  showScreen("screen-battle");
}

function updateBattleUI() {
  $("player-sprite").textContent = state.active.icon;
  $("player-name").textContent = state.active.name;
  $("enemy-sprite").textContent = state.enemy.icon;
  $("enemy-name").textContent = state.enemy.name;

  const pPct = (state.playerHp / state.maxHp) * 100;
  const ePct = (state.enemyHp / state.enemy.maxHp) * 100;
  $("player-hp").style.width = `${Math.max(0, pPct)}%`;
  $("enemy-hp").style.width = `${Math.max(0, ePct)}%`;
  $("player-hp-text").textContent = `${Math.max(0, state.playerHp)} / ${state.maxHp}`;
  $("enemy-hp-text").textContent = `${Math.max(0, state.enemyHp)} / ${state.enemy.maxHp}`;
}

function setActionsEnabled(on) {
  document.querySelectorAll(".btn.action").forEach((b) => { b.disabled = !on; });
}

function animateHit(side) {
  const el = side === "player" ? $("player-sprite") : $("enemy-sprite");
  el.classList.remove("hit");
  void el.offsetWidth;
  el.classList.add("hit");
}

function animateAttack(side) {
  const el = side === "player" ? $("player-sprite") : $("enemy-sprite");
  el.classList.remove("attack");
  void el.offsetWidth;
  el.classList.add("attack");
}

function applyDamage(target, amount, sourceName, side) {
  if (target === "player") {
    if (state.flags.dodge) {
      state.flags.dodge = false;
      log(`${state.active.name} phases through the hit!`, "player");
      const counter = calcDamage(state.active, state.enemy, 0.8);
      state.enemyHp -= counter;
      log(`Counter for ${counter} damage!`, "player");
      animateHit("enemy");
      return;
    }
    if (state.flags.reflect > 0) {
      const reflected = Math.floor(amount * 1.5);
      state.enemyHp -= reflected;
      log(`${state.active.name} reflects ${reflected} damage!`, "crit");
      state.flags.reflect = 0;
    }
    state.playerHp -= amount;
    state.lastDamageToPlayer = amount;
    log(`${sourceName} hits for ${amount}`, "enemy");
    animateHit("player");
  } else {
    let dmg = amount;
    if (state.flags.foresight) {
      dmg *= 2;
      state.flags.foresight = false;
      log("Foresight! Double damage!", "crit");
    }
    state.enemyHp -= dmg;
    log(`${sourceName} deals ${dmg} damage`, "player");
    animateHit("enemy");
  }
  updateBattleUI();
}

function enemyChooseAction() {
  const e = state.enemy;
  const r = Math.random();
  if (state.playerHp < 30 && r < 0.35) return "strike";
  if (state.enemyHp < 25 && r < 0.4) return "guard";
  if (r < 0.15) return "chaos";
  if (r < 0.35) return "skill";
  if (r < 0.55) return "guard";
  return "strike";
}

function resolveAction(actor, action, isPlayer) {
  const target = isPlayer ? state.enemy : state.active;
  const self = isPlayer ? state.active : state.enemy;
  const side = isPlayer ? "player" : "enemy";
  const name = self.name;
  const flavor = randomPick(FLAVOR[action] || FLAVOR.strike, 1)[0];

  actor.guarding = false;

  if (action === "guard") {
    actor.guarding = true;
    log(`${name} ${flavor}.`, side);
    return;
  }

  if (action === "strike") {
    animateAttack(side);
    const ignore = state.flags.deepScan && isPlayer ? 0.5 : 0;
    if (isPlayer && state.flags.deepScan) state.flags.deepScan = false;
    const defender = isPlayer
      ? { stats: state.enemy.stats, guarding: state.guarding.enemy }
      : { stats: state.active.stats, guarding: state.guarding.player };
    const dmg = calcDamage(self, defender, 1, ignore);
    applyDamage(isPlayer ? "enemy" : "player", dmg, name, side);
    return;
  }

  if (action === "skill") {
    log(`${name} ${flavor}: ${self.skill}!`, side);
    runSkill(self, isPlayer);
    return;
  }

  if (action === "chaos") {
    log(`${name} ${flavor}...`, side);
    const outcome = Math.random();
    if (outcome < 0.4) {
      const dmg = calcDamage(self, { stats: isPlayer ? state.enemy.stats : state.active.stats, guarding: false }, 1.8);
      applyDamage(isPlayer ? "enemy" : "player", dmg, name, side);
    } else if (outcome < 0.7) {
      const selfDmg = Math.floor(8 + Math.random() * 15);
      if (isPlayer) {
        state.playerHp -= selfDmg;
        log(`Backfire! ${selfDmg} self-damage`, "enemy");
      } else {
        state.enemyHp -= selfDmg;
        log(`Enemy implodes for ${selfDmg}!`, "player");
      }
      updateBattleUI();
    } else {
      log("Nothing happens. Classic chaos.", "system");
    }
  }
}

function runSkill(self, isPlayer) {
  const id = self.id;
  if (id === "oracle") {
    if (isPlayer) state.flags.foresight = true;
    else applyDamage("player", calcDamage(self, { stats: state.active.stats, guarding: state.guarding.player }, 1.2), self.name, "enemy");
  } else if (id === "spark") {
    for (let i = 0; i < 2; i++) {
      const dmg = calcDamage(self, { stats: isPlayer ? state.enemy.stats : state.active.stats, guarding: isPlayer ? state.guarding.enemy : state.guarding.player }, 0.65);
      applyDamage(isPlayer ? "enemy" : "player", dmg, self.name, isPlayer ? "player" : "enemy");
    }
  } else if (id === "titan") {
    if (isPlayer) {
      state.playerHp = Math.min(state.maxHp, state.playerHp + 15);
      state.guarding.player = true;
      log("Bulwark: +15 HP, guarding", "player");
    } else {
      applyDamage("player", calcDamage(self, { stats: state.active.stats, guarding: state.guarding.player }, 1), self.name, "enemy");
    }
    updateBattleUI();
  } else if (id === "mirror") {
    if (isPlayer) state.flags.reflect = 1;
    else applyDamage("player", calcDamage(self, { stats: state.active.stats, guarding: state.guarding.player }, 1), self.name, "enemy");
  } else if (id === "nomad") {
    if (isPlayer) state.flags.dodge = true;
    else applyDamage("player", calcDamage(self, { stats: state.active.stats, guarding: state.guarding.player }, 1.1), self.name, "enemy");
  } else if (id === "diver") {
    if (isPlayer) state.flags.deepScan = true;
    else applyDamage("player", calcDamage(self, { stats: state.active.stats, guarding: false }, 0.9), self.name, "enemy");
  } else if (id === "jester") {
    if (Math.random() < 0.5) {
      applyDamage(isPlayer ? "enemy" : "player", calcDamage(self, { stats: { power: 10, speed: 8, mind: 5, shield: 0, luck: 10 }, guarding: false }, 1.5), self.name, isPlayer ? "player" : "enemy");
    } else {
      const d = 12;
      if (isPlayer) { state.playerHp -= d; log(`Jester fumbles for ${d}`, "enemy"); }
      else { state.enemyHp -= d; log(`Enemy jester fumbles for ${d}`, "player"); }
      updateBattleUI();
    }
  } else if (id === "atom") {
    for (let i = 0; i < 3; i++) {
      let dmg = calcDamage(self, { stats: isPlayer ? state.enemy.stats : state.active.stats, guarding: isPlayer ? state.guarding.enemy : state.guarding.player }, 0.4);
      if (Math.random() < self.stats.luck * 0.08) { dmg *= 2; log("Micro-crit!", "crit"); }
      applyDamage(isPlayer ? "enemy" : "player", dmg, self.name, isPlayer ? "player" : "enemy");
    }
  } else if (id === "sage") {
    if (isPlayer) {
      state.playerHp = Math.min(state.maxHp, state.playerHp + 10);
      log("Balance: +10 HP", "player");
    } else applyDamage("player", calcDamage(self, { stats: state.active.stats, guarding: state.guarding.player }, 1), self.name, "enemy");
    updateBattleUI();
  } else if (id === "wraith") {
    applyDamage(isPlayer ? "enemy" : "player", calcDamage(self, { stats: isPlayer ? state.enemy.stats : state.active.stats, guarding: isPlayer ? state.guarding.enemy : state.guarding.player }, 1.2, 0.5), self.name, isPlayer ? "player" : "enemy");
  } else if (id === "forge") {
    const dmg = calcDamage(self, { stats: isPlayer ? state.enemy.stats : state.active.stats, guarding: false }, 2);
    applyDamage(isPlayer ? "enemy" : "player", dmg, self.name, isPlayer ? "player" : "enemy");
    if (isPlayer) { state.playerHp -= 10; log("Meltdown recoil: 10", "enemy"); }
    else { state.enemyHp -= 10; }
    updateBattleUI();
  } else if (id === "lotus") {
    if (isPlayer) {
      state.playerHp = Math.min(state.maxHp, state.playerHp + 20);
      log("Bloom: +20 HP", "player");
    } else applyDamage("player", calcDamage(self, { stats: state.active.stats, guarding: state.guarding.player }, 0.8), self.name, "enemy");
    updateBattleUI();
  } else {
    applyDamage(isPlayer ? "enemy" : "player", calcDamage(self, { stats: isPlayer ? state.enemy.stats : state.active.stats, guarding: isPlayer ? state.guarding.enemy : state.guarding.player }, 1.2), self.name, isPlayer ? "player" : "enemy");
  }
}

function checkBattleEnd() {
  if (state.enemyHp <= 0) {
    setActionsEnabled(false);
    state.wins++;
    state.active.currentHp = state.playerHp;
    log(`✦ ${state.enemy.name} defeated!`, "crit");
    if (state.tier >= 8) {
      setTimeout(() => endGame(true), 800);
    } else {
      state.tier++;
      setTimeout(() => startBattle(), 1200);
    }
    return true;
  }
  if (state.playerHp <= 0) {
    setActionsEnabled(false);
    state.active.alive = false;
    state.active.currentHp = 0;
    log(`✦ ${state.active.name} is down!`, "enemy");
    const remaining = state.bench.filter((f) => f.alive);
    if (remaining.length) {
      showSwap();
    } else {
      setTimeout(() => endGame(false), 800);
    }
    return true;
  }
  return false;
}

function showSwap() {
  $("action-bar").style.display = "none";
  $("swap-bar").classList.remove("hidden");
  const container = $("swap-options");
  container.innerHTML = "";
  state.bench.filter((f) => f.alive).forEach((f) => {
    const card = renderFighterCard(f, () => {
      state.active = f;
      state.playerHp = f.currentHp;
      state.maxHp = f.maxHp;
      $("swap-bar").classList.add("hidden");
      $("action-bar").style.display = "grid";
      log(`${f.name} enters the arena!`, "player");
      updateBattleUI();
      setActionsEnabled(true);
    });
    container.appendChild(card);
  });
}

function onPlayerAction(action) {
  if (state.gameOver) return;
  setActionsEnabled(false);
  state.guarding.player = false;

  resolveAction({ guarding: false }, action, true);

  if (checkBattleEnd()) return;

  setTimeout(() => {
    if (state.gameOver) return;
    const enemyAction = enemyChooseAction();
    state.guarding.enemy = false;
    resolveAction({ guarding: false }, enemyAction, false);
    if (!checkBattleEnd()) setActionsEnabled(true);
  }, 600);
}

function endGame(won) {
  state.gameOver = true;
  $("result-art").textContent = won ? "🏆" : "📦";
  $("result-title").textContent = won ? "Arena Cleared" : "Box Closed";
  $("result-body").textContent = won
    ? `You ran all 8 tiers with ${state.wins} wins. The mystery box respects you.`
    : `Fell at tier ${state.tier}. Wins: ${state.wins}. Pull again.`;
  showScreen("screen-result");
}

// --- Init ---

$("btn-start").addEventListener("click", startDraft);
$("btn-how").addEventListener("click", () => showScreen("screen-how"));
$("btn-how-back").addEventListener("click", () => showScreen("screen-title"));
$("btn-replay").addEventListener("click", () => showScreen("screen-title"));

document.querySelectorAll(".btn.action").forEach((btn) => {
  btn.addEventListener("click", () => onPlayerAction(btn.dataset.action));
});
