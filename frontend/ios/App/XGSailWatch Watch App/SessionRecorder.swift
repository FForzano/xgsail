import Foundation
import Combine
import CoreLocation
import HealthKit

/// The watch-side recording engine (docs/device-protocol.md §9). Runs an
/// `HKWorkoutSession` so recording continues in the background / wrist-down,
/// collecting GPS (CoreLocation) plus HealthKit physiological signals, and
/// appends each to a per-session CSV in the format the XGSail worker parses:
///
///   watch_nav.csv     t,lat,lon,speed_kn,course
///   watch_hr.csv      t,bpm
///   watch_energy.csv  t,kcal
///   watch_hrv.csv     t,ms
///   watch_resp.csv    t,brpm
///   watch_race.csv    t,phase   (optional — only written if race mode is used)
///
/// `t` is ISO 8601 UTC with millisecond precision + trailing Z. On stop the
/// files are handed to `WatchConnectivityClient` to transfer to the phone.
final class SessionRecorder: NSObject, ObservableObject {
    enum State { case idle, recording, paused, stopped }

    /// Race-mode start-sequence state (docs/device-protocol.md). Purely a
    /// watch-side observation: `.started`'s instant is written to
    /// `watch_race.csv` as raw per-session data, never as an authoritative
    /// race start — human tap latency means independent boats' watches will
    /// disagree slightly.
    enum RaceState: Equatable {
        case off
        case countdown(target: Date)
        case started(at: Date)
    }

    @Published private(set) var state: State = .idle
    /// Live nav readouts for the UI.
    @Published private(set) var speedKn: Double = 0
    @Published private(set) var courseDeg: Double = 0
    @Published private(set) var heartRate: Int = 0
    @Published private(set) var raceState: RaceState = .off

    private let healthStore = HKHealthStore()
    private var workoutSession: HKWorkoutSession?
    private var workoutBuilder: HKLiveWorkoutBuilder?
    private let locationManager = CLLocationManager()

    private var sessionId: String = ""
    private var startedAt: Date?
    private var sessionDir: URL?
    private var anchoredQueries: [HKQuery] = []
    private var raceFileReady = false

    private let isoFormatter: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        f.timeZone = TimeZone(identifier: "UTC")
        return f
    }()

    override init() {
        super.init()
        locationManager.delegate = self
        locationManager.desiredAccuracy = kCLLocationAccuracyBestForNavigation
        locationManager.activityType = .otherNavigation
    }

    // MARK: - Authorization

    /// Read authorization for the signals we record, plus workout write. Call
    /// once before the first recording.
    func requestAuthorization() async {
        guard HKHealthStore.isHealthDataAvailable() else { return }
        var readTypes: Set<HKObjectType> = [HKObjectType.workoutType()]
        for id in Self.quantityTypeIds {
            if let t = HKObjectType.quantityType(forIdentifier: id) { readTypes.insert(t) }
        }
        let shareTypes: Set<HKSampleType> = [HKObjectType.workoutType()]
        try? await healthStore.requestAuthorization(toShare: shareTypes, read: readTypes)
        locationManager.requestWhenInUseAuthorization()
    }

    private static let quantityTypeIds: [HKQuantityTypeIdentifier] = [
        .heartRate, .activeEnergyBurned, .heartRateVariabilitySDNN, .respiratoryRate,
    ]

    // MARK: - Lifecycle

    func start() {
        guard state == .idle else { return }
        sessionId = "\(Int(Date().timeIntervalSince1970))-\(UUID().uuidString.prefix(8))"
        startedAt = Date()
        prepareFiles()

        let config = HKWorkoutConfiguration()
        config.activityType = .sailing
        config.locationType = .outdoor
        do {
            let session = try HKWorkoutSession(healthStore: healthStore, configuration: config)
            let builder = session.associatedWorkoutBuilder()
            builder.dataSource = HKLiveWorkoutDataSource(healthStore: healthStore,
                                                         workoutConfiguration: config)
            builder.delegate = self
            session.delegate = self
            self.workoutSession = session
            self.workoutBuilder = builder
            session.startActivity(with: Date())
            builder.beginCollection(withStart: Date()) { _, _ in }
        } catch {
            // Fall back to location-only recording if HealthKit is unavailable.
        }

        locationManager.startUpdatingLocation()
        startAnchoredQueries()
        state = .recording
    }

    func pause() {
        guard state == .recording else { return }
        workoutSession?.pause()
        locationManager.stopUpdatingLocation()
        state = .paused
    }

    func resume() {
        guard state == .paused else { return }
        workoutSession?.resume()
        locationManager.startUpdatingLocation()
        state = .recording
    }

    /// Stop recording, close files, and transfer the bundle to the phone.
    func stop() {
        guard state == .recording || state == .paused else { return }
        locationManager.stopUpdatingLocation()
        anchoredQueries.forEach { healthStore.stop($0) }
        anchoredQueries.removeAll()

        let end = Date()
        workoutSession?.end()
        workoutBuilder?.endCollection(withEnd: end) { [weak self] _, _ in
            self?.workoutBuilder?.finishWorkout { _, _ in }
        }

        if let dir = sessionDir, let started = startedAt {
            WatchConnectivityClient.shared.transferSession(
                sessionId: sessionId,
                dir: dir,
                boatId: WatchContextStore.shared.boatId,
                mode: WatchContextStore.shared.mode,
                startedAt: isoFormatter.string(from: started),
                endedAt: isoFormatter.string(from: end)
            )
        }
        state = .stopped
        raceState = .off
        raceFileReady = false
    }

    func reset() {
        state = .idle
        speedKn = 0
        courseDeg = 0
        heartRate = 0
        raceState = .off
        raceFileReady = false
    }

    // MARK: - Race mode

    /// Enter the countdown, `minutes` from now. Only meaningful while
    /// recording — the marker needs a session to attach to.
    func startRaceCountdown(minutes: Int) {
        guard state == .recording, raceState == .off else { return }
        raceState = .countdown(target: Date().addingTimeInterval(TimeInterval(minutes * 60)))
        appendRaceEvent("countdown_start")
    }

    /// Realign the countdown target to the nearest whole minute (matches the
    /// committee boat's minute signals, same behavior as dedicated regatta
    /// watches), correcting for drift since `startRaceCountdown`.
    func resyncRaceCountdown() {
        guard case .countdown(let target) = raceState else { return }
        let rounded = (target.timeIntervalSince1970 / 60).rounded() * 60
        raceState = .countdown(target: Date(timeIntervalSince1970: rounded))
        appendRaceEvent("resync")
    }

    /// Called by the UI's periodic tick once `target` has passed — flips the
    /// countdown into a running chronometer and logs the observed start.
    func markRaceStart() {
        guard case .countdown = raceState else { return }
        raceState = .started(at: Date())
        appendRaceEvent("start")
    }

    func cancelRaceCountdown() {
        raceState = .off
    }

    private func appendRaceEvent(_ phase: String) {
        if !raceFileReady {
            writeHeader("watch_race.csv", "t,phase")
            raceFileReady = true
        }
        append("watch_race.csv", "\(now()),\(phase)")
    }

    // MARK: - File writing

    private func prepareFiles() {
        let base = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("sessions").appendingPathComponent(sessionId)
        try? FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        sessionDir = base
        writeHeader("watch_nav.csv", "t,lat,lon,speed_kn,course")
        writeHeader("watch_hr.csv", "t,bpm")
        writeHeader("watch_energy.csv", "t,kcal")
        writeHeader("watch_hrv.csv", "t,ms")
        writeHeader("watch_resp.csv", "t,brpm")
    }

    private func writeHeader(_ name: String, _ header: String) {
        guard let dir = sessionDir else { return }
        try? (header + "\n").write(to: dir.appendingPathComponent(name),
                                   atomically: true, encoding: .utf8)
    }

    private func append(_ name: String, _ line: String) {
        guard let dir = sessionDir else { return }
        let url = dir.appendingPathComponent(name)
        guard let handle = try? FileHandle(forWritingTo: url) else { return }
        defer { try? handle.close() }
        handle.seekToEndOfFile()
        if let data = (line + "\n").data(using: .utf8) { handle.write(data) }
    }

    private func now() -> String { isoFormatter.string(from: Date()) }

    // MARK: - HealthKit anchored queries (HRV + respiration)

    private func startAnchoredQueries() {
        guard let started = startedAt else { return }
        let predicate = HKQuery.predicateForSamples(withStart: started, end: nil, options: .strictStartDate)
        addAnchoredQuery(.heartRateVariabilitySDNN, unit: HKUnit.secondUnit(with: .milli),
                         file: "watch_hrv.csv", predicate: predicate)
        addAnchoredQuery(.respiratoryRate, unit: HKUnit.count().unitDivided(by: .minute()),
                         file: "watch_resp.csv", predicate: predicate)
    }

    private func addAnchoredQuery(_ id: HKQuantityTypeIdentifier, unit: HKUnit,
                                  file: String, predicate: NSPredicate) {
        guard let type = HKObjectType.quantityType(forIdentifier: id) else { return }
        let handler: (HKAnchoredObjectQuery, [HKSample]?, [HKDeletedObject]?, HKQueryAnchor?, Error?) -> Void = {
            [weak self] _, samples, _, _, _ in
            guard let self, let samples = samples as? [HKQuantitySample] else { return }
            for s in samples {
                let value = s.quantity.doubleValue(for: unit)
                self.append(file, "\(self.isoFormatter.string(from: s.endDate)),\(String(format: "%.2f", value))")
            }
        }
        let query = HKAnchoredObjectQuery(type: type, predicate: predicate,
                                          anchor: nil, limit: HKObjectQueryNoLimit,
                                          resultsHandler: handler)
        query.updateHandler = handler
        healthStore.execute(query)
        anchoredQueries.append(query)
    }
}

// MARK: - Location

extension SessionRecorder: CLLocationManagerDelegate {
    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard state == .recording, let loc = locations.last else { return }
        let kn = max(0, loc.speed) * 1.94384          // m/s → knots
        let course = loc.course >= 0 ? loc.course : courseDeg
        speedKn = kn
        courseDeg = course
        append("watch_nav.csv",
               "\(now()),\(loc.coordinate.latitude),\(loc.coordinate.longitude)," +
               "\(String(format: "%.2f", kn)),\(String(format: "%.1f", course))")
    }
}

// MARK: - Workout builder (heart rate + active energy)

extension SessionRecorder: HKLiveWorkoutBuilderDelegate {
    func workoutBuilder(_ builder: HKLiveWorkoutBuilder,
                        didCollectDataOf collectedTypes: Set<HKSampleType>) {
        for type in collectedTypes {
            guard let qType = type as? HKQuantityType,
                  let stats = builder.statistics(for: qType) else { continue }
            if qType == HKQuantityType.quantityType(forIdentifier: .heartRate) {
                let bpm = stats.mostRecentQuantity()?
                    .doubleValue(for: HKUnit.count().unitDivided(by: .minute())) ?? 0
                heartRate = Int(bpm.rounded())
                append("watch_hr.csv", "\(now()),\(Int(bpm.rounded()))")
            } else if qType == HKQuantityType.quantityType(forIdentifier: .activeEnergyBurned) {
                let kcal = stats.sumQuantity()?.doubleValue(for: .kilocalorie()) ?? 0
                append("watch_energy.csv", "\(now()),\(String(format: "%.2f", kcal))")
            }
        }
    }

    func workoutBuilderDidCollectEvent(_ builder: HKLiveWorkoutBuilder) {}
}

// MARK: - Workout session state

extension SessionRecorder: HKWorkoutSessionDelegate {
    func workoutSession(_ workoutSession: HKWorkoutSession,
                        didChangeTo toState: HKWorkoutSessionState,
                        from fromState: HKWorkoutSessionState, date: Date) {}
    func workoutSession(_ workoutSession: HKWorkoutSession, didFailWithError error: Error) {}
}
