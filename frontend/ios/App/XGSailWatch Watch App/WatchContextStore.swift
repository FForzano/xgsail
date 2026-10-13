import Foundation
import Combine

/// Holds the context the phone pushes to the watch (`sendContext` on the phone
/// → application context here): which boat the session is for, the recording
/// mode ("boat" = watch GPS is the boat track, "personal" = the boat already
/// has a tracker so it's just the wearer's own data), whether the watch has
/// been claimed as a device, and the phone's last live wind snapshot.
///
/// Persisted, because the watch has to work with no phone in range: a cold
/// launch on the water starts from the last context it heard, not from
/// nothing. Nothing here gates recording — an unclaimed watch still records,
/// and its sessions wait on the wrist until a claimed phone relays them.
final class WatchContextStore: ObservableObject {
    static let shared = WatchContextStore()

    struct PhoneWind: Equatable {
        let twdDeg: Double
        let twsKn: Double?
        let observedAt: Date
    }

    @Published private(set) var boatId: String?
    @Published private(set) var boatName: String?
    @Published private(set) var mode: String = "boat"
    @Published private(set) var deviceClaimed: Bool = false
    @Published private(set) var phoneWind: PhoneWind?

    private static let defaultsKey = "xgsail.watch.context"

    private init() {
        if let saved = UserDefaults.standard.dictionary(forKey: Self.defaultsKey) {
            apply(saved)
        }
    }

    func update(from context: [String: Any]) {
        guard !context.isEmpty else { return }
        UserDefaults.standard.set(context, forKey: Self.defaultsKey)
        DispatchQueue.main.async { self.apply(context) }
    }

    private func apply(_ context: [String: Any]) {
        boatId = context["boatId"] as? String
        boatName = context["boatName"] as? String
        if let mode = context["mode"] as? String { self.mode = mode }
        deviceClaimed = context["deviceClaimed"] as? Bool ?? false
        if let twd = context["windTwdDeg"] as? Double,
           let at = (context["windObservedAt"] as? String).flatMap(Self.parseISO) {
            phoneWind = PhoneWind(twdDeg: twd, twsKn: context["windTwsKts"] as? Double, observedAt: at)
        }
    }

    private static func parseISO(_ s: String) -> Date? {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = f.date(from: s) { return d }
        f.formatOptions = [.withInternetDateTime]
        return f.date(from: s)
    }
}
