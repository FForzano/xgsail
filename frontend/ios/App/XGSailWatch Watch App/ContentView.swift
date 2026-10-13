import SwiftUI

/// Root of the watch app. Recording and racing are one flow, not two modes:
/// a recording is the outing, and a race is a start sequence run inside it.
/// So "Start sequence" from idle starts the recording *and* the countdown in
/// one tap (the pre-start belongs on the track), and a finished race drops
/// back to plain instruments with the recording still running, ready for the
/// next start.
struct ContentView: View {
    @EnvironmentObject private var recorder: SessionRecorder

    var body: some View {
        switch recorder.state {
        case .idle: IdleView()
        case .recording, .paused: SessionView()
        case .stopped: SummaryView()
        }
    }
}

// MARK: - Idle

struct IdleView: View {
    @EnvironmentObject private var wind: WindEstimator
    @ObservedObject private var context = WatchContextStore.shared
    @State private var showStartSetup = false
    @State private var pending = 0

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    boatLine
                    Button { showStartSetup = true } label: {
                        Label("Start sequence", systemImage: "flag.checkered")
                    }
                    .buttonStyle(PrimaryButtonStyle())

                    Button { Sailing.shared.startOuting() } label: {
                        Label("Record outing", systemImage: "record.circle")
                            .frame(maxWidth: .infinity, minHeight: 40)
                    }
                    .tint(Palette.signal)

                    statusLines
                }
            }
            .navigationTitle("XGSail")
        }
        .sheet(isPresented: $showStartSetup) {
            StartSetupView { minutes in
                showStartSetup = false
                Sailing.shared.startSequence(minutes: minutes)
            }
        }
        .onAppear { pending = WatchConnectivityClient.shared.pendingSessionCount() }
    }

    private var boatLine: some View {
        VStack(alignment: .leading, spacing: 0) {
            Label {
                Group {
                    if let name = context.boatName { Text(verbatim: name) } else { Text("No boat from iPhone") }
                }
                .lineLimit(context.boatName == nil ? 2 : 1)
            } icon: {
                Image(systemName: "sailboat.fill")
            }
            .font(.system(.footnote, design: .rounded).weight(.semibold))
            if context.mode == "personal" {
                Text("Personal data only")
                    .font(.caption2)
                    .foregroundStyle(Palette.mist)
            }
        }
    }

    /// Everything the watch can't do alone, said plainly: none of it blocks
    /// going sailing.
    @ViewBuilder private var statusLines: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let estimate = wind.estimate, wind.currentTWD() != nil {
                statusLine("wind", "Wind \(Format.degrees(estimate.twdDeg)) · \(Format.age(since: estimate.at))")
            } else {
                statusLine("wind", "No wind yet. Set it on the water.")
            }
            if pending > 0 {
                statusLine("arrow.up.circle", "\(pending) recordings waiting for iPhone")
            }
            if !context.deviceClaimed {
                statusLine("applewatch.slash",
                           "Not paired in XGSail on iPhone. Recordings wait on the watch until you pair it.")
            }
        }
        .padding(.top, 4)
    }

    private func statusLine(_ icon: String, _ text: LocalizedStringKey) -> some View {
        Label { Text(text) } icon: { Image(systemName: icon) }
            .font(.caption2)
            .foregroundStyle(Palette.mist)
            .fixedSize(horizontal: false, vertical: true)
    }
}

// MARK: - Start setup

/// Sequence length on the Digital Crown (works with gloves, and through
/// spray that makes the touchscreen guess) or the − / + buttons.
struct StartSetupView: View {
    @EnvironmentObject private var race: RaceTimer
    let onGo: (Int) -> Void
    @State private var crown: Double = 5

    var body: some View {
        VStack(spacing: 6) {
            ReadoutLabel(text: "Start in")
            HStack(spacing: 4) {
                step("minus", by: -1)
                Text(verbatim: "\(race.sequenceMinutes):00")
                    .font(.readout(54))
                    .minimumScaleFactor(0.6)
                    .lineLimit(1)
                    .frame(maxWidth: .infinity)
                    .focusable()
                    .digitalCrownRotation($crown, from: Double(RaceTimer.minuteRange.lowerBound),
                                          through: Double(RaceTimer.minuteRange.upperBound),
                                          by: 1, sensitivity: .low, isContinuous: false,
                                          isHapticFeedbackEnabled: true)
                step("plus", by: 1)
            }
            Button { onGo(race.sequenceMinutes) } label: {
                Label("Go", systemImage: "flag.fill")
            }
            .buttonStyle(PrimaryButtonStyle())
            Text("Tap Go on the warning signal.")
                .font(.caption2)
                .foregroundStyle(Palette.mist)
                .multilineTextAlignment(.center)
        }
        .onAppear { crown = Double(race.sequenceMinutes) }
        .onChange(of: crown) { _, value in race.sequenceMinutes = Int(value.rounded()) }
    }

    private func step(_ icon: String, by delta: Int) -> some View {
        Button {
            let next = race.sequenceMinutes + delta
            guard RaceTimer.minuteRange.contains(next) else { return }
            race.sequenceMinutes = next
            crown = Double(next)
        } label: {
            Image(systemName: icon).font(.title3.weight(.bold)).frame(width: 40, height: 48)
        }
        .buttonStyle(.plain)
        .foregroundStyle(Palette.signal)
    }
}

// MARK: - Summary

struct SummaryView: View {
    @EnvironmentObject private var recorder: SessionRecorder

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                Label("Outing saved", systemImage: "checkmark.circle.fill")
                    .font(.system(.headline, design: .rounded))
                    .foregroundStyle(Palette.green)
                if let s = recorder.summary {
                    row("Time", Format.clock(s.duration))
                    row("Distance", String(format: "%.2f nm", s.distanceNm))
                    row("Top speed", "\(Format.knots(s.maxSogKn)) kn")
                }
                Text("It goes to your iPhone when the two are next together, then on to XGSail.")
                    .font(.caption2)
                    .foregroundStyle(Palette.mist)
                    .fixedSize(horizontal: false, vertical: true)
                Button("Done") { recorder.reset() }
                    .buttonStyle(PrimaryButtonStyle())
            }
        }
    }

    private func row(_ label: LocalizedStringKey, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline) {
            ReadoutLabel(text: label)
            Spacer()
            Text(verbatim: value).font(.readout(22))
        }
    }
}
