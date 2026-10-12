---
name: XGSail
description: Next-Gen Sailing Analytics
colors:
  night-harbour: "#0b1f33"
  harbour-deck: "#10283f"
  hull-surface: "#14324d"
  hull-surface-raised: "#1b3e5e"
  rigging-line: "#26506f"
  sail-white: "#eaf2f8"
  sea-mist: "#9fb6c9"
  chart-blue: "#2f9be0"
  chart-blue-bright: "#47abec"
  chart-blue-ink: "#04263c"
  distress-red: "#e05a5a"
  starboard-green: "#3fbf7f"
  signal-amber: "#e0b24a"
  gybe-coral: "#e0654f"
  leg-upwind-violet: "#9b6fe0"
  leg-reach-teal: "#0e93a8"
  leg-downwind-ochre: "#a5760a"
typography:
  display:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "clamp(1.8rem, 4vw, 2.6rem)"
    fontWeight: 700
    lineHeight: 1.25
  headline:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1.3rem"
    fontWeight: 800
    lineHeight: 1.25
  title:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1.05rem"
    fontWeight: 700
    lineHeight: 1.25
  body:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  body-dense:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.92rem"
    fontWeight: 400
  label:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.85rem"
    fontWeight: 600
  eyebrow:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.8rem"
    fontWeight: 800
    letterSpacing: "0.07em"
  readout:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1.05rem"
    fontWeight: 600
    fontFeature: "tnum"
  caption:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 700
rounded:
  xs: "4px"
  sm: "6px"
  md: "10px"
  pill: "999px"
  circle: "50%"
spacing:
  xs: "0.35rem"
  sm: "0.5rem"
  md: "0.75rem"
  lg: "1rem"
  page: "1.25rem"
  block: "1.5rem"
components:
  button-primary:
    backgroundColor: "{colors.chart-blue}"
    textColor: "{colors.chart-blue-ink}"
    rounded: "{rounded.md}"
    padding: "0.5rem 1rem"
  button-primary-hover:
    backgroundColor: "{colors.chart-blue-bright}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.sail-white}"
    rounded: "{rounded.md}"
    padding: "0.5rem 1rem"
  button-ghost-hover:
    backgroundColor: "{colors.hull-surface}"
  button-danger:
    backgroundColor: "{colors.distress-red}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "0.5rem 1rem"
  button-icon:
    rounded: "{rounded.circle}"
    size: "3.25rem"
  card:
    backgroundColor: "{colors.hull-surface}"
    rounded: "{rounded.md}"
    padding: "1rem 1.25rem"
  stat-tile:
    backgroundColor: "{colors.hull-surface}"
    rounded: "{rounded.md}"
    padding: "0.5rem 0.6rem"
    typography: "{typography.readout}"
  input:
    backgroundColor: "{colors.harbour-deck}"
    textColor: "{colors.sail-white}"
    rounded: "{rounded.md}"
    padding: "0.5rem 0.7rem"
  badge:
    backgroundColor: "{colors.hull-surface-raised}"
    textColor: "{colors.sea-mist}"
    rounded: "{rounded.pill}"
    padding: "0.15rem 0.55rem"
    typography: "{typography.caption}"
  tab:
    textColor: "{colors.sea-mist}"
    padding: "0.55rem 1rem"
  tab-active:
    textColor: "{colors.sail-white}"
  navbar:
    backgroundColor: "{colors.harbour-deck}"
    height: "58px"
  actionbar:
    backgroundColor: "{colors.harbour-deck}"
    textColor: "{colors.sea-mist}"
    height: "60px"
---

# Design System: XGSail

## Overview

**Creative North Star: "Crew Instruments"**

XGSail is a set of pro-grade sailing instruments made friendly and shared. The numbers have to read like marine electronics: tabular figures, honest units, colour that means something. But they live inside a social app a club follows, closer to Strava than to a chart plotter. A session opens like a logbook entry your crew can see, and underneath sit readouts precise enough to trust.

The incumbent world is dark-first and single-theme: a deep navy harbour at night, with one chart-blue signal carrying interaction and a small categorical palette reserved for what is drawn on maps and charts. Density is high, as in an instrument panel, with a compact type scale (mostly 0.7–1.05rem) and tight gaps (0.5–1rem). Structure comes from tonal layering and hairline borders, not boxes floating over a page. Components should feel **sporty and confident**: bold weights (600–800), clear hit areas and a decisive primary action.

The flat, tonal surface treatment is what exists today, not a stated preference. The owner wants a more contemporary feel, in line with current app trends. That is an open direction for a later redesign pass (see Do's and Don'ts). This file describes the shipped system until that pass replaces it.

**Key Characteristics:**
- Dark-first, single theme (navy at night); no light theme exists yet.
- One interactive accent (Chart Blue); status and categorical colours never stand in for it.
- Instrument density: compact type, tabular numbers on anything that ticks.
- Flat tonal layers + 1px rigging-line borders; shadows only on floating panels.
- One corner radius (10px) for nearly everything, pills for badges, circles for icon buttons.
- Phone-first shell: top navbar on desktop, bottom action bar ≤700px.

## Colors

A night-harbour navy ramp with one bright chart-blue signal, three status hues, and a small CVD-validated categorical set for map and chart marks.

### Primary
- **Chart Blue** (`chart-blue`): the one interactive colour: primary buttons, links, the active tab underline, focus outlines, the active action-bar item, progress fills, section eyebrows. Tints of it (12–30% via `color-mix`) mark selected/active rows and buttons.
- **Chart Blue Bright** (`chart-blue-bright`): hover state of the primary button only.
- **Chart Blue Ink** (`chart-blue-ink`): text on a Chart Blue fill. Never plain white on the primary.

### Secondary (status)
- **Starboard Green** (`starboard-green`): success badges and states; doubles as the course-change map mark.
- **Signal Amber** (`signal-amber`): warnings, pending rows (10–16% tint), the regatta badge, the admin nav link, tab count badges.
- **Distress Red** (`distress-red`): destructive buttons, form errors, the pending-upload nav dot.

### Tertiary (categorical marks)
Validated for colour-vision safety against a light map-tile surface. They exist for what is drawn on maps and charts and are reused as badge tints for entity kinds.
- **Gybe Coral** (`gybe-coral`): gybe markers.
- **Leg Upwind Violet** (`leg-upwind-violet`): upwind legs; the activity badge.
- **Leg Reach Teal** (`leg-reach-teal`): reaching legs; the club badge.
- **Leg Downwind Ochre** (`leg-downwind-ochre`): downwind legs; the group badge.
- Tacks reuse Chart Blue; course changes reuse Starboard Green.

### Neutral
- **Night Harbour** (`night-harbour`): page background, and the sticky tab bar's backing on phones.
- **Harbour Deck** (`harbour-deck`): app chrome (navbar, action bar), input wells, thumbnail backings.
- **Hull Surface** (`hull-surface`): cards, stat tiles, menus, ghost-button hover.
- **Hull Surface Raised** (`hull-surface-raised`): the active nav link, dropdown lists, neutral badges, inline edit inputs.
- **Rigging Line** (`rigging-line`): every border and divider; at 50% for table row rules.
- **Sail White** (`sail-white`): primary text.
- **Sea Mist** (`sea-mist`): secondary text, labels, inactive tabs and nav items, table headers.

### Named Rules
**The One Signal Rule.** Chart Blue is the only colour that means "you can act here." Status hues report state; categorical hues name things on a map. Neither is used as a second accent for buttons or links.

**The Tint, Not Fill Rule.** Badges and highlighted rows use a 10–25% `color-mix` tint of their hue behind full-strength text of the same hue. Solid status fills are reserved for the destructive button.

**The Token-Only Rule.** Feature CSS Modules read `var(--sf-*)`. The few raw values that remain (`#47abec` hover, `#fff` on danger, `#1a1a1a` on amber badges) are known debt, not precedent.

## Typography

**Body Font:** the platform system UI stack (`system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`)
**Display / Label Font:** same stack; hierarchy comes from weight, size and case, not a second family.

**Character:** native and fast, so on iOS and Android it reads as the platform's own voice. Personality comes from heavy weights (700–800) and the uppercase eyebrow.

### Hierarchy
- **Display** (700, `clamp(1.8rem, 4vw, 2.6rem)`, 1.25): landing hero title only.
- **Headline** (800, 1.3rem, 1.25): page titles (`sf-page-title`), a page's own heading when no card frames it.
- **Title** (700, 1.05rem, 1.25): card titles, panel headings.
- **Body** (400, 1rem, 1.5): prose, rich-text notes and descriptions.
- **Body Dense** (400, 0.92rem): tables and strip rows.
- **Label** (600, 0.85rem): form labels, small buttons, secondary metadata. The most-used size in the app.
- **Eyebrow** (800, 0.8rem, 0.07em, UPPERCASE, Chart Blue): `Section` block titles.
- **Readout** (600, 1.05rem, tabular figures): stat tile values and any number that updates live.
- **Caption** (700, 0.68–0.75rem): badges, action-bar labels, tab counts.

### Named Rules
**The Tabular Rule.** Any figure that ticks with playback, sits in a column, or is compared against a neighbour uses `font-variant-numeric: tabular-nums`. A readout that jitters as its digits change is broken.

**The Weight Carries It Rule.** One family, so hierarchy is weight. Body is 400; anything that labels, navigates or acts is 600 or heavier. Avoid 500, which falls between them.

## Layout

- **Container:** `sf-main` caps content at 1180px, centred, with a 1.25rem page inset (`--sf-page-pad`) and 3rem bottom air. `sf-main--wide` lifts the cap; `sf-main--bleed` drops cap and padding for full-screen map pages (Registra).
- **Breakpoint:** one, at **700px**. Below it the top navbar disappears and a fixed bottom action bar (60px + safe-area inset) takes over, page bottom padding grows to clear it, section tabs become sticky at the viewport top with a safe-area-aware inset, and `.sf-bleed` cancels the page inset so maps and charts run edge to edge.
- **Rhythm:** vertical stacks are flex columns with 1rem gaps (`sf-section`, `sf-section__body`); within a `Section`, 0.75rem. Adjacent `Section` blocks are separated by 1.5rem plus a hairline, not by boxes.
- **Grids:** auto-fill grids (`minmax(220px, 1fr)` for activity cards, `260px` for general grids, `180px` for form rows). Stat tiles go 4-up on desktop and 2×2 on phones.
- **Native safe areas:** `env(safe-area-inset-*)` is applied on the shell, tab bar, action bar and toasts. Android 15+ forces edge-to-edge, so this is load-bearing, not cosmetic.

### Named Rules
**The Section-Not-Card Rule.** A page-level region is a `Section` (heading, actions, content; no surface, no border). A `Card` is only an innermost discrete entity: one boat, one mark, one entry. Never a Card of Cards.

## Elevation & Depth

Depth is tonal today. Four navy steps (Night Harbour → Harbour Deck → Hull Surface → Hull Surface Raised) carry structure, with 1px Rigging Line borders on every surface. Cards and tiles sit flat. Shadows appear only on elements that genuinely float over content: dropdowns, option menus, map overlays and toasts. They are dark and close (black at 30–45%) because they sit on a dark ground.

### Shadow Vocabulary
- **Overlay hairline** (`0 1px 4px rgba(0,0,0,0.4)`): controls and the playback timeline floating over a map. The most common shadow.
- **Popover** (`0 4px 12px rgba(0,0,0,0.35)` → `0 4px 16px rgba(0,0,0,0.35)`): options panels, combobox lists.
- **Dialog** (`0 8px 24px rgba(4,15,26,0.5)`): modal and sheet surfaces.
- **Accent glow** (`0 2px 12px color-mix(chart-blue 45%)`): a single emphasised primary element; not a pattern to repeat.

### Named Rules
**The Float-Only Rule.** A shadow means "this is above the page and will go away." Resting content does not cast one.

## Shapes

One corner language: a gently rounded **10px** (`--sf-radius`) on buttons, cards, inputs, tiles, strips, menus and nav pills. Selects round slightly more (×1.2). Smaller nested elements use 6px (inline edit inputs) or 4px (session thumbnails). Badges and progress bars are full pills; icon buttons and avatars are circles. Map overlay chips are square-ish rather than pill-shaped so they read as controls, not tags. Dashed borders mean "empty" or "not yet": a missing thumbnail, a coming-soon badge.

## Components

### Buttons
Sporty and confident: weight 600, a clear fill for the one primary action, quiet outlines for the rest.
- **Shape:** gently rounded (10px); icon buttons are circles.
- **Primary:** Chart Blue fill, Chart Blue Ink text, `0.5rem 1rem`. Hover brightens to Chart Blue Bright.
- **Ghost:** transparent with a Rigging Line border and Sail White text; hover fills with Hull Surface. The default for secondary actions.
- **Danger:** Distress Red fill, white text.
- **Active (toggle):** 22% Chart Blue tint, Chart Blue border and text.
- **Small:** `0.3rem 0.7rem`, 0.85rem.
- **Icon:** 3.25rem circle for primary tap targets (recording controls); 2.1rem for toolbar rows.
- **Motion:** background, border and opacity transition in 0.15s. Disabled drops to 60% opacity.
- **Touch:** under a coarse pointer every `sf-btn` is at least 44px tall, and the small variants at least 44px wide (`@media (pointer: coarse)` in global.css). Desktop keeps the denser sizes. Size a new control for a finger the same way, by pointer type, not by viewport width.

### Chips / Badges
- **Style:** full pill, caption type (0.75rem / 700). The neutral badge is Hull Surface Raised on Sea Mist.
- **Variants:** status (success, warning, danger) and entity kind (regatta, activity, personal, club, group, crew), each a 25% tint of its hue behind same-hue text. A `--sm` size exists for tight rows. "Soon" is transparent with a dashed border.

### Cards / Containers
- **Card:** Hull Surface, 1px Rigging Line, 10px radius, `1rem 1.25rem` padding, with a head row (title + actions).
- **Activity card:** a tappable card with a 4:3 thumbnail on Harbour Deck; the border turns Chart Blue on hover.
- **Strip row:** a flat list row on a 12% Chart Blue–tinted surface; the muted variant is plain Hull Surface; active gets a Chart Blue border.
- **Shadow:** none (Float-Only Rule).

### Inputs / Fields
- **Style:** a Harbour Deck well, 1px Rigging Line, 10px radius, `0.5rem 0.7rem`, Sail White text. The label sits above in Sea Mist at 0.85rem / 600.
- **Focus:** a 2px Chart Blue outline inset by 1px.
- **Select:** custom chevron in Sea Mist, slightly larger radius.
- **Error:** Distress Red text at 0.9rem below the form.

### Navigation
- **Desktop navbar:** 58px, Harbour Deck, sticky, with a hairline bottom border. Brand at 800 weight; links are 600-weight Sea Mist pills that go Sail White on Hull Surface on hover and on Hull Surface Raised when active.
- **Phone action bar:** fixed bottom, 60px + safe area, Harbour Deck. Icons with 0.7rem / 600 labels; the active item turns Chart Blue. A Distress Red dot flags pending uploads.
- **Section tabs:** Sea Mist text with a 2px underline that goes Chart Blue when active. Horizontally scrollable with the scrollbar hidden; sticky on phones.

### Stat Tile (signature)
The instrument readout: a small Hull Surface tile with a 0.75rem Sea Mist label over a 1.05rem / 600 tabular value. Used both for live playback values at the cursor and for session aggregates.

### Map overlays (signature)
Every control drawn over the map tiles shares one chrome: the overlay surface (`--sf-overlay`, Hull Surface at 85%), a light border (`--sf-overlay-border`) and the overlay hairline shadow (`--sf-overlay-shadow`). Each is round, a circle or a pill, never Leaflet's white squares. Map marks use only the categorical palette.
- **Tools column (top-right):** the layers toggle and, on replay maps, **Segui la barca**, both 40px circles (44px on touch). Follow is a toggle. Pressed, it fills with Chart Blue and the camera stays on the boat. Pressed again, the map pulls back to the whole track.
- **Follow behaviour:** pressing play turns follow on and flies in (zoom ≥ 15, or the whole fleet on a multi-boat map). The boat then stays at the centre of the view: the camera glides to it a few times a second in short linear steps, never one pan per frame (that would redraw the whole track 60 times a second). Dragging the map hands the camera back to the user; pinch-zooming does not. Reaching the end of playback pulls back to the whole outing.
- **Boat marker:** the boat is drawn as its own silhouette, bow towards the direction it is moving (course over ground, averaged over a few fixes; a stationary boat keeps its last heading), easing through turns. A monohull is the dinghy outline; a catamaran (class hull type `multihull`) is a Tornado-style pair of slim hulls with crossbeams and a translucent trampoline, a little larger because its hulls are thin. Icons live in `components/race/boatIcons.ts`; a new hull type is one more entry there. The marker is filled with the boat's colour and outlined in Night Harbour so it reads on land and sea.
- **Several boats on one map:** each boat's line and marker take its own colour from the track palette, instead of the single-boat speed gradient (five identical gradients would say nothing about whose line is whose).
- **Transport (bottom-centre):** a compact pill of chrome-less 36px icon buttons around one filled Chart Blue play button, plus a tabular clock. On touch the hit areas grow to 44px tall while the boxes stay small.
- **Zoom (desktop, bottom-right):** a horizontal pill. It is hidden on touch, because pinch is how a finger zooms.
- **Credits:** a small overlay pill ("© OpenStreetMap contributors"). On phones it is collapsed behind a 24px "i" toggle, which turns light when open.

## Do's and Don'ts

### Do:
- **Do** read colour only through `var(--sf-*)` tokens in CSS Modules.
- **Do** keep Chart Blue as the single interactive accent (The One Signal Rule).
- **Do** use tabular figures for every live or columnar number.
- **Do** use the categorical leg/maneuver colours for anything drawn on a map or chart.
- **Do** use a `Section` for page regions and a `Card` only for one discrete entity.
- **Do** honour safe-area insets on anything fixed or sticky; native shells are the primary target.
- **Do** check that Italian and English copy both fit; Italian labels run longer.

### Don't:
- **Don't** nest a Card inside a Card, or box a page region that a `Section` should hold.
- **Don't** put a shadow on resting content (The Float-Only Rule).
- **Don't** introduce a second interactive accent, or use a status colour as decoration.
- **Don't** use solid status fills for badges; tint them.
- **Don't** add a second font family to create hierarchy; use weight.
- **Don't** treat this file's flat tonal look as the design goal. The owner wants a more modern, on-trend treatment of surfaces and depth. That is open and belongs in a dedicated redesign pass (`/impeccable` new-work), which will replace this file. Until then, extend the existing system consistently instead of inventing a one-off "modern" look per page.
