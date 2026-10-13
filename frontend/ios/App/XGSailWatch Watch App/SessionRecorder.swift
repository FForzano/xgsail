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
///   watch_race.csv    t,phase   (optional — only written if a start sequence is run)
///
/// `t` is ISO 8601 UTC with millisecond precision + trailing Z. On stop the
/// files are handed to `WatchConnectivityClient` to transfer to the phone.
final class SessionRecorder: NSObject, ObservableObject {
    enum State { case idle, recording, paused, stopped }

    /// What the stopped screen shows about the outing just ended.
    struct Summary {
        let duration: TimeInterval
        let distanceNm: Double
        let maxSogKn: Double
    }

    @Published private(set) var state: State = .idle
    /// Live nav readouts for the UI, smoothed — raw watch GPS speed jitters
    /// by a knot from fix to fix, which no one can read at a glance.
    @Published private(set) var speedKn: Double = 0
    @Published private(set) var courseDeg: Double = 0
    @Published private(set) var heartRate: Int = 0
    @Published private(set) var distanceNm: Double = 0
    @Published private(set) var maxSogKn: Double = 0
    @Published private(set) var lastFix: CLLocation?
    @Published private(set) var summary: Summary?

    /// Every smoothed fix, for the wind estimator (wired in `XGSailWatchApp`).
    var onFix: ((Date, _ cogDeg: Double, _ sogKn: Double) -> Void)?
    /// Called once a recording ends, so the race ends with it.
    var onStop: (() -> Void)?

    private let healthStore = HKHealthStore()
    private var workoutSession: HKWorkoutSession?
    private var workoutBuilder: HKLiveWorkoutBuilder?
    private let locationManager = CLLocationManager()

    private var sessionId: String = ""
    private(set) var startedAt: Date?
    private var pausedAt: Date?
    private var pausedTotal: TimeInterval = 0
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

    /// Time under way, paused stretches excluded.
    func elapsed(at now: Date = Date()) -> TimeInterval {
        guard let startedAt else { return 0 }
        let pausedNow = pausedAt.map { now.timeIntervalSince($0) } ?? 0
        return now.timeIntervalSince(startedAt) - pausedTotal - pausedNow
    }

    /// A fix recent and accurate enough to sail by.
    func hasFix(at now: Date = Date()) -> Bool {
        guard let lastFix else { return false }
        return now.timeIntervalSince(lastFix.timestamp) < 10 && lastFix.horizontalAccuracy < 50
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
        pausedAt = Date()
        state = .paused
    }

    func resume() {
        guard state == .paused else { return }
        workoutSession?.resume()
        locationManager.startUpdatingLocation()
        if let pausedAt { pausedTotal += Date().timeIntervalSince(pausedAt) }
        pausedAt = nil
        state = .recording
    }

    /// Stop recording, close files, and transfer the bundle to the phone —
    /// queued by WatchConnectivity if the phone isn't in range, so a phoneless
    /// outing uploads whenever the two next meet.
    func stop() {
        guard state == .recording || state == .paused else { return }
        locationManager.stopUpdatingLocation()
        anchoredQueries.forEach { healthStore.stop($0) }
        anchoredQueries.removeAll()

        let end = Date()
        summary = Summary(duration: elapsed(at: end), distanceNm: distanceNm, maxSogKn: maxSogKn)
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
        raceFileReady = false
        onStop?()
    }

    func reset() {
        state = .idle
        speedKn = 0
        courseDeg = 0
        heartRate = 0
        distanceNm = 0
        maxSogKn = 0
        lastFix = nil
        summary = nil
        startedAt = nil
        pausedAt = nil
        pausedTotal = 0
        raceFileReady = false
    }

    // MARK: - Race events

    /// One `watch_race.csv` row (docs/device-protocol.md §9.3), stamped with
    /// the instant the event happened — for `start` that is the gun, not
    /// whenever the screen next woke up.
    func appendRaceEvent(_ phase: String, at instant: Date) {
        guard sessionDir != nil else { return }
        if !raceFileReady {
            writeHeader("watch_race.csv", "t,phase")
            raceFileReady = true
        }
        append("watch_race.csv", "\(isoFormatter.string(from: instant)),\(phase)")
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
            guard let samples = samples as? [HKQuantitySample] else { return }
            let rows = samples.map { ($0.endDate, $0.quantity.doubleValue(for: unit)) }
            DispatchQueue.main.async {
                guard let self else { return }
                for (end, value) in rows {
                    self.append(file, "\(self.isoFormatter.string(from: end)),\(String(format: "%.2f", value))")
                }
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
        // Raw values go to the file; the worker does its own filtering.
        let rawCourse = loc.course >= 0 ? loc.course : courseDeg
        append("watch_nav.csv",
               "\(now()),\(loc.coordinate.latitude),\(loc.coordinate.longitude)," +
               "\(String(format: "%.2f", kn)),\(String(format: "%.1f", rawCourse))")

        guard loc.horizontalAccuracy >= 0, loc.horizontalAccuracy < 50 else { return }
        if let prev = lastFix, prev.horizontalAccuracy < 30, loc.horizontalAccuracy < 30 {
            distanceNm += loc.distance(from: prev) / 1852
        }
        speedKn = lastFix == nil ? kn : speedKn + (kn - speedKn) * 0.4
        lastFix = loc
        maxSogKn = max(maxSogKn, speedKn)
        // COG is noise below steerage way, so it holds its last value there.
        if loc.course >= 0, kn > 0.8 {
            courseDeg = NavMath.blend(courseDeg, loc.course, weight: 0.4)
        }
        onFix?(loc.timestamp, courseDeg, speedKn)
    }
}

// MARK: - Workout builder (heart rate + active energy)

extension SessionRecorder: HKLiveWorkoutBuilderDelegate {
    // HealthKit calls these on its own queue; state lives on the main actor.
    nonisolated func workoutBuilder(_ builder: HKLiveWorkoutBuilder,
                                    didCollectDataOf collectedTypes: Set<HKSampleType>) {
        DispatchQueue.main.async { self.collect(builder, collectedTypes) }
    }

    private func collect(_ builder: HKLiveWorkoutBuilder, _ collectedTypes: Set<HKSampleType>) {
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

    nonisolated func workoutBuilderDidCollectEvent(_ builder: HKLiveWorkoutBuilder) {}
}

// MARK: - Workout session state

extension SessionRecorder: HKWorkoutSessionDelegate {
    nonisolated func workoutSession(_ workoutSession: HKWorkoutSession,
                        didChangeTo toState: HKWorkoutSessionState,
                        from fromState: HKWorkoutSessionState, date: Date) {}
    nonisolated func workoutSession(_ workoutSession: HKWorkoutSession, didFailWithError error: Error) {}
}
