// Start Review — modal overlay that replays the 3-minute pre-start
// sequence with official RRS Appendix S horn signals.
//
// - Same Light Blue Carto basemap as the main race map (uses the
//   tile-light-blue CSS filter from race.css).
// - Same boat divIcon arrow rotated by COG, same 30-second trail
//   polyline, colored by team.
// - Own playback clock from t = -180s to t = +60s with 1×/5×/10×
//   speed selector (default 5×).
// - Web Audio horn synthesis (no audio assets to host).
// - Skips the optional 3:15 alert per request.

(function () {
  'use strict';

  const NS = (window.SailFramesStartReview = window.SailFramesStartReview || {});

  // RRS Appendix S 3-minute sequence. Optional 3:15 alert intentionally
  // omitted. L = long horn (~1.5s), S = short (~0.4s), space = group gap.
  const SIGNALS = [
    { t: -180, pattern: 'L L L', label: '3:00 — three long' },
    { t: -120, pattern: 'L L',   label: '2:00 — two long' },
    { t:  -90, pattern: 'L SSS', label: '1:30 — one long, three short' },
    { t:  -60, pattern: 'L',     label: '1:00 — one long' },
    { t:  -30, pattern: 'SSS',   label: '0:30 — three short' },
    { t:  -20, pattern: 'SS',    label: '0:20 — two short' },
    { t:  -10, pattern: 'S',     label: '0:10 — one short' },
    { t:   -5, pattern: 'S',     label: '0:05' },
    { t:   -4, pattern: 'S',     label: '0:04' },
    { t:   -3, pattern: 'S',     label: '0:03' },
    { t:   -2, pattern: 'S',     label: '0:02' },
    { t:   -1, pattern: 'S',     label: '0:01' },
    { t:    0, pattern: 'L',     label: 'START' },
  ];

  const T_START = -180;
  const T_END   =  60;
  const TRAIL_MS = 30_000;  // 30-second trail, matches user request

  // Internal state — single instance.
  let rootEl, mapEl, countdownEl, scrubberEl, playBtn, muteCb, speedSel, signalLabelEl;
  let map, startLineLayers = [];
  let boats = {};            // deviceId -> { marker, trail, gps[], color, label }
  let ctx = null;
  let audio = null;
  let muted = false;
  let speed = 5;             // playback rate (1, 5, or 10)

  let t = T_START;
  let running = false;
  let lastFrameMs = 0;
  let firedSignals = new Set();
  let rafHandle = null;

  // ---------- DOM ----------

  function build() {
    rootEl = document.createElement('div');
    rootEl.className = 'sf-sr-overlay';
    rootEl.hidden = true;
    rootEl.innerHTML = `
      <div class="sf-sr-panel">
        <header class="sf-sr-header">
          <strong class="sf-sr-title">Start Review</strong>
          <span class="sf-sr-race-name"></span>
          <button class="sf-sr-close" aria-label="Close">×</button>
        </header>
        <div class="sf-sr-body">
          <div class="sf-sr-map"></div>
          <div class="sf-sr-countdown">−3:00</div>
          <div class="sf-sr-signal" aria-live="polite"></div>
        </div>
        <footer class="sf-sr-controls">
          <button class="sf-sr-play">▶ Play</button>
          <button class="sf-sr-replay" title="Restart from −3:00">⟲</button>
          <select class="sf-sr-speed" title="Playback speed">
            <option value="1">1×</option>
            <option value="5" selected>5×</option>
            <option value="10">10×</option>
          </select>
          <input type="range" class="sf-sr-scrubber"
                 min="${T_START}" max="${T_END}" step="1" value="${T_START}">
          <span class="sf-sr-time">−3:00</span>
          <label class="sf-sr-mute"><input type="checkbox"> Mute horns</label>
        </footer>
      </div>`;
    document.body.appendChild(rootEl);

    mapEl         = rootEl.querySelector('.sf-sr-map');
    countdownEl   = rootEl.querySelector('.sf-sr-countdown');
    signalLabelEl = rootEl.querySelector('.sf-sr-signal');
    scrubberEl    = rootEl.querySelector('.sf-sr-scrubber');
    playBtn       = rootEl.querySelector('.sf-sr-play');
    muteCb        = rootEl.querySelector('.sf-sr-mute input');
    speedSel      = rootEl.querySelector('.sf-sr-speed');

    rootEl.querySelector('.sf-sr-close').onclick  = NS.close;
    rootEl.querySelector('.sf-sr-replay').onclick = () => seek(T_START);
    playBtn.onclick = togglePlay;
    scrubberEl.addEventListener('input', () => seek(parseInt(scrubberEl.value, 10) || 0));
    muteCb.addEventListener('change', () => { muted = muteCb.checked; });
    speedSel.addEventListener('change', () => { speed = parseFloat(speedSel.value) || 1; });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !rootEl.hidden) NS.close();
    });
  }

  // ---------- Audio ----------

  function ensureAudio() {
    if (audio) return audio;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    audio = new AC();
    return audio;
  }

  function horn(whenSec, durSec, freq = 220) {
    if (!audio || muted) return;
    const start = audio.currentTime + Math.max(0, whenSec);
    const osc = audio.createOscillator();
    const filt = audio.createBiquadFilter();
    const gain = audio.createGain();
    osc.type = 'sawtooth';
    osc.frequency.value = freq;
    filt.type = 'lowpass';
    filt.frequency.value = 900;
    filt.Q.value = 0.7;
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(0.45, start + 0.04);
    gain.gain.setValueAtTime(0.45, start + Math.max(0.05, durSec - 0.06));
    gain.gain.exponentialRampToValueAtTime(0.0001, start + durSec);
    osc.connect(filt).connect(gain).connect(audio.destination);
    osc.start(start);
    osc.stop(start + durSec + 0.05);
  }

  function playPattern(pattern) {
    let off = 0;
    for (const ch of pattern) {
      if (ch === 'L')      { horn(off, 1.5); off += 1.7; }
      else if (ch === 'S') { horn(off, 0.4); off += 0.6; }
      else if (ch === ' ') { off += 0.3; }
    }
  }

  // ---------- Map ----------

  function ensureMap() {
    if (map) return;
    map = L.map(mapEl, { attributionControl: false, zoomControl: true });
    // Same Light Blue tiles as the main race map. The .tile-light-blue
    // CSS class (in race.css) inverts + hue-shifts the Carto dark_all
    // raster so it reads as a soft sky-blue water canvas.
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 19,
      className: 'tile-light-blue',
    }).addTo(map);
  }

  function clearMap() {
    for (const l of startLineLayers) l.remove();
    startLineLayers = [];
    for (const b of Object.values(boats)) {
      if (b.marker) b.marker.remove();
      if (b.trail)  b.trail.remove();
    }
    boats = {};
  }

  function drawStartLine(race) {
    const sl = race?.start_line;
    if (!sl || sl.pin_lat == null || sl.boat_lat == null) {
      // Fallback: fit course marks bounds, no special start-line drawing.
      const marks = (race?.course || []).filter((m) => m.lat != null);
      if (marks.length) {
        map.fitBounds(L.latLngBounds(marks.map((m) => [m.lat, m.lon])).pad(0.5),
                      { animate: false, maxZoom: 17 });
      } else {
        map.setView([42.34, -70.95], 13);
      }
      setTimeout(() => map.invalidateSize(), 50);
      return;
    }

    const pin  = [sl.pin_lat,  sl.pin_lon];
    const cmte = [sl.boat_lat, sl.boat_lon];
    const line = L.polyline([pin, cmte], { color: '#22d3ee', weight: 3, opacity: 0.95 }).addTo(map);
    const pinMarker  = L.circleMarker(pin,  { radius: 6, color: '#22d3ee', fillColor: '#22d3ee', fillOpacity: 1, weight: 2 })
                        .bindTooltip('Pin', { direction: 'right', offset: [10, 0] }).addTo(map);
    const cmteMarker = L.circleMarker(cmte, { radius: 6, color: '#22d3ee', fillColor: '#22d3ee', fillOpacity: 1, weight: 2 })
                        .bindTooltip('Committee', { direction: 'right', offset: [10, 0] }).addTo(map);
    startLineLayers.push(line, pinMarker, cmteMarker);

    // Tight frame on the line itself with modest padding so we can see
    // boats positioning around it. Cap zoom so we don't punch in past
    // tile resolution.
    map.fitBounds(L.latLngBounds(pin, cmte), {
      animate: false,
      padding: [60, 60],
      maxZoom: 17,
    });
    setTimeout(() => map.invalidateSize(), 50);
  }

  // ---------- Boats ----------

  function buildBoatIcon(color, rotationDeg, label) {
    // Mirrors createBoatIcon() in race-app.js — same arrow SVG so the
    // visual matches the main map exactly. Just no stats chip.
    const svg = `
      <svg class="boat-marker-svg" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"
           style="transform: rotate(${rotationDeg}deg);">
        <path d="M12 2 L20 20 L12 16 L4 20 Z"
              fill="${color}" stroke="white" stroke-width="1.5"/>
      </svg>`;
    const lab = label
      ? `<span class="boat-marker-label"><span class="bml-init" style="color:${color}">${label}</span></span>`
      : '';
    return L.divIcon({
      html: `<div class="boat-marker-wrap">${svg}${lab}</div>`,
      className: 'boat-marker',
      iconSize: null,
      iconAnchor: [12, 12],
    });
  }

  function rebuildBoats(data) {
    if (!data?.boats) return;
    for (const [deviceId, info] of Object.entries(data.boats)) {
      const meta = info.boat || {};
      const color = (ctx.BOAT_COLORS && ctx.BOAT_COLORS[deviceId]) || '#1f2d3d';
      const teamName = meta.team_name || meta.boat_name || deviceId;
      const initials = teamName.split(/\s+/).map((w) => w[0] || '').join('').slice(0, 3).toUpperCase();

      const gps = (info.sensors?.gps || []).map((p) => ({
        ms: new Date(p.t).getTime(),
        lat: p.lat, lon: p.lon,
        speed: p.speed_kn,
        course: p.course,
      })).filter((p) => Number.isFinite(p.ms) && p.lat && p.lon);
      gps.sort((a, b) => a.ms - b.ms);

      const icon = buildBoatIcon(color, 0, initials);
      const marker = L.marker([0, 0], { icon }).bindTooltip(teamName, { direction: 'right', offset: [12, 0] });
      const trail = L.polyline([], { color, weight: 3, opacity: 0.85 });

      boats[deviceId] = { marker, trail, gps, color, initials, teamName };
    }
  }

  function positionAt(gps, absMs) {
    if (!gps.length) return null;
    if (absMs < gps[0].ms) return null;
    if (absMs > gps[gps.length - 1].ms) return gps[gps.length - 1];
    let lo = 0, hi = gps.length - 1;
    while (lo < hi - 1) {
      const mid = (lo + hi) >> 1;
      if (gps[mid].ms <= absMs) lo = mid; else hi = mid;
    }
    const f = (absMs - gps[lo].ms) / Math.max(1, gps[hi].ms - gps[lo].ms);
    return {
      lat: gps[lo].lat + (gps[hi].lat - gps[lo].lat) * f,
      lon: gps[lo].lon + (gps[hi].lon - gps[lo].lon) * f,
      course: gps[lo].course,
    };
  }

  function trailFor(gps, absMs) {
    const cutoff = absMs - TRAIL_MS;
    const pts = [];
    for (let i = 0; i < gps.length; i++) {
      if (gps[i].ms < cutoff) continue;
      if (gps[i].ms > absMs) break;
      pts.push([gps[i].lat, gps[i].lon]);
    }
    return pts;
  }

  function renderBoats() {
    const startMs = ctx.currentRace?.start_time ? new Date(ctx.currentRace.start_time).getTime() : null;
    if (!startMs) return;
    const absMs = startMs + t * 1000;
    for (const b of Object.values(boats)) {
      const p = positionAt(b.gps, absMs);
      if (!p) {
        b.marker.remove();
        b.trail.remove();
        continue;
      }
      // Update arrow rotation from current course (heading proxy ≥ 2 kt).
      b.marker.setLatLng([p.lat, p.lon]);
      b.marker.setIcon(buildBoatIcon(b.color, p.course || 0, b.initials));
      if (!b.marker._map) b.marker.addTo(map);

      // Trail polyline, last 30 s ending at the cursor.
      const tr = trailFor(b.gps, absMs);
      b.trail.setLatLngs(tr);
      if (!b.trail._map && tr.length >= 2) b.trail.addTo(map);
      else if (b.trail._map && tr.length < 2) b.trail.remove();
    }
  }

  // ---------- Time ----------

  function fmtCountdown(secs) {
    const n = Math.round(secs);
    if (n === 0) return 'GUN';
    if (n < 0) {
      const a = -n;
      return `−${Math.floor(a / 60)}:${String(a % 60).padStart(2, '0')}`;
    }
    return `+${Math.floor(n / 60)}:${String(n % 60).padStart(2, '0')}`;
  }

  function updateCountdown() {
    countdownEl.textContent = fmtCountdown(t);
    countdownEl.classList.toggle('sf-sr-cd-final', t >= -10 && t < 0);
    countdownEl.classList.toggle('sf-sr-cd-gun', Math.abs(t) < 0.5);
    scrubberEl.value = String(Math.round(t));
    rootEl.querySelector('.sf-sr-time').textContent = fmtCountdown(t);
  }

  // Boundary-inclusive: a signal whose t is *at or before* currT and
  // hasn't fired yet triggers when currT >= s.t. firedSignals dedupes.
  // This fixes the −3:00 → −1:30 silence: those signals sit *at* the
  // playback start and the previous strict-greater test never fired.
  function maybeFireSignals(prevT, currT) {
    if (currT < prevT) return;
    for (let i = 0; i < SIGNALS.length; i++) {
      const s = SIGNALS[i];
      if (firedSignals.has(i)) continue;
      if (s.t >= prevT && s.t <= currT) {
        firedSignals.add(i);
        signalLabelEl.textContent = s.label;
        playPattern(s.pattern);
      }
    }
  }

  // ---------- Loop ----------

  function loop(now) {
    rafHandle = null;
    if (!running) return;
    const dt = lastFrameMs ? (now - lastFrameMs) / 1000 : 0;
    lastFrameMs = now;
    const prev = t;
    t += dt * speed;
    if (t >= T_END) {
      t = T_END;
      stop();
      maybeFireSignals(prev, t);
      updateCountdown();
      renderBoats();
      return;
    }
    maybeFireSignals(prev, t);
    updateCountdown();
    renderBoats();
    rafHandle = requestAnimationFrame(loop);
  }

  async function start() {
    if (running) return;
    // If we're parked exactly on a signal (the −3:00 case), fire it
    // immediately so the first horn isn't lost to the boundary.
    // maybeFireSignals(t, t) will catch any signal with s.t === t.
    if (audio?.state === 'suspended') {
      try { await audio.resume(); } catch {}
    }
    maybeFireSignals(t - 0.001, t);
    running = true;
    lastFrameMs = 0;
    playBtn.textContent = '⏸ Pause';
    rafHandle = requestAnimationFrame(loop);
  }
  function stop() {
    running = false;
    playBtn.textContent = '▶ Play';
    if (rafHandle) cancelAnimationFrame(rafHandle);
    rafHandle = null;
  }
  function togglePlay() {
    if (running) stop(); else start();
  }
  function seek(newT) {
    const clamped = Math.max(T_START, Math.min(T_END, newT));
    if (clamped < t) firedSignals.clear();
    t = clamped;
    lastFrameMs = 0;
    updateCountdown();
    renderBoats();
  }

  // ---------- Open / close ----------

  async function fetchPaddedRaceData(raceId) {
    const apiBase = ctx.apiBase || window.location.origin;
    const url = `${apiBase}/api/races/${raceId}/data?sensors=gps&pad_start=240&pad_end=120`;
    try {
      const r = await fetch(url);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return await r.json();
    } catch (e) {
      console.warn('[StartReview] padded fetch failed, using race-window data:', e);
      const out = { boats: {} };
      for (const id of Object.keys(ctx.boatLayers || {})) {
        const layer = ctx.boatLayers[id];
        out.boats[id] = {
          boat: ctx.raceData?.boats?.[id]?.boat || {},
          sensors: { gps: layer?.data || [] },
        };
      }
      return out;
    }
  }

  NS.open = async function (incomingCtx) {
    if (!rootEl) build();
    ctx = incomingCtx || {};
    const r = ctx.currentRace;
    if (!r || !r.start_time) {
      alert('This race has no start time set — cannot run start review.');
      return;
    }
    rootEl.querySelector('.sf-sr-race-name').textContent = ` — ${r.name || ''}`;
    rootEl.hidden = false;

    ensureAudio();
    ensureMap();
    clearMap();
    drawStartLine(r);

    t = T_START;
    speed = parseFloat(speedSel.value) || 5;
    firedSignals.clear();
    signalLabelEl.textContent = '';
    updateCountdown();
    stop();

    const data = await fetchPaddedRaceData(r.race_id);
    rebuildBoats(data);
    renderBoats();
  };

  NS.close = function () {
    if (!rootEl) return;
    stop();
    rootEl.hidden = true;
    if (audio) audio.suspend();
  };
})();
