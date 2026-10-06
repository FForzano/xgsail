---
target: frontend/src/components/session/SessionDetail.tsx
total_score: 25
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 3
target_identity: "file:/Users/federico/Documents/Personal-DEV/xgsail/frontend/src/components/session/SessionDetail.tsx"
target_fingerprint: "sha256:4d6df94353db37dea906c4a26360a3c8f3c0f37a46565677d2a2491ff6456022"
target_path: /Users/federico/Documents/Personal-DEV/xgsail/frontend/src/components/session/SessionDetail.tsx
timestamp: 2026-10-06T09-55-00Z
slug: frontend-src-components-session-sessiondetail-tsx
---
# Critique: Session analysis (frontend/src/components/session/SessionDetail.tsx)

Method: dual-agent (A: design review · B: detector). The browser overlay was skipped: no browser tool was available.

## Score: 25/40 (Acceptable)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | On a phone, tapping a row scrolls the list away from the replay. |
| 2 | Match with the real world | 3 | "Polare media" has no referent; "Picco" next to "Raffica max" is ambiguous. |
| 3 | User control | 3 | Crew "Rimuovi" has no confirmation. |
| 4 | Consistency | 2 | Three visual languages (ranked sheet, stat tiles, stock Recharts); red means three things. |
| 5 | Error prevention | 2 | A 0.1 kn leg gap ranks with the same certainty as a 21 m tack. |
| 6 | Recognition over recall | 2 | Icon-only header buttons; the speed strip has no time axis. |
| 7 | Flexibility and efficiency | 2 | No next/previous loss and no filter. |
| 8 | Aesthetic and minimalist design | 2 | Below the fold: stacked heads and an empty polar. |
| 9 | Error recovery | 3 | Distance shows 0.00 at the replay start. |
| 10 | Help and documentation | 3 | |

## Specificity
- About 60% of the page belongs to the world and 40% is inherited dashboard.
- The first viewport is a signature.
- Below the fold, the KPI tiles and stock charts return.
- Detector: 0 findings.

## Priority issues
1. **[P1]** The dashboard returns below the fold. Fix: Bordi and Manovre as ruled tables, drop the maneuver bars, merge ANALISI/VENTO, and put the record under a quieter divider. → distill, layout
2. **[P1]** On mobile, going from a row to the replay is one-way. Fix: a sticky compact replay, or a loss stepper on the transport bar. → adapt
3. **[P1]** The ranking lists incidents, not habits. Fix: a verdict row grouped by code, and noise-threshold leg gaps. Possible overlap with maneuvers needs verifying (legs are cut at maneuvers in the worker). → clarify
4. **[P2]** The polar defaults to the lowest TWS bin; the speed strip has no loss markers. → clarify, bolder
5. **[P2]** Row button semantics, small map controls, red overloaded, unconfirmed crew removal. → harden, polish

## Personas
- **Club racer on a phone:** loses the list on every tap; the crew note and the data never meet; the page ends on admin.
- **Power user:** no stepping between losses and no filter; the tables are hidden while the charts are always open.
- **Screen reader user:** rows are not buttons; the current row is shown by colour only.

## Minor observations
- The map stops short of the table.
- Crew rows show email addresses.
- The demo energy series is a square wave.
- ABB vs "strambata" wording.
- The dark-theme tile luminance jump.

## Questions
- Bordi and Manovre as "show all" of the same sheet?
- End the page on a single "next outing" line?
