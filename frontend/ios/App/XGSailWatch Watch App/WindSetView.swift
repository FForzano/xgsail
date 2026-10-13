import SwiftUI

/// Set the true wind direction by hand: the phone-free way to get TWA and VMG.
/// The Crown turns it in 5° steps; "From heading" seeds it from the current
/// course for sailors who point head to wind, or sail close-hauled and add
/// the angle themselves. Tacks keep refining whatever is set here.
struct WindSetView: View {
    @EnvironmentObject private var wind: WindEstimator
    @EnvironmentObject private var recorder: SessionRecorder
    @Environment(\.dismiss) private var dismiss
    @State private var twd: Double = 0

    var body: some View {
        ScrollView {
            VStack(spacing: 6) {
                ReadoutLabel(text: "Wind from")
                Text(verbatim: Format.degrees(twd))
                    .font(.readout(52))
                    .minimumScaleFactor(0.6)
                    .focusable()
                    .digitalCrownRotation($twd, from: 0, through: 355, by: 5, sensitivity: .medium,
                                          isContinuous: true, isHapticFeedbackEnabled: true)
                Text(verbatim: Self.cardinal(twd))
                    .font(.system(.footnote, design: .rounded).weight(.bold))
                    .foregroundStyle(Palette.mist)
                Button("Set") {
                    wind.setManual(twd)
                    dismiss()
                }
                .buttonStyle(PrimaryButtonStyle())
                Button("From heading") { twd = (recorder.courseDeg / 5).rounded() * 5 }
                    .tint(Palette.signal)
                currentSource
            }
        }
        .onAppear {
            let start = wind.currentTWD() ?? recorder.courseDeg
            twd = NavMath.wrap360((start / 5).rounded() * 5)
        }
    }

    @ViewBuilder private var currentSource: some View {
        if let e = wind.estimate, wind.currentTWD() != nil {
            Group {
                switch e.source {
                case .phone: Text("Now: iPhone, \(Format.age(since: e.at)) ago")
                case .manual: Text("Now: set by hand, \(Format.age(since: e.at)) ago")
                case .tacks: Text("Now: refined by \(e.tacks) maneuvers")
                }
            }
            .font(.caption2)
            .foregroundStyle(Palette.mist)
            .multilineTextAlignment(.center)
        }
    }

    private static func cardinal(_ deg: Double) -> String {
        let points = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        return points[Int((NavMath.wrap360(deg) + 22.5) / 45) % 8]
    }
}
