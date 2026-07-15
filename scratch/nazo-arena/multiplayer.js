// Guild multiplayer client — opponents may be human or hidden System (never labeled)

(function () {
  const WS_URL = `${location.protocol === "https:" ? "wss" : "ws"}://${location.hostname}:8765`;
  const { ARCHETYPES, cloneFighter, randomPick, fightersForFaction, FACTIONS } = window.NazoData;
  const { showScreen, renderFighterCard, log, $ } = window.NazoSolo;

  const mp = {
    ws: null,
    playerId: null,
    nickname: "",
    guild: null,
    inviteCode: null,
    warId: null,
    youAre: null,
    opponent: null,
    warRoster: [],
    pickBuffer: [],
    warDraftIndex: 0,
    yourFighter: null,
    theirFighter: null,
    yourTurn: false,
    connected: false,
    factions: [],
  };

  function send(type, payload = {}) {
    if (!mp.ws || mp.ws.readyState !== WebSocket.OPEN) return;
    mp.ws.send(JSON.stringify({ type, ...payload }));
  }

  function setStatus(text, ok = true) {
    const el = $("mp-status");
    if (el) {
      el.textContent = text;
      el.className = ok ? "mp-status ok" : "mp-status err";
    }
  }

  function connect() {
    return new Promise((resolve, reject) => {
      mp.ws = new WebSocket(WS_URL);
      mp.ws.onopen = () => { mp.connected = true; resolve(); };
      mp.ws.onerror = () => reject(new Error("Cannot reach arena server"));
      mp.ws.onclose = () => { mp.connected = false; setStatus("Disconnected", false); };
      mp.ws.onmessage = (ev) => handleMessage(JSON.parse(ev.data));
    });
  }

  function handleMessage(msg) {
    switch (msg.type) {
      case "auth.ok":
        mp.playerId = msg.playerId;
        mp.nickname = msg.nickname;
        mp.guild = msg.guild;
        mp.factions = msg.factions || Object.values(window.NazoData.FACTIONS || {});
        if (mp.guild) {
          applyHouseTheme(mp.guild.factionId);
          renderGuildHall();
          showScreen("screen-guild");
        } else {
          renderHouseSelect();
          showScreen("screen-houses");
        }
        break;
      case "guild.updated":
        mp.guild = msg.guild;
        if (msg.inviteCode) mp.inviteCode = msg.inviteCode;
        if (mp.guild) applyHouseTheme(mp.guild.factionId);
        renderGuildHall();
        if (mp.guild) showScreen("screen-guild");
        break;
      case "error":
        setStatus(msg.message, false);
        break;
      case "war.queued":
        setStatus(msg.message);
        $("btn-war-queue").disabled = true;
        $("btn-war-cancel").classList.remove("hidden");
        break;
      case "war.unqueued":
        $("btn-war-queue").disabled = false;
        $("btn-war-cancel").classList.add("hidden");
        setStatus("Queue cancelled");
        break;
      case "war.matched":
        mp.warId = msg.warId;
        mp.youAre = msg.youAre;
        mp.opponent = msg.opponent;
        mp.pickBuffer = [];
        mp.warDraftIndex = 0;
        showOpponentIntro(msg.opponent);
        break;
      case "war.pick.status":
        $("war-pick-status").textContent = msg.line || "";
        break;
      case "war.duel.start":
        startWarDuel(msg);
        break;
      case "war.duel.update":
        onDuelUpdate(msg);
        break;
      case "war.end":
        showWarResult(msg);
        break;
    }
  }

  function showOpponentIntro(opp) {
    $("opp-crest").textContent = opp.crest;
    $("opp-name").textContent = opp.house ? `${opp.house} · ${opp.lab || ""}` : opp.name;
    $("opp-tag").textContent = `[${opp.tag}]`;
    $("opp-elo").textContent = `ELO ${opp.elo} · ${opp.wins}W ${opp.losses}L`;
    const members = opp.members.slice(0, 6).map((m) =>
      `<span class="member-chip">${m.name} <em>${m.lastSeen}</em></span>`
    ).join("");
    $("opp-members").innerHTML = members;
    $("opp-motd").textContent = opp.motd ? `"${opp.motd}"` : "";
    showScreen("screen-war-intro");
  }

  function applyHouseTheme(factionId) {
    document.body.className = factionId ? `house-${factionId}` : "";
  }

  function renderHouseSelect() {
    const el = $("house-grid");
    if (!el) return;
    el.innerHTML = "";
    const list = mp.factions.length ? mp.factions : Object.values(FACTIONS || {});
    list.forEach((fac) => {
      const card = document.createElement("div");
      card.className = `house-card house-${fac.id}`;
      card.innerHTML = `
        <div class="house-crest">${fac.crest}</div>
        <div class="house-name">${fac.house}</div>
        <div class="house-lab">${fac.lab}</div>
        <div class="house-motto">${fac.motd || ""}</div>
        <div class="house-passive-tag">✦ ${fac.passiveName}: ${fac.passiveDesc}</div>
        <div class="house-roster">${(fac.fighters || []).join(" · ")}</div>
      `;
      card.addEventListener("click", () => {
        send("guild.join_faction", { factionId: fac.id });
      });
      el.appendChild(card);
    });
  }

  function renderGuildHall() {
    const g = mp.guild;
    if (!g) {
      $("guild-panel").innerHTML = `<p class="muted">Choose a house to enlist.</p>`;
      $("btn-war-queue").disabled = true;
      return;
    }
    const lab = g.lab || "";
    const house = g.house || g.name;
    const fac = FACTIONS[g.factionId] || {};
    $("guild-panel").innerHTML = `
      <div class="guild-banner house-banner">
        <span class="guild-crest">${g.crest}</span>
        <div>
          <div class="guild-title">${house} <span class="tag">[${g.tag}]</span></div>
          <div class="guild-meta">${lab} · ELO ${g.elo} · ${g.wins}W ${g.losses}L · ${g.members.length} online</div>
          <div class="guild-meta">${g.motd || ""}</div>
          <div class="house-passive-tag">✦ ${fac.passiveName || g.passiveName || "Passive"}: ${fac.passiveDesc || ""}</div>
        </div>
      </div>
      <div class="member-list">${g.members.map((m) =>
        `<div class="member-row"><span>${m.name}</span><span class="role">${m.role}</span><span class="seen">${m.lastSeen}</span></div>`
      ).join("")}</div>
    `;
    $("btn-war-queue").disabled = false;
  }

  async function login() {
    const nick = ($("input-nick").value || "fighter").trim().slice(0, 20);
    if (!nick) return;
    setStatus("Connecting...");
    try {
      await connect();
      send("auth", { nickname: nick });
      setStatus("Online");
    } catch (e) {
      setStatus(e.message + " — start server: python3 server/server.py", false);
    }
  }

  function queueWar() {
    send("war.queue");
  }

  function cancelQueue() {
    send("war.unqueue");
  }

  function startWarDraft() {
    mp.warRoster = [];
    mp.pickBuffer = [];
    mp.warDraftIndex = 0;
    window.NazoSolo.state.mode = "war";
    showScreen("screen-war-draft");
    warDraftPull();
  }

  function warDraftPull() {
    $("war-pull-count").textContent = `${mp.warDraftIndex + 1} / 3`;
    const container = $("war-draft-options");
    container.innerHTML = "";
    const factionId = mp.guild?.factionId || mp.guild?.id?.replace("faction-", "");
    const pool = factionId ? fightersForFaction(factionId) : (window.NazoData.ALL_FIGHTERS || ARCHETYPES);
    randomPick(pool, 3).forEach((base) => {
      container.appendChild(renderFighterCard(base, (f) => {
        mp.pickBuffer.push(f.id);
        mp.warRoster.push(cloneFighter(f));
        mp.warDraftIndex++;
        if (mp.warDraftIndex >= 3) {
          send("war.pick", { warId: mp.warId, fighters: mp.pickBuffer });
          $("war-pick-wait").classList.remove("hidden");
          $("war-draft-options").innerHTML = `<p class="muted">Roster submitted. Waiting for ${mp.opponent.name}...</p>`;
        } else warDraftPull();
      }));
    });
  }

  function showBattlePassive(factionId) {
    const fac = FACTIONS[factionId] || {};
    const el = $("battle-passive");
    if (fac.passiveName) {
      el.textContent = `House passive — ${fac.passiveName}: ${fac.passiveDesc}`;
      el.classList.remove("hidden");
    } else {
      el.classList.add("hidden");
    }
  }

  function showIntel(action) {
    const el = $("battle-intel");
    if (!action) {
      el.classList.add("hidden");
      return;
    }
    el.textContent = `Ravenclaw Insight — opponent last used: ${action}`;
    el.classList.remove("hidden");
  }

  function startWarDuel(msg) {
    $("war-pick-wait").classList.add("hidden");
    window.NazoSolo.state.mode = "war";
    mp.yourFighter = msg.yourFighter;
    mp.theirFighter = msg.theirFighter;
    mp.yourTurn = msg.yourTurn === true;

    $("tier-label").textContent = `Duel ${msg.duelIndex} / 3`;
    $("score-label").textContent = `Score ${msg.homeScore} — ${msg.awayScore}`;

    window.NazoSolo.state.active = mp.yourFighter;
    window.NazoSolo.state.enemy = mp.theirFighter;
    window.NazoSolo.state.playerHp = msg.state.playerHp;
    window.NazoSolo.state.enemyHp = msg.state.enemyHp;
    window.NazoSolo.state.maxHp = msg.state.playerMax;

    $("battle-log").innerHTML = "";
    $("swap-bar").classList.add("hidden");
    $("action-bar").style.display = "grid";

    $("player-sprite").textContent = mp.yourFighter.icon;
    $("player-name").textContent = mp.yourFighter.name;
    $("enemy-sprite").textContent = mp.theirFighter.icon;
    $("enemy-name").textContent = mp.theirFighter.name;
    updateWarUI(msg.state);
    log(`— Duel ${msg.duelIndex}: ${mp.yourFighter.name} vs ${mp.theirFighter.name} —`);
    showBattlePassive(mp.guild?.factionId);
    showIntel(null);
    setWarActions(!!msg.yourTurn);
    showScreen("screen-battle");
  }

  function updateWarUI(st) {
    $("player-hp").style.width = `${Math.max(0, (st.playerHp / st.playerMax) * 100)}%`;
    $("enemy-hp").style.width = `${Math.max(0, (st.enemyHp / st.enemyMax) * 100)}%`;
    $("player-hp-text").textContent = `${Math.max(0, st.playerHp)} / ${st.playerMax}`;
    $("enemy-hp-text").textContent = `${Math.max(0, st.enemyHp)} / ${st.enemyMax}`;
  }

  function setWarActions(on) {
    document.querySelectorAll("#action-bar .btn.action").forEach((b) => { b.disabled = !on; });
    mp.yourTurn = on;
  }

  function onDuelUpdate(msg) {
    msg.log.forEach((e) => log(e.msg, e.cls));
    updateWarUI(msg.state);
    window.NazoSolo.state.playerHp = msg.state.playerHp;
    window.NazoSolo.state.enemyHp = msg.state.enemyHp;
    if (msg.opponentLastAction) showIntel(msg.opponentLastAction);
    if (msg.opponentThinking) {
      setWarActions(false);
      log("Opponent is thinking...", "system");
    } else {
      setWarActions(msg.yourTurn);
    }
  }

  function sendAction(action) {
    if (!mp.yourTurn || !mp.warId) return;
    setWarActions(false);
    send("war.action", { warId: mp.warId, action });
  }

  function showWarResult(msg) {
    $("btn-war-queue").disabled = false;
    $("btn-war-cancel").classList.add("hidden");
    mp.guild = msg.guild;
    renderGuildHall();
    $("result-art").textContent = msg.won ? "🏆" : "💀";
    $("result-title").textContent = msg.won ? "Guild Victory" : "Guild Defeat";
    $("result-body").textContent = msg.won
      ? `Your guild beat ${msg.opponent.name} ${msg.homeScore}–${msg.awayScore}. ELO ${msg.guild.elo}.`
      : `${msg.opponent.name} took it ${msg.awayScore}–${msg.homeScore}. ELO ${msg.guild.elo}.`;
    $("btn-replay").classList.add("hidden");
    $("btn-result-guild").classList.remove("hidden");
    showScreen("screen-result");
  }

  // Wire UI
  $("btn-mp").addEventListener("click", () => showScreen("screen-login"));
  $("btn-login-back").addEventListener("click", () => showScreen("screen-title"));
  $("btn-houses-back").addEventListener("click", () => showScreen("screen-title"));
  $("btn-login").addEventListener("click", login);
  $("btn-guild-back").addEventListener("click", () => showScreen("screen-title"));
  $("btn-leave-house").addEventListener("click", () => {
    send("guild.leave");
    applyHouseTheme(null);
    renderHouseSelect();
    showScreen("screen-houses");
  });
  $("btn-war-queue").addEventListener("click", queueWar);
  $("btn-war-cancel").addEventListener("click", cancelQueue);
  $("btn-war-intro-go").addEventListener("click", startWarDraft);
  $("btn-result-guild").addEventListener("click", () => {
    $("btn-replay").classList.remove("hidden");
    $("btn-result-guild").classList.add("hidden");
    showScreen("screen-guild");
  });

  window.NazoMP = { sendAction, mp };
})();
