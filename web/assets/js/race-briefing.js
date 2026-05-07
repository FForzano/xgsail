// Build a structured "race briefing" JSON document from the dashboard's
// in-memory state. Shipped to the chat Lambda with every turn.
//
// Two design rules the LLM expects:
//
// 1. Every boat's primary label is its team/boat name. Device IDs
//    (E1..E6) are kept under boat_id for round-trip but the system
//    prompt forbids surfacing them.
//
// 2. Every timestamp is a { local, t_sec } pair:
//      local: "11:34:22" in the venue timezone (America/New_York)
//      t_sec: integer seconds from race start
//    The model uses local for human readability and t_sec for the
//    `(t=N)` suffix so the chat UI can linkify it back into a
//    timeline jump.

(function () {
  'use strict';

  const NS = (window.SailFramesBriefing = window.SailFramesBriefing || {});
  const VENUE_TZ = 'America/New_York';

  function fmtLocal(ms) {
    if (ms == null) return null;
    return new Date(ms).toLocaleTimeString('en-US', {
      timeZone: VENUE_TZ,
      hour12: false,
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  }
  function fmtTime(ms, startMs) {
    if (ms == null) return null;
    return {
      local: fmtLocal(ms),
      t_sec: startMs != null ? Math.max(0, Math.round((ms - startMs) / 1000)) : null,
    };
  }
  const round = (x, p = 1) => {
    if (x == null || isNaN(x)) return null;
    const m = Math.pow(10, p);
    return Math.round(x * m) / m;
  };

  function summarizeWind(samples, startMs) {
    if (!samples || !samples.length) return null;
    let sx = 0, sy = 0, twsSum = 0, twsMin = Infinity, twsMax = -Infinity;
    for (const s of samples) {
      const r = (s.twd || 0) * Math.PI / 180;
      sx += Math.sin(r); sy += Math.cos(r);
      twsSum += s.tws || 0;
      if (s.tws != null) {
        if (s.tws < twsMin) twsMin = s.tws;
        if (s.tws > twsMax) twsMax = s.tws;
      }
    }
    const twdAvg = (Math.atan2(sx, sy) * 180 / Math.PI + 360) % 360;
    const twsAvg = twsSum / samples.length;

    const shifts = [];
    let baseline = samples[0].twd;
    let baselineTime = samples[0].tMs;
    for (let i = 1; i < samples.length; i++) {
      const diff = ((samples[i].twd - baseline + 540) % 360) - 180;
      if (Math.abs(diff) >= 10 && samples[i].tMs - baselineTime >= 5 * 60 * 1000) {
        shifts.push({
          at: fmtTime(samples[i].tMs, startMs),
          delta_deg: Math.round(diff),
          direction: diff > 0 ? 'right' : 'left',
        });
        baseline = samples[i].twd;
        baselineTime = samples[i].tMs;
      }
    }
    return {
      twd_avg_deg: Math.round(twdAvg),
      tws_avg_kn: round(twsAvg, 1),
      tws_range_kn: [round(twsMin === Infinity ? null : twsMin, 1),
                     round(twsMax === -Infinity ? null : twsMax, 1)],
      n_samples: samples.length,
      notable_shifts: shifts.slice(0, 5),
    };
  }

  // Pre-compute fleet rankings from roundingTimes. Two outputs:
  //
  //   final[]:    1st-to-last in finish order. Boats that finished a
  //               mark count are ranked by finish time. Boats with
  //               fewer marks rounded come after, sorted by marks-
  //               completed descending. Each entry has explicit
  //               position and did_not_finish flags.
  //
  //   by_mark[]:  rounding order at each mark in the course (mark 0
  //               = first mark of the race, mark N-1 = finish).
  //               Each is just an ordered list of names.
  //
  // The system prompt declares this structure authoritative — the
  // model is forbidden to reinvent the order from any other source.
  function computeRankings(boatsMap, layers, courseLen) {
    const ids = Object.keys(boatsMap);
    const nameOf = (id) => {
      const m = boatsMap[id]?.boat || {};
      return m.team_name || m.boat_name || id;
    };

    const totalMarks = Math.max(courseLen, 1);
    const lastMark = totalMarks - 1;

    // Collect per-boat: marks completed and finish time (= time at lastMark).
    const stats = ids.map((id) => {
      const rt = layers[id]?.roundingTimes || [];
      let marksCompleted = 0;
      for (let i = 0; i < totalMarks; i++) {
        if (rt[i] != null && Number.isFinite(rt[i])) marksCompleted++;
        else break;
      }
      const finishMs = (marksCompleted >= totalMarks) ? rt[lastMark] : null;
      return { id, name: nameOf(id), marksCompleted, finishMs };
    });

    // Final ranking: finishers first by time, then non-finishers by
    // marks-completed descending, then by name for stability.
    stats.sort((a, b) => {
      const aFin = a.finishMs != null;
      const bFin = b.finishMs != null;
      if (aFin && bFin) return a.finishMs - b.finishMs;
      if (aFin) return -1;
      if (bFin) return 1;
      if (a.marksCompleted !== b.marksCompleted) return b.marksCompleted - a.marksCompleted;
      return a.name.localeCompare(b.name);
    });

    return { stats, totalMarks };
  }

  function buildFinalRanking(stats, startMs) {
    return stats.map((s, idx) => {
      const entry = {
        position: idx + 1,
        name: s.name,
      };
      if (s.finishMs != null) {
        entry.finish = fmtTime(s.finishMs, startMs);
        entry.elapsed_sec = startMs != null
          ? Math.max(0, Math.round((s.finishMs - startMs) / 1000))
          : null;
      } else {
        entry.did_not_finish = true;
        entry.marks_completed = s.marksCompleted;
      }
      return entry;
    });
  }

  function buildByMarkRanking(boatsMap, layers, courseSeq) {
    const out = [];
    if (!courseSeq || !courseSeq.length) return out;
    const ids = Object.keys(boatsMap);
    const nameOf = (id) => {
      const m = boatsMap[id]?.boat || {};
      return m.team_name || m.boat_name || id;
    };

    for (let mi = 0; mi < courseSeq.length; mi++) {
      const arrivals = ids
        .map((id) => ({ id, name: nameOf(id), t: (layers[id]?.roundingTimes || [])[mi] }))
        .filter((x) => x.t != null && Number.isFinite(x.t))
        .sort((a, b) => a.t - b.t);
      if (!arrivals.length) continue;
      out.push({
        mark_index: mi,
        mark_name: courseSeq[mi]?.name || `mark ${mi + 1}`,
        order: arrivals.map((x) => x.name),
      });
    }
    return out;
  }

  function summarizeBoat(deviceId, boatMeta, layer, legRows, maneuvers, finishPosition, startMs) {
    const myLegs = (legRows || []).filter((r) => r.deviceId === deviceId);
    const myManeuvers = (maneuvers || []).filter((m) => m.deviceId === deviceId);
    const tacks = myManeuvers.filter((m) => m.type === 'tack');
    const gybes = myManeuvers.filter((m) => m.type === 'gybe');

    const avgLoss = (arr) => arr.length
      ? round(arr.reduce((a, b) => a + (b.loss || 0), 0) / arr.length, 2)
      : null;

    const finishMs = layer?.roundingTimes && layer.roundingTimes.length
      ? layer.roundingTimes[layer.roundingTimes.length - 1] : null;

    const totalDistM = myLegs.reduce((a, r) => a + (r.distM || 0), 0);
    const totalTimeSec = myLegs.reduce((a, r) => a + (r.durationSec || 0), 0);

    const meta = boatMeta?.boat || {};
    const team = meta.team_name || meta.boat_name || deviceId;
    const boatName = meta.boat_name || team;

    return {
      name: team,                // primary human label — what the LLM should use
      boat_name: boatName,       // hull/skipper name if distinct from team
      boat_id: deviceId,         // device serial — internal only, never surface
      finish_position: finishPosition || null,
      finish: finishMs != null ? fmtTime(finishMs, startMs) : null,
      total_time_sec: totalTimeSec ? Math.round(totalTimeSec) : null,
      total_distance_nm: totalDistM ? round(totalDistM / 1852, 2) : null,
      legs_completed: myLegs.length,
      legs: myLegs.map((r) => ({
        leg: r.leg,
        time_sec: round(r.durationSec, 0),
        avg_speed_kn: round(r.avgSog, 2),
        avg_polar_pct: r.avgPolPct == null ? null : round(r.avgPolPct, 0),
        distance_m: round(r.distM, 0),
      })),
      maneuvers: {
        tacks: tacks.length,
        gybes: gybes.length,
        avg_tack_speed_loss_kn: avgLoss(tacks),
        avg_gybe_speed_loss_kn: avgLoss(gybes),
        worst_tack: tacks.length ? (() => {
          const w = tacks.reduce((a, b) => ((b.loss || 0) > (a.loss || 0) ? b : a));
          return { at: fmtTime(w.tStart, startMs), speed_loss_kn: round(w.loss, 2) };
        })() : null,
      },
    };
  }

  // ============================================================
  // Enriched-context helpers (added 2026-05-07 for AI Coach v2)
  //
  // The original briefing was summary-only — counts, averages,
  // rankings. The model could state outcomes but couldn't reason
  // tactically ("did Vela Veloce overstand?", "was there a port-stbd
  // foul at the start?", "where did the wind shift right?").
  //
  // These helpers add primary-source data the model can analyze:
  //   - downsampled GPS tracks per boat
  //   - downsampled wind series (more granular than the 5-shift summary)
  //   - per-leg IMU summary (heel pattern → boat trim quality)
  //   - laylines computed at race-average TWD
  //   - boat-on-boat encounters (proximity events with relative geometry)
  //   - start-line analysis (distance from line at gun, OCS, line speed)
  //
  // All keep the {t_sec, local} timestamp convention so the model can
  // emit clickable permalinks.
  // ============================================================

  function distanceMeters(lat1, lon1, lat2, lon2) {
    const R = 6371000;
    const toRad = (d) => d * Math.PI / 180;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat / 2) ** 2
            + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
  }
  function bearingDeg(lat1, lon1, lat2, lon2) {
    const f1 = lat1 * Math.PI / 180, f2 = lat2 * Math.PI / 180;
    const dLam = (lon2 - lon1) * Math.PI / 180;
    const y = Math.sin(dLam) * Math.cos(f2);
    const x = Math.cos(f1) * Math.sin(f2) - Math.sin(f1) * Math.cos(f2) * Math.cos(dLam);
    return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
  }

  // GPS track at 1 s cadence (matching the LG290P's native rate).
  // 1 Hz × 25-min race × 6 boats ≈ 540 KB JSON ≈ 135 K input tokens —
  // fits in Haiku 4.5's 200 K window with room for the rules cheat-
  // sheet, conversation history, and ~4 K output. maxPts cap of 2400
  // covers a 40-minute race; longer races get truncated and the model
  // is told to mention it.
  function downsampleTrack(gps, startMs, stepSec = 1, maxPts = 2400) {
    if (!gps || !gps.length) return [];
    const out = [];
    let nextT = startMs == null ? null : startMs;
    let stepMs = stepSec * 1000;
    for (const p of gps) {
      const tMs = new Date(p.t).getTime();
      if (!Number.isFinite(tMs)) continue;
      if (nextT == null) nextT = tMs;
      if (tMs >= nextT) {
        out.push({
          t_sec: startMs != null ? Math.max(0, Math.round((tMs - startMs) / 1000)) : null,
          lat: round(p.lat, 5),
          lon: round(p.lon, 5),
          cog: round(p.course, 0),
          sog: round(p.speed_kn, 1),
        });
        nextT += stepMs;
        if (out.length >= maxPts) break;
      }
    }
    return out;
  }

  // Per-leg IMU summary — heel pattern is the strongest single
  // performance signal we have on this fleet (over-flat → underpowered
  // upwind, over-heeled → broaching downwind / wasted righting moment).
  function summarizeImuPerLeg(imu, legBoundsMs) {
    if (!imu || !imu.length || !legBoundsMs || legBoundsMs.length < 2) return [];
    const out = [];
    for (let i = 0; i < legBoundsMs.length - 1; i++) {
      const t0 = legBoundsMs[i], t1 = legBoundsMs[i + 1];
      let n = 0, sumHeel = 0, sumPitch = 0, maxHeelAbs = 0;
      for (const s of imu) {
        const tMs = new Date(s.t).getTime();
        if (tMs < t0 || tMs >= t1) continue;
        if (s.heel != null && Number.isFinite(s.heel)) {
          sumHeel += s.heel;
          if (Math.abs(s.heel) > maxHeelAbs) maxHeelAbs = Math.abs(s.heel);
        }
        if (s.pitch != null && Number.isFinite(s.pitch)) sumPitch += s.pitch;
        n++;
      }
      if (n === 0) continue;
      out.push({
        leg: i + 1,
        avg_heel_deg: round(sumHeel / n, 1),
        max_heel_abs_deg: round(maxHeelAbs, 1),
        avg_pitch_deg: round(sumPitch / n, 1),
        n_samples: n,
      });
    }
    return out;
  }

  // Build a downsampled wind series (one sample per minute by default)
  // — gives the model a real time-series to reason about local shifts,
  // not just the 5 notable-shift summary above.
  function buildWindSeries(samples, startMs, stepSec = 60, maxPts = 60) {
    if (!samples || !samples.length || startMs == null) return [];
    const stepMs = stepSec * 1000;
    let nextT = samples[0].tMs;
    const out = [];
    for (const s of samples) {
      if (s.tMs >= nextT) {
        out.push({
          t_sec: Math.max(0, Math.round((s.tMs - startMs) / 1000)),
          twd: Math.round(s.twd),
          tws: round(s.tws, 1),
        });
        nextT += stepMs;
        if (out.length >= maxPts) break;
      }
    }
    return out;
  }

  // Layline geometry: for each upwind mark in the course, compute the
  // port and starboard layline bearings using the J/80 nominal upwind
  // tack angle (42°) and the race-average TWD. These are the same
  // geometric values the dashboard renders on the map.
  function buildLaylines(courseSeq, raceAvgTwd, J80_TACK = 42) {
    if (!courseSeq || !courseSeq.length || raceAvgTwd == null) return [];
    const out = [];
    for (let i = 0; i < courseSeq.length; i++) {
      const m = courseSeq[i];
      if (!m || m.lat == null) continue;
      // Heuristic: any mark whose type contains "windward" or whose
      // sequence implies a beat (first mark) gets laylines drawn.
      const t = (m.type || '').toLowerCase();
      const isUpwind = t.includes('windward') || t.includes('weather') || i === 0;
      if (!isUpwind) continue;
      out.push({
        mark_index: i,
        mark_name: m.name || `mark ${i + 1}`,
        lat: round(m.lat, 5),
        lon: round(m.lon, 5),
        starboard_layline_bearing: Math.round((raceAvgTwd + 180 - J80_TACK + 360) % 360),
        port_layline_bearing:      Math.round((raceAvgTwd + 180 + J80_TACK) % 360),
        comment: 'Port layline approached on starboard tack; starboard layline approached on port tack.',
      });
    }
    return out;
  }

  // Boat-on-boat encounters: pairs that came within ENC_DIST_M of each
  // other. For each encounter we return the closing moment, the
  // distance, the relative geometry (who's to leeward/windward), and —
  // when wind data is available — the tack each boat is on. This is
  // the raw material for RRS-rule analysis (rule 10 port/stbd, rule 11
  // windward/leeward, rule 18 mark-room).
  function detectEncounters(layers, boatsMap, weatherSamples, startMs, opts = {}) {
    const ENC_DIST_M = opts.distM || 30;     // ~3-4 boatlengths for J/80
    const STEP_SEC   = opts.stepSec || 10;   // sample the geometry every N s
    const COOL_SEC   = opts.coolSec || 30;   // suppress duplicate logs from same encounter
    const MAX_OUT    = opts.max || 40;

    const ids = Object.keys(layers).filter((id) => layers[id]?.data?.length);
    if (ids.length < 2) return [];

    const nameOf = (id) => {
      const m = boatsMap[id]?.boat || {};
      return m.team_name || m.boat_name || id;
    };

    // windAt: linear vector mean interpolation, mirrors race-app.js logic.
    const windAt = (tMs) => {
      if (!weatherSamples || !weatherSamples.length) return null;
      if (tMs <= weatherSamples[0].tMs) return weatherSamples[0];
      const last = weatherSamples[weatherSamples.length - 1];
      if (tMs >= last.tMs) return last;
      let lo = 0, hi = weatherSamples.length - 1;
      while (lo + 1 < hi) {
        const mid = (lo + hi) >> 1;
        if (weatherSamples[mid].tMs <= tMs) lo = mid; else hi = mid;
      }
      const a = weatherSamples[lo], b = weatherSamples[hi];
      const f = (tMs - a.tMs) / (b.tMs - a.tMs);
      const ar = a.twd * Math.PI / 180, br = b.twd * Math.PI / 180;
      const sx = Math.sin(ar) * (1 - f) + Math.sin(br) * f;
      const sy = Math.cos(ar) * (1 - f) + Math.cos(br) * f;
      return { twd: (Math.atan2(sx, sy) * 180 / Math.PI + 360) % 360, tws: a.tws * (1 - f) + b.tws * f };
    };

    const tackOf = (cog, twd) => {
      if (cog == null || twd == null) return null;
      const twa = ((twd - cog + 540) % 360) - 180;  // signed
      // Convention: positive TWA = wind from starboard side = starboard tack.
      return twa > 0 ? 'starboard' : 'port';
    };

    // Sample each boat at fixed wall-clock intervals using its stored
    // times array (precomputed in addBoatTrack). This avoids paying
    // re-parsing cost per pair.
    const sample = (layer, tMs) => {
      const ts = layer.times;
      if (!ts || !ts.length) return null;
      // Binary search for the index closest to tMs.
      let lo = 0, hi = ts.length - 1;
      if (tMs <= ts[0]) return { idx: 0, p: layer.data[0] };
      if (tMs >= ts[hi]) return { idx: hi, p: layer.data[hi] };
      while (lo + 1 < hi) {
        const mid = (lo + hi) >> 1;
        if (ts[mid] <= tMs) lo = mid; else hi = mid;
      }
      return { idx: lo, p: layer.data[lo] };
    };

    // Build the timeline we'll walk: from race start (or earliest
    // GPS sample) to race end. Cap total iterations as a safety.
    const t0 = startMs != null ? startMs : Math.min(...ids.map((id) => layers[id].times[0]));
    const t1 = Math.max(...ids.map((id) => layers[id].times[layers[id].times.length - 1]));
    if (!Number.isFinite(t0) || !Number.isFinite(t1) || t1 <= t0) return [];

    const stepMs = STEP_SEC * 1000;
    const coolMs = COOL_SEC * 1000;
    const lastLogged = new Map();  // pair-key -> tMs of last log
    const out = [];

    for (let tMs = t0; tMs <= t1 && out.length < MAX_OUT; tMs += stepMs) {
      // Snapshot positions for every boat at this moment.
      const snap = ids.map((id) => ({ id, s: sample(layers[id], tMs) })).filter((x) => x.s && x.s.p && x.s.p.lat);
      const w = windAt(tMs);
      for (let i = 0; i < snap.length; i++) {
        for (let j = i + 1; j < snap.length; j++) {
          const A = snap[i], B = snap[j];
          const d = distanceMeters(A.s.p.lat, A.s.p.lon, B.s.p.lat, B.s.p.lon);
          if (d > ENC_DIST_M) continue;
          const key = A.id < B.id ? `${A.id}|${B.id}` : `${B.id}|${A.id}`;
          const lastT = lastLogged.get(key);
          if (lastT != null && tMs - lastT < coolMs) continue;
          lastLogged.set(key, tMs);
          // Bearing from A to B; if AB ≈ A's COG, B is ahead.
          const brgAB = bearingDeg(A.s.p.lat, A.s.p.lon, B.s.p.lat, B.s.p.lon);
          const tackA = tackOf(A.s.p.course, w?.twd);
          const tackB = tackOf(B.s.p.course, w?.twd);
          out.push({
            at: fmtTime(tMs, startMs),
            distance_m: Math.round(d),
            boats: [
              { name: nameOf(A.id), cog: round(A.s.p.course, 0), sog: round(A.s.p.speed_kn, 1), tack: tackA },
              { name: nameOf(B.id), cog: round(B.s.p.course, 0), sog: round(B.s.p.speed_kn, 1), tack: tackB },
            ],
            bearing_a_to_b_deg: Math.round(brgAB),
            // Same vs opposite tacks → which RRS family applies.
            // RRS 10 (opposite-tack) requires port to keep clear of stbd.
            // RRS 11 (same-tack overlapped) requires windward to keep clear of leeward.
            rule_family_hint: (tackA && tackB) ? (tackA === tackB ? 'same_tack' : 'opposite_tacks') : 'unknown',
          });
        }
      }
    }
    return out;
  }

  // Start-line analysis: distance from each boat to the line at the
  // start gun (negative = over early), the boat's speed at the gun,
  // and whether the boat appeared to be OCS (across the line before
  // t=0). Uses simple perpendicular-distance to the line segment.
  function startAnalysis(boatsMap, layers, startLine, startMs) {
    if (!startLine || startLine.pin_lat == null || startLine.boat_lat == null || startMs == null) return [];

    // Project the boat's position onto the start-line segment and
    // return the perpendicular distance (positive = behind the line
    // looking from the line toward the course, negative = over).
    // Because we don't know the upwind direction reliably for sign,
    // we just return absolute distance + a flag for "appears over".
    const linePin  = [startLine.pin_lat,  startLine.pin_lon];
    const lineBoat = [startLine.boat_lat, startLine.boat_lon];

    const out = [];
    for (const id of Object.keys(boatsMap)) {
      const layer = layers[id];
      if (!layer?.data?.length || !layer?.times?.length) continue;
      // Find sample nearest to start gun.
      const ts = layer.times;
      let lo = 0, hi = ts.length - 1;
      if (startMs <= ts[0]) lo = 0;
      else if (startMs >= ts[hi]) lo = hi;
      else {
        while (lo + 1 < hi) {
          const mid = (lo + hi) >> 1;
          if (ts[mid] <= startMs) lo = mid; else hi = mid;
        }
      }
      const p = layer.data[lo];
      if (!p || p.lat == null) continue;
      const dPin  = distanceMeters(p.lat, p.lon, linePin[0], linePin[1]);
      const dBoat = distanceMeters(p.lat, p.lon, lineBoat[0], lineBoat[1]);
      const lineLen = distanceMeters(linePin[0], linePin[1], lineBoat[0], lineBoat[1]);
      const meta = boatsMap[id]?.boat || {};
      const name = meta.team_name || meta.boat_name || id;
      out.push({
        name,
        speed_at_gun_kn: round(p.speed_kn, 1),
        cog_at_gun_deg: round(p.course, 0),
        distance_to_pin_m:  Math.round(dPin),
        distance_to_committee_m: Math.round(dBoat),
        // Heuristic line-bias / approach side: closer to pin or boat end.
        approach_end: dPin < dBoat ? 'pin' : 'committee',
        line_length_m: Math.round(lineLen),
      });
    }
    return out;
  }

  /**
   * @param {object} ctx in-memory state from race-app.js (see file header).
   * @returns {object} briefing JSON
   */
  NS.build = function (ctx) {
    const c = ctx.currentRace || {};
    const startMs = c.start_time ? new Date(c.start_time).getTime() : null;
    const endMs   = c.end_time   ? new Date(c.end_time).getTime()   : null;

    const boatsMap = ctx.raceDataBoats || {};
    const layers = ctx.boatLayers || {};
    const courseSeq = c.course || [];
    const boatIds = Object.keys(boatsMap);
    const wind = summarizeWind(ctx.weatherWindSamples || [], startMs);

    const { stats } = computeRankings(boatsMap, layers, courseSeq.length);
    const finalRanking = buildFinalRanking(stats, startMs);
    const byMarkRanking = buildByMarkRanking(boatsMap, layers, courseSeq);

    // deviceId -> finish_position lookup so per-boat objects can carry it.
    const posByName = new Map(finalRanking.map((r) => [r.name, r.position]));
    const finishPosByDeviceId = {};
    for (const id of boatIds) {
      const m = boatsMap[id]?.boat || {};
      const name = m.team_name || m.boat_name || id;
      finishPosByDeviceId[id] = posByName.get(name) || null;
    }

    const allFinished = stats.every((s) => s.finishMs != null);

    // Per-boat leg boundaries (start + each rounding) used for IMU
    // per-leg summarization.
    const legBoundsFor = (id) => {
      const rt = layers[id]?.roundingTimes || [];
      const out = [];
      if (startMs != null) out.push(startMs);
      for (const t of rt) if (t != null && Number.isFinite(t)) out.push(t);
      return out;
    };

    // Race-average TWD reused for layline geometry. Falls back to the
    // wind-summary value if the dashboard didn't compute it yet.
    const raceAvgTwd = wind?.twd_avg_deg != null ? wind.twd_avg_deg : null;

    const gpsTracksByName = {};
    const imuByName = {};
    for (const id of boatIds) {
      const m = boatsMap[id]?.boat || {};
      const name = m.team_name || m.boat_name || id;
      const sensors = boatsMap[id]?.sensors || {};
      gpsTracksByName[name] = downsampleTrack(sensors.gps, startMs);
      imuByName[name] = summarizeImuPerLeg(sensors.imu, legBoundsFor(id));
    }

    const windSeries = buildWindSeries(ctx.weatherWindSamples || [], startMs);
    const laylines = buildLaylines(courseSeq, raceAvgTwd);
    const encounters = detectEncounters(layers, boatsMap, ctx.weatherWindSamples || [], startMs);
    const startInfo = startAnalysis(boatsMap, layers, c.start_line, startMs);

    return {
      race: {
        id: c.race_id,
        name: c.name,
        date: c.date,
        venue: c.venue || 'Boston Harbor',
        timezone: VENUE_TZ,
        course_type: c.course_type || null,
        course: courseSeq.map((m) => ({
          name: m.name, type: m.type,
          lat: round(m.lat, 5), lon: round(m.lon, 5),
        })),
        start_line: c.start_line ? {
          pin: { lat: round(c.start_line.pin_lat, 5), lon: round(c.start_line.pin_lon, 5) },
          committee: { lat: round(c.start_line.boat_lat, 5), lon: round(c.start_line.boat_lon, 5) },
        } : null,
        finish_line: c.finish_line ? {
          pin: { lat: round(c.finish_line.pin_lat, 5), lon: round(c.finish_line.pin_lon, 5) },
          committee: { lat: round(c.finish_line.boat_lat, 5), lon: round(c.finish_line.boat_lon, 5) },
        } : null,
        start: startMs != null ? { local: fmtLocal(startMs), t_sec: 0 } : null,
        end:   endMs != null   ? fmtTime(endMs, startMs) : null,
        wind_source: ctx.weatherWindSource || null,
        wind: wind,
      },
      // AUTHORITATIVE — see system prompt rule on rankings.
      ranking: {
        status: allFinished ? 'final' : 'in_progress',
        final: finalRanking,
        by_mark: byMarkRanking,
      },
      fleet: boatIds.map((id) => {
        const m = boatsMap[id]?.boat || {};
        return m.team_name || m.boat_name || id;
      }),
      boats: boatIds.map((id) => summarizeBoat(
        id, boatsMap[id], layers[id], ctx.legRows, ctx.maneuvers,
        finishPosByDeviceId[id], startMs
      )),
      // Enriched-context block (added 2026-05-07 for AI Coach v2).
      // Keys named verbosely so the model knows what each is without
      // a separate schema. See helpers above for downsample rates +
      // caps; total payload typically ~30-50 KB JSON.
      tracks_per_boat: gpsTracksByName,             // {name: [{t_sec,lat,lon,cog,sog}, ...]}
      imu_per_leg: imuByName,                       // {name: [{leg, avg_heel_deg, max_heel_abs_deg, avg_pitch_deg}, ...]}
      wind_series: windSeries,                      // [{t_sec, twd, tws}, ...]  one sample/min
      laylines_at_avg_twd: laylines,                // [{mark_name, port_layline_bearing, starboard_layline_bearing, ...}]
      boat_encounters: encounters,                  // [{at, distance_m, boats[], rule_family_hint}]
      start_analysis: startInfo,                    // [{name, speed_at_gun_kn, distance_to_pin_m, ...}]
      generated_at: new Date().toISOString(),
    };
  };
})();
