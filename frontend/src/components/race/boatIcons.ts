import type { HullType } from "@/types";

/** Top-down boat silhouettes for the replay marker, all drawn bow-up so a
 * rotation by the boat's heading (clockwise from north) points the bow where
 * the boat is going.
 *
 * Adding a hull type means one more entry in `BOAT_ICONS`: its SVG viewBox
 * (which fixes the icon's proportions at a given height) and the markup that
 * fills it with `currentColor`. An unknown or unset hull type falls back to the
 * monohull. */

/** The monohull outline: bow at the top (100,20), flat transom at the bottom
 * (y=300), widest at 150/50 about two thirds aft. */
const MONOHULL_PATH =
  "M 100 20 C 112 50 150 110 150 190 C 150 240 142 280 136 300 H 64 " +
  "C 58 280 50 240 50 190 C 50 110 88 50 100 20 Z";

export interface BoatIcon {
  viewBox: string;
  /** Width / height of the viewBox, so the DOM box can match the drawing. */
  aspect: number;
  /** Drawn height in px. A catamaran is a longer boat than a dinghy, and two
   * 10:1 hulls need the extra height to stay legible at map scale. */
  height: number;
  /** Outline width in screen px: the catamaran's hulls are only ~4px wide, and
   * a dinghy-weight outline would leave them all stroke and no colour. */
  stroke: number;
  /** SVG children, filled/stroked by the caller through `currentColor`. */
  markup: string;
}

/** One catamaran hull on its own centreline (x=0): a slender, deep-V bow
 * running to a narrow transom, about 7.5:1 — a Tornado's are nearer 10:1, but
 * thinner than this the outline eats the fill at map scale. */
const CAT_HULL_PATH =
  "M 0 10 C 8 40 19 100 19 175 C 19 225 15 265 14 295 H -14 " +
  "C -15 265 -19 225 -19 175 C -19 100 -8 40 0 10 Z";

/** A Tornado-style catamaran: two long slim hulls 112 apart (centres at 44 and
 * 156), joined by two slim crossbeams with the trampoline stretched between
 * them. Beams and trampoline are drawn first so the hulls' fill and outline sit
 * over their ends; the trampoline is the same colour, translucent and
 * unoutlined, so it reads as fabric between the hulls and not a third solid
 * shape. */
const CATAMARAN_MARKUP = [
  `<rect x="63" y="99" width="74" height="113" stroke="none" fill-opacity="0.35"/>`,
  `<rect x="44" y="92" width="112" height="7"/>`,
  `<rect x="44" y="212" width="112" height="7"/>`,
  `<path d="${CAT_HULL_PATH}" transform="translate(44 0)"/>`,
  `<path d="${CAT_HULL_PATH}" transform="translate(156 0)"/>`,
].join("");

const MONOHULL: BoatIcon = {
  viewBox: "40 10 120 300",
  aspect: 120 / 300,
  height: 30,
  stroke: 1.6,
  markup: `<path d="${MONOHULL_PATH}"/>`,
};

const BOAT_ICONS: Record<HullType, BoatIcon> = {
  monohull: MONOHULL,
  multihull: {
    viewBox: "15 0 170 300",
    aspect: 170 / 300,
    height: 38,
    stroke: 1.1,
    markup: CATAMARAN_MARKUP,
  },
};

export function boatIconFor(hullType: HullType | null | undefined): BoatIcon {
  return (hullType && BOAT_ICONS[hullType]) || MONOHULL;
}

/** Side of the marker's square Leaflet box, in px: larger than any drawing
 * (the hulls are thin, and a bigger box is a bigger target to grab) and fixed,
 * so swapping icons never moves a boat's anchor. */
export const BOAT_MARKER_BOX = 48;

/** HTML for a Leaflet `divIcon`: a larger, transparent hit box (the drawing is
 * only ~12px wide, too thin to grab) centring the rotatable hull. The hull is
 * outlined in the dark chrome colour (a screen-pixel stroke, set in
 * MapView.module.css) so it reads on both light land and the pale sea. */
export function boatMarkerHtml(icon: BoatIcon, color: string, hullClass: string): string {
  const w = Math.round(icon.height * icon.aspect);
  return (
    `<span class="${hullClass}" style="color:${color}">` +
    `<svg viewBox="${icon.viewBox}" width="${w}" height="${icon.height}" aria-hidden="true">` +
    `<g fill="currentColor" stroke="#0b1f33" stroke-width="${icon.stroke}" stroke-linejoin="round">` +
    `${icon.markup}</g></svg></span>`
  );
}
