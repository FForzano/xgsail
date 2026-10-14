/** Plan dimensions of the class silhouettes drawn by boatIcons.ts, in cm, bow
 * at y=0. `length` and `beam` are the class rules' hull length and maximum
 * beam (overall beam for a catamaran, hull only for a boat with racks —
 * `wings.width` is the rule's beam over the racks). The plan-shape parameters
 * (`maxAt`, `transom`, `entry`, beam positions, sprit length) are not
 * measurement-rule figures for most classes: they are read off each class's
 * hull plans and photographs, so they get the character right rather than a
 * tolerance.
 *
 * The ids are what `boat_classes.silhouette` stores: renaming one orphans the
 * classes pointing at it (they fall back to the generic hull), so add, don't
 * rename. */

interface MonohullSpec {
  kind: "monohull";
  label: string;
  group: SilhouetteGroup;
  length: number;
  beam: number;
  /** Where the maximum beam falls, as a fraction of length from the bow. */
  maxAt: number;
  transom: number;
  /** Width of a pram bow (Optimist) or a punt bow (Fireball); 0 for a point. */
  bow?: number;
  /** Fullness of the forward sections: ~0.2 a fine bow, ~0.8 a round one. */
  entry: number;
  /** Bowsprit/pole projecting past the stem. */
  sprit?: number;
  /** Measured deck widths `[fraction from bow, full width]`: when the class
   * rules give stations, the outline goes through them (see HullPlan). */
  offsets?: readonly (readonly [number, number])[];
  /** Racks or wings, spanning `from`–`to` (fractions of length). */
  wings?: { width: number; from: number; to: number };
}

interface CatamaranSpec {
  kind: "catamaran";
  label: string;
  group: SilhouetteGroup;
  /** Hull length. */
  length: number;
  /** Overall beam, outside of one hull to outside of the other. */
  beam: number;
  /** One hull's own beam. */
  hullBeam: number;
  maxAt: number;
  transom: number;
  entry: number;
  /** Front and rear crossbeam positions, fractions of length from the bows. */
  beams: [number, number];
  /** Spinnaker pole projecting ahead of the bows, from the front beam. */
  sprit?: number;
  /** Board-less asymmetric hulls (0–1): flat inboard, curved outboard. */
  asymmetry?: number;
}

export type SilhouetteSpec = MonohullSpec | CatamaranSpec;
export type SilhouetteGroup = "olympic" | "dinghy" | "catamaran" | "keelboat";

export const SILHOUETTE_SPECS = {
  // Olympic (Paris 2024 / LA 2028 slate). iQFoil and Formula Kite are boards,
  // drawn with the monohull plan: a round nose, widest aft, a square tail.
  ilca: {
    kind: "monohull", label: "ILCA / Laser", group: "olympic",
    length: 423, beam: 137, maxAt: 0.62, transom: 96, entry: 0.3,
  },
  "470": {
    kind: "monohull", label: "470", group: "olympic",
    length: 470, beam: 169, maxAt: 0.52, transom: 98, entry: 0.3,
  },
  "49er": {
    kind: "monohull", label: "49er / 49erFX", group: "olympic",
    length: 499, beam: 175, maxAt: 0.7, transom: 150, entry: 0.22, sprit: 95,
    wings: { width: 290, from: 0.38, to: 0.94 },
  },
  nacra17: {
    kind: "catamaran", label: "Nacra 17", group: "olympic",
    length: 525, beam: 259, hullBeam: 38, maxAt: 0.55, transom: 28, entry: 0.18,
    beams: [0.36, 0.86], sprit: 45,
  },
  iqfoil: {
    kind: "monohull", label: "iQFoil", group: "olympic",
    length: 220, beam: 95, maxAt: 0.62, transom: 66, entry: 0.85,
  },
  formula_kite: {
    kind: "monohull", label: "Formula Kite", group: "olympic",
    length: 125, beam: 45, maxAt: 0.55, transom: 34, entry: 0.85,
  },

  // Dinghies.
  optimist: {
    kind: "monohull", label: "Optimist", group: "dinghy",
    length: 230, beam: 113, maxAt: 0.55, transom: 88, bow: 56, entry: 0.7,
  },
  "420": {
    kind: "monohull", label: "420", group: "dinghy",
    length: 420, beam: 163, maxAt: 0.55, transom: 110, entry: 0.35,
  },
  "29er": {
    kind: "monohull", label: "29er", group: "dinghy",
    length: 446, beam: 177, maxAt: 0.66, transom: 140, entry: 0.22, sprit: 75,
  },
  finn: {
    kind: "monohull", label: "Finn", group: "dinghy",
    length: 450, beam: 151, maxAt: 0.5, transom: 84, entry: 0.35,
  },
  europe: {
    kind: "monohull", label: "Europe", group: "dinghy",
    length: 335, beam: 138, maxAt: 0.5, transom: 84, entry: 0.6,
  },
  ok: {
    kind: "monohull", label: "OK Dinghy", group: "dinghy",
    length: 400, beam: 142, maxAt: 0.55, transom: 76, entry: 0.35,
  },
  snipe: {
    kind: "monohull", label: "Snipe", group: "dinghy",
    length: 472, beam: 152, maxAt: 0.55, transom: 96, entry: 0.35,
  },
  flying_dutchman: {
    kind: "monohull", label: "Flying Dutchman", group: "dinghy",
    length: 605, beam: 180, maxAt: 0.46, transom: 80, entry: 0.28,
  },
  "505": {
    kind: "monohull", label: "505", group: "dinghy",
    length: 505, beam: 188, maxAt: 0.48, transom: 95, entry: 0.3,
  },
  fireball: {
    kind: "monohull", label: "Fireball", group: "dinghy",
    length: 493, beam: 137, maxAt: 0.6, transom: 114, bow: 36, entry: 0.4,
  },
  flying_junior: {
    kind: "monohull", label: "Flying Junior", group: "dinghy",
    length: 403, beam: 150, maxAt: 0.52, transom: 94, entry: 0.35,
  },
  vaurien: {
    kind: "monohull", label: "Vaurien", group: "dinghy",
    length: 408, beam: 147, maxAt: 0.55, transom: 96, entry: 0.45,
  },
  dinghy_12: {
    kind: "monohull", label: "Dinghy 12'", group: "dinghy",
    length: 366, beam: 143, maxAt: 0.5, transom: 56, entry: 0.6,
  },
  rs_feva: {
    kind: "monohull", label: "RS Feva", group: "dinghy",
    length: 364, beam: 142, maxAt: 0.6, transom: 110, entry: 0.6, sprit: 55,
  },
  rs_aero: {
    kind: "monohull", label: "RS Aero", group: "dinghy",
    length: 400, beam: 140, maxAt: 0.6, transom: 96, entry: 0.3,
  },
  topper: {
    kind: "monohull", label: "Topper", group: "dinghy",
    length: 340, beam: 120, maxAt: 0.58, transom: 86, entry: 0.5,
  },
  moth: {
    kind: "monohull", label: "International Moth", group: "dinghy",
    length: 335.5, beam: 34, maxAt: 0.55, transom: 26, entry: 0.3,
    wings: { width: 225, from: 0.26, to: 0.76 },
  },
  waszp: {
    kind: "monohull", label: "WASZP", group: "dinghy",
    length: 335, beam: 52, maxAt: 0.55, transom: 40, entry: 0.3,
    wings: { width: 225, from: 0.28, to: 0.78 },
  },

  // Catamarans.
  tornado: {
    kind: "catamaran", label: "Tornado", group: "catamaran",
    length: 610, beam: 305, hullBeam: 40, maxAt: 0.55, transom: 28, entry: 0.2,
    beams: [0.31, 0.71],
  },
  f18: {
    kind: "catamaran", label: "F18", group: "catamaran",
    length: 552, beam: 260, hullBeam: 42, maxAt: 0.55, transom: 30, entry: 0.18,
    beams: [0.36, 0.86], sprit: 80,
  },
  nacra15: {
    kind: "catamaran", label: "Nacra 15", group: "catamaran",
    length: 470, beam: 235, hullBeam: 38, maxAt: 0.55, transom: 28, entry: 0.18,
    beams: [0.36, 0.86], sprit: 45,
  },
  // Hobies: asymmetric "banana" hulls with no daggerboards, and a square
  // frame (side rails 73" on the 16, 70" on the 14) sitting over the aft half
  // of the hulls, so the bows run far ahead of the trampoline.
  hobie16: {
    kind: "catamaran", label: "Hobie Cat 16", group: "catamaran",
    length: 504, beam: 241, hullBeam: 48, maxAt: 0.55, transom: 22, entry: 0.3,
    beams: [0.56, 0.94], asymmetry: 0.4,
  },
  hobie14: {
    kind: "catamaran", label: "Hobie Cat 14", group: "catamaran",
    length: 427, beam: 231, hullBeam: 46, maxAt: 0.55, transom: 22, entry: 0.3,
    beams: [0.52, 0.94], asymmetry: 0.4,
  },
  a_class: {
    kind: "catamaran", label: "A-Class", group: "catamaran",
    length: 549, beam: 230, hullBeam: 30, maxAt: 0.55, transom: 22, entry: 0.18,
    beams: [0.4, 0.82],
  },
  dart18: {
    kind: "catamaran", label: "Dart 18", group: "catamaran",
    length: 549, beam: 229, hullBeam: 42, maxAt: 0.5, transom: 28, entry: 0.3,
    beams: [0.34, 0.9],
  },

  // Keelboats.
  star: {
    kind: "monohull", label: "Star", group: "keelboat",
    length: 692, beam: 173, maxAt: 0.56, transom: 60, entry: 0.3,
  },
} satisfies Record<string, SilhouetteSpec>;

export type SilhouetteId = keyof typeof SILHOUETTE_SPECS;
