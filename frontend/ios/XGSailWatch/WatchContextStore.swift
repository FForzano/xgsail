import Foundation
import Combine

/// Holds the context the phone pushes to the watch (`sendContext` on the phone
/// → application context here): which boat the session is for, the recording
/// mode ("boat" = watch GPS is the boat track, "personal" = the boat already
/// has a tracker so it's just the wearer's own data), and whether the watch
/// has been claimed as a device (recording is blocked until it is).
final class WatchContextStore: ObservableObject {
    static let shared = WatchContextStore()

    @Published private(set) var boatId: String?
    @Published private(set) var boatName: String?
    @Published private(set) var mode: String = "boat"
    @Published private(set) var deviceClaimed: Bool = false

    func update(from context: [String: Any]) {
        DispatchQueue.main.async {
            self.boatId = context["boatId"] as? String
            self.boatName = context["boatName"] as? String
            if let mode = context["mode"] as? String { self.mode = mode }
            self.deviceClaimed = context["deviceClaimed"] as? Bool ?? false
        }
    }
}
