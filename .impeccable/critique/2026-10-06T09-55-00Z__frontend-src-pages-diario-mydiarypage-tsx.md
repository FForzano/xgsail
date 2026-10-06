---
target: frontend/src/pages/diario/MyDiaryPage.tsx
total_score: 27
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 2
target_identity: "file:/Users/federico/Documents/Personal-DEV/xgsail/frontend/src/pages/diario/MyDiaryPage.tsx"
target_fingerprint: "sha256:d0dee513c67330135480786b56bc0c1b0d934e3c858d8bf9c6f2746a2b37579c"
target_path: /Users/federico/Documents/Personal-DEV/xgsail/frontend/src/pages/diario/MyDiaryPage.tsx
timestamp: 2026-10-06T09-55-00Z
slug: frontend-src-pages-diario-mydiarypage-tsx
---
# Critique: Diary feeds (frontend/src/pages/diario/MyDiaryPage.tsx, ClubsDiaryPage, ClubEvents)

Method: dual-agent (A: design review · B: detector). The browser overlay was skipped: no browser tool was available.

## Score: 27/40 (Good)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | No processing / no-wind state on an entry. |
| 2 | Match with the real world | 3 | "nm" vs "mn"; the USCITA code doesn't match the filter types. |
| 3 | User control | 3 | The toggle reads only "Chiudi". |
| 4 | Consistency | 2 | Code placement varies; an ink rule sits over every figure line. |
| 5 | Error prevention | 3 | Today's description disappears at the start minute. |
| 6 | Recognition over recall | 3 | Import is hidden in ⋮. |
| 7 | Flexibility and efficiency | 2 | No season/month jump and no search. |
| 8 | Aesthetic and minimalist design | 3 | USCITA · PRIVATA repeated. |
| 9 | Error recovery | 2 | A fetch failure reads as an empty log. |
| 10 | Help and documentation | 3 | |

## Specificity
- Achieved: the date margin, the day rule and the track as the hero.
- Detector: 0 findings on this surface (ProgressPage side-tab is out of scope and real).

## Priority issues
1. **[P1]** The ink rule is overused: the compact ResultsRow top border competes with the day rule. → polish
2. **[P1]** On a phone, the StartChecklist takes the first viewport. → distill, onboard
3. **[P2]** Codes carry no information (PRIVATA on the personal tab, generic USCITA). → distill
4. **[P2]** Header code placement is inconsistent; the "Chiudi" label. → polish, clarify
5. **[P2]** No error/offline state; no "track processing / no track" line. → harden

## Personas
- **Racer at the marina:** the checklist pushes the race below the fold; an error reads as a lost upload.
- **Race officer:** an announce action on past events.
- **Three-season sailor:** no jump to a season; the year shows only on past seasons.

## Questions
- A season-total closing rule?
- Should the newest entry lead?
