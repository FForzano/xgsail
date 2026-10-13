import Foundation
import CoreLocation

/// Pure sailing geometry for the on-wrist instruments — no state, no UI.
/// Angles are degrees, true bearings (0 = north, clockwise); TWD is the
/// direction the wind blows *from*, as everywhere else in XGSail.
enum NavMath {
    static func wrap360(_ deg: Double) -> Double {
        let r = deg.truncatingRemainder(dividingBy: 360)
        return r < 0 ? r + 360 : r
    }

    /// Smallest signed difference `a − b`, in −180..<180.
    static func signedDelta(_ a: Double, _ b: Double) -> Double {
        let d = wrap360(a - b)
        return d >= 180 ? d - 360 : d
    }

    /// Moves `from` towards `to` by `weight` (0…1) along the shorter arc.
    static func blend(_ from: Double, _ to: Double, weight: Double) -> Double {
        wrap360(from + signedDelta(to, from) * weight)
    }

    /// Circular mean and steadiness (mean resultant length: 1 = every heading
    /// identical, 0 = no common direction). Nil for an empty input.
    static func circularMean(_ degs: [Double]) -> (mean: Double, steadiness: Double)? {
        guard !degs.isEmpty else { return nil }
        let x = degs.reduce(0) { $0 + cos($1 * .pi / 180) } / Double(degs.count)
        let y = degs.reduce(0) { $0 + sin($1 * .pi / 180) } / Double(degs.count)
        return (wrap360(atan2(y, x) * 180 / .pi), (x * x + y * y).squareRoot())
    }

    /// True wind angle, −180..<180: positive = wind over the starboard side
    /// (starboard tack), negative = port.
    static func twa(twd: Double, cog: Double) -> Double { signedDelta(twd, cog) }

    /// Velocity made good towards (positive) or away from (negative) the wind.
    static func vmg(sog: Double, twa: Double) -> Double { sog * cos(twa * .pi / 180) }

    /// The wind direction a tack or gybe implies. The bisector of the two
    /// steady headings points upwind after a tack and downwind after a gybe,
    /// and nothing in a COG trace says which — so it takes a prior estimate,
    /// keeps the reading nearer to it, and rejects one too far off to be the
    /// same wind. Nil when the turn isn't maneuver-sized.
    static func maneuverTWD(before: Double, after: Double, prior: Double) -> Double? {
        let turn = signedDelta(after, before)
        guard (60...140).contains(abs(turn)) else { return nil }
        let bisector = wrap360(before + turn / 2)
        let reading = abs(signedDelta(bisector, prior)) <= 90 ? bisector : wrap360(bisector + 180)
        return abs(signedDelta(reading, prior)) <= 35 ? reading : nil
    }

    /// Re-aligns a countdown on a committee minute signal: the gun is a whole
    /// number of minutes after the tap, whatever the wall clock reads, so the
    /// *remaining* time is rounded, not the target instant. A tap within 30 s
    /// of the gun means the gun is now.
    static func syncedGun(gun: Date, now: Date) -> Date {
        now.addingTimeInterval(syncedMinutes(gun: gun, now: now) * 60)
    }

    static func syncedMinutes(gun: Date, now: Date) -> Double {
        max(0, (gun.timeIntervalSince(now) / 60).rounded())
    }

    /// Perpendicular distance (m) from `point` to the start line through
    /// `boatEnd` and `pinEnd`, and — when the wind is known — whether `point`
    /// is on the course side of it. Nil when the two ends are too close
    /// together to define a line.
    static func startLine(boatEnd: CLLocationCoordinate2D, pinEnd: CLLocationCoordinate2D,
                          point: CLLocationCoordinate2D, twd: Double?) -> (metres: Double, over: Bool?)? {
        // Equirectangular metres around the boat end: plenty for a start line.
        let lat0 = boatEnd.latitude * .pi / 180
        func xy(_ c: CLLocationCoordinate2D) -> (x: Double, y: Double) {
            ((c.longitude - boatEnd.longitude) * .pi / 180 * cos(lat0) * 6_371_000,
             (c.latitude - boatEnd.latitude) * .pi / 180 * 6_371_000)
        }
        let v = xy(pinEnd), w = xy(point)
        let length = (v.x * v.x + v.y * v.y).squareRoot()
        guard length >= 5 else { return nil }
        let cross = v.x * w.y - v.y * w.x
        var over: Bool?
        if let twd {
            let upwind = (x: sin(twd * .pi / 180), y: cos(twd * .pi / 180))
            over = (cross > 0) == (v.x * upwind.y - v.y * upwind.x > 0)
        }
        return (abs(cross) / length, over)
    }
}
