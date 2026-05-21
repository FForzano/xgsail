# B1 PCB v1 — J_AUX Expansion Header Specification

**Document type:** Hardware spec for Claude Code (KiCad work) and Paul (sourcing)
**Status:** v1, lock before B1 v1 Gerber export
**Scope:** Defines the 6-pin J_AUX header on B1 v1 PCB and the components that connect to it

---

## Purpose

The J_AUX header is the B1 v1 PCB's planned future-expansion connector. It exposes:
- I²C bus (shared with BNO085)
- One input-only GPIO for sensor interrupt / data
- 3V3 and 5V power
- GND

In v2.0.0 firmware, the header serves two specific uses:
1. **KY-038 sound sensor** on RC signal-boat units, for horn detection
2. **Future RM3100 magnetometer upgrade** (v1.5+), for improved heading accuracy

Both use cases are I²C-compatible (KY-038 uses a single digital output pin, RM3100 is I²C). The header is designed to handle either, with a reserved "magnetic clean zone" adjacent to it for the RM3100 footprint placement in a future PCB revision.

---

## Header pinout

**Connector type:** 1×6 male pin header, 2.54 mm pitch, vertical, through-hole
**Reference designator:** J_AUX (or J1, J2 — whatever fits PCB naming convention)
**Silkscreen labels** on PCB top side adjacent to each pin

```
Pin │ Signal     │ ESP32 net  │ Direction │ Purpose
────┼────────────┼────────────┼───────────┼─────────────────────────────────────
 1  │ 3V3        │ +3V3       │ Power out │ 3.3V supply for sensors
 2  │ GND        │ GND        │ Ground    │ Common ground
 3  │ SDA        │ GPIO21     │ Bidir I²C │ I²C data, shared with BNO085 (0x4B)
 4  │ SCL        │ GPIO22     │ Bidir I²C │ I²C clock, shared with BNO085
 5  │ AUX_INT    │ GPIO36     │ Input     │ Interrupt / digital signal from sensor
 6  │ 5V         │ +5V_BOOST  │ Power out │ 5V supply (from Acxico Qi → boost output)
```

### Pin assignment rationale

- **Pin 1 (3V3)**: Required for all I²C sensors and the KY-038 (operates 3.3V or 5V; 3.3V keeps the digital output at 3.3V logic level safe for ESP32 GPIO).
- **Pin 2 (GND)**: Standard ground reference.
- **Pins 3-4 (SDA/SCL)**: Already routed for BNO085 at I²C address 0x4B. Bus supports multiple addressable devices. RM3100 default address is 0x20-0x23 (selectable) — no conflict. Pull-up resistors (4.7 kΩ on each line) are already populated on the BNO085 side.
- **Pin 5 (AUX_INT)**: GPIO36 (SVP) is input-only, ADC1_CH0. Already free in B1 pin map. Suitable for:
  - KY-038 digital output (rising edge interrupt)
  - RM3100 DRDY signal (data-ready interrupt)
  - Any other future sensor that needs to signal "data available"
- **Pin 6 (5V)**: From the Acxico Qi receiver / MT3608 boost output (~5.13V validated by bench test). Useful for sensors that prefer 5V (KY-038 supports either; future sensors may require 5V). Available because the Qi charging path generates this rail anyway.

### NOT exposed on J_AUX (and why)

- **GPIO1, GPIO3** (UART0): programming interface; sharing it with daughter board causes chaos.
- **Strapping pins** (GPIO0, 2, 5, 12, 15): daughter board pulling them at boot bricks the ESP32.
- **HSPI, VSPI pins**: shared bus would corrupt SD or TFT.
- **GPIO34** (battery monitor): committed.
- **GPIO19** (Hall flip-flop readback on B1): committed.
- **GPIO39** (1PPS from LC29HEA): committed.

---

## PCB placement requirements

### Header location

- **Recommended position**: X = 15 mm, Y = 70 mm (left side of PCB, opposite the Hall sensor)
- **Orientation**: Pins running parallel to the long axis of the PCB
- **Side**: Lid-facing side of the PCB (daughter board will sit in the lid space)
- **Clearance**: 10–15 mm minimum height clearance above for daughter board
- **Mounting boss conflict check**: must not interfere with the ML-34F PCB bosses at 85×50 mm spacing

### Reserved magnetic clean zone

Adjacent to J_AUX, reserve a 15×15 mm area with:
- **No copper pours**
- **No stitching vias**
- **No power traces underneath** (on either layer)
- **Silkscreen label**: "MAGNETIC CLEAN ZONE — KEEP COPPER FREE"

Purpose: future RM3100 placement (v1.5+) without PCB respin. The RM3100 is sensitive to nearby copper currents and ferromagnetic features. Reserving the area now costs nothing.

### Distance from sensitive components

| Component       | Min distance from J_AUX | Reason                          |
|-----------------|-------------------------|---------------------------------|
| LiPo battery    | 30 mm                   | Magnetic field during charging  |
| Hall sensor     | 50 mm                   | Both magnetic; cross-talk risk  |
| Qi receiver coil| 30 mm                   | Strong induced field while charging |
| ESP32 module    | 15 mm                   | High di/dt switching noise      |
| BNO085          | 5 mm (OK to be close)   | Both are magnetic sensors; already on same I²C bus |

These constraints favor the left-side-of-PCB position recommended above.

---

## Electrical details

### Pull-ups

- SDA/SCL pull-ups: **already populated** (4.7 kΩ each on BNO085 I²C lines). Do not add additional pull-ups on the daughter board side — that would parallel the existing ones and bring effective resistance below recommended values.
- AUX_INT (GPIO36): **no pull-up needed** if KY-038 driving HIGH actively. If using a sensor with open-drain output, add a 10 kΩ pull-up on the daughter board side.

### Power budget

| Pin | Max current | Notes |
|-----|-------------|-------|
| 3V3 | 100 mA      | Total available across all loads on J_AUX. Source: ESP32 module's onboard LDO. |
| 5V  | 200 mA      | From MT3608 boost; shared with charging path. Don't exceed if Qi is also active. |

The KY-038 draws ~3 mA at 3.3V. RM3100 draws ~0.5 mA at 3.3V. Plenty of headroom.

### ESD protection

Optional but recommended: add TVS diodes (e.g., SP0503BAHT) on SDA, SCL, AUX_INT to ground. Protects the ESP32 from static discharge through the header when daughter boards are hot-plugged. Adds ~$0.30 in BOM.

---

## Mechanical drawing

```
TOP VIEW OF B1 PCB (LID-FACING SIDE)
─────────────────────────────────────────────────────────────

  ┌─────────────────────────────────────────────────────┐
  │   ▒▒▒                                                │
  │   ▒▒▒  ← Mounting boss             ┌──────────┐     │
  │                                    │  HALL    │     │
  │                                    │  SENSOR  │     │
  │   ┌────────────┐                   │  + FF    │     │
  │   │  J_AUX     │                   └──────────┘     │
  │   │ ┌──┬──┬──┐ │                                    │
  │   │ │1 │3 │5 │ │   ┌─────────────────┐              │
  │   │ ├──┼──┼──┤ │   │   ESP32 MODULE   │              │
  │   │ │2 │4 │6 │ │   │   (DevKit V1)    │              │
  │   │ └──┴──┴──┘ │   │                  │              │
  │   └────────────┘   └─────────────────┘              │
  │                                                       │
  │   ┌──────────┐                                       │
  │   │ MAGNETIC │                                       │
  │   │ CLEAN    │   ← Reserved 15×15 mm                 │
  │   │ ZONE     │     no copper, no stitching          │
  │   └──────────┘                                       │
  │                                                       │
  │   ┌──────────┐                                       │
  │   │ BNO085   │                                       │
  │   └──────────┘                                       │
  │                                                       │
  │   ▒▒▒                                                │
  │   ▒▒▒  ← Mounting boss                               │
  └─────────────────────────────────────────────────────┘

         ↑                                ↑
         LEFT SIDE                        RIGHT SIDE
         (sensor zone)                    (Hall + switch)
```

---

## KiCad implementation checklist

For Claude Code working on the B1 v1 KiCad project:

1. **Add J_AUX component** to schematic:
   - Symbol: 1×6 pin header (use standard `Connector_Generic:Conn_01x06`)
   - Footprint: `Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical`
   - Reference: J_AUX

2. **Connect nets** as per pinout table above. Verify:
   - 3V3 net is the same as the BNO085 power net
   - GND is common
   - SDA and SCL connect to the SAME nets as BNO085 SDA/SCL (parallel taps, not a new bus)
   - GPIO36 routes from ESP32 module pin to J_AUX pin 5
   - 5V net comes from MT3608 output

3. **Place on PCB** at X≈15, Y≈70 mm, vertical orientation, lid-facing side.

4. **Define keep-out zone** (15×15 mm "magnetic clean zone") near the header. Use a "Keepout" zone with all copper/via options forbidden.

5. **Add silkscreen** labels:
   - Pin 1: "3V3" (with the standard square pad indicator for pin 1)
   - Pin 2: "GND"
   - Pin 3: "SDA"
   - Pin 4: "SCL"
   - Pin 5: "INT"
   - Pin 6: "5V"
   - Below the header: "J_AUX"
   - Inside keepout zone: "MAGNETIC CLEAN ZONE"

6. **DRC and ERC** clean — verify no shorts, no unconnected nets that should be connected.

7. **3D model**: optional but useful for verifying clearance with the ML-34F lid. Standard 1×6 header is a stock 3D model in KiCad.

---

## Validation tests (before B1 v1 Gerber export)

Before sending Gerbers to JLCPCB:

- [ ] Pin map matches both schematic and PCB layout
- [ ] J_AUX is reachable when ML-34F lid is closed (header height + daughter board doesn't hit lid)
- [ ] No copper or vias in the magnetic clean zone (use KiCad's "Highlight Net" to verify)
- [ ] Distance from J_AUX center to LiPo, Hall, Qi coil meets minimums in table above
- [ ] DRC clean
- [ ] BOM includes the header itself (Würth 61300611121 or generic equivalent)

---

## Header part number

Recommended (any of these work, pick one):

- **Würth 61300611121** — 1×6 vertical, 2.54 mm, gold-plated, $0.18 ea Mouser. Standard, widely stocked.
- **Sullins PRPC006SAAN-RC** — equivalent, ~$0.20 ea Digikey. Backup if Würth out of stock.
- **Generic JST PH or unbranded 2.54 mm header** — for prototyping, fine.

JLCPCB's Basic Parts library includes pin headers as standard SMT-assembly parts. The 1×6 2.54 mm through-hole header is hand-soldered post-SMT (JLCPCB does THT assembly but charges more). For 80 units, hand-soldering the J_AUX header is reasonable.

---

## Open hardware questions to resolve before fab

1. **Should J_AUX be populated by default on all B1 v1 units?** Yes — the cost is $0.20 per unit and it's the only future-expansion path. Populate on all units even if most won't have a daughter board.

2. **Add the second I²C pull-up jumper?** No — the existing BNO085 pull-ups are sufficient for the bus. Daughter boards should NOT add their own.

3. **TVS diodes on J_AUX lines?** Recommended but optional for v1. Add if BOM cost budget allows; skip if tight. Risk: hot-plug ESD damage to ESP32. Mitigation if skipped: documentation says "power down before connecting/disconnecting J_AUX devices."

4. **Conformal coating on the header pins?** No — header pins need to be exposed for daughter board plug-in. Conformal coat the rest of the PCB but mask the J_AUX area.
