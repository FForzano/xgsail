---
target: session detail
total_score: 21
max_score: 40
na_heuristics: 
p0_count: 1
p1_count: 2
target_identity: "file:/Users/federico/Documents/Personal-DEV/xgsail/frontend/src/components/session/SessionDetail.tsx"
target_fingerprint: "sha256:7d11deaa3f32d9f12442cd2b1c2072e165790e82d48b42234d5f6df375e895ad"
target_path: /Users/federico/Documents/Personal-DEV/xgsail/frontend/src/components/session/SessionDetail.tsx
timestamp: 2026-10-12T13-18-42Z
slug: frontend-src-components-session-sessiondetail-tsx
---
Method: dual-agent (A: design review, opus · B: detector, haiku). Browser visualization skipped: no browser tool in session; source-only review.

# Session detail — 21/40 (Acceptable)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 2 | `SessionAnalysis` returns null while analysis is pending (SessionAnalysis.tsx:85); status badge prints raw enum `processed` (SessionDetail.tsx:892) |
| 2 | Match system / real world | 3 | Real sailing vocabulary, port/starboard colours; let down by English enum and "Playback" fallback |
| 3 | User control and freedom | 2 | Crew "Rimuovi" unguarded, no undo; maneuver placement mode has no visible cancel |
| 4 | Consistency and standards | 2 | Stats as tiles, sf-table and a boxed WindCard; WindCard breaks Section-not-Card; English aria-labels |
| 5 | Error prevention | 2 | Crew role select changes on one tap and looks like a badge |
| 6 | Recognition rather than recall | 2 | Leg/maneuver pins off by default, buried ⋮ → Mostra su mappa → Andature |
| 7 | Flexibility and efficiency | 2 | No section jumps, no keyboard scrubbing |
| 8 | Aesthetic and minimalist design | 2 | 14 stacked regions; wind shown three times; crew emails visible |
| 9 | Error recovery | 2 | No-wind explainer has a recovery action, but mutations fall back to errors.generic |
| 10 | Help and documentation | 2 | Tour exists; polar/VMG/TWA unexplained for a non-technical reader |

Design specificity: authored components (tack comparison, own-polar optimal angles, speed-coloured track, gust band) inside a generic dashboard stack. Analysis — the core value — renders last (SessionDetail.tsx:1157), after stats, HealthCard, WindCard, crew, notes, photos, videos. No verdict, no hero. Title reads like a DB row.

Cognitive load: 5/8 fail (high): single focus, chunking (14 regions; ⋮ menu up to 9 items), grouping (summary split from Analisi by crew/media), hierarchy (uniform 0.8rem eyebrows; analysis subtitles smaller at 0.72rem), minimal choices (⋮ 9 items; 6 unlabeled header icons).

Strengths: tack comparison (AnalysisLegs.tsx:80–176); synthesis first, raw rows behind 44px count toggles; one time cursor drives map/charts/tiles with tabular numbers.

Priority issues:
- [P0] Analysis last and silently absent while pending → summary strip + verdict under title, Analisi right after replay, crew/media after, "Analisi in preparazione" state. layout, onboard.
- [P1] Replay/charts inaccessible; English aria-labels (Timeline.tsx:25,39,46; Menu.tsx:105; OptionsMenu.tsx:29); raw enum; unlabeled role select. harden.
- [P1] Touch targets under 44pt: sf-btn--icon-sm 34px, transport ~30px, map zoom 22px. adapt.
- [P2] Redundant summaries: cursor tiles look like totals; WindCard duplicates WindBadge and WindChart. distill.
- [P2] No hero, uniform flat sections, pins off by default, no speed legend. bolder, typeset.

Persona red flags: Casey — 45vh map captures scroll, unlabeled icons, small transport. Sam — no chart text alternatives, no keyboard seek, heading jumps h1→h2→h4→h5, 0.72rem/opacity .8 labels. Giulia — "Laser — 12/10/2026 10:04 processed", first numbers VMG/TWA at cursor zero, no-wind paragraph reads like a log, merged-track status hidden in ⋮, sees crew emails (SessionDetail.tsx:1043).

Minor: 4-col stats table overflows at 360px; "Clicca sulla traccia" on touch; empty crew "Nessuno"; 1295-line component; spinner not skeleton; desktop wastes width.

Questions: one-sentence verdict first? Replay as a focused full-screen mode so the page reads as a story? Different order for recorder vs clubmate?
