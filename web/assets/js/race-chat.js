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
  // Default endpoint = the prod HTTP API; override via window.SAILFRAMES_CHAT_URL.
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
        <div class="sf-chat-log"></div>
        <form class="sf-chat-input-row">
          <input type="text" class="sf-chat-input"
                 placeholder="Ask anything about this race…" autocomplete="off">
          <button type="submit" class="sf-chat-send">Send</button>
        </form>
        <div class="sf-chat-foot">Answers come from race data only.
          Powered by Claude. Be patient with long questions.</div>
      </div>`;
    document.body.appendChild(root);

    panelEl = root.querySelector('.sf-chat-panel');
    logEl = root.querySelector('.sf-chat-log');
    inputEl = root.querySelector('.sf-chat-input');
    boatSelectEl = root.querySelector('.sf-chat-boat');

    root.querySelector('.sf-chat-close').onclick = () => { panelEl.hidden = true; };
    root.querySelector('.sf-chat-input-row').onsubmit = (e) => {
      e.preventDefault();
      send(inputEl.value);
    };

    populateBoatSelect();
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

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  // Make every "t=N" token in the model's reply clickable. Two passes
  // so the canonical "HH:MM:SS (t=N)" form keeps its human time as the
  // link text, and any standalone "t=N" or "(t=N)" still gets linked
  // (rendered as a "[+M:SS]" offset). The contract with the LLM lives
  // in the system prompt; the linkifier is tolerant on purpose.
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

  async function send(text) {
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

    try {
      const resp = await fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          race_briefing: briefing,
          user_boat: userBoat,
          messages: messages,
        }),
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
