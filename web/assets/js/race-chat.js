// Collapsible chat panel for race.html. Streams from the SailFrames
// chat Lambda (Function URL). Conversation lives in memory only;
// refresh = new chat.
//
// Wiring: race-app.js calls SailFramesChat.attach(getCtx) once after
// the race has loaded, where getCtx() returns the in-memory state
// SailFramesBriefing.build expects. The chat panel rebuilds the
// briefing on each turn from getCtx() so it always reflects current
// dashboard state (e.g. if the user changes wind source).

(function () {
  'use strict';

  const NS = (window.SailFramesChat = window.SailFramesChat || {});
  // Endpoint behind API Gateway. NOTE: API Gateway has a hard 29 s
  // integration timeout (CLAUDE.md gotcha #10). Long Sonnet / Opus
  // turns may hit HTTP 503 {"message":"Service Unavailable"}. Until
  // the chat Lambda's Function URL is unblocked from the account-
  // level Lambda Public Access Block (AWS Console action), short
  // turns work fine; the Full Debrief chip may time out.
  // Override via window.SAILFRAMES_CHAT_URL.
  const ENDPOINT = window.SAILFRAMES_CHAT_URL ||
    'https://rnngzx7flk.execute-api.us-east-1.amazonaws.com/api/chat';

  let panelEl = null;
  let logEl = null;
  let inputEl = null;
  let boatSelectEl = null;
  let getCtx = null;
  const messages = [];        // { role, content }
  let streaming = false;

  function el(tag, cls, html) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }

  // Quick-action chips. Each fires a pre-baked prompt to give the
  // user a one-click path to common coaching analyses without
  // having to remember the magic words. `requiresBoat: true` chips
  // are only enabled when the user has identified their boat in
  // the "I'm" picker (otherwise the system prompt won't switch into
  // coach mode and the answer is generic).
  const QUICK_ACTIONS = [
    {
      key: 'debrief',
      label: '📋 Full debrief',
      requiresBoat: true,
      // intent="debrief" tells the Lambda to route this turn to
      // Opus 4.7 (vs Sonnet 4.6 default). Premium model for the one
      // chip that actually justifies the cost — multi-section,
      // multi-rule output with full reasoning depth.
      intent: 'debrief',
      prompt: 'Give me the full coach-mode debrief for my boat — bottom line, what worked, what cost time (with permalinks and the data that proves it), any rule encounters, and two concrete things to try next race.',
    },
    {
      key: 'rules',
      label: '⚖️ Rule check',
      prompt: 'Walk through the boat_encounters list and flag every potential racing-rules infringement you can see. For each, cite the RRS rule number, the moment in HH:MM:SS (t=N) form, who had right of way, and the geometric evidence. Distinguish clear-cut from ambiguous calls.',
    },
    {
      key: 'start',
      label: '🚩 Start analysis',
      prompt: 'Analyse how each boat started: line bias and approach end (pin vs committee), distance from the line at the gun, line speed at the gun, and any boats that look like they were OCS. Rank the starts best to worst with a short reason for each.',
    },
    {
      key: 'wind',
      label: '💨 Wind shifts',
      prompt: 'Identify the significant wind shifts during this race (use the wind_series). For each shift give the moment in HH:MM:SS (t=N), the magnitude in degrees, the direction, and which boats responded best vs worst (cross-reference against tracks_per_boat and any tacks in the maneuvers list).',
    },
    {
      key: 'marks',
      label: '🎯 Mark roundings',
      prompt: 'Review every mark rounding for the fleet. Use the by_mark ranking to see arrival order, then look at tracks_per_boat around each rounding to assess quality (inside/outside, speed retained, time lost or gained). Call out the cleanest and the costliest roundings of the race.',
    },
    {
      key: 'encounters',
      label: '🤝 Close encounters',
      prompt: 'Summarise the boat-on-boat close encounters (boat_encounters). Group them into tactical wins, tactical losses, and neutral crosses. For each, name the boats, the moment, the configuration (port/stbd, leeward/windward), and the outcome.',
    },
    {
      key: 'highlights',
      label: '🌊 Best & worst moments',
      prompt: 'Pick the 3 best and 3 worst tactical moments of this race across the entire fleet. For each, name the boat(s), the moment in HH:MM:SS (t=N), what happened, and the data that proves it (heel angle, %polar, layline distance, encounter geometry, etc.).',
    },
    {
      // Dynamic chip — asks the user for a rule number on click,
      // then sends a prompt that (1) explains the rule in plain
      // language and (2) scans the race for moments where the rule
      // could apply.
      key: 'rule-lookup',
      label: '📖 Look up RRS…',
      tooltip: 'Ask about a specific Racing Rule (e.g. 10, 18.2, 44.2). I explain it, then check this race for situations where it applies.',
      promptFn: () => {
        const raw = window.prompt(
          'Which Racing Rule? (e.g. 10, 11, 18.2, 44.2)\n\nLeave blank to cancel.'
        );
        if (!raw) return null;
        // Accept "10", "RRS 10", "rule 18.2(b)" etc. Strip the prefix
        // and any whitespace so we end up with just the number.
        const n = String(raw).trim().replace(/^(rrs|rule)\s*/i, '').trim();
        if (!n) return null;
        return (
          `Explain RRS ${n} from the Racing Rules of Sailing 2025-2028 ` +
          `in plain language — what it requires, who it applies to, and ` +
          `the typical situation. Then walk through this race's ` +
          `boat_encounters list (and tracks_per_boat where useful) and ` +
          `identify every moment where RRS ${n} could apply. For each: ` +
          `cite the moment in HH:MM:SS (t=N) form, name the boats and ` +
          `their tacks/configuration, and give your read on whether the ` +
          `rule was followed or potentially infringed.`
        );
      },
    },
  ];

  function build(ctx) {
    const root = el('div', 'sf-chat-root');
    root.innerHTML = `
      <div class="sf-chat-panel" hidden>
        <div class="sf-chat-header">
          <strong>Ask an AI Coach</strong>
          <label class="sf-chat-asas">
            <span>I'm</span>
            <select class="sf-chat-boat">
              <option value="">a spectator</option>
            </select>
          </label>
          <button class="sf-chat-close" aria-label="Close">×</button>
        </div>
        <div class="sf-chat-quickactions" role="toolbar" aria-label="Quick actions">
          ${QUICK_ACTIONS.map((qa) => `
            <button type="button" class="sf-chat-chip"
                    data-qa="${qa.key}"
                    data-requires-boat="${qa.requiresBoat ? '1' : '0'}"
                    title="${escapeAttr(qa.tooltip || qa.prompt || '')}">${qa.label}</button>
          `).join('')}
        </div>
        <div class="sf-chat-log"></div>
        <form class="sf-chat-input-row">
          <input type="text" class="sf-chat-input"
                 placeholder="Ask anything about this race…" autocomplete="off">
          <button type="submit" class="sf-chat-send">Send</button>
        </form>
        <div class="sf-chat-foot">
          <span>Answers come from race data only. Powered by Claude.</span>
          <button type="button" class="sf-chat-close-btn">Close</button>
        </div>
      </div>`;
    document.body.appendChild(root);

    panelEl = root.querySelector('.sf-chat-panel');
    logEl = root.querySelector('.sf-chat-log');
    inputEl = root.querySelector('.sf-chat-input');
    boatSelectEl = root.querySelector('.sf-chat-boat');

    const closeFn = () => { panelEl.hidden = true; };
    root.querySelector('.sf-chat-close').onclick = closeFn;
    root.querySelector('.sf-chat-close-btn').onclick = closeFn;
    enableDrag(panelEl, root.querySelector('.sf-chat-header'));
    root.querySelector('.sf-chat-input-row').onsubmit = (e) => {
      e.preventDefault();
      send(inputEl.value);
    };

    // Wire up quick-action chips. Each click fires the pre-baked
    // prompt straight into send() — no edit step. User can still
    // type a custom question in the input row.
    root.querySelectorAll('.sf-chat-chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        const qa = QUICK_ACTIONS.find((x) => x.key === chip.dataset.qa);
        if (!qa) return;
        if (qa.requiresBoat && !boatSelectEl.value) {
          // Nudge the user to pick their boat instead of silently sending
          // a debrief that the model can't actually personalise.
          boatSelectEl.focus();
          flashElement(boatSelectEl);
          return;
        }
        // promptFn chips compute their prompt at click time (e.g. they
        // need user input). Returning null cancels.
        const text = qa.promptFn ? qa.promptFn() : qa.prompt;
        if (!text) return;
        send(text, { intent: qa.intent || null });
      });
    });

    // Disable boat-required chips when the picker is on "spectator".
    const refreshChipState = () => {
      const haveBoat = !!boatSelectEl.value;
      root.querySelectorAll('.sf-chat-chip[data-requires-boat="1"]').forEach((chip) => {
        chip.disabled = !haveBoat;
        const qa = QUICK_ACTIONS.find((x) => x.key === chip.dataset.qa);
        chip.title = haveBoat
          ? (qa?.tooltip || qa?.prompt || '')
          : 'Pick your boat in the "I\'m" selector to enable coach-mode';
      });
    };
    boatSelectEl.addEventListener('change', refreshChipState);

    populateBoatSelect();
    refreshChipState();
  }

  function escapeAttr(s) {
    return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
  }
  function flashElement(el) {
    el.classList.add('sf-chat-flash');
    setTimeout(() => el.classList.remove('sf-chat-flash'), 800);
  }

  // Refresh the "I am" dropdown from the current ctx fleet. Called both
  // at build time and on every open() — the race may not be loaded yet
  // when the panel is first built.
  function populateBoatSelect() {
    if (!boatSelectEl || !getCtx) return;
    const prev = boatSelectEl.value;
    const c = getCtx() || {};
    const boats = c.raceDataBoats || c.boats || {};
    boatSelectEl.innerHTML = '<option value="">a spectator</option>';
    for (const id of Object.keys(boats)) {
      const meta = boats[id]?.boat || boats[id] || {};
      const team = meta.team_name || null;
      const boatName = meta.boat_name || meta.hull || null;
      // Format: "on Vela Veloce team (boat Wizard)"
      // If team and boat name are the same (or one is missing), collapse.
      let label;
      if (team && boatName && team !== boatName) {
        label = `on ${team} team (boat ${boatName})`;
      } else if (team) {
        label = `on ${team}`;
      } else if (boatName) {
        label = `on ${boatName}`;
      } else {
        label = `on ${id}`;
      }
      const opt = document.createElement('option');
      opt.value = id;
      opt.textContent = label;
      boatSelectEl.appendChild(opt);
    }
    // Preserve user selection across refreshes when possible.
    if (prev && [...boatSelectEl.options].some((o) => o.value === prev)) {
      boatSelectEl.value = prev;
    }
  }

  // Drag-to-move via the header. Skips when the user is interacting
  // with form controls (select, button, label) inside the header so
  // the close button and "I'm" picker still work normally. Pins the
  // panel via left/top once dragged so the original right/bottom
  // anchor doesn't keep pulling it back.
  function enableDrag(panel, handle) {
    if (!panel || !handle) return;
    let startX = 0, startY = 0, startLeft = 0, startTop = 0, dragging = false;

    handle.addEventListener('mousedown', (e) => {
      const tag = (e.target && e.target.tagName) || '';
      if (/^(SELECT|OPTION|BUTTON|INPUT)$/.test(tag)) return;
      if (e.target.closest && e.target.closest('label,button,select,input')) return;

      // Convert from right/bottom anchor to left/top once at drag start.
      const r = panel.getBoundingClientRect();
      panel.style.left = `${r.left}px`;
      panel.style.top = `${r.top}px`;
      panel.style.right = 'auto';
      panel.style.bottom = 'auto';

      startX = e.clientX; startY = e.clientY;
      startLeft = r.left; startTop = r.top;
      dragging = true;
      handle.style.cursor = 'grabbing';
      e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
      if (!dragging) return;
      const dx = e.clientX - startX, dy = e.clientY - startY;
      const r = panel.getBoundingClientRect();
      const maxLeft = window.innerWidth - r.width;
      const maxTop  = window.innerHeight - r.height;
      panel.style.left = `${Math.max(0, Math.min(startLeft + dx, maxLeft))}px`;
      panel.style.top  = `${Math.max(0, Math.min(startTop + dy, maxTop))}px`;
    });

    document.addEventListener('mouseup', () => {
      if (!dragging) return;
      dragging = false;
      handle.style.cursor = '';
    });
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  // Build an external link to the official Racing Rules of Sailing
  // 2025-2028. World Sailing publishes the PDF without stable
  // per-rule deep-links, so we route through a Google search scoped
  // to the authoritative sources. Always opens in a new tab so the
  // user doesn't lose their chat context.
  function ruleHref(ruleNumber) {
    const q = encodeURIComponent(
      `Racing Rules of Sailing 2025-2028 Rule ${ruleNumber}`
    );
    return `https://www.google.com/search?q=${q}`;
  }

  // Make every "t=N" token AND every "RRS N" / "Rule N" citation in
  // the model's reply clickable.
  //
  // Time linkification: two passes so "HH:MM:SS (t=N)" keeps the
  // human time as link text, and any bare/standalone "t=N" still
  // gets linked (rendered as a "[+M:SS]" offset).
  //
  // Rule linkification: matches "RRS 10", "RRS 18.2(b)", or
  // "Rule 10" / "rule 18", and wraps in an out-of-band link to the
  // official rule book. Skips matches inside an existing <a> tag
  // (the time pass runs first so this guard catches its output).
  function linkifyTimes(rawText) {
    let s = escapeHtml(rawText);
    // Pass 1: "HH:MM[:SS] (t=N)" → link the time, drop the marker.
    s = s.replace(
      /(\d{1,2}:\d{2}(?::\d{2})?)\s*\(t=(\d+)\)/g,
      (_, time, t) => {
        const n = parseInt(t, 10);
        return `<a href="#" class="sf-chat-tlink" data-t="${n}">${time}</a>`;
      }
    );
    // Pass 2: any remaining "(t=N)" or bare "t=N" → "[+M:SS]" offset.
    // href="#" so we don't accidentally re-match the previous pass's output.
    s = s.replace(
      /\(?\bt=(\d+)\)?/g,
      (_, t) => {
        const n = parseInt(t, 10);
        const mm = Math.floor(n / 60), ss = n % 60;
        const label = `[+${mm}:${String(ss).padStart(2, '0')}]`;
        return `<a href="#" class="sf-chat-tlink" data-t="${n}">${label}</a>`;
      }
    );
    // Pass 3: RRS rule citations. Match "RRS N" or "Rule N" with an
    // optional sub-rule decoration like "18.2(b)" or "44.2".
    // Trailing punctuation isn't captured so it stays outside the link.
    s = s.replace(
      /\b(RRS|Rule|rule)\s+(\d{1,3}(?:\.\d+)?(?:\([a-z]\))?)/g,
      (full, prefix, ruleNum) => {
        const url = ruleHref(ruleNum);
        return `<a href="${url}" class="sf-chat-rulelink" target="_blank" rel="noopener" title="Open Racing Rules of Sailing 2025-2028, Rule ${ruleNum}">${prefix} ${ruleNum}</a>`;
      }
    );
    return s;
  }

  function bindTimeLinks(el) {
    el.querySelectorAll('a.sf-chat-tlink').forEach((a) => {
      if (a.dataset.sfBound) return;
      a.dataset.sfBound = '1';
      a.addEventListener('click', (e) => {
        e.preventDefault();
        const t = parseInt(a.dataset.t, 10);
        if (window.SailFramesRace?.seekTo) window.SailFramesRace.seekTo(t);
        const u = new URL(location.href);
        u.searchParams.set('t', t);
        history.replaceState({}, '', u);
      });
    });
  }

  function pushMessage(role, text) {
    const m = el('div', `sf-chat-msg sf-chat-msg-${role}`);
    if (role === 'assistant' && text) {
      m.innerHTML = linkifyTimes(text);
      bindTimeLinks(m);
    } else {
      m.textContent = text;
    }
    logEl.appendChild(m);
    logEl.scrollTop = logEl.scrollHeight;
    return m;
  }

  function setAssistantText(el, text) {
    el.innerHTML = linkifyTimes(text);
    bindTimeLinks(el);
  }

  async function send(text, opts) {
    text = (text || '').trim();
    if (!text || streaming) return;
    streaming = true;
    inputEl.value = '';
    pushMessage('user', text);
    messages.push({ role: 'user', content: text });

    const replyEl = pushMessage('assistant', '');
    replyEl.textContent = '…';
    let buf = '';

    const ctx = getCtx();
    const briefing = window.SailFramesBriefing.build(ctx);

    // Send the team/boat NAME (not the device id) so the model
    // never sees E1..E6 in the user_boat field either.
    const selectedId = boatSelectEl.value;
    let userBoat = null;
    if (selectedId) {
      const m = (ctx.raceDataBoats && ctx.raceDataBoats[selectedId]?.boat) || {};
      userBoat = m.team_name || m.boat_name || selectedId;
    }

    // intent (optional) maps server-side to a stronger model. Today
    // only "debrief" is mapped → Claude Opus 4.7. All other turns use
    // the Sonnet 4.6 default. Keeping this server-side prevents
    // arbitrary model abuse from the client.
    const reqBody = {
      race_briefing: briefing,
      user_boat: userBoat,
      messages: messages,
    };
    if (opts && opts.intent) reqBody.intent = opts.intent;

    try {
      const resp = await fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reqBody),
      });
      if (!resp.ok) {
        const errBody = await resp.text();
        replyEl.textContent = `Error: HTTP ${resp.status} ${errBody.slice(0, 200)}`;
        streaming = false;
        return;
      }
      const data = await resp.json();
      buf = data.text || '';
      if (buf) setAssistantText(replyEl, buf);
      else replyEl.textContent = '(no response)';
      messages.push({ role: 'assistant', content: buf });
    } catch (e) {
      replyEl.textContent = `Error: ${e.message}`;
    } finally {
      streaming = false;
    }
  }

  /**
   * @param {function():object} contextFn  returns the current dashboard
   *   state for SailFramesBriefing.build (currentRace, boats, legRows,
   *   maneuvers, windSamples, windSource, finishOrder).
   */
  NS.attach = function (contextFn) {
    getCtx = contextFn;
    const init = () => {
      if (!panelEl) build();
      // Wire up the toolbar button if it's there.
      const btn = document.getElementById('btn-race-coach');
      if (btn && !btn.dataset.sfChatBound) {
        btn.dataset.sfChatBound = '1';
        btn.addEventListener('click', () => NS.open());
      }
    };
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
    } else {
      init();
    }
  };

  NS.open = function () {
    if (!panelEl) return;
    populateBoatSelect();
    panelEl.hidden = false;
    if (inputEl) inputEl.focus();
  };

  NS.close = function () {
    if (panelEl) panelEl.hidden = true;
  };
})();
