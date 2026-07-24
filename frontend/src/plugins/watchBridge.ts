import { registerPlugin } from "@capacitor/core";
import type { PluginListenerHandle } from "@capacitor/core";

// TS surface for the native WatchBridge Capacitor plugin (iOS only, Swift —
// frontend/ios/App/App/WatchBridgePlugin.swift). The plugin owns the phone
// side of WatchConnectivity: it receives the finished recording files the
// Apple Watch transfers (WCSession.transferFile), stores them under
// @capacitor/filesystem's Directory.Data, and emits `watchSessionReceived`
// once a session's whole bundle has landed. It also pushes the selected boat /
// recording mode / claim state out to the watch. All methods no-op / report
// unsupported off iOS.

export interface WatchSessionReceivedEvent {
  /** Watch-local session id (also the folder the files were stored under),
   * NOT an XGSail session id — see docs/device-protocol.md §8.2. */
  sessionId: string;
  /** Boat the operator picked on the watch/phone before recording, if any. */
  boatId: string | null;
  startedAt: string;
  endedAt: string | null;
  /** "boat": watch GPS is the boat track (subject_type=boat). "personal": the
   * boat already has a tracker, so GPS is the wearer's own (crew_member). */
  mode: "boat" | "personal";
  /** Directory (relative to Filesystem Directory.Data) holding the files. */
  dir: string;
  /** File basenames present, e.g. ["watch_nav.csv", "watch_hr.csv", ...]. The
   * sensor type is encoded in each name (docs/device-protocol.md §9.2). */
  files: string[];
}

export interface WatchContext {
  boatId?: string | null;
  mode?: "boat" | "personal";
  /** Whether the phone holds a device key for the watch (claimed here). The
   * watch UI can block recording until it's claimed. */
  deviceClaimed: boolean;
}

export interface WatchBridgePlugin {
  /** True only on iOS with a paired, app-installed Apple Watch. */
  isSupported(): Promise<{ supported: boolean }>;
  isPaired(): Promise<{ paired: boolean; reachable: boolean }>;
  /** Push boat/mode/claim state to the watch (WCSession application context). */
  sendContext(options: WatchContext): Promise<void>;
  /** Every stored session awaiting upload (durable across relaunches) — the
   * retry source so a session received while offline still uploads later. */
  listPendingSessions(): Promise<{ sessions: WatchSessionReceivedEvent[] }>;
  /** Tell the plugin a received session was uploaded: it deletes the local
   * files and acks the watch (guaranteed delivery) so the watch frees its
   * own buffer too. */
  ackSession(options: { sessionId: string }): Promise<void>;
  addListener(
    eventName: "watchSessionReceived",
    listener: (event: WatchSessionReceivedEvent) => void,
  ): Promise<PluginListenerHandle>;
  removeAllListeners(): Promise<void>;
}

export const WatchBridge = registerPlugin<WatchBridgePlugin>("WatchBridge");
