// Draws the Season app icon (1024×1024 PNG): a dark tile with a grid of week boxes.
// Usage: swift icon.swift out.png            macOS style: rounded tile with transparent margin
//        swift icon.swift out.png --square   iPhone/web style: full-bleed square (iOS rounds it)

import AppKit

let size: CGFloat = 1024
let args = CommandLine.arguments.dropFirst()
let square = args.contains("--square")
let out = args.first(where: { !$0.hasPrefix("--") }) ?? "icon.png"

func color(_ hex: UInt32, _ a: CGFloat = 1) -> NSColor {
    NSColor(srgbRed: CGFloat((hex >> 16) & 0xff) / 255, green: CGFloat((hex >> 8) & 0xff) / 255,
            blue: CGFloat(hex & 0xff) / 255, alpha: a)
}

let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(size), pixelsHigh: Int(size),
                           bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                           colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)

if square {
    // full bleed, no transparency: iOS applies its own rounded mask
    color(0x1b1a17).setFill()
    NSRect(x: 0, y: 0, width: size, height: size).fill()
} else {
    // macOS icon grid: 824pt tile centred in 1024 canvas
    let inset: CGFloat = 100
    let tile = NSRect(x: inset, y: inset, width: size - inset * 2, height: size - inset * 2)
    let tilePath = NSBezierPath(roundedRect: tile, xRadius: 185, yRadius: 185)
    color(0x1b1a17).setFill()
    tilePath.fill()
    color(0xf3f0e8, 0.08).setStroke()
    tilePath.lineWidth = 4
    tilePath.stroke()
}

// 4 × 4 grid of week boxes: past = filled grey, done = cream, now = amber, future = outline
let cols = 4, rows = 4
let box: CGFloat = square ? 150 : 118, gap: CGFloat = square ? 58 : 46
let gridW = CGFloat(cols) * box + CGFloat(cols - 1) * gap
let ox = (size - gridW) / 2
let oy = (size - gridW) / 2
let states: [Int] = [2, 2, 2, 1,
                     2, 2, 1, 2,
                     3, 0, 0, 0,
                     0, 0, 0, 0]   // top-left first
for r in 0..<rows {
    for c in 0..<cols {
        let s = states[r * cols + c]
        let x = ox + CGFloat(c) * (box + gap)
        let y = size - oy - box - CGFloat(r) * (box + gap)
        let rect = NSRect(x: x, y: y, width: box, height: box)
        let p = NSBezierPath(rect: rect)
        switch s {
        case 2: color(0xf3f0e8).setFill(); p.fill()
        case 1: color(0x4a4741).setFill(); p.fill()
        case 3: color(0xe8b64c).setFill(); p.fill()
        default:
            color(0xf3f0e8, 0.35).setStroke()
            let o = NSBezierPath(rect: rect.insetBy(dx: 5, dy: 5))
            o.lineWidth = 10
            o.stroke()
        }
    }
}

NSGraphicsContext.restoreGraphicsState()
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: out))
print("wrote \(out)")
