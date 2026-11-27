// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import AppKit
import SwiftUI

/// A real AppKit drag session for a file URL.
///
/// GTK never produced a payload Ableton accepted; AppKit does. The view is
/// transparent and sized by SwiftUI; press and drag anywhere in it to start a
/// file drag, which is what the transport's handle and the artwork use.
struct DragOutHandle: NSViewRepresentable {

    let fileURL: URL?
    var onDragBegan: (() -> Void)?
    var onDragEnded: (() -> Void)?

    func makeNSView(context: Context) -> DragSourceView {
        let view = DragSourceView()
        view.onDragBegan = onDragBegan
        view.onDragEnded = onDragEnded
        return view
    }

    func updateNSView(_ view: DragSourceView, context: Context) {
        view.fileURL = fileURL
        view.onDragBegan = onDragBegan
        view.onDragEnded = onDragEnded
    }
}

final class DragSourceView: NSView, NSDraggingSource {

    var fileURL: URL?
    var onDragBegan: (() -> Void)?
    var onDragEnded: (() -> Void)?

    private var mouseDownPoint: NSPoint?

    override var isFlipped: Bool { true }

    override func mouseDown(with event: NSEvent) {
        mouseDownPoint = convert(event.locationInWindow, from: nil)
    }

    override func mouseDragged(with event: NSEvent) {

        guard let start = mouseDownPoint, let fileURL,
              FileManager.default.fileExists(atPath: fileURL.path) else {
            return
        }

        let current = convert(event.locationInWindow, from: nil)

        guard abs(current.x - start.x) + abs(current.y - start.y) > 3 else { return }

        mouseDownPoint = nil
        onDragBegan?()

        let item = NSDraggingItem(pasteboardWriter: fileURL as NSURL)
        let image = NSWorkspace.shared.icon(forFile: fileURL.path)

        item.setDraggingFrame(
            NSRect(x: start.x - 16, y: start.y - 16, width: 32, height: 32),
            contents: image
        )

        beginDraggingSession(with: [item], event: event, source: self)
    }

    func draggingSession(
        _ session: NSDraggingSession, sourceOperationMaskFor context: NSDraggingContext
    ) -> NSDragOperation {
        .copy
    }

    func draggingSession(_ session: NSDraggingSession, endedAt screenPoint: NSPoint,
                         operation: NSDragOperation) {
        onDragEnded?()
    }
}
