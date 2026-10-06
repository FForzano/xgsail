---
target: frontend/src/pages/registra
total_score: 25
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 3
target_identity: "file:/Users/federico/Documents/Personal-DEV/xgsail/frontend/src/pages/registra"
timestamp: 2026-10-06T07-57-58Z
slug: frontend-src-pages-registra
---
# Critique: Registra (frontend/src/pages/registra + components/registra)

Method: dual-agent (A: design review · B: detector). Browser overlay skipped: no browser automation tool.

## Design Health Score: 25/40 (Acceptable)
| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 2 | Paused uses the green success badge. Elapsed time counts paused time. After Stop, the only signal is a 7px dot on a red button. |
| 2 | Match with the real world | 3 | Right domain language (mure, start-timer presets, Sync). "Standalone outing" is app-speak. |
| 3 | User control and freedom | 2 | Stop on the map panel has no confirmation. Deleting a local track and Reset on the timer have no confirm or undo. |
| 4 | Consistency | 2 | Start is a red FAB, then a blue circle. Stop is confirmed in nav mode but not on the panel. Elapsed time is m:ss on the panel but formatted with hours in nav mode. |
| 5 | Error prevention | 2 | Pause is one tap, 0.75rem from Stop. Delete sits next to Upload for a track that hasn't been uploaded. |
| 6 | Recognition over recall | 2 | Start, Pause and Stop are icon-only. Hold-to-exit is hard to discover. |
| 7 | Flexibility and efficiency | 3 | Remembers the last boat, join prefill, timer presets, landscape layout. |
| 8 | Aesthetic and minimalist design | 3 | Nav mode is disciplined. The sheet is cluttered: battery paragraph, a select on every row, the offline sentence in a pill. |
| 9 | Error recovery | 3 | The GPS modal and interrupted rows are honest. Upload errors show raw, untranslated e.message. |
| 10 | Help and documentation | 3 | The tour covers recording. The "?" button floats over the recording panel. |

## Design specificity
- **Nav mode** is authored for the water: true black, tabular numerals, readings that dim when stale instead of blanking, hold-to-exit, start timer with Sync, tack colours that are safe for colourblind readers. This is the best surface in the app.
- **The default recording screen** could be any app: a browse map that neither follows the boat nor draws the track, plus a small navy card with a 1.25rem timer.
- **Detector:** 0 findings (exit 0) on both directories. The real problems here are behavioural and state problems, which the scanner can't see.

## Priority issues
1. **[P1] Pause and Stop are unsafe, and pause is easy to miss.**
   - Stop on the panel isn't confirmed.
   - Pause sits right next to Stop.
   - Paused is shown with the green success badge, and in nav mode only as small text.
   - The clock counts paused time.
   - Fix: make Stop a hold everywhere, separate Pause from Stop, add an unmissable amber paused band, and freeze or relabel the clock. → harden
2. **[P1] One tap deletes a track that was never uploaded.**
   - There's no confirmation and no undo.
   - Delete sits next to Upload and stays enabled while uploading.
   - Fix: confirm (or undo toast) when not uploaded, move Delete away from Upload, disable it while uploading. → harden
3. **[P1] The default recording screen isn't an on-water screen.**
   - The map doesn't follow the boat or draw the track, and all overlay layers are on.
   - An m:ss clock with no hours shows a 2h outing as "125:03".
   - The panel hard-codes rgba/#fff colours.
   - The "?" button overlaps the panel.
   - Instruments only appear behind an opt-in button.
   - Fix: open nav mode automatically on Start (or remember the last choice); otherwise follow position, draw the track, show an instrument-scale clock and SOG, quieten the layers, and hide the tour button while recording. → adapt
4. **[P2] The session ends in silence.**
   - There's no feedback after Stop, and a successful upload disappears without a word.
   - The pending-upload dot is red on a red button.
   - Errors are raw text, timestamps aren't localized, and the boat name can fall back to a UUID.
   - Fix: an end card ("Saved · 1h 42m → uploading" then "Uploaded, open session"), a contrasting count badge, and EN/IT error copy. → clarify, delight
5. **[P2] Nav mode isn't glove- and glare-sized everywhere.**
   - Timer presets, Sync and Reset are 44px, below the 3.25rem rule, and Reset sits next to Sync.
   - Labels are 0.7rem.
   - The confirmation dialog is app-sized.
   - Likely countdown overflow on a 375×667 screen with the timer armed (inferred, not verified).
   - → layout, typeset

## Persona red flags
- **Giulia (ILCA/420 racer, gloves, chop):** 44px timer presets with Reset beside Sync during the start sequence; an accidental pause is almost invisible; 0.7rem labels in glare.
- **Casey (one-handed):** the start button is icon-only and right-aligned in a scrolling sheet that doesn't use the BottomSheet footer; 22px zoom controls; the "?" button sits in the thumb zone.
- **Sam (screen reader):** icon-only states; no live region on nav-mode status; the X can't be activated with Enter or Space; BottomSheet's close button has an English-only aria-label.

## Minor observations
- Red FAB versus blue start: pick one colour.
- The offline sentence is crammed into a pill; it should be a callout.
- The battery paragraph appears on every start.
- "Link to" select appears even on empty interrupted rows.
- The sheet has no bottom safe-area padding when there's no footer.
- The wind hint wraps to 3 lines at 0.7rem.
- GPS "poor" and "lost" are near-identical hues.
- No haptic or audio cue in the countdown.

## Questions
- Why is nav mode a place you go, instead of simply what recording looks like?
- If Exit is a hold, should Stop and Pause be holds too?
- Is the true-black nav mode already the start of the sunlight theme?
- What should the 30 seconds after Stop feel like?
