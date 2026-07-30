import Foundation
import Capacitor
import WatchConnectivity

/// Phone side of the Apple Watch companion (docs/native-apps.md "Apple Watch
/// companion", docs/device-protocol.md §9). Owns the iPhone's `WCSession`:
/// receives the finished recording files the watch transfers
/// (`WCSession.transferFile`), stores them under the app's Documents dir where
/// `@capacitor/filesystem` `Directory.Data` reads them, and emits
/// `watchSessionReceived` once a session's manifest arrives. Also pushes the
/// selected boat / recording mode / claim state out to the watch.
///
/// Data lifecycle (no unbounded accumulation): each session's metadata is
/// persisted to `manifest.json` on arrival so `listPendingSessions` can find it
/// again after a relaunch; JS relays it and calls `ackSession`, which deletes
/// the phone copy AND `transferUserInfo`s an ack to the watch (guaranteed
/// delivery) so the watch frees its own buffer. A load-time sweep clears
/// abandoned *partial* transfers (a folder that never got a manifest).
///
/// Registered via `WatchBridgePlugin.m`'s `CAP_PLUGIN` macro; JS wrapper is
/// `frontend/src/plugins/watchBridge.ts`.
@objc(WatchBridgePlugin)
public class WatchBridgePlugin: CAPPlugin, CAPBridgedPlugin, WCSessionDelegate {
    public let identifier = "WatchBridgePlugin"
    public let jsName = "WatchBridge"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "isSupported", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "isPaired", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "sendContext", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "listPendingSessions", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "ackSession", returnType: CAPPluginReturnPromise),
    ]

    // Files land under Documents/watch/<sessionId>/ — `Directory.Data` on iOS
    // resolves to the Documents directory (see @capacitor/filesystem's iOS
    // directory mapping), so JS reads them back with dir "watch/<sessionId>".
    private static let rootFolder = "watch"
    private static let manifestName = "manifest.json"
    // A partial transfer (data files but no manifest) older than this is
    // abandoned — safe to delete, since a real pending session always has a
    // manifest.json. Never deletes a session that has a manifest (that's real
    // pending data the retry loop still owns), so no upload is ever lost.
    private static let partialTTL: TimeInterval = 7 * 24 * 3600

    override public func load() {
        guard WCSession.isSupported() else { return }
        let session = WCSession.default
        session.delegate = self
        session.activate()
        sweepAbandonedPartials()
    }

    private func documentsURL() -> URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    }

    private func rootURL() -> URL {
        documentsURL().appendingPathComponent(Self.rootFolder)
    }

    // MARK: - Plugin methods

    @objc func isSupported(_ call: CAPPluginCall) {
        #if targetEnvironment(simulator) && DEBUG
        // WCSession.isPaired/isWatchAppInstalled stay false in Simulator even
        // with `simctl pair`ed devices — local-testing-only bypass, compiled
        // out of every device/Release build by the guards above.
        call.resolve(["supported": true])
        return
        #else
        let ok = WCSession.isSupported() && WCSession.default.isPaired
            && WCSession.default.isWatchAppInstalled
        call.resolve(["supported": ok])
        #endif
    }

    @objc func isPaired(_ call: CAPPluginCall) {
        guard WCSession.isSupported() else {
            call.resolve(["paired": false, "reachable": false]); return
        }
        #if targetEnvironment(simulator) && DEBUG
        call.resolve(["paired": true, "reachable": true])
        return
        #else
        call.resolve([
            "paired": WCSession.default.isPaired,
            "reachable": WCSession.default.isReachable,
        ])
        #endif
    }

    @objc func sendContext(_ call: CAPPluginCall) {
        guard WCSession.isSupported() else { call.resolve(); return }
        var context: [String: Any] = [
            "deviceClaimed": call.getBool("deviceClaimed") ?? false,
        ]
        if let boatId = call.getString("boatId") { context["boatId"] = boatId }
        if let mode = call.getString("mode") { context["mode"] = mode }
        do {
            try WCSession.default.updateApplicationContext(context)
            call.resolve()
        } catch {
            call.reject("Failed to send context to watch: \(error.localizedDescription)")
        }
    }

    /// Every stored session that has a manifest (i.e. is complete and awaiting
    /// upload) — the durable list JS retries on launch/foreground, so a session
    /// received while offline still uploads later.
    @objc func listPendingSessions(_ call: CAPPluginCall) {
        let fm = FileManager.default
        let dirs = (try? fm.contentsOfDirectory(atPath: rootURL().path)) ?? []
        var sessions: [[String: Any]] = []
        for id in dirs {
            let sessionDir = rootURL().appendingPathComponent(id)
            if let payload = loadManifestPayload(sessionId: id, sessionDir: sessionDir) {
                sessions.append(payload)
            }
        }
        call.resolve(["sessions": sessions])
    }

    @objc func ackSession(_ call: CAPPluginCall) {
        guard let sessionId = call.getString("sessionId") else {
            call.reject("sessionId is required"); return
        }
        // Delete the phone's copy…
        try? FileManager.default.removeItem(at: rootURL().appendingPathComponent(sessionId))
        // …and tell the watch to free its own buffer. transferUserInfo (not
        // sendMessage) so the ack is queued and delivered even if the watch app
        // isn't currently reachable.
        if WCSession.isSupported() {
            WCSession.default.transferUserInfo(["ack": sessionId])
        }
        call.resolve()
    }

    // MARK: - WCSessionDelegate

    public func session(_ session: WCSession, didReceive file: WCSessionFile) {
        let meta = file.metadata ?? [:]
        guard let sessionId = meta["sessionId"] as? String else { return }
        let sessionDir = rootURL().appendingPathComponent(sessionId)
        try? FileManager.default.createDirectory(at: sessionDir,
                                                 withIntermediateDirectories: true)

        let kind = meta["kind"] as? String ?? "data"
        if kind == "manifest" {
            // Last transfer of a session: persist the metadata durably, then
            // announce the completed bundle to JS for relaying.
            persistManifest(sessionId: sessionId, sessionDir: sessionDir, meta: meta)
            if let payload = loadManifestPayload(sessionId: sessionId, sessionDir: sessionDir) {
                notifyListeners("watchSessionReceived", data: payload)
            }
            return
        }

        // Data file: copy out of the OS temp location before returning (the
        // URL is only valid for the duration of this call).
        guard let filename = meta["filename"] as? String else { return }
        let dest = sessionDir.appendingPathComponent(filename)
        try? FileManager.default.removeItem(at: dest)
        try? FileManager.default.copyItem(at: file.fileURL, to: dest)
    }

    // MARK: - Manifest persistence

    private func persistManifest(sessionId: String, sessionDir: URL, meta: [String: Any]) {
        var stored: [String: Any] = [
            "sessionId": sessionId,
            "startedAt": meta["startedAt"] as? String ?? "",
            "mode": meta["mode"] as? String ?? "boat",
            "files": meta["files"] as? [String] ?? [],
        ]
        stored["boatId"] = meta["boatId"] as? String
        stored["endedAt"] = meta["endedAt"] as? String
        if let data = try? JSONSerialization.data(withJSONObject: stored) {
            try? data.write(to: sessionDir.appendingPathComponent(Self.manifestName))
        }
    }

    /// Reconstruct a `watchSessionReceived`-shaped payload from a persisted
    /// manifest.json, listing only files actually present on disk. Returns nil
    /// if the session has no manifest yet (a still-in-flight partial).
    private func loadManifestPayload(sessionId: String, sessionDir: URL) -> [String: Any]? {
        let manifestURL = sessionDir.appendingPathComponent(Self.manifestName)
        guard let data = try? Data(contentsOf: manifestURL),
              let stored = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }

        let declared = stored["files"] as? [String] ?? []
        let present = (try? FileManager.default.contentsOfDirectory(atPath: sessionDir.path)) ?? []
        let files = declared.filter { present.contains($0) }

        return [
            "sessionId": sessionId,
            "dir": "\(Self.rootFolder)/\(sessionId)",
            "files": files,
            "boatId": (stored["boatId"] as? String) ?? NSNull(),
            "startedAt": stored["startedAt"] as? String ?? "",
            "endedAt": (stored["endedAt"] as? String) ?? NSNull(),
            "mode": stored["mode"] as? String ?? "boat",
        ]
    }

    /// Delete abandoned partial transfers (a folder with data files but no
    /// manifest, older than `partialTTL`). Real pending sessions always have a
    /// manifest and are never touched here.
    private func sweepAbandonedPartials() {
        let fm = FileManager.default
        let dirs = (try? fm.contentsOfDirectory(atPath: rootURL().path)) ?? []
        let cutoff = Date().addingTimeInterval(-Self.partialTTL)
        for id in dirs {
            let sessionDir = rootURL().appendingPathComponent(id)
            let manifestURL = sessionDir.appendingPathComponent(Self.manifestName)
            if fm.fileExists(atPath: manifestURL.path) { continue } // real pending
            let created = (try? fm.attributesOfItem(atPath: sessionDir.path)[.creationDate]) as? Date
            if let created, created < cutoff {
                try? fm.removeItem(at: sessionDir)
            }
        }
    }

    // Required no-op delegate methods on iOS (support switching watches).
    public func session(_ session: WCSession,
                        activationDidCompleteWith activationState: WCSessionActivationState,
                        error: Error?) {}
    public func sessionDidBecomeInactive(_ session: WCSession) {}
    public func sessionDidDeactivate(_ session: WCSession) {
        WCSession.default.activate()
    }
}
