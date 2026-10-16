import SeasonCore
import SwiftUI

@main
struct SeasonApp: App {
    @State private var store: Store
    @Environment(\.scenePhase) private var phase

    init() {
        let defaults = UserDefaults.standard
        // UI tests and the simulator pass -SeasonServerURL / -SeasonFreshStart as launch arguments.
        let server = defaults.string(forKey: "SeasonServerURL")
            ?? (Bundle.main.object(forInfoDictionaryKey: "SeasonServerURL") as? String) ?? ""
        let file = Store.defaultFile()
        if defaults.bool(forKey: "SeasonFreshStart") { try? FileManager.default.removeItem(at: file) }
        _store = State(initialValue: Store(file: file, defaultServer: server))
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(store)
                .preferredColorScheme(.dark)
                .onChange(of: phase) { _, now in
                    if now == .active { Task { await store.syncNow() } }
                }
                .task {
                    // Keep in step with the Mac while the app is open.
                    while !Task.isCancelled {
                        await store.syncNow()
                        try? await Task.sleep(for: .seconds(60))
                    }
                }
        }
    }
}

struct RootView: View {
    @Environment(Store.self) private var store

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()
            if store.board != nil { BoardView() } else { ConnectView() }
        }
    }
}

/// First launch: the phone has no board yet and needs the Mac once.
struct ConnectView: View {
    @Environment(Store.self) private var store
    @State private var address = ""
    @State private var loading = false

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Season").font(.system(size: 30, weight: .semibold)).foregroundStyle(Theme.ink)
            Text("Load your board from your Mac once. After that it works offline and syncs whenever the Mac is reachable.")
                .font(.subheadline).foregroundStyle(Theme.muted)
            VStack(alignment: .leading, spacing: 6) {
                Text("MAC ADDRESS").font(.caption2).tracking(1).foregroundStyle(Theme.faint)
                TextField("https://your-mac.your-tailnet.ts.net", text: $address)
                    .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                    .font(.body).foregroundStyle(Theme.ink)
                    .padding(12).background(Theme.card).clipShape(RoundedRectangle(cornerRadius: 8))
                    .accessibilityIdentifier("server-field")
            }
            Button {
                store.server = address.trimmingCharacters(in: .whitespaces)
                loading = true
                Task { await store.syncNow(); loading = false }
            } label: {
                HStack { if loading { ProgressView().tint(Theme.bg) }; Text(loading ? "Loading…" : "Load board") }
                    .font(.headline).frame(maxWidth: .infinity).padding(.vertical, 14)
                    .background(Theme.ink).foregroundStyle(Theme.bg).clipShape(RoundedRectangle(cornerRadius: 10))
            }
            .disabled(address.trimmingCharacters(in: .whitespaces).isEmpty || loading)
            .accessibilityIdentifier("load-board")
            if case .offline(let why) = store.status {
                Text(why).font(.footnote).foregroundStyle(Theme.rose)
            }
            Spacer()
        }
        .padding(24)
        .onAppear { address = store.server }
    }
}
