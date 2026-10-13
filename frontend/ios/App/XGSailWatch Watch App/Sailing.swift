import Foundation

/// The three on-water models and the rules that span them. Shared because
/// two kinds of caller drive them: the app's views, and the Action button's
/// intents (`ActionButtonIntents.swift`), which run in the same process but
/// outside any view.
final class Sailing {
    static let shared = Sailing()

    let recorder = SessionRecorder()
    let race = RaceTimer()
    let wind = WindEstimator()

    private init() {
        race.log = { [weak recorder] phase, at in recorder?.appendRaceEvent(phase, at: at) }
        recorder.onFix = { [weak wind] t, cog, sog in wind?.ingest(at: t, cogDeg: cog, sogKn: sog) }
        recorder.onStop = { [weak race] in race?.reset() }
    }

    /// Make sure a recording is running: a fresh one from idle or from the
    /// summary of the last, or the paused one resumed.
    func startOuting() {
        switch recorder.state {
        case .stopped: recorder.reset(); recorder.start()
        case .idle: recorder.start()
        case .paused: recorder.resume()
        case .recording: break
        }
    }

    /// A race always runs inside a recording, so starting a sequence starts
    /// the recording too: the pre-start belongs on the track.
    func startSequence(minutes: Int) {
        startOuting()
        race.newStart()
        race.start(minutes: minutes)
    }

    /// One physical button, the most time-critical tap of the moment, done
    /// blind (gloves, Water Lock, eyes on the committee boat):
    /// no race → start a sequence; countdown → sync; racing → finish;
    /// finished → finish again. That last one is deliberate: an accidental
    /// press mid-race logs an early finish, and the real finish has to be able
    /// to replace it rather than start a new sequence. The next race's start
    /// is a tap on screen.
    func actionButton() {
        switch race.phase {
        case .off: startSequence(minutes: race.sequenceMinutes)
        case .countdown: race.sync()
        case .racing, .finished: race.finish()
        }
    }
}
