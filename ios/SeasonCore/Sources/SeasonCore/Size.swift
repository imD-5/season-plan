import Foundation

/// Task sizes: the same rules and shorthand as the server (season/domain/model.py).
public enum Size {
    public static let maxSessions = 12
    public static let maxHours = 8.0

    public static func valid(sessions: Int, hours: Double) -> Bool {
        (1...maxSessions).contains(sessions) && hours >= 0 && hours <= maxHours && (hours * 2).rounded() == hours * 2
    }

    /// "Read papers 3x2h" -> ("Read papers", 3, 2.0); "Call Kenji 30m" -> ("Call Kenji", nil, 0.5).
    public static func parse(_ text: String) -> (text: String, sessions: Int?, hours: Double?) {
        let pattern = #"\s+(?:(\d{1,2})\s*[x×*]\s*)?(?:(\d+(?:\.\d+)?)\s*h|(\d{1,3})\s*m(?:in)?)?\s*$"#
        guard let re = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]),
              let m = re.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)) else {
            return (text, nil, nil)
        }
        func group(_ i: Int) -> String? {
            let r = m.range(at: i)
            guard r.location != NSNotFound, let range = Range(r, in: text) else { return nil }
            return String(text[range])
        }
        let n = group(1), h = group(2), mins = group(3)
        if n == nil && h == nil && mins == nil { return (text, nil, nil) }
        let rest = String(text[..<Range(m.range, in: text)!.lowerBound]).trimmingCharacters(in: .whitespaces)
        if rest.isEmpty { return (text, nil, nil) }
        var hours: Double? = h.flatMap(Double.init) ?? mins.flatMap(Double.init).map { $0 / 60 }
        if let x = hours { hours = max(0.5, (x * 2).rounded() / 2) }
        return (rest, n.flatMap(Int.init), hours)
    }

    public static func label(sessions: Int, hours: Double) -> String {
        func h(_ x: Double) -> String { x == 0.5 ? "30m" : (x == x.rounded() ? "\(Int(x))h" : "\(x)h") }
        if hours == 0 { return sessions == 1 ? "+ time" : "\(sessions) boxes" }
        return sessions == 1 ? h(hours) : "\(sessions) × \(h(hours))"
    }
}
