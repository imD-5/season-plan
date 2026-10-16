import SeasonCore
import SwiftUI

struct SheetView: View {
    @Environment(Store.self) private var store
    @Environment(\.dismiss) private var dismiss
    let sheet: Sheet

    var body: some View {
        Group {
            switch sheet {
            case .note(let ref, let slot, let title, let old, let justTicked):
                NoteSheet(ref: ref, slot: slot, title: title, old: old, justTicked: justTicked)
            case .size(let task): SizeSheet(task: task)
            case .newType(let ref): NewTypeSheet(ref: ref)
            case .pages: PagesSheet()
            case .settings: SettingsSheet()
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .preferredColorScheme(.dark)
    }
}

private struct SheetTitle: View {
    let text: String
    var body: some View {
        Text(text).font(.headline).foregroundStyle(Theme.ink).lineLimit(1)
    }
}

private struct PrimaryButton: View {
    let title: String
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            Text(title).font(.headline).frame(maxWidth: .infinity).padding(.vertical, 12)
                .background(Theme.ink).foregroundStyle(Theme.bg).clipShape(RoundedRectangle(cornerRadius: 10))
        }
    }
}

// MARK: note

struct NoteSheet: View {
    @Environment(Store.self) private var store
    @Environment(\.dismiss) private var dismiss
    let ref: TaskRef, slot: Int, title: String, old: String?, justTicked: Bool
    @State private var text = ""
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            SheetTitle(text: justTicked ? "Done: \(title)" : title)
            TextField("", text: $text, prompt: Text("Note for this session (optional)").foregroundStyle(Theme.faint),
                      axis: .vertical)
                .lineLimit(3...6).font(.body).foregroundStyle(Theme.ink)
                .padding(12).background(Theme.bg).clipShape(RoundedRectangle(cornerRadius: 8))
                .focused($focused)
                .accessibilityIdentifier("note-field")
            HStack(spacing: 10) {
                if old != nil {
                    Button("Remove note") { save(nil) }.foregroundStyle(Theme.rose)
                        .accessibilityIdentifier("note-remove")
                } else if justTicked {
                    Button("Skip") { dismiss() }.foregroundStyle(Theme.muted)
                        .accessibilityIdentifier("note-skip")
                }
                Spacer()
                Button("Save") { save(text) }
                    .font(.headline).foregroundStyle(Theme.ink)
                    .accessibilityIdentifier("note-save")
            }
        }
        .onAppear { text = old ?? ""; focused = true }
    }

    private func save(_ value: String?) {
        let new = value?.trimmingCharacters(in: .whitespacesAndNewlines)
        let after = (new?.isEmpty ?? true) ? nil : new
        if after != old {
            store.perform(.note(ref, slot, after),
                          undo: .init(label: after == nil ? "Note removed." : (old == nil ? "Note saved." : "Note changed."),
                                      op: .note(ref, slot, old)))
        }
        dismiss()
    }
}

// MARK: size

struct SizeSheet: View {
    @Environment(Store.self) private var store
    @Environment(\.dismiss) private var dismiss
    let task: BoardTask
    @State private var sessions = 1
    @State private var hours = 1.0

    var body: some View {
        let minimum = max(1, task.checkedUpTo)
        VStack(alignment: .leading, spacing: 16) {
            SheetTitle(text: task.text)
            Stepper(value: $sessions, in: minimum...Size.maxSessions) {
                row("Boxes", "\(sessions)")
            }
            .accessibilityIdentifier("size-boxes")
            if minimum > 1 && sessions == minimum {
                Text("Box \(minimum) is checked. Uncheck it to go lower.").font(.caption).foregroundStyle(Theme.faint)
            }
            Stepper(value: $hours, in: 0...Size.maxHours, step: 0.5) {
                row("Hours each", hours == 0 ? "—" : Size.label(sessions: 1, hours: hours))
            }
            .accessibilityIdentifier("size-hours")
            Text(hours == 0 ? "No time estimate" : "About \(BoardView.hours(Double(sessions) * hours))h this week")
                .font(.caption).foregroundStyle(Theme.faint)
            PrimaryButton(title: "Done") {
                if sessions != task.sessions || hours != task.each {
                    store.perform(.resize(task.ref, sessions: sessions, hours: hours))
                }
                dismiss()
            }
            .accessibilityIdentifier("size-done")
        }
        .onAppear { sessions = task.sessions; hours = task.each }
    }

    private func row(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label).foregroundStyle(Theme.muted)
            Spacer()
            Text(value).monospacedDigit().foregroundStyle(Theme.ink)
        }
    }
}

// MARK: new type

struct NewTypeSheet: View {
    @Environment(Store.self) private var store
    @Environment(\.dismiss) private var dismiss
    let ref: TaskRef?
    @State private var label = ""
    @State private var description = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            SheetTitle(text: "New type")
            field("Name", "e.g. errands", $label)
            field("What goes in it (Jev uses this to sort)", "e.g. Paperwork, shopping, appointments", $description)
            PrimaryButton(title: "Create") {
                store.perform(.newCategory(label: label.trimmingCharacters(in: .whitespaces),
                                           description: description.trimmingCharacters(in: .whitespaces), task: ref))
                dismiss()
            }
            .disabled(label.trimmingCharacters(in: .whitespaces).isEmpty
                      || description.trimmingCharacters(in: .whitespaces).isEmpty)
        }
    }

    private func field(_ title: String, _ hint: String, _ value: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.caption).foregroundStyle(Theme.faint)
            TextField("", text: value, prompt: Text(hint).foregroundStyle(Theme.edge))
                .foregroundStyle(Theme.ink).padding(10).background(Theme.bg).clipShape(RoundedRectangle(cornerRadius: 8))
        }
    }
}

// MARK: pages

struct PagesSheet: View {
    @Environment(Store.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var text = ""
    @FocusState private var focused: Bool

    var body: some View {
        let target = store.board?.pagesTarget ?? 100
        VStack(alignment: .leading, spacing: 14) {
            SheetTitle(text: "Thesis pages written")
            HStack {
                TextField("", text: $text, prompt: Text("—").foregroundStyle(Theme.faint))
                    .keyboardType(.numberPad).font(.title2.monospacedDigit()).foregroundStyle(Theme.ink)
                    .focused($focused).frame(width: 90)
                Text("/ \(target)").font(.title2.monospacedDigit()).foregroundStyle(Theme.muted)
            }
            HStack(spacing: 12) {
                Button("Clear") { store.perform(.pages(nil)); dismiss() }.foregroundStyle(Theme.muted)
                Spacer()
                Button("Save") {
                    if let n = Int(text), (0...target).contains(n) { store.perform(.pages(n)) }
                    dismiss()
                }
                .font(.headline).foregroundStyle(Theme.ink)
            }
        }
        .onAppear { text = store.board?.pages.map(String.init) ?? ""; focused = true }
    }
}

// MARK: settings

struct SettingsSheet: View {
    @Environment(Store.self) private var store
    @State private var address = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            SheetTitle(text: "Settings")
            VStack(alignment: .leading, spacing: 4) {
                Text("Mac address").font(.caption).foregroundStyle(Theme.faint)
                TextField("https://your-mac.your-tailnet.ts.net", text: $address)
                    .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                    .foregroundStyle(Theme.ink).padding(10).background(Theme.bg).clipShape(RoundedRectangle(cornerRadius: 8))
                    .onSubmit { store.server = address }
            }
            Group {
                Text("\(store.outbox.count) change\(store.outbox.count == 1 ? "" : "s") waiting to sync")
                if let t = store.lastSync { Text("Last synced ") + Text(t, style: .relative) + Text(" ago") }
                if case .offline(let why) = store.status { Text(why).foregroundStyle(Theme.rose) }
            }
            .font(.footnote).foregroundStyle(Theme.muted)
            PrimaryButton(title: "Sync now") {
                store.server = address.trimmingCharacters(in: .whitespaces)
                Task { await store.syncNow() }
            }
            Text("The board lives on your Mac. This phone keeps a copy, works offline, and sends changes when it can reach the Mac over Tailscale.")
                .font(.caption).foregroundStyle(Theme.faint)
        }
        .onAppear { address = store.server }
    }
}
