/**
 * True for native-app builds (Capacitor iOS/Android), false for the plain web
 * SPA. Set at build time with `VITE_APP_MODE=native`; defaults to web so the
 * current deployment is unaffected. Native builds skip the marketing
 * landing page and go straight to /login — there's no one to "land" on a
 * device the user already installed the app on.
 */
export const isNativeApp = import.meta.env.VITE_APP_MODE === "native";

/**
 * True only for a native build meant for the Play Store / App Store, set at
 * build time with `VITE_APP_DISTRIBUTION=store` (the GitHub Release sideload
 * APK leaves it unset/`sideload`, same as web). Separate from `isNativeApp`
 * because both channels currently share that one flag, but only the store
 * build should hide the Buy Me a Coffee links — the stores have their own
 * donation systems, whereas the sideloaded APK has none.
 */
export const isStoreDistribution = import.meta.env.VITE_APP_DISTRIBUTION === "store";

/** Whether in-app Buy Me a Coffee links/pages should be shown. */
export const canShowSupportLinks = !isStoreDistribution;

/**
 * Origin to build shareable links with (join links, etc.).
 *
 * `window.location.origin` is wrong on native: Capacitor serves the app from
 * the purely virtual `app.xgsail.com` (see capacitor.config.ts), so a link
 * built from it is dead the moment it leaves the app. Native builds must set
 * `VITE_PUBLIC_WEB_ORIGIN` to the real web origin; the web SPA has no such
 * problem and falls back to its own origin.
 */
export const publicWebOrigin =
  import.meta.env.VITE_PUBLIC_WEB_ORIGIN?.replace(/\/+$/, "") || window.location.origin;
