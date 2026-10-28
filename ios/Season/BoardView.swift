import SeasonCore
import SwiftUI

/// What a sheet is open for.
enum Sheet: Identifiable {
    case note(ref: TaskRef, slot: Int, title: String, old: String?, justTicked: Bool)
    case day(ref: TaskRef, slot: Int, title: String, old: String)
    case size(BoardTask)
    case newType(TaskRef?)
    case pages
    case settings

    var id: String {
        switch self {
        case .note(let r, let s, _, _, _): return "note-\(r)-\(s)"
        case .day(let r, let s, _, _): return "day-\(r)-\(s)"
        case .size(let t): return "size-\(t.key)"
        case .newType: return "type"
        case .pages: return "pages"
        case .settings: return "settings"
        }
    }
}

struct BoardView: View {
    @Environment(Store.self) private var store
    @State private var picked: Int?            // week the user tapped; nil = this week
    @State private var sheet: Sheet?
    @State private var newTask = ""
    @FocusState private var adding: Bool

    var body: some View {
        let board = store.board!
        let today = Day.string()
        let current = board.weekIndex(containing: today)
        let wi = min(picked ?? current, board.weeks.count - 1)
        let week = board.weeks[wi]

        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                header(board, week)
                ticks(board, selected: wi, current: current, today: today).padding(.top, 10)
                if !week.glance.isEmpty {
                    Text(week.glance).font(.subheadline).foregroundStyle(Theme.muted).lineLimit(2).padding(.top, 8)
                }
                dayStrip(board, week, today: today).padding(.top, 8)
                Text("THIS WEEK — PICK ANY").font(.caption2).tracking(1).foregroundStyle(Theme.faint)
                    .padding(.top, 14).padding(.bottom, 0)
                ForEach(week.tasks) { task in
                    TaskRow(task: task, board: board, today: today, sheet: $sheet)
                    Divider().overlay(Theme.line.opacity(0.6))
                }
                addField(week)
                statusLine.padding(.top, 4)
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 12)
        }
        .scrollDismissesKeyboard(.interactively)
        .scrollBounceBehavior(.basedOnSize)
        .solidStatusBar()
        .refreshable { await store.syncNow() }
        .overlay(alignment: .bottom) { banner }
        .sheet(item: $sheet) { s in
            SheetView(sheet: s).environment(store)
                .presentationDetents([.height(s.isTall ? 420 : 300)])
                .presentationBackground(Theme.card)
        }
    }

    // MARK: header

    private func header(_ board: Board, _ week: Week) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(week.label).font(.system(size: 22, weight: .semibold)).foregroundStyle(Theme.ink)
            Spacer()
            Text("~\(Self.hours(week.hours))h").font(.footnote).monospacedDigit().foregroundStyle(Theme.muted)
            Button { sheet = .pages } label: {
                Text("\(board.pages.map(String.init) ?? "—") / \(board.pagesTarget) pp")
                    .font(.footnote).monospacedDigit().foregroundStyle(Theme.muted)
                    .padding(.vertical, 6).padding(.horizontal, 6)
            }
            .accessibilityIdentifier("pages")
            Button { sheet = .settings } label: {
                Image(systemName: "gearshape").font(.footnote).foregroundStyle(Theme.faint).padding(6)
            }
            .accessibilityLabel("Settings")
        }
        .padding(.top, 2)
    }

    static func hours(_ h: Double) -> String { h == h.rounded() ? String(Int(h)) : String(format: "%.1f", h) }

    // MARK: season ticks

    private func ticks(_ board: Board, selected: Int, current: Int, today: String) -> some View {
        let months = Dictionary(grouping: board.weeks.indices) { String(board.weeks[$0].start.prefix(7)) }
        let names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return FlowLayout(spacing: 12, lineSpacing: 8) {
            ForEach(months.keys.sorted(), id: \.self) { month in
                VStack(alignment: .leading, spacing: 4) {
                    Text(names[(Int(month.suffix(2)) ?? 1) - 1]).font(.caption2).tracking(1).foregroundStyle(Theme.faint)
                    HStack(spacing: 5) {
                        ForEach(months[month]!, id: \.self) { i in
                            let w = board.weeks[i]
                            Button { picked = i == current ? nil : i } label: {
                                Rectangle()
                                    .fill(i == current ? Theme.ink : (w.end < today ? Theme.edge : .clear))
                                    .overlay(Rectangle().stroke(i == current ? Theme.ink : Theme.edge, lineWidth: 1))
                                    .frame(width: 15, height: 15)
                                    .overlay(Rectangle().stroke(Theme.ink, lineWidth: 1).padding(-3)
                                        .opacity(i == selected && i != current ? 1 : 0))
                                    .padding(4).contentShape(Rectangle())
                            }
                            .padding(-4)
                            .accessibilityLabel(w.label)
                        }
                    }
                }
            }
        }
    }

    // MARK: day strip

    private func dayStrip(_ board: Board, _ week: Week, today: String) -> some View {
        HStack(alignment: .top, spacing: 2) {
            ForEach(0..<7, id: \.self) { i in
                let day = Day.adding(i, to: week.start)
                VStack(alignment: .leading, spacing: 2) {
                    Text("\(Day.weekday(day)) \(Int(day.suffix(2)) ?? 0)")
                        .font(.system(size: 10, weight: day == today ? .semibold : .regular)).monospacedDigit()
                        .foregroundStyle(day == today ? Theme.ink : Theme.muted)
                        .padding(.bottom, 3)
                    ForEach(Array((board.events[day] ?? []).enumerated()), id: \.offset) { _, e in
                        Text(e.t).font(.system(size: 10, weight: ["me", "due"].contains(e.k) ? .semibold : .regular))
                            .foregroundStyle(Theme.eventColor(e.k)).lineLimit(1)
                    }
                    // at most 3 lines per day so a busy day can't push the board off the screen
                    let done = board.done(on: day)
                    ForEach(Array(done.prefix(done.count > 3 ? 2 : 3).enumerated()), id: \.offset) { _, d in
                        Text("✓ \(d.label)").font(.system(size: 10)).foregroundStyle(Theme.green).lineLimit(1)
                    }
                    if done.count > 3 {
                        Text("✓ +\(done.count - 2) more").font(.system(size: 10)).foregroundStyle(Theme.green).lineLimit(1)
                    }
                }
                .frame(maxWidth: .infinity, minHeight: 40, alignment: .topLeading)
                .padding(.horizontal, 3).padding(.vertical, 5)
                .background(day == today ? Theme.ink.opacity(0.06) : .clear)
                .overlay(alignment: .top) { Rectangle().fill(day == today ? Theme.ink : Theme.line).frame(height: day == today ? 2 : 1) }
                .opacity(day < today ? 0.7 : 1)
            }
        }
    }

    // MARK: add

    private func addField(_ week: Week) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            TextField("", text: $newTask, prompt: Text("+ Add to this week").foregroundStyle(Theme.faint))
                .font(.body).foregroundStyle(Theme.ink)
                .focused($adding)
                .submitLabel(.done)
                .onSubmit { add(to: week) }
                .padding(.vertical, 10)
                .accessibilityIdentifier("add-field")
            if adding {
                Text("End with 3x2h for 3 boxes of 2h · 2h or 30m for one box · nothing = 1 box of 1h")
                    .font(.caption2).foregroundStyle(Theme.faint)
            }
        }
    }

    private func add(to week: Week) {
        let text = newTask.trimmingCharacters(in: .whitespaces)
        newTask = ""
        guard !text.isEmpty else { return }
        let parsed = Size.parse(text)
        guard Size.valid(sessions: parsed.sessions ?? 1, hours: parsed.hours ?? 1) else {
            newTask = text
            return
        }
        store.perform(.add(week: week.start, text: text, sessions: nil, hours: nil))
    }

    // MARK: status

    private var statusLine: some View {
        HStack(spacing: 6) {
            switch store.status {
            case .syncing:
                ProgressView().scaleEffect(0.6).frame(width: 12, height: 12)
                Text("Syncing…")
            case .offline(let why):
                Image(systemName: "icloud.slash")
                Text(store.outbox.isEmpty ? why : "\(store.outbox.count) change\(store.outbox.count == 1 ? "" : "s") waiting · \(why)")
            case .idle:
                Image(systemName: "checkmark.icloud")
                if let t = store.lastSync {
                    Text("Synced ") + Text(t, style: .relative) + Text(" ago")
                } else {
                    Text("Not synced yet")
                }
            }
        }
        .font(.caption).foregroundStyle(Theme.faint)
        .accessibilityIdentifier("sync-status")
    }

    // MARK: banners

    @ViewBuilder private var banner: some View {
        if !store.rejected.isEmpty {
            bannerBox {
                Text("The Mac couldn't apply \(store.rejected.count == 1 ? "a change" : "\(store.rejected.count) changes"): \(store.rejected.joined(separator: "; "))")
                    .font(.footnote).foregroundStyle(Theme.rose)
            }
        } else if let u = store.undo {
            bannerBox {
                HStack {
                    Text(u.label).font(.footnote).foregroundStyle(Theme.soft)
                    Spacer()
                    Button("Undo") { store.runUndo() }
                        .font(.footnote.weight(.semibold)).foregroundStyle(Theme.ink)
                        .padding(.vertical, 8).padding(.horizontal, 12)
                        .accessibilityIdentifier("undo")
                }
            }
            .task(id: u.op.id) {
                try? await Task.sleep(for: .seconds(8))
                if store.undo?.op.id == u.op.id { store.clearUndo() }
            }
        }
    }

    private func bannerBox<C: View>(@ViewBuilder _ content: () -> C) -> some View {
        content()
            .padding(.horizontal, 14).padding(.vertical, 6)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.card)
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.line))
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .padding(.horizontal, 12).padding(.bottom, 8)
    }
}

extension Sheet {
    var isTall: Bool {
        switch self {
        case .newType, .settings: return true
        default: return false
        }
    }
}

extension View {
    /// No blur under the status bar: iOS 26+ blurs scrolled content at the top edge by default.
    /// Turn that off and cover the status bar area with the background instead.
    func solidStatusBar() -> some View {
        modifier(SolidStatusBar())
    }
}

private struct SolidStatusBar: ViewModifier {
    func body(content: Content) -> some View {
        // a zero-height bar at the top edge whose background extends up through the status bar
        let base = content.overlay(alignment: .top) {
            Color.clear.frame(height: 0)
                .background(Theme.bg.ignoresSafeArea(edges: .top))
                .allowsHitTesting(false)
        }
        if #available(iOS 26.0, *) {
            base.scrollEdgeEffectHidden(true, for: .top)
        } else {
            base
        }
    }
}
