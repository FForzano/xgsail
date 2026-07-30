import SwiftUI

/// Glanceable nav display + recording controls (docs/device-protocol.md §9):
/// clock, speed-over-ground (kn) and course-over-ground (°) during recording,
/// and start / pause / stop. Boat + mode come from the phone
/// (`WatchContextStore`); recording is blocked until the watch is claimed.
struct ContentView: View {
    @EnvironmentObject private var recorder: SessionRecorder
    @ObservedObject private var context = WatchContextStore.shared

    var body: some View {
        VStack(spacing: 8) {
            clock
            if recorder.state == .recording || recorder.state == .paused {
                readouts
            } else {
                header
            }
            controls
        }
        .padding(.horizontal, 6)
    }

    private var clock: some View {
        TimelineView(.periodic(from: .now, by: 1)) { ctx in
            Text(ctx.date, format: .dateTime.hour().minute().second())
                .font(.system(.title3, design: .rounded).monospacedDigit())
                .foregroundStyle(.secondary)
        }
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
