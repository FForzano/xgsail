---
version: 1
slug: "frontend-src-pages-diario-mydiarypage-tsx"
primary_target: "frontend/src/pages/diario/MyDiaryPage.tsx"
related_targets: ["frontend/src/components/diario/EventRow.tsx","frontend/src/pages/diario/ClubsDiaryPage.tsx","frontend/src/pages/gruppi/ClubEvents.tsx"]
---

# Surface brief: Diary feed

Scope: the personal diary (`MyDiaryPage`) and the two feeds that share its row: the "Circoli e gruppi" diary tab (`ClubsDiaryPage`) and the club Eventi tab (`ClubEvents`). Mode: Operate. The world is settled in DESIGN.md (Bacheca dei risultati); this brief only covers composition.

Audience and job: a club racer reopening a recent outing to analyse it, on a phone or a laptop.

Constraints:
- The track render stays the hero of each outing.
- Live-recording, upcoming, toolbar, progress and start-checklist blocks keep their behaviour.
- Regattas keep the race-days toggle; clubs keep the announce action.
- Guided-tour anchors (`diario-feed`) stay.
- EN/IT copy; WCAG 2.2 AA; light and dark.

Description: an entry shows its description only while the event is still ahead. That is where an organiser puts logistics (meeting time, briefing) in the club Eventi feed. A past outing's notes are one tap away on its own page, so the logbook keeps no text preview, per the THESIS.

The date mark prints the year only for a past season.

Data: activity list payloads now carry `session_count`, plus `distance_m`/`duration_s` for a one-session activity.

## Direction contract

THESIS:
- The diary is a logbook: each outing is a dated entry, with the day set large in a margin column and the track and its results line beside it.
- It refuses the category default, a social-feed card stack with a cover image, pills and a text preview.

OWN-WORLD: the established results-sheet world.
- Paper and ink.
- The date margin set in condensed caps with a large day numeral.
- Results figures in a ruled line with condensed caps labels.
- Square codes for kind and ownership.
- 4px corners. No card surfaces and no shadows.

STORY: the newest outing is the first entry. The sailor recognises it by its track and date, sees its time, duration and distance, and taps it to open the analysis.

FIRST VIEWPORT:
- Live/upcoming banners, then the toolbar, then progress.
- Then the first day: the margin shows weekday, day numeral and month.
- To its right:
  - the entry title and codes;
  - the track render, full column width at 4:3;
  - one ruled results line: start time, duration, distance, and sessions when there are several.
- Entries on the same day share the margin. A new day starts under an ink rule.
- On a phone the margin narrows to a stacked day numeral.

FORM: Giornale con margine delle date. Dealt index 3 of my ordered list (lead card, THE ROLL); seed key 22e1a1ec.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
