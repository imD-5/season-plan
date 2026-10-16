// swift-tools-version: 6.0
// The phone app's logic with no UI: board model, offline change queue, local apply, sync.
// Tested on the Mac with `swift test`; the iOS app target depends on it.
import PackageDescription

let package = Package(
    name: "SeasonCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "SeasonCore", targets: ["SeasonCore"])],
    targets: [
        .target(name: "SeasonCore"),
        .testTarget(name: "SeasonCoreTests", dependencies: ["SeasonCore"]),
    ]
)
