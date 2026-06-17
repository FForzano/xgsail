# B1 v0.13 production-data audit (2026-06-17) — `production/` + `.kicad_pcb`

Audited the Fabrication-Toolkit outputs in `edge-b/hardware/production/` and the board
`kicad_sailframes-b1.kicad_pcb` for "safe to send to JLCPCB (PCB + assembly)."

## Verdict
**The data package is complete, current, consistent, and manufacturable.** Pre-order this was
"not safe to send blind" pending three items (rotations, DRC, THT). **UPDATE 2026-06-17:
ORDERED at JLCPCB** — JLC through-hole-assembles all headers; only Qi (J_QI1) + IMU (J8) are
hand-soldered; the rotation review + multi-line header confirmation were done in JLC's
"Confirm Parts Placement" at order time. The full pre-order audit is preserved below.

## ✅ Verified good
- **Current + consistent (content-checked, not just timestamps).** BOM, CPL, gerbers, and the
  IPC netlist all regenerated **2026-06-17 13:27** from the **committed** board. The BOM
  carries the *current* parts — **C510087** (10k), **C21189** (R28 0603 0Ω), **C57369 ×2**
  (J8 + J9, J9 now matched), C28453488 (U1). No `C25804`/`C17168` stale parts remain. The
  Edge_Cuts **gerber content** contains the v0.13 **notch** (121 vertices at the X=170 inner
  edge) — so the gerbers are the real current board, not a pre-notch export.
- **BOM complete** — 42 grouped lines / **71 parts**, every one has an LCSC #, zero
  "unconfirmed"/empty matches.
- **Gerbers complete** — F/B Cu, F/B Mask, F/B Paste, F/B Silk, Edge_Cuts, + PTH & NPTH drill
  files (+ drill maps). Full 2-layer set JLC needs.
- **CPL complete** — 71 parts with Mid X/Y + Rotation + Layer; the v0.13 additions
  (R30/R31/R32, R28=0Ω) are present; nothing erroneously on the bottom layer (J_QI1 Qi pads
  correctly excluded — hand-wired).
- **Manufacturable vs JLC limits** — vias 0.6 mm / 0.3 mm drill; drills 0.2–2.6 mm; copper
  traces ≤0.5 mm. All within JLC standard (min trace 0.127, min drill 0.2). (A `width 0.0`
  appears only on a non-copper graphic; the board is DRC-clean so there is no 0-width track.)
- **Copper + pour content-verified (not assumed).** B_Cu gerber: 198 pad flashes + **15
  filled regions** — and the board's single B.Cu copper zone has exactly **15 filled
  polygons** → the **ground pour exported intact** (no empty-pour bug). F_Cu gerber has 0 fill
  regions, which is **correct**: F.Cu has only 8 *keepout* zones and no copper pour by design
  (pour is B.Cu-only, per the EMI plan). Pad flashes (~363 top / ~198 bottom) are sane for
  ~71 parts. **Annular ring OK**: all vias 0.6 mm / 0.3 mm → 0.15 mm annular (> JLC 0.13);
  the 0.2 mm drills are non-plated (NPTH/holes), so no annular requirement.
- Board geometry already audited clean in `B1_V013_AUDIT.md` (connectivity, U1 footprint
  pad-vs-package, edge clearance ~0.59 mm) and the **GNSS RF path is field-validated**.

## ⛔ Hard gates — DO before sending
1. **CPL rotations — verify in JLC "Confirm Parts Placement."** I cannot verify rotation
   correctness from the CSV; it's the #1 cause of dead boards. Fabrication Toolkit applies JLC
   rotation corrections for *standard* footprints, but **U1 (LC29HEAMD) uses a CUSTOM
   footprint (`GPSM-SMD_24P`), so the plugin almost certainly applied NO correction — its 0°
   is the raw KiCad angle and may not match JLC's reel orientation. This is the highest risk
   (a mis-rotated GNSS module = dead board).** Eyeball every polarized part against pin-1:
   **U1 (0°), U2 (270°), U3 (180°), diodes D7(180)/D8(0)/D9(270)/D10(180) [SS14 cathode],
   LEDs D1–D6 (0°) [cathode], Q_INV1/Q_PWR1 (180°) [SOT-23].**
2. **DRC — reconfirm clean in KiCad.** I verified the specific manufacturability metrics
   directly (trace ≤0.5 mm, via 0.6/0.3 + 0.15 mm annular, drills 0.2–2.6 mm, edge clearance
   ~0.59 mm, pour filled). What I CANNOT check (kicad-cli 10 can't load format `20260206`):
   **no unrouted ratsnest, no trace-to-trace clearance violations, no shorts.** Re-run DRC in
   KiCad on the current board and confirm 0 violations + 0 unconnected before sending. (You
   reported it clean earlier — just confirm it's this exact board state.)

## ✅ Through-hole assembly — DECIDED + ORDERED (2026-06-17)
The CPL/BOM include 12 through-hole connectors. **Decision: JLC does through-hole assembly
for all headers.** Only **J_QI1 (Qi pads)** and **J8 (IMU / BNO085 module)** are hand-soldered
by the user; everything else (SMT + the rest of the THT headers) is JLC-assembled.
The multi-line-same-part header warnings (J9/J11/J12/J14/J16/J17 sharing C57369/C5116483/
C5156614 with J8/J10/J13) were confirmed in the JLC BOM tool. **Order placed.**

## Hygiene (not blocking)
- The `production/*` outputs are **uncommitted** (the board *is* committed). Commit them so
  there's a version-controlled record of exactly what was sent.
- **Extended parts** (blue/yellow/green LEDs, J1/J4 socket, J2, J3, J5, U1, U2, U3, L1, L2,
  R11) may carry per-type fees / stock risk — re-confirm in-stock at checkout (the BOM's own
  note: re-match if the export is >24 h old).

## Bottom line
Files are right and current. **Before you click order: (1) verify rotations in Confirm Parts
Placement — especially U1; (2) confirm KiCad DRC is clean; (3) decide THT vs hand-solder.**
