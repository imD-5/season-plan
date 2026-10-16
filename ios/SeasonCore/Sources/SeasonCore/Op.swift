import Foundation

/// One change made on the phone, queued until the Mac is reachable.
/// Encodes to exactly what POST /api/sync expects (see season/interfaces/http/sync_json.py).
public struct Op: Codable, Equatable, Sendable, Identifiable {
    public enum Kind: String, Codable, Sendable {
        case mark, unmark, restore, note, add, remove, resize, category
        case newCategory = "new_category"
        case pages, skip
    }

    public var id: String
    public var kind: Kind
    public var task: TaskRef?
    public var slot: Int?
    public var d: String?
    public var problem: Int?
    public var note: String?
    public var clientKey: String?
    public var week: String?
    public var text: String?
    public var sessions: Int?
    public var hours: Double?
    public var category: String?
    public var label: String?
    public var description: String?
    public var pages: Int?

    public init(_ kind: Kind, id: String = Op.newID()) { self.id = id; self.kind = kind }

    public static func newID() -> String { UUID().uuidString.lowercased() }

    // MARK: constructors, one per board action

    public static func mark(_ t: TaskRef, _ slot: Int, on day: String) -> Op {
        var o = Op(.mark); o.task = t; o.slot = slot; o.d = day; return o
    }
    public static func unmark(_ t: TaskRef, _ slot: Int) -> Op {
        var o = Op(.unmark); o.task = t; o.slot = slot; return o
    }
    public static func restore(_ t: TaskRef, _ slot: Int, _ s: Slot) -> Op {
        var o = Op(.restore); o.task = t; o.slot = slot; o.d = s.d; o.problem = s.problem; o.note = s.note; return o
    }
    public static func note(_ t: TaskRef, _ slot: Int, _ note: String?) -> Op {
        var o = Op(.note); o.task = t; o.slot = slot; o.note = note; return o
    }
    public static func add(week: String, text: String, sessions: Int?, hours: Double?,
                           clientKey: String = UUID().uuidString.lowercased()) -> Op {
        var o = Op(.add); o.week = week; o.text = text; o.sessions = sessions; o.hours = hours; o.clientKey = clientKey
        return o
    }
    public static func remove(_ t: TaskRef) -> Op { var o = Op(.remove); o.task = t; return o }
    public static func resize(_ t: TaskRef, sessions: Int, hours: Double) -> Op {
        var o = Op(.resize); o.task = t; o.sessions = sessions; o.hours = hours; return o
    }
    public static func assign(_ t: TaskRef, _ category: String) -> Op {
        var o = Op(.category); o.task = t; o.category = category; return o
    }
    public static func newCategory(label: String, description: String, task: TaskRef?) -> Op {
        var o = Op(.newCategory); o.label = label; o.description = description; o.task = task; return o
    }
    public static func pages(_ n: Int?) -> Op { var o = Op(.pages); o.pages = n; return o }
    public static func skip() -> Op { Op(.skip) }
}
