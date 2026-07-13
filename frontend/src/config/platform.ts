/**
 * True for native-app builds (Capacitor iOS/Android), false for the plain web
 * SPA. Set at build time with `VITE_APP_MODE=native`; defaults to web so the
 * current deployment is unaffected. Native builds skip the marketing
 * landing page and go straight to /login — there's no one to "land" on a
 * device the user already installed the app on.
 */
export const isNativeApp = import.meta.env.VITE_APP_MODE === "native";
