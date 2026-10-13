import SwiftUI
import WatchKit

/// A recording in progress, paged like the system Workout app: controls one
/// swipe to the left, the main page in the centre. The main page is the
/// countdown while a sequence runs and the instruments the rest of the time.
struct SessionView: View {
    @EnvironmentObject private var race: RaceTimer
    @State private var page = 1
    @State private var sheet: Sheet?

    enum Sheet: Identifiable {
        case startSetup, wind
        var id: Self { self }
    }

    var body: some View {
        TabView(selection: $page) {
            ControlsPage(present: { sheet = $0 }, done: { page = 1 })
                .tag(0)
            Group {
                if case .countdown(let gun) = race.phase {
                    CountdownPage(gun: gun)
                } else {
                    InstrumentsPage(onWind: { sheet = .wind })
                }
            }
            .tag(1)
        }
        .tabViewStyle(.page)
        .sheet(item: $sheet) { which in
            switch which {
            case .startSetup:
                StartSetupView { minutes in
                    sheet = nil
                    page = 1
                    Sailing.shared.startSequence(minutes: minutes)
                }
            case .wind:
                WindSetView()
            }
        }
    }
}

// MARK: - Controls

struct ControlsPage: View {
    @EnvironmentObject private var recorder: SessionRecorder
    @EnvironmentObject private var race: RaceTimer
    let present: (SessionView.Sheet) -> Void
    let done: () -> Void
    @State private var confirmEnd = false

    var body: some View {
        ScrollView {
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                raceControls
                ControlButton(icon: "location.north.line.fill", label: "Wind", tint: Palette.signal) {
                    present(.wind)
                }
                ControlButton(icon: "drop.fill", label: "Water Lock", tint: Palette.signal) {
                    WKInterfaceDevice.current().enableWaterLock()
                    done()
                }
                if recorder.state == .paused {
                    ControlButton(icon: "play.fill", label: "Resume", tint: Palette.green) {
                        recorder.resume()
                        done()
                    }
                } else {
                    ControlButton(icon: "pause.fill", label: "Pause", tint: Palette.amber) {
                        recorder.pause()
                        done()
                    }
                }
                ControlButton(icon: "xmark", label: "End", tint: Palette.red) { confirmEnd = true }
            }
        }
        .confirmationDialog("End this recording?", isPresented: $confirmEnd) {
            Button("End recording", role: .destructive) { recorder.stop() }
        }
    }

    /// What a race needs next: a start, the line ends and a way out of a
    /// recall, or the finish.
    @ViewBuilder private var raceControls: some View {
        switch race.phase {
        case .off, .finished:
            ControlButton(icon: "flag.checkered", label: "Start", tint: Palette.signal) {
                present(.startSetup)
            }
        case .countdown:
            ControlButton(icon: "ferry.fill", label: "Boat end", tint: Palette.signal,
                          done: race.boatEnd != nil, disabled: recorder.lastFix == nil) {
                if let fix = recorder.lastFix { race.ping(boat: fix.coordinate) }
            }
            ControlButton(icon: "mappin", label: "Pin end", tint: Palette.signal,
                          done: race.pinEnd != nil, disabled: recorder.lastFix == nil) {
                if let fix = recorder.lastFix { race.ping(pin: fix.coordinate) }
            }
            ControlButton(icon: "arrow.uturn.backward", label: "Cancel start", tint: Palette.mist) {
                race.cancel()
                done()
            }
        case .racing:
            ControlButton(icon: "flag.checkered", label: "Finish", tint: Palette.green) {
                race.finish()
                done()
            }
        }
    }
}

/// Round control in the Workout app's shape: a tinted disc, not a solid fill
/// (the Tint, Not Fill rule), with its name underneath.
struct ControlButton: View {
    let icon: String
    let label: LocalizedStringKey
    let tint: Color
    var done = false
    var disabled = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 4) {
                Image(systemName: done ? "checkmark" : icon)
                    .font(.system(size: 22, weight: .bold))
                    .foregroundStyle(tint)
                    .frame(maxWidth: .infinity, minHeight: 52)
                    .background(tint.opacity(done ? 0.4 : 0.22), in: Capsule())
                Text(label)
                    .font(.system(.caption2, design: .rounded).weight(.semibold))
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
                    .minimumScaleFactor(0.8)
            }
        }
        .buttonStyle(.plain)
        .disabled(disabled)
        .opacity(disabled ? 0.4 : 1)
    }
}
