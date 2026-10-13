import SwiftUI

/// DESIGN.md's tokens as the watch uses them. The ground is the system's
/// true black, not Night Harbour: on an OLED wrist in sunlight black is both
/// the contrast ceiling and the cheapest pixel. Chart Blue stays the one
/// "act here" colour; amber, green and red keep their status meanings.
enum Palette {
    static let signal = Color(red: 0x2f / 255, green: 0x9b / 255, blue: 0xe0 / 255)     // chart-blue
    static let signalInk = Color(red: 0x04 / 255, green: 0x26 / 255, blue: 0x3c / 255)  // chart-blue-ink
    static let amber = Color(red: 0xe0 / 255, green: 0xb2 / 255, blue: 0x4a / 255)      // signal-amber
    static let green = Color(red: 0x3f / 255, green: 0xbf / 255, blue: 0x7f / 255)      // starboard-green
    static let red = Color(red: 0xe0 / 255, green: 0x5a / 255, blue: 0x5a / 255)        // distress-red
    static let mist = Color(red: 0x9f / 255, green: 0xb6 / 255, blue: 0xc9 / 255)       // sea-mist
}

extension Font {
    /// Instrument figures: heavy, rounded, tabular, so digits never jitter.
    /// Sized to the largest that fits and allowed to shrink, which is what
    /// keeps one layout readable from the 40 mm SE to the 49 mm Ultra.
    static func readout(_ size: CGFloat) -> Font {
        .system(size: size, weight: .bold, design: .rounded).monospacedDigit()
    }
}

/// Instrument cell label: small caps-height text in Sea Mist.
struct ReadoutLabel: View {
    let text: LocalizedStringKey
    var body: some View {
        Text(text)
            .font(.system(.caption2, design: .rounded).weight(.semibold))
            .foregroundStyle(Palette.mist)
            .textCase(.uppercase)
            .lineLimit(1)
    }
}

enum Format {
    /// m:ss under an hour, h:mm:ss over it.
    static func clock(_ interval: TimeInterval) -> String {
        let total = max(0, Int(interval))
        let h = total / 3600, m = total / 60 % 60, s = total % 60
        return h > 0 ? String(format: "%d:%02d:%02d", h, m, s) : String(format: "%d:%02d", m, s)
    }

    static func degrees(_ value: Double) -> String { String(format: "%03.0f°", NavMath.wrap360(value.rounded())) }

    static func knots(_ value: Double) -> String { String(format: "%.1f", value) }

    /// "12′" / "3 h" — how old a wind reading is, at a glance.
    static func age(since date: Date, now: Date = Date()) -> String {
        let minutes = max(0, Int(now.timeIntervalSince(date) / 60))
        return minutes < 90 ? "\(minutes)′" : "\(minutes / 60) h"
    }
}

/// The filled primary button every key action uses: full width, at least
/// 48 pt tall so a wet finger finds it.
struct PrimaryButtonStyle: ButtonStyle {
    var tint: Color = Palette.signal
    var ink: Color = Palette.signalInk

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(.headline, design: .rounded).weight(.bold))
            .foregroundStyle(ink)
            .frame(maxWidth: .infinity, minHeight: 48)
            .background(tint.opacity(configuration.isPressed ? 0.7 : 1), in: Capsule())
            .contentShape(Capsule())
    }
}
