import SwiftUI

/// Same palette as the web board (board.html).
enum Theme {
    static let bg = Color(hex: 0x121210)
    static let card = Color(hex: 0x1D1C19)
    static let ink = Color(hex: 0xF3F0E8)
    static let soft = Color(hex: 0xD8D4CA)
    static let muted = Color(hex: 0x9C978C)
    static let faint = Color(hex: 0x6A665E)
    static let line = Color(hex: 0x34312C)
    static let edge = Color(hex: 0x4A4741)
    static let amber = Color(hex: 0xE8B64C)
    static let rose = Color(hex: 0xD99A9A)
    static let green = Color(hex: 0x8FB38A)

    static func eventColor(_ kind: String) -> Color {
        switch kind {
        case "me", "due": return amber
        case "her": return rose
        case "off": return faint
        default: return soft
        }
    }
}

extension Color {
    init(hex: UInt32) {
        self.init(.sRGB, red: Double((hex >> 16) & 0xFF) / 255, green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255, opacity: 1)
    }
}

/// Lays children left to right and wraps to a new line when out of room (the week ticks).
struct FlowLayout: Layout {
    var spacing: CGFloat = 16
    var lineSpacing: CGFloat = 12

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        var x: CGFloat = 0, y: CGFloat = 0, lineHeight: CGFloat = 0, widest: CGFloat = 0
        for s in subviews {
            let size = s.sizeThatFits(.unspecified)
            if x > 0, x + size.width > width { y += lineHeight + lineSpacing; x = 0; lineHeight = 0 }
            x += size.width + spacing
            widest = max(widest, x - spacing)
            lineHeight = max(lineHeight, size.height)
        }
        return CGSize(width: min(widest, width), height: y + lineHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX, y = bounds.minY, lineHeight: CGFloat = 0
        for s in subviews {
            let size = s.sizeThatFits(.unspecified)
            if x > bounds.minX, x + size.width > bounds.maxX { y += lineHeight + lineSpacing; x = bounds.minX; lineHeight = 0 }
            s.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            lineHeight = max(lineHeight, size.height)
        }
    }
}
