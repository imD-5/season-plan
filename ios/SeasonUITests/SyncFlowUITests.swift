import XCTest

/// Drives the real app in the simulator against a throwaway server (SEASON_TEST_SERVER).
final class SyncFlowUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    func testLoadTickNoteUndoAndAdd() throws {
        let server = ProcessInfo.processInfo.environment["SEASON_TEST_SERVER"] ?? "http://127.0.0.1:8899"
        let app = XCUIApplication()
        app.launchArguments = ["-SeasonServerURL", server, "-SeasonFreshStart", "YES"]
        app.launch()

        // first launch: the address came with the app, so the start-up sync may load the board
        // before anyone taps "Load board"
        let load = app.buttons["load-board"]
        if load.waitForExistence(timeout: 3), load.isHittable { load.tap() }
        let box = app.buttons["box-thesis-0"]
        XCTAssertTrue(box.waitForExistence(timeout: 15), "board did not load")
        snapshot(app, "1-board")

        // tick -> note sheet -> save
        box.tap()
        let field = app.textFields["note-field"].exists ? app.textFields["note-field"] : app.textViews["note-field"]
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        field.typeText("written on the phone")
        app.buttons["note-save"].tap()
        XCTAssertTrue(app.buttons["note-thesis-0"].waitForExistence(timeout: 5))
        XCTAssertEqual(box.value as? String, "done")
        snapshot(app, "2-ticked")

        // untick -> one tap on Undo restores it
        box.tap()
        XCTAssertEqual(box.value as? String, "open")
        let undo = app.buttons["undo"]
        XCTAssertTrue(undo.waitForExistence(timeout: 5))
        undo.tap()
        XCTAssertEqual(box.value as? String, "done")
        XCTAssertTrue(app.buttons["note-thesis-0"].waitForExistence(timeout: 5))

        // add a sized task
        let add = app.textFields["add-field"]
        add.tap()
        add.typeText("Read related papers 3x2h\n")
        XCTAssertTrue(app.staticTexts["Read related papers"].waitForExistence(timeout: 5))

        // wait until everything is synced
        let status = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'Synced'")).firstMatch
        XCTAssertTrue(status.waitForExistence(timeout: 20), "never reported synced")
        sleep(2)
        snapshot(app, "3-synced")
    }

    private func snapshot(_ app: XCUIApplication, _ name: String) {
        let a = XCTAttachment(screenshot: app.screenshot())
        a.name = name
        a.lifetime = .keepAlways
        add(a)
    }
}
