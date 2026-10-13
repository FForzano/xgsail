import Foundation
import Combine

/// The watch's working true wind direction, which TWA and VMG hang off. The
/// watch has no wind sensor, so the estimate comes from three places, newest
/// wins:
///
/// - **phone**: the iPhone's `GET /wind/nearest` snapshot, pushed with the
///   context before going out — a bonus, never a requirement;
/// - **manual**: the sailor sets it with the Crown, which works with no phone;
/// - **tacks**: each tack or gybe nudges the estimate towards the bisector of
///   the headings either side of it (`NavMath.maneuverTWD`) — the same idea as
///   the backend's `tack_wind.py`, and like it COG-based, so current biases it.
///   It needs a prior to know a tack from a gybe, so it refines, never seeds.
final class WindEstimator: ObservableObject {
    enum Source: String, Codable { case phone, manual, tacks }

    struct Estimate: Codable, Equatable {
        var twdDeg: Double
        var source: Source
        var at: Date
        var tacks: Int = 0
    }

    @Published private(set) var estimate: Estimate?
    /// Wind speed is only ever known from the phone's snapshot.
    @Published private(set) var phoneTwsKn: Double?

    /// Past this, a reading says more about yesterday than about now.
    static let staleAfter: TimeInterval = 3 * 3600

    private static let defaultsKey = "xgsail.watch.wind"
    private var fixes: [(t: Date, cog: Double)] = []
    private var lastManeuverAt = Date.distantPast
    private var phoneWatch: AnyCancellable?

    init(context: WatchContextStore = .shared) {
        if let data = UserDefaults.standard.data(forKey: Self.defaultsKey) {
            estimate = try? JSONDecoder().decode(Estimate.self, from: data)
        }
        phoneWatch = context.$phoneWind.compactMap { $0 }.sink { [weak self] in self?.applyPhone($0) }
    }

    /// The TWD to sail by, or nil when there is none fresh enough to trust.
    func currentTWD(at now: Date = Date()) -> Double? {
        guard let estimate, now.timeIntervalSince(estimate.at) < Self.staleAfter else { return nil }
        return estimate.twdDeg
    }

    func setManual(_ twd: Double) {
        save(Estimate(twdDeg: NavMath.wrap360(twd), source: .manual, at: Date()))
    }

    /// A phone snapshot replaces the estimate only if it is newer: a value
    /// set or refined on the water beats an older reading from ashore.
    private func applyPhone(_ wind: WatchContextStore.PhoneWind) {
        phoneTwsKn = wind.twsKn
        if let estimate, estimate.at >= wind.observedAt { return }
        save(Estimate(twdDeg: wind.twdDeg, source: .phone, at: wind.observedAt))
    }

    /// Feed every smoothed fix while moving; looks for a completed maneuver
    /// between a steady heading 15–25 s ago and a steady heading now.
    func ingest(at t: Date, cogDeg: Double, sogKn: Double) {
        guard sogKn >= 1.5 else { return }
        fixes.append((t, cogDeg))
        fixes.removeAll { t.timeIntervalSince($0.t) > 30 }
        guard t.timeIntervalSince(lastManeuverAt) > 30, let prior = currentTWD(at: t) else { return }

        let before = fixes.filter { (15...25).contains(t.timeIntervalSince($0.t)) }.map(\.cog)
        let after = fixes.filter { t.timeIntervalSince($0.t) <= 6 }.map(\.cog)
        guard before.count >= 3, after.count >= 3,
              let b = NavMath.circularMean(before), b.steadiness > 0.96,
              let a = NavMath.circularMean(after), a.steadiness > 0.96,
              let reading = NavMath.maneuverTWD(before: b.mean, after: a.mean, prior: prior)
        else { return }

        lastManeuverAt = t
        let tacks = (estimate?.source == .tacks ? estimate?.tacks ?? 0 : 0) + 1
        save(Estimate(twdDeg: NavMath.blend(prior, reading, weight: 0.35), source: .tacks, at: t, tacks: tacks))
    }

    private func save(_ new: Estimate) {
        estimate = new
        if let data = try? JSONEncoder().encode(new) {
            UserDefaults.standard.set(data, forKey: Self.defaultsKey)
        }
    }
}
