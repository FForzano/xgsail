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
  // regardless. With androidScheme "https" below, this origin is
  // https://app.xgsail.com on Android and capacitor://app.xgsail.com on iOS
  // (Capacitor 8 applies `hostname` to both platforms, not just Android —
  // confirmed via Safari Web Inspector's Network tab on a real iOS build).
  // Requires SAILFRAMES_CORS_ORIGINS on the backend to include both (see
  // deploy/docker-compose.prod.yml / docs/native-apps.md).
  // Because this origin is virtual, never build a shareable link from
  // window.location.origin — it would resolve nowhere outside the app. Use
  // `publicWebOrigin` (src/config/platform.ts), fed by VITE_PUBLIC_WEB_ORIGIN.
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
      // Manual mode: NativeUpdateGate (frontend/src/components/native/
      // NativeUpdateGate.tsx) owns the entire check/download/apply flow on
      // every cold start, blocking on a logo+progress screen until it's
      // done — so a published update is live on THIS launch, not just
      // visible after the next one. Leaving the native autoUpdate check on
      // here too would run a second, competing check/download on the same
      // launch. Still App Store-safe: the code swap happens before the app
      // is ever shown, not mid-session.
      autoUpdate: "off",
      resetWhenUpdate: true,
    },
  },
};

export default config;
