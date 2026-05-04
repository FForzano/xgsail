# S1 (Raspberry Pi) — Legacy Documentation

**Status: legacy / shelved.** S1 was an early attempt at a single-boat
"analysis" device on Raspberry Pi 5. The fleet-wide system that ships and
races is the ESP32-based **E1** (×6 deployed). This file preserves S1
hardware/software notes for reference and in case the camera/CV ideas get
revisited later. Day-to-day project documentation lives in `CLAUDE.md` at
the repo root and focuses on E1.

---

## S1 Hardware Stack (Raspberry Pi Analysis Boat)

| Component | Part | Interface | Notes |
|---|---|---|---|
| SBC | Raspberry Pi 5 | — | Primary compute |
| GPS | u-blox ZED-F9P | USB (CH340 serial) | Dual-band L1+L5, PPK-capable, 10Hz nav rate |
| IMU | GY-BNO08X (BNO085) | I2C @ 0x4A | 9DOF AHRS, 400kHz I2C required |
| Wind | Calypso Ultrasonic Portable Mini | BLE 5.1 | Wireless only, open-source protocol, 1Hz, IPX8 |
| Pressure | Adafruit DPS310 | I2C @ 0x77 (STEMMA QT) | Needs Gore-Tex vent in sealed enclosure |
| Camera | Pi Camera 3 Wide (IMX708) | CSI (22-pin MIPI) | Requires Pi 5 adapter cable |
| Display | Newhaven NHD-5.0-HDMI-N-RSXP | HDMI | 1100-nit sunlight-readable, 800×480, 5V/560mA |
| Power | 50,000mAh USB-C power bank | USB-C | Replaced PiSugar 3 Plus (pogo-pin vibration issues) |
| Storage (boot) | SanDisk Extreme 128GB microSD (A2) | — | Near-read-only boot volume |
| Storage (data) | Foresee XP1000F 128GB NVMe | M.2 2280 M-key | In Lemorele slim NVMe enclosure, mounted at `/data` |
| Enclosure | QILIPSU IP67 | — | Daily install/remove, no permanent boat modifications |

**Future / Considering (never implemented):**
- OAK-D Pro Wide — 3D sail shape analysis (adds ~2-4W power draw)

### S1 I2C Address Map

| Device | Address | Status |
|---|---|---|
| BNO085 IMU | 0x4A | Active |
| DPS310 Pressure | 0x77 | Active |

PiSugar battery hat (0x57, 0x68) removed due to vibration issues.
1602 LCD (0x27) replaced by Newhaven HDMI display.

```bash
sudo i2cdetect -y 1
# Expected: 0x4a, 0x77
```

The SparkFun ZED-F9P board has a rechargeable backup battery → warm-start
GPS fix in 1-5 seconds. Combined with chrony GPS time sync, the Pi clock
syncs within seconds of boot. No DS3231 RTC needed.

---

## S1 OS & Software Environment

- **OS:** Raspberry Pi OS Bookworm (64-bit)
- **Python:** 3.11+, async preferred
- **Config file:** `/boot/firmware/config.txt` (Bookworm location)
- **Camera stack:** `rpicam-*` commands (libcamera is deprecated on Bookworm)
- **Storage:** All writes directed to NVMe `/data` mount; SD card as near-read-only boot volume

### Required I2C config (`/boot/firmware/config.txt`)
```ini
dtparam=i2c_arm=on
dtparam=i2c_arm_baudrate=400000   # Required for BNO085 clock stretching fix
```

### Key Python Libraries
```bash
pip install adafruit-circuitpython-bno08x --break-system-packages
pip install adafruit-circuitpython-dps310 --break-system-packages
pip install bleak              # BLE for Calypso wind sensor
pip install pyserial           # ZED-F9P UART fallback
```

### GPS Time Sync (chrony + gpsd)

The system uses GPS time to keep the clock accurate while offline (on the water).

`/etc/chrony/conf.d/gps.conf`:
```ini
refclock SHM 0 refid GPS precision 1e-1 offset 0.0 delay 0.2 poll 3 trust
makestep 1 -1   # Allow large time corrections (important after power loss)
local stratum 10
```

```bash
chronyc sources    # Shows GPS as #* or #+ when active
chronyc tracking
gpspipe -w -n 3
```

- Online: NTP servers (more accurate)
- Offline: GPS fallback (~50ms accuracy via NMEA)
- Wrong-clock boot: auto-corrects from GPS within seconds

### Persistent Journald

`/etc/systemd/journald.conf.d/sailframes.conf`:
```ini
[Journal]
Storage=persistent
Compress=yes
SystemMaxUse=500M
SystemKeepFree=100M
MaxRetentionSec=2week
MaxFileSec=1day
MaxLevelStore=debug
SyncIntervalSec=1m
```

Post-sail debugging:
```bash
journalctl --list-boots
journalctl -b -1
journalctl -b -1 -p warning
journalctl --since "2026-03-24 13:00" -u "sailframes*"
journalctl -b -1 -k | grep -iE "usb|power|voltage|under"
```

---

## S1 Sensor Wiring

### BNO085 (GY-BNO08X breakout)
```
VCC → 3.3V       SCL → SCL1 (GPIO3, Pin 5)
GND → GND        SDA → SDA1 (GPIO2, Pin 3)
ADO → unconnected (I2C addr 0x4A)
CS  → unconnected (I2C mode)
```

### DPS310 (Adafruit breakout)
```
VIN → 3.3V       SCL → SCL1 (shared bus)
GND → GND        SDA → SDA1 (shared bus)
SDO → unconnected (addr 0x77)
```
STEMMA QT cable: Black=GND, Red=3.3V, Blue=SDA, Yellow=SCL.

### ZED-F9P GPS
- Preferred: USB → Pi 5 USB → `/dev/ttyACM0` or `/dev/sailframes-gps`
- Fallback UART: TX→GPIO15(RX), RX→GPIO14(TX)
- USB auto-detection: GPS service scans `/dev/ttyACM*` and `/dev/ttyUSB*`

Udev (`/etc/udev/rules.d/99-sailframes-gps.rules`):
```
SUBSYSTEM=="tty", ATTRS{idVendor}=="1546", ATTRS{idProduct}=="01a9", SYMLINK+="sailframes-gps"
```

### Newhaven NHD-5.0-HDMI-N-RSXP
```
Pi 5 micro-HDMI0 ── HDMI ──► Display HDMI input
Pi 5 5V (Pin 2)  ──────────► Display VDD
Pi 5 GND (Pin 6) ──────────► Display GND
Pi 5 GPIO 18 (PWM) ────────► Display PWM (optional dimming)
```

Append to `/boot/firmware/cmdline.txt`:
```
video=HDMI-A-1:800x480@60D
```
The `D` flag forces enable without proper EDID. Old `hdmi_group`/`hdmi_mode`
in config.txt do NOT work with Pi 5 KMS driver.

---

## Pi Camera 3 Wide

- Sensor: IMX708, 4608×2592, 10-bit RGGB
- Requires **22-pin Pi 5 adapter cable** (not the stock 15-pin cable)
- Detect: `rpicam-hello --list-cameras` → expect `imx708_wide [4608x2592]`
- Override: `dtoverlay=imx708,cam0` in config.txt

### Autofocus
Pi Camera 3 defaults to manual focus (AfMode=0):
```python
video_config = picam2.create_video_configuration(
    controls={ "AfMode": 2, "AfSpeed": 1, "AfRange": 0 }
)
picam2.set_controls({"AfTrigger": 1})
```

### Camera power management
- Maneuver-triggered recording (camera off by default, GPS-predictive turn-on)
- Rolling pre-buffer
- Target 1080p/15fps

### Mounting
Lens-through-lid: drill ~8mm hole, seal with marine silicone. GoPro Hero 5 as supplemental recorder.

### Preview during recording
Dashboard preview extracts frames from **completed** segments (MP4 moov atom is written at end of file).
- During first segment: "preview available after first segment completes"
- When not recording: `rpicam-still` for live capture

---

## Power Budget (S1)

| Component | Draw |
|---|---|
| Pi 5 (typical) | 3–5W |
| ZED-F9P | ~0.5W |
| Camera 3 Wide (active) | ~1–2W |
| Newhaven display (1100 nit) | ~2.8W |
| BNO085 / DPS310 | negligible |
| Wi-Fi AP | +0.1–0.2W |
| **Total** | **~7–10W** |

50,000mAh power bank (~185Wh):
- With display + camera: ~18–26 hours
- With display, no camera: ~24+ hours

Power saving:
- Duty-cycle camera
- PWM dim display in overcast
- Record raw video, do CV/ML in AWS post-race
- `hdmi_blanking=2` in config.txt

---

## Networking & Pi Dashboard

- Pi 5 ran as Wi-Fi AP (hostapd) during races
- Dashboard on port 8080 (Flask + Jinja2)
- Crew connects via browser, no app
- Each boat = isolated network
- Wi-Fi client config via netplan YAML for `wlan0`
- Post-race: sync to AWS S3

### Pages

| Page | URL | Purpose |
|------|-----|---------|
| Main | `/` | Live sensor data, recording controls |
| GPS Details | `/gps` | Constellation tracking |
| Battery History | `/battery` | Sessions |
| Video Review | `/video` | Browse / play |
| Data Management | `/data` | Storage / delete by date |
| Race Dashboard | `/race.html` | Multi-boat replay (now lives on AWS) |

### Recording controls
- Start: starts all sensor services + cameras
- Stop: stops cameras only; sensors keep running for live dashboard
- Confirmation dialog before stopping

### Data directory layout
```
/mnt/sailframes-data/
├── 2026-03-30/
│   ├── gps/track_20260330_140000.csv
│   ├── ubx/raw_20260330_140000.ubx
│   ├── imu/imu_20260330_140000.csv
│   ├── pressure/pressure_20260330_140000.csv
│   ├── wind/wind_20260330_140000.csv
│   └── video/
│       ├── cockpit/cockpit_20260330_140000.mp4
│       └── sails/sails_20260330_140000.mp4
```

### S3 path (S1)
`raw/{device_id}/{date}/{sensor_type}/{filename}.csv`
e.g. `raw/sailframes-01/2026-04-01/gps/track_20260401_140000.csv`

---

## S1 Enclosure (QILIPSU IP67)
- Daily install/remove on boat — no permanent cables, under 30 seconds
- Display mounted face-up against clear enclosure lid
- DPS310 requires Gore-Tex pressure vent (Amphenol LTW VENT-PS1, ~$2-5)
- Camera: lens-through-lid (~8mm hole, marine silicone seal)
- NVMe SSD in Lemorele slim enclosure mounted internally

---

## S1-specific Known Issues

1. **BNO085 I2C clock stretching** — must set baudrate=400000 in
   `/boot/firmware/config.txt`. Default 100kHz causes intermittent read
   errors. 400kHz is the fix (not slower).

2. **Pi 4 vs Pi 5** — Pi 4 images do NOT boot on Pi 5. Reflash with Pi
   Imager selecting Pi 5 as target device.

3. **Camera cable** — Pi Camera 3 Wide ships with 15-pin cable. Pi 5
   requires the 22-pin adapter cable.

4. **DPS310 in sealed enclosure** — without a pressure vent, the sensor
   reads internal enclosure pressure, not ambient. Gore-Tex vent required.

5. **Calypso wind sensor BLE** — only one device can connect at a time.
   Pi 5 BLE client claims the connection; disconnect other devices first.

6. **Monitor service file descriptors** — excessive subprocess calls can
   exhaust file descriptors (~1024 per process). Service status checks
   limited to every 60 seconds to prevent "Too many open files" crashes.

7. **Camera busy during recording** — Pi Camera can only be accessed by
   one process. Dashboard preview extracts frames from completed segments.

---

## S1 Project History (pruned)

- March 19, 2026: Initial CLAUDE.md created from Claude.ai conversations.
- March 30, 2026: Raw UBX logging, data management page, GPS constellation tracking.
- April 8, 2026: Calypso wind sensor 180° AWA correction (also applied to E1).
- Repo dir: `edge-s/` (services/, scripts/, config/).
- Eventually shelved when E1 (ESP32 fleet tracker) became the deployed product.
