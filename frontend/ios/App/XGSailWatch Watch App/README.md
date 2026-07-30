# XGSail Apple Watch companion (watchOS target)

Native SwiftUI watchOS app that records a sailing session's GPS + HealthKit
signals and relays them to the phone over WatchConnectivity, which uploads
them via the device protocol (see `docs/device-protocol.md` §9 and
`docs/native-apps.md` "Apple Watch companion").

These `.swift` files are **not** generated or touched by `cap sync` — they
are a hand-added watchOS target on the existing Capacitor iOS project
(`frontend/ios/App/App.xcodeproj`). Adding the target is a one-time manual
Xcode step, exactly like the iOS Share Extension in `docs/native-apps.md`.
Like all native code here, it **does not ship via OTA** and needs a **paid
Apple Developer account** to build to a device.

Physical location note: on Xcode 16+, a new watchOS target is backed by a
*filesystem-synchronized group* tied to a fixed on-disk folder next to
`App.xcodeproj` (`frontend/ios/App/XGSailWatch Watch App/`, this folder) —
that's why these sources live under `ios/App/`, not a standalone
`ios/XGSailWatch/` directory; Xcode requires the target's real files there,
not just a reference.

## Files

| File | Role |
|---|---|
| `XGSailWatchApp.swift` | `@main` App; activates WatchConnectivity, requests HealthKit auth. |
| `ContentView.swift` | Glanceable UI: clock, SOG (kn), COG (°), start/pause/stop. |
| `SessionRecorder.swift` | `HKWorkoutSession`+`HKLiveWorkoutBuilder` (background) + `CLLocationManager`; writes the 5 CSVs. |
| `WatchConnectivityClient.swift` | Transfers the finished CSV bundle + manifest to the phone; receives context/acks. |
| `WatchContextStore.swift` | Holds boat/mode/claim state pushed from the phone. |

The phone side is `frontend/ios/App/App/WatchBridgePlugin.swift` (+ `.m`) and
the JS is `frontend/src/plugins/watchBridge.ts` / `services/nativeWatch.ts`.

## One-time Xcode setup

1. **Add the target**: File → New → Target → **watchOS → App**. Name it
   `XGSailWatch`, interface **SwiftUI**, language **Swift**, select
   *"Watch App for Existing iOS App"* (embeds in `App`), and set the
   Organization Identifier so the bundle id comes out as
   `com.xgsail.app.watchkitapp` (fix it by hand in Signing & Capabilities if
   the wizard doesn't land on it exactly).
2. **Replace the generated sources** with the files in this folder (delete the
   stub `ContentView.swift`/`…App.swift` Xcode created, drag these 5 files in
   from Finder — **Action: "Move files to destination"**, not Copy, since the
   target's synchronized folder needs the real files inside it, and Move
   avoids leaving a duplicate copy elsewhere).
3. **Capabilities** (watch target): add **HealthKit**. **Background Modes**:
   enable **Workout processing**.
4. **Watch `Info.plist`** usage strings (required or the app crashes on first
   use) — settable directly from the HealthKit capability's own Usage
   Description fields plus one added manually under the target's **Info** tab:
   - `NSHealthShareUsageDescription` — "XGSail reads heart rate, energy, HRV
     and respiration to attach them to your sailing session."
   - `NSHealthUpdateUsageDescription` — "XGSail records a workout for the
     session."
   - `NSLocationWhenInUseUsageDescription` — "XGSail records your GPS track."
5. **Phone side**: add `WatchBridgePlugin.swift` + `WatchBridgePlugin.m` to the
   `App` target (**Action: "Reference files in place"** — the `App` target
   isn't a synchronized-folder target, so no move needed). No extra phone
   entitlement is needed for WatchConnectivity.
6. **Plugin registration (required, easy to miss)**: this Capacitor version
   does *not* auto-discover local (non-npm) native plugins by scanning the
   Objective-C runtime — calling `WatchBridge.*` from JS fails with `"WatchBridge"
   plugin is not implemented on ios` unless it's registered explicitly. Add
   `frontend/ios/App/App/BridgeViewController.swift`, a `CAPBridgeViewController`
   subclass that registers it in `capacitorDidLoad()`:
   ```swift
   import Capacitor
   class BridgeViewController: CAPBridgeViewController {
       override func capacitorDidLoad() {
           bridge?.registerPluginInstance(WatchBridgePlugin())
       }
   }
   ```
   and point `Main.storyboard`'s view controller's custom class at it
   (`BridgeViewController`, module `App`) instead of the default
   `CAPBridgeViewController` (module `Capacitor`).
7. **Deployment target**: watchOS 9+ (for `.sailing` workout type + the
   `HKLiveWorkoutBuilder` background behavior used here).

## How it flows

1. Phone (`nativeWatch.claimWatch`) claims the watch as a `wearable` device and
   stores its `device_api_key`; `sendContext` pushes the selected boat + mode.
2. Watch records standalone (works wrist-down / backgrounded via the workout
   session), showing SOG/COG live.
3. On stop, the watch `transferFile`s the 5 CSVs + a manifest to the phone.
4. `WatchBridgePlugin` stores them and emits `watchSessionReceived`;
   `useWatchRelay` → `nativeWatch.relaySession` uploads them via the device
   protocol (GPS as the boat track, physiological streams as the wearer's
   `crew_member` data — merged into the same boat session).

## Data lifecycle (no accumulation)

Recordings are deleted only after they are safely uploaded — never before —
and there are safety nets so nothing lingers forever:

- **Watch → phone** uses `transferFile` (guaranteed background delivery), so a
  session recorded with the phone out of range still arrives once it's back.
- The phone **persists each session** (`manifest.json`) and **retries** on
  launch and every foreground (`useWatchRelay` → `relayPending`); a session is
  deleted from the phone only after its upload succeeds.
- On success the phone acks the watch via `transferUserInfo` (also guaranteed
  delivery, even if the watch app was closed), and the watch deletes that
  session's folder (`didReceiveUserInfo`).
- Safety nets: the watch reclaims any session folder older than 30 days on
  launch (`sweepOldSessions`), and the phone clears abandoned *partial*
  transfers — folders that never received a manifest — older than 7 days
  (`sweepAbandonedPartials`). Neither ever deletes a real, still-pending
  upload.

Full verification (a real `transferFile` CSV bundle arriving, real HealthKit
sensor data) is manual on a paired watch — see `docs/native-apps.md`'s
"Testing without a paid Apple account" section for exactly what the
Simulator can and can't stand in for.
