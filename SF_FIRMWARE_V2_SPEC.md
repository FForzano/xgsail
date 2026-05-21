# SailFrames Firmware v2.0.0 — Implementation Spec for Claude Code

**Target codebase:** `edge-e/sailframes_e1.ino` (single firmware, runs on both E1 and B1 hardware)
**Target version string:** `2026.06.xx.01` (date-based per existing scheme)
**Scope:** OCS, ESP-NOW fleet mesh, RC unit role, race setup, 10 Hz GNSS, cloud config sync, status snapshots
**Hard constraints (do not violate):**
- ESP32 Arduino Core **3.3.7** pinned. Do not upgrade. 3.3.8 breaks I2C/TFT.
- NimBLE-Arduino **2.4.0** pinned. Do not upgrade. 2.5.0 breaks BLE+WiFi switching.
- Partition scheme **Minimal SPIFFS** (1.9 MB APP with OTA / 128 KB SPIFFS). Do not change.
- TLS is broken in this stack — use plain HTTP for all uploads/downloads. SHA256 in-firmware for integrity.
- TFT (VSPI) and SD (HSPI) must remain on separate SPI buses.
- Telnet listener stays OFF by default (LWIP deadlock with HTTP upload — already documented in code).

---

## Pre-work for Claude Code: read before changing anything

1. Read `sailframes_e1.ino` in full. The file is ~5500 lines. Pay particular attention to:
   - The pin map (lines ~99-164) — verified against PCB v1.1, do not change
   - The OTA pull architecture (`performOTAUpdate`, lines ~3759-3955) — model new pull patterns on this
   - The telnet command interpreter (lines ~4075-4760) — extend it for new commands
   - The dual-core task split — Core 1 owns OTA/telnet/WiFi; Core 0 owns uploads. Do not violate.
   - The fleet-hang firefight comments (lines ~106-115, ~494-500) — explains why telnet defaults off

2. Read `BNO085_100k.h` — custom driver, 100 kHz I2C with reset sequence. Already working.

3. Read `User_Setup.h` — TFT_eSPI config. Note that `TFT_BL` is on GPIO19 in the file but `BNO085_100k.h` notes that the actual pin map has `TFT_BL` on GPIO25 (the User_Setup.h file may be stale or hand-soldered swapped). Verify against `sailframes_e1.ino` definitions before any display code changes.

4. Do not delete or rewrite existing working subsystems (Calypso BLE, OTA, upload, GPS RTCM3 config, IMU, TFT). Add alongside.

5. Use the existing `tprint`/`tprintf`/`tprintln` for any output that should be visible on both Serial and telnet.

---

## Hardware role detection

The single firmware runs on two hardware platforms. Add a compile-time or runtime detection:

```cpp
// Detect hardware platform at boot from a config field or hardware probe
// E1: GPIO19 unused (LG290P UART2)
// B1: GPIO19 connected to Hall flip-flop readback (will read defined state)
enum HardwarePlatform {
    HW_E1 = 1,
    HW_B1 = 2
};

// Set via config.txt: hardware_platform=e1 or b1
// Default: HW_E1 if not specified (backward compat)
```

Platform affects:
- GPS chip (LG290P on E1, LC29HEAMD on B1 — both speak PQTM, B1 also speaks PAIR commands)
- Hall sensor presence (B1 only)
- LED count and assignments (E1 has fewer LEDs)
- Enclosure: B1 sealed (no telnet via USB practical; uses BLE/WiFi only for debug)

For v2.0.0, the firmware should be platform-aware via a single `hw` global derived from config.

---

## Unit role system (new)

Add a runtime role flag to `config.txt`:

```
unit_role=racing_boat   # default
# Other values:
#   rc_signal           - signal-boat end of start line
#   rc_pin              - pin end of start line
#   mark                - course mark (broadcasts position, no recording)
#   committee_chase     - mobile chase boat (records + broadcasts + can host iPad UI)
#   spare               - not in service, minimal power
```

Role determines:
- Whether the device computes OCS for itself (racing_boat, committee_chase: yes; RC/mark: no, but RC computes for whole fleet)
- Whether it hosts a WiFi AP + HTTP UI (rc_signal: yes, others: no for v2.0.0)
- Recording behavior (mark: never; others: speed-triggered)
- ESP-NOW broadcast type (boat / line endpoint / mark / RC)
- Mic horn detection (rc_signal: yes; others: no)

Define an enum:
```cpp
enum UnitRole {
    ROLE_RACING_BOAT = 0,
    ROLE_RC_SIGNAL = 1,
    ROLE_RC_PIN = 2,
    ROLE_MARK = 3,
    ROLE_COMMITTEE_CHASE = 4,
    ROLE_SPARE = 5
};
```

Parse from config.txt at boot into a global `UnitRole g_role`.

---

## Radio mode state machine (new)

Replaces the current implicit "WiFi up + BLE up" model. Single owner on Core 1.

States:
```
BOOT      - radios off, initializing peripherals
IDLE      - transitional, radios off
DOCK      - WiFi STA up, uploads + OTA pull + config sync; ESP-NOW off; BLE-C (Calypso) if applicable
RACING    - ESP-NOW broadcasting/listening; WiFi off; BLE-C (Calypso) on wind-sensor boat only
RC_ACTIVE - ESP-NOW + WiFi AP up serving iPad UI (rc_signal/committee_chase only)
```

Transition triggers:
- BOOT → IDLE: setup() complete
- IDLE → DOCK: known dock SSID visible AND device stationary (SOG < 0.5 kt for 30s)
- IDLE → RACING: motion detected (SOG > 1.5 kt for 10s, matches existing recording-start logic) AND role is racing_boat or committee_chase or mark
- IDLE → RC_ACTIVE: role is rc_signal or rc_pin or committee_chase (always on for these)
- DOCK → IDLE: motion detected OR WiFi association lost
- RACING → IDLE: stationary 3 min (matches existing recording-stop)
- RC_ACTIVE → DOCK: rc unit returns to known dock SSID range
- Any → BOOT: hard fault or reboot

Implementation:
- Single `RadioMode g_radio_mode` global
- `radioModeTransition(RadioMode target)` function called from Core 1 main loop
- Each transition does explicit teardown of previous radios before bringing up next
- Log every transition to boot.log with timestamp and reason
- Add `tprintln` of state changes for debug visibility

```cpp
enum RadioMode {
    MODE_BOOT,
    MODE_IDLE,
    MODE_DOCK,
    MODE_RACING,
    MODE_RC_ACTIVE
};
```

**Critical: never run WiFi STA + WiFi AP + BLE-Peripheral + ESP-NOW simultaneously.** The state machine prevents this by design. Validated combinations:
- DOCK: WiFi STA + BLE-C (Calypso) — known working today
- RACING: ESP-NOW + BLE-C — needs validation in Phase B test
- RC_ACTIVE: ESP-NOW + WiFi AP — needs validation in Phase B test

---

## ESP-NOW peer mesh (new)

### Channel and addressing
- Use WiFi channel 1 for ESP-NOW (free in most marinas; configurable in config.txt: `espnow_channel=1`)
- Broadcast address (FF:FF:FF:FF:FF:FF) for all fleet messages — no peer registration needed
- Encryption disabled (closed fleet, no PII)
- ESP-NOW init must happen *after* radio mode transition to RACING/RC_ACTIVE, *not* in setup()

### Message envelope

All ESP-NOW messages share this envelope:
```cpp
struct __attribute__((packed)) MeshHeader {
    uint8_t  magic[2];      // 'S','F' (0x53, 0x46)
    uint8_t  version;       // 1
    uint8_t  msg_type;      // see enum below
    uint16_t seq;           // monotonic per sender
    uint8_t  ttl;           // hops remaining; 0 = no rebroadcast
    uint8_t  reserved;
    uint32_t sender_id;     // hash of boat_id string, stable across reboots
    uint32_t gps_time_ms;   // GPS time of day in ms (rolls over daily)
};
// Total: 16 bytes
```

Message types:
```cpp
enum MeshMsgType {
    MSG_BOAT_STATE   = 0x01,  // boat/mark position broadcast
    MSG_LINE_ENDPOINT = 0x02, // RC unit broadcasts line endpoint
    MSG_RACE_ARMED   = 0x10,  // RC: start time + line + fleet
    MSG_START_LOCKED = 0x11,  // RC: actual start time from horn detect
    MSG_GENERAL_RECALL = 0x12,
    MSG_INDIVIDUAL_RECALL = 0x13,
    MSG_ABANDON = 0x14,
    MSG_SHORTEN_COURSE = 0x15,
    MSG_ACK = 0x20,           // boat acks receipt of RC message
};
```

### MSG_BOAT_STATE payload

For racing_boat, committee_chase, mark:
```cpp
struct __attribute__((packed)) BoatStatePayload {
    int32_t  lat_e7;        // latitude × 10^7
    int32_t  lon_e7;        // longitude × 10^7
    int16_t  sog_cm_s;      // SOG in cm/s (0-3000 = 0-30 m/s)
    int16_t  cog_deg10;     // COG in 0.1° (0-3599)
    int16_t  heading_deg10; // heading from IMU, 0.1°
    int8_t   heel_deg;      // heel angle in degrees, signed
    uint8_t  fix_quality;   // 0=none, 1=GPS, 2=DGPS, 4=RTK fixed, 5=RTK float
    uint8_t  sat_count;
    uint8_t  unit_role;     // for receivers to know who's broadcasting
    uint8_t  reserved[3];
};
// Total: 20 bytes payload + 16 bytes header = 36 bytes
// At 25 boats × 10 Hz = 250 broadcasts/sec × 36 bytes = 9 KB/sec aggregate
// Well within ESP-NOW capacity
```

### MSG_RACE_ARMED payload (RC unit → fleet)
```cpp
struct __attribute__((packed)) RaceArmedPayload {
    char     fleet[8];          // "sonar23\0", "j80\0"
    uint32_t start_time_gps_s;  // start time in GPS seconds-of-week
    int32_t  pin_lat_e7;
    int32_t  pin_lon_e7;
    int32_t  rc_lat_e7;
    int32_t  rc_lon_e7;
    uint8_t  race_num;          // 1-99
    uint8_t  reserved[3];
};
// Total: 36 bytes payload + 16 bytes header = 52 bytes
```

### Mesh discipline rules
- TTL=0 (no rebroadcast) for MSG_BOAT_STATE in RACING mode — direct peer-to-peer, ~120m range with current antenna
- TTL=2 (single rebroadcast) for MSG_BOAT_STATE outside RACING mode (e.g., motoring out)
- TTL=2 for all RC unit messages (MSG_RACE_ARMED etc.) — must reach everyone reliably
- Dedup cache: ring buffer of last 256 `(sender_id, seq)` pairs per receiving device; drop duplicates
- Adaptive broadcast rate per BoatStatePayload (see "Adaptive broadcast rate" below)

### Reception handler
- Register ESP-NOW receive callback that runs in WiFi task context — keep it short, just enqueue
- Main loop processes the queue, parses messages, dispatches by type
- Store peer state in a small in-memory table indexed by sender_id: position, last-seen timestamp, role
- Expire peer state entries after 30s of no updates
- Log all received MSG_BOAT_STATE messages to `mesh.log` on SD (one line per message for post-race analysis)

---

## 10 Hz GNSS reconfiguration

### LG290P (E1)
Add to existing PQTM config sequence in `setupGPS()`:
```cpp
sendPQTM("PQTMCFGFIXRATE,W,100");  // 100ms fix interval = 10Hz
// Verify with: sendPQTM("PQTMCFGFIXRATE,R");
```

Also bump message rates so each message comes once per fix:
```cpp
sendPQTM("PQTMCFGMSGRATE,W,GGA,1");  // already there
sendPQTM("PQTMCFGMSGRATE,W,RMC,1");  // already there
// At 10 Hz fix, "rate 1" = once per fix = 10 Hz output
```

But suppress GSA/GSV at high rates (satellite state doesn't change that fast):
```cpp
sendPQTM("PQTMCFGMSGRATE,W,GSA,10"); // once per 10 fixes = 1 Hz
sendPQTM("PQTMCFGMSGRATE,W,GSV,10"); // once per 10 fixes = 1 Hz
```

### LC29HEA (B1)
Uses PAIR commands instead of PQTM for fix rate:
```cpp
// PAIR050: set position output rate
sendPAIR("050,100");  // 100ms = 10Hz
```
Verify the LC29HEAMD datasheet for the exact PAIR command syntax in `setupGPS()` when `g_hw == HW_B1`.

### Adaptive rate logic

After setting GPS to 10 Hz capability, control actual broadcast rate per state:

```cpp
uint16_t getCurrentBroadcastIntervalMs() {
    if (g_role == ROLE_MARK && g_isStationary) return 10000;  // 0.1 Hz
    if (g_role == ROLE_SPARE) return 60000;                    // 0.017 Hz
    if (g_radio_mode != MODE_RACING) return 1000;              // 1 Hz when not racing

    // In RACING mode, adapt to race phase:
    int32_t time_to_start_ms = g_start_time_gps_ms - g_current_gps_ms;
    if (time_to_start_ms < 30000 && time_to_start_ms > -10000) {
        return 100;  // 10 Hz during start window
    }
    if (g_near_mark) return 200;  // 5 Hz approaching a mark
    return 500;  // 2 Hz general racing
}
```

GPS itself runs at 10 Hz always (during RACING). Only the broadcast rate adapts.

### IMU rate

Change `IMU_INTERVAL_MS` from 1000 to 100. The comment "1 Hz - was 50ms/20Hz overkill" is correct for general logging but wrong for OCS. 10 Hz IMU pairs with 10 Hz GNSS.

Power impact is negligible (BNO085 runs fusion at 400 Hz internally).

---

## OCS state machine

### Per-boat local computation (boats only)

Each racing_boat unit computes its own OCS state:

```cpp
struct OCSState {
    bool armed;                 // race armed (start time + line received)
    bool over_line;             // bow currently past line on course side
    bool was_over_at_start;     // was over when start_time fired
    float distance_to_line_m;   // signed; positive = pre-start side
    float closure_rate_m_s;     // negative = approaching line from pre-start side
    uint32_t over_since_gps_ms; // when did we go over (0 if not)
    uint32_t cleared_at_gps_ms; // when did we return (0 if not)
};
```

Algorithm per tick (called from main loop at GPS update rate):
```
1. If not armed, return.
2. Get current position from GPS.
3. Get current heading from IMU (or GPS COG if SOG > 2 kt and IMU stale).
4. Compute bow position:
     bow_lat = pos_lat + bow_offset_m * cos(heading_rad) / METERS_PER_DEG_LAT
     bow_lon = pos_lon + bow_offset_m * sin(heading_rad) / METERS_PER_DEG_LON(lat)
5. Project bow onto line AB (pin → RC):
     Use signed perpendicular distance from line.
     d = (bow - A) · perp(B - A) / |B - A|
     d > 0: pre-start side (the side away from the course)
     d < 0: course side (OCS if past T+0)
6. Compute closure rate (derivative of d over last 500ms window).
7. Update state machine:
   - t < T_start: tracking only, no OCS flag
   - t in [T_start - 0.5s, T_start + 0.5s] AND d < -hysteresis: over_at_start = true
   - t >= T_start AND d < 0: over_line = true, over_since_gps_ms = current GPS time
   - over_line AND d > +0.5m for >2s: over_line = false, cleared_at_gps_ms = current GPS time
8. Drive local feedback:
   - Red LED solid: over_line == true
   - Red LED blinking: over_line == false but was_over_at_start (i.e., recall pending)
   - Update TFT display per role
```

Hysteresis values (defaults; tunable via config):
- `ocs_threshold_m = 0.5` — must be more than 50cm over to call OCS (accounts for GNSS uncertainty)
- `ocs_clear_threshold_m = 0.5` — must be more than 50cm back to clear
- `ocs_clear_dwell_s = 2.0` — must stay clear for this long

## Class registry CSV schema

Located at `/sd/class_registry.csv` (loaded at boot, refreshed via config sync):

```csv
boat_id,sail_no,class,bow_offset_m,boat_name,team_name,boat_size_ft,skipper_name
USA42,42,sonar23,2.4,Wind Dancer,Boston YC Team A,23,John Smith
USA37,37,sonar23,2.4,,,23,
USA12,12,j80,2.8,Quicksilver,,26,
```

**Required columns** (firmware reads for OCS computation):
- `boat_id` — unique identifier matching device's configured boat_id
- `sail_no` — for RC display
- `class` — class name, links to compass calibration profile
- `bow_offset_m` — distance from GNSS antenna to bow in meters (measured with tape measure)

**Optional columns** (for RC display and post-race reporting):
- `boat_name`
- `team_name`
- `boat_size_ft`
- `skipper_name`

Empty values are allowed for any optional field. The RC unit's web UI shows whatever's available ("USA42 'Wind Dancer' — J. Smith, Boston YC Team A" if fully populated; "USA37" if only required fields).

Class defaults can be defined for `bow_offset_m` per class — boats inherit if not specified per-row. This goes in a separate `class_defaults.csv`:
```csv
class,default_bow_offset_m,class_name
sonar23,2.4,Sonar 23
j80,2.8,J/80
```

Loading order: read `class_defaults.csv` first, then `class_registry.csv` and apply per-row overrides on top of class defaults.

### RC unit aggregation (rc_signal only)

The rc_signal unit computes OCS for every boat from received MSG_BOAT_STATE broadcasts, plus its own line endpoints.

```cpp
struct FleetBoat {
    uint32_t sender_id;
    char     sail_no[8];
    char     class[8];
    float    bow_offset_m;
    int32_t  last_lat_e7;
    int32_t  last_lon_e7;
    float    last_heading;
    float    last_sog;
    uint32_t last_seen_gps_ms;
    bool     ocs;                 // RC's authoritative call
    float    distance_to_line_m;
};
FleetBoat g_fleet[32];  // up to 32 boats (25 + RC + marks + spares)
```

RC unit's OCS algorithm: same math as boat-local, but applied to received BoatStatePayload. RC unit knows the line endpoints directly (it set them). RC unit looks up each sender's bow_offset from a local class registry table loaded from `class_registry.csv` on SD.

When RC unit calls OCS on a boat, it broadcasts MSG_INDIVIDUAL_RECALL with that boat's sail_no. The boat receives this, updates its local override state, drives red LED solid until cleared.

### Disagreement detection

When a boat hears its own sail_no in MSG_INDIVIDUAL_RECALL but its local computation says clean (or vice versa), log to `ocs_disagreement.log`:
```
2026-06-07T14:30:00.4Z USA42 local=clean rc=ocs local_dist=+0.3 rc_dist=-0.4 hdg=215 sog=4.2
```

For post-race analysis. Do not change LED behavior based on local opinion — the RC unit's call always wins.

---

## RC unit web UI (rc_signal only)

### WiFi AP setup

When `g_role == ROLE_RC_SIGNAL` and entering MODE_RC_ACTIVE:

```cpp
WiFi.mode(WIFI_AP);
WiFi.softAP("SF-RC1", "sailframes", 1, 0);  // channel 1, not hidden
// IP: 192.168.4.1 (default)
```

SSID format: `SF-RC<boat_id_short>` (e.g., `SF-RC-USA1`).
Password: `wind` (default, locked in firmware constant `RC_AP_DEFAULT_PASSWORD`). Override via config.txt field `rc_ap_password=` if club needs a different one.

ESP-NOW + WiFi AP coexistence: both run on channel 1 (forced). Already documented to work.

### HTTP server

Use Arduino `WebServer.h` (synchronous, simple). NOT ESPAsyncWebServer (more deps, more bugs).

Route handlers:
```
GET  /                  → serves main HTML page (single-file SPA)
GET  /api/status        → JSON: current race state, RC unit health
GET  /api/fleet         → JSON: array of all known boats and their OCS state
GET  /api/race          → JSON: current race config (armed, line endpoints, start time)
POST /api/race/setup    → set up next race (start time, sequence)
POST /api/race/arm      → arm race (begins horn sequence detection)
POST /api/race/start    → manual start override (if horn detection missed)
POST /api/race/recall   → general recall
POST /api/race/recall_individual → with boat list
POST /api/race/abandon  → abandon race
POST /api/race/shorten  → shorten course
POST /api/line/refresh  → re-broadcast current pin+rc positions as line endpoints
GET  /api/ws            → WebSocket for live updates (1 Hz push of /api/fleet)
```

JSON shape examples:

`GET /api/status`:
```json
{
  "version": "2026.06.07.01",
  "unit_id": "USA1",
  "role": "rc_signal",
  "gps_fix": "rtk_float",
  "sats": 14,
  "battery_pct": 87,
  "uptime_s": 3421,
  "espnow_peers": 24,
  "wifi_ap_clients": 1,
  "horn_detection": "armed"
}
```

`GET /api/fleet`:
```json
{
  "race_armed": true,
  "race_num": 3,
  "start_time_iso": "2026-06-07T14:30:00Z",
  "time_to_start_s": -8,
  "line": { "pin_lat": 42.3601, "pin_lon": -71.0589, "rc_lat": 42.3604, "rc_lon": -71.0578, "length_m": 87.3, "bias_deg": -3.0 },
  "boats": [
    { "sail_no": "USA37", "ocs": true, "distance_m": -1.4, "closure_m_s": 0.8, "speed_kt": 5.2 },
    { "sail_no": "USA12", "ocs": true, "distance_m": -0.8, "closure_m_s": 0.2, "speed_kt": 4.8 },
    { "sail_no": "USA21", "ocs": false, "distance_m": 0.4, "closure_m_s": -1.2, "speed_kt": 5.5 }
  ]
}
```

### HTML/CSS/JS payload

Single-file SPA embedded in firmware via `PROGMEM`. Aim for <20 KB of HTML+CSS+JS.

Layout: the OCS view design from earlier conversation:
- Top half: OCS section, red background tint when any boats over
- Middle: line bar with PIN/RC labels and bias indicator
- Bottom half: approaching section + further-back summary
- Status strip: countdown, wind, line bias
- Bottom controls: race setup, recall, abandon buttons

WebSocket from `/api/ws` pushes fleet state at 1 Hz. Client renders incrementally.

Use vanilla JS, no framework. Tailwind not needed for this scope — inline styles in `<style>` tag are fine.

### Two views: race setup, live monitor

`/` shows live monitor by default. A "Setup" button toggles to the race-setup form. After "Start Sequence" is pressed, view auto-switches to live monitor.

---

## Horn detection — comparator-based sound sensor

**Hardware:** KY-038 / LM393 sound detection module (or equivalent). ~$2 per unit.

This replaces the deferred I2S microphone approach. The KY-038 is a small board with an electret mic + LM393 threshold comparator + adjustable trimpot. It outputs a single digital line that goes HIGH when sound exceeds the threshold. Fits B1's pin budget perfectly via the J_AUX header.

### Why not I2S microphone

For horn detection we don't need audio fidelity, only a binary "loud sound detected" signal. The I2S approach (INMP441) requires three GPIOs (BCK output, WS output, SD input) with output-capable pins, which B1 doesn't have free after Hall sensor takes GPIO19. The comparator approach needs one input-only pin, which B1 has at GPIO36 via the J_AUX header.

I2S also costs continuous CPU/DMA load processing the audio stream plus ~32 KB of audio buffer RAM. The comparator costs zero CPU when idle and ~10 µs per trigger event.

### Wiring on B1 (RC unit only)

```
KY-038 board       J_AUX pin       B1 pin
────────────       ─────────       ──────
VCC (3.3V)    →    Pin 1 (3V3)     -
GND           →    Pin 2 (GND)     -
DOUT          →    Pin 5 (AUX_INT) GPIO36 (input-only, ADC1_CH0, perfect)
AOUT          →    not connected   (optional: could route to a second ADC pin for analog level monitoring; not needed for v2.0.0)
```

3 wires. No additional B1 PCB changes needed — uses the planned J_AUX header.

### Mechanical installation

The KY-038 mounts inside the B1 enclosure. No acoustic vent or external mount — the polycarbonate lid is sufficient acoustic path given the high horn signal level.

**Acoustic budget at <2 meters:**
- Marine air horn at 1m: ~110-120 dB SPL
- At 2m (typical signal-boat sensor placement): ~104-114 dB SPL (6 dB drop per doubling)
- Polycarbonate lid attenuation (3mm clear PC): ~10-15 dB at horn frequencies (400-1500 Hz)
- Sound reaching KY-038 microphone: ~89-104 dB SPL

This is loud — well above the LM393 comparator's detection threshold and 30-40 dB above ambient marine noise (wind, water lapping, radio chatter at ~50-70 dB SPL). The signal-to-noise ratio is excellent without any acoustic port.

**Internal mounting:**
- Mount KY-038 PCB on standoffs or hot-glue to the inside of the B1 lid, positioning the microphone element 1-2 mm from the polycarbonate surface
- Microphone faces toward the lid (outward-facing direction)
- Mount **opposite** the Hall sensor side to avoid magnetic interference (Hall on right wall = mount mic on left/top of lid)
- Keep ≥30mm from the LiPo battery and Qi receiver coil

**Threshold tuning:**
- Set the trimpot during install with the signal boat docked
- Fire the horn at intended deployment position (~1.5-2m from B1)
- Adjust trimpot so the LED triggers cleanly on horn but not on close shouting, hand-claps, or distant horns
- The 30-40 dB margin gives plenty of latitude

**Why no acoustic vent:**
- Sealed polycarbonate path is adequate for binary detection at this SPL
- Avoids drilling any holes in B1 enclosure (preserves IP68 integrity)
- Eliminates Gore vent BOM cost (~$5/unit) and assembly step
- Eliminates risk of vent membrane failure over years of UV exposure

### Firmware implementation

```cpp
// New file: horn_detect.h
#ifndef HORN_DETECT_H
#define HORN_DETECT_H

#define HORN_MIC_PIN 36  // GPIO36, via J_AUX pin 5
#define HORN_DEBOUNCE_MS 200  // ignore repeat triggers within this window

extern volatile uint32_t g_lastHornTriggerGPSMs;
extern volatile bool g_hornTriggerFlag;

void IRAM_ATTR hornISR();
void hornDetectSetup();      // called only on rc_signal role
void processHornDetection(); // called from main loop

#endif
```

```cpp
// horn_detect.cpp (or include in main .ino)

volatile uint32_t g_lastHornTriggerGPSMs = 0;
volatile uint32_t g_lastHornEdgeMs = 0;
volatile bool g_hornTriggerFlag = false;

void IRAM_ATTR hornISR() {
    uint32_t now = millis();
    // Debounce: ignore edges within 200ms of last
    if (now - g_lastHornEdgeMs < HORN_DEBOUNCE_MS) return;
    g_lastHornEdgeMs = now;
    g_lastHornTriggerGPSMs = getCurrentGPSTimeMs();  // single fast read
    g_hornTriggerFlag = true;
}

void hornDetectSetup() {
    pinMode(HORN_MIC_PIN, INPUT);
    attachInterrupt(digitalPinToInterrupt(HORN_MIC_PIN), hornISR, RISING);
    tprintln("[HORN] Detection armed on GPIO36");
}

void processHornDetection() {
    if (!g_hornTriggerFlag) return;
    g_hornTriggerFlag = false;
    
    uint32_t triggerTime = g_lastHornTriggerGPSMs;
    
    if (!g_race_armed) {
        tprintf("[HORN] Trigger ignored (race not armed): GPS %u\n", triggerTime);
        return;
    }
    
    uint32_t plannedStart = g_planned_start_time_gps_ms;
    int32_t deltaToStart = (int32_t)(triggerTime - plannedStart);
    
    // Check for start horn (T+0 ± 2 sec)
    if (abs(deltaToStart) < 2000) {
        if (!g_start_locked) {
            g_actual_start_time_gps_ms = triggerTime;
            g_start_locked = true;
            broadcastMessage(MSG_START_LOCKED, &g_actual_start_time_gps_ms);
            tprintf("[HORN] START LOCKED at GPS %u (delta %+d ms from planned)\n",
                    triggerTime, deltaToStart);
        }
        return;
    }
    
    // Check for intermediate horns (T-5, T-4, T-1) — for confidence tracking
    StartSequence* seq = lookupSequence(g_sequence_mode);
    if (seq) {
        for (int i = 0; i < seq->step_count; i++) {
            uint32_t stepTime = plannedStart - (seq->steps[i].t_minus_s * 1000);
            int32_t deltaToStep = (int32_t)(triggerTime - stepTime);
            if (abs(deltaToStep) < 2000) {
                g_horn_sequence_hits[i] = true;
                tprintf("[HORN] Step %d (%s) detected at GPS %u (delta %+d ms)\n",
                        i, seq->steps[i].label, triggerTime, deltaToStep);
                return;
            }
        }
    }
    
    // Outside any expected window — log as spurious
    tprintf("[HORN] Spurious trigger at GPS %u (no matching window)\n", triggerTime);
}
```

### False positive mitigations

Three layers, all enabled by default:

1. **Time-window gating.** Trigger is only accepted as a horn if it falls within ±2 seconds of an expected sequence step time. Outside windows, log as spurious and ignore. Most random sounds happen outside the ~4-second total window per race.

2. **Sequence confidence tracking.** Track which sequence steps had detected horns. A full sequence (4 hits for mode 30) is high-confidence; fewer hits is lower-confidence but still usable. Log to `race_summary.csv` for post-race review.

3. **Hardware threshold tuning.** The KY-038 trimpot is set at install time so the sensor triggers reliably on the start horn (right next to the mic on the signal boat) but not on horns from other boats 100m+ away. Acoustic energy drops ~6 dB per doubling of distance, giving a 20-30 dB margin between own horn and distant horns.

### Auto-fallback if no horn detected

If the planned start time arrives and no horn was detected within the ±2s window:

```cpp
// In main loop on RC unit:
if (g_race_armed && !g_start_locked) {
    uint32_t now = getCurrentGPSTimeMs();
    if (now >= g_planned_start_time_gps_ms + 2000) {
        // 2 seconds past planned start, no horn detected — fall back
        g_actual_start_time_gps_ms = g_planned_start_time_gps_ms;
        g_start_locked = true;
        broadcastMessage(MSG_START_LOCKED, &g_actual_start_time_gps_ms);
        tprintln("[HORN] No detection in window — fell back to planned start time");
    }
}
```

This guarantees a MSG_START_LOCKED broadcast goes out within 2 seconds of the planned start no matter what.

### Manual override (RC web UI)

The race-setup page still has a "Manual START" button for PROs who want to force a lock independent of the horn (e.g., horn malfunction). Sends `POST /api/race/start` which sets `g_actual_start_time_gps_ms = getCurrentGPSTimeMs()` and broadcasts.

The three paths (horn detection, auto-fallback, manual button) are functionally equivalent — whichever fires first wins. Boats receive one MSG_START_LOCKED per race.

### Telnet commands

```
horn          - show current state: armed, last trigger time, sequence hits
horn test     - simulate a horn trigger now (for bench testing)
horn threshold - print recommended trimpot adjustment guidance
```

### Hardware acceptance test

Before deploying an RC unit:
1. Power up B1 in RC mode
2. Tap the KY-038 mic firmly — should see DOUT go high momentarily, logged via `horn` telnet command
3. Run `horn test` to simulate a trigger and verify MSG_START_LOCKED broadcasts
4. Set up a virtual race in telnet: `race arm <iso_time>` for 1 minute future
5. At T+0 fire an actual horn or air horn near the mic — verify start locks
6. Adjust trimpot if false-triggering on background sounds, or if not triggering on horn

### Pin verification

Stage 1 of implementation must verify GPIO36 is not used elsewhere in the firmware:
- 1PPS is on GPIO39 (SVN), not GPIO36 (SVP) — confirmed in pin map
- ADC2 pins are claimed by WiFi when active — GPIO36 is ADC1, safe
- No conflicts found

### v2.1+ upgrade path

If false-positive rate proves problematic in real deployment, upgrade options without changing the hardware-level approach:

- **Replace KY-038 with a better-tuned analog input + comparator.** Custom small board with adjustable hysteresis and software-readable analog level (via second ADC pin) for confidence checking.
- **Add an I2S microphone in B1 v1.5 hardware** (if pin budget can be freed by then). Run both in parallel; cross-reference triggers. Use I2S for frequency-domain confidence check after a comparator trigger.
- **Add a second cheap ESP32-C3 module dedicated to audio processing**, talking to main B1 over I²C. Total system cost increases by ~$3 per RC unit but lets you do sophisticated signal processing without taxing the main board.

---

## Start sequence modes (Balboa Race Management list)

The race-setup UI lets the PRO choose a start sequence mode. Reference: https://www.balboaracing.com/sequence_list.htm

### Modes supported in v2.0.0

**Tier 1 (always available in UI):**
- **Mode 30**: ISAF Rule 26 (5-4-1-0) — DEFAULT
  - T-5:00 long horn, class flag up (warning)
  - T-4:00 long horn, prep flag up (preparatory)
  - T-1:00 long horn, prep flag down
  - T-0:00 long horn, class flag down (start)
- **Mode 27**: Short (3-2-1-0)
  - T-3:00 long horn, class flag up
  - T-2:00 long horn, prep flag up
  - T-1:00 long horn, prep flag down
  - T-0:00 long horn, class flag down

**Tier 2 (in UI but less common):**
- **Mode 32**: Keelboat (6-5-1-0)
- **Mode 60**: Olympic (10-5-4-1-0)

**Tier 3 (deferred to v2.1+):**
- Multi-fleet sequenced starts (mode 90+)
- Match racing 4-minute Rule 26
- Custom user-defined sequences

### Sequence data structure

In-firmware lookup table (defined in `sequences.h`):
```cpp
struct SequenceStep {
    uint16_t t_minus_s;     // seconds before start
    const char* action;      // "class_flag_up", "prep_flag_up", etc.
    const char* audio;       // "long_horn", "short_horn", "none"
    const char* label;       // displayed on RC unit and boats
};

struct StartSequence {
    uint8_t mode;
    const char* name;
    SequenceStep steps[8];
    uint8_t step_count;
};

const StartSequence SEQUENCES[] = {
    {30, "ISAF Rule 26 (5-4-1-0)", {
        {300, "class_flag_up", "long_horn", "Warning"},
        {240, "prep_flag_up", "long_horn", "Preparatory"},
        {60, "prep_flag_down", "long_horn", "One Minute"},
        {0, "class_flag_down", "long_horn", "Start"}
    }, 4},
    {27, "Short (3-2-1-0)", {
        {180, "class_flag_up", "long_horn", "Warning"},
        {120, "prep_flag_up", "long_horn", "Preparatory"},
        {60, "prep_flag_down", "long_horn", "One Minute"},
        {0, "class_flag_down", "long_horn", "Start"}
    }, 4},
    {32, "Keelboat (6-5-1-0)", {
        {360, "class_flag_up", "long_horn", "Warning"},
        {300, "prep_flag_up", "long_horn", "Preparatory"},
        {60, "prep_flag_down", "long_horn", "One Minute"},
        {0, "class_flag_down", "long_horn", "Start"}
    }, 4},
    {60, "Olympic (10-5-4-1-0)", {
        {600, "class_flag_up", "long_horn", "Warning"},
        {300, "prep_flag_up", "long_horn", "Preparatory"},
        {240, "another_signal", "long_horn", "Four Minute"},
        {60, "prep_flag_down", "long_horn", "One Minute"},
        {0, "class_flag_down", "long_horn", "Start"}
    }, 5},
};
```

### MSG_RACE_ARMED payload — revised to include sequence_mode

```cpp
struct __attribute__((packed)) RaceArmedPayload {
    char     fleet[8];          // "sonar23\0"
    uint32_t start_time_gps_s;  // start time in GPS seconds-of-week
    int32_t  pin_lat_e7;
    int32_t  pin_lon_e7;
    int32_t  rc_lat_e7;
    int32_t  rc_lon_e7;
    uint8_t  race_num;          // 1-99
    uint8_t  sequence_mode;     // 30, 27, 32, 60, etc.
    uint8_t  reserved[2];
};
// Total: 36 bytes payload + 16 bytes header = 52 bytes
```

**This supersedes the earlier RaceArmedPayload definition.** Update Stage 5 work to use this shape.

### UI rendering

RC unit web UI shows current sequence step prominently. Boat units render countdown on their TFT during the sequence:

```
┌────────────────────────────┐
│  Race 3 — Sonar 23         │
│                            │
│       T-04:23              │
│                            │
│   Preparatory              │
│   Class flag and P up      │
│                            │
│   Next: T-1:00             │
│   Prep flag down           │
└────────────────────────────┘
```

For v2.0.0, render as text only (no flag graphics). Flag graphics are nice-to-have for v2.1.

### Audio signals

The RC unit web UI displays a visual indicator at each step's time: a color flash on the screen plus text "FIRE HORN". The PRO fires the actual horn manually based on this cue. No audio output from firmware.

### Race-setup UI integration

The race-setup page dropdown lists the sequence modes:

```
Start Sequence
┌──────────────────────────────────────────┐
│ ● Mode 30: Rule 26 (5-4-1-0)  [default] │
│ ○ Mode 27: Short (3-2-1-0)              │
│ ○ Mode 32: Keelboat (6-5-1-0)           │
│ ○ Mode 60: Olympic (10-5-4-1-0)         │
└──────────────────────────────────────────┘
```

Selected mode is stored in the race-setup state, broadcast in MSG_RACE_ARMED, and used by the RC unit to schedule its own visual horn cues during the countdown.

---

## Cloud config sync (new — parallel to existing OTA pull)

Modeled on `performOTAUpdate()`. New function `performConfigSync()`.

### Endpoint pattern
```
http://sailframes-fleet-data-prod.s3.us-east-1.amazonaws.com/config/<boat_id>/latest.json
http://sailframes-fleet-data-prod.s3.us-east-1.amazonaws.com/config/<boat_id>/latest.sha256
```

(Plain HTTP — same TLS workaround as OTA.)

### Sync schedule
- Once per dock cycle, after successful upload, before OTA check
- Throttled to once per 60 seconds even if multiple events would trigger it
- One-shot per boot (set `g_configCheckedThisBoot` after first attempt)

### JSON shape served from S3
```json
{
  "version": 7,
  "boat_id": "USA42",
  "sail_no": "42",
  "class": "sonar23",
  "bow_offset_m": 2.4,
  "unit_role": "racing_boat",
  "wifi_ssids": [
    {"ssid": "BostonYC-Dock", "psk": "..."},
    {"ssid": "SailFrames-Field", "psk": "..."}
  ],
  "espnow_channel": 1,
  "feature_flags": {
    "ocs_enabled": true,
    "horn_detection": false,
    "mesh_rebroadcast": true,
    "10hz_gnss": true
  },
  "class_profile_url": "http://.../class-profiles/sonar23.json",
  "applied_at_iso": null
}
```

### Application logic
- Download JSON
- Verify SHA256 against `latest.sha256`
- Compare `version` to locally stored `g_config_version`
- If newer:
  - Parse and validate schema (reject if missing required fields)
  - Update local `config.txt` with new values
  - Set `g_config_version = new_version`
  - For non-structural fields (feature flags, thresholds): apply live
  - For structural fields (unit_role, boat_id, class): schedule reboot in 5 seconds
  - Log to boot.log: "config sync: applied version N"

### Rollback
- Before applying new config, save current config to `config.bak`
- If device fails to boot 3 times within 60s (existing watchdog pattern), restore `config.bak`

### Class profile pull (separate)
Class profile contains per-class compass calibration:
```json
{
  "class": "sonar23",
  "heading_offset_deg": 1.4,
  "heading_scale_sin": 0.3,
  "heading_scale_cos": -0.2,
  "valid_within_deg": 2.5,
  "calibrated_date": "2026-06-05"
}
```
Cached to SD as `class_profile.json`. Applied as software offset to BNO085 heading at runtime.

---

## Status snapshot upload (new)

After every successful upload cycle, also upload one small JSON blob to:
```
http://sailframes-fleet-data-prod.s3.us-east-1.amazonaws.com/status/<boat_id>/latest.json
```

Contents:
```json
{
  "version": "2026.06.07.01",
  "boat_id": "USA42",
  "ts_iso": "2026-06-07T18:42:14Z",
  "gps_fix": "rtk_float",
  "sats": 14,
  "last_position": { "lat": 42.3601, "lon": -71.0589 },
  "battery_pct": 67,
  "battery_v": 3.94,
  "uptime_s": 14523,
  "free_heap_kb": 142,
  "sd_free_mb": 4096,
  "espnow_peers_last_race": 24,
  "config_version": 7,
  "last_race_id": "2026-06-07-R3",
  "errors_24h": []
}
```

This gives the cloud admin UI a fleet-wide health view without touching individual devices.

---

## New telnet commands

Extend existing command interpreter:

```
role                  - show current unit_role
role <name>           - set unit_role (writes config.txt, reboots)
mesh                  - show current mesh state (peers, last broadcasts)
ocs                   - show current OCS state (boat-local)
fleet                 - rc_signal only: show RC's view of all boats
race                  - show current race state (armed, time-to-start, line)
race arm <iso_time>   - rc_signal only: arm next race with start time
race recall           - rc_signal only: general recall
race abandon          - rc_signal only: abandon current race
hwid                  - print detected hardware platform (E1 or B1)
configver             - print current config version
configsync            - force config sync now
flags                 - print feature flag state
flag <name> on|off    - toggle feature flag at runtime (persisted to config.txt)
ws_clients            - rc_signal only: print connected WebSocket clients
```

Use existing `tprintln`/`tprintf` for output.

---

## Implementation order for Claude Code

Don't try to ship all of this in one PR. Stage it across feature branches that all merge into a `v2.0.0` integration branch. Each stage should compile and pass on bench before next stage starts.

### Stage 1: Foundation (no behavior change yet)
**Branch: `feature/v2-foundation`**

1. Add hardware platform detection (HW_E1 / HW_B1) from config.txt
2. Add unit role enum and config loading
3. Add radio mode state machine skeleton (just transitions, no new functionality)
4. Bump `IMU_INTERVAL_MS` to 100 and verify BNO085 still works at 10 Hz
5. Add `PQTMCFGFIXRATE,W,100` for E1 GPS (10 Hz fix rate)
6. Update version string to `2026.06.xx.01`
7. Add new telnet commands: `role`, `hwid`, `configver`

Verify: compiles, boots, GPS reports 10 Hz fixes, IMU at 10 Hz, telnet commands work. Existing functionality (Calypso, OTA, upload) unaffected.

### Stage 2: ESP-NOW mesh
**Branch: `feature/v2-espnow`** (depends on Stage 1)

1. Add ESP-NOW init/teardown in radio mode transitions
2. Implement MeshHeader + MSG_BOAT_STATE serialization
3. Add broadcast logic on all roles except SPARE
4. Add reception handler + dedup cache + peer state table
5. Add adaptive broadcast rate logic
6. Add `mesh` telnet command
7. Log received MSG_BOAT_STATE to `mesh.log`

Verify on bench: two E1 devices broadcasting, both seeing each other in peer table. Walk-around test to confirm ~120m range with default antennas.

### Stage 3: Cloud config sync + status snapshots
**Branch: `feature/v2-cloud-config`** (depends on Stage 1)

1. Implement `performConfigSync()` modeled on `performOTAUpdate()`
2. Add config version tracking
3. Add class profile pull and cache
4. Add status snapshot upload after each upload cycle
5. Add `configsync`, `flags`, `flag` telnet commands

Verify: device pulls config from S3 on dock cycle, applies changes, falls back gracefully if config is malformed.

### Stage 4: OCS state machine (boat-local)
**Branch: `feature/v2-ocs-boat`** (depends on Stage 1, Stage 2)

1. Implement OCSState struct and tick function
2. Wire OCS computation into main loop at GPS update rate
3. Add MSG_RACE_ARMED, MSG_START_LOCKED reception
4. Add LED feedback for local OCS state
5. Add `ocs`, `race` telnet commands

Verify on bench: simulate a "race armed" message via telnet command, walk past a virtual line, observe OCS state transitions in log.

### Stage 5: RC unit aggregation
**Branch: `feature/v2-rc-unit`** (depends on Stage 2, Stage 4)

1. Add FleetBoat table
2. Aggregate received MSG_BOAT_STATE into fleet view
3. Compute fleet-wide OCS from RC's view
4. Implement MSG_INDIVIDUAL_RECALL broadcasting
5. Add disagreement logging
6. Add `fleet` telnet command

Verify on bench: two boat units + one RC unit, RC sees both boats' positions, computes OCS for each.

### Stage 6: RC unit WiFi AP + HTTP server
**Branch: `feature/v2-rc-webui`** (depends on Stage 5)

1. WiFi AP setup in radio mode transition to RC_ACTIVE
2. WebServer.h routes for `/api/*`
3. Embedded HTML/CSS/JS SPA in PROGMEM
4. WebSocket for live fleet push
5. Race setup and control endpoints
6. Add `ws_clients` telnet command

Verify on bench: connect iPad/laptop to RC unit's WiFi AP, browse to 192.168.4.1, see fleet state update live.

### Stage 7: Start sequence modes + horn detection
**Branch: `feature/v2-sequences-horn`** (depends on Stage 6)

1. Define `sequences.h` with the StartSequence struct and the lookup table
2. Add `sequence_mode` to RaceArmedPayload (revised from earlier spec)
3. Implement countdown rendering on boat TFT (text-based)
4. Implement RC web UI: sequence dropdown in race-setup page
5. Implement visual horn cue in RC UI (color flash + "FIRE HORN" text at each step's time)
6. Implement KY-038 horn detection (`horn_detect.h/cpp`) — ISR-driven, time-window gated
7. Sequence confidence tracking (`g_horn_sequence_hits`)
8. Auto-fallback path: lock to planned time if no horn detected within 2s of planned start
9. Manual START button on RC UI as third path (`POST /api/race/start`)
10. Add telnet commands: `horn`, `horn test`, `race start_now` (manual override testing)

Verify on bench:
- Arm a race with mode 30
- Watch RC unit cue each step at the correct time
- Tap KY-038 mic at expected horn times — verify sequence hits accumulate
- Verify start locks via horn detection if horn fires at T+0
- Disconnect KY-038 and verify auto-fallback fires 2s after planned start
- Use manual button — verify it locks immediately regardless of timing

Verify in the field:
- Install KY-038 on signal boat with chosen acoustic vent / external mount
- Tune trimpot during a practice session
- Run a club race and confirm start time locks correctly to actual horn fire

### Stage 8: Integration testing + canary deployment
**Branch: `v2.0.0-integration`**

1. Merge all feature branches
2. Build and SHA256
3. Upload to S3 as `firmware/USA42/latest.json` only (canary on Paul's boat)
4. Run a club race with v2.0.0-beta on one boat, watch logs
5. Iterate on bugs found in field

---

## Things to validate during integration testing

1. **Radio mode transitions don't deadlock.** Each transition must complete in <2s. Add timing instrumentation.
2. **Mesh load stays under capacity at 25 boats × 10 Hz.** Use bench simulation with multiple ESP32s.
3. **OCS calls are consistent between boat-local and RC-central.** Disagreement rate should be <1% during normal racing.
4. **Config sync doesn't brick devices.** Test rollback path by pushing intentionally-broken config to a test device.
5. **WiFi AP + ESP-NOW coexistence at RC unit.** Measure ESP-NOW packet loss with 0/1/2/4 WebSocket clients connected.
6. **Horn detection false positive rate.** Run RC unit on dock at marina; should not falsely detect club horns, tugs, etc.
7. **Memory: free heap remains >100 KB at all times.** ESP32 has 320 KB total; budget carefully.
8. **Watchdog never trips.** All long operations broken into yieldable chunks.

---

## What's explicitly NOT in v2.0.0

To bound scope:
- No iPhone/Android native app (deferred)
- No on-device debug webpage for non-RC roles (use telnet)
- No BLE peripheral for config (deferred — config is cloud-managed)
- No PPK OCS audit (server-side, separate rollout)
- No second-board RM3100 magnetometer (B1 v1.5 work, after fleet stable)
- No ESP-NOW LR mode (Arduino limitation; only if standard mode proves inadequate)
- No B1-specific Hall-toggle or Qi-charging firmware (separate work when B1 fab returns)

---

## Coordination notes for Claude Code

- Use `view` on `/mnt/user-data/uploads/sailframes_e1.ino` before any edit to confirm current line numbers
- Use `str_replace` for targeted edits; do not rewrite whole sections
- After each stage, build with `arduino-cli compile --fqbn esp32:esp32:esp32 sailframes_e1.ino --build-property "build.partitions=min_spiffs"` and verify it links
- Run `shasum -a 256` on the resulting .bin and update the manifest before promoting to S3
- New files: create as separate `.h` headers (e.g., `mesh.h`, `ocs.h`, `rc_unit.h`, `mic.h`) included from main `.ino`. Keep .ino as the orchestrator, not the implementation.
- All new code must respect the dual-core split: WiFi/OTA/telnet stays on Core 1, uploads stay on Core 0. ESP-NOW callbacks run in WiFi task (managed by the SDK). HTTP server (RC unit) runs on Core 1 alongside telnet (mutually exclusive via radio mode state machine).
- Don't introduce new pinned library versions. NimBLE-Arduino 2.4.0, ArduinoJson, TFT_eSPI, BNO085_100k stay as-is.
- For HTTP server, use Arduino built-in `WebServer.h`, NOT ESPAsyncWebServer (avoid new dependency).
- For WebSocket, use built-in `WebServer.h`'s WebSocket support OR write a minimal frame-by-frame WebSocket handler. Don't pull in WebSockets_Generic library.

---

## Open questions for Paul to resolve before Stage 1 starts

**Resolved (locked):**
- ✓ Class registry CSV schema: `boat_id,sail_no,class,bow_offset_m,boat_name,team_name,boat_size_ft,skipper_name` (last 4 optional)
- ✓ Default WiFi AP password for RC units: `wind`
- ✓ ESP-NOW channel: 1 default, configurable via `espnow_channel=` in config.txt
- ✓ Bow offset measurement: tape measure, recorded in class_registry.csv per boat
- ✓ Microphone deferred: replaced with manual START button + auto-fallback
- ✓ Start sequence modes: Balboa list, modes 30/27/32/60 in v2.0.0, mode 30 default

**Still open (not blocking Stage 1):**
- PSK rotation fallback strategy: if dock WiFi password changes and a device misses the config sync, how does it recover? Options: keep a factory-default SSID baked in firmware that always works, OR allow USB/serial config reset. Decide before fleet password ever rotates.
- Service UUID for future BLE peripheral: generate when needed, not now.
- Mark unit role behavior: does a mark device record any data, or just broadcast position? Decide before deploying first autonomous mark (later than v2.0.0 in any case).
