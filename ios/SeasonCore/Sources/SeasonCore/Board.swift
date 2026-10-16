import Foundation

// The board as the server sends it (GET/POST /api/…). Same shape is stored on the phone.

public struct Problem: Codable, Equatable, Sendable {
    public var number: Int
    public var title: String
    public init(number: Int, title: String) { self.number = number; self.title = title }
}

public struct Category: Codable, Equatable, Sendable, Identifiable {
    public var key: String
    public var label: String
    public var description: String
    public var builtin: Bool
    public var id: String { key }
    public init(key: String, label: String, description: String, builtin: Bool) {
        self.key = key; self.label = label; self.description = description; self.builtin = builtin
    }
}

public struct Event: Codable, Equatable, Sendable {
    public var t: String
    public var k: String
}

public struct Slot: Codable, Equatable, Sendable {
    public var d: String            // yyyy-MM-dd, the day it was done
    public var problem: Int?
    public var note: String?
    public init(d: String, problem: Int? = nil, note: String? = nil) { self.d = d; self.problem = problem; self.note = note }
}

public struct BoardTask: Codable, Equatable, Sendable, Identifiable {
    public var id: Int              // server id; negative for a task added on the phone and not yet synced
    public var key: String
    public var text: String
    public var category: String
    public var assignedBy: String
    public var confidence: Double?
    public var sessions: Int
    public var each: Double
    public var userAdded: Bool
    public var problemList: Bool
    public var minSessions: Int?
    public var slots: [Slot?]

    /// How the phone names this task in a sync operation.
    public var ref: TaskRef {
        if id < 0, key.hasPrefix(Board.phoneKeyPrefix) { return .client(String(key.dropFirst(Board.phoneKeyPrefix.count))) }
        return .id(id)
    }
    public var isDone: Bool { sessions > 0 && slots.allSatisfy { $0 != nil } }
    public var checkedUpTo: Int { (slots.lastIndex { $0 != nil } ?? -1) + 1 }
}

public struct Week: Codable, Equatable, Sendable, Identifiable {
    public var start: String
    public var end: String
    public var label: String
    public var glance: String
    public var hours: Double
    public var tasks: [BoardTask]
    public var id: String { start }
}

public struct Board: Codable, Equatable, Sendable {
    public static let phoneKeyPrefix = "phone-"

    public var today: String
    public var pages: Int?
    public var pagesTarget: Int
    public var problem: Problem?
    public var upcoming: [Problem]?
    public var categories: [Category]
    public var events: [String: [Event]]
    public var weeks: [Week]

    public func category(_ key: String) -> Category? { categories.first { $0.key == key } }

    public func weekIndex(containing day: String) -> Int {
        if let i = weeks.firstIndex(where: { $0.start <= day && day <= $0.end }) { return i }
        guard let first = weeks.first else { return 0 }
        return day < first.start ? 0 : weeks.count - 1
    }

    /// Where a task lives, by server id or phone key.
    public func locate(_ ref: TaskRef) -> (week: Int, task: Int)? {
        for (wi, w) in weeks.enumerated() {
            for (ti, t) in w.tasks.enumerated() {
                switch ref {
                case .id(let id) where t.id == id: return (wi, ti)
                case .client(let key) where t.key == Board.phoneKeyPrefix + key: return (wi, ti)
                default: continue
                }
            }
        }
        return nil
    }

    /// Everything done on a day, for the day strip: "Thesis", "LC 117", "Read papers ×2".
    public func done(on day: String) -> [(label: String, notes: [String])] {
        var order: [String] = [], counts: [String: Int] = [:], notes: [String: [String]] = [:]
        for w in weeks {
            for t in w.tasks {
                for case let s? in t.slots where s.d == day {
                    let label = t.problemList ? "LC \(s.problem.map(String.init) ?? "")"
                        : (t.userAdded ? t.text : (category(t.category)?.label ?? t.category).capitalized)
                    if counts[label] == nil { order.append(label) }
                    counts[label, default: 0] += 1
                    if let n = s.note { notes[label, default: []].append(n) }
                }
            }
        }
        return order.map { (counts[$0]! > 1 ? "\($0) ×\(counts[$0]!)" : $0, notes[$0] ?? []) }
    }

    // MARK: JSON

    public static func decoder() -> JSONDecoder {
        let d = JSONDecoder(); d.keyDecodingStrategy = .convertFromSnakeCase; return d
    }
    public static func encoder() -> JSONEncoder {
        let e = JSONEncoder(); e.keyEncodingStrategy = .convertToSnakeCase; e.outputFormatting = [.sortedKeys]; return e
    }
}

public enum TaskRef: Codable, Equatable, Hashable, Sendable {
    case id(Int)
    case client(String)

    public init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if let n = try? c.decode(Int.self) { self = .id(n) } else { self = .client(try c.decode(String.self)) }
    }
    public func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .id(let n): try c.encode(n)
        case .client(let s): try c.encode(s)
        }
    }
}

public enum Day {
    /// Today's date on this phone, yyyy-MM-dd in the phone's time zone.
    public static func string(_ date: Date = Date(), calendar: Calendar = .current) -> String {
        let c = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", c.year!, c.month!, c.day!)
    }

    public static func date(_ s: String) -> Date? {
        let p = s.split(separator: "-").compactMap { Int($0) }
        guard p.count == 3 else { return nil }
        return Calendar.current.date(from: DateComponents(year: p[0], month: p[1], day: p[2]))
    }

    public static func adding(_ days: Int, to s: String) -> String {
        guard let d = date(s), let n = Calendar.current.date(byAdding: .day, value: days, to: d) else { return s }
        return string(n)
    }

    static let weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    public static func weekday(_ s: String) -> String {
        guard let d = date(s) else { return "" }
        return weekdays[(Calendar.current.component(.weekday, from: d) + 5) % 7]
    }
}
