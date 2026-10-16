import SeasonCore
import SwiftUI
import UIKit

struct TaskRow: View {
    @Environment(Store.self) private var store
    let task: BoardTask
    let board: Board
    let today: String
    @Binding var sheet: Sheet?

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                name
                Button { sheet = .size(task) } label: {
                    Text(Size.label(sessions: task.sessions, hours: task.each))
                        .font(.caption).monospacedDigit().lineLimit(1)
                        .foregroundStyle(task.each == 0 ? Theme.edge : (task.isDone ? Theme.edge : Theme.faint))
                        .padding(.vertical, 6).padding(.horizontal, 6)
                }
                .fixedSize()
                .accessibilityIdentifier("size-\(task.key)")
            }
            // type chip, then the boxes; boxes wrap onto more lines when there are many
            FlowLayout(spacing: 8, lineSpacing: 6) {
                typeMenu.fixedSize()
                boxes
            }
            notes
        }
        .padding(.vertical, 7)
        .contextMenu {
            if task.problemList, board.problem != nil {
                Button("Skip to the next problem", systemImage: "forward") { store.perform(.skip()) }
            }
            if task.userAdded {
                Button("Remove", systemImage: "trash", role: .destructive) { store.perform(.remove(task.ref)) }
            }
        }
    }

    private var title: String {
        if task.problemList, let p = board.problem { return "\(p.number) · \(p.title)" }
        return task.text
    }

    private var name: some View {
        Text(title)
            .font(.system(size: 16))
            .foregroundStyle(task.isDone ? Theme.faint : Theme.ink)
            .strikethrough(task.isDone, color: Theme.faint)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: type

    private var typeMenu: some View {
        Menu {
            ForEach(board.categories) { c in
                Button { if c.key != task.category { store.perform(.assign(task.ref, c.key)) } } label: {
                    if c.key == task.category { Label(c.label, systemImage: "checkmark") } else { Text(c.label) }
                }
            }
            Divider()
            Button("New type…", systemImage: "plus") { sheet = .newType(task.ref) }
        } label: {
            Text(task.assignedBy == "pending" ? "sorting…" : (board.category(task.category)?.label ?? task.category))
                .font(.caption).lineLimit(1)
                .foregroundStyle(task.category == "other" ? Theme.amber : Theme.muted)
                .padding(.vertical, 4).padding(.horizontal, 8)
                .background(Theme.ink.opacity(0.06))
                .clipShape(RoundedRectangle(cornerRadius: 6))
        }
    }

    // MARK: boxes

    @ViewBuilder private var boxes: some View {
        Group {
            ForEach(Array(task.slots.enumerated()), id: \.offset) { i, slot in
                Button { tap(i, slot) } label: {
                    Rectangle()
                        .fill(slot == nil ? Color.clear : Theme.ink)
                        .overlay(Rectangle().stroke(Theme.ink, lineWidth: 1))
                        .frame(width: 24, height: 24)
                        .padding(4).contentShape(Rectangle())
                }
                .padding(-4)
                .contextMenu {
                    // a note is optional: long-press a checked box to add or edit it
                    if let s = slot {
                        Button(s.note == nil ? "Add note" : "Edit note", systemImage: "square.and.pencil") {
                            sheet = .note(ref: task.ref, slot: i, title: title, old: s.note, justTicked: false)
                        }
                    }
                }
                .accessibilityIdentifier("box-\(task.key)-\(i)")
                .accessibilityValue(slot == nil ? "open" : "done")
            }
        }
    }

    private func tap(_ i: Int, _ slot: Slot?) {
        if let old = slot {
            store.perform(.unmark(task.ref, i),
                          undo: .init(label: old.note == nil ? "Unchecked." : "Unchecked (note kept for undo).",
                                      op: .restore(task.ref, i, old)))
        } else {
            store.perform(.mark(task.ref, i, on: today))
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
        }
    }

    // MARK: notes

    @ViewBuilder private var notes: some View {
        let withNotes = task.slots.enumerated().compactMap { i, s in s?.note == nil ? nil : (i, s!) }
        if !withNotes.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(withNotes, id: \.0) { i, s in
                    Button {
                        sheet = .note(ref: task.ref, slot: i, title: title, old: s.note, justTicked: false)
                    } label: {
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text("\(Day.weekday(s.d)) \(Int(s.d.suffix(2)) ?? 0)\(s.problem.map { " · \($0)" } ?? "")")
                                .foregroundStyle(Theme.faint).monospacedDigit()
                            Text(s.note ?? "").foregroundStyle(Theme.muted).lineLimit(2).multilineTextAlignment(.leading)
                        }
                        .font(.caption)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .accessibilityIdentifier("note-\(task.key)-\(i)")
                }
            }
        }
    }
}
