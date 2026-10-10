// Season — a tiny macOS window around the season board (http://127.0.0.1:8765/).
// Build: ./build.sh

import Cocoa
import WebKit

let boardURL = URL(string: "http://127.0.0.1:8765/")!
let bg = NSColor(srgbRed: 0x12 / 255.0, green: 0x12 / 255.0, blue: 0x10 / 255.0, alpha: 1)

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var retrying = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMenu()

        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = self
        web.setValue(false, forKey: "drawsBackground")
        web.allowsMagnification = true

        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 620, height: 800),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Season"
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.appearance = NSAppearance(named: .darkAqua)
        window.backgroundColor = bg
        window.minSize = NSSize(width: 500, height: 520)
        window.contentView = web
        window.center()
        window.setFrameAutosaveName("SeasonMain")
        window.isReleasedWhenClosed = false
        window.makeKeyAndOrderFront(nil)

        load()
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag { window.makeKeyAndOrderFront(nil) }
        return true
    }

    func applicationDidBecomeActive(_ notification: Notification) {
        // The page refreshes itself on focus; this covers a dead page after sleep.
        if web.url == nil { load() }
    }

    @objc func load() {
        retrying = false
        web.load(URLRequest(url: boardURL, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 5))
    }

    // Server not up yet: show a calm message, nudge launchd, try again.
    func serverDown(_ error: Error) {
        if (error as NSError).code == NSURLErrorCancelled || retrying { return }
        retrying = true
        let html = """
        <html><body style="background:#121210;color:#9c978c;font:13px -apple-system;padding:40px">
        Starting the board server…</body></html>
        """
        web.loadHTMLString(html, baseURL: nil)
        let kick = Process()
        kick.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        kick.arguments = ["kickstart", "gui/\(getuid())/com.daigokimura.season-board"]
        try? kick.run()
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in self?.load() }
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        serverDown(error)
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        serverDown(error)
    }

    func buildMenu() {
        let main = NSMenu()

        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Hide Season", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Quit Season", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        main.addItem(appItem)

        let editItem = NSMenuItem()
        let edit = NSMenu(title: "Edit")
        edit.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
        edit.addItem(withTitle: "Redo", action: Selector(("redo:")), keyEquivalent: "Z")
        edit.addItem(.separator())
        edit.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = edit
        main.addItem(editItem)

        let viewItem = NSMenuItem()
        let view = NSMenu(title: "View")
        let reload = NSMenuItem(title: "Reload", action: #selector(load), keyEquivalent: "r")
        reload.target = self
        view.addItem(reload)
        viewItem.submenu = view
        main.addItem(viewItem)

        let winItem = NSMenuItem()
        let win = NSMenu(title: "Window")
        win.addItem(withTitle: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        win.addItem(withTitle: "Close", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        winItem.submenu = win
        main.addItem(winItem)
        NSApp.windowsMenu = win

        NSApp.mainMenu = main
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
