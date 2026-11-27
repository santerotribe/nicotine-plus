// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import AppKit
import SwiftUI

/// A full-bleed window with no titlebar: the app draws its own chrome, and the
/// window still has to be draggable from that chrome.
struct WindowConfigurator: NSViewRepresentable {

    func makeNSView(context: Context) -> NSView {
        let view = NSView()

        DispatchQueue.main.async {
            guard let window = view.window else { return }

            window.titlebarAppearsTransparent = true
            window.titleVisibility = .hidden
            window.styleMask.insert(.fullSizeContentView)
            window.isMovableByWindowBackground = true
            window.backgroundColor = NSColor(Theme.bgCanvas)
        }

        return view
    }

    func updateNSView(_ view: NSView, context: Context) {}
}
