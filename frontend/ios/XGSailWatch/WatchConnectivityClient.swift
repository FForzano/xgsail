import Foundation
import WatchConnectivity

/// Watch side of WatchConnectivity. Sends each finished recording file to the
/// phone with `transferFile` (guaranteed background delivery — a phoneless
/// dinghy session uploads when the phone is next in range), then a final
/// `manifest` transfer that tells the phone the bundle is complete. Also
/// receives the phone's application context (selected boat / recording mode /
/// whether the watch is claimed) into `WatchContextStore`.
final class WatchConnectivityClient: NSObject, WCSessionDelegate {
    static let shared = WatchConnectivityClient()

    /// Session folders older than this are reclaimed on launch as a last
    /// resort (see `sweepOldSessions`) — long enough that anything real has
    /// been uploaded + acked (and thus already deleted) well before.
    private static let sessionTTL: TimeInterval = 30 * 24 * 3600

    func activate() {
        guard WCSession.isSupported() else { return }
        WCSession.default.delegate = self
        WCSession.default.activate()
        sweepOldSessions()
    }

    private func sessionsRoot() -> URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("sessions")
    }

    private func deleteSession(_ sessionId: String) {
        try? FileManager.default.removeItem(at: sessionsRoot().appendingPathComponent(sessionId))
    }

    /// Last-resort safety net so a watch whose phone never manages to upload
    /// (and therefore never acks) doesn't accumulate recordings forever. The
    /// primary cleanup is the ack path below; this only fires for folders older
    /// than `sessionTTL`.
    private func sweepOldSessions() {
        let fm = FileManager.default
        let dirs = (try? fm.contentsOfDirectory(atPath: sessionsRoot().path)) ?? []
        let cutoff = Date().addingTimeInterval(-Self.sessionTTL)
        for id in dirs {
            let url = sessionsRoot().appendingPathComponent(id)
            let created = (try? fm.attributesOfItem(atPath: url.path)[.creationDate]) as? Date
            if let created, created < cutoff { try? fm.removeItem(at: url) }
        }
    }

    /// Transfer one recorded session's CSV bundle to the phone. Each data file
    /// carries `{sessionId, filename, kind:"data"}`; a final `kind:"manifest"`
    /// transfer carries the session metadata + file list.
    func transferSession(sessionId: String, dir: URL, boatId: String?, mode: String,
                         startedAt: String, endedAt: String) {
        guard WCSession.isSupported() else { return }
        let session = WCSession.default
        let files = (try? FileManager.default.contentsOfDirectory(atPath: dir.path)) ?? []
        let dataFiles = files.filter { $0.hasSuffix(".csv") }

        for name in dataFiles {
            let url = dir.appendingPathComponent(name)
            session.transferFile(url, metadata: [
                "sessionId": sessionId, "filename": name, "kind": "data",
            ])
        }

        // Manifest last — same session folder, an empty marker file (transferFile
        // needs a real URL) with all the metadata attached.
        let manifestURL = dir.appendingPathComponent("_manifest")
        FileManager.default.createFile(atPath: manifestURL.path, contents: Data())
        var meta: [String: Any] = [
            "sessionId": sessionId, "kind": "manifest", "mode": mode,
            "startedAt": startedAt, "endedAt": endedAt, "files": dataFiles,
        ]
        if let boatId { meta["boatId"] = boatId }
        session.transferFile(manifestURL, metadata: meta)
    }

    // MARK: - WCSessionDelegate

    func session(_ session: WCSession,
                 activationDidCompleteWith activationState: WCSessionActivationState,
                 error: Error?) {}

    func session(_ session: WCSession, didReceiveApplicationContext context: [String: Any]) {
        WatchContextStore.shared.update(from: context)
    }

    /// The phone acks an uploaded session (frees the watch's local buffer).
    /// The phone sends this via `transferUserInfo` (guaranteed delivery, even
    /// if the watch app was closed when the upload finished); the message
    /// variant is kept for the reachable case.
    func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any]) {
        if let sessionId = userInfo["ack"] as? String { deleteSession(sessionId) }
    }

    func session(_ session: WCSession, didReceiveMessage message: [String: Any]) {
        if let sessionId = message["ack"] as? String { deleteSession(sessionId) }
    }
}
