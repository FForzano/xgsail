---
name: XGSail
description: Sailing session analytics, set like the club results sheet pinned on the noticeboard.
colors:
  paper: "#f2f4f6"
  sheet: "#ffffff"
  paper-shade: "#e5e8ec"
  hairline: "#d1d6dc"
  ink: "#16181b"
  pencil: "#5a6068"
  results-blue: "#1f55a6"
  results-blue-deep: "#17468c"
  committee-red: "#b8262d"
  starboard-green: "#1d7346"
  protest-amber: "#95600a"
  graphite: "#131416"
  graphite-sheet: "#1d1f22"
  graphite-shade: "#282b2f"
  graphite-hairline: "#34383d"
  night-ink: "#e9eae6"
  night-pencil: "#a0a6ad"
  night-blue: "#84aef0"
  night-blue-ink: "#0d1726"
  night-red: "#f07272"
  night-green: "#5cc995"
  night-amber: "#e2b553"
  chrome-ink: "#16181b"
  chrome-ink-night: "#0c0d0e"
  chrome-text: "#f2f4f6"
  chrome-muted: "#a9aeb4"
  overlay: "rgba(22, 24, 27, 0.86)"
  overlay-night: "rgba(12, 13, 14, 0.86)"
  scrim: "rgba(10, 11, 13, 0.62)"
  tack-blue: "#2f9be0"
  course-change-green: "#3fbf7f"
  gybe-coral: "#e0654f"
  upwind-violet: "#9b6fe0"
  reach-teal: "#0e93a8"
  downwind-ochre: "#a5760a"
  mark-amber: "#e0b24a"
  tile-ring: "#ffffff"
typography:
  headline:
    fontFamily: "Archivo Variable, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "clamp(1.45rem, 1.2rem + 1vw, 1.9rem)"
    fontWeight: 750
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Archivo Variable, system-ui, sans-serif"
    fontSize: "1.15rem"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "0.02em"
    fontVariation: "'wdth' 72"
  section-title:
    fontFamily: "Archivo Variable, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "0.02em"
    fontVariation: "'wdth' 72"
  figure:
    fontFamily: "Archivo Variable, system-ui, sans-serif"
    fontSize: "1.3rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.01em"
    fontFeature: "'tnum' 1"
  day-numeral:
    fontFamily: "Archivo Variable, system-ui, sans-serif"
    fontSize: "4.5rem"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.02em"
    fontVariation: "'wdth' 72"
  body:
    fontFamily: "Archivo Variable, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "'tnum' 1"
  table:
    fontFamily: "Archivo Variable, system-ui, sans-serif"
    fontSize: "0.94rem"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "'tnum' 1"
  label:
    fontFamily: "Archivo Variable, system-ui, sans-serif"
    fontSize: "0.72rem"
    fontWeight: 750
    lineHeight: 1.35
    letterSpacing: "0.04em"
    fontVariation: "'wdth' 72"
rounded:
  bar: "1px"
  tag: "2px"
  sheet: "4px"
  circle: "50%"
spacing:
  hairline-gap: "0.25rem"
  cell-y: "0.55rem"
  cell-x: "0.75rem"
  block-gap: "0.75rem"
  section-gap: "1rem"
  page-pad: "1.25rem"
  lead-gap: "1.5rem"
  block-sep: "1.75rem"
components:
  button-primary:
    backgroundColor: "{colors.results-blue}"
    textColor: "{colors.sheet}"
    rounded: "{rounded.sheet}"
    padding: "0.45rem 1rem"
    height: "2.5rem"
  button-primary-hover:
    backgroundColor: "{colors.results-blue-deep}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.sheet}"
    padding: "0.45rem 1rem"
    height: "2.5rem"
  button-ghost-hover:
    backgroundColor: "{colors.paper-shade}"
  button-danger:
    backgroundColor: "{colors.committee-red}"
    textColor: "{colors.paper}"
    rounded: "{rounded.sheet}"
  code-tag:
    backgroundColor: "{colors.paper-shade}"
    textColor: "{colors.pencil}"
    typography: "{typography.label}"
    rounded: "{rounded.tag}"
    padding: "0.1rem 0.4rem"
  code-tag-regatta:
    backgroundColor: "color-mix(in srgb, #95600a 14%, transparent)"
    textColor: "{colors.protest-amber}"
    typography: "{typography.label}"
    rounded: "{rounded.tag}"
    padding: "0.1rem 0.4rem"
  field-input:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sheet}"
    padding: "0.5rem 0.7rem"
    height: "2.5rem"
  table-head:
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    padding: "0.45rem 0.75rem"
  table-cell:
    textColor: "{colors.ink}"
    typography: "{typography.table}"
    padding: "0.55rem 0.75rem"
  results-row-cell:
    textColor: "{colors.ink}"
    typography: "{typography.figure}"
    padding: "0.55rem 0.9rem 0.6rem"
  results-row-compact-cell:
    textColor: "{colors.ink}"
    typography: "{typography.figure}"
    padding: "0.4rem 0.9rem 0.45rem"
  logbook-entry:
    padding: "1rem 0 1.5rem"
  logbook-day-mark:
    textColor: "{colors.ink}"
    typography: "{typography.day-numeral}"
    width: "6rem"
  navbar:
    backgroundColor: "{colors.chrome-ink}"
    textColor: "{colors.chrome-muted}"
    height: "56px"
    padding: "0 1.25rem"
  actionbar:
    backgroundColor: "{colors.chrome-ink}"
    textColor: "{colors.chrome-muted}"
    height: "60px"
  map-overlay-control:
    backgroundColor: "{colors.overlay}"
    textColor: "{colors.chrome-text}"
    rounded: "{rounded.sheet}"
  map-control-chip:
    backgroundColor: "{colors.overlay}"
    textColor: "{colors.chrome-text}"
    rounded: "{rounded.sheet}"
    size: "36px"
  map-control-chip-hover:
    backgroundColor: "{colors.chrome-ink}"
  habit-bar:
    rounded: "{rounded.bar}"
    height: "8px"
  loss-tick:
    backgroundColor: "{colors.committee-red}"
    textColor: "{colors.paper}"
    rounded: "{rounded.bar}"
    size: "14px"
---

# Design System: XGSail

## Overview

**Creative North Star: "Bacheca dei risultati"**

XGSail is set like the results sheet the race committee pins on the club noticeboard after racing: paper and ink, ruled tables, condensed uppercase column heads, right-aligned tabular figures, and short uppercase codes in the manner of DNF and OCS. The ranking itself is the emphasis. A region of the page reads as a ruled block of the sheet, not as a box floating on a background, and a figure is something read down a column.

Light and dark are one system. Light is a cool paper-white ground with near-black ink; dark is the same sheet read at night, a graphite ground with paper-white ink. Every themed colour is redefined once for dark, so a component that reads only the shared tokens themes itself. The app chrome (top navbar on desktop, bottom action bar on phones) is an ink band in both themes, which frames the sheet the way the noticeboard frames the paper. Map tiles are the one surface the theme cannot touch, so everything drawn on them stays fixed.

Density is that of a printed table: hairline rules, tight cell padding, one weight family doing all the work through width and weight rather than through size jumps. The user explicitly rejected anything that reads as a SaaS dashboard: no grid of rounded KPI tiles, no soft cards on a tinted canvas.

Two surfaces are rebuilt in depth: the session analysis page, and the diary feeds set as a logbook (the personal diary, the "Circoli e gruppi" diary tab and a club's Eventi tab, which share one entry). The other areas (Gruppi beyond the club Eventi tab, Profilo, Registra, landing) currently inherit these tokens and the global primitives without having been recomposed; they are not yet expressions of the world beyond that inheritance.

**Key Characteristics:**
- Paper and ink, light and dark designed as one sheet.
- Ruled tables are the primary component: an ink rule under the head, hairlines between rows.
- Archivo set condensed and uppercase for headers, column heads, codes and labels; tabular figures everywhere.
- Corners at most 4px; circles only for avatars, map pins and on-water recording controls.
- Flat on the page; shadow only for what floats over a map or the page.
- An ink chrome band in both themes.

## Colors

Paper, ink and two working inks: committee red for what was lost, results blue for what can be followed or selected.

### Primary
- **Results Blue** (#1f55a6 light, Night Blue #84aef0 dark): links, focus rings, selection, the primary button, the active row of a ranked table, and the "show all" link under a table. Hover deepens to Results Blue Deep (#17468c light, #a3c3f5 dark). Text on a Results Blue fill is white in light and Night Blue Ink (#0d1726) in dark.

### Secondary
- **Committee Red** (#b8262d light, Night Red #f07272 dark): losses, penalties and destructive actions. It colours the metres-lost total and the loss share bars in "Dove hai perso", the numbered loss ticks on the speed strip, error text, danger buttons and the pending-upload dot. It is also the **port** half of every port/starboard comparison.

### Tertiary
- **Starboard Green** (#1d7346 light, Night Green #5cc995 dark): success states, confirmed toasts, and the **starboard** half of port/starboard comparisons.
- **Protest Amber** (#95600a light, Night Amber #e2b553 dark): warnings, pending rows, regatta badges, the tab count badge.

### Map categories (theme-invariant)
These sit on map tiles, which do not change with the theme, so they are defined once and never redefined for dark. The set was validated for colourblind separation against a light tile surface.
- **Tack Blue** (#2f9be0), **Course-change Green** (#3fbf7f), **Gybe Coral** (#e0654f): maneuver pins and their codes.
- **Upwind Violet** (#9b6fe0), **Reach Teal** (#0e93a8), **Downwind Ochre** (#a5760a): leg (point-of-sail) categories.
- The maneuver and leg colours also fill the Habit Strip's segments and the swatch that leads a loss code, so a habit, its rows and its pins read as one thing.
- **Mark Amber** (#e0b24a): race marks.
- **Tile Ring** (#ffffff): the 2px paper edge around anything laid on a map tile, today the photo inset on a diary entry's track render, so it reads as lying on the map rather than as a hole in it. Fixed for the same reason as the categories: the tile under it does not theme.

### Neutral
- **Paper** (#f2f4f6) / **Graphite** (#131416): the page ground. Also the browser theme colour for each scheme.
- **Sheet** (#ffffff) / **Graphite Sheet** (#1d1f22): inputs, modals, popovers, cards.
- **Paper Shade** (#e5e8ec) / **Graphite Shade** (#282b2f): tag fill, ghost hover, menu hover.
- **Hairline** (#d1d6dc) / **Graphite Hairline** (#34383d): row rules, cell dividers, card and field borders.
- **Ink** (#16181b) / **Night Ink** (#e9eae6): text, and the heavy rule under a table head or a block title.
- **Pencil** (#5a6068) / **Night Pencil** (#a0a6ad): secondary text, column heads in the ranked table, units, details.
- **Chrome Ink** (#16181b light, #0c0d0e dark) with **Chrome Text** (#f2f4f6) and **Chrome Muted** (#a9aeb4): the navbar and the mobile action bar.
- **Overlay** (rgba(22,24,27,0.86) light, rgba(12,13,14,0.86) dark): controls floating over a map (wind badge, playback bar, layer panel, popups). **Scrim** (rgba(10,11,13,0.62) light, rgba(0,0,0,0.7) dark) behind modals.

### Named Rules
**The Committee Red Rule.** Red means something was lost, penalised or destroyed. It is never decoration and never a brand accent.

**The Navigation Lights Rule.** Port is red and starboard is green, taken from the danger and success tokens, because it is the one colour pairing a sailor reads without a legend. Do not recolour a tack comparison.

**The Fixed Tile Rule.** The map category colours never change with the theme, and they are used as fills, swatches, pins and lines, never as text on the page ground.

**The Ink Band Rule.** The app chrome is an ink band in both themes. Light mode does not get a white navbar.

**The Plain Code Rule.** Kind and ownership codes (the activity type, crew, club, group) are plain code tags, Paper Shade with Pencil text, told apart by their words. A code says only what is not the diary's default: a solo outing carries no kind code and a personal entry no ownership code. The regatta code alone keeps a colour, the 14% Protest Amber tint, and a map category hue never becomes a tag colour.

## Typography

**Display Font:** Archivo Variable, with its width axis (with system-ui, -apple-system, Segoe UI, Roboto, sans-serif)
**Body Font:** Archivo Variable (same stack)

**Character:** one grotesque doing every job. Width does the work a second family would: the condensed cut (72% width) is the header row of the results sheet, the normal width is everything read as text or as a figure.

### Hierarchy
- **Headline** (750, clamp(1.45rem, 1.2rem + 1vw, 1.9rem), 1.15, -0.02em): the page title, normal width, sentence case. On a session it is the boat's name.
- **Title** (800, 1.15rem, condensed, uppercase, 0.02em): the title of a signature table such as "Dove hai perso".
- **Section Title** (800, 1rem, condensed, uppercase, 0.02em): every Section head; subsection heads inside analysis drop to 0.9rem with a 1px ink rule.
- **Figure** (700, 1.3rem, -0.01em, tabular): the values in a results row; the loss column in a ranked table is 1.15rem at 750 with its unit in Pencil at 0.8rem.
- **Day Numeral** (800, 4.5rem, condensed, -0.02em, line-height 1): the day in a logbook margin, between a weekday and a month in the condensed label cut (750, 0.8rem, uppercase, 0.06em, Pencil); 2.4rem on a phone with its labels at 0.68rem. The year follows in Pencil at 650 only for another season.
- **Body** (400, 1rem, 1.5): running text; table text at 0.94rem; table notes cap at 62ch.
- **Label** (750, 0.72rem, condensed, uppercase, 0.04em): column heads, results-row labels, stat labels, badges. Codes (VIR, BOL, TCK) are 800 at 0.72rem with 0.06em tracking.

### Named Rules
**The Header Row Rule.** The condensed uppercase cut belongs to things that head or classify: section titles, column heads, labels, codes and tags. Values, names and prose stay at normal width in sentence case.

**The Tabular Column Rule.** Tabular figures are on for the whole document, and figures in a table are right-aligned. Numbers never get a monospace face.

## Layout

The page sits in a centred column capped at 1180px with a 1.25rem side inset; wide pages drop the cap and the Registra map runs edge to edge. Page blocks stack in a 1rem column gap, a block's own head and content sit 0.75rem apart, and adjacent blocks add 1.75rem of air on top of that, separated by their 2px ink head rule rather than by boxes.

On the session page the lead is one ruled results row (duration, distance, average and max speed, polar, maneuvers), then from 1000px up a two-column grid of 5fr losses to 7fr replay (2rem gap), the replay sticky 1rem below the navbar while the ranking runs on beside it; below 1000px they stack, replay first and the ranking under it (the user's decision: the track is what confirms "this is that outing"), with 1.5rem between. Results-row cells auto-fit at a 7.5rem minimum; below 560px they go three to a line at a smaller figure size. Stat tiles run 4-up, 2-up below 700px. The ranked table drops its time column below 520px, since selecting a row seeks the replay there anyway. Below the lead the analysis is a stack of ruled sheet tables (legs, maneuvers), closed by the Next Outing block; the outing's record (health, wind, crew, notes, media) follows under a plain hairline with 2.25rem of air above it and no label.

The diary feeds read in a 760px column shared by the toolbar and the feed, so the two line up as one block. Each entry is a two-column grid: a 6rem date margin, a 1.5rem gap, then the entry. At 560px and below the margin narrows to 2.6rem (0.85rem gap) and holds only the stacked day numeral. The date mark sticks just below the navbar while its day scrolls past. A feed split in two (a club's upcoming and past events) heads each half with a Section Title and no rule of its own, 1.75rem above, because the first entry's ink rule sits right under it.

At 700px and below, the top navbar is replaced by the bottom action bar, section tabs stick to the top carrying the safe-area inset, and `.sf-bleed` cancels the page inset so maps and charts run edge to edge.

**The Table Stays a Table Rule.** On a phone (700px and below) a results table drops its optional columns and tightens its cells to 0.4rem; it never turns its rows into label/value tiles and never relies on a sideways scroll.

**The Ruled, Not Boxed Rule.** A page-level region is a Section: heading, actions, content, no border, surface or radius. A Card is reserved for one innermost discrete entity (one boat, one mark, one entry). A region listing card-shaped items is a Section of those items or of flat ruled rows, never a Card of Cards.

## Elevation & Depth

The page is flat. Depth on the sheet comes from rules (a 2px ink rule under a block head, 1.5px under a table head, 1px hairlines between rows and cells) and from the Paper/Sheet tonal step. Shadows exist only for things that physically float: popovers and menus over the page, the floating help button on phones, and controls over a map, including the photo inset laid on a diary entry's track render.

### Shadow Vocabulary
- **Pop** (`box-shadow: 0 6px 20px rgba(16, 18, 20, 0.16)` light, `0 6px 20px rgba(0, 0, 0, 0.5)` dark): popovers, comboboxes, options menus, the floating help button.
- **Map lift** (`box-shadow: 0 2px 8px rgba(0, 0, 0, 0.28)`): everything that floats on a map tile, the playback bar and the map control chips (zoom, recenter, options, layers) alike.

### Named Rules
**The Flat Sheet Rule.** Nothing that sits in the page flow casts a shadow. If an element needs a shadow, it is floating; otherwise it needs a rule.

**The Opaque Overlay Rule.** Controls over a map use the solid Overlay ink, not translucency or blur, because whatever tile sits behind them would otherwise decide their contrast.

## Shapes

Square-cornered with a hairline softening: 4px is the ceiling for buttons, fields, cards, modals, popovers, toasts and map overlays. Tags and codes are 2px; loss share bars, progress bars, code swatches, Habit Strip segments and the numbered loss ticks are 1px. Map controls are square chips at the 4px corner, never round. Circles are reserved for avatars, map pins and position markers, and the on-water recording controls in Registra, where a large round tap target is a safety feature. Active tabs and nav links are marked by a 2px underline in ink, not by a filled pill.

**The 4px Ceiling Rule.** No surface on the page rounds past 4px, and nothing on the page is a pill.

## Components

### Buttons
Plain, firm and small-cornered.
- **Shape:** sheet corner (4px), 2.5rem minimum height, 650 weight; small variant 2rem at 0.875rem.
- **Primary:** Results Blue fill with white text (Night Blue Ink in dark), 0.45rem by 1rem.
- **Hover / Focus:** hover deepens the fill; transitions run 0.15s ease-out on background, border and colour. Focus is a 2px Results Blue outline offset 2px, everywhere.
- **Ghost:** transparent with a hairline border and ink text; hover fills Paper Shade and darkens the border. Over a map the ghost takes the overlay's own ink.
- **Danger:** Committee Red fill with ground-coloured text, confirmations only.
- **Active toggle:** a 14% Results Blue tint with a Results Blue border and text.

### Chips / Tags
- **Style:** short uppercase codes in the condensed label cut, 2px corner, Paper Shade fill with Pencil text by default; status variants use a 14% tint of their status colour with that colour as text.
- **Kind and ownership codes:** plain code tags (see The Plain Code Rule); only the regatta code takes the Protest Amber tint. A solo outing shows no kind code and a personal entry no ownership code.
- **Loss codes:** in the ranked table a code is ink text led by a 1px-cornered square swatch in the matching map category colour, so a row and its pin read as one thing.

### Cards / Containers
- **Corner Style:** 4px.
- **Background:** Sheet on the Paper ground.
- **Shadow Strategy:** none (see The Flat Sheet Rule).
- **Border:** 1px Hairline; hover on a tappable card raises the border to ink.
- **Internal Padding:** 1rem by 1.25rem.

### Inputs / Fields
- **Style:** Sheet fill, 1px border mixed 22% toward ink, 4px corner, 2.5rem height; label above in Pencil at 0.85rem, 650.
- **Focus:** 2px Results Blue outline, inset by 1px.
- **Error:** Committee Red text under the field.

### Tables
The primary component of the world.
- **Head:** ink text in the condensed label cut, uppercase, over a 1.5px ink rule; no fill.
- **Rows:** 0.55rem by 0.75rem cells over 1px hairlines; hover tints 4% toward ink; a clickable row gets a focus outline inset 2px and a faint trailing chevron.
- **Figures:** right-aligned, tabular.
- **Sheet tables** (the analysis's legs and maneuver summary): figure columns right-aligned with their heads sharing the same right edge; a kind cell is led by its map category swatch. At 700px and below the optional columns (average and max speed, distance; a maneuver's duration) drop out and cells tighten to 0.4rem (see The Table Stays a Table Rule).

### Navigation
- **Desktop:** a 56px Chrome Ink navbar. Links are Chrome Muted at 650, turning Chrome Text on hover; the active link carries a 2px Chrome Text underline. The tour help button sits in this bar as a quiet icon before the profile avatar.
- **Section tabs:** muted text over a 1px hairline; the active tab turns ink with a 2px ink underline. On phones the bar sticks to the top; the tabs scroll in their own strip and the help button sits beside that strip at the bar's end, reserving its 2.25rem, so it never covers the last tab. At 560px and below the tabs close their gap and drop to 0.5rem side padding.
- **Mobile:** a 60px Chrome Ink bottom action bar, icon over a 0.72rem label, active item in Chrome Text.

### Results Row
One shared ruled line of labelled figures, the row a results sheet prints for each boat. A 2px ink rule above, a hairline below, cells divided by vertical hairlines with the first cell flush left; each cell is a condensed uppercase Pencil label over a Figure value. Two sizes:
- **Default:** the page header of a session, its totals. Cells auto-fit at 7.5rem; below 560px they go three to a line at 1.02rem.
- **Compact:** a logbook entry's figures. A hairline above instead of the 2px ink rule, because ink is reserved for the day and section rules; tighter cells (0.4rem top), auto-fit at 5.5rem (4.75rem on a phone), and it stays on one line on a phone, because wrapping would split the entry.
Stat tiles use the same vocabulary one step quieter (hairlines top and bottom, 1.1rem values).

### Logbook Entry
The signature of the diary feeds: each outing or regatta is a dated entry in a logbook, never a social-feed card.
- **Date margin:** the Day Mark (weekday, Day Numeral, month; the year only for another season) in the left column, printed once per day.
- **Day rule:** the first entry of a day opens under a 2px ink rule; a second entry the same day sits under a 1px hairline with its margin empty.
- **Head:** the title (700, 1.2rem, sentence case, underlined on hover) with its codes beside it; at 560px and below the codes always sit under the title.
- **Track:** the track render at full column width in a 4:3 box (Paper Shade, hairline border, 4px corner, border to ink on hover), `contain`-fitted so the whole route shows. A photo is a 2px-cornered inset at the bottom right (28% wide, at most 150px) ringed in Tile Ring with a soft lift; a photo takes the main slot, `cover`-fitted, only when there is no track. With no image at all there is no box; an outing that has already started says "Nessuna traccia registrata" in Pencil at 0.9rem instead, and a scheduled one says nothing.
- **Figures:** a compact Results Row: start time, duration, and distance, or the session count when an outing holds several. A regatta prints its date range instead ("27–28 ott"), the month and year said once.
- **Description:** shown only while the event is still ahead, in Pencil at 0.92rem, two lines at most, 65ch.
- **Race days:** a small ghost toggle with a trailing chevron that flips with its state.
- **Feed error:** ruled like an entry (2px ink rule above, hairline below), a Pencil message and a small ghost "Riprova".
- **Start checklist:** at the head of the personal diary, its step CTAs are small ghost buttons. Once an outing exists it folds to one line (a progress count and a chevron to reopen it); it is hidden while the feed is in error.

**The One Margin Per Day Rule.** A day is printed once, in the margin of its first entry. A new day starts under the ink rule; everything else that day sits under a hairline.

### Ranked Loss Table ("Dove hai perso")
The signature component. A condensed uppercase title over a 2px ink rule, with the total metres lost in Committee Red at the right. Below, a table with a rank column (800, condensed), the event (category code, name, a Pencil detail line, and a 2px share bar filled in Committee Red against a hairline track to show the drop-off from the worst loss), the time, and metres lost right-aligned. Every row is a button into the replay; the row under the replay cursor is tinted 10% Results Blue with its rank in Results Blue. Five rows show by default; a Results Blue underlined text link expands the rest. A leg whose VMG is within 0.2 kn of the best leg is not ranked: that gap is inside what the data can resolve.
- **Habit Strip:** heads the table, between the title rule and the column heads, over a hairline. One lead sentence (650, 1.05rem) names the habit that cost most, with its count, metres and share; under it one 8px bar split by kind (2px gaps, 1px corners, 4px minimum segment) in the fixed map category colours; then a key of codes with their percentages, swatch in colour and text in Pencil.
- **Loss Stepper:** rides on the replay's overlay playback bar, set apart by a 1px rule at 28% of the overlay text: a previous and next ghost button around a tabular count, "6 perdite" at rest and "n/N" once stepping. Each step pauses and seeks to that loss. At 560px and below, a bar carrying it drops its fine-step and speed buttons.
- **Loss ticks:** the five worst losses are numbered on the speed strip in ranking order, a dashed 1px Committee Red line under a 14px Committee Red square holding the rank in the ground colour. The playback cursor on the strip is page ink, not white.

**The Same Number Rule.** A loss carries one number everywhere: its rank in the table, its tick on the speed strip, its step on the replay bar.

### Next Outing ("Da allenare alla prossima uscita")
Closes the analysis like the bottom line of the sheet: a 2px ink rule, the title in the Section Title cut, then one sentence at 700, clamp(1.25rem, 1.05rem + 0.9vw, 1.6rem), 40ch, led by the habit's code with its category swatch; the numbers behind it follow in Pencil at 0.95rem. A session with nothing ranked says so in the same large sentence.

### Map Overlays
Wind badge, playback bar, layer panel and track popups share the Overlay ink with Chrome Text, a 4px corner and tabular 650 figures, reading the same over any tile in either theme.
- **Control chips:** zoom, recenter, options and the layers toggle are square chips on the same Overlay ink with Map lift: zoom buttons 32px, stacked and divided by a rule at 18% of the overlay text; the others 36px. Hover turns them Chrome Ink. On the replay map at 560px and below the bottom-right chips lift 3.5rem clear of the playback bar.

## Do's and Don'ts

### Do:
- **Do** separate page regions with a 2px ink rule under a condensed uppercase title, and rows with 1px hairlines.
- **Do** set every figure tabular and right-align figures in a table.
- **Do** use Committee Red only for loss, penalty, port and destructive actions, and Results Blue for links, focus and selection.
- **Do** redefine any new themed colour in both dark blocks (the OS preference block and the explicit `data-theme="dark"` block).
- **Do** keep map category colours fixed across themes and match a table code's swatch to its map pin colour.
- **Do** put controls that float over a map on the solid Overlay ink.
- **Do** keep a results table a table on a phone by dropping its optional columns.
- **Do** give a loss the same number in the ranking, on the speed strip and on the replay's stepper.
- **Do** set a feed of dated outings as a logbook: one date margin per day, a 2px ink rule opening the day, the track at full column width and a compact Results Row beneath it.

### Don't:
- **Don't** compose a screen as a grid of rounded KPI tiles or soft cards; the user rejected the SaaS-dashboard look.
- **Don't** round anything past 4px or make a pill; circles are only for avatars, map pins and Registra's on-water controls.
- **Don't** nest a Card inside a Card or box a page region; use a Section.
- **Don't** use a map category colour as text on the page ground.
- **Don't** set figures in a monospace face or use translucent, blurred panels over a map.
- **Don't** give the chrome a light fill in light mode.
- **Don't** put a placeholder box where an entry has no image, or a text preview on a past entry.
- **Don't** colour a kind or ownership code; the regatta's amber is the only coloured code.
- **Don't** turn a table's rows into label/value tiles on a phone, or make a map control round.
