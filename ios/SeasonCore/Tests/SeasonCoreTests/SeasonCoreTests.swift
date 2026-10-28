import Foundation
import Testing
@testable import SeasonCore

// A small board in the server's JSON shape.
let boardJSON = """
{"today":"2026-10-14","pages":16,"pages_target":100,
 "problem":{"number":117,"title":"Next Right Pointers II"},
 "upcoming":[{"number":117,"title":"Next Right Pointers II"},{"number":114,"title":"Flatten"},{"number":112,"title":"Path sum"}],
 "categories":[{"key":"thesis","label":"thesis","description":"Thesis","builtin":true},
               {"key":"leetcode","label":"leetcode","description":"LC","builtin":true},
               {"key":"other","label":"other","description":"Else","builtin":true}],
 "events":{"2026-10-13":[{"t":"Lab","k":""}]},
 "weeks":[{"start":"2026-10-12","end":"2026-10-18","label":"12 Oct – 18 Oct","glance":"First week","hours":7.0,
   "tasks":[{"id":1,"key":"thesis","text":"Thesis","category":"thesis","assigned_by":"plan","confidence":null,
             "sessions":2,"each":2.0,"user_added":false,"problem_list":false,"min_sessions":1,
             "slots":[{"d":"2026-10-12","problem":null,"note":"intro"},null]},
            {"id":2,"key":"lc","text":"Top Interview 150","category":"leetcode","assigned_by":"plan","confidence":null,
             "sessions":3,"each":1.0,"user_added":false,"problem_list":true,"min_sessions":1,"slots":[null,null,null]}]}]}
"""

func sample() throws -> Board { try Board.decoder().decode(Board.self, from: Data(boardJSON.utf8)) }

@Suite struct BoardTests {
    @Test func decodesServerJSON() throws {
        let b = try sample()
        #expect(b.weeks[0].tasks[0].slots[0]?.note == "intro")
        #expect(b.weeks[0].tasks[1].problemList)
        #expect(b.events["2026-10-13"]?.first?.t == "Lab")
        #expect(b.weekIndex(containing: "2026-10-14") == 0)
        #expect(b.weekIndex(containing: "2027-03-01") == 0)
    }

    @Test func dayStripLabels() throws {
        let b = try sample()
        #expect(b.done(on: "2026-10-12").map(\.label) == ["Thesis"])
        #expect(b.done(on: "2026-10-12").first?.notes == ["intro"])
    }

    @Test func days() {
        #expect(Day.weekday("2026-10-12") == "Mon")
        #expect(Day.adding(6, to: "2026-10-12") == "2026-10-18")
        #expect(Day.adding(1, to: "2026-12-31") == "2027-01-01")
    }
}

@Suite struct SizeTests {
    @Test(arguments: [
        ("Read papers 3x2h", "Read papers", 3, 2.0),
        ("Read papers 3 × 1.5h", "Read papers", 3, 1.5),
        ("Draft intro 2h", "Draft intro", nil, 2.0),
        ("Call Kenji 30m", "Call Kenji", nil, 0.5),
        ("Call Kenji 20min", "Call Kenji", nil, 0.5),
        ("Exercises 4x", "Exercises", 4, nil),
        ("Ch.2 section 3", "Ch.2 section 3", nil, nil),
        ("2h", "2h", nil, nil),
    ] as [(String, String, Int?, Double?)])
    func shorthand(input: String, text: String, sessions: Int?, hours: Double?) {
        let p = Size.parse(input)
        #expect(p.text == text && p.sessions == sessions && p.hours == hours)
    }

    @Test func labels() {
        #expect(Size.label(sessions: 3, hours: 2) == "3 × 2h")
        #expect(Size.label(sessions: 1, hours: 0.5) == "30m")
        #expect(Size.label(sessions: 2, hours: 1.5) == "2 × 1.5h")
        #expect(Size.label(sessions: 1, hours: 0) == "+ time")
        #expect(!Size.valid(sessions: 13, hours: 1) && !Size.valid(sessions: 2, hours: 1.25))
    }
}

@Suite struct ApplyTests {
    @Test func markAndUnmarkLeetCodeMovesTheList() throws {
        var b = try sample()
        b.apply(.mark(.id(2), 0, on: "2026-10-14"))
        #expect(b.weeks[0].tasks[1].slots[0] == Slot(d: "2026-10-14", problem: 117))
        #expect(b.problem?.number == 114)
        b.apply(.unmark(.id(2), 0))
        #expect(b.weeks[0].tasks[1].slots[0] == nil)
        #expect(b.problem?.number == 117)
    }

    @Test func noteRestoreAndPages() throws {
        var b = try sample()
        b.apply(.note(.id(1), 0, "  revised  "))
        #expect(b.weeks[0].tasks[0].slots[0]?.note == "revised")
        let old = b.weeks[0].tasks[0].slots[0]!
        b.apply(.unmark(.id(1), 0))
        b.apply(.restore(.id(1), 0, old))
        #expect(b.weeks[0].tasks[0].slots[0] == old)
        b.apply(.pages(42)); #expect(b.pages == 42)
        b.apply(.pages(500)); #expect(b.pages == 42)
    }

    @Test func addPhoneTaskThenActOnIt() throws {
        var b = try sample()
        let add = Op.add(week: "2026-10-12", text: "Read papers 3x2h", sessions: nil, hours: nil, clientKey: "abcd1234")
        b.apply(add)
        let t = b.weeks[0].tasks.last!
        #expect(t.text == "Read papers" && t.sessions == 3 && t.each == 2 && t.id < 0 && t.ref == .client("abcd1234"))
        #expect(b.weeks[0].hours == 13)
        b.apply(.mark(t.ref, 2, on: "2026-10-15"))
        b.apply(.resize(t.ref, sessions: 2, hours: 1))            // box 3 is checked: refused
        #expect(b.weeks[0].tasks.last!.sessions == 3)
        b.apply(.resize(t.ref, sessions: 4, hours: 1.5))
        #expect(b.weeks[0].tasks.last!.sessions == 4 && b.weeks[0].tasks.last!.minSessions == 3)
        b.apply(.remove(t.ref))
        #expect(b.weeks[0].tasks.count == 2)
        b.apply(add); b.apply(add)                                    // same task twice: added once
        #expect(b.weeks[0].tasks.count == 3)
        #expect(Board.tempID(for: "abcd1234") == Board.tempID(for: "abcd1234"))
    }

    @Test func dayChangeKeepsTheNoteAndStaysInTheWeek() throws {
        var b = try sample()                                  // today 2026-10-14, week 12–18 Oct
        b.apply(.date(.id(1), 0, on: "2026-10-13"))
        #expect(b.weeks[0].tasks[0].slots[0]?.d == "2026-10-13")
        #expect(b.weeks[0].tasks[0].slots[0]?.note == "intro")
        b.apply(.date(.id(1), 1, on: "2026-10-14"))           // that box is empty: ignored
        #expect(b.weeks[0].tasks[0].slots[1] == nil)
        b.apply(.date(.id(1), 0, on: "2026-10-19"))           // next week: ignored
        b.apply(.date(.id(1), 0, on: "2026-10-15"))           // tomorrow: ignored
        #expect(b.weeks[0].tasks[0].slots[0]?.d == "2026-10-13")
    }

    @Test func categories() throws {
        var b = try sample()
        b.apply(.newCategory(label: "Side Quest!", description: "Fun", task: .id(1)))
        #expect(b.categories.map(\.key) == ["thesis", "leetcode", "side-quest", "other"])
        #expect(b.weeks[0].tasks[0].category == "side-quest" && b.weeks[0].tasks[0].assignedBy == "manual")
        b.apply(.assign(.id(1), "nope"))
        #expect(b.weeks[0].tasks[0].category == "side-quest")
    }

    @Test func opEncodesForTheServer() throws {
        let data = try Board.encoder().encode(Op.add(week: "2026-10-12", text: "x", sessions: 2, hours: nil,
                                                     clientKey: "abcd1234"))
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        #expect(json["kind"] as? String == "add" && json["client_key"] as? String == "abcd1234")
        #expect(json["hours"] == nil)
        let nc = try JSONSerialization.jsonObject(with: Board.encoder().encode(
            Op.newCategory(label: "a", description: "b", task: .client("k1234567")))) as! [String: Any]
        #expect(nc["kind"] as? String == "new_category" && nc["task"] as? String == "k1234567")
        let day = try JSONSerialization.jsonObject(with: Board.encoder().encode(
            Op.date(.id(1), 0, on: "2026-10-13"))) as! [String: Any]
        #expect(day["kind"] as? String == "date" && day["d"] as? String == "2026-10-13" && day["slot"] as? Int == 0)
    }
}

// MARK: store

actor FakeMac: SyncTransport {
    var board: Board
    var reachable = true
    var received: [[Op]] = []
    init(_ board: Board) { self.board = board }

    func setReachable(_ r: Bool) { reachable = r }

    nonisolated func sync(server: URL, ops: [Op]) async throws -> SyncResponse { try await handle(ops) }

    func handle(_ ops: [Op]) throws -> SyncResponse {
        guard reachable else { throw SyncError.unreachable("offline") }
        received.append(ops)
        var results: [OpResult] = []
        for op in ops {
            if op.task == .id(999) { results.append(OpResult(id: op.id, ok: false, error: "no task 999")); continue }
            board.apply(op)
            results.append(OpResult(id: op.id, ok: true, error: nil))
        }
        return SyncResponse(board: board, results: results)
    }
}

@MainActor @Suite struct StoreTests {
    func tempFile() -> URL { FileManager.default.temporaryDirectory.appending(path: "season-\(UUID().uuidString).json") }

    @Test func firstSyncLoadsTheBoard() async throws {
        let mac = FakeMac(try sample())
        let store = Store(file: tempFile(), transport: mac, defaultServer: "https://mac.example")
        #expect(store.board == nil)
        await store.syncNow()
        #expect(store.board?.weeks.count == 1 && store.status == .idle && store.lastSync != nil)
    }

    @Test func offlineChangesQueueAndSurviveARestart() async throws {
        let file = tempFile()
        let mac = FakeMac(try sample())
        let store = Store(file: file, transport: mac, defaultServer: "https://mac.example")
        await store.syncNow()
        await mac.setReachable(false)
        store.perform(.mark(.id(1), 1, on: "2026-10-13"))
        await store.syncNow()
        #expect(store.board?.weeks[0].tasks[0].slots[1]?.d == "2026-10-13")   // shown right away
        #expect(store.outbox.count == 1)
        if case .offline = store.status {} else { Issue.record("expected offline, got \(store.status)") }

        let reopened = Store(file: file, transport: mac, defaultServer: "")
        #expect(reopened.outbox.count == 1 && reopened.server == "https://mac.example")
        #expect(reopened.board?.weeks[0].tasks[0].slots[1]?.d == "2026-10-13")

        await mac.setReachable(true)
        await reopened.syncNow()
        #expect(reopened.outbox.isEmpty)
        let macBoard = await mac.board
        #expect(macBoard.weeks[0].tasks[0].slots[1]?.d == "2026-10-13")         // the Mac got the real day
        #expect(reopened.board == macBoard.withToday(reopened.board!.today))
    }

    @Test func rejectedChangesAreReportedAndDropped() async throws {
        let mac = FakeMac(try sample())
        let store = Store(file: tempFile(), transport: mac, defaultServer: "https://mac.example")
        await store.syncNow()
        store.perform(.mark(.id(999), 0, on: "2026-10-13"))
        await store.syncNow()
        #expect(store.rejected == ["no task 999"] && store.outbox.isEmpty)
    }

    @Test func undoQueuesTheInverse() async throws {
        let mac = FakeMac(try sample())
        let store = Store(file: tempFile(), transport: mac, defaultServer: "https://mac.example")
        await store.syncNow()
        let old = store.board!.weeks[0].tasks[0].slots[0]!
        store.perform(.unmark(.id(1), 0), undo: .init(label: "Unchecked.", op: .restore(.id(1), 0, old)))
        #expect(store.board?.weeks[0].tasks[0].slots[0] == nil)
        store.runUndo()
        #expect(store.board?.weeks[0].tasks[0].slots[0] == old && store.undo == nil)
        await store.syncNow()
        let macBoard = await mac.board
        #expect(macBoard.weeks[0].tasks[0].slots[0] == old)
    }

    @Test func noServerConfigured() async throws {
        let store = Store(file: tempFile(), transport: FakeMac(try sample()), defaultServer: "")
        await store.syncNow()
        #expect(store.status == .offline(SyncError.noServer.localizedDescription))
    }
}

extension Board {
    func withToday(_ t: String) -> Board { var b = self; b.today = t; return b }
}
