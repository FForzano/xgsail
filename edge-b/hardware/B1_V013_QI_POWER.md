# B1 v0.13 — Qi-pad on/off (magnet + button both removed)

**Status: VALIDATED ON HARDWARE (2026-06-29) — survives multi-lift off the pad on battery
at full radio load (FW 2026.06.29.01). The latch is proven good at the J17 `LATCH_DBG`
header: LATCH_Q=3.269 V (R28 is a true 0 Ω jumper), MOSFET_GATE=12.6 mV (AO3401A load switch
hard on). NOTE: an early "dies on lift" scare was a LOOSE BATTERY JST connector, not the
power stage — reseat/verify the battery connector on every fresh board. Battery gauge
calibrated for B1: GPIO34 divider ratio 2.09 (E1 stays 2.25); multimeter 4.096 V read as
4.41 V at 2.25. v0.13 boards arrived 2026-06-28 — the self-power latch
VALIDATED: a board boots on the pad and survives lift-off once PWR_HOLD is driven HIGH.
FIRMWARE IMPLEMENTED in `sailframes_edge.ino` (FW 2026.06.28.01, all under `#ifdef BUILD_B1`;
E build verified byte-identical except the version string). Two deltas from the original §6
spec, both deliberate (see §6): (1) "parked" is a non-blocking loop state, never a halt —
a spin would trip the Core-1 loop watchdog into a restart that re-latches power ON;
(2) the lift-and-replace gesture was DROPPED (a coil-alignment nudge would false-trigger it)
— deliberate off is the `poweroff` serial/telnet command, plus the 30-min idle-on-pad
store-and-forget trigger.**

This replaces the magnetic hall latch with **the Qi charging pad as the power switch** —
no magnet, no button, **zero enclosure penetration** (best possible IP68). Place B1 on
the pad → it powers up (already true via the Option-A `D7` path); it uploads + checks OTA
+ charges; lift it to go race; it auto-records on boat speed; bring it home, set it on the
pad → it stops, uploads, tops off, and powers itself off.

## 1. Why this works without new wiring (the lucky break)

The existing power topology (read from the real netlist, not memory):

```
VBAT ─ U3 (MT3608 boost) ─VOUT→ V5_UNSW ─ Q_PWR1 (AO3401A P-FET) ─D→ V5_SW → ESP32 VIN
                              EN(pin4)            gate(pin1)
                                 ▲                   ▲
                                 └──── /LATCH_Q ──────┴─ R14 → Q_INV1 (2N3904) → gate
Qi pad → TP4056(U2) → TP4056_VCC ─ D7 ──────────────────────────→ V5_SW   (Option-A: powers MCU on-pad)
```

`/LATCH_Q` is the **single master enable** — it drives both the boost `EN` (U3 pin4) and
the P-FET gate path (R14→Q_INV1→Q_PWR1). In v0.12 it was sourced by the flip-flop `U_FF1`.

**The break:** `R28` already bridges **GPIO19** (`/LATCH_Q_RB`, the MCU's old read-back) ↔
`/LATCH_Q`. So deleting the flip-flop makes **GPIO19 the sole driver of `/LATCH_Q` through
the resistor that is already on the board.** `PWR_HOLD = GPIO19`, no new copper for the
latch itself. The ESP32 now *holds its own power* and can *release it* — fixing the v0.12
limitation where the MCU could read the latch but never turn itself off.

> **⚠ REQUIRED value change: `R28` 10 kΩ → 0 Ω (jumper).** The v0.12 flip-flop drove
> `LATCH_Q` **push-pull** (clean high). A series resistor does not: GPIO19(3.3 V) →
> R28(10k) → LATCH_Q → R14(10k) → Q_INV1 base (Vbe-clamped ~0.7 V) is a *divider* that pins
> `LATCH_Q ≈ 1.9 V` — only ~0.4 V over MT3608 `EN` V_IH(~1.5 V). **Set R28 = 0 Ω** so GPIO19
> drives `LATCH_Q` at a full 3.3 V (it sources only R14's ~0.26 mA base current — trivial).
> Change the value *and* the LCSC field to a 0 Ω jumper. (R14, R15 stay 10k/100k.)

## 2. Parts DELETED (done in schematic, verified)

| Ref | Was | Why gone |
|---|---|---|
| `U_HALL1` | DRV5032 hall | magnet sensing removed |
| `U_FF1` | SN74LVC1G74 toggle FF | latch is now the MCU (`PWR_HOLD`) |
| `U_RST1` | MAX809 POR | only existed to reset the FF |
| `R12` | hall pull-up | hall gone |
| `R13`, `C9` | hall→FF debounce | FF gone |
| `D11` | LATCH_Q_RB→V3V3 clamp | GPIO19 is now an output ≤3.3 V, no clamp needed |
| (magnet) | — | the whole point |

**Kept intact** (netlist-confirmed UNCHANGED): `U3`, `Q_PWR1`, `Q_INV1`, `R14`, `R15`,
`R28`, the D7/D8 Option-A path, TP4056. The entire power-delivery chain survives.

### Netlist proof (before → after, the check that matters — ERC was clean on the v0.12 bugs too)
```
/LATCH_Q   : removed U_FF1.5 ;  kept U3.4(EN) + R14.1 + R28.1 + J17.4   ← now driven only via R28 from GPIO19
/V5_SW     : UNCHANGED   /V5_UNSW : UNCHANGED   /MOSFET_GATE : UNCHANGED   /Q_INV_BASE : UNCHANGED
/LATCH_Q_RB: removed D11 ; kept J4.10(GPIO19) ↔ R28.2
/HALL_OUT, /CLK_DEBOUNCED → harmless single-pin J17 debug stubs ;  /RESET_N → gone
components 78→71, nets 79→77
```
34 ERC warnings remain — all `label_dangling` / `unconnected_wire_endpoint` from the
removed front-end. They carry **no netlist nodes**; rubber-band-delete the orphaned labels
in the latch corner during the GUI reflow.

## 3. Parts to ADD (GUI — §5)

| New | Net A | Net B | Value | Purpose |
|---|---|---|---|---|
| `R_PD` | `LATCH_Q` | `GND` | 100 kΩ | **REQUIRED.** Default-off: holds boost `EN` low while GPIO19 is hi-Z at boot, so the MCU boots on the D7/Qi rail first, then asserts `PWR_HOLD`. Without it, `U3 EN` floats at power-up. |
| `R_QA` | `V_QI` | `QI_PRESENT` | **47 kΩ** | Top of QI-present divider |
| `R_QB` | `QI_PRESENT` | `GND` | **68 kΩ** | Bottom — ratio 68/115 → on-pad `QI_PRESENT` ≈ **2.96 V** (solid logic-high, ESP32 V_IH ≈ 2.5 V), and ≤ 3.3 V. |

`QI_PRESENT` → **GPIO15** (J4.3, currently the free `/GPIO15` stub).

> **Divider math (corrected — earlier 100k/47k gave ~1.6 V, which is *below* V_IH and
> would never read high).** Need ratio ≥ 0.5 off the 5 V pad. With **R_QA=47k, R_QB=68k**:
> - **On pad, running** (firmware sets GPIO15 = `INPUT`, no internal pull): node = 5·68/115
>   ≈ **2.96 V** → clean HIGH. ✅
> - **At boot** GPIO15 has its ~45 kΩ internal pull-up to 3.3 V (strapping default). With the
>   divider in parallel the node solves to ≈ **3.1 V** (< 3.3 V, no over-drive) — and GPIO15
>   is a strapping pin that **must be HIGH at boot**, which the divider satisfies *for free*
>   because the device only ever cold-boots while on the pad (V_QI present). ✅
> - **Off pad, running** (V_QI = 0, internal pull disabled): node = 0 V → clean LOW. ✅
>
> Firmware MUST set GPIO15 to `INPUT` (pull disabled) after boot so the off-pad read is a
> solid low. If V_QI is not 5.0 V nominal, re-check that the boot node stays ≤ 3.3 V.
> (Alt pin: `GPIO36`/VP if you free it from `AUX_INT`.)

Charge-complete needs **no extra pin**: infer from the existing battery ADC (`VBAT_DIV`,
GPIO34) plateauing ≥ ~4.15 V while `QI_PRESENT` is high. (Optional richer signal: tap
`TP_STDBY` (U2 pin6, open-drain) to a spare pin — but pins are scarce; battery-plateau is
enough.)

## 4. Final pin map delta

| GPIO | v0.12 | v0.13 |
|---|---|---|
| GPIO19 (J4.10) | `LATCH_Q_RB` (read-only) | **`PWR_HOLD`** — output, drives `/LATCH_Q` via R28. HIGH = on, LOW = off. |
| GPIO15 (J4.3) | reserved/strap | **`QI_PRESENT`** — input, V_QI divider. HIGH = on pad. |
| GPIO34 | `VBAT_DIV` | unchanged — also used for charge-complete inference |

## 5. PCB reflow — GUI ONLY (kicad-cli cannot route)

1. Open `kicad_sailframes-b1.kicad_pcb`, **Tools → Update PCB from Schematic** (F8). This
   removes the 7 deleted footprints **and their traces** and flags the latch corner.
2. Add the 3 new passives (`R_PD`, `R_QA`, `R_QB`) — 0402/0603 to match the board; place in
   the freed latch-corner space near `U3`/`R28`.
3. Route: `LATCH_Q`→R_PD→GND; `V_QI`→R_QA→GPIO15(J4.3)→R_QB→GND. The `GPIO19→R28→LATCH_Q`
   trace already exists — verify it survived.
4. **Re-pour B.Cu ground** (and, while here, the §7 antenna keepout).
5. **DRC must be clean.** Then net-trace GPIO19→R28→U3.EN and GPIO15→R_QB by eye — don't
   trust DRC alone (the v0.12 microSD + U_HALL bugs were DRC-clean).
6. Regenerate fab outputs (gerbers/BOM/CPL) only after DRC + the J5 + antenna fixes (§7).

## 6. Firmware (IMPLEMENTED — FW 2026.06.28.01, gated `#ifdef BUILD_B1`)

In `sailframes_edge.ino`, gated at **compile time** by `#ifdef BUILD_B1` (NOT runtime
`g_hw`): GPIO19 is physically `TFT_BL` on E (User_Setup.h), so an E binary must never
touch it. Implemented as: `setup()` drives PWR_HOLD HIGH + GPIO15 `INPUT` as the first GPIO
op; `b1PowerTick()` (per loop) evaluates the triggers; `b1EnterParked()` releases the latch;
`b1ParkedLoop()` is the non-blocking parked state; `drawB1ChargingScreen()` is the on-pad UI;
`power`/`poweroff` serial commands. Set GPIO15 = `INPUT` (no pull) right after boot (see §3
divider note).

> **Two deliberate deltas from the original spec below** (kept the spec text for context):
> - **Parked = non-blocking loop state, never a halt.** `b1EnterParked()` sets `g_b1Parked`,
>   drops PWR_HOLD, and `loop()` early-returns each iteration *after* `g_loopIter++`/wdt-feed.
>   A `while(true)` halt would freeze `g_loopIter`, the Core-1 loop watchdog (gotcha #22)
>   would `esp_restart()`, and `setup()` would re-latch PWR_HOLD HIGH ~90 s later → the unit
>   powers itself back ON. Off-pad the latch drop is instant death anyway; on-pad it dies
>   when lifted.
> - **No lift-and-replace gesture (was trigger 2).** Qi coil alignment means users routinely
>   nudge a board on the pad — a lift+replace within 3 s = normal handling, not a deliberate
>   act. Deliberate off is now the **`poweroff`** serial/telnet command; store-and-forget is
>   the **30-min idle-on-pad** trigger (3).

**Core rule: `PWR_HOLD` stays HIGH the whole time the MCU is running, EXCEPT for three
explicit power-off triggers.** This is the fix for the otherwise-fatal conflict below.

- `setup()`: drive `PWR_HOLD` (GPIO19) **HIGH immediately** — first GPIO op, before slow init
  — so the device latches on the instant it boots (always on the pad, via D7) and survives
  lift-off. It then *stays* high.
- On the pad (`QI_PRESENT` high): run the existing stationary-upload + OTA sweep + charge.
  TFT: `Charging NN%` → when full, `Charged ✓ · LIFT to RACE`. **`PWR_HOLD` stays HIGH** — so
  a topped-off unit that you lift goes straight to racing. (Charge-complete does NOT drop
  power; it only ends fast-charge / updates the TFT.)
- Lift to race (`QI_PRESENT` high→low while `PWR_HOLD` high): normal logging; auto-record on
  >1.5 kt (existing). Always works regardless of charge state — that's the point of the rule.
- **Power-off trigger 1 — low battery** (off-pad, `VBAT` < cutoff): `PWR_HOLD` LOW → off.
- **Power-off trigger 2 — deliberate park gesture on the pad:** while `QI_PRESENT` high, a
  recognizable gesture (e.g. lift-and-replace within 3 s, or a TFT-confirmed "hold 3 s to
  power off") → `PWR_HOLD` LOW. On the pad the MCU stays alive on D7 until you lift it; **on
  lift it's fully off** → store. *(Pick the exact gesture at firmware time; the hardware
  doesn't care. This is what lets you intentionally store a charged unit.)*
- **Power-off trigger 3 (optional) — long idle-on-pad after full:** e.g. fully charged +
  uploaded + untouched 30 min → `PWR_HOLD` LOW (store-and-forget), since you clearly aren't
  about to race it.
- Core-1 loop watchdog (existing) covers field hangs — the only field recovery, since there's
  no pad on the water. **This is the accepted trade-off of a button-free sealed unit.**

> The conflict this resolves: an earlier draft dropped `PWR_HOLD` on charge-complete *and*
> defined lift-to-race as "QI_PRESENT low while PWR_HOLD high." A full battery would then sit
> with PWR_HOLD already LOW → lifting it powers **off**, never races. Keeping PWR_HOLD high
> and gating power-off behind explicit triggers (low-batt / park gesture / long-idle) fixes it.

## 7. Bundle with the other v0.13 gates
This spin must also carry: **J5 microSD net→pad fix** (`B1_J5_MICROSD_FIX.md`) and the
**2.4 GHz antenna provision** (`project_espnow_range_antenna`). All three close in one fab.
