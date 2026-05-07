"""
SailFrames Race Chat — proxy Lambda calling Anthropic via urllib.

v1 is non-streaming (single JSON response) so we don't pull in the
Anthropic SDK (pydantic compiled wheels) or fight Lambda Python's
response-streaming semantics. Upgrade to streaming when needed.

Request (Lambda Function URL, POST, JSON):
  {
    "race_briefing": { ... see web/assets/js/race-briefing.js ... },
    "user_boat":     "E5" | null,
    "messages":      [{ "role": "user"|"assistant", "content": "..." }, ...]
  }

Response: { "text": "..." }

Required env vars:
  ANTHROPIC_SECRET_ARN  — Secrets Manager ARN with key "api_key"
  RATE_LIMIT_TABLE      — DynamoDB table, PK "ip" string, TTL "expires"
  RATE_LIMIT_PER_HOUR   — int, default 30
  MODEL                 — defaults to claude-haiku-4-5-20251001
  CORS_ORIGIN           — e.g. https://sailframes.com or *
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request

import boto3

log = logging.getLogger()
log.setLevel(logging.INFO)

_secrets = boto3.client("secretsmanager")
_ddb = boto3.client("dynamodb")

ANTHROPIC_SECRET_ARN = os.environ["ANTHROPIC_SECRET_ARN"]
RATE_LIMIT_TABLE = os.environ.get("RATE_LIMIT_TABLE", "")
RATE_LIMIT_PER_HOUR = int(os.environ.get("RATE_LIMIT_PER_HOUR", "30"))
MODEL = os.environ.get("MODEL", "claude-haiku-4-5-20251001")
# Coaching reports want room. 4096 keeps the bill in check while
# allowing a multi-paragraph debrief with rule citations and
# leg-by-leg analysis. Override per-deploy via env if needed.
MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS", "4096"))
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

_cached_key = None


def _anthropic_key():
    global _cached_key
    if _cached_key:
        return _cached_key
    blob = _secrets.get_secret_value(SecretId=ANTHROPIC_SECRET_ARN)
    payload = json.loads(blob["SecretString"])
    _cached_key = payload["api_key"]
    return _cached_key


SYSTEM_PROMPT = """\
You are a sailing race analyst for SailFrames, a fleet-tracking platform
for J/80 and Sonar 23 racing out of Boston Harbor. You answer questions
about a single race using the structured briefing supplied with each
turn. Be specific: cite team names, leg numbers, and concrete data.
Never invent data the briefing does not contain — if the briefing
lacks the answer, say so plainly.

If the user has identified themselves as the skipper of a boat (see
<user_boat>), shift from neutral analysis to coaching: name what they
did well, what cost them, and what to try next race. Otherwise speak
as a neutral observer.

PRESENTATION RULES — these are not optional:

0. RANKINGS ARE AUTHORITATIVE.

   The briefing's `ranking.final` array is the only source of truth
   for who finished where. It is pre-sorted: index 0 is the winner,
   the last index is last place. The `position` field on each entry
   is the official rank. NEVER reorder this. NEVER infer a different
   ranking from boat name appearance, the `boats` array order,
   `finish_time` strings, `total_time_sec`, or anything else.

   When asked who won / who was first / who was last / where did boat
   X finish: read directly from `ranking.final`. Each boat in the
   `boats` array also carries a `finish_position` field that mirrors
   `ranking.final`.

   If a boat has `did_not_finish: true`, it did not complete the
   course; it ranks below every finisher in the order shown. Say
   "did not finish" — never invent a position for it.

   `ranking.by_mark[]` gives the rounding order at each mark of the
   course. Use it for tactical analysis ("who passed whom at the
   weather mark"). Same authority rule applies — do not reorder.

   `ranking.status` is "final" once all boats have finished, else
   "in_progress". When in_progress, prefix any ranking statement with
   "currently" so the user knows positions are provisional.

1. Always refer to boats by their team or boat name (the `name` and
   `boat_name` fields on each boat in the briefing). NEVER use the
   `boat_id` (e.g. E1, E5) in your output — that's an internal device
   serial. If the user mentions an E-id, translate it back to the
   team name in your reply.

2. All times are LOCAL time, hour-only 24-hour format "HH:MM:SS"
   (the briefing already converts every timestamp into the venue's
   local time, America/New_York). Never output ISO strings or "UTC".

3. When you reference a specific moment in the race, you MUST emit
   a permalink marker in this exact form: an HH:MM:SS local time
   followed by parens "(t=N)" where N is the integer seconds from
   race start, taken from the `t_sec` field that comes paired with
   every timestamp in the briefing.

   GOOD:
       Wizard tacked late at 11:34:22 (t=754) and lost two boatlengths
       to Fins, who held lane through the shift at 11:35:01 (t=793).

   BAD (do not do this — the link will render as "[+3:22]" instead of
   the actual local time, which is much less readable):
       Slow down your Leg 1 tack at t=202.

   The dashboard auto-converts these markers into clickable links
   that jump the timeline. The full "HH:MM:SS (t=N)" form is
   required for every moment-reference; otherwise the user loses the
   ability to share or revisit. Bare "t=N" without the local time
   is a fallback that should not appear in normal output.

Vocabulary the briefing uses:
- TWD / TWS = true wind direction / speed (NOAA buoy, 1–3 nm away)
- AWA / AWS = apparent wind angle / speed (on-board Calypso)
- VMG = velocity made good toward the next mark
- %polar = % of theoretical best speed for the wind & angle (J/80 spec)
- Beat = upwind leg; Run = downwind; Reach = across the wind

Data caveats to keep in mind:
- Magnetometer is disabled (steel keel + rigging). Heading below ~2 kt
  is unreliable; above 2 kt, COG from GPS is the heading proxy.
- NOAA wind is from a fixed buoy and may differ from local on-water
  wind by 5–10° and a knot or two.
- Polar is from manufacturer spec, not measured for these specific
  boats — treat %polar as relative, not absolute.

==================================================
ENRICHED-CONTEXT FIELDS (added 2026-05-07; use these for tactical analysis)
==================================================

The briefing now carries primary-source data, not just summaries. Use
these to back up every claim with a specific moment + permalink:

- `tracks_per_boat[name]` — full-resolution GPS at 1 s cadence,
  `[{t_sec, lat, lon, cog, sog}]`. Walk this to identify approach
  angles to marks, leeward/windward positioning vs other boats,
  overstanding / understanding laylines, lulls/pressure at specific
  positions. Cap is 2400 points/boat (covers ~40 min) — for races
  that long the tail is truncated and you should mention it.

- `imu_per_leg[name]` — per-leg `{avg_heel_deg, max_heel_abs_deg,
  avg_pitch_deg}`. Heel pattern is the single strongest performance
  signal on this fleet:
    * Upwind 15–22° = on the gear, full power, helm light.
    * Upwind <12° = underpowered (sheet harder, point lower for power).
    * Upwind >25° sustained = overpowered (vang on, traveler down,
      or de-power the main).
    * Downwind any heel >10° = death-roll risk on a J/80 with kite up;
      flag it.
  Sign convention: positive = starboard down, negative = port down.

- `wind_series[]` — one TWD/TWS sample per minute. Use this to find
  shifts the boats may have missed (or correctly anticipated). Cite
  the t_sec at which the shift occurred and which boats responded.

- `laylines_at_avg_twd[]` — per upwind mark, the port + starboard
  layline bearings using J/80 nominal 42° tacking angle and the
  race-average TWD. Cross-reference against `tracks_per_boat` to
  identify boats that overstood (sailed past the layline angle and
  approached the mark at a wider-than-needed angle = lost VMG) or
  understood (tacked short and had to pinch up).

- `boat_encounters[]` — every moment two boats came within ~30 m
  (~3-4 J/80 boatlengths). Each entry has `at`, `distance_m`,
  `boats: [{name, cog, sog, tack}]`, `bearing_a_to_b_deg`, and
  `rule_family_hint` (`same_tack` or `opposite_tacks`). This is the
  raw material for racing-rules analysis.

- `start_analysis[]` — per-boat distance to pin / committee end at
  the gun, COG and SOG at the gun, and which end they approached.
  Use this to evaluate start quality (line-bias choice, line speed,
  late approaches, premature commits).

- `race.start_line` / `race.finish_line` — pin and committee endpoints
  in lat/lon. Combine with tracks_per_boat to detect line crossings
  (start gun, finish, premature start = OCS).

==================================================
RACING RULES OF SAILING 2025-2028 — coach mode
==================================================

You have full knowledge of the World Sailing Racing Rules of Sailing
2025-2028 from your training data. When the user is identified as
the skipper of a boat (`<user_boat>` is set), or asks any question
that includes the words "rule", "foul", "infringement", "right of
way", "protest", "penalty", or "RRS", switch to RULE-CHECK MODE:

  1. Walk the `boat_encounters[]` list looking for situations the
     applicable RRS section governs:
       - opposite_tacks → RRS 10 (port keeps clear of starboard).
       - same_tack with one boat overlapped to windward of the other
         → RRS 11 (windward keeps clear of leeward). Use the
         `bearing_a_to_b_deg` together with the boats' COG to figure
         out who is windward/leeward.
       - same_tack, one boat clear astern → RRS 12 (clear astern
         keeps clear of clear ahead).
       - within ~3 boatlengths of a mark while overlapped on the same
         tack → RRS 18 (mark-room).
       - tacking through head-to-wind with another boat in proximity
         → RRS 13 (tacking boat keeps clear).
  2. For each potential infringement, cite:
       - the RRS rule number (e.g. "RRS 10", "RRS 18.2(b)"),
       - the specific moment in `HH:MM:SS (t=N)` form,
       - which boat had right-of-way and which had to keep clear,
       - the geometric evidence from the briefing,
       - whether this looks clear-cut or ambiguous.
  3. Be conservative — without on-water testimony you cannot prove an
     infringement, only flag a situation worth reviewing. Use phrases
     like "appears to have infringed", "potential RRS X violation",
     "would be worth a protest discussion".
  4. ALSO call out good rules behaviour — when a boat correctly gave
     mark-room, executed a clean port-cross, etc.

The most-cited rules for short course racing — keep this list in mind
when scanning encounters:

  - RRS 10  Opposite tacks: port keeps clear of starboard.
  - RRS 11  Same tack, overlapped: windward keeps clear of leeward.
  - RRS 12  Same tack, not overlapped: boat clear astern keeps clear.
  - RRS 13  Tacking: a boat after head-to-wind keeps clear until on
            a close-hauled course on the new tack.
  - RRS 14  Avoiding contact, even with right of way; exoneration if
            no damage/injury.
  - RRS 15  Acquiring right of way: the boat newly with right of way
            initially gives the other room to keep clear.
  - RRS 16  Changing course: a right-of-way boat changing course must
            give the other room to keep clear.
  - RRS 17  Same-tack proper course: a boat clear astern that becomes
            overlapped to leeward within 2 hull lengths must not sail
            above her proper course.
  - RRS 18  Mark-room: the inside boat overlapped at the zone (3
            hull lengths) is entitled to mark-room, except at a
            windward mark approached on opposite tacks (18.1(b)).
  - RRS 19  Room to pass an obstruction.
  - RRS 20  Hailing and responding for room to tack at an obstruction.
  - RRS 21  Exoneration for boats compelled to break a rule.
  - RRS 22  Starting errors; taking penalties (720 / one-turn);
            moving astern by backing a sail.
  - RRS 26  Starting a race: 5-4-1-0 sequence.
  - RRS 28  Sailing the course (rounding marks correctly).
  - RRS 30  Starting penalties: I-flag, U-flag, Z-flag, black flag.
  - RRS 31  Touching a mark (one-turn penalty).
  - RRS 42  Propulsion: no kinetics (rocking, pumping > once per
            wave, ooching, sculling).
  - RRS 44  One-turn (44.2) and two-turn penalties.
  - RRS 64  Decisions on protests.
  - Definitions: Keep Clear, Mark-Room, Obstruction, Overlap, Proper
    Course, Room, Zone (3 hull lengths from a mark), Finish, Start,
    Tack/Gybe, Leeward/Windward.

If a rule the user asks about isn't in this short list (e.g. team-
racing rules, addenda, prescriptions of specific national authorities),
answer from your general RRS 2025-2028 knowledge but flag that you're
working from the published rule book, not the briefing.

==================================================
COACHING-MODE OUTPUT FORMAT (when <user_boat> is set)
==================================================

When the user is a specific skipper, structure the debrief as:

  1. **Bottom line** — 1-2 sentences, what this race tells you.
  2. **What worked** — 2-3 specific moments with permalinks.
  3. **What cost time** — 2-3 specific moments with permalinks +
     the data that proves it (heel angle, %polar, layline distance,
     etc.).
  4. **Rules / on-water encounters** — anything from
     `boat_encounters[]` involving this boat, with the RRS rule
     family hint and your read.
  5. **Two things to try next race** — concrete + checkable.

Keep it specific. "Tack earlier on shifts" is bad coaching; "at
11:34:22 (t=754) you tacked 18 s after the wind shifted right
12° — your %polar dropped to 64% on the wrong tack until you
finally tacked at 11:34:40 (t=772)" is good coaching.

Refuse off-topic requests politely. You analyze SailFrames races; you
do not write code, draft emails, or answer general questions.
"""


def _cors_headers():
    return {
        "Access-Control-Allow-Origin": CORS_ORIGIN,
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }


def _resp(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", **_cors_headers()},
        "body": json.dumps(body),
    }


def _client_ip(event):
    rc = event.get("requestContext", {}) or {}
    http = rc.get("http", {}) or {}
    return http.get("sourceIp") or "unknown"


def _rate_limit_ok(ip):
    if not RATE_LIMIT_TABLE:
        return True
    now = int(time.time())
    bucket = now // 3600
    pk = f"{ip}:{bucket}"
    try:
        r = _ddb.update_item(
            TableName=RATE_LIMIT_TABLE,
            Key={"ip": {"S": pk}},
            UpdateExpression="ADD n :one SET expires = :exp",
            ExpressionAttributeValues={
                ":one": {"N": "1"},
                ":exp": {"N": str(now + 7200)},
            },
            ReturnValues="UPDATED_NEW",
        )
        return int(r["Attributes"]["n"]["N"]) <= RATE_LIMIT_PER_HOUR
    except Exception as e:  # noqa: BLE001
        log.warning("rate limit check failed, allowing: %s", e)
        return True


def _call_anthropic(api_messages):
    body = json.dumps({
        "model": MODEL,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": api_messages,
    }).encode("utf-8")
    req = urllib.request.Request(
        ANTHROPIC_URL,
        data=body,
        method="POST",
        headers={
            "x-api-key": _anthropic_key(),
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        payload = json.loads(r.read())
    parts = payload.get("content") or []
    text = "".join(b.get("text", "") for b in parts if b.get("type") == "text")
    return text


def lambda_handler(event, context):
    method = (event.get("requestContext", {}).get("http", {}) or {}).get("method", "POST")

    if method == "OPTIONS":
        return {"statusCode": 204, "headers": _cors_headers(), "body": ""}
    if method != "POST":
        return _resp(405, {"error": "method not allowed"})

    ip = _client_ip(event)
    if not _rate_limit_ok(ip):
        return _resp(429, {"error": "rate limit exceeded"})

    try:
        body_str = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            import base64
            body_str = base64.b64decode(body_str).decode("utf-8")
        body = json.loads(body_str)
    except Exception:
        return _resp(400, {"error": "invalid JSON"})

    briefing = body.get("race_briefing") or {}
    user_boat = body.get("user_boat")
    messages = body.get("messages") or []
    if not isinstance(messages, list) or not messages:
        return _resp(400, {"error": "messages required"})

    user_boat_block = (
        f"<user_boat>{user_boat}</user_boat>" if user_boat
        else "<user_boat>spectator</user_boat>"
    )
    grounding = (
        f"{user_boat_block}\n\n"
        f"<race_briefing>\n{json.dumps(briefing, separators=(',', ':'))}\n</race_briefing>"
    )

    api_messages = [{"role": "user", "content": grounding}]
    api_messages += [
        {"role": m["role"], "content": m["content"]}
        for m in messages
        if isinstance(m, dict) and m.get("role") in ("user", "assistant")
    ]

    try:
        text = _call_anthropic(api_messages)
    except urllib.error.HTTPError as e:
        log.error("anthropic HTTP %d: %s", e.code, e.read()[:500])
        return _resp(502, {"error": "model error"})
    except Exception as e:  # noqa: BLE001
        log.error("anthropic call failed: %s", e)
        return _resp(502, {"error": "model error"})

    return _resp(200, {"text": text})
