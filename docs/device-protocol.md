# Device Protocol

A practical guide for firmware authors integrating a hardware device
(SailFrames E1, a third-party tracker, or any future custom device)
with XGSail. It documents the actual, implemented endpoints —
every request/response shape below matches the backend code exactly
(`backend/routers/devices.py`, `backend/routers/device_api.py`,
`backend/auth/device.py`, `backend/schemas/device.py`).

XGSail is hardware-agnostic: any device that implements this
protocol can integrate, regardless of what board or firmware stack it
runs. Device/PCB/firmware design itself lives outside this repository.

All requests/responses are JSON unless noted. All IDs (`device_id`,
`session_id`, `session_upload_id`, `boat_id`, ...) are UUID strings.

---

## 1. Device identity

Every device is identified by an `external_id`: a stable string —
hardware serial number, BLE UUID, or MAC address, whatever the device
can reliably expose. **It must not change across reboots** — it is the
value the device sends on claim, and the server rejects a second claim
for an `external_id` that's already claimed.

The device type (e.g. `"SailFrames E1"`) is chosen when the claim is
created by the user (§2), not by the device — the device only needs to
know its `external_id`.

---

## 2. Provisioning (claim flow)

A device **cannot send data before it is claimed** — there is no
auto-registration on first upload.

1. **User creates a claim** (from the app, authenticated):

   ```
   POST /api/devices/claims
   Content-Type: application/json

   {
     "device_type_id": "3f2a1c...-uuid",
     "nickname": "Optimist 12 tracker",   // optional
     "owner_user_id": null,               // exactly one of these three
     "owner_boat_id": "42a1...-uuid",     // must be non-null
     "owner_club_id": null
   }
   ```

   Response 200:

   ```
   { "device_id": "1234...-uuid", "claim_code": "K7XMPQR2", "expires_at": "2026-07-08T10:15:00Z" }
   ```

   `claim_code` is an 8-character code drawn from an unambiguous
   alphabet (no `0/O/1/I`, easy to hand-type). It expires 15 minutes
   after creation.

2. **The user passes `claim_code` to the device out of band** — for
   the E1, by writing it into `config.txt` on the SD card before boot
   (`claim_code=K7XMPQR2`), or via a serial command
   (`claim K7XMPQR2`) if the device is already powered on and in
   provisioning mode. How the code reaches the device is
   device-specific; only the confirm call below is part of the
   protocol.

3. **The device confirms the claim, exactly once**, as soon as it has
   a `claim_code` and connectivity. This call needs **no user
   authentication** — possession of a valid, unexpired `claim_code` is
   the credential:

   ```
   POST /api/devices/claim/confirm
   Content-Type: application/json

   { "external_id": "AA:BB:CC:DD:EE:FF", "claim_code": "K7XMPQR2" }
   ```

   Response 200:

   ```
   { "device_id": "1234...-uuid", "device_api_key": "sfd_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "issued_at": "2026-07-08T10:01:00Z" }
   ```

4. **The device must persist `device_api_key` to non-volatile storage**
   (SD card, NVS, ...). The server stores only a hash of it — it
   cannot be recovered in plaintext after this response. If the device
   loses the key, the user must trigger a key rotation (§5) and
   rewrite the new key onto the device.

Errors on `claim/confirm`:

| Status | Cause | Expected device behavior |
|---|---|---|
| 400 | missing/blank `external_id` or `claim_code` | do not retry — firmware bug |
| 404 | `claim_code` not found | do not retry — needs a fresh claim from the user |
| 409 | `claim_code` expired, or `external_id` already claimed by another device | needs a fresh claim from the user |
| 429 | more than 10 confirm attempts/minute from this IP | back off, retry later |

---

## 3. Authenticating subsequent calls

Every call under `/api/devices/me/...` (§4) carries:

```
Authorization: DeviceKey sfd_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

The header name is `Authorization`, the scheme is the literal word
`DeviceKey` (case-insensitive), followed by a space and the raw key —
not `Bearer`, not JWT.

A `401` response means the key is not valid right now — wrong,
revoked (`DELETE /api/devices/{id}`), or rotated (§5). There is no way
to distinguish these cases from the response; on `401` the device must
stop retrying and surface the error (LED/display/log) until it
receives a new key through manual reprovisioning. It must not attempt
to re-run the claim flow automatically.

**Transport security**: use TLS whenever the device's network stack
supports it reliably. If a given hardware/SDK combination cannot do
TLS reliably, the key travels in the clear over plain HTTP for that
device — it is not cryptographically strong in that case, but it still
scopes an attacker to a single device's uploads rather than to a whole
storage bucket.

---

## 4. Sending data

### 4.1 Open/append to a `session_upload`

```
POST /api/devices/me/session-uploads
Authorization: DeviceKey <device_api_key>
Content-Type: application/json

{
  "boat_id": "42a1...-uuid",         // required unless the device's type is
                                      // category="boat_tracker" (then it
                                      // defaults to the device's own boat)
  "activity_id": null,               // optional — omit to let the server
                                      // create/attach one automatically
  "started_at": "2026-07-08T14:05:00Z",  // required, ISO 8601 with offset
  "ended_at": null,                  // optional
  "sequence_number": 0,              // 0 = first/only chunk (default)
  "is_final": true,                  // true = single upload (default, standard case)
  "subject_type": "boat",            // "boat" | "crew_member" (default "boat")
  "subject_user_id": null,           // required if subject_type="crew_member"
  "filename": "data.csv"             // object name for the uploaded bundle (default "data.csv")
}
```

Response 201:

```
{
  "session_upload_id": "987f...-uuid",
  "session_id": "555a...-uuid",
  "activity_id": "111b...-uuid",
  "upload_url": "https://.../raw/uploads/987f.../data.csv?X-Amz-...",
  "upload_url_expires_at": "2026-07-08T15:05:00Z"
}
```

The device then does a **direct `PUT`** of the raw file bytes to
`upload_url`. This call bypasses the API entirely (goes straight to
the object store) and needs **no `Authorization` header** — the
authorization is already embedded in the signed URL, which expires one
hour after issuance.

This call is **idempotent** on `(session, device, sequence_number)`:
calling it again with the same `sequence_number` for the same session
returns the same `session_upload_id` with a freshly-signed
`upload_url` — safe to call again after a timeout or a lost response
(see retry guidance, §6).

### 4.2 Incremental uploads (optional, live tracking)

To stream a session as multiple chunks instead of one bundle at the
end:

- send one `POST .../session-uploads` per chunk, same session
  (implied by `boat_id` + `started_at`/timeframe), with an
  incrementing `sequence_number` and `is_final=false`
- the last chunk uses `is_final=true`
- the backend only finalizes the session's stream once it has
  received the `is_final=true` chunk for that device

If you don't need live tracking, ignore this section: the default
(`sequence_number=0, is_final=true`) already sends a single upload at
the end of the session.

### 4.3 Closing or failing an upload after the fact

```
PATCH /api/devices/me/session-uploads/{session_upload_id}
Authorization: DeviceKey <device_api_key>
Content-Type: application/json

{ "is_final": true }
```

or, if the device detects a local failure (e.g. a corrupted file on
the SD card before upload completed):

```
{ "status": "failed" }
```

`"failed"` is the only status a device is allowed to report — any
other value is rejected with `422`.

### 4.4 Health snapshot

```
POST /api/devices/me/health
Authorization: DeviceKey <device_api_key>
Content-Type: application/json

{
  "battery_pct": 78,
  "battery_v": 3.91,
  "heap_free": 142300,
  "firmware_version": "2026.05.22.02",
  "uptime_s": 5423
}
```

Response: `{ "ok": true }`. All fields are optional — send whatever the
device can measure. Each call **replaces** the previous snapshot
(latest-wins); the device owner reads it back via
`GET /api/devices/{device_id}/health` from the app. Recommended
frequency: every 5 minutes, or on-demand.

---

## 5. Recovery — lost key or replaced device

The device cannot regenerate its own key. This always requires user
action from the app, by whoever manages the device (owner, or the
boat/club admin it's claimed under):

```
POST /api/devices/{device_id}/rotate-key
```

Response: a new `device_api_key` (shown once, exactly like at claim
time — §2.4). `external_id`, owner, nickname and `claimed_at` are
unchanged; only the secret changes. The user must rewrite the new key
onto the device (config file, serial command, however the device
accepts it). Rotating fails with `409` if the device isn't currently in
`claimed` status.

**If the physical device itself is replaced** (new hardware taking
over the same role on the same boat), don't rotate the key: the old
`external_id` and the new one are different values, so instead the
user should `DELETE /api/devices/{device_id}` (revokes the old device)
and create a brand-new claim (§2) for the new device's `external_id`.

---

## 6. Retry and backoff

- If the `PUT` to `upload_url` fails or the URL has expired, **do not
  retry `POST .../session-uploads` with the same `sequence_number`
  from scratch expecting a new object** — you'll get back the *same*
  `session_upload_id` (§4.1 is idempotent), which is exactly what you
  want: call it again to get a fresh `upload_url`, then retry the
  `PUT`. Never invent a new `sequence_number` just to work around a
  failed upload — that creates a duplicate chunk.
- Recommended backoff for both the `POST` and the `PUT`: exponential,
  starting at 5s, capped at 5 minutes.
- Health snapshot (§4.4) failures are non-critical: don't retry
  aggressively, just send the next scheduled snapshot.

---

## 7. Endpoint quick reference

| Method & path | Auth | Purpose |
|---|---|---|
| `POST /api/devices/claims` | user cookie | Create a claim code for a device type + owner target |
| `POST /api/devices/claim/confirm` | none (claim code is the credential) | Device redeems the code, receives its API key |
| `POST /api/devices/me/session-uploads` | `DeviceKey` | Open/append a session upload, get a presigned upload URL |
| `PATCH /api/devices/me/session-uploads/{id}` | `DeviceKey` | Mark an upload final, or report a local failure |
| `POST /api/devices/me/health` | `DeviceKey` | Push a health snapshot |
| `POST /api/devices/{id}/rotate-key` | user cookie (owner) | Invalidate the current key, issue a new one |
| `DELETE /api/devices/{id}` | user cookie (owner) | Revoke a device |
| `GET /api/devices/{id}/health` | user cookie (owner) | Read back the latest health snapshot |

---

## 8. Transport: direct WiFi vs. phone BLE relay

Everything in §2–§4 is **transport-neutral**: authentication is a bearer-style
header or a claim code, not something tied to a socket or the device's own
network stack, and the upload URL from §4.1 carries its own authorization —
nothing checks *who* performs the `PUT`. So a device with no WiFi/cellular
radio at all can still fully participate: the owner's phone, over Bluetooth
Low Energy, relays the exact same calls documented in §2 and §4 on the
device's behalf. This section is that relay's contract — it adds no backend
endpoint and no new device state.

**For firmware, in short**: expose the five BLE characteristics in §8.2, in
the wire format given there. Treat a key arriving via `provisioning` exactly
like one received over WiFi at claim time (§2 step 4) — same persistence, same
`401` handling. Buffer any session you can't upload directly and list it in
`session_manifest` until `control` tells you it's been acknowledged. That's
the whole surface; §8.3/§8.4 below just walk through the call sequence in
order.

### 8.1 When to use which transport

Prefer sending data over the device's own WiFi (§4.1) whenever it has
connectivity — simpler, no phone needs to be in range. BLE relay is the
fallback: no network radio, or WiFi temporarily unavailable. This is a
runtime choice made per upload, not a different device type or claim flow —
the same physical device may upload one session directly and the next one via
relay, depending on what connectivity it has at the time.

### 8.2 GATT contract

One custom BLE GATT service, five characteristics. UUIDs are freshly
generated (v4, random) rather than reused from a known public service like
Nordic UART, so a scan filtered on the service UUID can't false-positive-match
an unrelated nearby BLE device. `frontend/src/services/nativeBle.ts` is the
source of truth if these two ever drift.

| Characteristic | UUID | Properties | Purpose |
|---|---|---|---|
| (service) | `24e6db2c-3c8a-4b5b-ba5a-23bc4c818046` | — | Groups the characteristics below; also the §8.1 scan filter |
| `identity` | `985a1aae-858e-4727-9d5c-c8670bd6bd06` | read | `external_id` (same value used in §2) and firmware version |
| `provisioning` | `db2c2e63-9e13-4fa9-867c-0b579ce2ae57` | write, notify | App writes the `device_api_key` from §2 step 3; device persists it and notifies claim status |
| `session_manifest` | `ed9efdc8-70d4-4ce5-a0a3-9fa6d88b9b9e` | read, notify | Device announces buffered, not-yet-uploaded sessions: id, byte size, `started_at`/`ended_at` |
| `session_data` | `728d2815-0409-49ce-ad73-ecca6fc6d981` | notify (chunked) | Device streams one session's raw bytes to the app, framed with a sequence index so the app can detect drops |
| `control` | `ec88dd3e-2562-420c-aebe-30a4ae40bdf9` | write | App → device commands: `start-transfer <session>`, `ack-uploaded <session>` |

`provisioning` (or any characteristic that could leak `device_api_key`) must
not be readable/writable except over a **bonded, encrypted** connection —
proximity alone isn't enough, the key is equivalent to full write access to
that device's uploads.

**Wire format** (UTF-8 JSON unless noted):
- `identity` read: `{"external_id": "...", "firmware_version": "..."}`.
- `provisioning` write: `{"device_api_key": "..."}`; notifies back
  `{"status": "claimed"}` once persisted.
- `session_manifest` read/notify: a JSON array of
  `{"session_id": "...", "byte_size": N, "started_at": "...", "ended_at": "..."|null}`.
- `session_data` notify: **not** JSON — raw binary, a 4-byte big-endian
  sequence index followed by that chunk's bytes. The app reassembles by
  index and considers the transfer complete once it has `byte_size` bytes
  total (from the manifest entry) — no separate end-of-stream marker needed.
- `control` write: `{"cmd": "start-transfer"|"ack-uploaded", "session_id": "..."}`.

### 8.3 Claim over BLE (replaces manually typing the claim code)

Instead of writing `claim_code` to an SD card or serial console (§2 step 2):

1. User creates a claim in the app as in §2 step 1, receives `claim_code`.
2. App connects to the device over BLE, reads `external_id` from `identity`.
3. App calls `POST /api/devices/claim/confirm` with `{external_id, claim_code}`
   itself — the same unauthenticated call the device would otherwise make
   (§2 step 3). The app is a pure relay here, nothing else changes.
4. App writes the returned `device_api_key` to `provisioning`; device
   persists it exactly as if received over its own network, and notifies
   confirmation.
5. App also stores `device_api_key` locally — it's the natural first upload
   relay for that device, since it already holds the key.

Claim-code semantics are unchanged from §2: still 15-minute TTL, single-use,
same `400`/`404`/`409`/`429` errors.

### 8.4 Upload relay

For each session the device has buffered but couldn't upload directly:

1. App reads `session_manifest` to discover it.
2. App calls `POST /api/devices/me/session-uploads` (§4.1) itself, using the
   `device_api_key` it holds, exactly as the device would.
3. App writes `start-transfer <session>` to `control`, then receives the
   session's bytes as `session_data` notifications arrive.
4. App `PUT`s those bytes to the `upload_url` from step 2 — no additional
   authorization needed, identical to a device-initiated upload.
5. App calls `PATCH .../session-uploads/{id} {"is_final": true}` (§4.3), then
   writes `ack-uploaded <session>` to `control` so the device can free its
   buffer.

Device must not free a session's buffer before `ack-uploaded` arrives — if the
app disconnects or crashes first, the same session is simply retried on the
next connection. This is safe because §4.1 is idempotent on
`(session, device, sequence_number)`: a dropped BLE connection mid-transfer
just re-opens the same `session_upload_id` with a fresh `upload_url`, never a
duplicate.
