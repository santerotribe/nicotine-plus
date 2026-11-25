# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Seamless native drag: an AppKit view laid over the GTK drag handle.

GTK's own drag never produced a pasteboard item macOS accepted, and a separate
chip window forces a second gesture. This puts a transparent NSView on top of
the GTK window (the GTK window *is* an NSWindow), positioned exactly over the
"Drag to Ableton" handle. A real mouse press inside it starts a native
NSDraggingSession, so press-drag-drop is one gesture.
"""

from __future__ import annotations

from gi.repository import GLib

try:
    import objc

    from AppKit import (
        NSDragOperationCopy,
        NSDraggingItem,
        NSDraggingSource,
        NSView,
        NSWorkspace,
    )
    from Foundation import NSURL

    AVAILABLE = True

except Exception:  # noqa: BLE001 - PyObjC is optional
    AVAILABLE = False
    NSView = object


if AVAILABLE:

    class _DragOverlay(NSView, NSDraggingSource):

        def initWithProvider_(self, provider):
            self = objc.super(_DragOverlay, self).initWithFrame_(((0, 0), (10, 10)))

            if self is None:
                return None

            self._provider = provider
            return self

        def isOpaque(self):
            return False

        def mouseDown_(self, event):
            path = self._provider()

            if not path:
                return

            try:
                from pynicotine.logfacility import log

                log.add(f"Digging: native drag started for {path}")

            except Exception:  # noqa: BLE001
                pass

            url = NSURL.fileURLWithPath_(str(path))
            item = NSDraggingItem.alloc().initWithPasteboardWriter_(url)
            icon = NSWorkspace.sharedWorkspace().iconForFile_(str(path))
            item.setDraggingFrame_contents_(self.bounds(), icon)
            self.beginDraggingSessionWithItems_event_source_([item], event, self)

        def draggingSession_sourceOperationMaskForDraggingContext_(self, _session, _context):
            return NSDragOperationCopy

        def draggingSession_endedAtPoint_operation_(self, _session, _point, _operation):
            return


class NativeDragOverlay:
    """Keeps an AppKit drag view aligned with a GTK widget."""

    def __init__(self, gtk_window, handle_widget, provider) -> None:
        self.gtk_window = gtk_window
        self.handle = handle_widget
        self.provider = provider
        self.view = None
        self.ns_window = None
        self._timer_id = None
        self._attach()
        self._timer_id = GLib.timeout_add(250, self._reposition)

    # -- setup ------------------------------------------------------------

    def _find_ns_window(self):
        from AppKit import NSApplication

        title = self.gtk_window.get_title()
        candidates = list(NSApplication.sharedApplication().windows())

        for window in candidates:
            try:
                if title and str(window.title()) == title:
                    return window

            except Exception:  # noqa: BLE001
                continue

        return None

    def _attach(self) -> None:

        self.ns_window = self._find_ns_window()

        if self.ns_window is None:
            return

        content = self.ns_window.contentView()

        if content is None:
            return

        self.view = _DragOverlay.alloc().initWithProvider_(self.provider)
        content.addSubview_(self.view)
        self._reposition()

    # -- geometry ---------------------------------------------------------

    def _reposition(self) -> bool:

        if self.view is None or self.ns_window is None or not self.handle.get_mapped():
            return True

        try:
            ok, rect = self.handle.compute_bounds(self.gtk_window)
            content = self.ns_window.contentView()
            height = content.bounds().size.height
            x = rect.origin.x
            y = height - rect.origin.y - rect.size.height
            self.view.setFrame_(((x, y), (rect.size.width, rect.size.height)))
            self.view.setHidden_(False)

        except Exception:  # noqa: BLE001 - geometry is cosmetic
            pass

        return True

    # -- teardown ---------------------------------------------------------

    def detach(self) -> None:

        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

        try:
            if self.view is not None:
                self.view.removeFromSuperview()

        except Exception:  # noqa: BLE001
            pass

        self.view = None


def attach(gtk_window, handle_widget, provider) -> NativeDragOverlay | None:
    """Best-effort: return an overlay, or None when PyObjC is unavailable."""

    if not AVAILABLE:
        return None

    try:
        overlay = NativeDragOverlay(gtk_window, handle_widget, provider)

    except Exception:  # noqa: BLE001
        return None

    if overlay.view is None:
        return None

    return overlay
