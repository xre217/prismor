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
    replays: [],
    liveWars: [],
    boardTab: "houses",
    contestTerritoryId: null,
    spectating: false,
    canAssist: false,
    alliance: null,
    theirAlliance: null,
    raidMode: false,
    raidId: null,
    replayView: null,
    replayDuelIdx: 0,
    replayLogIdx: 0,
    replayTimer: null,
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
    if (msg.replays) mp.replays = msg.replays;
    if (msg.liveWars) mp.liveWars = msg.liveWars;
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
        mp.alliance = msg.alliance || null;
        mp.theirAlliance = msg.theirAlliance || null;
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
      case "war.assist.ok":
        mp.canAssist = false;
        setAssistButton(false);
        setStatus(msg.message || "Assist sent");
        break;
      case "raid.pick":
        mp.raidMode = true;
        mp.raidId = msg.raidId;
        renderRaidPick(msg);
        showScreen("screen-raid-pick");
        break;
      case "raid.duel.start":
        mp.raidMode = true;
        startRaidDuel(msg);
        break;
      case "raid.duel.update":
        onRaidDuelUpdate(msg);
        break;
      case "raid.duel.end":
        onRaidDuelEnd(msg);
        break;
      case "raid.end":
        if (msg.stats) mp.stats = msg.stats;
        showRaidResult(msg);
        break;
      case "war.duel.start":
        if (msg.spectator) mp.spectating = true;
        startWarDuel(msg);
        break;
      case "war.duel.update":
        onDuelUpdate(msg);
        break;
      case "war.duel.end":
        onDuelEnd(msg);
        break;
      case "war.spectate.ok":
        mp.spectating = true;
        mp.warId = msg.warId;
        mp.youAre = "home";
        setStatus(`Spectating ${msg.home?.house || "home"} vs ${msg.opponent?.house || "away"}`);
        if (msg.phase === "draft") {
          $("opp-crest").textContent = msg.opponent?.crest || "◈";
          $("opp-name").textContent = `${msg.home?.house || "Home"} vs ${msg.opponent?.house || "Away"}`;
          $("opp-tag").textContent = "LIVE";
          $("opp-elo").textContent = `Score ${msg.homeScore}–${msg.awayScore} · draft in progress`;
          const terrEl = $("opp-territory");
          if (terrEl) {
            if (msg.territory) {
              terrEl.classList.remove("hidden");
              terrEl.textContent = `Contesting ${msg.territory.icon} ${msg.territory.name}`;
            } else terrEl.classList.add("hidden");
          }
          $("opp-members").innerHTML = "";
          $("opp-motd").textContent = "Spectating — waiting for duels…";
          showScreen("screen-war-intro");
          $("btn-war-intro-go").classList.add("hidden");
        }
        break;
      case "replay.data":
        openReplayViewer(msg.replay);
        break;
      case "war.unspectate.ok":
        mp.spectating = false;
        mp.warId = null;
        setStatus("Left spectator seat");
        showScreen("screen-guild");
        renderGuildHall();
        break;
      case "relic.updated":
        if (msg.stats) mp.stats = msg.stats;
        renderGuildHall();
        setStatus("Relic equipped");
        break;
      case "quest.updated":
        if (msg.stats) mp.stats = msg.stats;
        renderGuildHall();
        if (msg.reward) {
          let line = `Quest claimed · +${msg.reward.qpGained || 0} QP`;
          if (msg.reward.relic) line += ` · ${msg.reward.relic.icon} ${msg.reward.relic.name}`;
          if (msg.reward.mastery) line += ` · +${msg.reward.mastery.xp} mastery`;
          setStatus(line);
        } else if (msg.shopPurchase) {
          const p = msg.shopPurchase;
          let line = "Shop purchase";
          if (p.relic) line = `Unlocked ${p.relic.icon} ${p.relic.name}`;
          if (p.mastery) line = `+${p.mastery.xp} mastery XP`;
          setStatus(line);
        } else {
          setStatus("Quests updated");
        }
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
    const bond = mp.alliance;
    const their = mp.theirAlliance;
    let bondLine = "";
    if (bond) {
      bondLine = `Your bond ${bond.icon} ${bond.name} (${bond.count} online)`;
      if (their) bondLine += ` · Their ${their.icon} ${their.name}`;
    }
    const members = opp.members.slice(0, 6).map((m) =>
      `<span class="member-chip">${m.name} <em>${m.lastSeen}</em></span>`
    ).join("");
    $("opp-members").innerHTML = members;
    $("opp-motd").textContent = [
      opp.motd ? `"${opp.motd}"` : "",
      bondLine,
    ].filter(Boolean).join(" · ") || "";
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
        <div class="stat-line">Quest points · <strong>${s.questPoints || 0} QP</strong></div>
        ${s.season ? `<div class="stat-line">Season · Wars ${s.season.warsWon}W ${s.season.warsLost}L · Duels ${s.season.duelsWon}W ${s.season.duelsLost}L</div>` : ""}
        ${mastery
          ? `<div class="mastery-row">${mastery}</div>`
          : `<div class="stat-line muted">No fighter mastery yet — draft a war roster.</div>`}
        <div class="stat-line muted">Mastery boosts stats in guild war duels (Adept → Legend).</div>
      </div>
    `;
  }

  function formatReset(sec) {
    const s = Math.max(0, sec | 0);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return `${h}h ${m}m`;
  }

  function renderQuestPanel() {
    const el = $("quest-panel");
    if (!el) return;
    const d = mp.stats?.dailies;
    if (!d) {
      el.innerHTML = `<h3>Daily Quests</h3><p class="muted">Connect to load today's slate.</p>`;
      return;
    }
    const quests = d.quests || [];
    el.innerHTML = `
      <h3>Daily Quests · ${d.questPoints || 0} QP</h3>
      <p class="muted">Resets in ${formatReset(d.resetsInSec)} (UTC)</p>
      <div class="quest-list">
        ${quests.map((q) => `
          <div class="quest-row ${q.complete ? "complete" : ""} ${q.claimed ? "claimed" : ""}">
            <div class="quest-main">
              <span class="quest-icon">${q.icon}</span>
              <div>
                <div class="quest-title">${q.title}</div>
                <div class="quest-desc">${q.desc}</div>
                <div class="quest-reward">${q.rewardDesc}</div>
              </div>
            </div>
            <div class="quest-side">
              <div class="quest-prog">${q.progress}/${q.target}</div>
              ${q.claimable
                ? `<button type="button" class="btn tiny quest-claim" data-id="${q.id}">Claim</button>`
                : q.claimed
                  ? `<span class="quest-done">Claimed</span>`
                  : `<span class="quest-pending">In progress</span>`}
            </div>
          </div>
        `).join("")}
      </div>
      <h4 class="quest-shop-title">Quest Shop</h4>
      <div class="quest-shop">
        ${(d.shop || []).map((item) => `
          <button type="button" class="shop-card ${item.affordable ? "" : "locked"}"
            data-id="${item.id}" ${item.affordable ? "" : "disabled"}>
            <span class="shop-icon">${item.icon}</span>
            <span class="shop-name">${item.name}</span>
            <span class="shop-cost">${item.cost} QP</span>
            <span class="shop-desc">${item.desc}</span>
          </button>
        `).join("")}
      </div>
    `;
    el.querySelectorAll(".quest-claim").forEach((btn) => {
      btn.addEventListener("click", () => send("quest.claim", { questId: btn.dataset.id }));
    });
    el.querySelectorAll(".shop-card:not(.locked)").forEach((btn) => {
      btn.addEventListener("click", () => send("quest.shop", { itemId: btn.dataset.id }));
    });
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

  function renderReplayPanel() {
    const el = $("replay-panel");
    if (!el) return;
    const live = mp.liveWars || [];
    const replays = mp.replays || [];
    const myFid = mp.guild?.factionId;

    const liveHtml = live.length
      ? `<div class="replay-list">${live.map((w) => {
          const mine = myFid && (w.homeFaction === myFid || w.awayFaction === myFid);
          return `
            <div class="replay-row live">
              <div class="replay-match">
                <span>${w.homeCrest} ${w.homeHouse}</span>
                <span class="replay-vs">${w.homeScore}–${w.awayScore}</span>
                <span>${w.awayCrest} ${w.awayHouse}</span>
              </div>
              <div class="replay-meta">${w.phase}${w.territory ? ` · ${w.territory.icon}` : ""}</div>
              ${mine
                ? `<span class="quest-pending">Your war</span>`
                : `<button type="button" class="btn tiny spectate-btn" data-id="${w.warId}">Spectate</button>`}
            </div>`;
        }).join("")}</div>`
      : `<p class="muted">No live wars right now.</p>`;

    const replayHtml = replays.length
      ? `<div class="replay-list">${replays.map((r) => `
          <button type="button" class="replay-row" data-id="${r.id}">
            <div class="replay-match">
              <span>${r.homeCrest} ${r.homeHouse}</span>
              <span class="replay-vs">${r.homeScore}–${r.awayScore}</span>
              <span>${r.awayCrest} ${r.awayHouse}</span>
            </div>
            <div class="replay-meta">Watch replay</div>
          </button>
        `).join("")}</div>`
      : `<p class="muted">Finish a house war to archive a replay.</p>`;

    el.innerHTML = `
      <h3>Wars · Live & Replays</h3>
      <h4 class="quest-shop-title">Live</h4>
      ${liveHtml}
      <h4 class="quest-shop-title">Recent Replays</h4>
      ${replayHtml}
    `;
    el.querySelectorAll(".spectate-btn").forEach((btn) => {
      btn.addEventListener("click", () => send("war.spectate", { warId: btn.dataset.id }));
    });
    el.querySelectorAll(".replay-row[data-id]:not(.live)").forEach((btn) => {
      btn.addEventListener("click", () => send("replay.get", { replayId: btn.dataset.id }));
    });
  }

  function stopReplayTimer() {
    if (mp.replayTimer) {
      clearInterval(mp.replayTimer);
      mp.replayTimer = null;
    }
    const play = $("btn-replay-play");
    if (play) play.textContent = "Play";
  }

  function openReplayViewer(replay) {
    stopReplayTimer();
    mp.replayView = replay;
    mp.replayDuelIdx = 0;
    mp.replayLogIdx = 0;
    const home = FACTIONS[replay.homeFaction] || {};
    const away = FACTIONS[replay.awayFaction] || {};
    $("replay-header").textContent =
      `${home.crest || ""} ${home.house || replay.homeFaction} ${replay.homeScore}–${replay.awayScore} ${away.house || replay.awayFaction} ${away.crest || ""}`;
    const draft = replay.draft || {};
    $("replay-draft").innerHTML = `
      <div>Home bans: ${(draft.homeBans || []).join(", ") || "—"} · picks: ${(draft.homePicks || []).join(", ") || "—"}</div>
      <div>Away bans: ${(draft.awayBans || []).join(", ") || "—"} · picks: ${(draft.awayPicks || []).join(", ") || "—"}</div>
      ${replay.territory ? `<div>Territory: ${replay.territory.icon} ${replay.territory.name}</div>` : ""}
    `;
    const tabs = $("replay-duel-tabs");
    const duels = replay.duels || [];
    tabs.innerHTML = duels.map((d, i) =>
      `<button type="button" class="board-tab ${i === 0 ? "active" : ""}" data-i="${i}">Duel ${d.index || i + 1}</button>`
    ).join("") || `<span class="muted">No duel logs captured.</span>`;
    tabs.querySelectorAll(".board-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        stopReplayTimer();
        mp.replayDuelIdx = Number(btn.dataset.i);
        mp.replayLogIdx = 0;
        renderReplayDuel();
      });
    });
    showScreen("screen-replay");
    renderReplayDuel();
  }

  function currentReplayDuel() {
    return (mp.replayView?.duels || [])[mp.replayDuelIdx] || null;
  }

  function renderReplayDuel() {
    const duel = currentReplayDuel();
    const tabs = $("replay-duel-tabs");
    if (tabs) {
      tabs.querySelectorAll(".board-tab").forEach((b, i) => {
        b.classList.toggle("active", i === mp.replayDuelIdx);
      });
    }
    if (!duel) {
      $("replay-home-card").textContent = "—";
      $("replay-away-card").textContent = "—";
      $("replay-score").textContent = "—";
      $("replay-log").innerHTML = `<div class="log-line system">No data</div>`;
      return;
    }
    const hf = duel.homeFighter || {};
    const af = duel.awayFighter || {};
    $("replay-home-card").innerHTML = `<div class="r-icon">${hf.icon || "◈"}</div><div>${hf.name || "?"}</div><div class="muted">${duel.finalHomeHp ?? "?"} HP</div>`;
    $("replay-away-card").innerHTML = `<div class="r-icon">${af.icon || "◈"}</div><div>${af.name || "?"}</div><div class="muted">${duel.finalAwayHp ?? "?"} HP</div>`;
    $("replay-score").textContent = duel.homeWon ? "Home win" : "Away win";
    const logEl = $("replay-log");
    const lines = duel.log || [];
    const shown = lines.slice(0, Math.max(1, mp.replayLogIdx));
    logEl.innerHTML = shown.map((e) =>
      `<div class="log-line ${e.cls || "system"}">${e.msg}</div>`
    ).join("");
    logEl.scrollTop = logEl.scrollHeight;
  }

  function replayStep(delta) {
    const duel = currentReplayDuel();
    if (!duel) return;
    const lines = duel.log || [];
    mp.replayLogIdx = Math.max(0, Math.min(lines.length, mp.replayLogIdx + delta));
    if (mp.replayLogIdx === 0 && delta < 0) mp.replayLogIdx = 0;
    renderReplayDuel();
    if (mp.replayLogIdx >= lines.length) stopReplayTimer();
  }

  function toggleReplayPlay() {
    if (mp.replayTimer) {
      stopReplayTimer();
      return;
    }
    const duel = currentReplayDuel();
    if (!duel) return;
    if (mp.replayLogIdx >= (duel.log || []).length) mp.replayLogIdx = 0;
    $("btn-replay-play").textContent = "Pause";
    mp.replayTimer = setInterval(() => {
      const d = currentReplayDuel();
      if (!d || mp.replayLogIdx >= (d.log || []).length) {
        stopReplayTimer();
        return;
      }
      mp.replayLogIdx += 1;
      renderReplayDuel();
    }, 450);
  }

  function renderRaidPanel() {
    const el = $("raid-panel");
    if (!el) return;
    const r = mp.stats?.raid;
    if (!r) {
      el.innerHTML = `<h3>Season Raid</h3><p class="muted">Connect to see the seasonal boss.</p>`;
      return;
    }
    const phases = (r.phasePreview || []).map((p) =>
      `<span class="raid-phase-chip">${p.icon} ${p.name} · ${p.maxHp} HP</span>`
    ).join("");
    el.innerHTML = `
      <h3>Season Raid · ${r.icon} ${r.name}</h3>
      <p class="muted">${r.flavor}</p>
      <div class="raid-phases">${phases}</div>
      <div class="raid-meta">${r.attemptsLeft}/${r.dailyAttempts} attempts left · ${r.clears} season clears · ${r.rewardDesc}</div>
      <button type="button" class="btn primary" id="btn-raid-start" ${r.attemptsLeft > 0 ? "" : "disabled"}>
        ${r.attemptsLeft > 0 ? "Enter Raid" : "No attempts left"}
      </button>
    `;
    const btn = $("btn-raid-start");
    if (btn && r.attemptsLeft > 0) {
      btn.addEventListener("click", () => send("raid.start"));
    }
  }

  function renderRaidPick(msg) {
    const boss = msg.boss || {};
    $("raid-boss-banner").textContent =
      `${boss.icon || "⚔"} ${boss.name || "Raid"} — pick ${msg.need} more`;
    $("raid-pick-status").textContent = `Gauntlet of ${boss.phases || 3} phases. Order = duel order.`;
    const pool = $("raid-pick-pool");
    pool.innerHTML = "";
    (msg.pool || []).forEach((f) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "fighter-card";
      card.innerHTML = `
        <div class="icon">${f.icon}</div>
        <div class="cname">${f.name}</div>
        <div class="ctype">${f.type} · ${f.skill}</div>
      `;
      card.addEventListener("click", () => send("raid.pick", { fighterId: f.id }));
      pool.appendChild(card);
    });
    const roster = $("raid-pick-roster");
    roster.innerHTML = (msg.picks || []).length
      ? `<h3>Raid roster</h3><div class="roster-tags">${msg.picks.map((p) =>
          `<span class="roster-tag">${p.icon} ${p.name}</span>`).join("")}</div>`
      : "";
  }

  function startRaidDuel(msg) {
    window.NazoSolo.state.mode = "raid";
    mp.raidMode = true;
    mp.yourFighter = msg.yourFighter;
    mp.theirFighter = msg.theirFighter;
    mp.yourTurn = true;
    mp.spectating = false;

    $("tier-label").textContent = `Raid · Phase ${msg.phaseIndex}/${msg.phaseTotal}`;
    $("score-label").textContent = msg.bossName || "Boss";

    window.NazoSolo.state.active = mp.yourFighter;
    window.NazoSolo.state.enemy = mp.theirFighter;
    window.NazoSolo.state.playerHp = msg.state.playerHp;
    window.NazoSolo.state.enemyHp = msg.state.enemyHp;
    window.NazoSolo.state.maxHp = msg.state.playerMax;

    $("battle-log").innerHTML = "";
    $("swap-bar").classList.add("hidden");
    $("action-bar").style.display = "grid";
    setAssistButton(false);

    $("player-sprite").textContent = mp.yourFighter.icon;
    $("player-name").textContent = mp.yourFighter.name;
    $("enemy-sprite").textContent = mp.theirFighter.icon;
    $("enemy-name").textContent = mp.theirFighter.name;
    updateWarUI(msg.state);
    log(`— Phase ${msg.phaseIndex}: ${mp.yourFighter.name} vs ${mp.theirFighter.name} —`);
    if (msg.yourMastery && msg.yourMastery.tier > 0) {
      log(`Mastery — ${msg.yourMastery.tierName}: ${msg.yourMastery.bonusDesc}`, "crit");
    }
    if (msg.yourRelic) {
      log(`Relic — ${msg.yourRelic.icon} ${msg.yourRelic.name}`, "player");
    }
    (msg.log || []).forEach((e) => log(e.msg, e.cls));
    showBattlePassive(mp.guild?.factionId);
    showAllianceBanner(null);
    showMasteryBanner(msg.yourMastery);
    showRelicBanner(msg.yourRelic);
    showIntel(null);
    setWarActions(true);
    showScreen("screen-battle");
  }

  function onRaidDuelUpdate(msg) {
    (msg.log || []).forEach((e) => log(e.msg, e.cls));
    updateWarUI(msg.state);
    window.NazoSolo.state.playerHp = msg.state.playerHp;
    window.NazoSolo.state.enemyHp = msg.state.enemyHp;
    if (msg.opponentThinking) {
      setWarActions(false);
      log("Boss is acting...", "system");
    } else {
      setWarActions(!!msg.yourTurn);
    }
  }

  function onRaidDuelEnd(msg) {
    setWarActions(false);
    log(
      msg.won
        ? `✦ Phase ${msg.phaseIndex} cleared!`
        : `☠ Fallen at phase ${msg.phaseIndex}`,
      msg.won ? "crit" : "enemy"
    );
  }

  function showRaidResult(msg) {
    mp.raidMode = false;
    mp.raidId = null;
    setWarActions(false);
    setAssistButton(false);
    if (msg.stats) mp.stats = msg.stats;
    renderGuildHall();
    if (msg.aborted) {
      setStatus("Raid aborted");
      showScreen("screen-guild");
      return;
    }
    const boss = msg.boss || {};
    $("result-art").textContent = msg.won ? (boss.icon || "🏆") : "💀";
    $("result-title").textContent = msg.won ? "Raid Cleared" : "Raid Failed";
    let body = msg.won
      ? `You cleared ${boss.icon || ""} ${boss.name || "the raid"}.`
      : `The ${boss.name || "boss"} stands. Try again tomorrow if attempts remain.`;
    const r = msg.rewards || {};
    if (msg.won) {
      if (r.qp) body += ` +${r.qp} QP.`;
      if (r.masteryXp) body += ` +${r.masteryXp} mastery.`;
      if (r.relic) body += ` Relic: ${r.relic.icon} ${r.relic.name}.`;
    }
    $("result-body").textContent = body;
    $("btn-replay").classList.add("hidden");
    $("btn-result-guild").classList.remove("hidden");
    setStatus(msg.won ? "Raid cleared" : "Raid failed");
    showScreen("screen-result");
  }

  function renderGuildHall() {
    renderStandings();
    renderPlayerStats();
    renderQuestPanel();
    renderRaidPanel();
    renderRelicPanel();
    renderTerritoryMap();
    renderReplayPanel();
    const g = mp.guild;
    if (!g) {
      $("guild-panel").innerHTML = `<p class="muted">Choose a house to enlist.</p>`;
      $("btn-war-queue").disabled = true;
      return;
    }
    const lab = g.lab || "";
    const house = g.house || g.name;
    const fac = FACTIONS[g.factionId] || {};
    const bond = localAlliancePreview();
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
          ${bond ? `<div class="alliance-tag">${bond.icon} ${bond.name} · ${bond.desc}</div>` : ""}
        </div>
      </div>
      <div class="member-list">${g.members.map((m) =>
        `<div class="member-row"><span>${m.name}</span><span class="role">${m.role}</span><span class="seen">${m.lastSeen}</span></div>`
      ).join("")}</div>
      <p class="muted">More house members online → stronger alliance bonds in wars. Each ally can Assist once per duel (+6 HP).</p>
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
    mp.yourTurn = msg.spectator ? false : msg.yourTurn === true;
    if (msg.spectator) mp.spectating = true;
    if (msg.youAre) mp.youAre = msg.youAre;

    const yourScore = mp.youAre === "away" ? msg.awayScore : msg.homeScore;
    const theirScore = mp.youAre === "away" ? msg.homeScore : msg.awayScore;
    $("tier-label").textContent = msg.spectator
      ? `Spectating · Duel ${msg.duelIndex} / 3`
      : `Duel ${msg.duelIndex} / 3`;
    $("score-label").textContent = msg.spectator
      ? `${yourScore} — ${theirScore}`
      : `You ${yourScore} — ${theirScore} Them`;

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
    if (msg.spectator) log("Spectating — home POV (actions disabled)", "system");
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
    if (msg.alliance) mp.alliance = msg.alliance;
    if (msg.theirAlliance) mp.theirAlliance = msg.theirAlliance;
    mp.canAssist = !!msg.canAssist && !msg.spectator;
    showBattlePassive(mp.guild?.factionId);
    showAllianceBanner(msg.alliance || mp.alliance);
    showMasteryBanner(msg.yourMastery);
    showRelicBanner(msg.yourRelic);
    showIntel(null);
    setAssistButton(mp.canAssist);
    setWarActions(!msg.spectator && !!msg.yourTurn);
    showScreen("screen-battle");
  }

  function showAllianceBanner(alliance) {
    const el = $("battle-alliance");
    if (!el) return;
    if (alliance && alliance.tier > 1) {
      el.textContent = `Alliance — ${alliance.icon} ${alliance.name}: ${alliance.desc}`;
      el.classList.remove("hidden");
    } else if (alliance) {
      el.textContent = `Alliance — ${alliance.icon} ${alliance.name}`;
      el.classList.remove("hidden");
    } else {
      el.classList.add("hidden");
    }
  }

  function setAssistButton(on) {
    const btn = $("btn-war-assist");
    if (!btn) return;
    if (on && !mp.spectating) {
      btn.classList.remove("hidden");
      btn.disabled = false;
    } else {
      btn.classList.add("hidden");
      btn.disabled = true;
    }
  }

  function localAlliancePreview() {
    const g = mp.guild;
    if (!g) return null;
    const n = Math.max(1, (g.members || []).length);
    const tiers = {
      1: { tier: 1, name: "Lone Wolf", icon: "🐺", desc: "Fighting alone — no alliance bonus.", count: n },
      2: { tier: 2, name: "Duo Bond", icon: "🤝", desc: "+3 HP · open Regen on duel 1.", count: n },
      3: { tier: 3, name: "Trio Bond", icon: "🔗", desc: "+5 HP · +1 Shield · open Focus on duel 1.", count: n },
      4: { tier: 4, name: "House United", icon: "🏛", desc: "+8 HP · +1 Power · +6% damage · open Focus.", count: n },
    };
    const key = n >= 4 ? 4 : n;
    return tiers[key];
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
    if (mp.spectating) on = false;
    document.querySelectorAll("#action-bar .btn.action").forEach((b) => { b.disabled = !on; });
    mp.yourTurn = on;
  }

  function onDuelUpdate(msg) {
    msg.log.forEach((e) => log(e.msg, e.cls));
    updateWarUI(msg.state);
    window.NazoSolo.state.playerHp = msg.state.playerHp;
    window.NazoSolo.state.enemyHp = msg.state.enemyHp;
    if (msg.opponentLastAction) showIntel(msg.opponentLastAction);
    if (mp.spectating) {
      setWarActions(false);
      return;
    }
    if (msg.opponentThinking) {
      setWarActions(false);
      log("Opponent is thinking...", "system");
    } else {
      setWarActions(msg.yourTurn);
    }
  }

  function onDuelEnd(msg) {
    setWarActions(false);
    $("score-label").textContent = mp.spectating
      ? `${msg.yourScore} — ${msg.theirScore}`
      : `You ${msg.yourScore} — ${msg.theirScore} Them`;
    log(
      msg.won
        ? `✦ Duel ${msg.duelIndex} won! Score ${msg.yourScore}–${msg.theirScore}`
        : `☠ Duel ${msg.duelIndex} lost. Score ${msg.yourScore}–${msg.theirScore}`,
      msg.won ? "crit" : "enemy"
    );
  }

  function sendAction(action) {
    if (mp.spectating || !mp.yourTurn) return;
    if (mp.raidMode) {
      setWarActions(false);
      send("raid.action", { action });
      return;
    }
    if (!mp.warId) return;
    setWarActions(false);
    send("war.action", { warId: mp.warId, action });
  }

  function showWarResult(msg) {
    $("btn-war-queue").disabled = false;
    $("btn-war-cancel").classList.add("hidden");
    $("btn-war-intro-go").classList.remove("hidden");
    setAssistButton(false);
    mp.canAssist = false;
    if (msg.guild) mp.guild = msg.guild;
    mp.warId = null;
    const wasSpec = mp.spectating || msg.spectator;
    mp.spectating = false;
    renderGuildHall();
    const your = msg.yourScore ?? (mp.youAre === "away" ? msg.awayScore : msg.homeScore);
    const their = msg.theirScore ?? (mp.youAre === "away" ? msg.homeScore : msg.awayScore);
    if (wasSpec) {
      $("result-art").textContent = "👁";
      $("result-title").textContent = "War Complete";
      let body = `Final score ${msg.homeScore ?? your}–${msg.awayScore ?? their}.`;
      if (msg.replayId) body += " Open Replays in the guild hall to re-watch.";
      $("result-body").textContent = body;
      $("btn-replay").classList.add("hidden");
      $("btn-result-guild").classList.remove("hidden");
      if (msg.replayId) {
        $("btn-replay").textContent = "Watch Replay";
        $("btn-replay").classList.remove("hidden");
        $("btn-replay").onclick = () => send("replay.get", { replayId: msg.replayId });
      }
      setStatus("Spectated war ended");
      showScreen("screen-result");
      return;
    }
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
    if (msg.replayId) body += " Replay saved.";
    mp.contestTerritoryId = null;
    $("result-body").textContent = body;
    $("btn-replay").classList.add("hidden");
    $("btn-result-guild").classList.remove("hidden");
    if (msg.replayId) {
      $("btn-replay").textContent = "Watch Replay";
      $("btn-replay").classList.remove("hidden");
      $("btn-replay").onclick = () => send("replay.get", { replayId: msg.replayId });
    }
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
    if (mp.spectating) send("war.unspectate");
    showScreen("screen-title");
  });
  $("btn-leave-house").addEventListener("click", () => {
    cancelQueueAndLeaveHall();
    if (mp.spectating) send("war.unspectate");
    send("guild.leave");
    applyHouseTheme(null);
    renderHouseSelect();
    showScreen("screen-houses");
  });
  $("btn-war-queue").addEventListener("click", queueWar);
  $("btn-war-cancel").addEventListener("click", cancelQueue);
  $("btn-war-assist").addEventListener("click", () => {
    if (!mp.canAssist || !mp.warId || mp.spectating) return;
    send("war.assist", { warId: mp.warId });
    mp.canAssist = false;
    setAssistButton(false);
  });
  $("btn-raid-abort").addEventListener("click", () => send("raid.abort"));
  $("btn-war-intro-go").addEventListener("click", startWarDraft);
  $("btn-result-guild").addEventListener("click", () => {
    $("btn-replay").classList.remove("hidden");
    $("btn-result-guild").classList.add("hidden");
    $("btn-replay").textContent = "Run it back";
    $("btn-replay").onclick = null;
    showScreen("screen-guild");
  });
  $("btn-replay-back").addEventListener("click", () => {
    stopReplayTimer();
    mp.replayView = null;
    showScreen("screen-guild");
    renderGuildHall();
  });
  $("btn-replay-prev").addEventListener("click", () => {
    stopReplayTimer();
    replayStep(-1);
  });
  $("btn-replay-next").addEventListener("click", () => {
    stopReplayTimer();
    replayStep(1);
  });
  $("btn-replay-play").addEventListener("click", toggleReplayPlay);

  window.NazoMP = { sendAction, mp };
})();
