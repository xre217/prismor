// Procedural SFX + visual juice — no external audio assets.
(function () {
  const STORAGE_KEY = "nazo-arena-mute";
  let ctx = null;
  let muted = localStorage.getItem(STORAGE_KEY) === "1";
  let master = null;

  function ensureAudio() {
    if (muted) return null;
    if (!ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      ctx = new AC();
      master = ctx.createGain();
      master.gain.value = 0.22;
      master.connect(ctx.destination);
    }
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    return ctx;
  }

  function tone(freq, dur, type, gain, when, slideTo) {
    const ac = ensureAudio();
    if (!ac || !master) return;
    const t0 = when != null ? when : ac.currentTime;
    const osc = ac.createOscillator();
    const g = ac.createGain();
    osc.type = type || "square";
    osc.frequency.setValueAtTime(freq, t0);
    if (slideTo != null) {
      osc.frequency.exponentialRampToValueAtTime(Math.max(20, slideTo), t0 + dur);
    }
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(gain ?? 0.15, t0 + 0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.connect(g);
    g.connect(master);
    osc.start(t0);
    osc.stop(t0 + dur + 0.02);
  }

  function noiseBurst(dur, gain, when) {
    const ac = ensureAudio();
    if (!ac || !master) return;
    const t0 = when != null ? when : ac.currentTime;
    const len = Math.floor(ac.sampleRate * dur);
    const buf = ac.createBuffer(1, len, ac.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < len; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / len);
    const src = ac.createBufferSource();
    src.buffer = buf;
    const g = ac.createGain();
    const f = ac.createBiquadFilter();
    f.type = "bandpass";
    f.frequency.value = 1200;
    g.gain.setValueAtTime(gain ?? 0.12, t0);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    src.connect(f);
    f.connect(g);
    g.connect(master);
    src.start(t0);
    src.stop(t0 + dur + 0.02);
  }

  const SFX = {
    ui() {
      tone(520, 0.06, "triangle", 0.08);
    },
    pick() {
      tone(440, 0.07, "square", 0.1);
      tone(660, 0.09, "square", 0.08, ensureAudio()?.currentTime + 0.05);
    },
    hit() {
      noiseBurst(0.08, 0.14);
      tone(180, 0.1, "sawtooth", 0.12, undefined, 70);
    },
    crit() {
      noiseBurst(0.12, 0.18);
      const t = ensureAudio()?.currentTime || 0;
      tone(320, 0.08, "square", 0.14, t);
      tone(480, 0.1, "square", 0.12, t + 0.06);
      tone(720, 0.14, "triangle", 0.1, t + 0.12);
    },
    guard() {
      tone(220, 0.12, "triangle", 0.1);
      tone(330, 0.1, "triangle", 0.07, ensureAudio()?.currentTime + 0.05);
    },
    heal() {
      const t = ensureAudio()?.currentTime || 0;
      tone(392, 0.1, "sine", 0.1, t);
      tone(523, 0.12, "sine", 0.09, t + 0.07);
      tone(659, 0.14, "sine", 0.08, t + 0.14);
    },
    chaos() {
      noiseBurst(0.16, 0.16);
      tone(90, 0.18, "sawtooth", 0.14, undefined, 40);
      tone(600, 0.08, "square", 0.08, ensureAudio()?.currentTime + 0.04, 200);
    },
    match() {
      const t = ensureAudio()?.currentTime || 0;
      tone(392, 0.1, "square", 0.1, t);
      tone(494, 0.1, "square", 0.1, t + 0.1);
      tone(587, 0.16, "square", 0.12, t + 0.2);
    },
    win() {
      const t = ensureAudio()?.currentTime || 0;
      [523, 659, 784, 1046].forEach((f, i) => tone(f, 0.16, "triangle", 0.11, t + i * 0.09));
    },
    lose() {
      const t = ensureAudio()?.currentTime || 0;
      tone(300, 0.2, "sawtooth", 0.12, t, 120);
      tone(180, 0.28, "triangle", 0.1, t + 0.12, 80);
    },
    assist() {
      const t = ensureAudio()?.currentTime || 0;
      tone(440, 0.08, "sine", 0.1, t);
      tone(554, 0.1, "sine", 0.09, t + 0.06);
      tone(659, 0.14, "sine", 0.1, t + 0.12);
    },
  };

  function play(name) {
    if (muted) return;
    const fn = SFX[name];
    if (fn) {
      try {
        fn();
      } catch (_) {
        /* ignore audio failures */
      }
    }
  }

  function $(id) {
    return document.getElementById(id);
  }

  function shake(intensity) {
    const arena = document.querySelector("#screen-battle.active .arena") || document.querySelector(".arena");
    if (!arena) return;
    const cls = intensity === "heavy" ? "juice-shake-heavy" : "juice-shake";
    arena.classList.remove("juice-shake", "juice-shake-heavy");
    void arena.offsetWidth;
    arena.classList.add(cls);
    setTimeout(() => arena.classList.remove(cls), 450);
  }

  function flash(kind) {
    let el = $("juice-flash");
    if (!el) {
      el = document.createElement("div");
      el.id = "juice-flash";
      el.className = "juice-flash";
      document.body.appendChild(el);
    }
    el.className = `juice-flash ${kind || "hit"}`;
    void el.offsetWidth;
    el.classList.add("on");
    setTimeout(() => el.classList.remove("on"), 220);
  }

  function floatText(side, text, kind) {
    const panel = side === "player"
      ? document.querySelector(".fighter-panel.player-side")
      : document.querySelector(".fighter-panel.enemy-side");
    if (!panel) return;
    const node = document.createElement("div");
    node.className = `juice-float ${kind || "dmg"}`;
    node.textContent = text;
    panel.appendChild(node);
    setTimeout(() => node.remove(), 900);
  }

  function pulseHp(side) {
    const bar = side === "player" ? $("player-hp") : $("enemy-hp");
    if (!bar) return;
    bar.classList.remove("juice-hp-flash");
    void bar.offsetWidth;
    bar.classList.add("juice-hp-flash");
    setTimeout(() => bar.classList.remove("juice-hp-flash"), 350);
  }

  function hit(side, opts) {
    opts = opts || {};
    const amount = opts.amount;
    if (opts.heal) {
      play("heal");
      if (amount != null) floatText(side, `+${Math.round(amount)}`, "heal");
      pulseHp(side);
      return;
    }
    if (opts.crit) {
      play("crit");
      flash("crit");
      shake("heavy");
    } else {
      play("hit");
      flash(side === "player" ? "hurt" : "hit");
      shake(side === "player" ? "heavy" : "light");
    }
    if (amount != null && amount > 0) {
      floatText(side, `-${Math.round(amount)}`, opts.crit ? "crit" : "dmg");
    }
    pulseHp(side);
    const sprite = side === "player" ? $("player-sprite") : $("enemy-sprite");
    if (sprite) {
      sprite.classList.remove("hit");
      void sprite.offsetWidth;
      sprite.classList.add("hit");
    }
  }

  function attack(side) {
    play("ui");
    const sprite = side === "player" ? $("player-sprite") : $("enemy-sprite");
    if (sprite) {
      sprite.classList.remove("attack");
      void sprite.offsetWidth;
      sprite.classList.add("attack");
    }
  }

  function reactLog(msg, cls) {
    if (!msg) return;
    const m = String(msg);
    // Damage / heal SFX come from hit() + HP deltas — only cue verbs without HP swing.
    if (/Chaos|backfire|implode|Wild Card|fumble/i.test(m)) {
      play("chaos");
      return;
    }
    if (/\bguards?\b|Bulwark|Dedication/i.test(m) && !/hits|deals/i.test(m)) {
      play("guard");
    }
  }

  function reactHpDelta(prevPlayer, prevEnemy, nextPlayer, nextEnemy) {
    if (typeof prevPlayer === "number" && typeof nextPlayer === "number") {
      const d = nextPlayer - prevPlayer;
      if (d < -0.5) hit("player", { amount: -d });
      else if (d > 0.5) hit("player", { amount: d, heal: true });
    }
    if (typeof prevEnemy === "number" && typeof nextEnemy === "number") {
      const d = nextEnemy - prevEnemy;
      if (d < -0.5) hit("enemy", { amount: -d });
      else if (d > 0.5) hit("enemy", { amount: d, heal: true });
    }
  }

  function setMuted(on) {
    muted = !!on;
    localStorage.setItem(STORAGE_KEY, muted ? "1" : "0");
    syncMuteButton();
    if (!muted) ensureAudio();
  }

  function toggleMute() {
    setMuted(!muted);
    if (!muted) play("ui");
    return muted;
  }

  function syncMuteButton() {
    const btn = $("btn-mute");
    if (!btn) return;
    btn.textContent = muted ? "🔇 Sound off" : "🔊 Sound on";
    btn.setAttribute("aria-pressed", muted ? "true" : "false");
  }

  function bindUiClicks() {
    document.addEventListener(
      "click",
      (e) => {
        const btn = e.target.closest("button.btn, button.hall-tab, button.draft-card, .fighter-card");
        if (!btn || btn.disabled || btn.id === "btn-mute") return;
        if (btn.classList.contains("action")) return; // battle actions handle their own SFX
        play("ui");
      },
      true
    );
    document.addEventListener(
      "pointerdown",
      () => {
        ensureAudio();
      },
      { once: true }
    );
  }

  function init() {
    syncMuteButton();
    const btn = $("btn-mute");
    if (btn) btn.addEventListener("click", toggleMute);
    bindUiClicks();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.NazoJuice = {
    play,
    hit,
    attack,
    shake,
    flash,
    floatText,
    reactLog,
    reactHpDelta,
    setMuted,
    toggleMute,
    isMuted: () => muted,
    ensureAudio,
  };
})();
