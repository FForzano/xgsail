import Foundation
import Combine
import CoreLocation
import WatchKit

/// One race's start sequence, run *inside* a recording: the outing is the
/// container, a race is a phase of it (several per regatta day). Starting a
/// sequence from idle starts the recording too, so the pre-start manoeuvring
/// is always on the track. Every event goes to `watch_race.csv` through `log`
/// (docs/device-protocol.md §9.3) — observational only, never a race result.
///
/// The ticker lives here, not in a view: with the wrist down no view is
/// drawing, and the gun still has to fire, buzz, and be logged at the instant
/// it actually happened.
final class RaceTimer: ObservableObject {
    enum Phase: Equatable {
        case off
        case countdown(gun: Date)
        case racing(gun: Date)
        case finished(gun: Date, finish: Date)
    }

    @Published private(set) var phase: Phase = .off
    @Published private(set) var boatEnd: CLLocationCoordinate2D?
    @Published private(set) var pinEnd: CLLocationCoordinate2D?
    /// Length of the next sequence, remembered across launches.
    @Published var sequenceMinutes: Int {
        didSet { UserDefaults.standard.set(sequenceMinutes, forKey: Self.minutesKey) }
    }

    static let minuteRange = 1...10
    /// Receives each event for `watch_race.csv`: phase name and its instant.
    var log: ((String, Date) -> Void)?

    private static let minutesKey = "xgsail.watch.sequenceMinutes"
    private var ticker: Timer?
    private var lastCueSecond: Int?

    init() {
        let saved = UserDefaults.standard.integer(forKey: Self.minutesKey)
        sequenceMinutes = Self.minuteRange.contains(saved) ? saved : 5
    }

    func start(minutes: Int) {
        let now = Date()
        phase = .countdown(gun: now.addingTimeInterval(TimeInterval(minutes * 60)))
        log?("countdown_start", now)
        lastCueSecond = minutes * 60   // the start buzz already covers this second
        WKInterfaceDevice.current().play(.start)
        startTicker()
    }

    /// Tap on a committee minute signal: snap to the nearest whole minute.
    func sync() {
        guard case .countdown(let gun) = phase else { return }
        let now = Date()
        let synced = NavMath.syncedGun(gun: gun, now: now)
        log?("resync", now)
        WKInterfaceDevice.current().play(.click)
        if synced <= now {
            fireGun(at: now)
        } else {
            phase = .countdown(gun: synced)
            lastCueSecond = Int(synced.timeIntervalSince(now).rounded())
        }
    }

    /// Postponement or general recall: back to no race, ready for a new start.
    func cancel() {
        guard case .countdown = phase else { return }
        log?("cancel", Date())
        stopTicker()
        phase = .off
    }

    /// Crossing the finish line — instant, no confirmation, the time matters.
    /// Callable again once finished: the later press replaces the finish (and
    /// the last `finish` row is the one that counts), so an accidental early
    /// press is corrected by the real one.
    func finish() {
        let gun: Date
        switch phase {
        case .racing(let g), .finished(let g, _): gun = g
        default: return
        }
        let now = Date()
        log?("finish", now)
        WKInterfaceDevice.current().play(.success)
        phase = .finished(gun: gun, finish: now)
    }

    func newStart() {
        if case .finished = phase { phase = .off }
    }

    func ping(boat location: CLLocationCoordinate2D) {
        boatEnd = location
        WKInterfaceDevice.current().play(.click)
    }

    func ping(pin location: CLLocationCoordinate2D) {
        pinEnd = location
        WKInterfaceDevice.current().play(.click)
    }

    /// The recording ended; the race (and its line) end with it.
    func reset() {
        stopTicker()
        phase = .off
        boatEnd = nil
        pinEnd = nil
    }

    // MARK: - Ticker

    private func startTicker() {
        stopTicker()
        let timer = Timer(timeInterval: 0.1, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.tick() }
        }
        RunLoop.main.add(timer, forMode: .common)
        ticker = timer
    }

    private func stopTicker() {
        ticker?.invalidate()
        ticker = nil
    }

    private func tick() {
        guard case .countdown(let gun) = phase else { return }
        let now = Date()
        if now >= gun { fireGun(at: gun); return }
        let second = Int(gun.timeIntervalSince(now).rounded(.up))
        guard second != lastCueSecond else { return }
        lastCueSecond = second
        if let cue = Self.cue(secondsLeft: second) { WKInterfaceDevice.current().play(cue) }
    }

    /// Like a dedicated regatta watch: a strong cue on every minute and at
    /// 30 s, ticks at 20 and 15, then every second of the last ten.
    private static func cue(secondsLeft s: Int) -> WKHapticType? {
        if s % 60 == 0 || s == 30 { return .notification }
        if s == 20 || s == 15 || s <= 10 { return .click }
        return nil
    }

    private func fireGun(at gun: Date) {
        stopTicker()
        phase = .racing(gun: gun)
        log?("start", gun)
        WKInterfaceDevice.current().play(.start)
    }
}
