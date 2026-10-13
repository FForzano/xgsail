import SwiftUI

/// The underway page. Speed over ground is the one number everyone reads, so
/// it takes the screen; VMG and TWA sit under it once a wind direction is
/// known. The top line is whatever clock matters right now: the race clock
/// after a gun, else time under way.
struct InstrumentsPage: View {
    @EnvironmentObject private var recorder: SessionRecorder
    @EnvironmentObject private var race: RaceTimer
    @EnvironmentObject private var wind: WindEstimator
    let onWind: () -> Void

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { ctx in
            let twd = wind.currentTWD(at: ctx.date)
            let fix = recorder.hasFix(at: ctx.date)
            VStack(spacing: 0) {
                topLine(ctx.date, fix: fix)
                Spacer(minLength: 0)
                HStack(alignment: .firstTextBaseline, spacing: 3) {
                    Text(verbatim: fix ? Format.knots(recorder.speedKn) : "–")
                        .font(.readout(96))
                        .minimumScaleFactor(0.5)
                        .lineLimit(1)
                        .layoutPriority(1)
                    Text("kn")
                        .font(.system(.footnote, design: .rounded).weight(.bold))
                        .foregroundStyle(Palette.mist)
                }
                Spacer(minLength: 0)
                windCells(twd: fix ? twd : nil)
                windLine(twd: twd)
            }
        }
    }

    @ViewBuilder private func topLine(_ now: Date, fix: Bool) -> some View {
        HStack(spacing: 4) {
            switch race.phase {
            case .racing(let gun):
                Label(Format.clock(now.timeIntervalSince(gun)), systemImage: "flag.fill")
                    .foregroundStyle(Palette.green)
            case .finished(let gun, let finish):
                Label(Format.clock(finish.timeIntervalSince(gun)), systemImage: "flag.checkered")
                    .foregroundStyle(Palette.mist)
            default:
                Text(verbatim: Format.clock(recorder.elapsed(at: now)))
                    .foregroundStyle(Palette.mist)
            }
            Spacer(minLength: 0)
            if recorder.state == .paused {
                Text("Paused").foregroundStyle(Palette.amber)
            } else if !fix {
                Label("GPS", systemImage: "location.slash").foregroundStyle(Palette.amber)
            }
        }
        .font(.system(.footnote, design: .rounded).weight(.bold).monospacedDigit())
        .lineLimit(1)
    }

    private func windCells(twd: Double?) -> some View {
        let twa = twd.map { NavMath.twa(twd: $0, cog: recorder.courseDeg) }
        return HStack(spacing: 0) {
            ReadoutCell(label: "VMG",
                        value: twa.map { Format.knots(abs(NavMath.vmg(sog: recorder.speedKn, twa: $0))) },
                        icon: twa.map { abs($0) < 90 ? "arrow.up" : "arrow.down" })
            Rectangle().fill(Palette.mist.opacity(0.35)).frame(width: 1, height: 34)
            ReadoutCell(label: "TWA",
                        value: twa.map { String(format: "%.0f°", abs($0)) },
                        side: twa.map { $0 >= 0 })
        }
    }

    /// COG, and the wind it is all measured against — tap to set or check it.
    private func windLine(twd: Double?) -> some View {
        Button(action: onWind) {
            HStack(spacing: 4) {
                Text(verbatim: "COG \(Format.degrees(recorder.courseDeg))")
                    .foregroundStyle(Palette.mist)
                Spacer(minLength: 2)
                if let twd, let source = wind.estimate?.source {
                    Image(systemName: source.icon)
                    Text(verbatim: "TWD \(Format.degrees(twd))")
                } else {
                    Label("Set wind", systemImage: "location.north.line.fill")
                }
            }
            .font(.system(.caption2, design: .rounded).weight(.bold).monospacedDigit())
            .foregroundStyle(Palette.signal)
            .frame(minHeight: 30)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

/// One secondary instrument: label over a tabular value, "–" when unknown.
struct ReadoutCell: View {
    let label: LocalizedStringKey
    let value: String?
    var icon: String?
    /// Starboard (true) / port (false) tack for an angle to the wind.
    var side: Bool?
    var size: CGFloat = 32

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 3) {
                ReadoutLabel(text: label)
                if let side {
                    // Colour follows the nav lights, but the word carries it.
                    Text(side ? "stbd" : "port")
                        .font(.system(.caption2, design: .rounded).weight(.heavy))
                        .foregroundStyle(side ? Palette.green : Palette.red)
                        .textCase(.uppercase)
                }
            }
            HStack(alignment: .firstTextBaseline, spacing: 2) {
                if let icon { Image(systemName: icon).font(.system(size: size * 0.45, weight: .heavy)) }
                Text(verbatim: value ?? "–")
                    .font(.readout(size))
                    .minimumScaleFactor(0.6)
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity)
    }
}

extension WindEstimator.Source {
    var icon: String {
        switch self {
        case .phone: "iphone"
        case .manual: "pencil"
        case .tacks: "arrow.left.arrow.right"
        }
    }
}

// MARK: - Countdown

/// The start sequence: one huge clock, one huge Sync, and the line once both
/// ends are pinged. The timeline is anchored on the gun, so the digits turn
/// over on the same instants the haptics fire.
struct CountdownPage: View {
    @EnvironmentObject private var recorder: SessionRecorder
    @EnvironmentObject private var race: RaceTimer
    @EnvironmentObject private var wind: WindEstimator
    @Environment(\.isLuminanceReduced) private var dimmed
    let gun: Date

    var body: some View {
        TimelineView(.periodic(from: gun.addingTimeInterval(-3600), by: 1)) { ctx in
            let left = gun.timeIntervalSince(ctx.date)
            VStack(spacing: 4) {
                Text(verbatim: Format.clock((left - 0.05).rounded(.up)))
                    .font(.readout(96))
                    .minimumScaleFactor(0.5)
                    .lineLimit(1)
                    .layoutPriority(1)
                    .foregroundStyle(left <= 60 ? Palette.amber : .white)
                if !dimmed {
                    syncButton(minutes: Int(NavMath.syncedMinutes(gun: gun, now: ctx.date)))
                }
                lineCells(left: left)
            }
        }
    }

    private func syncButton(minutes: Int) -> some View {
        Button { race.sync() } label: {
            if minutes == 0 {
                Label("Gun now", systemImage: "flag.fill")
            } else {
                // Says what the tap will snap to, so a late press is visible.
                Label { Text(verbatim: "Sync \(minutes):00") } icon: { Image(systemName: "arrow.triangle.2.circlepath") }
            }
        }
        .buttonStyle(PrimaryButtonStyle())
    }

    /// SOG always; distance to the line and time to burn once both ends are
    /// in. Watch GPS is good to a few metres and the watch is on the sailor,
    /// not the bow, so this is a guide for the approach, not an OCS call.
    @ViewBuilder private func lineCells(left: TimeInterval) -> some View {
        let sog = recorder.speedKn
        if let boat = race.boatEnd, let pin = race.pinEnd, let fix = recorder.lastFix,
           let line = NavMath.startLine(boatEnd: boat, pinEnd: pin, point: fix.coordinate,
                                        twd: wind.currentTWD()) {
            HStack(spacing: 0) {
                ReadoutCell(label: "SOG", value: Format.knots(sog), size: 24)
                ReadoutCell(label: line.over == true ? "Over" : "Line", value: "\(Int(line.metres))m", size: 24)
                    .foregroundStyle(line.over == true ? Palette.red : .white)
                ReadoutCell(label: "Burn", value: burn(left: left, metres: line.metres, sogKn: sog), size: 24)
            }
        } else {
            HStack(spacing: 0) {
                ReadoutCell(label: "SOG", value: Format.knots(sog))
                ReadoutCell(label: "COG", value: Format.degrees(recorder.courseDeg))
            }
        }
    }

    /// Seconds to spare if you sailed straight at the line now; negative = late.
    private func burn(left: TimeInterval, metres: Double, sogKn: Double) -> String? {
        guard sogKn > 0.5 else { return nil }
        let spare = Int((left - metres / (sogKn * 0.514444)).rounded())
        let magnitude = abs(spare) >= 60 ? Format.clock(TimeInterval(abs(spare))) : "\(abs(spare))s"
        return (spare >= 0 ? "+" : "−") + magnitude
    }
}
