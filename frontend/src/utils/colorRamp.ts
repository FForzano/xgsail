// Color helpers for the ordinal ramp used wherever a value's *position on a
// scale* is the message: polar-chart wind buckets, heart-rate zones.
//
// One hue, light→dark by position — never a green-to-red rainbow. Two reasons:
// a single-hue ramp is the correct encoding for ordered magnitude (a rainbow
// implies unrelated categories and falls apart under colour-vision
// deficiency), and red/amber/green are reserved as status colours in this
// design system, so spending them on "zone 5" makes real warnings ambiguous.

export type Rgb = [number, number, number];

export function hexToRgb(hex: string): Rgb {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff];
}

export function mixRgb(a: Rgb, b: Rgb, t: number): Rgb {
  return [0, 1, 2].map((i) => Math.round(a[i] + (b[i] - a[i]) * t)) as Rgb;
}

export function rgbCss([r, g, b]: Rgb): string {
  return `rgb(${r},${g},${b})`;
}

/** Blends toward white — for a variant of a series that must read as a tint of
 * it rather than an unrelated colour. */
export function lightenRgb(rgb: Rgb, amount: number): Rgb {
  return mixRgb(rgb, [255, 255, 255], amount);
}

// Anchored on --sf-primary: the lightest step is a tint of it, the strongest a
// shade, so a control's position and the mark's colour always agree.
export const BASE_RGB = hexToRgb("#2f9be0");
export const RAMP_LIGHT = mixRgb(BASE_RGB, [255, 255, 255], 0.55);
export const RAMP_DARK = mixRgb(BASE_RGB, [0, 0, 0], 0.35);

/** `t` in 0..1 along the light→dark ramp. */
export function rampRgb(t: number): Rgb {
  return mixRgb(RAMP_LIGHT, RAMP_DARK, t);
}

/** Ramp colour for step `i` of `count` (count 1 returns the mid tone). */
export function rampStep(i: number, count: number): string {
  return rgbCss(rampRgb(count <= 1 ? 0.5 : i / (count - 1)));
}
