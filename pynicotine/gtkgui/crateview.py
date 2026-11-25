# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Crate tab: what was kept, where its stems are, and how to open the set."""

from __future__ import annotations

import subprocess
import sys

from pathlib import Path

from gi.repository import GLib
from gi.repository import Gtk

from pynicotine.digging.crate import STATUS_FAILED, STATUS_SCHEDULED, STATUS_SEPARATING
from pynicotine.digging.settings import DiggingSettings


STATUS_LABELS = {
    "kept": "downloaded",
    STATUS_SEPARATING: "separating…",
    STATUS_SCHEDULED: "Live set ready",
    "ready": "stems ready",
    STATUS_FAILED: "failed",
    "candidate": "candidate",
}


class CrateView:

    def __init__(self, window) -> None:

        self.window = window
        self.application = window.application
        self._signature = None
        self._timer_id = None

        self.page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0, visible=True)
        self.page.id = "crate"
        self.page.set_margin_start(12)
        self.page.set_margin_end(12)
        self.page.set_margin_top(12)
        self.page.set_margin_bottom(12)

        # Header bar content owned by this page (moved into the window header bar)
        self.toolbar_start_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, visible=True)
        title = Gtk.Label(label="Crate", visible=True)
        title.add_css_class("title-4")
        self.toolbar_start_content.append(title)

        self.summary_label = Gtk.Label(label="", visible=True)
        self.summary_label.add_css_class("dim-label")

        self.setup_button = Gtk.Button(label="Separation…", visible=True)
        self.setup_button.connect("clicked", self._on_setup_clicked)

        finish_button = Gtk.Button(label="Clear finished", visible=True)
        finish_button.connect("clicked", self._on_clear_finished_clicked)

        self.toolbar_end_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, visible=True)
        self.toolbar_end_content.append(self.summary_label)
        self.toolbar_end_content.append(self.setup_button)
        self.toolbar_end_content.append(finish_button)

        # Non-CSD fallback: the window moves these widgets in and out of this row
        self.toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, visible=True)
        toolbar_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, visible=True)
        toolbar_content.set_hexpand(True)
        spacer = Gtk.Box(hexpand=True, visible=True)
        toolbar_content.append(self.toolbar_start_content)
        toolbar_content.append(spacer)
        toolbar_content.append(self.toolbar_end_content)
        self.toolbar.append(toolbar_content)
        self.page.append(self.toolbar)

        scroller = Gtk.ScrolledWindow(vexpand=True, visible=True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.list_box = Gtk.ListBox(visible=True)
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.add_css_class("boxed-list")
        scroller.set_child(self.list_box)
        self.page.append(scroller)

        self._timer_id = GLib.timeout_add_seconds(2, self._tick)
        self.page.connect("destroy", self._on_destroy)
        self.refresh()

    # -- lifecycle --------------------------------------------------------

    def on_focus(self, *_args) -> None:
        self.refresh()

    def destroy(self) -> None:
        """Called by the main window when the tab is torn down."""

        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

        self.page = None

    def _on_destroy(self, *_args) -> None:

        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    def _tick(self) -> bool:

        if self.page is None:
            return False

        self.refresh()
        return True

    # -- data -------------------------------------------------------------

    def _load(self):

        settings = DiggingSettings.load()

        try:
            from pynicotine.digging.actions import crate_for

            crate = crate_for(settings)

        except OSError:
            return settings, []

        return settings, crate.tracks

    def refresh(self) -> None:

        settings, tracks = self._load()
        signature = tuple((track.id, track.status, len(track.stems), track.als_path) for track in tracks)

        if signature == self._signature:
            return

        self._signature = signature
        self._settings = settings

        while True:
            child = self.list_box.get_first_child()

            if child is None:
                break

            self.list_box.remove(child)

        ready = sum(1 for track in tracks if track.als_path)
        self.summary_label.set_text(f"{len(tracks)} kept · {ready} with Live sets")

        if not tracks:
            empty = Gtk.Label(label="Nothing kept yet — press Enter on a file, then Keep.",
                              xalign=0, visible=True)
            empty.add_css_class("dim-label")
            wire = Gtk.ListBoxRow(visible=True)
            wire.set_child(empty)
            self.list_box.append(wire)
            return

        for track in tracks:
            self.list_box.append(self._build_row(track))

    def _build_row(self, track) -> Gtk.ListBoxRow:

        row = Gtk.ListBoxRow(visible=True)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, visible=True)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(10)
        box.set_margin_end(10)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, visible=True)
        text_box.set_hexpand(True)

        name = Gtk.Label(label=track.filename or track.virtual_path, xalign=0, visible=True)
        name.set_ellipsize(3)
        text_box.append(name)

        detail_parts = [STATUS_LABELS.get(track.status, track.status)]

        if track.bpm:
            detail_parts.append(f"{track.bpm:.0f} BPM")

        if track.stems:
            detail_parts.append(", ".join(track.stems))

        if track.error:
            detail_parts.append(track.error[:80])

        detail = Gtk.Label(label=" · ".join(detail_parts), xalign=0, visible=True)
        detail.add_css_class("dim-label")
        detail.set_ellipsize(3)
        text_box.append(detail)

        box.append(text_box)

        if track.als_path:
            open_button = Gtk.Button(label="Open in Live", visible=True)
            open_button.add_css_class("suggested-action")
            open_button.connect("clicked", lambda *_args, t=track: self._open_set(t))
            box.append(open_button)

        if track.status != STATUS_SCHEDULED and not track.stems:
            separate_button = Gtk.Button(label="Separate now", visible=True)
            separate_button.connect("clicked", lambda *_args, t=track: self._separate(t))
            box.append(separate_button)

        reveal_button = Gtk.Button(label="Show file", visible=True)
        reveal_button.connect("clicked", lambda *_args, t=track: self._reveal(t))
        box.append(reveal_button)

        remove_button = Gtk.Button(icon_name="user-trash-symbolic", visible=True)
        remove_button.set_tooltip_text("Remove from the crate")
        remove_button.connect("clicked", lambda *_args, t=track: self._remove(t))
        box.append(remove_button)

        row.set_child(box)
        return row

    # -- actions ----------------------------------------------------------

    def _open_set(self, track) -> None:

        path = Path(track.als_path)

        if not path.is_file():
            self.summary_label.set_text("Live set is missing on disk")
            return

        from pynicotine.digging import ableton

        ableton.open_in_live(path, self._settings)

    def _separate(self, track) -> None:

        try:
            from pynicotine.digging.service import start_service

            start_service().kick(track)
            self.summary_label.set_text(f"separating {track.filename}…")

        except Exception as error:  # noqa: BLE001
            self.summary_label.set_text(f"could not start separation: {error}")

    def _reveal(self, track) -> None:

        path = track.local_path or str(
            self._settings.work_path / "downloads" / track.username / (track.filename or ""))

        if sys.platform == "darwin":
            subprocess.run(["open", "-R", path], check=False)
        else:
            subprocess.run(["open", str(Path(path).parent)], check=False)

    def _remove(self, track) -> None:

        from pynicotine.digging.actions import crate_for

        crate = crate_for(self._settings)
        crate.remove(track.id)
        self.refresh()

    def _on_clear_finished_clicked(self, *_args) -> None:

        from pynicotine.digging.actions import crate_for

        crate = crate_for(self._settings)

        for track in list(crate.tracks):
            if track.als_path:
                crate.remove(track.id)

        self.refresh()

    def _on_setup_clicked(self, *_args) -> None:

        from pynicotine.gtkgui.digsetup import SeparationSetup

        SeparationSetup(self.application, on_saved=lambda _settings: self.refresh()).present()
