# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Seamless native drag over the GTK drag handle.

GTK's own drag never produced a pasteboard item macOS targets accepted, and a
floating chip forces a second gesture. Putting an NSView inside the GTK window
does not work either: the GTK NSWindow intercepts mouse events before subviews
see them.

So this uses a tiny, fully transparent child NSWindow positioned exactly over
the "Drag to Ableton" handle. Child windows receive their own mouse events, so a
real click there starts a real NSDraggingSession with the file's NSURL. Nothing
appears on screen: press the handle, drag into Ableton, release.
"""

from __future__ import annotations

from gi.repository import GLib

try:
    import objc

    from AppKit import (
        NSBackingStoreBuffered,
        NSColor,
        NSDragOperationCopy,
        NSDraggingItem,
        NSDraggingSource,
        NSView,
        NSWindow,
        NSWindowAbove,
        NSWorkspace,
    )
    from Foundation import NSMakeRect, NSURL

    AVAILABLE = True

except Exception:  # noqa: BLE001 - PyObjC is optional
    AVAILABLE = False
    NSView = object


if AVAILABLE:

    class _DragOverlay(NSView, NSDraggingSource):

        def initWithProvider_(self, provider):
            self = objc.super(_DragOverlay, self).initWithFrame_(NSMakeRect(0, 0, 10, 10))

            if self is None:
                return None

            self._provider = provider
            return self

        def isOpaque(self):
            return False

        def acceptsFirstMouse_(self, _event):
            return True

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
    """A transparent child NSWindow aligned with a GTK widget."""

    def __init__(self, gtk_window, handle_widget, provider) -> None:
        self.gtk_window = gtk_window
        self.handle = handle_widget
        self.provider = provider
        self.view = None
        self.ns_window = None
        self.child = None
        self._timer_id = None
        self._attach()
        self._timer_id = GLib.timeout_add(200, self._reposition)

    # -- setup ------------------------------------------------------------

    def _find_ns_window(self):
        from AppKit import NSApplication

        title = self.gtk_window.get_title()

        for window in list(NSApplication.sharedApplication().windows()):
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

        self.view = _DragOverlay.alloc().initWithProvider_(self.provider)

        self.child = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 10, 10), 0, NSBackingStoreBuffered, False
        )
        self.child.setOpaque_(False)
        self.child.setBackgroundColor_(NSColor.clearColor())
        self.child.setHasShadow_(False)
        self.child.setIgnoresMouseEvents_(False)
        self.child.setReleasedWhenClosed_(False)
        self.child.setLevel_(self.ns_window.level())
        self.child.setContentView_(self.view)
        try:
            self.ns_window.addChildWindow_ordered_(self.child, NSWindowAbove)
            self.child.orderFront_(None)

        except Exception as error:  # noqa: BLE001
            from pynicotine.logfacility import log

            log.add(f"Digging: native drag overlay could not attach: {error}")
            self.child = None
            return

        self._reposition()

    # -- geometry ---------------------------------------------------------

    def _reposition(self) -> bool:

        if self.child is None or self.ns_window is None:
            return True

        if not self.gtk_window.get_visible() or not self.handle.get_mapped():
            self.child.orderOut_(None)
            return True

        try:
            if not self.gtk_window.is_active():
                # Do not leave an invisible click-catcher floating over other apps
                self.child.orderOut_(None)
                return True

        except AttributeError:
            pass

        try:
            ok, rect = self.handle.compute_bounds(self.gtk_window)

            if not ok or rect.size.width < 2:
                self.child.orderOut_(None)
                return True

            content = self.ns_window.contentView()
            height = content.bounds().size.height
            frame = self.ns_window.frame()

            # NSView has no convertRectToScreen in this PyObjC; content-local
            # coordinates equal window coordinates, so offset by the window frame.
            screen = NSMakeRect(
                frame.origin.x + rect.origin.x,
                frame.origin.y + height - rect.origin.y - rect.size.height,
                rect.size.width,
                rect.size.height,
            )
            self.child.setFrame_display_(screen, True)
            self.child.orderFront_(None)

        except Exception:  # noqa: BLE001 - geometry is cosmetic
            pass

        return True

    # -- teardown ---------------------------------------------------------

    def detach(self) -> None:

        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

        try:
            if self.child is not None:
                self.ns_window.removeChildWindow_(self.child)
                self.child.orderOut_(None)
                self.child.close()

        except Exception:  # noqa: BLE001
            pass

        self.child = None
        self.view = None


def attach(gtk_window, handle_widget, provider) -> NativeDragOverlay | None:
    """Best-effort: return an overlay, or None when PyObjC is unavailable."""

    if not AVAILABLE:
        return None

    try:
        overlay = NativeDragOverlay(gtk_window, handle_widget, provider)

    except Exception:  # noqa: BLE001
        return None

    if overlay.child is None:
        return None

    return overlay
