# SailFrames B1 — Hardware Specification v0.10 (Pilot)

**Status:** Draft for Claude Code KiCad implementation
**Scope:** Successor hardware platform to E1. Unified design for boats and buoys.
**Target output:** KiCad 8/9 schematic, PCB layout, BOM, Gerbers, CPL for JLCPCB PCBA

---

## Purpose

B1 is the next-generation SailFrames hardware platform replacing E1. It preserves all proven E1 functionality (BNO085 IMU, microSD logging, TFT display, Calypso BLE wind sensor support, S3 upload) while:

1. **Replacing the LG290P quad-band GNSS** with the **Quectel LC29HEAMD** dual-band (L1/L5) module
2. **Integrating the power section** (TP4056 + MT3608) onto the PCB, eliminating the DWEII USB-C boost module
3. **Adding an internal L1/L5 active patch antenna** (Quectel **YFGC007E3A**, DigiKey-sourced, hand-installed during final assembly — see Section 3 / Component Selection)
4. **Adding Qi wireless charging support** for fully sealed-enclosure operation
5. **Adding magnetic toggle power switch** (Hall sensor + latching circuit) — no mechanical switch through enclosure wall
6. **Adding ESP-NOW fleet mesh** capability for OCS detection and live fleet data
7. **Adding BLE peripheral mode** for iPhone app connection (connect-on-demand)
8. **Fitting Polycase ML-34F\*1508** enclosure (IP68/NEMA 6P, clear lid)
9. **Fully sealed enclosure — no holes in any wall** (see Sealed Enclosure Design Principles below)

The display (TFT 3.5") and IMU (BNO085 breakout) are **optional populate** per unit. The same PCB serves both boats (fully populated) and buoys (minimal populate).

---

## Reading guide for Claude Code

Before generating any KiCad files, read:

1. **`CLAUDE.md`** — project context, especially E1 hardware history and lessons learned
2. **`edge-e/hardware/`** — existing E1 PCB v1.1 KiCad project; reuse symbols, footprints, and design patterns
3. **`edge-e/firmware/`** — existing E1 firmware; understand which GPIOs are used and which peripherals connect
4. **This document** — complete B1 specification

Key constraints to respect:

- B1 firmware will be a fork of E1 firmware. **Keep GPIO assignments compatible with E1 wherever possible** to minimize firmware port effort.
- LC29HEAMD command set differs from LG290P (PAIR vs PQTM commands) — that's a firmware concern, not a hardware concern, but the UART connection must be identical (same GPIO pins).
- **No software deep sleep.** Hardware power latch (Hall sensor + flip-flop + P-MOSFET) controls 5V → ESP32 VIN. Toggle by bringing external magnet near the right side of the enclosure.
- **TFT and SD MUST be on separate SPI buses.** Sharing causes display flicker during SD writes. Same as E1.
- **Polycase ML-34F\*1508 enclosure** constrains PCB outline to 104.7×79.3mm with corner cutouts (see PCB Template section).
- **NO HOLES in any enclosure wall.** Charging via Qi (through clear lid). Power toggle via magnet (through right side wall). Firmware update via WiFi OTA. Data offload via WiFi to S3. SD card never removed during normal operation.

---

## Sealed Enclosure Design Principles

B1 is designed as a **fully sealed unit** with no holes in any enclosure wall. This is a fundamental architectural decision driven by marine environment requirements (salt spray, rain, immersion during capsizes).

**Operational consequences:**

| Function | E1 method | B1 method |
|----------|-----------|-----------|
| Power on/off | SPDT slide switch through wall | Hall sensor + magnetic toggle (right side) |
| Charging | USB-C through wall | Qi wireless coil through clear lid |
| Firmware update | USB-C through wall | WiFi OTA from S3 |
| Race data offload | USB-C / SD removal through wall | WiFi upload to S3 from dock |
| Diagnostics | USB-C serial console | Open enclosure (4 lid screws); USB-C accessible internally |
| SD card | Push-push socket through wall | Internal only — accessed by opening lid for service |

**Internal-only access components:**

- ESP32 DevKit USB-C: Internal use only. Accessible only by removing 4 lid screws. Used during initial bring-up, firmware development, factory provisioning. Not used during normal operation.
- microSD socket: Internal only. SD card stays in place permanently. Data flows to S3 via WiFi. Lid opens only if SD card needs replacement (rare).

**The five signal paths through enclosure walls (RF/magnetic/inductive, not physical):**

1. **GNSS signal** (L1/L5 satellite signals) — through clear polycarbonate lid via internal Quectel YFGC007E3A active antenna
2. **WiFi signal** (2.4 GHz) — through enclosure walls via ESP32 PCB antenna (polycarbonate is RF-transparent)
3. **BLE signal** (2.4 GHz) — through enclosure walls via ESP32 PCB antenna
4. **Qi power** (~120-200 kHz inductive coupling) — through enclosure BASE (opposite the clear lid) via Qi receiver coil taped to inside of base wall
5. **Magnetic toggle** (DC magnetic field) — through right side wall via Hall sensor

**Enclosure integrity verification (pilot test plan):**

- Submersion test: 30 minutes at 1m depth (IP67 minimum, ML-34F is rated IP68/NEMA 6P)
- Salt spray test: 4 hours simulated marine spray
- Thermal cycling: -10°C to +50°C across 5 cycles, then submersion test
- Drop test: 1m onto wood deck, then submersion test

---

## Component Selection (Verified)

### GNSS Receiver

**Quectel LC29HEAMD** (LCSC C28453488, JLCPCB Assembly Extended part)

- Package: 24-pin LCC, 12.2×16×2.5 mm
- Frequencies: L1 (1575.42 MHz) + L5 (1176.45 MHz) dual-band
- Constellations: GPS, GLONASS, Galileo, BeiDou, QZSS
- SBAS: WAAS, EGNOS, MSAS, GAGAN
- RTK rover/base capable (used in rover mode for B1, base mode TBD)
- Raw observation output: 1 Hz max (acceptable for SailFrames analytics)
- UART1: 3.3 V logic (direct connect to ESP32)
- UART2: 1.8 V logic (not used — requires level shifting)
- VCC: 3.1–3.6 V, 3.3 V typical
- Active mode current: ~30 mA
- JLCPCB stock as of 2026-05-15: 20 units at $24.10/unit

**Footprint source:** Use `JLC2KiCadLib` to generate symbol + footprint from C28453488:
```bash
pip install JLC2KiCadLib
JLC2KiCadLib C28453488
```

This produces a JLCPCB-verified symbol and footprint that matches the assembly line's expectation. Do not hand-create the footprint.

**Reference documents to consult:**

- Quectel LC29H Series Hardware Design V1.3 (2024-07-30) — pin assignments, electrical specs, reference circuits
- Quectel LC29H Series Reference Design V1.2 (2023-01-18) — full reference schematic Quectel publishes

### MCU

**ELEGOO ESP32 DevKit V1** (socketed)

- ESP32-WROOM-32 module on dev board
- USB-C connector for programming and serial console
- Onboard CH340 USB-UART
- Onboard AMS1117-3.3 LDO (handles VIN → 3.3V)
- 38-pin DevKit form factor

**Mounting:** Female headers on B1 PCB; DevKit plugs in vertically. Same as E1.

**Why socketed:** Field replacement, easy firmware flashing via DevKit USB, identical to E1 (no firmware GPIO changes needed).

### Power — Charger

**TP4056** (LCSC C16581 or equivalent, SOP-8 package)

- Single-cell LiPo charger, CC-CV
- 5V input from USB or Qi receiver
- Charge current programmable via single resistor (RPROG)
- Charge status outputs (CHRG, STDBY LEDs)

**Battery protection:** Add **DW01A + 8205A** protection circuit (or use protected LiPo cell). DW01A handles over-voltage, over-discharge, over-current. 8205A is the dual MOSFET that switches the battery.

### Power — Boost Converter

**MT3608** (LCSC C47764, SOT23-6 package)

- 3.7V LiPo → 5V boost
- 2A max output (we'll use ~500mA)
- Output voltage set by resistor divider (R1/R2)
- External inductor: 22 µH, 1A min
- External Schottky diode: SS14 or equivalent
- Input/output capacitors: 22 µF MLCC

### LiPo Battery

**Locked 2026-05-18 (v0.10): 503562 protected LiPo, 5 × 35 × 62 mm, 1500 mAh, JST PH 2.0**

Sourcing: widely stocked at Adafruit-class hobby vendors and AliExpress. Examples: Sparkfun PRT-13855 (close form factor, verify protection), Adafruit 354 (similar), or generic 503562 from AliExpress (~$10–15 each, verify built-in protection PCB).

Specs:
- 3.7 V nominal, 4.2 V fully charged, 2.5 V protection cutoff (DW01A on-cell)
- **5 mm thick** — fits in the 5 mm below-PCB clearance (boss height measured 5 mm)
- 35 × 62 mm footprint — sits on enclosure base floor beside the Qi receiver coil
- 1500 mAh — same capacity as the v0.8 803450 choice
- Protected cell (on-cell DW01A + 8205A) — no protection circuit on B1 PCB
- JST PH 2.0 mm connector — mates with J2 on B1 PCB

**Why this cell** (changed from 803450 in v0.8 → v0.10):
The Polycase ML-34F mounting bosses measured 5 mm on the actual sample. The previous 803450 cell (8 mm thick) cannot fit in the 5 mm below-PCB envelope. The 503562 cell preserves the 1500 mAh capacity at a thinner profile.

**Fallback if 503562 hard to source: 503450** (5 × 34 × 50 mm, 1000 mAh, also protected). Reduces run-time by ~33 %; acceptable for pilot, marginal for long race days.

**Run-time math** (1500 mAh / ~300 mA average draw): ~5 hours — covers a typical race day with margin. Off-state drain (~80 µA per v0.8 power table) → 1500 mAh / 80 µA = ~18,750 hours = ~2.1 year off-season storage.

### Qi Wireless Charging Receiver

**Acxico 5W Qi Wireless Charger Receiver Module** (or equivalent generic 5W Qi module)

Validated by bench test 2026-05-16: 5.13V stable continuous output through E1 enclosure wall, full ESP32 boot from Qi power alone with battery disconnected, DWEII USB-A charging chain operates correctly.

**Module specifications:**

- Input: Inductive coupling from Qi-compatible transmitter pad (5W mode)
- Output: 5V ± 0.25V DC, 1A maximum
- Charging efficiency: ~75%
- Transmission distance: 2-8mm (works through ~3mm polycarbonate wall)
- Coil: ~41 × 29 mm flat copper coil
- Receiver PCB body: ~25 × 15 mm SMD board with rectifier and 5V regulator
- Coil-to-PCB connection: short soldered leads, fixed (not user-detachable)
- Output: 2 leads (red = +5V, black = GND), ~100mm long
- Sourcing: Acxico on Amazon ($10 for 2-pack), or equivalent from AliExpress ($1-3 each)

**Mounting on B1 enclosure: BOTTOM of enclosure (opposite the clear lid)**

The Qi coil is mounted on the **inside of the enclosure base** — the polycarbonate wall opposite the clear lid. This places the coil at the bottom of the unit when it sits flat on a charging dock with the clear lid facing up.

```
Charging dock alignment (unit lid-up on Qi pad):

         ┌───────────────────────────┐
         │  CLEAR LID (sky-facing)    │  ← TFT, LEDs, GNSS antenna visible
         ├───────────────────────────┤
         │                           │
         │   TFT (above main PCB)    │
         │                           │
         │   B1 main PCB             │
         │   (GNSS, ESP32, sensors)  │
         │                           │
         │   LiPo battery            │
         │                           │
         │   Qi receiver PCB body    │
         │   ────[coil]────          │  ← Qi coil taped to inside of base
         ├───────────────────────────┤
         │  ENCLOSURE BASE            │  ← faces DOWN onto charging pad
         └───────────────────────────┘
                    ↓
              Qi transmitter pad
              (W9, Calypso dock, etc.)
```

**Why bottom of enclosure (not lid):**

1. Clear lid is needed for TFT visibility, status LED visibility, and GNSS antenna sky-view
2. Sailor places unit lid-up on dock → sees TFT and LEDs during charging
3. Bottom of enclosure naturally faces down toward the charging pad (phone-style)
4. Polycarbonate base is RF-transparent at Qi frequencies (~120-200 kHz)

**Mechanical attachment:**

- Qi coil: double-sided adhesive (3M VHB or equivalent) to inside surface of enclosure base, centered laterally for charging pad alignment
- Qi PCB body: also taped to enclosure base, immediately adjacent to coil (preserves the fixed coil-PCB lead geometry)
- Output wires (red/black): routed up from PCB body to dedicated J_QI solder pads on B1 PCB top layer, ~80-100mm wire length allows lid to be opened for service without strain
- For production: consider mounting only the coil to the base, with the receiver PCB body soldered to B1 PCB bottom layer (cleaner manufacturing)

**Wall thickness verification (resolved 2026-05-17 from Polycase ML-34F datasheet rev C/1, 6/11/2020):**

- Base wall typical: 0.125" = **3.18 mm** polycarbonate
- Clear lid (ML-34C\*08) top surface typical: 0.130" = **3.30 mm** polycarbonate
- Base is essentially equivalent to lid thickness — Qi through-base architecture validated by existing bench test (Acxico through E1 enclosure of comparable thickness gave 5.13V stable output through enclosure wall)
- Acxico module 2-8mm transmission distance spec easily covers 3.18mm base wall

### IMU (Optional)

**Adafruit BNO085 breakout** (same as E1) — socketed, optional populate

- 9-DOF sensor fusion (gyro + accel + mag)
- I2C @ 0x4A (with 4.7KΩ pull-ups on PCB)
- 3-5V VIN tolerant (connect to 3.3V)
- Pinout: VIN, GND, 3Vo, SDA, SCL, INT, RST, P0, P1
- **Mounting orientation MUST match E1** (chip facing up, edge alignment) to preserve existing firmware rotation transforms

### TFT Display (Optional)

**Hosyond 3.5" IPS ST7796U** (same as E1) — socketed via header pins, optional populate

- 480×320 IPS color display
- ST7796U driver IC
- SPI interface (4-wire)
- Backlight LED with control pin
- Built-in microSD slot (NOT used — B1 has dedicated microSD slot on PCB)
- PCB footprint: ~98×61 mm
- Stacks above main B1 PCB on standoffs

### microSD Card Holder

**Push-push microSD socket** (e.g., LCSC C160390 or equivalent, SMD)

- Same as E1 (HSPI bus, separate from TFT VSPI)
- 3.3V signaling (no level shifters needed)
- Mount on B1 PCB, NOT via TFT's built-in slot

### GNSS Antenna

**Quectel YFGC007E3A — Active GNSS L1 & L5 Antenna**

Externally sourced from DigiKey (P/N 2958-YFGC007E3A-ND, ~$14.12 at qty 20). **Not in JLCPCB's Assembly Parts Library** — hand-installed during final B1 assembly. The B1 PCB is designed with a u.FL receptacle (J3), bias-T components, and 4 plated thru-hole buckle-mount holes; the antenna is plugged in and snapped down at final assembly.

Specs verified against the Quectel YFGC007E3A Datasheet V1.1 (2024-02-05):

| Spec | Value |
|------|-------|
| Product name | Active GNSS L1 & L5 Antenna |
| Type | Active (2× 3 dB hybrid couplers + SAW filters + 2-stage LNA + diplexer, all integrated) |
| Frequency Range | 1164–1189 MHz (L5) + 1559–1606 MHz (L1) |
| Polarization | RHCP (Right Hand Circular) |
| LNA Gain | **17 ± 3 dB** (measured 17.1 @ L5, 18.1 @ 1575 MHz) |
| Noise Figure | **≤ 2.5 dB** (measured 2.2 @ L5, 2.0 @ 1575 MHz) |
| VSWR (antenna side) | 1.25 @ L5, 1.30 @ 1575 MHz, 1.38 @ 1602 MHz |
| Output VSWR (LNA side) | < 2.0 |
| Filter Out-of-Band Attenuation | **≥ 50 dB at f₀ ± 100 MHz** (excellent — protects against LTE/cellular blockers) |
| Working Voltage | **3–5 V** (3.3 V from LC29HEAMD VDD_RF is at the low end of spec) |
| Working Current | **15.5 ± 4 mA** |
| Impedance | 50 Ω |
| Dimensions | **50 × 50 × 14.5 mm** (carrier PCB 50×50, frame 38×38, ceramic patch 25×25) |
| Cable | 100 mm, Φ1.13 mm, black, IPEX MHF1 (= u.FL) plug |
| Mount | 4 buckle pins on bottom, ~37 × 37 mm spacing |
| Weight | Typ. 48.5 g |
| Operating Temperature | -40 °C to +85 °C |
| Datasheet | Quectel_Antenna_YFGC007E3A_Datasheet_V1.1.pdf (2024-02-05) |

**GNSS coverage (per datasheet Section 1.4):**

- GPS: L1 ✓ + L5 ✓
- GLONASS: G1 ✓
- Galileo: E1 ✓ + E5a ✓
- BeiDou: B1I ✓ + B1C ✓ + B2a ✓
- QZSS: L1 ✓ + L5 ✓
- IRNSS: L5 ✓

**Block diagram (per datasheet Section 1.3):** dual feeds → 2× 3 dB hybrid couplers → SAW filters → 1st-stage LNAs → diplexer → 2nd-stage LNA → internal LDO → single RF+DC output to IPEX cable. **All RF complexity is internal to the antenna module — the B1 PCB needs only a 50 Ω microstrip and a bias-T.**

**Why this antenna was chosen:**

1. **Active with manufacturer-matched LNA gain** — 17 dB at the receiver's expected input level
2. **RHCP polarization** — required for multipath rejection over Boston Harbor water reflections
3. **Single-port output with internal hybrid couplers + diplexer** — no RF design work needed on B1 PCB beyond the bias-T
4. **In stock at DigiKey** with 60-day return path — de-risks the pilot
5. **Quectel-Quectel pairing** with LC29HEAMD receiver
6. **Excellent out-of-band rejection** (≥ 50 dB at ±100 MHz) — survives ESP32 WiFi (2.4 GHz) and LTE blockers from a phone in the cockpit

**Why alternatives were rejected:**

- **Quectel YCGO014AA** (LCSC C20108097, JLCPCB-stocked, passive L1/L5) — **dual-feed** patch that requires the customer PCB to provide its own hybrid couplers + diplexer + 50 Ω terminations as printed microstrip features. Substantial precision RF layout work; not suitable without a dedicated RF engineer. Performance acceptable if implemented correctly.
- **Quectel YCGA001AA / YCGA002AA** (JLCPCB pre-order) — **L1-only** passive ceramic patches. Loss of L5 cripples PPK convergence, which is the project's strategic differentiator.
- **Quectel YC0013AA** (LCSC C3292993, JLCPCB-stocked) — 1206 SMD chip antenna, L1-only, 1.19 dBi. Built for fitness trackers, not GNSS positioning.
- **Suzhou Maswell AN.GNSS.L1.PCB.02** (LCSC C5562344) — out of stock at LCSC and JLCPCB; not viable.
- **External SMA antenna + bulkhead** — would require an enclosure penetration; B1 design mandates fully sealed enclosure with no holes.
- **Earlier-spec "YCGA014AA"** — does not exist in JLCPCB's library; v0.1–v0.8 referenced this part based on fabricated specs. YFGC007E3A is the real Quectel part the spec was attempting to describe (matching 17 dB LNA, RHCP, IPEX 100 mm cable, active L1/L5 architecture).

**PCB integration:**

- 50 × 50 mm continuous copper **ground pour** on B1 PCB top layer below antenna position (datasheet test condition; required for spec performance). Stitched to bottom-layer GND with vias every 2–3 mm.
- 4 plated **thru-hole mounting holes** at 37 ± 0.2 mm × 37 ± 0.2 mm spacing for the antenna's buckle pins. Hole diameter ~1.2–1.4 mm (fit clearance for the buckle pin diameter).
- Ceramic patch face-up toward enclosure clear lid (sky-facing). Z-axis from PCB top: 14.5 mm.
- **No other components within 15 mm** of antenna outline (per datasheet keep-out).
- **u.FL receptacle (J3)** on PCB within ~80 mm of antenna's IPEX cable exit point (100 mm cable, allow slack to coil flat — do not pull taut).
- 50 Ω controlled-impedance microstrip from J3 through bias-T to LC29HEAMD RF_IN. **Trace length < 20 mm. No vias on RF trace.**
- Stack height above PCB: **14.5 mm** (fits in ML-34F's ~25 mm above-PCB clearance, but tightens the TFT standoff budget — verify TFT clears antenna patch face by ≥ 5 mm).

**Bias-T circuit on B1 PCB (LC29HEAMD side):**

The YFGC007E3A is fed DC bias (3.3 V, 15.5 mA) through the same coax cable that carries the RF signal back. Standard bias-T between the u.FL receptacle and LC29HEAMD RF_IN pin:

```
u.FL center ──[L_BIAS 33 nH, 0402]──┬── 3.3 V (LC29HEAMD VDD_RF)
                                     │
                                     ├──[C_BYPASS 10 nF, 0402]── GND (RF bypass)
                                     │
LC29HEAMD RF_IN ──[C_BLOCK 100 pF, 0402]──┘
                  (DC block, passes RF)
```

Component value rationale:
- **L_BIAS = 33 nH, 0402** (changed from 10 nH in v0.8). X_L at L1 (1575 MHz) = 326 Ω, at L5 (1176 MHz) = 244 Ω — > 5× the 50 Ω line impedance in both bands, so RF leakage into the DC path is negligible. The earlier 10 nH gave only ~100 Ω at L1, which leaked too much RF.
- **C_BLOCK = 100 pF, 0402.** X_C at L1 = 1.0 Ω, at L5 = 1.4 Ω — transparent to RF, blocks DC.
- **C_BYPASS = 10 nF, 0402.** Provides a low-impedance RF return for the LNA bias supply.
- **Verify on first prototype**: with antenna installed and unit powered, measure ~15.5 mA on the 3.3 V bias trace. Zero current = LNA dead (bad solder, bad cable, or damaged antenna). > 25 mA = wrong part or damaged. This is the day-one canary that the antenna chain works.

**No external SMA bulkhead** — B1 design mandates fully sealed enclosure with no holes. All RF signal routing is internal.

**Procurement and assembly:**

- DigiKey P/N **2958-YFGC007E3A-ND**, $14.12 each at qty 20 (qty-20 break is the sweet spot — also covers spares and the 60-day partial-return path if validation fails)
- 8-week manufacturer standard lead time (DigiKey stock at order placement: 109 units 2026-05-18)
- Pilot order: 20 units placed 2026-05-18, invoice 2026-05-18 → return window through ~2026-07-17
- Open one tray cavity for validation; keep remaining 19 antennas sealed in original Quectel tray packaging until first-prototype validation passes
- Production assembly step (per unit, ~3 min): snap buckle pins into 4 B1 PCB mounting holes; route 100 mm IPEX cable; snap IPEX plug onto u.FL receptacle (J3) with audible click; optional 3 mm bead of Dow Corning 3145 RTV silicone over the u.FL for vibration insurance; close enclosure lid (4 screws)

### Hardware Power Switch (Magnetic Toggle Latch)

**Architecture:** Hall effect sensor + discrete toggle flip-flop + P-channel MOSFET. No mechanical switch through enclosure wall. User toggles power by holding a small neodymium magnet against the marked spot on the **right side** of the enclosure exterior for ~1 second.

**User experience:**

- Bring magnet near right side of enclosure → Hall sensor detects → flip-flop toggles → power latches ON (TFT boots, LED blinks once)
- Bring magnet near same spot again → Hall sensor detects → flip-flop toggles → power latches OFF (LED blinks twice, then off)
- Magnet does NOT need to stay near the unit. Toggle is momentary action; state is latched.
- Single magnet shared across the fleet (race organizer's keychain magnet)

**Components:**

| Designator | Part | LCSC # | Function |
|------------|------|--------|----------|
| U_HALL | TI DRV5032AJ | C606060 | Hall sensor, ±2.5 mT operating point, 1.3 µA quiescent, omnipolar |
| U_FF | 74LVC1G74 | LCSC stocked | Single D flip-flop SOT-23-8 with async PRE/CLR pins (toggle config: D tied to /Q). **PIN NUMBER WARNING:** the pin numbers used elsewhere in this document (1=/PRE, 2=D, 3=CLK, 4=/CLR, 5=GND, 6=/Q, 7=Q, 8=VCC) are illustrative for the topology. The actual SOT-23-8 pinout differs by vendor — TI SN74LVC1G74 uses a different mapping than Nexperia 74LVC1G74. **Before drawing the KiCad symbol, fetch the manufacturer datasheet for the exact LCSC part chosen and remap the pin numbers to match.** The net topology (D↔/Q tie, CLK from debounce, Q to MT3608 EN and NPN base, /CLR from U_RST, /PRE to VCC) is correct as written; only the pin numbers need vendor verification. |
| Q_INV | 2N3904 NPN | LCSC C20526 or equiv | Level-shifter inverter for MOSFET gate drive (FF output 0-3.3V → MOSFET gate 0-5V) |
| Q_PWR | AO3401A | C15127 | P-channel MOSFET, 4A, switches 5V → ESP32 VIN |
| R_DBNC | 10 KΩ 0603 | various | Debounce RC with C_DBNC |
| C_DBNC | 100 nF 0603 | various | Debounce capacitor (~1 ms time constant) |
| R_BASE | 10 KΩ 0603 | various | Base resistor for 2N3904 |
| R_PULLUP | 100 KΩ 0603 | various | Collector pull-up to 5V (controls MOSFET gate when NPN OFF) |
| U_RST | MAX809T-T (or equiv) | LCSC TBD | Voltage supervisor on /CLR, 3.08 V threshold, 240 ms reset timeout, SOT-23-3, push-pull active-LOW |

**Circuit topology:**

```
Battery (3.7V LiPo) ──┬──→ DRV5032AJ VCC (always-on, 1.3 µA quiescent)
                      └──→ 74LVC1G74 VCC (always-on, 0.1 µA quiescent)

DRV5032AJ OUT ──[R_DBNC + C_DBNC debounce]──→ 74LVC1G74 CLK (pin 3)
74LVC1G74 D (pin 2) ──── tied to /Q (pin 6) — toggle configuration
74LVC1G74 /PRE (pin 1) ── tied to VCC (never preset)
74LVC1G74 /CLR (pin 4) ── U_RST /RESET output (held LOW until VCC > 3.08 V, then 240 ms hold)
74LVC1G74 Q (pin 7) ────┬→ NPN level shifter → Q_PWR gate (gates 5 V → ESP32 VIN)
                         └→ MT3608 EN pin   (gates the boost converter itself)

NPN level shifter (translates FF 3.3V output to MOSFET 5V gate):
  74LVC1G74 Q ──[R_BASE 10K]── 2N3904 base
                                  │
                                  ├── 2N3904 emitter → GND
                                  │
                                  └── 2N3904 collector ──[R_PULLUP 100K]── +5V
                                                            │
                                                            └── Q_PWR gate

MT3608 5V OUT ──[Q_PWR P-MOSFET source-drain]──→ ESP32 DevKit VIN
MT3608 EN ←─────── 74LVC1G74 Q  (boost shuts down when latch is OFF)

Logic table:
  Q=HIGH → MT3608 EN HIGH (boost running, 5 V on VOUT)
         + NPN ON → P-MOSFET gate ~0V → P-MOSFET ON (Vgs ≈ -5V) → Power ON
  Q=LOW  → MT3608 EN LOW  (boost in shutdown, <1 µA, 5 V rail collapsed)
         + NPN OFF → P-MOSFET gate pulled to 5V via R_PULLUP → P-MOSFET OFF → Power OFF
  (Double-gated: even a leaky MOSFET cannot pass current because the 5 V rail is also off.)
```

**Power-on default state:**

- 74LVC1G74 /CLR pin is held LOW by U_RST voltage supervisor (MAX809T-T or equiv, 3.08 V threshold) whenever VCC < 3.08 V. After VCC crosses threshold, /RESET is held LOW for an additional 240 ms reset timeout, then released.
- /CLR LOW forces Q = LOW → MT3608 EN LOW (boost off) AND NPN OFF (MOSFET off). Safe default — unit powers up in OFF state.
- A supervisor IC is used instead of an RC POR network because the RC variant fails on slow VCC ramps (e.g., the multi-minute ramp of a depleted protected cell being trickle-charged through the protection FET body diode). The supervisor's threshold-and-timeout behavior is independent of ramp speed.
- /PRE tied permanently to VCC (never used).

**Power consumption:**

| State | Component drain | Total |
|-------|-----------------|-------|
| OFF | DRV5032AJ: 1.3 µA + 74LVC1G74: 0.1 µA + U_RST supervisor: ~12 µA + NPN reverse leak: <1 µA + MOSFET leak: <1 µA + MT3608 shutdown (EN LOW): <1 µA + TP4056 shutdown: 0.5 µA | ~15–18 µA |
| ON | All of above + ESP32 + LC29HEA + (optional TFT/IMU) | 200-400 mA |
| Standby total | ~15–18 µA latch logic + ~20 µA battery monitor divider + ~30–60 µA LiPo self-discharge | ~70–95 µA |

**Off-season storage:** 1500 mAh / ~80 µA ≈ 19,000 hours ≈ 2.1 years. Six-month off-season storage uses ~20 % of battery capacity. Previous always-on MT3608 design depleted in ~31 days from full — gating MT3608 EN on the latch is what makes seasonal storage viable.

**PCB placement: RIGHT side of PCB, middle height vertically**

- Coordinate suggestion: X = 102.7 mm (1 mm from right edge), Y = 40 mm (vertical middle of 79.3 mm PCB)
- Hall sensor IC oriented with sensing face perpendicular to right edge (X-axis sensitivity)
- Marker on enclosure exterior right wall: small silkscreen or sticker label, ~12 mm diameter circle, aligned with sensor position
- Keep at least 20 mm from MT3608 inductor (switching field rejection)
- Keep at least 30 mm from BNO085 (avoids interfering with magnetometer calibration)
- BNO085 is placed on LEFT side of PCB (matches E1 PCB v1.1 orientation), opposite side from Hall sensor

**Magnet for users (supplied separately, not on PCB):**

- 10mm × 3mm N52 neodymium disc magnet
- ~$0.30-0.50 each from AliExpress
- Activation distance through enclosure right wall: 5-8 mm
- Buy 20-30 for fleet (single magnet shared by race organizer, plus spares)
- Optional: attach to keychain, lanyard, or marine-grade clip

**Confirmation indication on toggle:**

- ON event: Status LED D4 (Red, power/heartbeat) goes solid for 1 second, then begins slow blink pattern. TFT begins boot sequence (~2 seconds to first display).
- OFF event: Status LED D4 (Red) flashes 3 times rapidly (~1 second total), then power cuts. Firmware should listen for impending shutdown and write any pending log data to SD before LED finishes blinking.

**Firmware integration:**

- ESP32 GPIO assigned to read the latch state (HIGH = currently on)
- When the flip-flop toggles to OFF state, ESP32 has ~500 ms to write pending data before MOSFET cuts power. Use this window for:
  - Flush SD card buffer
  - Close any open log files
  - Set "clean shutdown" flag in NVS
- On next power-on, ESP32 reads the clean-shutdown flag to distinguish graceful shutdown from power loss

---

## PCB Mechanical Constraints

### Enclosure: Polycase ML-34F\*1508

- External: 4.531" × 3.563" × 2.258" = 115 × 90 × 57 mm
- Internal cavity: 4.124" × 3.122" × 1.93" = 105 × 79 × 49 mm
- Internal base depth (floor to gasket seat): 1.500" = 38.1 mm
- **Base wall thickness (typical): 0.125" = 3.18 mm** polycarbonate
- **Clear lid (ML-34C\*08) top surface thickness (typical): 0.130" = 3.30 mm** polycarbonate
- Cover height: 0.690" = 17.5 mm (with internal dome rising to 0.758" = 19.3 mm)
- Cover: Clear UV-stabilized polycarbonate, IP68/NEMA 6P (ML-34C\*08, BOM item 2)
- Base: Light gray polycarbonate with brass inserts (ML-34BF\*15, BOM item 4)
- Gasket: Continuous silicone (GASKET-6, between lid and base)
- Cover screws: 6-32 × 1.25" stainless steel pan-head Phillips (SCREWS-SS6-4, 4-pack)
- Mounting: 4 brass 6-32 inserts in base at corner positions for cover screws
- 8 internal PCB mounting bosses in base (4 brass-insert for lid + 4 plastic PCB bosses)
- Datasheet: `Polycase_ML-34F_drawing.pdf` (drawing C, rev 1, 6/11/2020)

### PCB Template (Polycase ML-34BF-PCB)

- **PCB outline: 4.124" × 3.122" = 104.7 × 79.3 mm** with corner cutouts (R = 0.377" = 9.6 mm)
- **4 corner cutouts** to clear the mounting boss bumps (corner R.377)
- **Mounting hole pattern: 4× 0.165" diameter (4.19 mm) clearance for 6-32 screws**
  - X spacing: 3.344" (85.0 mm) center-to-center
  - Y spacing: 1.969" (50.0 mm) center-to-center
- **Reference:** Polycase ML-34F\*1508 datasheet, page 6 (PCB template ML-34BF-PCB, rev A)
- Includes 0.031" (0.79 mm) clearance from interior walls

Claude Code: import the Polycase PCB template dimensions from the ML-34F\*1508 datasheet drawing (downloaded to `edge-e/hardware/datasheets/Polycase_ML-34F_drawing.pdf`, page 6).

### Component Placement Zones

```
B1 PCB top view (looking down at lid side):

Orientation reference:
  TOP edge of PCB    = sky-facing edge (antenna), away from sailor
  BOTTOM edge of PCB = near-sailor edge (Qi coil under it for charging pad alignment)
  LEFT side of PCB   = port-side wall when boat-mounted (IMU)
  RIGHT side of PCB  = starboard-side wall when boat-mounted (magnetic toggle)

┌──────────────────────────────────────┐  ← TOP edge (antenna up, sky-facing)
│ ANTENNA + GNSS ZONE                  │
│ YFGC007E3A (50×50 mm, hand-installed)│
│ 50×50 mm GND pour + 4× 1.3 mm holes  │
│ at 37×37 mm spacing for buckle pins  │
│ LC29HEAMD adjacent (RF trace <20mm)  │
│ u.FL receptacle J3 + bias-T          │
├──────────────────────────────────────┤
│ MCU / SENSOR ZONE                    │   ┌────┐
│                                      │   │    │
│ [BNO085]     [ESP32 DevKit V1]      │   │ U_ │ ← Hall sensor
│  socket      socketed, USB-C        │   │HALL│   (RIGHT edge,
│  LEFT side   pointing inward         │   │    │   middle height)
│              (internal access only)  │   │    │
│              [microSD onboard]       │   │    │
├──────────────────────────────────────┤   └────┘
│ POWER ZONE                           │
│ [TP4056] [MT3608+inductor] [Q_PWR]   │
│ [U_FF flip-flop + debounce RC]       │
│ [LiPo JST PH connector]              │
│ [J_QI solder pads — wires to Qi      │
│  receiver module mounted on base]    │
│ ●─●─●─●─●─●  LED bar (6 LEDs)        │
└──────────────────────────────────────┘  ← BOTTOM edge (toward sailor)
   ↑                                       Qi coil mounted on inside of
LEFT side                              RIGHT side       enclosure BASE
(IMU)                            (magnetic toggle)      (opposite clear lid)

TFT mounts above main PCB via standoffs (when populated for boats).
6-LED status bar at BOTTOM edge of PCB, visible through clear lid:
[Blue/Qi] [Yellow/CHRG] [Green/STDBY] [Red/Power] [White/GPS] [Cyan/SD]

Qi receiver module (coil + PCB body) mounts on INSIDE surface of enclosure BASE,
opposite the clear lid. Two wires route up to J_QI solder pads on B1 PCB.
```

**Critical placement rules:**

1. **Antenna at TOP edge of PCB**, away from ESP32 and switching power supplies. Minimum 30 mm separation from MT3608 inductor and ESP32 antenna trace.
2. **Ground plane under antenna** (50×50mm min copper pour, top + bottom layer, stitched with vias every 2-3 mm).
3. **LC29HEAMD adjacent to antenna** to keep RF trace short (<20 mm).
4. **ESP32 DevKit centered** with USB-C connector pointing INWARD (toward PCB center, not toward enclosure edge). USB-C is INTERNAL-ONLY access — requires opening lid (4 screws) to plug in.
5. **Power components grouped at BOTTOM** of PCB. MT3608 inductor and Schottky on inner-layer return paths.
6. **BNO085 socket on LEFT side** of PCB (matches E1 PCB v1.1 orientation for firmware-compatible IMU rotation transforms).
7. **Hall sensor (U_HALL) on RIGHT side** of PCB, middle height vertically (X=102.7mm, Y=40mm). Marker on enclosure right wall exterior for magnet placement.
8. **microSD socket positioned for internal access only.** No enclosure side wall opening. SD card stays in place during normal operation.
9. **6-LED status bar at BOTTOM edge of PCB** (Y=5mm, X=15-90mm spread, 15mm spacing). Sailor-facing when boat-mounted, top-facing on charging dock (visible through clear lid). Not blocked by TFT (TFT mounts in center-top area). See Section 9 for details.
10. **J_QI solder pads near BOTTOM edge of PCB** for Qi receiver module wires. The Qi receiver itself is NOT on the B1 PCB — it's mounted on the inside surface of the enclosure base (opposite the clear lid). Allow ~80-100mm wire routing.
11. **No components on PCB edges that would require enclosure wall holes.** All connectors are internal-access or use RF/magnetic/inductive coupling through walls.

### Stack-up Heights (Vertical Budget)

Verified from ML-34F datasheet:
- Total internal cavity height: 49 mm (base floor to cover dome interior)
- Base interior depth (floor to gasket seat): **38.1 mm** (1.500")
- Cover internal depth: ~10 mm (above gasket seat to dome interior)

**Resolved 2026-05-18: PCB mounting boss height = 5 mm** (measured on Polycase ML-34F sample with calipers). This is the lower bound of typical Polycase boss heights and forces the LiPo choice (see below — 803450 at 8 mm no longer fits; switched to 503562 at 5 mm thick).

**Stack-up — measured 2026-05-18 with 5 mm boss height:**

```
Cover dome interior ────────────────────  49 mm above base floor
                                              │  (cover internal: ~10mm)
Gasket seat ────────────────────────────  38.1 mm
                                              │
                                              │  Above-PCB space:
                                              │  ~31 mm available (38.1 - 5 boss - 1.6 PCB - 0.5 margin)
TFT display surface (boats only):              ~36 mm
  TFT module body + components                  ~28 mm
  TFT standoffs above main PCB                  10 mm
                                              │
YFGC007E3A antenna stack:                      ~21 mm
  Patch face                                    14.5 mm above PCB
  Antenna body                                  0-14.5 mm above PCB
                                              │
ESP32 DevKit V1 with headers                  ~15 mm above PCB
BNO085 breakout (optional)                     8 mm above PCB
Tallest passive components                     5 mm above PCB
                                              │
Main B1 PCB top surface (1.6 mm FR4)          ~6.6 mm above base
                                              │
PCB sitting on bosses (5 mm tall, MEASURED)   ~5 mm above base
                                              │
                                              │  Below-PCB space:
                                              │  5 mm — LiPo + Qi coil sit on base floor SIDE-BY-SIDE
LiPo 503562 (5 × 35 × 62 mm, 1500 mAh) ─┐
                                          ├── on base floor, side-by-side
Qi receiver coil (0.5 mm thick) ────────┘
                                              │
Base interior floor ────────────────────  0 mm
Base wall (3.18 mm polycarbonate) ─────  faces DOWN toward Qi pad
```

**Below-PCB layout (top-down view of enclosure base floor, 5 mm tall to top of bosses):**

```
┌─────────────────────────────────────────────┐  ← Top of ML-34F base (looking down)
│ ●(boss)                          (boss)● │   ← 4 PCB bosses at corners
│                                             │
│  ┌─────────────────┐  ┌──────────────────┐ │
│  │  Qi RX coil     │  │  LiPo 503562     │ │
│  │  ~41 × 29 mm    │  │  5 × 35 × 62 mm  │ │
│  │  ~0.5 mm thick  │  │  1500 mAh        │ │
│  │  (centered for  │  │  protected cell  │ │
│  │   charging-pad  │  │  JST PH 2.0      │ │
│  │   alignment)    │  │  connector       │ │
│  └─────────────────┘  └──────────────────┘ │
│                                             │
│ ●(boss)                          (boss)● │
└─────────────────────────────────────────────┘
       ← Qi receiver PCB body NOT here — relocated to B1 PCB top side (see below)
```

**Qi receiver PCB body** (the small SMD board that rectifies coil output into 5 V DC) cannot fit in the 5 mm below-PCB envelope. **Relocate to B1 PCB top side** — soldered or taped to a small allocated area on the top surface of B1 PCB, with two thin wires running down to the Qi coil on the base floor. The J_QI solder pads on B1 PCB top become the Qi coil's wire termination (red = +5 V from receiver, black = GND); the receiver's own PCB body sits adjacent to those pads on the B1 PCB top side.

**LiPo decision locked:**

- **Primary: 503562** protected LiPo, 5 × 35 × 62 mm, **1500 mAh**, JST PH 2.0 connector. Preserves v0.8 capacity target (was 803450 1500 mAh at 8 mm thick — same capacity, thinner profile).
- **Fallback if 503562 hard to source: 503450** protected, 5 × 34 × 50 mm, 1000 mAh. Reduces run-time from ~5 h to ~3.3 h at 300 mA average draw; tight for a long race day but workable for the pilot.
- Both options preserve the v0.4 decision: protected cell, no DW01A+8205A on B1 PCB.

**For buoy variant (no TFT):** Above-PCB space freed up by ~28 mm. Could use a larger / taller cell if buoy run-time targets exceed boat targets. Out of scope for this pilot.

**For boat variant (with TFT):** Stack-up is tight but workable. The TFT (10 mm standoffs + 28 mm body = 38 mm top above PCB) approaches the 38.1 mm above-PCB ceiling. **Verify with physical mock-up before locking PCB layout** — if TFT clearance is too tight, drop TFT standoffs to 8 mm (still leaves 5 mm clearance above the YFGC007E3A antenna patch).

### Antenna Ground Plane

- **Minimum:** 50×50 mm continuous copper on top layer
- **Recommended:** 70×70 mm if PCB area allows
- **Pour:** GND on top and bottom layer in antenna zone, stitched with vias every 2-3 mm
- **No traces through ground plane area** (no shortcuts, no test points, no silkscreen)
- **Keep-out:** No components (other than the patch antenna itself and its u.FL connector) in the ground plane area

---

## Schematic Sections

### Section 1: Power Input and Battery Management

**Inputs:**
- 5V from USB-C connector on PCB edge (J1)
- 5V from Qi receiver solder pads (P_QI)

**Both inputs feed in parallel** to the TP4056 charger input via OR-ing Schottky diodes (SS14 each) to prevent reverse current flow.

```
USB-C VBUS ──[SS14]──┐
                     ├──► TP4056 VCC pin
Qi 5V output ─[SS14]─┘
```

**TP4056 charger circuit:**

- IC: TP4056 SOP-8
- RPROG resistor (pin 2 to GND): 2.0 KΩ → 580 mA charge current
- CHRG LED (pin 7): red LED + 1KΩ resistor to VCC
- STDBY LED (pin 6): green LED + 1KΩ resistor to VCC
- TEMP pin (1): 10 KΩ resistor to GND (disable thermistor)
- BAT pin (5): connect to LiPo positive terminal via JST PH 2.0 connector
- Decoupling: 10 µF + 100 nF on VCC, 10 µF + 100 nF on BAT

**Battery protection:**
- If using **protected LiPo cell**: no DW01A/8205A on B1 PCB. Cell handles protection.
- If using **unprotected cell**: add DW01A + 8205A protection circuit per Adafruit/Sparkfun reference designs.

**Recommendation for pilot:** Use protected LiPo cells. Simpler B1 PCB, established cell vendors handle protection reliably.

### Section 2: Boost Converter (LiPo → 5V)

**MT3608 boost circuit:**

- IC: MT3608 SOT23-6
- Input: LiPo voltage (3.0-4.2V, direct from TP4056 BAT pin)
- Output: 5.0V regulated
- Inductor: 22 µH, 1A min current, low-DCR (Bourns SRR4528 or equivalent), SMD package
- Schottky diode: SS14 SMA package
- Feedback resistors (set Vout = 5.0V):
  - R_FB1 (top): 100 KΩ (between VOUT and FB)
  - R_FB2 (bottom): 12.4 KΩ (between FB and GND)
  - Vout = 0.6V × (1 + R_FB1/R_FB2) = 0.6 × (1 + 100/12.4) = 5.04V
- Input cap: 22 µF MLCC + 100 nF
- Output cap: 22 µF MLCC + 100 nF
- Enable (EN): driven by **74LVC1G74 Q output** (the Hall-latch state node), not tied to VIN. When the latch is OFF, Q = LOW → MT3608 enters shutdown (< 1 µA quiescent). When the latch is ON, Q = HIGH (≈ LiPo VCC, 3.0–4.2 V) → MT3608 boosts to 5 V. This gates the boost converter on the same toggle that gates the P-MOSFET — the 5 V rail is collapsed when the unit is OFF. EN logic levels: V_IH_min = 1.5 V (easily met by Q = HIGH at 3.0–4.2 V); V_IL_max = 0.4 V (easily met by Q = LOW ≈ 0 V). Without this gating, MT3608's ~1.9 mA quiescent would drain the LiPo in roughly 31 days during off-state storage.

**Output → ESP32 DevKit VIN via Hall-latch-controlled P-MOSFET (Q_PWR), with boost also gated by the latch:**

```
                          74LVC1G74 Q
                              │
                              ├──► MT3608 EN  (boost ON only when latch ON)
                              │
                              └──► 2N3904 base  ──► Q_PWR gate (P-MOSFET ON only when latch ON)

MT3608 VOUT ──[Q_PWR P-MOSFET source-drain]──► ESP32 DevKit VIN pin
                                              ├──► (3.3V regulated inside DevKit)
                                              │
                                              └──► VCC for LC29HEAMD via DevKit 3V3 pin
```

Double-gating: when the latch is OFF, the 5 V rail is collapsed at the boost (EN LOW) **and** the P-MOSFET is held off. Any single-fault leak (e.g., MOSFET Vgs failing to fully reach 0) cannot energize the ESP32 because the rail being switched is also off.

See **Section 10: Hardware Power Switch (Magnetic Toggle Latch)** for the complete latch circuit description.

### Section 3: LC29HEAMD GNSS Section

**Power:**
- VCC (pin TBD per datasheet): 3.3V from ESP32 DevKit 3V3 pin
- Decoupling: 10 µF tantalum + 100 nF + 10 nF in parallel, placed within 5 mm of VCC pin
- V_BCKP (backup): tie to VCC through Schottky diode (SS14 small package)
- GND: connect all GND pins to ground pour, multiple vias

**Reset:**
- RESET_N: 10 KΩ pull-up to VCC
- Optional: route to ESP32 GPIO for software reset (specify GPIO in firmware spec)

**ON_OFF:**
- Tie to VCC through 10 KΩ pull-up (continuous mode, no backup mode)

**Interface selection (D_SEL1, D_SEL2 — 1.8V logic):**
- Both tied to GND through 10 KΩ pull-down resistors
- This selects default UART1 mode
- **Do not tie to VCC** (3.3V would exceed 1.8V tolerance, may damage pin)

**UART1 (3.3V logic, the primary interface):**
- TXD1 → ESP32 GPIO16 (UART2 RX on ESP32)
- RXD1 ← ESP32 GPIO17 (UART2 TX on ESP32)
- **Matches E1 LG290P GPIO assignment** for firmware compatibility

**UART2 (1.8V logic, NOT USED):**
- TXD2, RXD2: leave N/C
- Do not connect to ESP32 without level shifter

**1PPS output:**
- Route to ESP32 **GPIO39** (input-only pin, no strapping issues, wake-capable, ideal for 1PPS)
- Useful for fleet time synchronization and sensor fusion

**LC29HEA Debugging and Firmware Updates:**

The LC29HEA module accepts UART commands (PAIR/PQTM) for configuration and supports firmware updates via Quectel's QGPSFlashTool over UART1 at 921600 baud. Architecture for B1:

| Operation | Frequency | Method | Access |
|-----------|-----------|--------|--------|
| PAIR/PQTM configuration | Every boot | ESP32 firmware sends commands via UART2 | Automatic, no external access needed |
| Manual PAIR/PQTM testing | Development only | ESP32 serial console with "passthrough" debug command | DevKit USB-C (internal, lid open) |
| LC29HEA firmware update | Rare (maybe never) | ESP32 passthrough OR direct UART via test pads | Test pads or DevKit (lid open) |

**Implementation:** Add 4 small SMD test pads near LC29HEA for emergency direct UART access:

- TP1: LC29HEA UART1 TXD (same net as ESP32 GPIO16)
- TP2: LC29HEA UART1 RXD (same net as ESP32 GPIO17)
- TP3: LC29HEA RESET_N (active LOW, drives module into bootloader for firmware download)
- TP4: GND

Test pads are exposed copper on PCB top layer (no through-holes, no soldermask), accessible via SOIC clips or alligator probes when the enclosure lid is open. Costs nothing extra to manufacture.

ESP32 firmware should implement a `gnss_passthrough` debug command:
- Sets ESP32 GPIO16/17 to high-impedance (disables ESP32's UART control)
- Pulls LC29HEA RESET_N low briefly to trigger bootloader
- Bridges USB-C serial bytes ↔ LC29HEA UART1 at 921600 baud
- Allows QGPSFlashTool to drive the LC29HEA directly through the ESP32 DevKit USB-C

For routine sailing operations, none of this is needed — the LC29HEA runs on whatever firmware it shipped with from JLCPCB.

**EXT_INT, WI, RESERVED pins:**
- Leave N/C per datasheet instructions

**Antenna RF section (bias-T circuit):**

Feeds Quectel YFGC007E3A active antenna (3.3 V, 15.5 mA). See **Component Selection → GNSS Antenna** for the detailed datasheet-verified values and rationale; this section gives the schematic-level view.

```
LC29HEAMD VDD_RF ──[L_BIAS 33 nH, 0402]──┬── to u.FL receptacle (J3) center pin
                                          │
                                          ├──[C_BYPASS 10 nF, 0402]── GND (RF bypass)
                                          │
LC29HEAMD RF_IN ──[C_BLOCK 100 pF, 0402]──┘
                  (DC block, passes RF)
```

The bias-T:
- **L_BIAS (33 nH)** blocks RF from VDD_RF — X_L ≈ 326 Ω at L1, 244 Ω at L5 (> 5× line Z₀). The earlier 10 nH value gave only ~100 Ω at L1 and leaked too much RF into the DC path.
- **C_BLOCK (100 pF)** blocks DC from RF_IN — X_C ≈ 1 Ω at L1 (transparent to RF)
- **C_BYPASS (10 nF)** provides RF return path for the LNA bias supply

**Antenna feed point:**
- u.FL female receptacle (J3) on B1 PCB top layer — mates with the IPEX MHF1 plug on the YFGC007E3A's 100 mm cable
- 50 Ω controlled-impedance trace from bias-T junction to J3 center pin
- **Trace length: < 20 mm**
- **No vias on RF trace**
- Continuous GND below the RF trace (no plane splits)

### Section 4: ESP32 DevKit V1 Socket

**Female header positions:**
- 2× 19-pin female headers (38 pins total for DevKit V1)
- Spacing: matches DevKit V1 pin pitch (2.54 mm)
- Center-to-center between rows: 25.4 mm (1.0")

**Pin connections to other B1 sections:**

| ESP32 GPIO | Function | Connects to |
|------------|----------|-------------|
| GPIO16 (U2RX) | LC29HEA TXD1 | GNSS section |
| GPIO17 (U2TX) | LC29HEA RXD1 | GNSS section |
| GPIO21 (SDA) | I2C SDA | BNO085 socket |
| GPIO22 (SCL) | I2C SCL | BNO085 socket |
| GPIO23 (MOSI) | VSPI MOSI | TFT socket |
| GPIO25 (BL) | TFT backlight PWM | TFT socket |
| GPIO18 (CLK) | VSPI CLK | TFT socket |
| GPIO5 (CS) | VSPI CS | TFT socket |
| GPIO2 (DC) | TFT data/cmd | TFT socket |
| GPIO4 (RST) | TFT reset | TFT socket |
| GPIO14 (CLK) | HSPI CLK | microSD |
| GPIO35 (MISO) | HSPI MISO (input-only) | microSD |
| GPIO13 (MOSI) | HSPI MOSI | microSD |
| GPIO27 (CS) | HSPI CS | microSD |
| GPIO34 (ADC1_6) | Battery voltage (input-only) | Battery monitor divider |
| GPIO39 (input-only) | 1PPS input from LC29HEA | GNSS section (input-only, no strapping issues, wake-capable) |
| GPIO33 | D4 Red LED (power/heartbeat) | LED bar (active LOW) |
| GPIO32 | D5 White LED (GPS fix) | LED bar (active LOW) |
| GPIO26 | D6 Cyan LED (SD activity) | LED bar (active LOW) |
| GPIO19 | Hall latch state readback | Read 74LVC1G74 Q output via 10K series + 3.3V clamp diode (or 10K/22K divider) for voltage protection from 4.2V FF output |
| GPIO36 (input-only) | RESERVED for future use | ADC1_0, input-only |
| GPIO15 | RESERVED (strapping pin) | Boot strap pin — avoid using for inputs that may be LOW at boot |
| GPIO0 | Strapping, boot | Reserved |
| GPIO12 | Strapping, MTDI | Reserved (do not use — boot fails if HIGH at boot) |
| VIN (pin) | 5V input | MT3608 VOUT via Q_PWR P-MOSFET (Hall latch) |
| 3V3 (pin) | 3.3V output | LC29HEAMD VCC, BNO085 VIN, pull-ups |
| GND (multiple) | Ground | Ground pour |

**GPIO assignments verified against E1 firmware source `sailframes_e1.ino`:**

E1 v1.1 pin map (correct, from firmware):
- GPS UART2: GPIO16 RX, GPIO17 TX
- I2C: GPIO21 SDA, GPIO22 SCL (BNO085 @ 0x4B, DPS310 @ 0x77)
- TFT VSPI: MOSI=23, SCLK=18, CS=5, DC=2, RST=4, **BL=25** (note: backlight is GPIO25, NOT GPIO19 as previously documented)
- TFT MISO=25 (declared in User_Setup.h but not actually wired or used by firmware)
- SD HSPI: CLK=14, **MISO=35** (input-only pin), MOSI=13, CS=27
- Battery ADC: GPIO34 (input-only)
- **GPIO19 is unused** in E1 v1.1 (header comment was stale) — available for B1 use

B1 GPIO assignments preserve full E1 pin compatibility and add 5 new assignments using previously unused pins.

### Section 5: BNO085 IMU Socket (Optional)

**Female header position:**
- 1× 9-pin female header (matches Adafruit BNO085 STEMMA QT breakout)
- Adjacent to ESP32 socket for short I2C traces

**Connections:**
- VIN → ESP32 3V3
- GND → GND
- 3Vo → N/C (this is the breakout's regulated output, not an input)
- SDA → ESP32 GPIO21 (via 4.7 KΩ pull-up to 3.3V)
- SCL → ESP32 GPIO22 (via 4.7 KΩ pull-up to 3.3V)
- INT → N/C (or ESP32 GPIO if firmware uses interrupts)
- RST → N/C (or ESP32 GPIO if firmware controls reset)
- P0, P1 → defaults via breakout (verify Adafruit breakout silkscreen for I2C @ 0x4A)

**Pull-ups:** 4.7 KΩ on SDA and SCL to 3.3V, mounted on B1 PCB (not relying on breakout pull-ups).

**Mounting orientation:** Match E1 PCB v1.1. Chip label "BNO085" faces up, "VIN" pin nearest the bow direction (as defined by boat-frame in E1 firmware).

### Section 6: TFT Display Socket (Optional)

**Female header position:**
- 2× 8-pin female headers matching Hosyond 3.5" TFT pinout
- Position for vertical TFT mounting via standoffs (25 mm above main PCB)

**Connections:**

| TFT Pin | Function | ESP32 GPIO |
|---------|----------|------------|
| VCC | 5V | MT3608 VOUT (via Q_PWR P-MOSFET, Hall latch) |
| GND | Ground | GND |
| CS | Chip select | GPIO5 |
| RESET | Reset | GPIO4 |
| DC/RS | Data/command | GPIO2 |
| SDI/MOSI | VSPI MOSI | GPIO23 |
| SCK | VSPI CLK | GPIO18 |
| LED | Backlight | **GPIO25** (via current-limiting resistor, ~22 Ω) — matches E1 firmware (`BL=25` in `sailframes_e1.ino`). GPIO19 was a stale header-comment in E1's source and is reassigned in B1 to Hall-latch state readback. |
| SDO/MISO | VSPI MISO | **N/C** — E1 firmware never reads from TFT; declaring this pin in `User_Setup.h` is the legacy behavior but it is not actually wired or used. Leave the breakout's MISO pin unconnected on B1. |
| T_CLK | Touch CLK | N/C (touch not used) |
| T_CS | Touch CS | N/C |
| T_DIN | Touch MOSI | N/C |
| T_DO | Touch MISO | N/C |
| T_IRQ | Touch interrupt | N/C |
| SD_MOSI | SD card MOSI | N/C (NOT USED — use B1 onboard microSD instead) |
| SD_MISO | SD card MISO | N/C |
| SD_SCK | SD card CLK | N/C |
| SD_CS | SD card CS | N/C |

**Note:** TFT has built-in SD slot that we do NOT use. B1 has its own microSD socket on the PCB.

**Standoffs:** 4× M2.5 brass standoffs, 25 mm tall, mount the TFT PCB above the main B1 PCB.

### Section 7: microSD Card Holder

**SMD push-push microSD socket** on B1 PCB (NOT via TFT built-in slot)

- HSPI bus (separate from TFT's VSPI bus)
- **3.3V signaling, no level shifter** (microSD spec accepts 2.7-3.6V)
- 10 KΩ pull-ups on CS, MOSI, MISO, CLK, CD (card detect)
- Decoupling: 10 µF + 100 nF near VCC pin
- Card detect (CD) routed to ESP32 GPIO if used (optional)

**Connections to ESP32:**

| microSD pin | ESP32 GPIO |
|-------------|------------|
| CLK | GPIO14 |
| MOSI | GPIO13 |
| MISO | GPIO35 |
| CS | GPIO27 |
| VCC | 3.3V |
| GND | GND |

**Same as E1 PCB v1.1.**

### Section 8: Battery Monitor

**Voltage divider on LiPo battery:**

- R1: 100 KΩ from BAT+ to GPIO34
- R2: 100 KΩ from GPIO34 to GND
- Divider ratio: 2:1 (4.2V battery → 2.1V at ADC)
- ADC reading × 2 = battery voltage

**Decoupling cap:** 100 nF from GPIO34 to GND (filters ADC noise)

Same as E1 PCB v1.1.

### Section 9: Status Indicators

**6 LEDs arranged as a horizontal bar at the BOTTOM edge of the PCB**, visible through the clear lid of the ML-34F enclosure. All LEDs are high-brightness type (≥1000 mcd) to ensure visibility through polycarbonate lid under sunlight conditions and after weathering.

**LED placement:**

- Single horizontal row along bottom edge of PCB (sailor's side when boat-mounted)
- 15 mm center-to-center spacing between LEDs
- 5 mm from bottom PCB edge
- Coordinates (origin at bottom-left corner of PCB):
  - D1 (Blue/Qi): X=15mm, Y=5mm
  - D2 (Yellow/CHRG): X=30mm, Y=5mm
  - D3 (Green/STDBY): X=45mm, Y=5mm
  - D4 (Red/Power): X=60mm, Y=5mm
  - D5 (White/GPS): X=75mm, Y=5mm
  - D6 (Cyan/SD): X=90mm, Y=5mm

This places the LED bar at the sailor-facing edge when the unit is mounted on the boat, and at the front edge when sitting on the charging dock. All 6 LEDs are simultaneously visible at a glance.

**LED specifications:**

- Package: 0805 SMD (slightly larger than 0603, better light output)
- Brightness: ≥1000 mcd at rated forward current
- Viewing angle: 120° (wide enough to see through ~3mm polycarbonate at any reasonable viewing angle)
- Orientation: Top-emitting (light points up through lid, NOT side-emitting)
- All JLCPCB Basic library parts (no Extended part fees)

| Designator | Color | Function | Driver source | Pattern / behavior |
|------------|-------|----------|---------------|--------------------|
| D1 | Blue | Qi power present | Acxico/Qi receiver +5V via 470Ω + LED to GND | Solid when 5V is present at Qi receiver output (charging pad correctly aligned) |
| D2 | Yellow | Battery charging | TP4056 CHRG pin (open-drain, active-low) via 1KΩ + LED to +5V | Solid when TP4056 is actively charging LiPo |
| D3 | Green | Battery full | TP4056 STDBY pin (open-drain, active-low) via 1KΩ + LED to +5V | Solid when charging complete (LiPo full, on charger) |
| D4 | Red | Power / Heartbeat | ESP32 GPIO via 220Ω + LED to GND | Boot: solid 1s. Running: slow blink 1Hz. Shutdown: 3 fast flashes. Fault: SOS pattern |
| D5 | White | GPS fix | ESP32 GPIO via 220Ω + LED to GND | Off: no fix. Slow blink: 2D/low-quality fix. Fast blink: good 3D + SBAS fix |
| D6 | Cyan | SD activity | ESP32 GPIO via 220Ω + LED to GND | Brief flash on each successful SD write |

**Driver circuit details:**

For LEDs driven from Qi receiver +5V (D1) — common-anode style with LED to GND:

```
Qi receiver +5V ──[R 470Ω]──[LED D1 anode → cathode]── GND
```

Forward current at 5V: (5V - 3.0V LED Vf) / 470Ω = ~4.3 mA. Adequate for 1000 mcd brightness without overdriving.

For LEDs driven from TP4056 open-drain pins (D2, D3) — common-anode style with LED between +5V and TP4056 pin:

```
+5V (Qi receiver output) ──[R 1KΩ]──[LED anode → cathode]── TP4056 pin (sinks to GND when active)
```

This is the configuration shown in the TP4056 datasheet. The LEDs only illuminate when:
- +5V is present (input power available, system on charger)
- TP4056 pin is active-low (charging or charge-complete state)

Forward current: (5V - 3.0V Vf) / 1KΩ = ~2 mA. Lower current than D1 because TP4056 status LEDs don't need to be as bright as the alignment-feedback LED (D1 is the one sailors check at-a-glance).

For ESP32 GPIO-driven LEDs (D4, D5, D6) — common-anode style with GPIO sinking:

```
+3.3V (ESP32 3V3 rail) ──[R 220Ω]──[LED anode → cathode]── ESP32 GPIO
```

GPIO drives LOW to illuminate LED. Forward current: (3.3V - 2.0V Vf for red, ~3.0V for white/cyan) / 220Ω = ~5-6 mA. Good brightness for outdoor visibility.

**Suggested specific parts (verify JLCPCB Basic library at order time):**

| Color | Forward voltage (Vf) | Suggested part family |
|-------|---------------------|----------------------|
| Blue | ~3.0V | Kingbright KP-2012QBC-D (1200 mcd) or equivalent 0805 high-brightness blue |
| Yellow | ~2.0V | Kingbright KP-2012SYC (1000 mcd) or equivalent 0805 high-brightness yellow |
| Green | ~3.0V | Kingbright KP-2012CGCK (1500 mcd) or equivalent 0805 high-brightness pure green |
| Red | ~2.0V | Kingbright KP-2012SRC (1000 mcd) or equivalent 0805 high-brightness red |
| White | ~3.0V | Kingbright KP-2012QWP (1500 mcd) or equivalent 0805 high-brightness white |
| Cyan | ~3.0V | 0805 high-brightness cyan (1000+ mcd) |

**Operational scenarios (what sailor sees):**

| Scenario | LED state |
|----------|-----------|
| Unit on charging dock, properly aligned, battery <80% | Blue ON, Yellow ON, others OFF |
| Unit on charging dock, properly aligned, battery full | Blue ON, Green ON, others OFF |
| Unit on charging dock, MISALIGNED (no Qi power) | All OFF (sailor sees nothing — must reseat) |
| Unit off, removed from dock | All OFF |
| Unit just toggled ON by magnet | Red solid for 1s, then Red slow blink. After ~30s, White starts blinking (GPS searching) |
| Unit running, no GPS fix yet | Red slow blink, White off |
| Unit running, GPS fix with SBAS | Red slow blink, White fast blink, Cyan brief flashes during SD writes |
| Unit running, battery low (<3.4V) | Red triple-blink-pause pattern (warning) |
| Unit toggled OFF by magnet | Red 3 fast flashes, then all off |
| System fault | Red SOS pattern (··· ─── ···) |

**Buoy variant (no TFT populated):**

All 6 LEDs serve the same functions. Without the TFT, the LED behaviors become the primary status interface for unattended buoy operation. No additional LEDs required — D4 (Red) blink patterns convey all necessary state.

**Visibility verification (pilot test):**

- View LEDs through ML-34F clear lid at 1m distance in direct sunlight: each LED must be clearly distinguishable
- View at 3m distance in overcast conditions: each LED must be visible if not necessarily distinguishable by color
- Pattern recognition: verify red LED blink patterns are distinguishable at 1m distance

### Section 10: Hardware Power Switch (Magnetic Toggle Latch)

This section provides the schematic-level detail. See the high-level architecture section earlier in this document ("Hardware Power Switch (Magnetic Toggle Latch)") for the full UX and component rationale.

**Schematic implementation:**

```
LiPo (3.0-4.2V) ──┬──→ DRV5032AJ VCC (pin 1)
                  │    DRV5032AJ GND (pin 3) ── GND
                  │    DRV5032AJ OUT (pin 2) ──┐
                  │                            │
                  └──→ 74LVC1G74 VCC (pin 8)   │
                       74LVC1G74 GND (pin 5)   │
                       74LVC1G74 /PRE (pin 1) ── tied to VCC (never preset)
                                                 │
   [DRV5032 OUT] ──┬──[R_DBNC 10K]──┬──→ 74LVC1G74 CLK (pin 3)
                   │                │
                   └──[C_DBNC 100nF]┘── GND
                       (forms ~1ms debounce filter)
   
   74LVC1G74 D (pin 2) ──── tied to /Q (pin 6)  ← toggle configuration
   74LVC1G74 Q (pin 7) ────┬→ NPN level shifter → Q_PWR gate (see below)
                            └→ MT3608 EN (boost runs only when latch ON)

   Voltage supervisor on /CLR (pin 4) — replaces RC POR:
     LiPo VCC ──→ U_RST VCC pin
     GND      ──→ U_RST GND pin
     U_RST /RESET (active LOW push-pull) ──→ 74LVC1G74 /CLR (pin 4)

   Suggested part: MAX809T-T (3.08 V threshold, 240 ms reset timeout, SOT-23-3),
   or pin-compatible equivalent (TLV803S, APX803-30, MCP130-300, STM6315 family).

   U_RST behavior:
     VCC < 3.08 V → /RESET LOW → /CLR LOW → forces Q = LOW (MT3608 OFF + MOSFET OFF)
     VCC crosses 3.08 V → /RESET held LOW for 240 ms reset timeout (regardless of ramp speed)
     After 240 ms timeout → /RESET HIGH → /CLR released → FF responds to CLK normally
     If VCC drops back below 3.08 V (e.g. brownout) → /RESET re-asserts immediately → safe OFF

   Why a supervisor IC, not an RC network:
     During depletion recovery the protected cell ramps slowly (minutes) via TP4056
     trickle charge through the protection FET body diode. An RC POR (R+C on /CLR)
     tracks a slow VCC ramp nearly in lockstep and fails to assert clear, leaving the
     FF in an undefined state on power-up. A 50/50 chance the unit auto-wakes mid-
     charge and the ESP32 then steals charging current, preventing full recovery.
     The supervisor's defined V_TH + fixed timeout is independent of ramp speed.

   NPN level shifter (translates 74LVC1G74 Q to MOSFET gate):
     74LVC1G74 Q ──[R_BASE 10K]── 2N3904 base
                                      │
                                      ├── 2N3904 emitter → GND
                                      │
                                      └── 2N3904 collector ──[R_PULLUP 100K]── +5V
                                                                │
                                                                └── Q_PWR gate
   
   MT3608 VOUT (5V) ──[Q_PWR AO3401A P-MOSFET source-drain]──→ ESP32 DevKit VIN
   
   Logic table:
     Q = HIGH → MT3608 EN HIGH → 5 V rail energised
              + NPN ON → MOSFET gate ~0 V → Vgs ≈ -5 V → P-MOSFET ON → ESP32 powered
     Q = LOW  → MT3608 EN LOW  → 5 V rail collapsed (boost in shutdown <1 µA)
              + NPN OFF → MOSFET gate = (the now-0 V rail) via R_PULLUP → MOSFET OFF
              → ESP32 receives 0 V from both ends (rail off AND switch off)
```

**Component placement:**

- DRV5032AJ: RIGHT edge of PCB at (X=102.7mm, Y=40mm), oriented for X-axis magnetic sensitivity
- 74LVC1G74: Within 10mm of DRV5032AJ (short CLK trace, low noise)
- U_RST supervisor: Adjacent to 74LVC1G74 /CLR pin (pin 4), trace under 5 mm to keep the reset line clean
- 2N3904 NPN level shifter: Between 74LVC1G74 and Q_PWR, traces under 20mm to minimize switching transients
- Q_PWR (AO3401A): In POWER ZONE near MT3608 output
- MT3608 EN trace: routed from 74LVC1G74 Q output to MT3608 EN pin, keep under 30 mm; this is the second leg of the latch's double-gating
- Debounce R/C: Between DRV5032AJ and 74LVC1G74, on a clean ground

**Enclosure marker for users:**

- External silkscreen or sticker on right wall of enclosure
- 12mm diameter circle marker
- Aligned with DRV5032AJ position inside
- Recommended marker text: "ON/OFF" or magnet icon

### Section 11: USB-C Connector (Internal Access Only)

**Architecture decision: NO separate USB-C on B1 PCB. Use ESP32 DevKit V1's onboard USB-C only, for internal-only access.**

The ESP32 DevKit V1 has its own USB-C port on the dev board. This is used for:

- Initial firmware flash during factory provisioning
- Bring-up testing and serial console diagnostics
- Emergency firmware recovery if OTA fails

**Access procedure (internal only):**

1. Remove 4 lid screws (no glue, no permanent seal — gasket reseals on closure)
2. Lift clear lid carefully (TFT module may attach to lid via standoffs or remain on main PCB; verify before lifting). Note: Qi receiver is on the enclosure BASE, not the lid, so opening the lid does not disturb the Qi module.
3. ESP32 DevKit V1 USB-C is now accessible inside the enclosure
4. Plug USB-C cable from computer to DevKit
5. After service, reseal lid with 4 screws — gasket compresses against enclosure rim

**Important: DevKit orientation on PCB**

The DevKit must be oriented with its USB-C port pointing INWARD (toward PCB center), not outward (toward the enclosure wall). This way:

- USB-C cable can be plugged in while lid is open
- USB-C cable doesn't hit the enclosure wall during use
- No need for an enclosure wall opening (preserves sealed enclosure mandate)

**Power input via USB-C (when DevKit is connected):**

- VBUS (5V) from DevKit's USB-C → TP4056 input via OR-ing Schottky diode (SS14)
- Same TP4056 input as Qi receiver 5V output (parallel feed)
- Allows USB-charging during development without removing the unit from charging pad

**No separate USB-C on B1 PCB:**

- Pros: Simpler PCB, fewer components, no second USB-C connector to seal
- Cons: B1 cannot accept USB charging when DevKit is not installed (rare scenario for production units)

**Production firmware update workflow:**

Normal operation NEVER requires opening the enclosure:

1. Pre-race / post-race: WiFi associates with dock router
2. ESP32 checks S3 bucket for new firmware version (s3://sailframes-fleet-data-prod/firmware/E1/current/firmware.bin)
3. If newer version available, OTA update downloads and flashes (same mechanism as E1)
4. ESP32 reboots to new firmware
5. Verification: First successful S3 upload after reboot confirms firmware works
6. Rollback: If 3 consecutive boots fail to upload, automatic rollback to previous firmware in OTA partition

---

## BOM (Pilot Order, Qty 5 boards)

JLCPCB PCBA service. Use Standard PCBA tier (not Economic) for LC29HEAMD reliability.

| Designator | Part | LCSC # | Qty (per board) | Notes |
|------------|------|--------|-----------------|-------|
| U1 | LC29HEAMD | C28453488 | 1 | JLCPCB-stocked Extended part |
| U2 | TP4056 | C16581 | 1 | LiPo charger |
| U3 | MT3608 | C47764 | 1 | Boost converter |
| U4 | **YFGC007E3A** (Quectel active L1/L5 antenna) | **DigiKey 2958-YFGC007E3A-ND** | 1 | **NOT on PCBA — externally sourced from DigiKey, hand-installed during final assembly.** ~$14.12 each at qty 20. 4 buckle pins into B1 PCB; 100 mm IPEX cable mates with u.FL J3. See Component Selection → GNSS Antenna for full spec. PCB provides 50×50 mm GND fill + 4× ⌀1.3 mm plated thru-holes at 37×37 mm centers. |
| U_HALL | DRV5032AJ | C606060 | 1 | Hall sensor, ±2.5 mT, 1.3 µA quiescent (RIGHT side of PCB) |
| U_FF | 74LVC1G74 | TBD | 1 | Single D flip-flop SOT-23-8 with async PRE/CLR (toggle config) |
| Q_INV | 2N3904 NPN | C20526 | 1 | Level shifter for MOSFET gate (3.3V FF output → 5V gate swing) |
| Q_PWR | AO3401A | C15127 | 1 | P-channel MOSFET, latch-controlled 5V switch |
| U_RST | MAX809T-T (or equiv) | LCSC TBD | 1 | Voltage supervisor on 74LVC1G74 /CLR, 3.08 V threshold, 240 ms reset timeout, SOT-23-3 push-pull active-LOW. Equivalents: TLV803S, APX803-30, MCP130-300, STM6315 family |
| L1 | 22 µH inductor 1A | TBD | 1 | Bourns SRR4528 or equiv |
| L_BIAS | **33 nH** inductor 0402 | TBD | 1 | Antenna bias-T RF choke (X_L ≈ 326 Ω at L1, 244 Ω at L5 — bumped up from 10 nH in v0.8 which was too low) |
| D1 | Blue 0805 LED, ≥1000 mcd | TBD | 1 | **Qi power-present indicator** (driven by Qi receiver +5 V via 470 Ω). Bottom edge of PCB |
| D2 | Yellow 0805 LED, ≥1000 mcd | TBD | 1 | **TP4056 CHRG indicator** (driven by TP4056 CHRG open-drain via 1 KΩ to +5 V). Bottom edge of PCB |
| D3 | Green 0805 LED, ≥1000 mcd | TBD | 1 | **TP4056 STDBY indicator** (driven by TP4056 STDBY open-drain via 1 KΩ to +5 V). Bottom edge of PCB |
| D4 | Red 0805 LED, ≥1000 mcd | TBD | 1 | **ESP32 power/heartbeat** (driven by ESP32 GPIO33, active LOW, via 220 Ω). Bottom edge of PCB |
| D5 | White 0805 LED, ≥1000 mcd | TBD | 1 | **ESP32 GPS-fix indicator** (driven by ESP32 GPIO32, active LOW, via 220 Ω). Bottom edge of PCB |
| D6 | Cyan 0805 LED, ≥1000 mcd | TBD | 1 | **ESP32 SD-activity indicator** (driven by ESP32 GPIO26, active LOW, via 220 Ω). Bottom edge of PCB |
| D7 | SS14 Schottky SMA | C2480 | 1 | USB-C VBUS → TP4056 input OR-ing diode |
| D8 | SS14 Schottky SMA | C2480 | 1 | Qi 5 V → TP4056 input OR-ing diode |
| D9 | SS14 Schottky SMA | C2480 | 1 | MT3608 boost converter Schottky |
| D10 | SS14 Schottky SMA (small package) | C2480 | 1 | LC29HEAMD V_BCKP backup diode |
| C1-C10 | Decoupling caps | various | 10 | 10 µF + 100 nF combos |
| C_DBNC | 100 nF 0603 | various | 1 | Hall sensor debounce cap |
| C_BLOCK | 100 pF 0402 | various | 1 | Antenna bias-T DC block on RF_IN (X_C ≈ 1 Ω at L1, transparent) |
| C_BYPASS | 10 nF 0402 | various | 1 | Antenna bias-T RF bypass on 3.3 V leg of L_BIAS |
| R1-R10 | Pull-ups, dividers | various | 10 | 0603 resistors |
| R_DBNC | 10 KΩ 0603 | various | 1 | Hall sensor debounce resistor |
| R_BASE | 10 KΩ 0603 | various | 1 | 2N3904 base resistor |
| R_PULLUP | 100 KΩ 0603 | various | 1 | NPN collector pullup to 5V (controls MOSFET gate) |
| J2 | JST PH 2.0 battery | C144394 | 1 | LiPo connector |
| J3 | u.FL receptacle | C108061 | 1 | For YFGC007E3A antenna's IPEX MHF1 plug (100 mm cable) |
| J_ANT_MNT | 4× plated thru-hole, ⌀1.3 mm | n/a | 4 (1 set) | YFGC007E3A buckle-pin mounting holes at 37 × 37 mm centers, within 50 × 50 mm GND fill |
| J5 | microSD push-push socket | C160390 | 1 | Internal access only (no enclosure cutout) |
| TP1-TP4 | Test pads for LC29HEA debug | n/a | 4 | Exposed copper pads on PCB top layer (TXD, RXD, RESET_N, GND); no through-holes |
| J_QI | Qi receiver solder pads (2-pad) | n/a | 1 | Solder pads on B1 PCB top layer for wires from Qi module on enclosure base |
| J6-J7 | ESP32 DevKit headers | various | 2× 19-pin female | DevKit oriented USB-C INWARD |
| J8 | BNO085 breakout header | various | 9-pin female | LEFT side of PCB |
| J9-J10 | TFT display headers | various | 2× 8-pin female | TFT stacker, optional populate |

**Components NOT on PCB (supplied separately for assembly):**

- **Quectel YFGC007E3A active L1/L5 GNSS antenna** (DigiKey 2958-YFGC007E3A-ND, $14.12 @ qty 20) — hand-installed during final assembly (4 buckle pins + IPEX cable plug onto u.FL J3). See Component Selection → GNSS Antenna for full procurement and assembly notes.
- ESP32 DevKit V1 board (~$5-8 each) — socketed, USB-C oriented inward
- BNO085 Adafruit breakout (~$25 each) — pilot only, populate per unit, LEFT side
- Hosyond 3.5" TFT module (~$18 each) — pilot only, populate per unit, stacker headers
- LiPo battery **503562 protected, 5 × 35 × 62 mm, 1500 mAh** (~$10–15 each, AliExpress / Adafruit-class), JST PH 2.0 connector. Fallback: 503450 (5 × 34 × 50 mm, 1000 mAh) if 503562 unavailable.
- Qi receiver module 5W (~$1-5 each, Acxico-class or equivalent) — taped to inside of enclosure BASE with double-sided adhesive, wires soldered to J_QI pads on B1 PCB
- M2.5 brass standoffs for TFT (set of 4, ~$3)
- M3 stainless screws for enclosure (4× per unit)
- 10mm × 3mm N52 disc magnets (~$0.30 each) — 5-10 for fleet operations (single magnet shared by race organizer)

**Estimated cost per pilot board fully assembled with all peripherals: ~$145-175** (was ~$130-160 in v0.8 — antenna cost moved from "free as part of PCBA" to "$14 from DigiKey")

---

## Verification Checklist (Before Ordering PCBA)

Claude Code: verify all of the following before submitting PCBA order:

- [ ] LC29HEAMD footprint matches JLCPCB C28453488 (use JLC2KiCadLib generated footprint, do NOT hand-create)
- [ ] LC29HEAMD pin assignments verified against Quectel LC29H Series Hardware Design V1.3
- [ ] PCB outline matches Polycase ML-34BF-PCB template (104.7×79.3 mm with corner cutouts)
- [ ] Mounting holes at 85×50 mm spacing, 3.18 mm clearance for 6-32 screws
- [ ] Antenna ground plane ≥50×50 mm continuous copper, no traces through
- [ ] RF trace from bias-T to antenna feed <20 mm, 50Ω controlled impedance, no vias
- [ ] TFT and microSD on separate SPI buses (VSPI vs HSPI) — verified in net assignments
- [ ] All RESERVED/WI pins on LC29HEAMD left N/C
- [ ] D_SEL1, D_SEL2 pulled to GND (not VCC — they're 1.8V tolerant only)
- [ ] UART2 on LC29HEAMD left N/C (1.8V logic, no level shifter)
- [ ] BNO085 mounting orientation matches E1 PCB v1.1
- [ ] GPIO assignments match E1 PCB v1.1 for firmware compatibility
- [ ] **MT3608 EN net connects to 74LVC1G74 Q output, NOT to VIN.** (Verify net name on EN pin = same net driving Q_INV base.) An always-on MT3608 burns ~1.9 mA continuously and breaks off-season storage.
- [ ] **U_RST voltage supervisor placed on 74LVC1G74 /CLR.** Threshold = 3.08 V (T-suffix), output is push-pull active-LOW. Confirm no R_POR / C_POR RC network on /CLR (would defeat the supervisor).
- [ ] **L_BIAS antenna RF choke = 33 nH, NOT 10 nH.** (10 nH gives only ~100 Ω at L1 and leaks RF into the DC bias path.)
- [ ] **TFT backlight on GPIO25** (matches E1 firmware `BL=25`), NOT GPIO19. GPIO19 is reserved for Hall-latch state readback.
- [ ] **TFT MISO (SDO) pin left N/C** — E1 firmware never reads from TFT.
- [ ] **YFGC007E3A buckle-mount provisions on PCB:** 4× plated thru-holes at ⌀1.3 mm, 37 ± 0.2 mm × 37 ± 0.2 mm centers; 50 × 50 mm continuous GND fill (top + bottom layer, via-stitched) under antenna; 15 mm component keep-out around antenna outline.
- [ ] **u.FL receptacle (J3) within ~80 mm of antenna's cable exit point** so the 100 mm IPEX cable can route without strain or tight bends.
- [ ] **Antenna NOT placed by JLCPCB PCBA** — verify the BOM/CPL submitted to JLCPCB excludes U4 (YFGC007E3A); the antenna is hand-installed during final B1 assembly.
- [ ] **74LVC1G74 SOT-23-8 pin numbers verified against actual LCSC part's manufacturer datasheet** — pin numbers in this document's schematic blocks are illustrative; do NOT copy them blindly into the KiCad symbol.
- [ ] **Designator scheme**: D1–D6 are the six status LEDs (Blue/Yellow/Green/Red/White/Cyan); D7/D8/D9/D10 are the four SS14 Schottkys (USB OR-ing, Qi OR-ing, MT3608 boost, LC29HEA V_BCKP). No designator collisions between LEDs and diodes.
- [ ] DRC (Design Rules Check) passes with no errors
- [ ] ERC (Electrical Rules Check) passes with no errors
- [ ] No unconnected critical pins (RESET_N, ON_OFF, V_BCKP, VCC all explicitly handled)
- [ ] All passive components have JLCPCB Basic library parts where possible (minimize Extended part fees)
- [ ] BOM matches JLCPCB CPL format requirements
- [ ] Gerbers exported per JLCPCB specifications

---

## Pilot Test Plan (Before Ordering 30 Production Units)

### Bring-up (Day 1)

1. Visual inspection of all 5 boards (soldering quality, no shorts)
2. **Off-state quiescent current** (with battery connected, latch OFF, not on charger): insert a µA meter in series with the LiPo. Expect ≤ 100 µA total (target ~80 µA: U_RST ~12 µA + Hall ~1.3 µA + FF ~0.1 µA + battery-monitor divider ~20 µA + LiPo self-discharge). **A reading >500 µA means MT3608 is not actually gated by the latch** — almost certainly EN tied to VIN by accident. Do not proceed until resolved; this is the canary for fix v0.8 #1.
3. **Latch toggle reliability**: with battery connected, swipe a 10 mm × 3 mm N52 magnet past the marked spot on the right wall ≥ 100 times. Each swipe must produce exactly one ON↔OFF transition (verify by watching D4 Red and measuring 5 V rail). Confirms debounce values and U_RST threshold are sane.
4. **Depletion-recovery cold start**: drain a cell to ~2.5 V (protection trip), then place unit on Qi pad. Verify the unit charges silently — D1 Blue + D2 Yellow ON, D4 Red OFF (ESP32 stays off through the entire recovery), until cell reaches full. This is the canary for fix v0.8 #2 — if D4 lights mid-charge or the cell never reaches full, U_RST is not holding /CLR through the trickle ramp.
5. **Hand-install the YFGC007E3A antenna** (per assembly procedure in Component Selection → GNSS Antenna): snap 4 buckle pins into PCB mounting holes, route 100 mm IPEX cable, snap onto u.FL receptacle J3 with audible click.
6. Power-on each board with the magnet, verify:
   - 5V rail from MT3608 (measure with multimeter, expect 4.95-5.05V)
   - 3.3V from ESP32 DevKit (expect 3.25-3.35V)
   - LC29HEAMD VCC stable (measure pin)
   - **Antenna bias current**: measure DC current on the 3.3 V trace feeding L_BIAS to the u.FL. Expect **~15.5 mA** (datasheet typ). **Zero current = LNA dead** (bad solder on u.FL, damaged antenna, or bias-T component error). **> 25 mA = wrong part, damaged antenna, or short.** This is the canary that the YFGC007E3A chain works before relying on satellite tracking.
   - TP4056 CHRG LED indicates correct state
7. Flash ESP32 with bring-up test firmware
8. Verify UART communication with LC29HEAMD
9. Verify SD card mounts and writes
10. Verify BNO085 detected on I2C (if populated)
11. Verify TFT initializes and displays test pattern (if populated)
12. **Quick GNSS check**: with the unit on a sky-visible windowsill, log NMEA `$GxGSV` sentences for 5 minutes. Verify at least 6 satellites tracked with C/N0 > 30 dB-Hz across both L1 (`L1CA` IDs) and L5 (`L5` IDs) bands. Failure of L5 satellites to appear while L1 works = check that LC29HEAMD's L5 path is enabled in firmware (PAIR command), and that the antenna's IPEX cable is fully seated.

### Indoor static test (Days 2-3)

1. Set one B1 board next to an existing E1 unit on window sill (controlled environment)
2. Log NMEA from both for 1 hour each day
3. Compare:
   - Satellite count (expect LC29HEA to see ~half of LG290P due to L1/L5 vs L1/L2/L5)
   - C/N0 distribution
   - Position uncertainty from $GST messages
   - Time-to-first-fix on cold start

### Outdoor static test (Days 4-5)

1. Deploy one B1 board outside in open sky for 24 hours
2. Log raw NMEA continuously
3. Compute CEP from sample variance
4. Compare to E1 in same location

### Sailing pilot (Days 6-10)

1. Mount one B1 prototype next to one E1 on the same boat
2. Sail 2-3 race days (real conditions)
3. Compare:
   - Track quality during maneuvers (tacks, gybes, mark roundings)
   - Fix retention in rigging shadow
   - Heading accuracy from BNO085 (should be identical if mounted correctly)
   - SD logging reliability
   - TFT operation under boat motion
   - Battery life with B1 1500 mAh vs E1 6000 mAh

### Decision criteria (Day 11)

- LC29HEA horizontal accuracy within 2× of LG290P → COMMIT B1 fleet
- LC29HEA satellite count adequate for fix retention (≥10 sats sailing, ≥8 sats in rigging shadow) → COMMIT
- BNO085 heading consistency identical to E1 → COMMIT
- Significant degradation in any of the above → REASSESS

### If pilot succeeds: Production order (Day 12+)

- Order 30 B1 units via JLCPCB PCBA Standard tier
- Order 30 Polycase ML-34F\*1508 enclosures from polycase.com
- Order 30 BNO085 breakouts (or omit for buoys), 30 antennas, 30 LiPos, 30 Qi receivers
- Expected production cost per unit: ~$120-140 fully assembled

---

## Open Questions for Resolution Before Final Design

These should be resolved before Claude Code generates the final KiCad files:

~~1. PCB mounting boss height in ML-34F~~ **RESOLVED 2026-05-18: 5 mm (measured on Polycase sample with calipers). Forces LiPo change to 503562 (5 mm thick) per v0.10.** All open questions now closed.

**Resolved decisions (no further discussion):**

- ✓ ML-34F enclosure wall thicknesses verified from datasheet (drawing C, REV 1, 6/11/2020):
  - **Base wall typical: 0.125" = 3.18 mm**
  - **Clear lid (ML-34C\*08) top surface typical: 0.130" = 3.30 mm**
  - Base is slightly thinner than lid — Qi-through-base architecture validated by existing bench test (Acxico through E1 enclosure of comparable thickness gave 5.13V stable)
- ✓ **GPIO assignments verified against E1 firmware source `sailframes_e1.ino` (2026-05-17):**
  - 1PPS input from LC29HEA: **GPIO39** (input-only, no strapping issues, wake-capable)
  - D5 Red LED (power/heartbeat): **GPIO33**
  - D6 White LED (GPS fix): **GPIO32**
  - D7 Cyan LED (SD activity): **GPIO26**
  - Hall latch state readback: **GPIO19** (clean GPIO, requires voltage protection from FF Q output up to 4.2V)
- ✓ **LC29HEA debug/programming strategy (2026-05-17):** No external USB connection needed during routine operation. ESP32 firmware sends all PAIR/PQTM configuration via UART2 every boot. For development debugging, ESP32 implements `gnss_passthrough` command bridging USB-C ↔ LC29HEA UART1 at 921600 baud (accessed by opening lid). 4 SMD test pads on B1 PCB top layer (TXD/RXD/RESET_N/GND) provide emergency direct UART access for QGPSFlashTool if ESP32 passthrough fails. LC29HEA firmware updates are rare and don't require routine field access.
- ✓ GNSS antenna: **Quectel YFGC007E3A** (active GNSS L1+L5, 17 ± 3 dB LNA, NF ≤ 2.5 dB, RHCP, 50 × 50 × 14.5 mm, 4 buckle pins at 37 mm centers, 100 mm IPEX MHF1 cable). Sourced from DigiKey (P/N 2958-YFGC007E3A-ND, ~$14.12 @ qty 20). **NOT placed by JLCPCB PCBA** — hand-installed during final assembly (snap pins into PCB, plug IPEX into u.FL receptacle J3). 20 units ordered 2026-05-18 (return window through ~2026-07-17). Earlier "YCGA014AA" in v0.1–v0.8 was a fabricated transcription that does not exist in JLCPCB's library; YFGC007E3A is the actual Quectel part the spec was attempting to describe.
- ✓ Antenna bias-T: L_BIAS = **33 nH** 0402 (NOT 10 nH), C_BLOCK = 100 pF 0402 DC block on RF_IN, C_BYPASS = 10 nF 0402 RF bypass on the 3.3 V leg. 10 nH gave only ~100 Ω at L1 and leaked RF into DC path; 33 nH gives 326 Ω at L1, 244 Ω at L5.
- ✓ TFT backlight on **GPIO25** (matches E1 firmware), TFT MISO left N/C. GPIO19 is reserved for Hall-latch state readback.
- ✓ Reference-designator scheme: D1–D6 = the six status LEDs (Blue/Yellow/Green/Red/White/Cyan from left to right on bottom edge); D7/D8/D9/D10 = SS14 Schottkys (USB OR-ing, Qi OR-ing, MT3608 boost, LC29HEA V_BCKP). LED D4–D6 are driven by ESP32 GPIO33/32/26 respectively (active-LOW).
- ✓ GNSS receiver: Quectel LC29HEAMD (JLCPCB C28453488)
- ✓ Power switch sensor: **DRV5032AJ** Hall sensor (±2.5 mT, standard sensitivity), LCSC C606060
- ✓ Power switch flip-flop: **74LVC1G74** (SOT-23-8, with async PRE and CLR pins) — NOT 74LVC1G79 (no async preset)
- ✓ Power-on reset: **MAX809T-T voltage supervisor IC** (or pin-compatible equivalent: TLV803S, APX803-30, MCP130-300, STM6315) on /CLR, 3.08 V threshold, 240 ms reset timeout, SOT-23-3. Replaces RC POR (100KΩ + 1µF) which was unreliable on slow VCC ramps during depletion-recovery trickle-charging. /PRE tied to VCC (never preset).
- ✓ **MT3608 EN gated by 74LVC1G74 Q output** (not tied always-on to VIN). When latch OFF, boost is in shutdown (<1 µA quiescent). This double-gates the 5 V → ESP32 path (boost OFF AND P-MOSFET OFF) and is what makes off-season storage viable — always-on MT3608 quiescent would have depleted the LiPo in ~31 days.
- ✓ MOSFET gate driver: **2N3904 NPN inverter** + 100KΩ pull-up to 5V (provides 0V/5V gate swing to fully turn off AO3401A P-MOSFET). 74LVC1G74 alone cannot swing high enough to fully turn off P-MOSFET since FF VCC = LiPo voltage (3.0-4.2V) < 5V source.
- ✓ Power switch MOSFET: AO3401A P-channel (LCSC C15127), 4A continuous, 30V Vds
- ✓ USB-C: Internal only (DevKit's onboard USB-C, oriented inward, accessed by opening lid)
- ✓ Enclosure: Polycase ML-34F\*1508 with no holes
- ✓ microSD: Internal only, no enclosure cutout
- ✓ Charging: Qi only — Acxico-class 5W receiver module, mounted on inside of enclosure BASE (opposite clear lid). Coil and PCB body taped to base with double-sided adhesive. Validated via bench test 2026-05-16.
- ✓ LiPo battery: **503562 protected cell** (5 × 35 × 62 mm, 1500 mAh, JST PH 2.0). Changed from 803450 (8 mm thick) in v0.10 because the measured 5 mm boss height leaves only 5 mm below-PCB clearance. Protected cell means NO DW01A+8205A on B1 PCB. Fallback if 503562 unavailable: 503450 (5 × 34 × 50 mm, 1000 mAh, also protected).
- ✓ **PCB mounting boss height in ML-34F = 5 mm** (measured 2026-05-18 with calipers on Polycase sample). This forces the LiPo change above; below-PCB layout has LiPo + Qi coil side-by-side (not stacked) on the enclosure base floor; Qi receiver PCB body relocates to B1 PCB top side.
- ✓ Firmware update: WiFi OTA from S3 (no USB-C access during normal operation)
- ✓ Data offload: WiFi to S3 (no SD card removal during normal operation)
- ✓ BNO085 placement: LEFT side of PCB (matches E1 v1.1 orientation)
- ✓ Hall sensor placement: RIGHT side of PCB, middle height (X≈102.7mm, Y≈40mm)
- ✓ Status LEDs: 6-LED bar at BOTTOM edge of PCB, 0805 high-brightness ≥1000 mcd, sailor-facing (D2-D7)

---

## Document History

- v0.1 (2026-05-15): Initial draft for pilot order. Based on E1 PCB v1.1 with LC29HEAMD swap, integrated power section, internal antenna, Polycase ML-34F enclosure.
- v0.2 (2026-05-16): Antenna selection finalized (Quectel YCGA014AA, JLCPCB-stocked). Sealed enclosure mandate: NO HOLES in any wall. Power switch redesigned as Hall sensor + flip-flop toggle latch (RIGHT side, magnetic activation). USB-C is DevKit-only with internal-only access (oriented inward, lid removal for development). Firmware update via WiFi OTA. SD card internal-only.
- v0.3 (2026-05-16): Qi charging chain validated by bench test (Acxico receiver + W9/Calypso pad through E1 enclosure wall, 5.13V stable, ESP32 boots cleanly on Qi-only power). Status indicator LEDs finalized: 6-LED bar at BOTTOM edge of PCB (Blue/Yellow/Green/Red/White/Cyan), 0805 high-brightness ≥1000 mcd, with driver schemes specified for each. LED operational scenarios documented for charging dock and racing modes.
- v0.4 (2026-05-17): Group 1+2+3 open questions resolved. Qi receiver finalized as Acxico-class 5W module mounted on inside of enclosure BASE (opposite clear lid), wires to J_QI pads on B1 PCB. LiPo finalized: 803450 protected cell (1500 mAh). Power latch architecture finalized: DRV5032AJ Hall + 74LVC1G74 flip-flop (with async PRE/CLR) + 2N3904 NPN level shifter + AO3401A P-MOSFET. POR network (100KΩ + 1µF on /CLR) guarantees safe OFF default. GPIO assignments proposed for 1PPS (GPIO15), D5/D6/D7 LEDs (GPIO33/32/26), Hall readback (GPIO36). Stack-up budget updated to include Qi module under LiPo at base of enclosure. All architectural decisions now locked for KiCad implementation.
- v0.5 (2026-05-17): ML-34F enclosure dimensions and wall thicknesses verified from Polycase datasheet (drawing C, rev 1, 6/11/2020): base wall 3.18 mm, clear lid 3.30 mm, base interior depth 38.1 mm. Qi-through-base architecture confirmed by verified base wall thickness equivalent to E1 bench-test wall. PCB outline confirmed: 104.7 × 79.3 mm with R=9.6 mm corner cutouts. Mounting holes: 0.165" (4.19 mm) at 85 × 50 mm spacing. PCB mounting boss height flagged as TBD pending physical measurement of ML-34F sample — affects below-PCB clearance for LiPo + Qi module. Stack-up section updated with contingency layouts based on actual boss height.
- v0.6 (2026-05-17): GPIO assignments verified against E1 firmware source `sailframes_e1.ino`. Discovered firmware actually uses GPIO25 for TFT backlight (not GPIO19 as previously documented in memory) — GPIO19 is unused in E1 and now assigned to Hall latch readback for B1. 1PPS reassigned from GPIO15 (strapping pin, boot risk) to GPIO39 (input-only, no boot issues). All B1 GPIO assignments confirmed: 1PPS=39, D5=33, D6=32, D7=26, Hall readback=19. Only remaining open question is PCB boss height (measurement coming 2026-05-18).
- v0.7 (2026-05-17): LC29HEA debug/programming strategy added. No external USB during routine operation — ESP32 sends all PAIR/PQTM commands via UART2 every boot (same model as E1 with LG290P). For development debugging and rare firmware updates: ESP32 implements `gnss_passthrough` debug command bridging DevKit USB-C ↔ LC29HEA UART1 at 921600 baud, accessed by opening lid. 4 SMD test pads (TXD/RXD/RESET_N/GND) added to BOM for emergency direct QGPSFlashTool access. Sealed enclosure mandate preserved.
- v0.8 (2026-05-18): Two fixes addressing the depletion-and-recharge scenario, both required for the sealed-enclosure architecture to actually deliver multi-month off-season storage. (1) **MT3608 EN re-routed from "always-on tied to VIN" to the 74LVC1G74 Q output.** Boost converter now shuts down (<1 µA) when the latch is OFF, instead of burning ~1.9 mA continuously. The previous design depleted the 1500 mAh cell in ~31 days from full — incompatible with the claimed 2.6-year storage life. Net effect: the 5 V → ESP32 path is now double-gated (boost EN + P-MOSFET) by the same latch node. (2) **RC POR network (R_POR 100 KΩ + C_POR 1 µF on /CLR) replaced with U_RST voltage supervisor IC** (MAX809T-T or equivalent: TLV803S, APX803-30, MCP130-300, STM6315 family). 3.08 V threshold, 240 ms reset timeout, SOT-23-3 push-pull active-LOW. The RC POR was unreliable on slow VCC ramps that occur during trickle-charge recovery of a depleted protected cell (multi-minute ramp through the protection-FET body diode) — could leave the FF in an undefined state and cause the unit to wake mid-charge and steal charging current. The supervisor's threshold-and-timeout behavior is independent of ramp speed. Off-state drain rises from claimed ~65 µA to actual ~80 µA (includes U_RST ~12 µA + battery-monitor divider ~20 µA + LiPo self-discharge ~30–60 µA), still yielding ~2.1-year off-season storage from full. BOM: removed R_POR + C_POR, added U_RST.
- v0.9 (2026-05-18): GNSS antenna locked + accumulated v0.8-era cleanups landed. **(1) Antenna swap**: replaced fabricated "YCGA014AA" with the real Quectel **YFGC007E3A** active L1/L5 antenna (DigiKey 2958-YFGC007E3A-ND, 20 units ordered today at $14.12 each). YFGC007E3A is the part the spec was actually trying to describe — same Quectel manufacturer, same 17 ± 3 dB LNA, same RHCP, same 100 mm IPEX cable, same active L1/L5 architecture; the earlier name was a transcription error and that part doesn't exist in JLCPCB's library. Datasheet-verified specs replace fabricated ones: 50 × 50 × 14.5 mm body (was assumed 25 × 25 × 11.9), 48.5 g (was 21 g), NF ≤ 2.5 dB (was 1.23 dB), working voltage 3–5 V (was 2.7–3.3 V — 3.3 V is at the low end now, verify margin on first prototype), working current 15.5 ± 4 mA (was ≤ 45 mA), out-of-band attenuation ≥ 50 dB at f₀ ± 100 MHz (was 16 dB at f₀ ± 50 MHz — actual is much better). Antenna is **NOT placed by JLCPCB PCBA** — hand-installed during final B1 assembly: 4 buckle pins snap into 4× ⌀1.3 mm plated thru-holes at 37 × 37 mm centers on B1 PCB, then 100 mm IPEX cable plugs into u.FL receptacle J3. B1 PCB provides 50 × 50 mm continuous GND fill (top + bottom layer, via-stitched) below antenna position. **(2) Bias-T inductor bumped 10 nH → 33 nH** — at 10 nH X_L was only 99 Ω at L1, leaking RF into the DC path; at 33 nH it's 326 Ω at L1, 244 Ω at L5, > 5× line Z₀ in both bands. **(3) Section 6 TFT pinout fix** — TFT backlight reassigned from GPIO19 to GPIO25 to match the actual E1 firmware (`BL=25` in `sailframes_e1.ino`); GPIO19 stays reserved for Hall-latch readback. TFT MISO declared N/C (E1 firmware never reads from TFT). **(4) Designator collisions resolved** — D1–D6 are the six status LEDs (Blue/Yellow/Green/Red/White/Cyan, left to right on bottom edge); D7/D8/D9/D10 are the four SS14 Schottkys (USB OR-ing, Qi OR-ing, MT3608 boost, LC29HEA V_BCKP). LED-driving GPIOs in Section 4 retagged D4/D5/D6 (was D5/D6/D7). **(5) 74LVC1G74 pinout warning added** — the pin numbers used illustratively throughout (1=/PRE, 2=D, 3=CLK, 4=/CLR, 5=GND, 6=/Q, 7=Q, 8=VCC) don't match the standard TI/Nexperia SOT-23-8 pinout; the topology is right, the pin numbers must be re-verified against the actual LCSC part's datasheet before drawing the KiCad symbol. **(6) Pilot test plan**: Day-1 antenna bias current check (~15.5 mA) added as the canary that the RF chain works; quick GNSS check (5-min windowsill, ≥ 6 sats with C/N0 > 30 dB-Hz on L1 AND L5) added before sailing tests. Hand-install antenna step inserted before power-on. Spec is now ready for KiCad implementation — only remaining open item is PCB mounting boss height (Polycase sample measurement).
- v0.10 (2026-05-18): PCB mounting boss height measured on Polycase ML-34F sample = **5 mm**. This was the last open spec question. Consequence: 803450 LiPo (8 mm thick) no longer fits in below-PCB clearance. **Switched LiPo to 503562** (5 × 35 × 62 mm, 1500 mAh protected — same capacity as the previous 803450 choice, thinner profile). Fallback if 503562 unavailable: 503450 (5 × 34 × 50 mm, 1000 mAh). Stack-up section rewritten with measured 5 mm boss height and below-PCB LiPo + Qi coil side-by-side layout (not stacked). Qi receiver PCB body relocates from enclosure base (no longer fits in 5 mm) to B1 PCB top side, with wires running down to the coil on the base floor. All architectural decisions and open questions now closed; spec is locked for KiCad implementation.

---

## Reference Documents

Place these in `edge-e/hardware/datasheets/` for Claude Code to reference:

- `Quectel_LC29H_Series_Hardware_Design_V1.3.pdf` (forums.quectel.com)
- `Quectel_LC29H_Series_Reference_Design_V1.2.pdf` (mouser.com)
- `Polycase_ML-34F_drawing.pdf` (polycase.com/ml-34f#ML-34F*1508)
- `TP4056_datasheet.pdf` (lcsc.com C16581)
- `MT3608_datasheet.pdf` (lcsc.com C47764)
- `BNO085_datasheet.pdf` (Bosch / Hillcrest Labs)
- `ST7796U_datasheet.pdf` (Sitronix)

---

## End of Spec
