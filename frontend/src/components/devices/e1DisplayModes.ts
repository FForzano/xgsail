// Shared display-mode metadata for the XGSail E1's onboard screen — one
// source of truth for the mode list, default, and preview image paths
// instead of hand-syncing DisplayModePicker/E1InfoDialog/Landing.

export const E1_DISPLAY_MODES = [1, 2, 3] as const;

export type E1DisplayMode = (typeof E1_DISPLAY_MODES)[number];

export const E1_DEFAULT_DISPLAY_MODE: E1DisplayMode = 2;

export function e1DisplayModeSrc(mode: E1DisplayMode): string {
  return `/devices/e1-display-modes/d${mode}.png`;
}
