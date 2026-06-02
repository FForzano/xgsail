# Real-Time RTK for E1 OCS — Research & Plan

**Goal:** Make OCS (over-the-line at race start) resolve a **0.5 m** threshold. Today's
field test proved autonomous GPS has a ~2 m noise floor (the pin boat read ~2.4 m off
*itself*; separate-device errors don't cancel), so RTK is required.

**Status:** Research done 2026-06-02 (deep-research, 21 sources, 23 verified claims).
Not yet implemented. This supersedes the autonomous-GPS OCS for accuracy purposes.

---

## TL;DR — two phases

- **Phase 1 (proof, bench/backyard over WiFi):** the LG290P is *already* in 10 Hz Rover
  mode and accepts RTCM3 input on any UART **by default** (`PQTMCFGPROT` bit 2 = RTCM3,
  default `0x5` on UART1–3). Enable/tune RTK with `PQTMCFGRTK,W,1,2,120` (Auto + relative
  mode, 120 s diff-age). Feed it corrections from **RTK2go** (`rtk2go.com:2101`, plain TCP
  NTRIP v1 — works around the broken-TLS ESP32). Watch NMEA GGA quality → **4 = RTK FIXED**
  (cm), 5 = float. **The one unknown to confirm empirically:** does firmware AANR01A06S
  actually emit 10 Hz RTK-FIXED while ingesting 1 Hz corrections (it silently violated spec
  on the MSM *output* side before — input side is spec-clean but field-unverified).
- **Phase 2 (race course, no internet):** RC boat = local RTK base (LG290P Base mode,
  locked 1 Hz, emits `1005` every ~10 s + MSM7 `1077/1087/1097/1127` at 1 Hz). Relay RTCM3
  over the existing **ESP-NOW mesh** with fragment/reassemble (prior art: LoRa RTCM relays,
  same ~256 B cap). Rovers still output 10 Hz RTK off the 1 Hz corrections. **Survey-in base
  is fine** — base-position error is common-mode across all rovers, so relative fleet
  accuracy stays cm (a 3 m base offset → sub-mm relative error at race-course ranges).

---

## Findings (confidence / adversarial vote)

### Correction source (Phase 1)
- **RTK2go** — `rtk2go.com:2101`, **plain TCP NTRIP v1** (status `http://rtk2go.com:2101/SNIP::STATUS`),
  satisfies the broken-TLS constraint. Free; serves standard RTCM3 (MSM4/7 + 1005/1006), 800+
  live stations. Pull the nearest live mountpoint. **Recommended starting point.** (high, 3-0)
- **MaCORS** (MassDOT) — strongest free Boston source: free w/ registration, NTRIP user/pass auth,
  mountpoint **`RTCM3MSM_IMAX`** (GPS+GLO+GAL+BDS), ~20 km baselines around Boston, 1–3 cm.
  CAVEATS: it's **MSM4** (not 7), a **VRS/iMAX** stream needing **rover GGA upload** + auth, and
  its **plain-TCP reachability is unconfirmed** (may be TLS-only → unusable on this ESP32). (high, 3-0)
- Commercial trials (Skylark/PointOne, PointPerfect, Onocoy, Geodnet): no verified plain-TCP NTRIP v1
  endpoint found — likely TLS/token/PPP-RTK, treat as unusable under broken-TLS until proven.
- NOAA/NGS CORS: post-processing/RINEX only, not a real-time stream.

### LG290P RTK rover config (Phase 1)
- RTCM3 input accepted on any UART by default (`PQTMCFGPROT` bit2, default `0x5`). No input-side
  mode restriction found — but **spec-level only, not field-verified on AANR01A06S** (medium, 2-1).
- `PQTMCFGRTK,W,<DiffMode>,<RelMode>[,<Timeout>]`: DiffMode `1`=Auto, RelMode `2`=relative
  (cm relative to base — the OCS case), Timeout default 120 s. → **`PQTMCFGRTK,W,1,2,120`**. (high, 3-0)
- Fix confirmation: **NMEA GGA quality 4 = RTK FIXED** (use this), 5 = float. (high, 3-0)
- Base mode locked to **1 Hz** (`PQTMCFGRCVRMODE,W,2`); Rover mode 10 Hz (`,W,1`); `PQTMCFGFIXRATE`
  in ms. 1 Hz corrections → 10 Hz rover RTK is standard practice. (high, 3-0)

### ESP-NOW relay (Phase 2)
- Base RTCM set: MSM7 `1077/1087/1097/1127` @ 1 Hz + `1005` (or `1006`) every ~10–30 s. Rover needs
  one of 1005/1006 to locate relative to base. (high, 3-0)
- RTCM3 frames ~100–1200 B → fragment to <~250 B ESP-NOW packets, reassemble + parse on rover, write
  to GNSS UART. Direct prior art: TinkerBug LoRa relay (256 B cap, same pattern). RTCM is loss-tolerant
  (rover rides 120 s diff-age). (high, 3-0)
- Throughput ~0.5–1 KB/s ≈ 3–6 frags/s — fits alongside the 2 Hz boat-state broadcast on channel 1.

### Accuracy concept
- **Survey-in base sufficient for OCS:** RTK is cm *relative* to base; base error is common-mode →
  cancels in rover-to-rover/relative positions. ≤3 m base error acceptable when only relative matters.
  (high, 3-0, 7 claims merged)

---

## Open questions (resolve empirically)
1. **Does AANR01A06S output 10 Hz RTK-FIXED while ingesting 1 Hz RTCM?** ← the Phase-1 gate.
2. Is MaCORS reachable over plain-TCP NTRIP v1 (or TLS-only)?
3. Any commercial trial usable under broken-TLS (plain-TCP NTRIP v1)?
4. Real ESP-NOW throughput/loss budget for fragmented RTCM3 sharing channel 1 with boat-state + WiFi.

---

## Task list

### Phase 1 — NTRIP-over-WiFi proof (do first; confirms RTK rover before any mesh work)
1. Register on RTK2go; pick nearest live mountpoint (or MaCORS `RTCM3MSM_IMAX` if plain-TCP confirmed).
2. Minimal **NTRIP v1 client over plain TCP** on the ESP32: connect `host:2101`, send
   `GET /<mountpoint> HTTP/1.0` + `Ntrip-Version: Ntrip/1.0` + Basic auth if needed; stream RTCM3.
   Upload a GGA sentence if the mountpoint is VRS/iMAX.
3. Pipe received RTCM3 straight to the LG290P UART (input default already accepts it; set
   `PQTMCFGPROT` explicitly if needed).
4. Issue `PQTMCFGRTK,W,1,2,120`; confirm `PQTMCFGFIXRATE` keeps 10 Hz in Rover mode.
5. Parse GGA quality; log time-to-FLOAT(5) then time-to-FIXED(4); **VERIFY 10 Hz GGA stays quality 4
   while ingesting 1 Hz corrections** (the AANR01A06S unknown). ← gate before Phase 2.

### Phase 2 — RC-boat base + ESP-NOW relay (only after Phase 1 passes)
6. RC LG290P → Base mode (`PQTMCFGRCVRMODE,W,2`, locks 1 Hz), survey-in position, emit
   `1005` ~every 10 s + MSM7 `1077/1087/1097/1127` @ 1 Hz.
7. RC ESP32: read RTCM3 off GNSS UART, frame-parse (length from 3-byte header), fragment into
   ESP-NOW packets (<~250 B) with new `MSG_RTCM_FRAG` = {msg_id, frag_index, frag_count, payload}.
8. Rover ESP32: reassemble by msg_id, drop incomplete/timed-out frames, write completed RTCM3 to UART.
9. Coexist on channel 1 with the 2 Hz boat-state broadcast + intermittent WiFi; budget throughput;
   respect `WiFi.disconnect(false)` ESP-NOW-teardown gotcha (#26).
10. `static_assert` every new packed wire struct (gotcha #25).

---

## Multi-chip scalability (E = LG290P, B = LC29HEAMD)

The RTK design must span both GNSS chips in the fleet. **The chip boundary is
RTCM3-in / NMEA-out, which is identical on both** — so almost everything is reusable.

- **LC29HEAMD (B1 U1) does RTK rover at 10 Hz** (10 Hz default), same role as the LG290P
  rovers. Confirmed: rtklibexplorer LC29HEA RTK guide + Quectel LC29H DR&RTK App Note.
- Command dialect differs: LG290P = Quectel **`PQTM…`**; LC29H = Airoha/MediaTek **`$PAIR…`**.
- RTCM3 input (rover) is a UART byte stream on both → feeding corrections is the **same
  `Serial.write(rtcm)`** call regardless of chip. Fix readout is the **same NMEA GGA quality
  4/5** parse on both.
- LC29H base quirk: `$PAIR432` (RTCM MSM7 output) **does not persist to flash** — reverts to
  MSM4 after power-cycle. Only matters if a B-device is the base; re-issue each boot if so
  (same pattern as the LG290P's non-persisting `PQTMCFGRTCM`).

**Abstraction to build now (while writing E1 RTK):**
```
CHIP-AGNOSTIC (shared E + B): NTRIP client, ESP-NOW RTCM relay, RTCM3→UART write,
                              NMEA GGA quality parse, OCS computation.
CHIP-SPECIFIC (thin driver):  gnssConfigure(platform, role) →
                                E1 → PQTMCFGRCVRMODE / PQTMCFGRTK,W,1,2,120 / PQTMCFGFIXRATE
                                B1 → $PAIR rover/RTK/rate equivalents
                              branch on config.hardware_platform.
```
**Fleet rules:** rovers can be mixed E + B freely (relay payload is chip-blind). Keep the
**base on one known-good LG290P** (1 Hz base lock is fine for RTK; avoid the LC29H base
MSM7-flash quirk). B1 firmware doesn't exist yet (only KiCad hardware) — the B1 GNSS bring-up
later is just the `$PAIR` implementation behind this interface.

## Key sources
- Quectel LG290P(03)&LGx80P(03) Protocol Spec v1.1 (PQTMCFGPROT §2.3.12, PQTMCFGRTK §2.3.29,
  PQTMCFGFIXRATE §2.3.28) — via SparkFun.
- RTK2go (rtk2go.com), MaCORS (macors.massdot.state.ma.us).
- TinkerBug LoRa RTCM relay (fragment/reassemble prior art); slgrobotics/Esp32_RTK_BaseStation.
- SBG / NovAtel / Wikipedia RTK (relative vs absolute, common-mode base error).

*Generated from deep-research run wf_a9494623-41c, 2026-06-02.*
