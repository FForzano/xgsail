import type { HullType } from "@/types";
import { SILHOUETTE_SPECS, type SilhouetteId, type SilhouetteSpec } from "./boatSilhouettes";

/** Top-down boat silhouettes for the replay marker, all drawn bow-up so a
 * rotation by the boat's heading (clockwise from north) points the bow where
 * the boat is going.
 *
 * A class silhouette is generated from its plan dimensions (boatSilhouettes.ts)
 * rather than hand-drawn, so every class is drawn by the same rules and adding
 * one is a row of numbers. A class without a silhouette falls back to the
 * generic drawing for its hull type, and an unknown or unset hull type to the
 * monohull. */

/** One closed shape of an icon. `tint` draws it as a light, opaque tint of the
 * boat colour (white underneath, so the map never shows through) — trampolines
 * and racks; `color-mix` would do it in one fill but the iOS 14 WebView lacks
 * it. `outline: false` leaves it unstroked. */
export interface IconPart {
  d: string;
  tint?: boolean;
  outline?: boolean;
}

export interface BoatIcon {
  viewBox: string;
  /** Width / height of the viewBox, so the DOM box can match the drawing. */
  aspect: number;
  /** Drawn height in px. */
  height: number;
  /** Outline width in screen px: a slim hull needs a lighter outline, or it is
   * all stroke and no colour at map scale. */
  stroke: number;
  /** Painted in order, filled/stroked by the caller through `currentColor`. */
  parts: IconPart[];
}

/** The generic monohull outline: bow at the top (100,20), flat transom at the
 * bottom (y=300), widest at 150/50 about two thirds aft. */
const MONOHULL: BoatIcon = {
  viewBox: "40 10 120 300",
  aspect: 120 / 300,
  height: 30,
  stroke: 1.6,
  parts: [
    {
      d:
        "M 100 20 C 112 50 150 110 150 190 C 150 240 142 280 136 300 H 64 " +
        "C 58 280 50 240 50 190 C 50 110 88 50 100 20 Z",
    },
  ],
};

const r = (n: number) => Math.round(n * 10) / 10;

type Pt = readonly [number, number];
/** One cubic Bézier segment: two control points and the end point. */
type Seg = readonly [Pt, Pt, Pt];

export interface HullPlan {
  length: number;
  beam: number;
  maxAt: number;
  transom: number;
  bow?: number;
  entry: number;
  /** Measured deck widths, `[fraction of length from the bow, full width in
   * cm]`, bow to stern. When given, the outline is a spline through them
   * instead of the `maxAt`/`entry` curve. */
  offsets?: readonly (readonly [number, number])[];
  asymmetry?: number;
}

/** Catmull-Rom through `pts` as cubic Béziers: a smooth curve that passes
 * exactly through every measured station. */
function splineThrough(pts: Pt[]): Seg[] {
  const segs: Seg[] = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[Math.min(pts.length - 1, i + 2)];
    segs.push([
      [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6],
      [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6],
      p2,
    ]);
  }
  return segs;
}

/** Plan of one hull on centreline `cx`, bow at `y0`, in cm.
 *
 * Without `offsets`, the forward curve runs from the bow (a point, or a pram
 * bow `bow` wide) out to the maximum beam at `maxAt`; `entry` is how quickly it
 * gets there (0 a fine bow, 1 a full round one). Even the finest stays convex
 * — a deck plan has no hollow, only the waterlines below it do. The aft curve
 * then closes in to a flat transom `transom` wide.
 *
 * `asymmetry` (0–1) shifts beam to the `outboard` side (+1 starboard, -1 port)
 * and straightens the other: a board-less catamaran's hull (Hobie 16) is
 * nearly flat inboard and carries its curve outboard, so it grips like a foil. */
function hullPath(cx: number, y0: number, h: HullPlan, outboard: 1 | -1 = 1): string {
  const L = h.length;
  const b = (h.bow ?? 0) / 2;
  const a = h.asymmetry ?? 0;
  const Y = h.maxAt * L;
  // One side's half-breadth, bow to transom, as positive x.
  const side = (sign: 1 | -1): Seg[] => {
    const inboard = a > 0 && sign !== outboard;
    const share = inboard ? 1 - a : 1 + a;
    const t = (Math.min(h.transom, h.beam) / 2) * share;
    if (h.offsets) {
      const stations = h.offsets.map(([f, w]): Pt => [(w / 2) * share, f * L]);
      return splineThrough([[b, 0], ...stations, [t, L]]);
    }
    const m = (h.beam / 2) * share;
    const entry = inboard ? 1 : h.entry;
    return [
      [[b + (m - b) * (0.4 + 0.5 * entry), Y * 0.3], [m, Y * 0.65], [m, Y]],
      [[m, Y + (L - Y) * 0.45], [t + (m - t) * 0.55, L - (L - Y) * 0.12], [t, L]],
    ];
  };
  const p = (sign: number, c: Pt) => `${r(cx + sign * c[0])} ${r(y0 + c[1])}`;
  const stbd = side(1);
  const port = side(-1);
  // Port runs stern to bow: each segment reversed (controls swapped, ending
  // at the previous segment's end, or the bow).
  const portBack = port
    .map((seg, i) => `C ${p(-1, seg[1])} ${p(-1, seg[0])} ${p(-1, i ? port[i - 1][2] : [b, 0])}`)
    .reverse();
  return (
    `M ${p(1, [b, 0])} ${stbd.map((seg) => `C ${seg.map((c) => p(1, c)).join(" ")}`).join(" ")} ` +
    `L ${p(-1, port[port.length - 1][2])} ${portBack.join(" ")} Z`
  );
}

const rect = (x0: number, y0: number, x1: number, y1: number) =>
  `M ${r(x0)} ${r(y0)} H ${r(x1)} V ${r(y1)} H ${r(x0)} Z`;

/** Racks/wings: a frame `width` wide over a span of the hull, its leading
 * corners swept back a little as the real tubes are. */
function wingsPath(width: number, y0: number, y1: number): string {
  const w = width / 2;
  const sweep = (y1 - y0) * 0.12;
  return `M ${r(-w)} ${r(y0 + sweep)} L ${r(-w * 0.55)} ${r(y0)} H ${r(w * 0.55)} L ${r(w)} ${r(y0 + sweep)} V ${r(y1)} H ${r(-w)} Z`;
}

/** Legibility floors, as fractions of hull length: at ~30px a 10:1 hull or a
 * 3cm tube would vanish under its own outline, so slim parts are drawn fatter
 * than the class rule says. */
const MIN_HULL_BEAM = 1 / 7.5;
const MIN_BAR = 1 / 40;

/** Drawn heights: close to one size for every class (a map marker, not a scale
 * model), growing only with the fourth root of hull length — an Optimist is
 * ~26px, a Star ~34px. Multihulls get a bonus so two slim hulls stay legible. */
const BASE_HEIGHT = 30;
const BASE_LENGTH_CM = 420;
const MULTIHULL_BONUS = 1.15;
const MAX_HEIGHT = 44;

function buildIcon(spec: SilhouetteSpec): BoatIcon {
  const L = spec.length;
  const sprit = spec.sprit ?? 0;
  const bar = L * MIN_BAR;
  const parts: IconPart[] = [];
  let halfWidth: number;

  if (spec.kind === "catamaran") {
    const hullBeam = Math.max(spec.hullBeam, L * MIN_HULL_BEAM);
    // A widened hull keeps its transom in proportion.
    const transom = (spec.transom * hullBeam) / spec.hullBeam;
    const c = (spec.beam - spec.hullBeam) / 2;
    const yFront = spec.beams[0] * L;
    const yRear = spec.beams[1] * L;
    // Beams and trampoline first, so the hulls sit over their ends. The
    // trampoline runs hull centreline to hull centreline, so no gap shows at
    // the tapering bow and stern.
    parts.push({ d: rect(-c, yFront, c, yRear), tint: true, outline: false });
    parts.push({ d: rect(-c, yFront - bar, c, yFront) });
    parts.push({ d: rect(-c, yRear, c, yRear + bar) });
    if (sprit) parts.push({ d: rect(-bar / 2, -sprit, bar / 2, yFront) });
    const hull = {
      length: L,
      beam: hullBeam,
      maxAt: spec.maxAt,
      transom,
      entry: spec.entry,
      asymmetry: spec.asymmetry,
    };
    parts.push({ d: hullPath(-c, 0, hull, -1) }, { d: hullPath(c, 0, hull, 1) });
    halfWidth = c + (hullBeam / 2) * (1 + (spec.asymmetry ?? 0));
  } else {
    const beam = Math.max(spec.beam, L * MIN_HULL_BEAM);
    if (spec.wings) {
      parts.push({ d: wingsPath(spec.wings.width, spec.wings.from * L, spec.wings.to * L), tint: true });
    }
    if (sprit) parts.push({ d: rect(-bar / 2, -sprit, bar / 2, L * 0.1) });
    parts.push({ d: hullPath(0, 0, { ...spec, beam }) });
    halfWidth = Math.max(beam, spec.wings?.width ?? 0) / 2;
  }

  const pad = L * 0.03;
  const width = 2 * (halfWidth + pad);
  const span = L + sprit + 2 * pad;
  const bonus = spec.kind === "catamaran" ? MULTIHULL_BONUS : 1;
  const hullHeight = BASE_HEIGHT * bonus * (L / BASE_LENGTH_CM) ** 0.25;
  const thin = spec.kind === "catamaran" || (spec.kind === "monohull" && !!spec.wings);
  return {
    viewBox: `${r(-width / 2)} ${r(-sprit - pad)} ${r(width)} ${r(span)}`,
    aspect: width / span,
    height: Math.min(MAX_HEIGHT, Math.round((hullHeight * span) / (L + 2 * pad))),
    stroke: thin ? 1.1 : 1.6,
    parts,
  };
}

const CLASS_ICONS = Object.fromEntries(
  Object.entries(SILHOUETTE_SPECS).map(([id, spec]) => [id, buildIcon(spec)]),
) as Record<SilhouetteId, BoatIcon>;

/** The generic multihull is the Tornado, the catamaran most people picture. */
const GENERIC_ICONS: Record<HullType, BoatIcon> = {
  monohull: MONOHULL,
  multihull: CLASS_ICONS.tornado,
};

export function boatIconFor(
  silhouette: string | null | undefined,
  hullType: HullType | null | undefined,
): BoatIcon {
  if (silhouette && silhouette in CLASS_ICONS) return CLASS_ICONS[silhouette as SilhouetteId];
  return (hullType && GENERIC_ICONS[hullType]) || MONOHULL;
}

/** Side of the marker's square Leaflet box, in px: larger than any drawing
 * (the hulls are thin, and a bigger box is a bigger target to grab) and fixed,
 * so swapping icons never moves a boat's anchor. */
export const BOAT_MARKER_BOX = 48;

export const ICON_OUTLINE = "#0b1f33";

function partHtml(part: IconPart): string {
  const noStroke = part.outline === false ? ` stroke="none"` : "";
  if (!part.tint) return `<path d="${part.d}"${noStroke}/>`;
  return (
    `<path d="${part.d}" fill="#fff" stroke="none"/>` +
    `<path d="${part.d}" fill-opacity="0.35"${noStroke}/>`
  );
}

/** HTML for a Leaflet `divIcon`: a larger, transparent hit box (the drawing is
 * only ~12px wide, too thin to grab) centring the rotatable hull. The hull is
 * outlined in the dark chrome colour (a screen-pixel stroke, set in
 * MapView.module.css) so it reads on both light land and the pale sea. */
export function boatMarkerHtml(icon: BoatIcon, color: string, hullClass: string): string {
  const w = Math.round(icon.height * icon.aspect);
  return (
    `<span class="${hullClass}" style="color:${color}">` +
    `<svg viewBox="${icon.viewBox}" width="${w}" height="${icon.height}" aria-hidden="true">` +
    `<g fill="currentColor" stroke="${ICON_OUTLINE}" stroke-width="${icon.stroke}" stroke-linejoin="round">` +
    `${icon.parts.map(partHtml).join("")}</g></svg></span>`
  );
}
