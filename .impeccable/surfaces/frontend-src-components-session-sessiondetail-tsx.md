---
version: 1
slug: "frontend-src-components-session-sessiondetail-tsx"
primary_target: "frontend/src/components/session/SessionDetail.tsx"
related_targets: ["frontend/src/components/session/SessionAnalysis.tsx"]
---

# Surface brief: Session analysis

Scope: the session detail page (`SessionDetail.tsx` + `SessionAnalysis.tsx` and its siblings). This is the first surface of a replacement visual world for the whole app. Mode: Operate.

Audience and job: a club racer, ashore after sailing, on a phone or laptop. The question the page must answer first is "dove posso migliorare?" (where can I improve?).

Constraints:
- EN/IT copy at equal length.
- WCAG 2.2 AA.
- Light and dark themes designed together.
- Must not read as a SaaS dashboard (user's explicit rejection).
- Standard controls only; existing behaviour, permissions and demo/tour hooks (`data-tour`) are untouched.

Unresolved: how the remaining surfaces (Diario lists, Gruppi, Profilo, Registra, landing) adopt the world. That comes in follow-up extensions.

## Direction contract

THESIS:
- The session reads like the results sheet pinned on the club noticeboard: a ranking of where time and distance were lost, worst first, set in tabular type.
- It refuses the category default of a map hero plus a grid of KPI tiles and charts.

OWN-WORLD:
- Light: a cool paper-white ground and near-black ink. Committee red marks losses and penalties. Results blue marks links, focus and selection.
- Dark: the same sheet at night, with a graphite ground and paper-white ink.
- Tables are the primary component: hairline rules, condensed uppercase column heads, right-aligned tabular figures.
- Codes are short uppercase tags, like DNF/OCS.
- No cards and no rounded tiles. Radius is at most 4px.

STORY:
- The sailor opens the session and immediately sees a ranked list of losses: maneuvers by metres lost, and legs by VMG gap to their best leg of the same kind.
- Each row jumps the replay to that moment. They understand what to practise.

FIRST VIEWPORT:
- Standard app shell.
- A header line: boat, date, duration, distance, average and max speed, as one ruled results row.
- Below it, on desktop, two columns:
  - left: "Dove hai perso" (where you lost), headed by a habit line (the costliest habit, plus one bar split by kind), then the top 5 losses ranked;
  - right: the replay map.
- On a phone the replay comes FIRST and the ranking follows. This is the user's decision: they arrive from a diary entry whose picture is the track, and the map must be there. A ‹ n/N › loss stepper on the replay bar walks the ranking without scrolling.
- The primary action is a tap on a loss row, or the stepper.
- The analysis closes on "Da allenare alla prossima uscita" before the quieter outing record.

FORM: Bacheca dei risultati, position 1 on my ordered list (IMPECCABLE'S PICK), seed key 202b38ba.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
