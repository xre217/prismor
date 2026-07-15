// Solo campaign mode — uses NazoData from data.js

const { ARCHETYPES, ENEMY_NAMES, FLAVOR, cloneFighter, randomPick } = window.NazoData;

const state = {
  mode: "solo",
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

function $(id) { return document.getElementById(id); }

function showScreen(id) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.remove("active"));
  $(id).classList.add("active");
}

function log(msg, cls = "system") {
  const el = $("battle-log");
  if (!el) return;
  const line = document.createElement("div");
  line.className = cls;
  line.textContent = msg;
  el.appendChild(line);
  el.scrollTop = el.scrollHeight;
}

function statLine(s) {
  return `PWR ${s.power} · SPD ${s.speed} · MND ${s.mind} · SHD ${s.shield} · LCK ${s.luck}`;
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
    <div class="stats">${statLine(f.stats)}<br>${f.skillDesc || ""}</div>
  `;
  card.addEventListener("click", () => onClick(f, card));
  return card;
}

window.NazoSolo = { showScreen, renderFighterCard, log, $, state };

function startDraft() {
  state.mode = "solo";
  state.roster = [];
  state.pullIndex = 0;
  state.bench = [];
  showScreen("screen-draft");
  nextPull();
}

function nextPull() {
  $("pull-count").textContent = `${state.pullIndex + 1} / 3`;
  const pool = window.NazoData.ALL_FIGHTERS || ARCHETYPES;
  const options = randomPick(pool, 3);
  const container = $("draft-options");
  container.innerHTML = "";
  options.forEach((base) => {
    container.appendChild(renderFighterCard(base, (f) => {
      state.roster.push(cloneFighter(f));
      state.pullIndex++;
      if (state.pullIndex >= 3) finishDraft();
      else nextPull();
    }));
  });
  renderRosterPreview();
}

function renderRosterPreview() {
  const el = $("roster-preview");
  if (!state.roster.length) { el.innerHTML = ""; return; }
  el.innerHTML = `<h3>Your roster</h3><div class="roster-tags">${state.roster
    .map((f) => `<span class="roster-tag">${f.icon} ${f.name}</span>`).join("")}</div>`;
}

function finishDraft() {
  state.bench = [...state.roster];
  state.tier = 1;
  state.wins = 0;
  startBattle();
}

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
  if (!state.active) { endGame(false); return; }

  state.enemy = makeEnemy(state.tier);
  state.playerHp = state.active.currentHp;
  state.enemyHp = state.enemy.currentHp;
  state.maxHp = state.active.maxHp;
  state.guarding = { player: false, enemy: false };
  state.flags = { foresight: false, reflect: 0, dodge: false, deepScan: false };
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
  const bp = $("battle-passive");
  const bi = $("battle-intel");
  if (bp) bp.classList.add("hidden");
  if (bi) bi.classList.add("hidden");
}

function updateBattleUI() {
  $("player-sprite").textContent = state.active.icon;
  $("player-name").textContent = state.active.name;
  $("enemy-sprite").textContent = state.enemy.icon;
  $("enemy-name").textContent = state.enemy.name;
  $("player-hp").style.width = `${Math.max(0, (state.playerHp / state.maxHp) * 100)}%`;
  $("enemy-hp").style.width = `${Math.max(0, (state.enemyHp / state.enemy.maxHp) * 100)}%`;
  $("player-hp-text").textContent = `${Math.max(0, state.playerHp)} / ${state.maxHp}`;
  $("enemy-hp-text").textContent = `${Math.max(0, state.enemyHp)} / ${state.enemy.maxHp}`;
}

function setActionsEnabled(on) {
  document.querySelectorAll("#action-bar .btn.action").forEach((b) => { b.disabled = !on; });
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
      log(`${state.active.name} phases through!`, "player");
      state.enemyHp -= calcDamage(state.active, state.enemy, 0.8);
      animateHit("enemy");
      updateBattleUI();
      return;
    }
    if (state.flags.reflect > 0) {
      const reflected = Math.floor(amount * 1.5);
      state.enemyHp -= reflected;
      log(`Reflect ${reflected}!`, "crit");
      state.flags.reflect = 0;
    }
    state.playerHp -= amount;
    log(`${sourceName} hits for ${amount}`, "enemy");
    animateHit("player");
  } else {
    let dmg = amount;
    if (state.flags.foresight) { dmg *= 2; state.flags.foresight = false; log("Foresight ×2!", "crit"); }
    state.enemyHp -= dmg;
    log(`${sourceName} deals ${dmg}`, "player");
    animateHit("enemy");
  }
  updateBattleUI();
}

function enemyChooseAction() {
  const r = Math.random();
  if (state.playerHp < 30 && r < 0.35) return "strike";
  if (state.enemyHp < 25 && r < 0.4) return "guard";
  if (r < 0.15) return "chaos";
  if (r < 0.35) return "skill";
  if (r < 0.55) return "guard";
  return "strike";
}

function resolveAction(action, isPlayer) {
  const self = isPlayer ? state.active : state.enemy;
  const side = isPlayer ? "player" : "enemy";
  const name = self.name;
  const flavor = randomPick(FLAVOR[action] || FLAVOR.strike, 1)[0];

  if (isPlayer) state.guarding.player = false;
  else state.guarding.enemy = false;

  if (action === "guard") {
    if (isPlayer) state.guarding.player = true;
    else state.guarding.enemy = true;
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
    applyDamage(isPlayer ? "enemy" : "player", calcDamage(self, defender, 1, ignore), name, side);
    return;
  }
  if (action === "skill") {
    log(`${name}: ${self.skill}!`, side);
    runSkill(self, isPlayer);
    return;
  }
  if (action === "chaos") {
    const outcome = Math.random();
    if (outcome < 0.4) {
      applyDamage(isPlayer ? "enemy" : "player", calcDamage(self, { stats: isPlayer ? state.enemy.stats : state.active.stats, guarding: false }, 1.8), name, side);
    } else if (outcome < 0.7) {
      const d = Math.floor(8 + Math.random() * 15);
      if (isPlayer) { state.playerHp -= d; log(`Backfire ${d}`, "enemy"); }
      else { state.enemyHp -= d; log(`Implode ${d}!`, "player"); }
      updateBattleUI();
    } else log("Chaos fizzles.", "system");
  }
}

function runSkill(self, isPlayer) {
  const skill = self.skill;
  const s = state;
  if (skill === "Foresight") {
    if (isPlayer) s.flags.foresight = true;
    else applyDamage("player", calcDamage(self, { stats: s.active.stats, guarding: s.guarding.player }, 1.2), self.name, "enemy");
  } else if (skill === "Overclock") {
    for (let i = 0; i < 2; i++) {
      applyDamage(isPlayer ? "enemy" : "player", calcDamage(self, { stats: isPlayer ? s.enemy.stats : s.active.stats, guarding: isPlayer ? s.guarding.enemy : s.guarding.player }, 0.65), self.name, isPlayer ? "player" : "enemy");
    }
  } else if (skill === "Constitution" || skill === "Bulwark") {
    if (isPlayer) { s.playerHp = Math.min(s.maxHp, s.playerHp + 15); s.guarding.player = true; log("Bulwark +15", "player"); }
    else applyDamage("player", calcDamage(self, { stats: s.active.stats, guarding: s.guarding.player }, 1), self.name, "enemy");
    updateBattleUI();
  } else if (skill === "Reflect") {
    if (isPlayer) s.flags.reflect = 1;
    else applyDamage("player", calcDamage(self, { stats: s.active.stats, guarding: s.guarding.player }, 1), self.name, "enemy");
  } else if (skill === "Fade") {
    if (isPlayer) s.flags.dodge = true;
    else applyDamage("player", calcDamage(self, { stats: s.active.stats, guarding: s.guarding.player }, 1.1), self.name, "enemy");
  } else if (skill === "Deep Scan" || skill === "Precision") {
    if (isPlayer) s.flags.deepScan = true;
    else applyDamage("player", calcDamage(self, { stats: s.active.stats, guarding: false }, 0.9), self.name, "enemy");
  } else if (skill === "Wild Card") {
    if (Math.random() < 0.5) {
      applyDamage(isPlayer ? "enemy" : "player", calcDamage(self, { stats: { power: 10, speed: 8, mind: 5, shield: 0, luck: 10 }, guarding: false }, 1.5), self.name, isPlayer ? "player" : "enemy");
    } else {
      const d = 12;
      if (isPlayer) { s.playerHp -= d; log(`Wild Card fumble ${d}`, "enemy"); }
      else { s.enemyHp -= d; log(`Fumble ${d}!`, "player"); }
      updateBattleUI();
    }
  } else if (skill === "Split") {
    for (let i = 0; i < 3; i++) {
      let dmg = calcDamage(self, { stats: isPlayer ? s.enemy.stats : s.active.stats, guarding: isPlayer ? s.guarding.enemy : s.guarding.player }, 0.4);
      if (Math.random() < self.stats.luck * 0.08) { dmg *= 2; log("Micro-crit!", "crit"); }
      applyDamage(isPlayer ? "enemy" : "player", dmg, self.name, isPlayer ? "player" : "enemy");
    }
  } else if (skill === "Balance") {
    if (isPlayer) { s.playerHp = Math.min(s.maxHp, s.playerHp + 10); log("Balance +10", "player"); }
    else applyDamage("player", calcDamage(self, { stats: s.active.stats, guarding: s.guarding.player }, 1), self.name, "enemy");
    updateBattleUI();
  } else if (skill === "Phase") {
    applyDamage(isPlayer ? "enemy" : "player", calcDamage(self, { stats: isPlayer ? s.enemy.stats : s.active.stats, guarding: isPlayer ? s.guarding.enemy : s.guarding.player }, 1.2, 0.5), self.name, isPlayer ? "player" : "enemy");
  } else if (skill === "Bloom") {
    if (isPlayer) { s.playerHp = Math.min(s.maxHp, s.playerHp + 20); log("Bloom +20", "player"); }
    else applyDamage("player", calcDamage(self, { stats: s.active.stats, guarding: s.guarding.player }, 0.8), self.name, "enemy");
    updateBattleUI();
  } else {
    applyDamage(isPlayer ? "enemy" : "player", calcDamage(self, { stats: isPlayer ? s.enemy.stats : s.active.stats, guarding: isPlayer ? s.guarding.enemy : s.guarding.player }, 1.2), self.name, isPlayer ? "player" : "enemy");
  }
}

function checkBattleEnd() {
  if (state.enemyHp <= 0) {
    setActionsEnabled(false);
    state.wins++;
    state.active.currentHp = state.playerHp;
    log(`✦ ${state.enemy.name} down!`, "crit");
    if (state.tier >= 8) setTimeout(() => endGame(true), 800);
    else { state.tier++; setTimeout(() => startBattle(), 1200); }
    return true;
  }
  if (state.playerHp <= 0) {
    setActionsEnabled(false);
    state.active.alive = false;
    if (state.bench.filter((f) => f.alive).length) showSwap();
    else setTimeout(() => endGame(false), 800);
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
    container.appendChild(renderFighterCard(f, () => {
      state.active = f;
      state.playerHp = f.currentHp;
      state.maxHp = f.maxHp;
      $("swap-bar").classList.add("hidden");
      $("action-bar").style.display = "grid";
      log(`${f.name} enters!`, "player");
      updateBattleUI();
      setActionsEnabled(true);
    }));
  });
}

function onSoloAction(action) {
  if (state.mode !== "solo" || state.gameOver) return;
  setActionsEnabled(false);
  resolveAction(action, true);
  if (checkBattleEnd()) return;
  setTimeout(() => {
    if (state.gameOver) return;
    resolveAction(enemyChooseAction(), false);
    if (!checkBattleEnd()) setActionsEnabled(true);
  }, 600);
}

function endGame(won) {
  state.gameOver = true;
  $("result-art").textContent = won ? "🏆" : "📦";
  $("result-title").textContent = won ? "Arena Cleared" : "Box Closed";
  $("result-body").textContent = won
    ? `8 tiers cleared. ${state.wins} wins.`
    : `Fell at tier ${state.tier}. Pull again.`;
  showScreen("screen-result");
}

$("btn-start").addEventListener("click", startDraft);
$("btn-how").addEventListener("click", () => showScreen("screen-how"));
$("btn-how-back").addEventListener("click", () => showScreen("screen-title"));
$("btn-replay").addEventListener("click", () => showScreen("screen-title"));

document.querySelectorAll("#action-bar .btn.action").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (state.mode === "solo") onSoloAction(btn.dataset.action);
    else if (window.NazoMP) window.NazoMP.sendAction(btn.dataset.action);
  });
});
