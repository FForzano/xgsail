# RTK Phase 2 — RC-boat base + ESP-NOW RTCM relay (design / scope)

**Status:** Scoped 2026-06-03. Not implemented. Firmware not started.
**Prereq met:** Phase 1 passed — LC29HEA (B-chip) held **RTK FIXED (GGA q=4) at 10 Hz off ~1 Hz RTCM3** for 148 s (MaCORS VRS, E6 bench, 2026-06-03). See [`RTK_PLAN.md`](RTK_PLAN.md) + `project_rtk_plan` memory.

**Goal:** Deliver cm-relative fleet positioning on the race course **with no internet** so OCS can resolve a 0.5 m line, by turning the RC boat's GNSS into a local RTK base and relaying its RTCM3 over the existing ESP-NOW mesh.

---

## 0. What's already de-risked (read before sequencing)

- **LG290P base-mode RTCM output is on record, not a guess.** `docs/RTCM_PPK_ARCHIVE.md` (line 56, build `08cdadfe`) empirically produced 1 Hz **MSM7 1077/1087/1097/1127 + 1006 station ref (every 10 epochs) + ephemeris (~30 s)** via `PQTMCFGRTCM,W,7,0,-90,07,06,1,0` in Base mode (`PQTMCFGRCVRMODE,W,2`). ~500 B/s. So the **base half is revivable from git**, not net-new research.
- **LC29HEA rover (10 Hz RTK off 1 Hz RTCM) is field-proven** (Phase 1, q=4, 2026-06-03).
- **Genuinely-open chip gate: the LG290P *rover* (10 Hz RTK-in) is NOT verified.** The AANR01A06S firmware already lied about MSM *output* in Rover mode (PPK archive line 12), so don't assume the *input* side until it's seen on hardware.

**Consequence for sequencing:** the first end-to-end bench is **LG290P base → ESP-NOW relay → LC29HEA rover** — it uses only verified endpoints and isolates the relay. The LG290P-rover gate is a *separate, later* test (§7, M5), never on the critical path to first fix.

---

## 1. Architecture

```
RC boat (role=rc_signal, LG290P)              Rover boats (racing_boat, E=LG290P or B=LC29HEA)
┌─────────────────────────────┐               ┌──────────────────────────────────┐
│ LG290P  Base mode, 1 Hz      │               │  GNSS  Rover mode, 10 Hz RTK       │
│  → RTCM3 stream on Serial2   │               │   ← RTCM3 bytes written to Serial2 │
│        │ (read in loop)      │               │        ▲ (drained in loop)         │
│        ▼                     │   ESP-NOW     │        │ SPSC ring buffer           │
│ RTCM frame-parser (0xD3/len) │   ch 1        │   reassemble complete frame        │
│        ▼ per complete frame  │  broadcast    │        ▲ by (msg_id, frag_index)   │
│ fragment → MSG_RTCM_FRAG ────┼──────────────▶│  meshOnReceive dispatch            │
│  (16B MeshHeader + meta+data)│   2× tx       │                                    │
└─────────────────────────────┘               │  GGA quality 4 ⇒ this rover is cm  │
                                               └──────────────────────────────────┘
```

- **Frame-parse on the RC, not byte-stream chunking.** The RC reads the RTCM3 byte stream, finds frame boundaries (`0xD3` sync, 10-bit length, +3 CRC-24Q), and relays **one complete RTCM frame as N fragments**. The rover reassembles a *whole frame* before writing it to the GNSS UART. A lost fragment drops that whole frame cleanly (never feeds the GNSS a torn frame). RTCM is loss-tolerant (rover rides 120 s diff-age), so dropped frames just delay, they don't corrupt. Prior art: TinkerBug LoRa relay.
- **Callback never touches the UART.** `meshOnReceive` runs in the WiFi/ESP-NOW task. It reassembles into a small per-`msg_id` buffer and, on frame complete, pushes bytes into a **single-producer/single-consumer ring buffer**. The main loop's GNSS section drains the ring to `Serial2.write()`. Keeps the callback bounded and avoids HardwareSerial TX-buffer blocking inside the radio task (same discipline as the `handleTelnet`/LWIP and TFT_eSPI thread-safety gotchas).

---

## 2. New wire type (add to `mesh.h`)

```c
// MSG_RTCM_FRAG = 0x30  (add to MeshMsgType enum)
#define RTCM_FRAG_MAX 230   // 16 (MeshHeader) + 4 (meta) + 230 = 250 = ESP-NOW cap

struct __attribute__((packed)) RtcmFragPayload {
    uint8_t  msg_id;      // rolls per complete RTCM frame at the RC
    uint8_t  frag_index;  // 0 .. frag_count-1
    uint8_t  frag_count;  // total fragments for this frame (max 5: ceil(1029/230))
    uint8_t  frag_len;    // RTCM bytes in this fragment (<= RTCM_FRAG_MAX)
    uint8_t  data[RTCM_FRAG_MAX];
};
static_assert(sizeof(RtcmFragPayload) == 4 + RTCM_FRAG_MAX, "RtcmFragPayload size"); // gotcha #25
```

- Max RTCM3 frame = 3 + 1023 + 3 ≈ 1029 B ⇒ `frag_count` ≤ 5. Reassembly buffer = 1029 B, single in-flight frame.
- **Send only `16 + 4 + frag_len` bytes**, not the full struct — `frag_len` bounds the write. The fixed-size `data[]` exists only so `static_assert` can pin the max; never `esp_now_send(... sizeof(RtcmFragPayload))`.
- Header reuse: `MeshHeader` (16 B) carries `magic/version/msg_type=MSG_RTCM_FRAG/sender_id`, so `meshOnReceive` routes it with the existing dispatch (add an `else if (h->msg_type == MSG_RTCM_FRAG ...)` branch alongside the boat-state/race-armed/recall branches at ~`sailframes_edge.ino:1082`).

**Reliability knobs (cheap, big win on water):**
- **Transmit each fragment 2×.** RTCM @ 500 B/s leaves channel 1 nearly idle; double-tx is free airtime. Rover **dedupes by `(msg_id, frag_index)`** so the second copy is ignored when the first arrived.
- **Pass `1006`/`1005` straight through** (it's just another framed RTCM message in the stream). Optionally **re-emit the most-recent `1006` to a newly-seen peer** (peer appears in `g_mesh_peers` with no prior RTCM) so a late-joining rover gets the base position fast instead of waiting up to 10 epochs.

---

## 3. RC (base) side — **either chip can be the base**

**Both the LG290P (E) and the LC29HEA (B) share the Quectel `$PQTM` base-mode command family** — `PQTMCFGRCVRMODE,W,2`, survey-in, `PQTMSAVEPAR`. They differ only in *which* command enables the RTCM output messages. So `gnssConfigure(platform, ROLE_BASE)` is a thin branch, not a fork. (Sources at bottom: rtklibexplorer LC29HEA RTK guide + Quectel base-RTCM forum thread.)

**E (LG290P) base** — `gnssConfigure(HW_E1, ROLE_BASE)`:
- `PQTMCFGRCVRMODE,W,2` (Base, locks 1 Hz)
- `PQTMCFGRTCM,W,7,0,-90,07,06,1,0` (MSM7 1077/1087/1097/1127 + ephemeris + 1006) — **doesn't persist NVM, re-send every boot** (PPK archive, build `08cdadfe`)
- Re-enable NMEA (`PQTMCFGMSGRATE,W,GGA,1` …) — base mode auto-disables NMEA (§2.3.25)

**B (LC29HEA) base** — `gnssConfigure(HW_B1, ROLE_BASE)` (✅ now supported, was "avoid"):
- `$PQTMRESTOREPAR` then `$PQTMCFGRCVRMODE,W,2` (Base mode — same Quectel command as the LG290P)
- Survey-in: `$PQTMCFGSVIN,W,<mode>,<minDur>,<3dStdDev>,<x>,<y>,<z>` — use a **short survey-in** (loose accuracy) for race ops, see §3 survey-in note. Fixed-coord form `$PQTMCFGSVIN,W,2,0,0,x,y,z` also works if a surveyed mark is known.
- RTCM enables (Airoha `$PAIR`, not PQTM): `$PAIR432,1` = **MSM7**, `$PAIR434,1` = **1005** station position, `$PAIR436,1` = **ephemeris**
- NMEA GGA: `$PAIR062,0,01`
- `$PQTMSAVEPAR` then reboot (`$PAIR023` or power-cycle)
- **The MSM7 quirk is benign for us:** `$PAIR432,1` (MSM7) does **not persist to flash** → reverts to `$PAIR432,0` (MSM4) on power-cycle, and on some firmware `$PAIR432,1` even returns `COMMAND SENDING FAILED`. **MSM4 does cm RTK fine** (it's what MaCORS streamed in Phase 1 → q=4). So: try MSM7, **fall back to MSM4**, and **re-issue the chosen enable every boot** — exactly the same "re-send each boot" pattern as the LG290P's non-persisting `PQTMCFGRTCM`. No architectural cost.

**Shared (either base):**
- **Survey-in.** Error is **common-mode** across all rovers ⇒ a ≤3 m base offset → sub-mm *relative* fleet error (all OCS needs), so a short survey-in (or even instant fixed = current autonomous position) is acceptable; we do **not** need the 1-hour / 1.2 m absolute convergence the guides suggest. Anchor swing *after* survey-in is also common-mode and cancels.
- RC still needs its own GGA (1 Hz) for the fleet-OCS math — that's why NMEA is re-enabled above.
- Loop: read RTCM bytes off `Serial2`, run the frame-parser, fragment each complete frame into `MSG_RTCM_FRAG`, `esp_now_send` 2×.

**Fleet rule:** base can be **E or B**; rovers can be mixed E + B (relay payload is chip-blind). The only remaining "prefer LG290P" reason was the MSM7-flash quirk — now handled by re-issue-each-boot + MSM4 fallback, so a B-only RC boat is fully supported.

## 4. Rover side

- `gnssConfigure(platform, ROLE_ROVER)`:
  - E (LG290P): `PQTMCFGRCVRMODE,W,1` + `PQTMCFGRTK,W,1,2,120` + `PQTMCFGFIXRATE,W,100`
  - B (LC29HEA): `$PAIR` rover/RTK/10 Hz equivalents (proven path from Phase 1)
- `meshOnReceive`: reassemble `MSG_RTCM_FRAG` by `(msg_id, frag_index)`; on `frag_count` complete, push the frame bytes to the SPSC ring; discard a partial frame if a new `msg_id` starts before it completes or it times out (~2 s).
- **MUST track the last-COMPLETED `msg_id` and drop any fragment for it (Gate A bug, 2026-06-05).** With 2×-tx the *second* copy of a frame arrives *after* the frame already completed; without this guard a 1-fragment frame re-completes and **double-writes to the GNSS UART**, and a multi-frag trailing dup spawns a phantom partial. Dedup is therefore two-level: `got_mask` bit per `frag_index` for in-flight dups + `last_done_msg_id` for trailing dups. (msg_id only recollides 256 frames later, by which point `last_done` has advanced — safe.)
- Main loop GNSS section: drain ring → `Serial2.write()`. Name this `g_loopSection` (e.g. `"rtcm_drain"`) so the Core-1 loop watchdog can pinpoint it if it wedges.
- Confirm fix via existing GGA quality parse: **4 = FIXED**, 5 = float.

## 5. The line MUST be in the RTK frame (first-class deliverable) — ✅ IMPLEMENTED (increment 2, 2026-06-05)

**Prerequisite found in review (increment 1.5): `gps.lat/lon` were `float`.** A float32 near 42° has ~0.4 m resolution (worse at the `atof` of `ddmm.mmmm`), silently quantizing away the cm RTK fix *before storage* — capping OCS at ~0.5 m regardless of fix quality, and invisible to fix_quality/GST tests. Fixed → `double` (parse + store); `lat_e7` wire pack unchanged (int32 e7 = 1.1 cm). This is a fleet-wide accuracy fix (not flag-gated; strict improvement, same CSV/wire formats).

**Implementation:** new `race armrtk <secs>` command (RC `rc_signal` only, requires `rtk_enabled`): RC end = own position (base = committee end = frame origin), PIN end = the `rc_pin` peer's latest RTK-FIXED position from `g_mesh_peers`. Gates: rtk_enabled, role, own-pos valid, rc_pin peer seen <5 s + `fix_quality==4`, line length 10–1000 m. Then existing `ocsArm` + `meshBroadcastRaceArmed` (cm coords) → fleet arms; boats are cm RTK rovers (increment 1) → cm-consistent geometry. Typed `race arm <coords>` kept as manual fallback.

**Open verification:** RC end is taken from base-mode GGA — must confirm empirically it equals the surveyed ARP (1005), else the RC end wanders ~1 m off the frame origin (does not cancel). **Honest scope: increment 2 removes the *line* error; OCS sub-0.5 m is still gated by heading×bow_offset (~0.2–0.4 m, IMU-limited at the start) + 10 Hz timing. Deliverable = "start line now in the RTK frame," not "OCS is 0.5 m."**


The relay makes *boats* cm-accurate **relative to the base**. OCS compares the **bow to the start line**, so the **line endpoints must be captured in the same RTK frame** — otherwise cm boats are measured against 2 m autonomous-GPS line coordinates and the entire gain evaporates.

- The **pin-end mark boat must be an RTK rover on the same base** (role `rc_pin`), and the RC end likewise (it *is* the base, so it's in-frame by definition).
- **`race arm` must take RTK-captured endpoints**, not typed lat/lon. Capture pin from the `rc_pin` rover's fixed position and RC from the base, both post-FIXED, then broadcast via the existing `MSG_RACE_ARMED` (`RaceArmedPayload` already carries pin/RC e7 — no wire change, just feed it FIXED coords).
- Common-mode cancellation holds **because** boats, pin, and RC all share one base. That's exactly why the line has to be in-frame.

## 6. Operational timeline (state it in race ops)

A boat-as-base needs **minutes of survey-in before it serves usable corrections**. So:
- RC arms the base **well before the warning signal**, not at the gun.
- Wait for the `rc_pin` and RC positions to reach FIXED before capturing line endpoints.
- Rovers should be powered + receiving corrections early enough to be FIXED by the prep signal.

## 7. Sequenced plan + the two independent bench gates

Wire the two halves together **only after both gates are green** — each isolates one failure domain.

- **Gate A — relay correctness, NO GNSS. ✅ PASS (2026-06-05, E6, `edge-e/firmware/gate_a_relay_test/`).** `SELFTEST` mode, all 5 scenarios green: synth-CRC, clean+2×-dedup (complete=8 dup=19 0 mismatch), out-of-order reassembly, single-frag-loss clean-drop, bulk-20%-loss zero-corruption (200 sent → 184 survived w/ 2×-tx, **0 corrupt**). **Caught a real bug** (see "trailing-duplicate" below) before it reached firmware. `PRODUCER`/`CONSUMER` modes for a 2-board ESP-NOW transport test remain optional (real-RF loss budget → M3). The fragment/reassemble/CRC code here is production-bound — drops into `meshOnReceive`→ring→UART.
- **Gate B — base emission, NO ESP-NOW.** Run on **both chips** (one board each, antenna open sky):
  - **B-base ✅ FULL PASS (2026-06-04, E6 + LC29HEA, sketch `edge-e/firmware/lc29h_base_test/`):** the documented command set works as written. `$PQTMCFGRCVRMODE,W,2` + `$PQTMCFGSVIN,W,1,60,...` + `$PQTMSAVEPAR` + `$PAIR023` reboot, then all 4 enables ACK'd `$PAIR001,<id>,0` = SUCCESS (incl. **MSM7 `$PAIR432,1` — no "command sending failed" on this unit's firmware**). Streamed the **complete base set: MSM7 1077/1087/1097/1117(QZSS)/1127 + ephemeris 1019/1020/1042/1046 + station position 1005** at ~460–590 B/s (matches the ~500 B/s budget). **1005 appeared at t+120 s** = 60 s survey-in min + open-sky acquisition (on the bench, poor sky, survey-in never converged so 1005 was absent — open sky fixed it; alternatively use fixed-coord `$PQTMCFGSVIN,W,2,0,0,<x>,<y>,<z>`, rough ECEF OK since base error is common-mode). Command set now empirically pinned, not web-trusted. **A fully B-chip RTK fleet (B base + B rovers) is now proven at the chip level.**
  - **E-base:** LG290P Base mode + `PQTMCFGRTCM`; confirm 1 Hz MSM7 + 1006 + ephemeris (revives `08cdadfe`).
  - Both: verify short survey-in convergence + byte rate on current firmware.
- **M2 — first end-to-end ✅ THROUGH REAL FIRMWARE (2026-06-05, E4 LG290P base → mesh → E6 LG290P rover, no NTRIP):** relay byte-perfect — 950 frames over 160 s, `crc_fail=0 dropped=0 bad=0`, dedup working, ~6 frames/s. Rover reached **FLOAT q=5** off purely mesh-relayed corrections (requires base 1005 + obs → whole chain validated). **Did NOT reach FIXED q=4** — the same antenna-env/ambiguity limit as all bench tests (FLOAT indoors/marginal, FIXED needs genuine open sky), NOT a firmware/relay issue. **q=4-in-open-sky is the only remaining step before the push-to-main gate is satisfied.** (Original M2 plan was LC29HEA rover; ran LG290P rover instead since both boats had LG290P.)
- **M3 — scale + coexistence:** 6 rovers + the 2 Hz boat-state broadcast load on channel 1. Measure fragment loss %, fix-hold duration, time-to-fix at range over water.
  - **✅ 2-board transport verified (2026-06-05, E4 producer → E6 consumer, real ESP-NOW ch1, bench range):** `pkts=896 complete=188 crc_fail=0 dropped=0 dup=448 bad=0` over ~40 s. Byte-exact over the air (0 CRC fail), 2×-tx deduped, 0 loss at close range. Setup trick: power the producer standalone (battery/charger) and connect only the consumer to the Mac — sidesteps the duplicate `SLAB_USBtoUART`/`usbserial-0001` node naming (generic, reused per-board; identify boards by MAC via `esptool chip-id` — E6=`70:4b:ca:25:a1:b8`, E4=`70:4b:ca:26:1f:90`). **Still TODO for full M3:** loss % at range/over-water + coexistence under the 2 Hz boat-state load + multiple rovers.
- **M4 — OCS integration:** `rc_pin` rover + RTK-captured `race arm`; two FIXED boats show cm-stable relative distance; 0.5 m threshold becomes meaningful.
- **M5 — LG290P rover gate ✅ PASSED (2026-06-04, off critical path, done early):** E6+LG290P open sky, sketch `edge-e/firmware/lg290p_rtk_test/`, NTRIP MaCORS IMAX → **GGA quality 4 = FIXED at t+88 s**, held ~75 s. AANR01A06S *does* emit 10 Hz RTK-FIXED while ingesting 1 Hz RTCM — the input-side gate is cleared. Both chips now proven RTK rovers; **all 6 E1 boats can be RTK rovers.** (Slower TTF + end-on-FLOAT was NTRIP-stream stalls over a flaky hotspot, not a chip limit; the RC-base-over-ESP-NOW path replaces NTRIP.)

## 8. Chip-agnostic abstraction (build during this work)

```
CHIP-AGNOSTIC (shared E + B): RTCM frame-parser, ESP-NOW fragment/reassemble,
                              ring→UART drain, RTCM3→UART write, GGA quality parse, OCS.
CHIP-SPECIFIC (thin driver):  gnssConfigure(platform, role)
                                E + BASE  → PQTMCFGRCVRMODE,W,2 / PQTMCFGRTCM,W,7,... / re-enable NMEA
                                E + ROVER → PQTMCFGRCVRMODE,W,1 / PQTMCFGRTK,W,1,2,120 / FIXRATE,100
                                B + ROVER → $PAIR rover/RTK/10 Hz  (Phase-1 proven)
                                B + BASE  → $PQTMCFGRCVRMODE,W,2 (shared!) / $PQTMCFGSVIN /
                                            $PAIR432(MSM7→MSM4 fallback)+$PAIR434+$PAIR436 / $PAIR062 GGA
                                            — re-issue RTCM enables each boot (non-persist)
                              branch on config.hardware_platform.

Note how little is chip-specific: base *mode* + survey-in + save are the **same `$PQTM` commands**
on both chips; only the RTCM-message *enables* differ (LG290P `PQTMCFGRTCM` vs LC29HEA `$PAIR432/434/436`).
Model the driver as `setBaseMode()` / `setSurveyIn()` (shared) + `enableRtcmOut()` (per-chip).
```

## 9. Open risks (resolve empirically, in gate order)

1. **ESP-NOW broadcast reliability/ordering at range over water** (multipath, distance). Loss is tolerable to 120 s diff-age, but sustained loss → float-not-fix. → M3 measures it; 2×-tx + dedupe is the first mitigation.
2. **Survey-in convergence time + true common-mode behavior** of a ≤3 m base offset. → Gate B + M4.
3. ~~**LG290P rover RTK-in on AANR01A06S**~~ ✅ RESOLVED 2026-06-04 (M5 passed, q=4 FIXED). Both chips proven.
4. **Does Base mode leave the RC enough NMEA** (1 Hz) for its own fleet-OCS math? Plan: RC captures line endpoints once at arm time, so it doesn't need 10 Hz; verify GGA re-enable works in base mode.
5. **Dock AP association channel-hops off ch 1 and kills the mesh.** Moot on open water (no AP), but the firmware must not try to join a club AP while racing. Existing `wifiBusy`/`uploading` gates + no-AP-on-course covers it; note for ops.

## 10. Gotchas this design must respect

- **#25** — `static_assert` the new `RtcmFragPayload`; never write past `frag_len`. **Bound the SUM, not just each field:** the reassembler must reject `frag_index*RTCM_FRAG_MAX + frag_len > RTK_MAX_RTCM_FRAME` before the memcpy — individually-valid fields (index≤4, len≤230) still sum to 1150 > the 1045 B buffer (a spoofed/corrupt packet; real ≤1029 B frames never trip it). Found in review 2026-06-05.
- **Base UART RX overflow** — the base broadcasts RTCM (a few ms of `delayMicroseconds`) *inside* `readGPSBase()`'s read loop; at 460800 the default 256 B Serial2 RX FIFO fills in ~5.5 ms → dropped outgoing RTCM that looks like a relay bug on the rover. Mitigate: `Serial2.setRxBufferSize(2048)` before `begin()` + keep the inter-fragment delay small (250 µs).
- **#26** — `WiFi.disconnect(false)` keeps the radio for the mesh; `meshTick` already auto-recovers `ESP_ERR_ESPNOW_NOT_INIT`. On-course there's no WiFi cycle anyway.
- **Callback context** — reassembly buffer + ring head/tail are the only state the radio-task callback touches; the UART write lives in the loop.
- **RTCM-enable non-persistence on BOTH chips** — re-send every boot: LG290P `PQTMCFGRTCM`, LC29HEA `$PAIR432/434/436`. LC29HEA additionally reverts MSM7→MSM4 (benign — MSM4 does cm RTK); try MSM7, fall back to MSM4.

## Sources (LC29HEA base mode)

- [rtklibexplorer — Configuring the Quectel LC29HEA for real-time RTK](https://rtklibexplorer.wordpress.com/2024/05/06/configuring-the-quectel-lc29hea-receiver-for-real-time-rtk-solutions/) — base command sequence + the MSM7-doesn't-persist-to-flash caveat.
- [Quectel forum — LC29H (EA) mode base RTCM messages](https://forums.quectel.com/t/lc29h-ea-mode-base-rtcm-messages/57138) — `$PAIR432/434/436` enables, reboot-after-save, MSM7 `COMMAND SENDING FAILED` on some firmware.
- [Quectel forum — LC29HEA as base station](https://forums.quectel.com/t/lc29hea-as-base-station/44415) / [survey-in behavior](https://forums.quectel.com/t/survey-in-on-lc29hea-completes-instantly/39694).

---

*Companion to `RTK_PLAN.md`. Base-mode evidence: `RTCM_PPK_ARCHIVE.md`. Mesh wire types/dispatch: `edge-e/firmware/sailframes_edge/mesh.h` + `meshOnReceive`/`meshInit` in `sailframes_edge.ino`.*
