import Foundation
import Observation

/// Sends the queued changes to the Mac and returns the Mac's board.
public protocol SyncTransport: Sendable {
    func sync(server: URL, ops: [Op]) async throws -> SyncResponse
}

public struct OpResult: Codable, Equatable, Sendable {
    public var id: String
    public var ok: Bool
    public var error: String?
}

public struct SyncResponse: Sendable {
    public var board: Board
    public var results: [OpResult]
    public init(board: Board, results: [OpResult]) { self.board = board; self.results = results }
}

public enum SyncError: Error, Equatable, LocalizedError {
    case noServer
    case unreachable(String)
    case server(Int, String)

    public var errorDescription: String? {
        switch self {
        case .noServer: return "Set your Mac's address in Settings."
        case .unreachable(let why): return "Mac not reachable (\(why))."
        case .server(let code, let msg): return "The Mac answered \(code): \(msg)"
        }
    }
}

/// POST /api/sync over HTTPS (Tailscale) or http://127.0.0.1 (simulator).
public struct HTTPTransport: SyncTransport {
    public init() {}

    public func sync(server: URL, ops: [Op]) async throws -> SyncResponse {
        var req = URLRequest(url: server.appending(path: "api/sync"), timeoutInterval: 10)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("season", forHTTPHeaderField: "X-Requested-With")
        req.httpBody = try Board.encoder().encode(["ops": ops])
        let data: Data, response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: req)
        } catch {
            throw SyncError.unreachable((error as? URLError)?.code == .timedOut ? "timed out" : error.localizedDescription)
        }
        let code = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard code == 200 else {
            let msg = (try? JSONDecoder().decode([String: String].self, from: data))?["error"] ?? "error"
            throw SyncError.server(code, msg)
        }
        struct Envelope: Decodable { var sync: Results?; struct Results: Decodable { var results: [OpResult] } }
        let board = try Board.decoder().decode(Board.self, from: data)
        let results = (try? Board.decoder().decode(Envelope.self, from: data))?.sync?.results ?? []
        return SyncResponse(board: board, results: results)
    }
}

/// Everything the phone keeps between launches.
struct Saved: Codable {
    var base: Board?            // the Mac's board as of the last sync
    var outbox: [Op]            // changes not yet confirmed by the Mac
    var lastSync: Date?
    var server: String?
}

/// The phone's board: the last synced board plus local changes, persisted, synced when possible.
@MainActor @Observable
public final class Store {
    public enum Status: Equatable {
        case idle, syncing
        case offline(String)
    }

    public struct Undo: Equatable {
        public var label: String
        public var op: Op
        public init(label: String, op: Op) { self.label = label; self.op = op }
    }

    public private(set) var board: Board?
    public private(set) var outbox: [Op] = []
    public private(set) var lastSync: Date?
    public private(set) var status: Status = .idle
    /// Changes the Mac refused at the last sync, with its reasons. Cleared on the next action.
    public private(set) var rejected: [String] = []
    public private(set) var undo: Undo?
    public var server: String { didSet { save() } }

    private var base: Board?
    private let file: URL
    private let transport: SyncTransport
    private var syncTask: Task<Void, Never>?
    private var resync = false

    public init(file: URL, transport: SyncTransport = HTTPTransport(), defaultServer: String = "") {
        self.file = file
        self.transport = transport
        let saved = (try? Data(contentsOf: file)).flatMap { try? JSONDecoder().decode(Saved.self, from: $0) }
        server = saved?.server ?? defaultServer
        base = saved?.base
        outbox = saved?.outbox ?? []
        lastSync = saved?.lastSync
        rebuild()
    }

    public static func defaultFile() -> URL {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appending(path: "season-board.json")
    }

    // MARK: actions

    public func perform(_ op: Op, undo: Undo? = nil) {
        guard board != nil else { return }
        outbox.append(op)
        board?.apply(op)
        self.undo = undo
        rejected = []
        save()
        scheduleSync()
    }

    public func runUndo() {
        guard let u = undo else { return }
        undo = nil
        perform(u.op)
    }

    public func clearUndo() { undo = nil }

    // MARK: sync

    /// Send the queue (or just pull, if empty). Safe to call often; overlapping calls coalesce.
    public func syncNow() async {
        if syncTask != nil { resync = true; await syncTask?.value; return }
        let task = Task { await runSync() }
        syncTask = task
        await task.value
        syncTask = nil
        if resync { resync = false; await syncNow() }
    }

    private func scheduleSync() {
        Task { await syncNow() }
    }

    private func runSync() async {
        guard let url = URL(string: server.trimmingCharacters(in: .whitespaces)), url.scheme != nil else {
            status = .offline(SyncError.noServer.localizedDescription)
            return
        }
        let sending = outbox
        status = .syncing
        do {
            let response = try await transport.sync(server: url, ops: sending)
            let sent = Set(sending.map(\.id))
            outbox.removeAll { sent.contains($0.id) }
            base = response.board
            lastSync = Date()
            let refused = response.results.filter { !$0.ok }.map { $0.error ?? "rejected" }
            if !refused.isEmpty { rejected += refused }   // an empty follow-up sync must not hide them
            status = .idle
            rebuild()
            save()
        } catch {
            status = .offline((error as? LocalizedError)?.errorDescription ?? error.localizedDescription)
        }
    }

    private func rebuild() {
        guard var b = base else { board = nil; return }
        for op in outbox { b.apply(op) }
        b.today = Day.string()
        board = b
    }

    private func save() {
        let saved = Saved(base: base, outbox: outbox, lastSync: lastSync, server: server)
        if let data = try? JSONEncoder().encode(saved) { try? data.write(to: file, options: .atomic) }
    }
}
