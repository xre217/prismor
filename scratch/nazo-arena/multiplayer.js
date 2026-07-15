// Guild multiplayer client — opponents may be human or hidden System (never labeled)

(function () {
  const WS_URL = `${location.protocol === "https:" ? "wss" : "ws"}://${location.hostname}:8765`;
  const { ARCHETYPES, cloneFighter, fightersForFaction, FACTIONS } = window.NazoData;
  const { showScreen, renderFighterCard, log, $ } = window.NazoSolo;

  const mp = {
    ws: null,
    playerId: null,
    token: localStorage.getItem("nazo-arena-token") || null,
    nickname: "",
    guild: null,
    inviteCode: null,
    warId: null,
    youAre: null,
    opponent: null,
    warRoster: [],
    pickBuffer: [],
    warDraftIndex: 0,
    draft: null,
    yourFighter: null,
    theirFighter: null,
    yourTurn: false,
    connected: false,
    factions: [],
    stats: null,
    standings: [],
    season: null,
    playerBoard: [],
    history: [],
    territories: [],
    boardTab: "houses",
    contestTerritoryId: null,
  };

  function send(type, payload = {}) {
    if (!mp.ws || mp.ws.readyState !== WebSocket.OPEN) return;
    mp.ws.send(JSON.stringify({ type, ...payload }));
  }

  function setStatus(text, ok = true) {
    ["mp-status", "guild-status"].forEach((id) => {
      const el = $(id);
      if (el) {
        el.textContent = text;
        el.className = ok ? "mp-status ok" : "mp-status err";
      }
    });
  }

  function connect() {
    return new Promise((resolve, reject) => {
      mp.ws = new WebSocket(WS_URL);
      mp.ws.onopen = () => { mp.connected = true; resolve(); };
      mp.ws.onerror = () => reject(new Error("Cannot reach arena server"));
      mp.ws.onclose = () => {
        mp.connected = false;
        setStatus("Disconnected — reconnect from login", false);
        const q = $("btn-war-queue");
        const c = $("btn-war-cancel");
        if (q) q.disabled = false;
        if (c) c.classList.add("hidden");
      };
      mp.ws.onmessage = (ev) => handleMessage(JSON.parse(ev.data));
    });
  }

  function applyBoard(msg) {
    if (msg.standings) mp.standings = msg.standings;
    if (msg.season) mp.season = msg.season;
    if (msg.playerBoard) mp.playerBoard = msg.playerBoard;
    if (msg.history) mp.history = msg.history;
    if (msg.territories) mp.territories = msg.territories;
  }

  function handleMessage(msg) {
    switch (msg.type) {
      case "auth.ok":
        mp.playerId = msg.playerId;
        mp.token = msg.token;
        mp.nickname = msg.nickname;
        mp.guild = msg.guild;
        mp.stats = msg.stats || null;
        mp.factions = msg.factions || Object.values(window.NazoData.FACTIONS || {});
        applyBoard(msg);
        if (msg.token) localStorage.setItem("nazo-arena-token", msg.token);
        setStatus(msg.restored ? "Welcome back · Online" : "Online");
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
        if (msg.stats) mp.stats = msg.stats;
        applyBoard(msg);
        if (mp.guild) applyHouseTheme(mp.guild.factionId);
        else applyHouseTheme(null);
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
        mp.draft = msg.draft || null;
        mp.contestTerritoryId = null;
        setStatus("War matched");
        showOpponentIntro(msg.opponent, msg.territory);
        break;
      case "war.draft.update":
        mp.draft = msg.draft;
        if (msg.line) $("war-pick-status").textContent = msg.line;
        if ($("screen-war-draft").classList.contains("active")
            || $("screen-war-intro").classList.contains("active")) {
          renderDraftBoard();
        }
        break;
      case "war.duel.start":
        startWarDuel(msg);
        break;
      case "war.duel.update":
        onDuelUpdate(msg);
        break;
      case "war.duel.end":
        onDuelEnd(msg);
        break;
      case "relic.updated":
        if (msg.stats) mp.stats = msg.stats;
        renderGuildHall();
        setStatus("Relic equipped");
        break;
      case "war.end":
        if (msg.stats) mp.stats = msg.stats;
        applyBoard(msg);
        showWarResult(msg);
        if (msg.relicDrop) {
          setStatus(`Relic unlocked: ${msg.relicDrop.icon} ${msg.relicDrop.name}`);
        }
        break;
    }
  }

  function showOpponentIntro(opp, territory) {
    $("opp-crest").textContent = opp.crest;
    $("opp-name").textContent = opp.house ? `${opp.house} · ${opp.lab || ""}` : opp.name;
    $("opp-tag").textContent = `[${opp.tag}]`;
    $("opp-elo").textContent = `ELO ${opp.elo} · ${opp.wins}W ${opp.losses}L`;
    const terrEl = $("opp-territory");
    if (terrEl) {
      if (territory) {
        terrEl.classList.remove("hidden");
        terrEl.textContent = `Contesting ${territory.icon} ${territory.name} — ${territory.bonusDesc}`;
      } else {
        terrEl.classList.add("hidden");
        terrEl.textContent = "";
      }
    }
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

  function renderSeasonBanner() {
    const el = $("season-banner");
    if (!el) return;
    const s = mp.season;
    if (!s) {
      el.innerHTML = "";
      return;
    }
    const left = s.daysLeft >= 1
      ? `${s.daysLeft} days left`
      : `${s.hoursLeft}h left`;
    el.innerHTML = `
      <div class="season-title">${s.name}</div>
      <div class="season-meta">House ELO resets each season · ${left}</div>
    `;
  }

  function renderStandings() {
    const el = $("standings-panel");
    if (!el) return;
    renderSeasonBanner();

    const tabs = `
      <div class="board-tabs">
        <button type="button" class="board-tab ${mp.boardTab === "houses" ? "active" : ""}" data-tab="houses">Houses</button>
        <button type="button" class="board-tab ${mp.boardTab === "captains" ? "active" : ""}" data-tab="captains">Captains</button>
        <button type="button" class="board-tab ${mp.boardTab === "history" ? "active" : ""}" data-tab="history">Past</button>
      </div>
    `;

    let body = "";
    if (mp.boardTab === "houses") {
      if (!mp.standings.length) {
        body = `<p class="muted">No wars recorded this season yet.</p>`;
      } else {
        body = `<div class="standings-table">${mp.standings.map((s) => `
          <div class="standings-row">
            <span class="rank">#${s.rank}</span>
            <span class="crest">${s.crest}</span>
            <span class="house">${s.house}</span>
            <span class="elo">${s.elo} ELO</span>
            <span class="record">${s.wins}W ${s.losses}L</span>
            <span class="members">${s.members} enlisted · ${s.territories || 0} lands</span>
          </div>
        `).join("")}</div>`;
      }
    } else if (mp.boardTab === "captains") {
      if (!mp.playerBoard.length) {
        body = `<p class="muted">Win a house war to appear on the captain board.</p>`;
      } else {
        body = `<div class="standings-table">${mp.playerBoard.map((p) => `
          <div class="standings-row captains-row">
            <span class="rank">#${p.rank}</span>
            <span class="crest">${p.crest || "·"}</span>
            <span class="house">${p.nickname}</span>
            <span class="elo">${p.house || "—"}</span>
            <span class="record">${p.warsWon}W ${p.warsLost}L</span>
            <span class="members">${p.duelsWon}D</span>
          </div>
        `).join("")}</div>`;
      }
    } else {
      if (!mp.history.length) {
        body = `<p class="muted">No closed seasons yet.</p>`;
      } else {
        body = `<div class="standings-table">${mp.history.map((h) => `
          <div class="standings-row history-row">
            <span class="rank">${h.crest || h.championCrest || "🏆"}</span>
            <span class="house">${h.name}</span>
            <span class="elo">${h.championHouse || h.championFaction || "—"}</span>
            <span class="record">${h.championElo ? h.championElo + " ELO" : ""}</span>
          </div>
        `).join("")}</div>`;
      }
    }

    el.innerHTML = `<h3>Season Board</h3>${tabs}${body}`;
    el.querySelectorAll(".board-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        mp.boardTab = btn.dataset.tab;
        renderStandings();
      });
    });
  }

  function masteryInfo(fighterId) {
    const m = (mp.stats?.mastery || []).find((x) => x.fighter_id === fighterId);
    if (!m) return { xp: 0, tier: 0, tierName: "Rookie", bonusDesc: "No bonus", wins: 0, losses: 0 };
    return {
      xp: m.xp || 0,
      tier: m.tier ?? tierFromXp(m.xp || 0),
      tierName: m.tierName || tierNameFromXp(m.xp || 0),
      bonusDesc: m.bonusDesc || "",
      wins: m.wins || 0,
      losses: m.losses || 0,
    };
  }

  function tierFromXp(xp) {
    if (xp >= 120) return 4;
    if (xp >= 72) return 3;
    if (xp >= 36) return 2;
    if (xp >= 12) return 1;
    return 0;
  }

  function tierNameFromXp(xp) {
    return ["Rookie", "Adept", "Veteran", "Master", "Legend"][tierFromXp(xp)];
  }

  function masteryXp(fighterId) {
    return masteryInfo(fighterId).xp;
  }

  function renderPlayerStats() {
    const el = $("player-stats");
    if (!el) return;
    const s = mp.stats;
    if (!s) {
      el.innerHTML = `<div class="player-stats"><div class="stat-line muted">Stats unlock after your first connect.</div></div>`;
      return;
    }
    const mastery = (s.mastery || []).slice(0, 4).map((m) => {
      const f = (window.NazoData.ALL_FIGHTERS || []).find((x) => x.id === m.fighter_id);
      const name = f ? f.name : m.fighter_id;
      const tier = m.tierName || tierNameFromXp(m.xp || 0);
      return `<span class="mastery-chip tier-${m.tier ?? tierFromXp(m.xp || 0)}">${name} · ${tier} · ${m.xp} XP · ${m.wins}W/${m.losses}L</span>`;
    }).join("");
    el.innerHTML = `
      <div class="player-stats">
        <div class="stat-line"><strong>${s.nickname || mp.nickname}</strong></div>
        <div class="stat-line">Career · Wars ${s.warsWon}W ${s.warsLost}L · Duels ${s.duelsWon}W ${s.duelsLost}L</div>
        ${s.season ? `<div class="stat-line">Season · Wars ${s.season.warsWon}W ${s.season.warsLost}L · Duels ${s.season.duelsWon}W ${s.season.duelsLost}L</div>` : ""}
        ${mastery
          ? `<div class="mastery-row">${mastery}</div>`
          : `<div class="stat-line muted">No fighter mastery yet — draft a war roster.</div>`}
        <div class="stat-line muted">Mastery boosts stats in guild war duels (Adept → Legend).</div>
      </div>
    `;
  }

  function renderRelicPanel() {
    const el = $("relic-panel");
    if (!el) return;
    const relics = mp.stats?.relics || [];
    const equipped = mp.stats?.equippedRelic;
    if (!relics.length) {
      el.innerHTML = `<h3>Relics</h3><p class="muted">Win house wars to unlock relics.</p>`;
      return;
    }
    el.innerHTML = `
      <h3>Relics ${equipped ? `· Equipped ${equipped.icon} ${equipped.name}` : ""}</h3>
      <div class="relic-grid">
        ${relics.map((r) => `
          <button type="button" class="relic-card rarity-${r.rarity} ${r.equipped ? "equipped" : ""} ${r.owned ? "" : "locked"}"
            data-id="${r.id}" ${r.owned ? "" : "disabled"}>
            <span class="relic-icon">${r.owned ? r.icon : "❓"}</span>
            <span class="relic-name">${r.owned ? r.name : "Locked"}</span>
            <span class="relic-rarity">${r.rarity}</span>
            <span class="relic-desc">${r.owned ? r.desc : "Win wars to discover"}</span>
          </button>
        `).join("")}
      </div>
    `;
    el.querySelectorAll(".relic-card:not(.locked)").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.dataset.id;
        const already = mp.stats?.equippedRelic?.id === id;
        send("relic.equip", { relicId: already ? null : id });
      });
    });
  }

  function houseLabel(factionId) {
    if (!factionId) return "Neutral";
    const fac = FACTIONS[factionId] || (mp.factions || []).find((f) => f.id === factionId);
    return fac ? `${fac.crest || ""} ${fac.house || factionId}` : factionId;
  }

  function renderTerritoryMap() {
    const el = $("territory-panel");
    if (!el) return;
    const list = mp.territories || [];
    const myFid = mp.guild?.factionId;
    if (!list.length) {
      el.innerHTML = `<h3>Territory Map</h3><p class="muted">Map loads after connect.</p>`;
      return;
    }
    el.innerHTML = `
      <h3>Territory Map</h3>
      <p class="muted">Click a rival or neutral region to contest it. Owned lands grant mild war bonuses (max 3 stacked).</p>
      <div class="territory-map">
        ${list.map((t) => {
          const owned = t.ownerFaction === myFid;
          const ownerCls = t.ownerFaction ? `owned-${t.ownerFaction}` : "neutral";
          const selected = mp.contestTerritoryId === t.id ? "selected" : "";
          const disabled = owned ? "disabled" : "";
          return `
            <button type="button" class="territory-cell ${ownerCls} ${selected} ${owned ? "yours" : ""}"
              style="grid-row:${t.row};grid-column:${t.col}"
              data-id="${t.id}" ${disabled}
              title="${t.flavor}">
              <span class="t-icon">${t.icon}</span>
              <span class="t-name">${t.name}</span>
              <span class="t-bonus">${t.bonusDesc}</span>
              <span class="t-owner">${owned ? "Your house" : houseLabel(t.ownerFaction)}</span>
            </button>`;
        }).join("")}
      </div>
    `;
    el.querySelectorAll(".territory-cell:not(.yours)").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.dataset.id;
        mp.contestTerritoryId = mp.contestTerritoryId === id ? null : id;
        renderTerritoryMap();
        if (mp.contestTerritoryId) {
          const t = list.find((x) => x.id === id);
          setStatus(`Ready to contest ${t?.icon || ""} ${t?.name || id}`);
        } else {
          setStatus("Open war queue (no territory)");
        }
      });
    });
  }

  function renderGuildHall() {
    renderStandings();
    renderPlayerStats();
    renderRelicPanel();
    renderTerritoryMap();
    const g = mp.guild;
    if (!g) {
      $("guild-panel").innerHTML = `<p class="muted">Choose a house to enlist.</p>`;
      $("btn-war-queue").disabled = true;
      return;
    }
    const lab = g.lab || "";
    const house = g.house || g.name;
    const fac = FACTIONS[g.factionId] || {};
    const contestHint = mp.contestTerritoryId
      ? (() => {
          const t = (mp.territories || []).find((x) => x.id === mp.contestTerritoryId);
          return t ? `Contest ${t.icon} ${t.name}` : "Contest selected region";
        })()
      : "Queue House War";
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
    const qBtn = $("btn-war-queue");
    qBtn.disabled = false;
    qBtn.textContent = contestHint;
  }

  async function login() {
    const nick = ($("input-nick").value || "fighter").trim().slice(0, 20);
    if (!nick) return;
    setStatus("Connecting...");
    try {
      await connect();
      send("auth", { nickname: nick, token: mp.token });
      setStatus("Online");
    } catch (e) {
      setStatus(e.message + " — start server: python3 server/server.py", false);
    }
  }

  function queueWar() {
    const payload = {};
    if (mp.contestTerritoryId) payload.territoryId = mp.contestTerritoryId;
    send("war.queue", payload);
  }

  function cancelQueue() {
    send("war.unqueue");
  }

  function startWarDraft() {
    window.NazoSolo.state.mode = "war";
    showScreen("screen-war-draft");
    renderDraftBoard();
  }

  function nameForId(fid, pool) {
    const hit = (pool || []).find((f) => f.id === fid);
    if (hit) return `${hit.icon} ${hit.name}`;
    const all = window.NazoData.ALL_FIGHTERS || [];
    const f = all.find((x) => x.id === fid);
    return f ? `${f.icon} ${f.name}` : fid;
  }

  function renderDraftBoard() {
    const d = mp.draft;
    if (!d) {
      $("draft-prompt").textContent = "Waiting for draft...";
      return;
    }

    $("draft-step-label").textContent = `${Math.min(d.step + 1, d.totalSteps)} / ${d.totalSteps}`;
    $("draft-prompt").textContent = d.prompt;
    $("draft-prompt").className = d.yourTurn ? "draft-prompt your-turn" : "draft-prompt";

    $("draft-your-bans").textContent = d.yourBans.length
      ? d.yourBans.map((id) => nameForId(id, d.yourPool)).join(", ")
      : "—";
    $("draft-their-bans").textContent = d.theirBans.length
      ? d.theirBans.map((id) => nameForId(id, d.theirPool)).join(", ")
      : "—";
    $("draft-your-picks").textContent = d.yourPicks.length
      ? d.yourPicks.map((id, i) => `${i + 1}. ${nameForId(id, d.yourPool)}`).join(" · ")
      : "—";
    $("draft-their-picks").textContent = d.theirPicks.length
      ? d.theirPicks.map((id, i) => `${i + 1}. ${nameForId(id, d.theirPool)}`).join(" · ")
      : "—";

    const selectable = new Set(d.selectable || []);
    renderDraftPool($("draft-their-pool"), d.theirPool, {
      selectable,
      banned: new Set(d.theirBans || []),
      picks: d.theirPicks || [],
      canAct: d.yourTurn && d.phase === "ban",
    });
    renderDraftPool($("draft-your-pool"), d.yourPool, {
      selectable,
      banned: new Set(d.yourBans || []),
      picks: d.yourPicks || [],
      canAct: d.yourTurn && d.phase === "pick",
    });

    const wait = $("war-pick-wait");
    if (d.yourTurn || d.phase === "done") wait.classList.add("hidden");
    else wait.classList.remove("hidden");
  }

  function renderDraftPool(container, pool, opts) {
    container.innerHTML = "";
    const pickIndex = {};
    opts.picks.forEach((id, i) => { pickIndex[id] = i + 1; });

    (pool || []).forEach((f) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "draft-card";
      const xp = masteryXp(f.id);
      const info = masteryInfo(f.id);
      let state = "";
      if (opts.banned.has(f.id)) {
        card.classList.add("banned");
        state = "BANNED";
      } else if (pickIndex[f.id]) {
        card.classList.add("picked");
        state = `#${pickIndex[f.id]}`;
      }

      const canClick = opts.canAct && opts.selectable.has(f.id);
      if (canClick) card.classList.add("selectable");
      card.disabled = !canClick;
      if (info.tier > 0) card.classList.add(`tier-${info.tier}`);

      card.innerHTML = `
        <span class="draft-icon">${f.icon}</span>
        <span class="draft-name">${f.name}</span>
        <span class="draft-type">${f.type} · ${f.skill}</span>
        <span class="draft-stats">PWR ${f.stats.power} · SPD ${f.stats.speed} · MND ${f.stats.mind}</span>
        ${info.tier > 0 ? `<span class="draft-xp">${info.tierName} · ${xp} XP</span>` : ""}
        ${info.tier > 0 ? `<span class="draft-bonus">${info.bonusDesc || ""}</span>` : ""}
        ${state ? `<span class="draft-state">${state}</span>` : ""}
      `;

      if (canClick) {
        card.addEventListener("click", () => {
          send("war.draft", { warId: mp.warId, fighterId: f.id });
          card.disabled = true;
        });
      }
      container.appendChild(card);
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

    const yourScore = mp.youAre === "away" ? msg.awayScore : msg.homeScore;
    const theirScore = mp.youAre === "away" ? msg.homeScore : msg.awayScore;
    $("tier-label").textContent = `Duel ${msg.duelIndex} / 3`;
    $("score-label").textContent = `You ${yourScore} — ${theirScore} Them`;

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
    if (msg.yourMastery && msg.yourMastery.tier > 0) {
      log(`Your mastery — ${msg.yourMastery.tierName}: ${msg.yourMastery.bonusDesc}`, "crit");
    }
    if (msg.theirMastery && msg.theirMastery.tier > 0) {
      log(`Their mastery — ${msg.theirMastery.tierName}: ${msg.theirMastery.bonusDesc}`, "system");
    }
    if (msg.yourRelic) {
      log(`Your relic — ${msg.yourRelic.icon} ${msg.yourRelic.name}: ${msg.yourRelic.desc}`, "player");
    }
    if (msg.theirRelic) {
      log(`Their relic — ${msg.theirRelic.icon} ${msg.theirRelic.name}`, "enemy");
    }
    (msg.log || []).forEach((e) => log(e.msg, e.cls));
    showBattlePassive(mp.guild?.factionId);
    showMasteryBanner(msg.yourMastery);
    showRelicBanner(msg.yourRelic);
    showIntel(null);
    setWarActions(!!msg.yourTurn);
    showScreen("screen-battle");
  }

  function showMasteryBanner(mastery) {
    const el = $("battle-mastery");
    if (!el) return;
    if (mastery && mastery.tier > 0) {
      el.textContent = `Mastery — ${mastery.tierName}: ${mastery.bonusDesc}`;
      el.classList.remove("hidden");
    } else {
      el.classList.add("hidden");
    }
  }

  function showRelicBanner(relic) {
    const el = $("battle-relic");
    if (!el) return;
    if (relic) {
      el.textContent = `Relic — ${relic.icon} ${relic.name}: ${relic.desc}`;
      el.classList.remove("hidden");
    } else {
      el.classList.add("hidden");
    }
  }

  function renderStatuses(st) {
    const statuses = st?.statuses || { player: [], enemy: [] };
    [["player-statuses", statuses.player], ["enemy-statuses", statuses.enemy]].forEach(([id, list]) => {
      const el = $(id);
      if (!el) return;
      if (!list || !list.length) {
        el.innerHTML = "";
        return;
      }
      el.innerHTML = list.map((s) =>
        `<span class="status-chip ${s.kind || ""}" title="${s.name} (${s.turns})">${s.icon} ${s.turns}</span>`
      ).join("");
    });
  }

  function updateWarUI(st) {
    $("player-hp").style.width = `${Math.max(0, (st.playerHp / st.playerMax) * 100)}%`;
    $("enemy-hp").style.width = `${Math.max(0, (st.enemyHp / st.enemyMax) * 100)}%`;
    $("player-hp-text").textContent = `${Math.max(0, st.playerHp)} / ${st.playerMax}`;
    $("enemy-hp-text").textContent = `${Math.max(0, st.enemyHp)} / ${st.enemyMax}`;
    renderStatuses(st);
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

  function onDuelEnd(msg) {
    setWarActions(false);
    $("score-label").textContent = `You ${msg.yourScore} — ${msg.theirScore} Them`;
    log(
      msg.won
        ? `✦ Duel ${msg.duelIndex} won! Score ${msg.yourScore}–${msg.theirScore}`
        : `☠ Duel ${msg.duelIndex} lost. Score ${msg.yourScore}–${msg.theirScore}`,
      msg.won ? "crit" : "enemy"
    );
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
    mp.warId = null;
    renderGuildHall();
    const your = msg.yourScore ?? (mp.youAre === "away" ? msg.awayScore : msg.homeScore);
    const their = msg.theirScore ?? (mp.youAre === "away" ? msg.homeScore : msg.awayScore);
    const oppName = msg.opponent.house || msg.opponent.name;
    $("result-art").textContent = msg.won ? "🏆" : "💀";
    $("result-title").textContent = msg.won ? "Guild Victory" : "Guild Defeat";
    let body = msg.won
      ? `Your guild beat ${oppName} ${your}–${their}. ELO ${msg.guild.elo}.`
      : `${oppName} took it ${their}–${your}. ELO ${msg.guild.elo}.`;
    if (msg.relicDrop) {
      body += ` Relic unlocked: ${msg.relicDrop.icon} ${msg.relicDrop.name}.`;
    }
    if (msg.territory) {
      const t = msg.territory;
      body += msg.won
        ? ` Your house now holds ${t.icon} ${t.name}.`
        : ` ${t.icon} ${t.name} slipped away.`;
    }
    mp.contestTerritoryId = null;
    $("result-body").textContent = body;
    $("btn-replay").classList.add("hidden");
    $("btn-result-guild").classList.remove("hidden");
    setStatus(msg.won ? "Victory recorded" : "Defeat recorded");
    showScreen("screen-result");
  }

  function cancelQueueAndLeaveHall() {
    if (mp.connected) send("war.unqueue");
    $("btn-war-queue").disabled = false;
    $("btn-war-cancel").classList.add("hidden");
  }

  // Wire UI
  $("btn-mp").addEventListener("click", () => showScreen("screen-login"));
  $("btn-login-back").addEventListener("click", () => showScreen("screen-title"));
  $("btn-houses-back").addEventListener("click", () => showScreen("screen-title"));
  $("btn-login").addEventListener("click", login);
  $("btn-guild-back").addEventListener("click", () => {
    cancelQueueAndLeaveHall();
    showScreen("screen-title");
  });
  $("btn-leave-house").addEventListener("click", () => {
    cancelQueueAndLeaveHall();
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
