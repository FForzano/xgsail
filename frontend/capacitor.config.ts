import type { CapacitorConfig } from "@capacitor/cli";

// Native shell config for the iOS/Android wrapper around the existing SPA.
// The web app is unaffected by any of this — Capacitor only reads this file
// during `cap sync`/native builds, never during `vite dev`/`vite build`.
//
// Minimum OS targets: Android 8 (API 26, set in android/variables.gradle
// after `cap add android`) and iOS 14 (set as the Xcode deployment target
// after `cap add ios`) — see docs/native-apps.md.
const config: CapacitorConfig = {
  appId: "com.xgsail.app",
  appName: "XGSail",
  webDir: "dist",
  // useLegacyBridge: required by @capacitor-community/background-geolocation
  // (see its README) — without it, Android silently stops delivering
  // location updates ~5 minutes after the app is backgrounded/screen-locked,
  // which would otherwise cut GPS recordings short with no error shown.
  android: { minWebViewVersion: 60, useLegacyBridge: true },
  // Without this, Capacitor serves the app from https://localhost, which
  // password managers (Bitwarden, etc.) show as the site. app.xgsail.com is
  // a dedicated, purely virtual hostname — it doesn't need to exist in DNS,
  // and doesn't need to match the real xgsail.com exactly: password
  // managers match by base domain by default, so credentials saved for
  // xgsail.com still autofill here. This only changes the WebView's own
  // virtual origin (cookies/autofill/CORS identity); it does NOT redirect
  // network requests — VITE_API_BASE still points at api.xgsail.com
  // regardless. Requires SAILFRAMES_CORS_ORIGINS on the backend to include
  // https://app.xgsail.com (see deploy/docker-compose.prod.yml).
  server: {
    hostname: "app.xgsail.com",
    androidScheme: "https",
  },
  plugins: {
    CapacitorUpdater: {
      // Points at the standalone ota-service (see ota-service/), never the
      // FastAPI backend — OTA bundles are unrelated to app data.
      updateUrl: "https://ota.xgsail.com/manifest.json",
      // Self-hosted: no Capgo cloud analytics endpoint.
      statsUrl: "",
      // `true` = "atBackground": checks for an update on every foreground
      // transition (app opened/resumed) and downloads it silently, but only
      // applies it on the *next* background/restart — never hot-swapping
      // the running session. So a fresh install needs one full
      // open-close-reopen cycle before an update becomes visible. Keeps
      // update behavior predictable for App Store review (no mid-session
      // code swap).
      autoUpdate: true,
      resetWhenUpdate: true,
    },
  },
};

export default config;
