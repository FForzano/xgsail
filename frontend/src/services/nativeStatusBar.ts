import { Capacitor } from "@capacitor/core";
import { StatusBar, Style } from "@capacitor/status-bar";

// Android (API 35+, targetSdkVersion 36 here) defaults to edge-to-edge,
// drawing the WebView under the status bar/notch — a problem on devices
// with a punch-hole or camera cutout. setOverlaysWebView(false) makes the
// status bar reserve its own strip instead of overlaying content; the
// matching background color keeps that strip visually part of the app
// rather than a stray black/white bar. The web bundle never imports this
// module (see contexts/AuthContext.tsx's nativeAuth for the same pattern).
//
// The strip takes the page ground of whichever theme is showing, read from
// the same --sf-bg token the page paints with, and follows the OS switching
// between light and dark while the app is open.
const darkScheme = window.matchMedia("(prefers-color-scheme: dark)");
let followingScheme = false;

async function paintStatusBar(): Promise<void> {
  const bg = getComputedStyle(document.documentElement).getPropertyValue("--sf-bg").trim();
  if (bg) await StatusBar.setBackgroundColor({ color: bg });
  // Style.Dark means light icons, for a dark background.
  await StatusBar.setStyle({ style: darkScheme.matches ? Style.Dark : Style.Light });
}

export async function initNativeStatusBar(): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;
  await StatusBar.setOverlaysWebView({ overlay: false });
  await paintStatusBar();
  if (!followingScheme) {
    followingScheme = true;
    darkScheme.addEventListener("change", () => void paintStatusBar());
  }
}

/** Navigation mode (components/registra/NavModeOverlay.tsx) takes the whole
 * screen: the status bar's reserved strip is one more lit band on an OLED and
 * one more thing competing with the instrument readout, so it's hidden for
 * the duration and the app's normal chrome restored on the way out. */
export async function setNavModeStatusBar(on: boolean): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;
  if (on) {
    await StatusBar.hide();
    return;
  }
  await StatusBar.show();
  await initNativeStatusBar();
}
