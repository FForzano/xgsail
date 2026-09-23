/** Best-effort Android detection for the browser-only "install the app"
 * nudge (InstallAppBanner). Native Capacitor builds never reach it — they're
 * gated separately via `isNativeApp` (config/platform.ts). */
export function isAndroidUserAgent(): boolean {
  return /Android/i.test(navigator.userAgent);
}
