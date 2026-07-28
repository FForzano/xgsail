import * as liveFix from "@/services/liveFix";

// Development-only synthetic GPS source, so navigation mode's whole display —
// layout, clamp typography, portrait/landscape, TWA/VMG math, tack colours,
// the start timer — can be worked on in a desktop browser, where there is no
// background-geolocation watcher to feed it.
//
// Its own module (never imported statically by app code, only dynamically by
// RegistraPage behind `import.meta.env.DEV`) so it is not part of the
// production bundle at all, rather than relying on tree-shaking.

// A slow circle off Genoa: enough heading change to exercise COG, the tack
// indicator and VMG's sign flip within a couple of minutes.
const CENTRE = { lat: 44.395, lon: 8.95 };
const RADIUS_DEG = 0.004; // ~450 m
const PERIOD_S = 180;
const SPEED_MS = 3.2; // ~6.2 kn

let timer: number | null = null;

export function startMockFixes(): void {
  if (timer != null) return;
  const started = Date.now();
  liveFix.reset();
  timer = window.setInterval(() => {
    const phase = ((Date.now() - started) / 1000 / PERIOD_S) * 2 * Math.PI;
    liveFix.pushFix({
      latitude: CENTRE.lat + RADIUS_DEG * Math.cos(phase),
      longitude: CENTRE.lon + RADIUS_DEG * Math.sin(phase),
      time: Date.now(),
      accuracy: 6,
      speed: SPEED_MS + Math.sin(phase * 5) * 0.4,
      // Tangent to the circle, so the heading sweeps a full 360° per lap.
      bearing: (((phase * 180) / Math.PI + 90) % 360 + 360) % 360,
    });
  }, 1000);
}

export function stopMockFixes(): void {
  if (timer == null) return;
  window.clearInterval(timer);
  timer = null;
  liveFix.reset();
}
