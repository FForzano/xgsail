# B1 PCB pre-route review — 2026-05-29

Board: `kicad_sailframes-b1.kicad_pcb` (KiCad 10, 79.5 × 89.3 mm, 2-layer,
77 footprints, 0 routed segments/vias). Headless DRC unavailable on this
nightly ("Failed to load board") — DRC must run in the GUI.

## ✅ FIXED 2026-05-29 in schematic (3 label renames, backup `.bak-boostfix`)

`L1.p1 MT3608_SW→VBAT`, `L1.p2 BOOST_OUT→MT3608_SW`, `D9.anode BOOST_OUT→MT3608_SW`.
Resulting nets: VBAT={U3.VIN, L1.p1}, MT3608_SW={U3.SW, L1.p2, D9.anode},
V5_UNSW={D9.cathode, C8, R10}, BOOST_OUT=deleted. **Still TODO:** Update PCB from
Schematic (F8), then re-place the switcher per the section below.

## 🔴 (original finding) MT3608 boost inductor was not in the power path

Net evidence (PCB + schematic agree):

| Node | Net | Members |
|---|---|---|
| Battery in | `/VBAT` | C4.1 C5.1 C7.1 J2.2 U2.5 **U3.5 (VIN pin)** … (no L1!) |
| Switch node | `/MT3608_SW` | **U3.1 (SW)**, **L1.1** |
| L–D junction | `/BOOST_OUT` | **L1.2**, **D9.2 (anode)** |
| 5 V output | `/V5_UNSW` | **D9.1 (cathode)**, C8, R10 (FB top) |

A boost requires `VBAT — L1 — [SW pin + diode anode]`, diode cathode → Vout.
As drawn, the inductor sits between the SW pin and the diode, and **VBAT only
reaches the VIN bias pin — nothing charges the inductor from the battery.**
The converter cannot boost. FB divider (100k/13.7k → 4.98 V) confirms a 5 V
boost was intended.

**Fix in schematic, before routing:** inductor between `VBAT` and the SW node;
SW pin and diode anode on one node; eliminate the `BOOST_OUT` intermediate so
`MT3608_SW` = {U3.1, L1.x, D9.anode}.

**Why it will pass bench test and fail in the field:** the downstream chain is
`V5_UNSW → Q_PWR1 (AO3401A load switch) → V5_SW → J1.15 (ESP32 VIN)`, and
`ESP32 3V3 LDO → J4.1 → /V3V3` feeds GNSS/IMU/SD. USB 5 V (`/TP4056_VCC`) is
OR'd into both rails via D7 (→V5_SW) and D8 (→V5_UNSW), so **on USB the whole
board powers up normally and the dead boost is invisible.** On battery alone the
MT3608 is the only 5 V source → V5_SW dead → ESP32 never boots → V3V3 dead →
nothing works. This is exactly the bug that survives a USB-powered smoke test.

This class of error (valid connectivity, wrong topology) passes BOTH ERC and DRC —
only a manual net trace catches it. The rest of the power tree was traced clean:
TP4056 charge path (USB→BAT→VBAT) ✓, V3V3 sourced from the ESP32 module LDO ✓,
VBAT_DIV battery-monitor divider → J1.4 ✓.

## 🟠 Boost placement (valid once topology fixed)

- D9 (rectifier) is **24 mm** from U3/L1 — the switching loop (SW→diode→Cout→GND)
  must be tiny. Pull D9 + output cap C8 (currently 8.6 mm) right against L1/U3.
- No VBAT bypass at U3 pin 5 — nearest VBAT cap (C7) is ~30 mm. Add a ceramic
  at the VIN pin.
- FB divider R10/R11 are 16–17 mm from U3 pin 3 (FB is hi-Z, noise-sensitive) —
  place them at the pin, away from the SW node.

## ✅ FIXED 2026-05-29 — D7 reversed to Option A (backup `.bak-d7fix`)

Swapped D7's two pin labels: cathode-side `TP4056_VCC→V5_SW`, anode-side
`V5_SW→TP4056_VCC`. D7 now conducts **TP4056_VCC → V5_SW** (charger powers the ESP32
rail directly when docked; no back-feed when on battery). **TODO:** Update PCB from
Schematic (F8). Firmware: boot → upload → `esp_deep_sleep()` for the dock-and-upload
workflow. Note: ESP32 has no self-power-off path (reads `LATCH_Q_RB` only) — true
power-down while docked is not possible in Option A; it deep-sleeps until removed.

## 🔴 (original finding) D7 reversed — parasitic battery→boost→charger loop

Under the *same* `B1_SS14` symbol (pin1=K, pin2=A), D8/D9/D10 all come out correct
and **only D7 is reversed** — so this isn't a convention mistake. D7: K=`/TP4056_VCC`,
A=`/V5_SW` → conducts **V5_SW (boost 5 V output) → TP4056_VCC (charger input)**.

During normal battery operation (device ON, no Qi): boost makes V5_SW≈5 V, VCC=0,
so D7 pulls TP4056_VCC up to ~4.6 V. The TP4056 sees input present and charges the
battery — from the boost, which is fed by that same battery. A lossy circulating
current (~0.6 A charge × 4.6 V, drawn from the battery via the boost) → continuous
drain, heat, CHRG LED on, charge-terminate oscillation.

**Fix:** the as-drawn back-feed is definitely wrong; the diode must be reversed. Node
choice depends on intent: A=`/TP4056_VCC`→K=`/V5_SW` powers the system from the charger
(but boots the ESP32 whenever on the charger, bypassing the magnet latch); if you want
**charge-while-off**, target `/V5_UNSW` instead (upstream of the Q_PWR1 load switch, so
the latch still gates ESP32 power).

Diode orientations checked: D8 ✓ (V_QI→VCC), D9 ✓ (SW→V5_UNSW, post-fix),
D10 ✓ (V3V3→V_BCKP), **D7 ✗ (reversed)**.

## ✅ FIXED 2026-05-29 — added C17 100nF bypass on V_BCKP (backup `.bak-vbckp`)

New C17 (100nF 0603, C14663) on `GNSS_V_BCKP → GND`, near D10. Cold start is
acceptable for B1, so no supercap needed — this is purely decoupling. **TODO:**
Update PCB from Schematic (F8) → place C17 next to U1 pin 22. Residual (optional,
your call): D10 still drops ~0.4 V and, with no backup energy source, is functionally
optional — could tie V_BCKP straight to V3V3 if the drop nears the LC29H min spec.

## 🟠 (original) GNSS V_BCKP — no backup energy, diode drop, no decoupling

`/GNSS_V_BCKP` = {U1.22, D10.K}; D10.A=V3V3. **Add a bypass cap on V_BCKP** (the lone
D10 diode implies an intended-but-missing backup source — there's no cap and no
supercap/coin cell). As-is, V_BCKP loses power when V3V3 drops, so every power-up is a
cold start (slow TTFF) — a design choice, not a defect; add a supercap if you want
warm starts. The ~0.4 V SS14 drop puts V_BCKP below V3V3 — verify LC29H V_BCKP min spec.

## 🔴 BNO085 (J8) — WRONG PINOUT for the GY-BNO08X (would short SCL to GND)

B1 uses the **GY-BNO08X** (same as E1), but J8 was laid out for the Adafruit
breakout — different pin order AND pin count. Confirmed against E1's field-proven
J3 (`PinHeader_1x10`, pads 1-4 = 3V3 / GND / SCL / SDA):

| pin | E1 J3 (works) | B1 J8 (current) | GY-BNO08X plugged into B1 |
|---|---|---|---|
| 1 | 3V3 | 3V3 | ✓ |
| 2 | **GND** | **NC** | module GND floating — no ground ✗ |
| 3 | **SCL** | **GND** | SCL shorted to GND → hangs whole I2C bus ✗ |
| 4 | SDA | SDA | ✓ |
| 5 | NC | **SCL** | module pin5 on B1's SCL net ✗ |
| 6-10 | NC | NC (6-9) | — |

Plus J8 is **9-pin** (`PinHeader_1x09`); E1/GY-BNO08X is **10-pin** → won't seat.

**Fix: make J8 = E1's J3 exactly** — footprint `PinHeader_1x10_P2.54mm_Vertical`,
symbol `Conn_01x10`, nets `pin1=3V3, pin2=GND, pin3=SCL, pin4=SDA, pins5-10=NC`.
This is a footprint+symbol change (do in GUI, not a surgical label edit).

**Address:** GY-BNO08X pulls ADO high on-board → **0x4B** with no strap (E1 leaves
address pin NC and runs 0x4B). Firmware `BNO085_ADDR 0x4B` is CORRECT — leave it.
Docs saying "0x4A / Adafruit" (README, spec §5) are wrong for this module → fix to 0x4B.

## (dropped) Indicator LEDs D4/D5/D6 on 5 V — this is correct

Anodes via 1k to `/V5_SW` (5 V), cathodes to active-low GPIOs. At GPIO-high (3.3 V)
the LED only conducts if 5−Vf > 3.3 (Vf < 1.7 V); red ~1.9 V and white/cyan ~3.0 V
are **fully off**. 5 V is the right rail — high-Vf white/cyan need the headroom
(on 3V3 they'd get ~0.3 mA, too dim). Only a harmless ~100 ms glow during boot hi-Z.
No change. (Optionally confirm the red one fully extinguishes.)

## ✅ Verified correct (no action)

- **ESP32 strapping:** GPIO12 + GPIO15 are isolated nets to expansion headers only,
  **no pull resistors** — gotcha #15 avoided. HSPI (SD) and VSPI (TFT) on separate
  buses (gotcha #16). SD pull-ups (R23–R26) are on non-strapping nets.
- **I2C pull-ups** R21/R22 = 4.7k to V3V3 on SDA/SCL ✓
- **SD line pull-ups** R23–R27 = 10k ✓; CD line pulled up ✓
- **Power latch:** hall (DRV5032AJ) → toggle FF (SN74LVC1G74, D tied to Q̄) →
  drives boost EN (`LATCH_Q→U3.4`) + load-switch gate via 2N3904; MAX809 holds the
  FF reset at power-on so the device boots OFF until a magnet tap. Gate pull-up
  R15=100k to source ✓. Sound design.
- **Charge LEDs** D2 (CHRG) / D3 (STDBY) correctly OR'd to TP4056 open-drain ✓
- **Qi charge path** Qi module → V_QI → D8 → TP4056 → battery ✓

## TP4056 config — verify (not errors)

- R6 (PROG) = 2k → ≈600 mA charge current. Confirm that suits the B1 cell.
- TP_TEMP via R7 (10k) to GND — datasheet disables temp sensing by grounding TEMP;
  10k-to-GND usually reads as disabled but confirm it sits below 45% of VCC.

## 🟢 GNSS RF — topology plausible, verify against reference design

U.FL J3 → LC29H U1 = 15.3 mm with what looks like a standard active-antenna bias-tee
(L2 33nH feeds `/GNSS_VDD_RF`) + match (C11 100pF / C10 10nF). Switcher is 78 mm away
(diagonally opposite) — good isolation. Topology only — **verify component values and
the match against the LC29H reference design** (I didn't check RF correctness).

## 🟡 Mechanical / minor

- U_HALL1 (DRV5032 magnetic power latch) at (102.6, 125), 2.7 mm from left edge,
  47 mm from Qi coil (no field interference). **Verify it aligns with the magnet
  position in the enclosure** — placement is mechanical, not electrical.
- Only J_QI1 on B.Cu — "no SMD on back under LiPo" constraint satisfied ✓.
- Bypass distance: BNO085 C16 = 10 mm, flip-flop U_FF1 → C9 = 11 mm. Acceptable
  (module onboard caps / low-speed logic) but tighten if convenient.

## Verify in GUI before routing
1. Run DRC; ignore "unconnected", act on courtyard/clearance/silk-over-pad.
2. Toggle ratsnest; inspect the J4-TFT ↔ BNO knot for parts that want to swap.
3. Route the switcher loop + RF feed first as a routability probe.
