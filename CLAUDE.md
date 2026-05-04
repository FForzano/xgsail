# SailFrames — Sailboat Racing Data Logger

## Project Context for Claude Code

**Note:** S1 (Raspberry Pi single-boat analysis device) was shelved.
All S1 hardware/software notes live in `docs/S1_LEGACY.md`. This file
is focused on the deployed system: ESP32 **E1** fleet trackers (×6) and
the web race dashboard.

---

## Project Overview

**SailFrames** is an open-source sailboat racing data logger and analytics platform.

- **License:** Apache 2.0
- **GitHub org:** github.com/sailframes
- **Main repo:** github.com/sailframes/core
- **Domain:** sailframes.com (AWS-hosted)
- **Cloud:** AWS (S3 + Lambda + CloudFront + Route 53)
- **S3 bucket:** `sailframes-fleet-data-prod`
- **Fleet:** 6 boats — Sonar 23 / J/80 class, Boston Harbor

The fleet captures GPS + IMU + (some) wind during races, uploads to S3
post-sail, and provides a web dashboard for race replay and analytics.

**Strategic differentiator:** SailFrames is the first sailing analytics
platform using PPK (Post-Processed Kinematic) GNSS — leveraging free NOAA
CORS base station data via RTKLIB for sub-meter accuracy with no base
station hardware.

---

## Repository Structure (Monorepo)

```
sailframes/core/
├── CLAUDE.md              # This file — E1 + web project context
├── docs/
│   └── S1_LEGACY.md       # Shelved Raspberry Pi notes
├── edge-e/                # ESP32 device (E1 = first gen)
│   ├── hardware/          # KiCad PCB v1.1 (Gerbers ordered)
│   └── firmware/          # ESP32 Arduino firmware (sailframes_e1.ino)
├── edge-s/                # LEGACY — Raspberry Pi (see docs/S1_LEGACY.md)
├── web/                   # Race dashboard
│   ├── api/               # FastAPI backend
│   ├── assets/            # JS / CSS for dashboard pages
│   ├── *.html             # race.html, sessions.html, etc.
│   └── frontend/          # (legacy React, mostly deprecated)
├── processing/            # Python analytics (maneuvers, polar, stats)
├── lambda/                # AWS Lambda (post-upload processing, APIs)
├── infrastructure/        # CDK/Terraform + deploy.sh
├── scripts/               # Utility scripts (flash-e1.sh, sync, repro)
├── export/                # Report / video export
└── .github/workflows/     # CI: firmware-e1.yml builds the .bin on push
```

---

## E1 Hardware Stack (ESP32 Fleet Tracker)

| Component | Part | Interface | Notes |
|---|---|---|---|
| MCU | ELEGOO ESP32 DevKit V1 (CP2102) | USB-C | Dual-core 240 MHz, Wi-Fi + BLE |
| GPS | Waveshare LG290P GNSS module | UART2 (GPIO16/17) | Quad-band, PPK-capable, ~$109 with antenna |
| IMU | GY-BNO08X (BNO085) | I2C (GPIO21/22) @ 0x4A | Heel/pitch, GAME_ROTATION_VECTOR mode |
| Display | Hosyond 3.5" IPS TFT (ST7796U) | SPI VSPI (480×320) | Sunlight-readable, white background |
| Storage | microSD module | SPI HSPI (separate bus) | CSV + raw RTCM3 binary for PPK |
| Power | DWEII USB-C 5V 2A boost charger | 5V → ESP32 VIN | LiPo charging + protection + boost |
| Battery | 906090 3.7V 6000 mAh LiPo | JST PH 2.0 mm | ~10+ hours runtime |
| Enclosure | YETLEBOX IP67 ABS clear lid | — | Daily install/remove |
| Wind (one boat) | Calypso Ultrasonic Portable Mini | BLE 5.1 | Apparent wind; only on E1 currently |

Future expansion (PCB headers): wind UART1 (GPIO32/33), I2C connectors
for DPS310 / extras, GPIO header (D26, D15, VP, VN).

### Power Management

- DWEII boost charger handles LiPo charge + 5V boost
- SPDT slide switch on boost-output → ESP32 VIN
- Battery monitoring: GPIO34 ADC via 2× 100KΩ voltage divider
- Battery % shown on bottom bar of TFT

### E1 Wiring Summary

**TFT (VSPI) and SD (HSPI) MUST be on separate SPI buses** — sharing one
bus causes severe display flicker during SD writes.

```
LG290P GPS (UART2):
  TXD3 → GPIO16 (RX2)  ⚠ NOT GPIO21/22 (those are I2C)
  RXD3 → GPIO17 (TX2)
  5V → boost-module 5V, GND → GND

BNO085 IMU (I2C):
  SDA → GPIO21,  SCL → GPIO22
  VCC → 3V3 from ESP32, GND → GND

TFT ST7796U (VSPI):
  MOSI → GPIO23, MISO → GPIO25 (swapped with BL),
  CLK → GPIO18, CS → GPIO5, DC → GPIO2, RST → GPIO4,
  BL → GPIO19 (swapped with MISO),  VCC → 3V3, GND → GND

SD card module (HSPI — SEPARATE from TFT):
  CLK → GPIO14, MISO → GPIO35 (input-only, avoids GPIO12 strapping issue),
  MOSI → GPIO13, CS → GPIO27, VCC → 3V3, GND → GND

Battery:
  Boost OUT+ → SPDT switch → ESP32 VIN
  Boost OUT- → GND
  LiPo B+ → boost B+, also → 100K → GPIO34 → 100K → GND
  LiPo B- → boost B-

Future expansion:
  Wind UART1: GPIO32 (RX), GPIO33 (TX)
  I2C expansion: shared bus on GPIO21/22
  GPIO expansion: GPIO26, GPIO15, VP (GPIO36), VN (GPIO39)
```

### KiCad PCB v1.1

**Status:** Gerbers ordered from JLCPCB (April 18, 2026).
**Specs:** 60.5 × 91.5 mm, 2-layer, 1.6 mm, green solder mask.
**Files:** `edge-e/hardware/kicad_sailframes-e1/`

Connectors: ESP32 DevKit V1 (U1), TFT (U2), SD module (J1),
LG290P GPS (J2), BNO085 (J3), DPS310 (J4 future), boost module (J5),
I2C expansion (J6/J7), wind sensor (J8), GPIO expansion (J9),
battery JST (J10), SPDT power switch (SW1), voltage divider 2×100KΩ
(R1/R2), I2C pull-ups 2×4.7KΩ (R3/R4).

Layout: ground pour on B.Cu for EMI, 4× M2.5 mounting holes at corners,
Freerouting + manual cleanup.

---

## E1 Firmware (`edge-e/firmware/sailframes_e1/sailframes_e1.ino`)

- NMEA parsing (GGA/RMC/GSA/GSV) from LG290P
- Raw RTCM3 binary capture for PPK post-processing
- BNO085 reads at 1 Hz (was 20 Hz, reduced — sailing doesn't need 20 Hz)
- DPS310 pressure at 0.1 Hz (weather trends; not gust detection)
- SD logging: CSV (human-readable) + raw `.rtcm3` binary
- TFT: speed/COG huge, status bar, Vakaros-style white background
- Battery monitoring (GPIO34 ADC + voltage divider)
- Wi-Fi auto-upload to S3 over plain HTTP on yacht-club / Home-IOT detection
- GPS-speed-triggered auto-recording (start >2 kt, stop after sustained <0.5 kt)
- Power-button toggle of recording
- Configuration via SD `config.txt`

### Pinned library / core versions (do NOT auto-update)

- ESP32 board package **3.3.7** (3.3.8 breaks I2C and TFT)
- TFT_eSPI (latest)
- NimBLE-Arduino **2.4.0** (2.5.0 has BLE/WiFi switching issues)
- Adafruit BusIO 1.17.4
- Adafruit GFX 1.12.6
- Adafruit BNO08x 1.2.5
- Adafruit DPS310 1.1.3

**Partition scheme:** `Minimal SPIFFS (1.9 MB APP with OTA / 128 KB SPIFFS)`.
This keeps OTA partitions for any future firmware-pull mechanism. Do NOT
use `huge_app` — it disables OTA.

### TFT layout (D2)

Row 1 (y=440, font 2): heel + pitch + AWS + AWA when wind connected;
heel + pitch alone when no wind sensor. Single row.

Row 2 (y=458): left = `BAT N% [W]`, right = WiFi indicator + upload counts.
Counts split into:
- `N` = sessions with non-RTCM3 files still pending
- `R` = sessions with RTCM3 files still pending

### Serial / telnet commands

| Command | Description |
|---------|-------------|
| `start` / `stop` | Manual start/stop recording |
| `recstate` | Show recording state |
| `upload` | Trigger Wi-Fi upload |
| `clearmarkers` | Delete `.uploaded` markers (retry uploads) |
| `cleanup` | Delete already-uploaded files |
| `status` | GPS/IMU/SD/WiFi/RTCM frame count |
| `gps` / `gpsraw` / `gpscfg` | GPS debug |
| `config` | Show config |
| `telneton` / `telnetoff` | Enable/disable runtime telnet listener |

Telnet listener defaults **OFF** — its `WiFiServer.hasClient()` calls
deadlocked Core 1 inside LWIP under upload contention (firmware
2026.05.03.04 fleet hang). Enable with `telneton` for live debug.

### SD card layout

```
/sf/
├── 20260405_225030/                # Session folder (GPS datetime)
│   ├── E1_20260405_225030_nav.csv  # NMEA parsed
│   ├── E1_20260405_225030_imu.csv
│   ├── E1_20260405_225030_raw.rtcm3
│   ├── E1_20260405_225030_wind.csv
│   └── E1_20260405_225030_pres.csv
├── boot.log                         # Reset reason / heap per boot
├── config.txt
└── wind_mac.txt                     # Calypso MAC; presence = wind enabled
```

### `boot.log` format (since 2026.05.03.08)

Each boot appends one line: `boot fw=<ver> reset=<reason> heap=<free> min_heap=<min>`
where `reset` is one of `POWERON / SW / PANIC / TASK_WDT / INT_WDT / BROWNOUT / DEEPSLEEP / EXT`.

---

## E1 Wi-Fi Upload Architecture

ESP32 Arduino Core 3.3.7 has broken TLS (mbedTLS BIGNUM allocation
failures). The E1 uploads **directly to S3 over plain HTTP**, bypassing
API Gateway entirely.

**Endpoint:**
```
http://{bucket}.s3.{region}.amazonaws.com/raw/E1/{date}/{filename}
```

**Flow:**
1. E1 connects to known Wi-Fi (yacht club / Home-IOT)
2. DNS + TCP test to S3 on port 80
3. HTTP PUT direct to S3
4. Bucket policy allows unauthenticated PUT to `raw/E1/*` paths

**S3 bucket policy snippet:**
```json
{
  "Sid": "FleetDirectHTTPUpload",
  "Effect": "Allow",
  "Principal": "*",
  "Action": "s3:PutObject",
  "Resource": "arn:aws:s3:::sailframes-fleet-data-prod/raw/*"
}
```

**Markers:** After each successful PUT we create `<filename>.uploaded` so
retries skip done files. `clearmarkers` over serial wipes them.

**Why HTTP, not HTTPS:** ESP32 TLS is fundamentally broken in 3.3.7
("RSA - public key operation failed: BIGNUM - Memory allocation failed").
Fleet data isn't sensitive; S3 supports HTTP natively. See
`infrastructure/aws/E1_HTTP_UPLOAD_SETUP.md`.

### BLE / Wi-Fi shared-radio coexistence

ESP32 has a single shared radio. Under heavy WiFi (large RTCM3 PUTs),
NimBLE scan calls can stall indefinitely. The firmware:

1. `pauseBLEForWiFi()` at the start of `connectWiFi()` — stops in-flight
   scans and disconnects any wind client.
2. `checkWindConnection()` early-returns when `wifiConnected || uploading
   || triggerUpload`.
3. `wifiBusy` flag gates Core 1 LWIP-touching paths during upload (telnet
   stop, stale-flag teardown, teardown branch).

**Required deinit order if you ever reintroduce BLE deinit:** disconnect
WiFi BEFORE BLE. `NimBLEDevice::deinit(false)` only — `deinit(true)` causes
heap corruption.

### Watchdog + diagnostic heartbeat

- Task watchdog timeout: 300 s (was 120 s; bumped after a 660 KB RTCM3 PUT
  could take >120 s on weak signal). Both `loopTask` and `uploadTaskFunc`
  subscribed to it.
- A separate `diagnosticsTask` on Core 0 prints every 5 s:
  `[DIAG] uptime=Ns heap=H sect=<section> iter=<count> (+delta)`.
  When `loopTask` hangs, the diag heartbeat keeps printing — the last
  `sect=` value names the section Core 1 was inside. This pinpointed the
  `handleTelnet` hang in firmware 2026.05.03.04.

---

## GNSS Strategy

| Tier | Receiver | Use | Cost | Accuracy |
|---|---|---|---|---|
| Fleet (E1 ×6) | Quectel LG290P (Waveshare) | All 6 boats | ~$109 | Sub-meter (PPK) |

LG290P logs raw RTCM3 observations during racing. Post-race we download
NOAA CORS base data (`geodesy.noaa.gov/UFCORS`, free, ~1 hr after
recording) and process in RTKLIB.

### LG290P configuration

The Waveshare LG290P uses Quectel's PQTM commands. Best configured via
**QGNSS on Windows** — PyGPSClient on macOS has limited support.

USB-C: PC config (CH343 USB-serial). UART SH1.0: ESP32 connection at
460800 baud. RST button: single press reboots; no factory reset.

RTCM3 PPK config (saved to NVM):
```
$PQTMCFGRTCM,W,7,0,-90,07,06,1,0*       # MSM7 for all constellations
$PQTMCFGMSGRATE,W,RTCM3-1019,1*         # GPS ephemeris
$PQTMCFGMSGRATE,W,RTCM3-1020,1*         # GLONASS ephemeris
$PQTMCFGMSGRATE,W,RTCM3-1042,1*         # BeiDou ephemeris
$PQTMCFGMSGRATE,W,RTCM3-1046,1*         # Galileo ephemeris
$PQTMCFGMSGRATE,W,RTCM3-1006,10*        # Station ref every 10 epochs
$PQTMCFGCNST,W,1,1,1,1,1,1*             # Enable all constellations
$PQTMSAVEPAR*
$PQTMHOT*
```

**PQTMCFGMSGRATE syntax:** firmware AANR01A06S uses TWO parameters
(message, rate). Three-parameter form returns `ERROR,1`.

**E1 firmware sends RTCM3 config at every boot** (not relying on QGNSS
pre-config), so devices replaced from spare stock work without manual
configuration.

RTCM3 messages output:
- 1077 / 1087 / 1097 / 1127 — GPS / GLO / GAL / BDS MSM7 (every epoch)
- 1019 / 1020 / 1042 / 1046 — ephemerides (~30 s)
- 1006 — station reference (every 10 epochs)

### PPK post-processing

1. Race produces `*.rtcm3` files on SD
2. Download CORS base data from NOAA UFCORS for that day
3. RTKLIB (RTKPOST): rover .rtcm3 + base obs + nav → fixed solution
4. No base station hardware needed — uses free NOAA infrastructure

### Dashboard GPS display

- Satellites in fix: from GSA sentences (actually contributing)
- Satellites in view: from GSV sentences (visible, may not be used)
- Per-constellation: GPS / GLONASS / Galileo / BeiDou color-coded

---

## BNO085 IMU Configuration

### Recommended mode: GAME_ROTATION_VECTOR (6DOF, no magnetometer)

```python
import adafruit_bno08x
bno.enable_feature(adafruit_bno08x.BNO_REPORT_GAME_ROTATION_VECTOR)
```

The 9DOF ROTATION_VECTOR includes the magnetometer, which is unreliable
on a sailboat (lead keel, stainless rigging, engine causing 10–20°
heading drift; can also corrupt roll/pitch). GPS COG is more reliable
above ~2 kt.

### Calibration

- Startup tare to record current orientation as zero (accounts for mounting)
- Daily boat changes — software calibration keyed to known heading
- Gyro auto-zeros on startup (hold still 2-3 s)
- Accelerometer gravity reference handles heel/pitch automatically
- Log calibration accuracy bits for post-race quality assessment

---

## Web Race Dashboard (`web/race.html`)

Single-page dashboard for live + post-race fleet visualization. Hosted at
sailframes.com behind CloudFront.

**Tier 1 (shipped):** map with boat tracks + markers, leaderboard ranked
by along-course distance, three stacked time-axis comparison charts
(Speed / Heel / NOAA TWD), playback scrubber + cursor on all charts,
team-color toggles.

**Tier 2 (shipped):** course-aware ranking — `(legsCompleted DESC,
distToNext ASC)` — VMG to next mark, gap to leader in meters, mark
roundings precomputed at race load (35 m radius).

**Tier 2.5 (shipped):** NOAA wind integration. Castle Island (CSIM3)
primary, Logan (KBOS) and Boston 16NM (44013) selectable. TWD/TWS badge
in panel header, TWD curve in 3rd chart, raceAvgTWD-driven layline
overlay on map (J/80 upwind tack angle 42°), per-boat TWA in leaderboard
tile, vector-mean TWD interpolation (handles 0/360 wraparound).

**Tier 3 (shipped):**
- Wind rose marker on map at NOAA station, rotates with TWD
- J/80 polar table embedded (Seapilot, 7 TWS × 10 TWA), bilinear interp,
  synthesized optimal-beat row prepended; %polar in leaderboard
- Per-boat detail drawer (click boat marker or leaderboard row) — slides
  in from right with motion / IMU / onboard wind / NOAA wind / polar /
  next-mark stats. Esc or × closes.

**Pre-race ops (shipped 2026-05-03 night):**
- Layline toggle (Leaflet topright control)
- Wind source segmented picker (toolbar): Castle Is / Logan / 16NM
- Polar overlay toggle in speed-chart header
- Legs button → modal with per-leg per-boat summary table
- Maneuvers button → modal with tacks/gybes detection + per-team
  summary (avg loss, avg duration) and per-maneuver detail

### Mark types in the editor

- `windward` (top)
- `leeward` (bottom, single)
- `gate_port` + `gate_stbd` (paired bottom gate; fleet picks one to round)
- `offset` (small mark just below windward, common in modern J/80 racing)
- `custom`

### Deployment

Web changes go through:
1. `git push origin main`
2. `aws s3 cp <changed files> s3://sailframes-web-prod/...
   --cache-control max-age=60 --profile sailframes`
3. `aws cloudfront create-invalidation --distribution-id EFO342DVGM3QS
   --paths /<files>`

(The full `infrastructure/deploy.sh` also rebuilds Lambda — overkill for
HTML/JS-only changes.)

---

## Data Flow

```
[On boat]
  Sensors → ESP32 firmware → SD card

[Post sail]
  E1 → WiFi (HTTP) → s3://sailframes-fleet-data-prod/raw/E1/{date}/

[AWS pipeline]
  S3 ObjectCreated → Lambda (process_upload) → processed JSON
  CORS download Lambda → GPS rinex/nav → PPK-ready bundle
  NOAA buoy fetch Lambda → /api/buoys/data

[Web]
  Browser → CloudFront → S3-static (race.html, JS, CSS)
  Browser → CloudFront → API Gateway → Lambda → S3/processed JSON
```

**S3 path format (E1):** `raw/{device_id}/{date}/{filename}.csv`
e.g. `raw/E1/2026-04-01/E1_20260401_140000_nav.csv`.

**Race-data API:** `GET /api/races/{race_id}/data?sensors=gps,imu,wind`
returns `{boats: {device_id: {boat, sensors: {gps: [...], imu: [...], wind: [...]}}}}`.

**NOAA buoys API:** `GET /api/buoys/data?start_ts=...&end_ts=...` returns
`{buoys: {STATIONID: {data_points: [...], lat, lon, name, color}}}`.
Stations: 44013 / CSIM3 (Castle Island) / 44029 / BUZM3 / NTKM3 / KBOS (Logan).

---

## Known Issues & Gotchas (E1 + shared)

1. **DPS310 in sealed enclosure** — without a pressure vent the sensor
   reads internal pressure. Gore-Tex vent (Amphenol LTW VENT-PS1) required
   if the box is sealed.

2. **Calypso wind sensor BLE** — only one device can connect at a time.
   The boat's E1 will claim it; disconnect other phones/laptops first.

3. **DOP reflects geometry, not accuracy** — Good HDOP/VDOP indicates
   favorable satellite geometry but doesn't guarantee positional accuracy.

4. **E1 GPIO conflict** — GPS UART must use GPIO16/17 (UART2), NOT
   GPIO21/22 which are I2C. Edit net labels on the schematic sheet, not
   the component symbol.

5. **KiCad Footprint Editor** — access from the KiCad project launcher,
   not from the schematic editor.

6. **ESP32 BLE/Wi-Fi radio conflict** — single shared radio. Pause BLE
   scans before WiFi work; see `pauseBLEForWiFi()` in firmware.

7. **NimBLEDevice::deinit(true) crashes** — heap corruption. Always
   `deinit(false)`. Disconnect WiFi BEFORE deinitializing BLE if you ever
   need to deinit at all.

8. **macOS Spotlight files on SD card** — Mac creates `.Spotlight-V100`
   and `.fseventsd`. Firmware skips hidden files during upload. Disable
   indexing on the volume:
   `sudo mdutil -i off /Volumes/E1; touch /Volumes/E1/.metadata_never_index`.

9. **LG290P PQTM command syntax** — firmware AANR01A06S uses two-parameter
   `PQTMCFGMSGRATE` (message, rate). Three-parameter form returns
   `ERROR,1`. PyGPSClient on macOS has limited support — use QGNSS on
   Windows for first-time configuration.

10. **API Gateway 29-second timeout** — Lambdas behind API Gateway have a
    hard 29 s timeout. Large uploads via API Gateway fail with HTTP -3.
    E1 sidesteps this by uploading direct to S3 over HTTP.

11. **E1 GPS session folder naming** — uses GPS datetime when valid year
    + fix; falls back to `session_NNN` otherwise. Previously failed for
    days 1–9 / hours 00–09 UTC due to a first-character-only check; fixed.

12. **E1 deep sleep removed** — software deep sleep had button-still-pressed
    + GPS-stays-powered issues. Hardware SPDT slide switch now controls
    power.

13. **ESP32 TLS broken in Arduino Core 3.3.7** — mbedTLS BIGNUM allocation
    failures during RSA. Cannot reliably do HTTPS. E1 uploads to S3 over
    plain HTTP; bucket policy permits it for `raw/E1/*`.

14. **Calypso wind sensor 180° AWA inversion** — with the bow-mark
    forward, raw AWA is 180° off. Both E1 firmware and historical data
    apply `(raw_awa + 180) % 360`. `scripts/correct_wind_awa.py`
    backfilled S3.

15. **ESP32 GPIO12 is a strapping pin** — controls flash voltage at boot.
    Pull HIGH at boot → ESP32 fails. Do NOT use GPIO12 for SD MISO. Use
    GPIO35 (input-only) instead.

16. **TFT + SD SPI bus contention** — sharing one SPI bus causes display
    flicker during SD writes. TFT on VSPI, SD on HSPI. Eliminates flicker.

17. **ESP32 partition scheme for E1** — `Minimal SPIFFS (1.9 MB APP with
    OTA / 128 KB SPIFFS)`. Do NOT use `huge_app` — it disables OTA.

18. **ESP32 Arduino Core 3.3.8 breaks I2C and TFT** — devices not detected,
    display issues. Stick with 3.3.7. Downgrade with
    `arduino-cli core install esp32:esp32@3.3.7`.

19. **NimBLE-Arduino 2.5.0 BLE/WiFi switching issues** — use 2.4.0.
    `arduino-cli lib install "NimBLE-Arduino@2.4.0"`.

20. **`handleTelnet` deadlock under upload contention** (fixed
    2026.05.03.05) — `WiFiServer.hasClient()` calls share LWIP locks with
    Core 0's HTTP uploads and deadlock under sustained traffic. Telnet
    listener defaults OFF; enable with `telneton`.

21. **Simultaneous fleet reboots during slow uploads** (mitigated
    2026.05.03.08) — wdt could fire on a single 660 KB+ RTCM3 PUT at
    weak signal. Bumped wdt to 300 s. `boot.log` on SD now records reset
    reasons so future similar events are self-documenting.

---

## Weather Data Integration

- **NOAA NDBC buoys:** 44013 (Boston 16NM), CSIM3 (Castle Island), 44029,
  BUZM3, NTKM3
- **METAR:** KBOS (Logan)
- **GOES-16/19 imagery:** `s3://noaa-goes16/`, `s3://noaa-goes19/`
  via `goes2go` Python library (Boston BOX office offers regional crops)
- **NOAA Tides & Currents:** station 8443970
- **Open-Meteo** for forecasts
- **NOAA UFCORS** for free PPK base data

---

## Tools & Resources

- **GNSS:** QGNSS (LG290P config, Windows), RTKLIB (PPK post-processing),
  NOAA UFCORS, GNSS View app, pyubx2
- **Firmware development:** Arduino IDE, KiCad (schematic + PCB),
  Freerouting, JLCPCB
- **Cloud:** AWS S3, Lambda, CloudFront, Route 53, CloudFormation
- **Reference texts:** Groves 2013 (GNSS/INS), Kaplan & Hegarty,
  Teunissen & Montenbruck, Markley & Crassidis (attitude estimation),
  Madgwick

---

## Competitive Landscape (placeholder)

Differentiators worth preserving in product framing:
- PPK GNSS — only platform doing post-processed kinematic on the fleet
- Multi-sensor hardware (IMU + barometer + wind + camera-future)
- Fleet-wide simultaneous logging (×6 on the same course)
- Open source (Apache 2.0)
- No permanent install — under 30 second daily install/remove

Competitor brand names are kept out of code/docs; competitive analysis
lives separately.

---

## Project History (E1-relevant, pruned)

- **2026-03:** Repo reorganized as monorepo. `edge-e/` (ESP32) added.
- **2026-03-29:** E1 KiCad schematic complete, firmware written.
- **2026-04-04:** E1 BLE/WiFi fixes, presigned S3 URLs, HTTP uploads,
  `clearmarkers`, LG290P RTCM3 config via QGNSS.
- **2026-04-07:** TLS broken in Arduino Core 3.3.7 → direct-to-S3 HTTP
  uploads. Bucket policy for unauthenticated `raw/E1/*` PUT.
- **2026-04-08:** Calypso 180° AWA correction (firmware + historical S3).
- **2026-04-10–12:** TFT replaces OLED, separate SPI buses, DWEII boost
  charger, 6000 mAh LiPo, complete KiCad PCB v1.0.
- **2026-04-18:** PCB v1.1 (ground pour, mounting holes), Gerbers ordered.
  Race dashboard built (Leaflet + Chart.js, multi-boat).
- **2026-04-19:** Library version pinning documented (Core 3.3.7,
  NimBLE 2.4.0).
- **2026-05-01–03:** Fleet hang firefight resolved via diag heartbeat —
  `handleTelnet` LWIP deadlock isolated and disabled by default
  (2026.05.03.05). Reset-reason logging added (.08). TX power restored
  to 19.5 dBm (.09). All 6 devices verified stable.
- **2026-05-03:** Race dashboard Tier 2 → 3 (course-aware leaderboard,
  VMG, NOAA wind integration, polar overlay, per-boat drawer, layline
  toggle, wind source picker, leg + maneuver modals).

---

*Last updated: 2026-05-04 — S1 Pi notes split into `docs/S1_LEGACY.md`;
this file refocused on the deployed E1 fleet + web dashboard.*
