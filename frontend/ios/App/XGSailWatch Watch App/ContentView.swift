import SwiftUI

/// Glanceable nav display + recording controls (docs/device-protocol.md §9):
/// clock, speed-over-ground (kn) and course-over-ground (°) during recording,
/// and start / pause / stop. Boat + mode come from the phone
/// (`WatchContextStore`); recording is blocked until the watch is claimed.
struct ContentView: View {
    @EnvironmentObject private var recorder: SessionRecorder
    @ObservedObject private var context = WatchContextStore.shared
    @State private var raceMinutes = 5
    @State private var showRaceStaging = false

    var body: some View {
        VStack(spacing: 8) {
            topArea
            if recorder.state == .recording || recorder.state == .paused {
                readouts
            } else {
                header
            }
            controls
        }
        .padding(.horizontal, 6)
    }

    /// Clock, unless recording and race mode is staged/running — then the
    /// countdown/chronometer takes its place (docs/device-protocol.md).
    @ViewBuilder private var topArea: some View {
        if recorder.state == .recording {
            switch recorder.raceState {
            case .off:
                if showRaceStaging {
                    raceStaging
                } else {
                    VStack(spacing: 2) {
                        clock
                        Button("Regata") { showRaceStaging = true }
                            .font(.caption2)
                            .buttonStyle(.plain)
                            .foregroundStyle(.blue)
                    }
                }
            case .countdown(let target):
                raceCountdown(target: target)
            case .started(let startedAt):
                raceChronometer(since: startedAt)
            }
        } else {
            clock
        }
    }

    private var clock: some View {
        TimelineView(.periodic(from: .now, by: 1)) { ctx in
            Text(ctx.date, format: .dateTime.hour().minute().second())
                .font(.system(.title3, design: .rounded).monospacedDigit())
                .foregroundStyle(.secondary)
        }
    }

    private var raceStaging: some View {
        VStack(spacing: 4) {
            Button {
                raceMinutes = raceMinutes == 5 ? 4 : (raceMinutes == 4 ? 1 : 5)
            } label: {
                Text("\(raceMinutes) min")
                    .font(.system(.title3, design: .rounded).monospacedDigit())
            }
            .buttonStyle(.plain)
            HStack {
                Button("Via") {
                    recorder.startRaceCountdown(minutes: raceMinutes)
                    showRaceStaging = false
                }.tint(.green)
                Button("Annulla") { showRaceStaging = false }.tint(.gray)
            }
            .font(.caption2)
        }
    }

    private func raceCountdown(target: Date) -> some View {
        TimelineView(.periodic(from: .now, by: 1)) { ctx in
            VStack(spacing: 4) {
                Text(raceClock(target.timeIntervalSince(ctx.date)))
                    .font(.system(.title2, design: .rounded).monospacedDigit())
                HStack {
                    Button("Resync") { recorder.resyncRaceCountdown() }.tint(.blue)
                    Button("Annulla") { recorder.cancelRaceCountdown() }.tint(.gray)
                }
                .font(.caption2)
            }
            .onChange(of: ctx.date) { _, newDate in
                if newDate >= target { recorder.markRaceStart() }
            }
        }
    }

    private func raceChronometer(since startedAt: Date) -> some View {
        TimelineView(.periodic(from: .now, by: 1)) { ctx in
            VStack(spacing: 2) {
                Text(raceClock(ctx.date.timeIntervalSince(startedAt)))
                    .font(.system(.title2, design: .rounded).monospacedDigit())
                    .foregroundStyle(.green)
                Button("Orologio") { recorder.cancelRaceCountdown() }
                    .font(.caption2)
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
            }
        }
    }

    /// mm:ss for both the countdown (counting down to 0) and the chronometer
    /// (counting up) — negative/overflowing input is clamped to 0.
    private func raceClock(_ interval: TimeInterval) -> String {
        let total = max(0, Int(interval.rounded()))
        return String(format: "%02d:%02d", total / 60, total % 60)
    }

    private var header: some View {
        VStack(spacing: 2) {
            Text("XGSail").font(.headline)
            if let boat = context.boatName ?? context.boatId {
                Text(boat).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            Text(context.mode == "personal" ? "Dati personali" : "Traccia barca")
                .font(.caption2).foregroundStyle(.secondary)
        }
    }

    private var readouts: some View {
        HStack {
            metric(value: String(format: "%.1f", recorder.speedKn), unit: "kn")
            Divider()
            metric(value: String(format: "%.0f", recorder.courseDeg), unit: "°")
            if recorder.heartRate > 0 {
                Divider()
                metric(value: "\(recorder.heartRate)", unit: "bpm")
            }
        }
        .frame(maxWidth: .infinity)
    }

    private func metric(value: String, unit: String) -> some View {
        VStack(spacing: 0) {
            Text(value).font(.system(.title, design: .rounded).monospacedDigit())
            Text(unit).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder private var controls: some View {
        switch recorder.state {
        case .idle, .stopped:
            Button {
                recorder.state == .stopped ? recorder.reset() : recorder.start()
            } label: {
                Label(recorder.state == .stopped ? "Nuova" : "Avvia",
                      systemImage: "record.circle").frame(maxWidth: .infinity)
            }
            .tint(.green)
            .disabled(!context.deviceClaimed)
            if !context.deviceClaimed {
                Text("Abbina l'orologio dall'app iPhone")
                    .font(.caption2).foregroundStyle(.secondary).multilineTextAlignment(.center)
            }
        case .recording:
            HStack {
                Button { recorder.pause() } label: {
                    Image(systemName: "pause.fill").frame(maxWidth: .infinity)
                }.tint(.yellow)
                Button { recorder.stop() } label: {
                    Image(systemName: "stop.fill").frame(maxWidth: .infinity)
                }.tint(.red)
            }
        case .paused:
            HStack {
                Button { recorder.resume() } label: {
                    Image(systemName: "play.fill").frame(maxWidth: .infinity)
                }.tint(.green)
                Button { recorder.stop() } label: {
                    Image(systemName: "stop.fill").frame(maxWidth: .infinity)
                }.tint(.red)
            }
        }
    }
}
