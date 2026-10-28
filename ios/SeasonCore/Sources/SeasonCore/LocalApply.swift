import Foundation

/// Applying a queued change to the phone's copy, so the board updates instantly offline.
/// Mirrors the server's rules closely enough for display; the server's answer always wins
/// at the next sync. A change that doesn't apply locally is simply ignored here.
extension Board {
    public mutating func apply(_ op: Op) {
        switch op.kind {
        case .mark:
            guard let r = op.task, let slot = op.slot, let day = op.d, let (w, t) = locate(r),
                  slot < weeks[w].tasks[t].slots.count, weeks[w].tasks[t].slots[slot] == nil else { return }
            var problem: Int? = nil
            if weeks[w].tasks[t].problemList, let current = self.problem {
                problem = current.number
                advanceProblem()
            }
            weeks[w].tasks[t].slots[slot] = Slot(d: day, problem: problem, note: nil)
            refresh(w, t)

        case .unmark:
            guard let r = op.task, let slot = op.slot, let (w, t) = locate(r),
                  slot < weeks[w].tasks[t].slots.count, let old = weeks[w].tasks[t].slots[slot] else { return }
            if weeks[w].tasks[t].problemList, let n = old.problem { rewindProblem(to: n) }
            weeks[w].tasks[t].slots[slot] = nil
            refresh(w, t)

        case .restore:
            guard let r = op.task, let slot = op.slot, let day = op.d, let (w, t) = locate(r),
                  slot < weeks[w].tasks[t].slots.count, weeks[w].tasks[t].slots[slot] == nil else { return }
            if weeks[w].tasks[t].problemList, let n = op.problem, problem?.number == n { advanceProblem() }
            weeks[w].tasks[t].slots[slot] = Slot(d: day, problem: op.problem, note: Board.cleanNote(op.note))
            refresh(w, t)

        case .note:
            guard let r = op.task, let slot = op.slot, let (w, t) = locate(r),
                  slot < weeks[w].tasks[t].slots.count, weeks[w].tasks[t].slots[slot] != nil else { return }
            weeks[w].tasks[t].slots[slot]?.note = Board.cleanNote(op.note)

        case .date:
            // the day has to stay inside the session's own week and not run into the future
            guard let r = op.task, let slot = op.slot, let day = op.d, let (w, t) = locate(r),
                  slot < weeks[w].tasks[t].slots.count, weeks[w].tasks[t].slots[slot] != nil,
                  day >= weeks[w].start, day <= min(weeks[w].end, today) else { return }
            weeks[w].tasks[t].slots[slot]?.d = day

        case .add:
            guard let start = op.week, let key = op.clientKey, let raw = op.text,
                  let w = weeks.firstIndex(where: { $0.start == start }) else { return }
            let parsed = Size.parse(raw.split(whereSeparator: \.isWhitespace).joined(separator: " "))
            let sessions = op.sessions ?? parsed.sessions ?? 1, hours = op.hours ?? parsed.hours ?? 1
            guard Size.valid(sessions: sessions, hours: hours), !parsed.text.isEmpty,
                  locate(.client(key)) == nil else { return }
            let tempID = Board.tempID(for: key)
            weeks[w].tasks.append(BoardTask(
                id: tempID, key: Board.phoneKeyPrefix + key, text: parsed.text, category: "other",
                assignedBy: "pending", confidence: nil, sessions: sessions, each: hours, userAdded: true,
                problemList: false, minSessions: 1, slots: Array(repeating: nil, count: sessions)))
            recountHours(w)

        case .remove:
            guard let r = op.task, let (w, t) = locate(r), weeks[w].tasks[t].userAdded else { return }
            weeks[w].tasks.remove(at: t)
            recountHours(w)

        case .resize:
            guard let r = op.task, let n = op.sessions, let h = op.hours, let (w, t) = locate(r),
                  Size.valid(sessions: n, hours: h), n >= weeks[w].tasks[t].checkedUpTo else { return }
            var task = weeks[w].tasks[t]
            task.slots = Array(task.slots.prefix(n)) + Array(repeating: nil, count: max(0, n - task.slots.count))
            task.sessions = n
            task.each = h
            weeks[w].tasks[t] = task
            refresh(w, t)

        case .category:
            guard let r = op.task, let key = op.category, category(key) != nil, let (w, t) = locate(r) else { return }
            weeks[w].tasks[t].category = key
            weeks[w].tasks[t].assignedBy = "manual"
            weeks[w].tasks[t].confidence = nil

        case .newCategory:
            guard let label = op.label?.trimmingCharacters(in: .whitespaces), !label.isEmpty,
                  let description = op.description?.trimmingCharacters(in: .whitespaces), !description.isEmpty
            else { return }
            let key = Board.categoryKey(label)
            guard !key.isEmpty, category(key) == nil else { return }
            let other = categories.firstIndex { $0.key == "other" } ?? categories.endIndex
            categories.insert(Category(key: key, label: label, description: description, builtin: false), at: other)
            if let r = op.task, let (w, t) = locate(r) {
                weeks[w].tasks[t].category = key
                weeks[w].tasks[t].assignedBy = "manual"
            }

        case .pages:
            if let n = op.pages, !(0...pagesTarget).contains(n) { return }
            pages = op.pages

        case .skip:
            advanceProblem()
        }
    }

    // MARK: helpers

    mutating func advanceProblem() {
        guard problem != nil else { return }
        var rest = upcoming ?? []
        if rest.first == problem { rest.removeFirst() }
        problem = rest.first
        upcoming = rest
    }

    mutating func rewindProblem(to number: Int) {
        guard problem?.number != number else { return }
        let title = upcoming?.first { $0.number == number }?.title ?? "Problem \(number)"
        let p = Problem(number: number, title: title)
        var rest = upcoming ?? []
        if let current = problem, rest.first != current { rest.insert(current, at: 0) }
        rest.insert(p, at: 0)
        problem = p
        upcoming = rest
    }

    mutating func refresh(_ w: Int, _ t: Int) {
        weeks[w].tasks[t].minSessions = max(1, weeks[w].tasks[t].checkedUpTo)
        recountHours(w)
    }

    mutating func recountHours(_ w: Int) {
        weeks[w].hours = weeks[w].tasks.reduce(0) { $0 + Double($1.sessions) * $1.each }
    }

    /// A stable negative id for a phone task (String.hashValue changes every launch).
    static func tempID(for key: String) -> Int {
        var h: UInt64 = 0xcbf29ce484222325
        for b in key.utf8 { h = (h ^ UInt64(b)) &* 0x100000001b3 }
        return -Int(h % 1_000_000_000) - 1
    }

    static func cleanNote(_ note: String?) -> String? {
        guard let n = note?.trimmingCharacters(in: .whitespacesAndNewlines), !n.isEmpty else { return nil }
        return String(n.prefix(500))
    }

    /// Same as Category.key_from_label on the server: "Side Quest!" -> "side-quest".
    static func categoryKey(_ label: String) -> String {
        var out = "", dash = false
        for ch in label.lowercased() {
            if ch.isLetter || ch.isNumber { out.append(ch); dash = false }
            else if !out.isEmpty && !dash { out.append("-"); dash = true }
        }
        while out.hasSuffix("-") { out.removeLast() }
        return String(out.prefix(32))
    }
}
