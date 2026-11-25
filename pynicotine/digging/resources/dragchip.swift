// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Tiny native drag chip. GTK's outbound drag never produced a pasteboard item
// macOS targets accept, so this helper hands the file to AppKit directly:
// a small floating chip appears under the cursor and drags as a real
// public.file-url, exactly like a drag from Finder.
//
// usage: dragchip <path-to-file>

import AppKit

final class ChipView: NSView, NSDraggingSource {

    let fileURL: URL
    let icon: NSImage
    var dragBeganAt = Date.distantPast

    init(frame: NSRect, fileURL: URL) {
        self.fileURL = fileURL
        self.icon = NSWorkspace.shared.icon(forFile: fileURL.path)
        super.init(frame: frame)
        self.icon.size = NSSize(width: 32, height: 32)
    }

    required init?(coder: NSCoder) {
        fatalError("not used")
    }

    override func draw(_ dirtyRect: NSRect) {
        let background = NSBezierPath(roundedRect: bounds.insetBy(dx: 1.5, dy: 1.5), xRadius: 12, yRadius: 12)
        NSColor(calibratedWhite: 0.11, alpha: 0.97).setFill()
        background.fill()

        NSColor(calibratedWhite: 1.0, alpha: 0.14).setStroke()
        background.lineWidth = 1
        background.stroke()

        let iconRect = NSRect(x: 12, y: (bounds.height - 32) / 2, width: 32, height: 32)
        icon.draw(in: iconRect)

        let paragraph = NSMutableParagraphStyle()
        paragraph.lineBreakMode = .byTruncatingMiddle

        let attributes: [NSAttributedString.Key: Any] = [
            .foregroundColor: NSColor.white,
            .font: NSFont.systemFont(ofSize: 12, weight: .medium),
            .paragraphStyle: paragraph
        ]

        let textRect = NSRect(x: 52, y: (bounds.height - 16) / 2, width: bounds.width - 64, height: 16)
        (fileURL.lastPathComponent as NSString).draw(in: textRect, withAttributes: attributes)
    }

    override func mouseDown(with event: NSEvent) {
        let item = NSPasteboardItem()
        item.setString(fileURL.absoluteString, forType: .fileURL)

        let draggingItem = NSDraggingItem(pasteboardWriter: item)
        draggingItem.setDraggingFrame(bounds, contents: snapshot())

        dragBeganAt = Date()
        beginDraggingSession(with: [draggingItem], event: event, source: self)
    }

    func draggingSession(_ session: NSDraggingSession,
                         sourceOperationMaskFor context: NSDraggingContext) -> NSDragOperation {
        return .copy
    }

    func draggingSession(_ session: NSDraggingSession,
                         endedAt screenPoint: NSPoint,
                         operation: NSDragOperation) {
        let elapsed = Date().timeIntervalSince(dragBeganAt)

        FileHandle.standardError.write(Data("dragchip: drag ended after \(elapsed)s\n".utf8))

        // A synthesized drag can be refused immediately; leave the chip on
        // screen so a normal click-drag still works.
        if operation == [] && elapsed < 0.3 {
            return
        }

        NSApp.terminate(nil)
    }

    private func snapshot() -> NSImage {
        guard let rep = bitmapImageRepForCachingDisplay(in: bounds) else {
            return icon
        }

        cacheDisplay(in: bounds, to: rep)
        let image = NSImage(size: bounds.size)
        image.addRepresentation(rep)
        return image
    }
}

let arguments = CommandLine.arguments
let immediate = arguments.contains("--immediate")
let paths = arguments.dropFirst().filter { !$0.hasPrefix("--") }

guard let path = paths.first else {
    FileHandle.standardError.write(Data("usage: dragchip [--immediate] <file>\n".utf8))
    exit(2)
}

let fileURL = URL(fileURLWithPath: path)

guard FileManager.default.fileExists(atPath: fileURL.path) else {
    FileHandle.standardError.write(Data("dragchip: no such file\n".utf8))
    exit(3)
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)

let size = NSSize(width: 300, height: 56)
let mouse = NSEvent.mouseLocation
let origin = NSPoint(x: mouse.x - (size.width / 2), y: mouse.y - (size.height / 2))

let panel = NSPanel(
    contentRect: NSRect(origin: origin, size: size),
    styleMask: [.borderless, .nonactivatingPanel],
    backing: .buffered,
    defer: false
)

panel.level = .floating
panel.isOpaque = false
panel.backgroundColor = .clear
panel.hasShadow = true
panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
let chip = ChipView(frame: NSRect(origin: .zero, size: size), fileURL: fileURL)
panel.contentView = chip
panel.orderFrontRegardless()

if immediate {
    // The pointer is still down on the GTK side when the chip is created, so
    // start the drag ourselves instead of asking for a second gesture. The
    // chip stays usable if this is rejected.
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
        let location = panel.convertPoint(fromScreen: NSEvent.mouseLocation)

        if let event = NSEvent.mouseEvent(
            with: .leftMouseDown,
            location: location,
            modifierFlags: [],
            timestamp: ProcessInfo.processInfo.systemUptime,
            windowNumber: panel.windowNumber,
            context: nil,
            eventNumber: 0,
            clickCount: 1,
            pressure: 1.0
        ) {
            FileHandle.standardError.write(Data("dragchip: starting immediate drag\n".utf8))
            chip.mouseDown(with: event)
        }
    }
}

// Safety: never leave a ghost window behind
DispatchQueue.main.asyncAfter(deadline: .now() + 30) {
    NSApp.terminate(nil)
}

app.run()
