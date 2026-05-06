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
MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS", "1024"))
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
