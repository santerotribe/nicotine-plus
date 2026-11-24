# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Dig player: audition a browsed track with a waveform and transport.

Flow for one track:

1. match the filename against iTunes (fast, 30 s preview) while the UI shows a
   matching state
2. decode the preview and play it with a full waveform
3. run a YouTube lookup in the background; when it finds a better full-length
   match, swap the player to that stream in place

Peer fetching (the fallback for unreleased material) plugs into load(...) later.
"""

from __future__ import annotations

import threading

from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import Gtk
from gi.repository import Pango

from pynicotine.digging.audition import match
from pynicotine.digging.audition.player import Player, PlayerError
from pynicotine.gtkgui.application import GTK_API_VERSION

WINDOW_TITLE = "Dig"
DEFAULT_WIDTH = 780
DEFAULT_HEIGHT = 260


def _append(container, child) -> None:
    if GTK_API_VERSION >= 4:
        container.append(child)  # pylint: disable=no-member
    else:
        container.pack_start(child, False, False, 0)


class DigPlayer:

    def __init__(self, application) -> None:

        self.application = application
        self.player = Player()
        self.track_name = ""
        self.candidate = None
        self.source = None
        self._timer_id = None
        self._token = 0
        self.state_callback = None   # called with (playing: bool) on transport changes

        kwargs = {
            "title": WINDOW_TITLE,
            "default_width": DEFAULT_WIDTH,
            "default_height": DEFAULT_HEIGHT,
            "resizable": True,
        }
        gtk_app = getattr(application, "_instance", None)

        if isinstance(gtk_app, Gtk.Application):
            kwargs["application"] = gtk_app

        self.window = Gtk.Window(**kwargs)
        self.window.connect("destroy", self._on_destroy)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, visible=True)
        outer.set_margin_top(14)
        outer.set_margin_bottom(14)
        outer.set_margin_start(16)
        outer.set_margin_end(16)

        self.title_label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, visible=True)
        self.title_label.add_css_class("title-4")
        self.match_label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, visible=True)
        self.match_label.add_css_class("dim-label")

        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, visible=True)
        _append(header, self.title_label)
        _append(header, self.match_label)
        _append(outer, header)

        self.waveform = Gtk.DrawingArea(visible=True)
        self.waveform.set_content_height(110)
        self.waveform.set_draw_func(self._draw_waveform)
        self.waveform.set_cursor_from_name("pointer")

        click = Gtk.GestureClick()
        click.connect("pressed", self._on_waveform_click)
        self.waveform.add_controller(click)

        drag = Gtk.GestureDrag()
        drag.connect("drag-update", self._on_waveform_drag)
        self.waveform.add_controller(drag)

        drag_source = Gtk.DragSource(actions=Gdk.DragAction.COPY)
        drag_source.connect("prepare", self._on_drag_prepare)
        drag_source.connect("drag-begin", self._on_drag_begin)
        drag_source.connect("drag-end", self._on_drag_end)
        self.waveform.add_controller(drag_source)
        self.drag_source = drag_source

        _append(outer, self.waveform)

        self.hint_label = Gtk.Label(label="drag the waveform into Ableton", xalign=0, visible=True)
        self.hint_label.add_css_class("dim-label")
        _append(outer, self.hint_label)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, visible=True)

        self.play_button = Gtk.Button(label="▶", width_request=56, visible=True)
        self.play_button.connect("clicked", self._on_play_clicked)
        self.seek_back_button = Gtk.Button(label="−10s", visible=True)
        self.seek_back_button.connect("clicked", lambda *_args: self._seek_relative(-10))
        self.seek_forward_button = Gtk.Button(label="+10s", visible=True)
        self.seek_forward_button.connect("clicked", lambda *_args: self._seek_relative(10))

        self.position_label = Gtk.Label(label="0:00 / 0:00", visible=True)

        self.volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.01)
        self.volume.set_value(0.7)
        self.volume.set_size_request(120, -1)
        self.volume.set_draw_value(False)
        self.volume.set_visible(True)
        self.volume.connect("value-changed", self._on_volume_changed)

        self.keep_button = Gtk.Button(label="Keep + separate", visible=True)
        self.keep_button.connect("clicked", self._on_keep_clicked)

        _append(controls, self.play_button)
        _append(controls, self.seek_back_button)
        _append(controls, self.seek_forward_button)
        _append(controls, self.position_label)
        _append(controls, Gtk.Box(hexpand=True, visible=True))
        _append(controls, self.volume)
        _append(controls, self.keep_button)
        _append(outer, controls)

        bottom_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, visible=True)
        self.status_label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, visible=True)
        self.status_label.add_css_class("dim-label")
        self.status_label.set_hexpand(True)
        self.export_button = Gtk.Button(label="Reveal file", visible=True)
        self.export_button.connect("clicked", self._on_export_clicked)
        _append(bottom_row, self.status_label)
        _append(bottom_row, self.export_button)
        _append(outer, bottom_row)

        if GTK_API_VERSION >= 4:
            self.window.set_child(outer)  # pylint: disable=no-member
        else:
            self.window.add(outer)

        self.player.set_finish_callback(lambda: GLib.idle_add(self._on_finished))

    # -- public API -------------------------------------------------------

    def present(self) -> None:
        self.window.present()

    def load(self, filename: str, duration_hint: float = 0.0, source_path: str = "",
             source=None) -> None:
        """Start auditioning a filename. Safe to call repeatedly."""

        self._token += 1
        token = self._token

        self.track_name = filename
        self.source = source
        self.candidate = None
        self.player.stop()

        self.title_label.set_text(filename)
        self.match_label.set_text("")
        self.status_label.set_text("matching…")
        self.play_button.set_label("▶")
        self._update_labels()
        self.present()

        if source_path:
            self.status_label.set_text("loading local file…")
            threading.Thread(target=self._load_local, args=(source_path, token), daemon=True).start()
            return

        threading.Thread(target=self._match_fast, args=(filename, duration_hint, token), daemon=True).start()

    # -- matching ---------------------------------------------------------

    def _load_local(self, path: str, token: int) -> None:

        try:
            duration = self.player.load(path)

        except PlayerError as error:
            GLib.idle_add(self._fail, str(error), token)
            return

        GLib.idle_add(self._on_loaded, None, "local file", path, token, duration)

    def _match_fast(self, filename: str, duration: float, token: int) -> None:

        try:
            candidates = match.resolve(filename, expected_duration=duration, sources=("itunes",))

        except Exception as error:  # noqa: BLE001 - matching must never crash the player
            GLib.idle_add(self._fail, f"match failed: {error}", token)
            return

        if token != self._token:
            return

        if candidates:
            GLib.idle_add(self._play_candidate, candidates[0], token)
        else:
            GLib.idle_add(self._status, "no iTunes match — asking YouTube…", token)

        threading.Thread(target=self._match_full, args=(filename, duration, token), daemon=True).start()

    def _match_full(self, filename: str, duration: float, token: int) -> None:

        try:
            candidates = match.resolve(filename, expected_duration=duration)

        except Exception:  # noqa: BLE001
            return

        if token != self._token:
            return

        if not candidates:
            GLib.idle_add(self._fail, "no catalogue match — peer fetch is the fallback", token)
            return

        best = candidates[0]

        if best.source != "youtube":
            return

        current = self.candidate

        if current is not None and best.score < current.score + 0.05:
            return

        GLib.idle_add(self._play_candidate, best, token)

    def _play_candidate(self, candidate, token: int) -> bool:

        if token != self._token:
            return False

        self.status_label.set_text(f"loading {candidate.source} audio…")

        def work() -> None:
            try:
                if candidate.source == "youtube":
                    url = match.youtube_stream(candidate)
                else:
                    url = candidate.preview_url

                duration = self.player.load(url)

            except (PlayerError, RuntimeError, OSError) as error:
                GLib.idle_add(self._fail, str(error), token)
                return

            GLib.idle_add(self._on_loaded, candidate, candidate.label,
                          f"{candidate.source} · {candidate.score:.2f} match", token, duration)

        threading.Thread(target=work, daemon=True).start()
        return False

    # -- playback state ---------------------------------------------------

    def _on_loaded(self, candidate, label: str, detail: str, token: int, duration: float) -> bool:

        if token != self._token:
            return False

        self.candidate = candidate
        self.match_label.set_text(f"{label}  ({detail}, {_clock(duration)})")
        self.status_label.set_text("ready")
        self._update_labels()
        self.waveform.queue_draw()
        self.player.play()
        self.play_button.set_label("⏸")
        self._start_timer()
        self._notify_state()
        return False

    def _fail(self, message: str, token: int) -> bool:

        if token != self._token:
            return False

        self.status_label.set_text(message[:220])
        self.match_label.set_text("no playable source — peer fetch is the fallback")
        return False

    def _status(self, message: str, token: int) -> bool:

        if token == self._token:
            self.status_label.set_text(message)

        return False

    def _on_finished(self) -> bool:
        self.play_button.set_label("▶")
        self._stop_timer()
        self._update_labels()
        self._notify_state()
        return False

    def _on_destroy(self, *_args) -> None:
        self.player.stop()
        self._stop_timer()
        application = self.application
        application.dig_player = None

    def toggle(self) -> None:
        """Play or pause whatever is loaded (used by Enter and row buttons)."""

        if self.player.duration:
            self._on_play_clicked()

    def _notify_state(self) -> None:

        if self.state_callback:
            self.state_callback(self.player.is_playing)

    def _on_play_clicked(self, *_args) -> None:

        try:
            if self.player.is_playing:
                self.player.pause()
                self.play_button.set_label("▶")
                self._stop_timer()

            else:
                self.player.play()
                self.play_button.set_label("⏸")
                self._start_timer()

        except PlayerError as error:
            self.status_label.set_text(str(error))

        self._notify_state()

    def _seek_relative(self, delta: float) -> None:
        self.player.skip(delta)
        self._update_labels()
        self.waveform.queue_draw()

    def _on_volume_changed(self, scale) -> None:
        self.player.volume = scale.get_value()

    def _on_keep_clicked(self, *_args) -> None:

        if self.source is None:
            self.status_label.set_text("nothing to keep (no browsed file attached)")
            return

        try:
            from pynicotine.core import core
            from pynicotine.digging.actions import keep_source

            track = keep_source(core, self.source)

        except Exception as error:  # noqa: BLE001 - surface the reason in the UI
            self.status_label.set_text(f"keep failed: {error}")
            return

        self.status_label.set_text(f"kept {track.filename} — downloading and queueing separation")

    # -- export and drag-to-DAW ------------------------------------------

    def _export_dir(self):

        from pynicotine.digging.settings import DiggingSettings

        folder = DiggingSettings.load().work_path / "exports"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _export_name(self) -> str:

        from pynicotine.digging.export import safe_name

        if self.candidate is not None:
            label = self.candidate.label
            source = self.candidate.source
        else:
            label = self.track_name
            source = "local"

        return f"{safe_name(label)} [{source}].wav"

    def export_audio(self):
        """Write the currently loaded audio to a WAV that a DAW can accept."""

        audio = self.player.audio

        if audio is None or len(audio) == 0:
            return None

        path = self._export_dir() / self._export_name()

        if path.is_file() and path.stat().st_size > 1024:
            return path

        from pynicotine.digging.export import write_wav

        return write_wav(audio, path, self.player.sample_rate)

    def _on_drag_prepare(self, _source, _x, _y):

        path = self.export_audio()

        if path is None:
            return None

        gfile = Gio.File.new_for_path(str(path))
        providers = [Gdk.ContentProvider.new_for_value(Gdk.FileList.new_from_array([gfile]))]

        try:
            uri = GLib.Bytes.new(f"{gfile.get_uri()}\r\n".encode())
            providers.append(Gdk.ContentProvider.new_for_bytes("text/uri-list", uri))

        except Exception:  # noqa: BLE001 - uri-list support is a bonus
            pass

        return Gdk.ContentProvider.new_union(providers)

    def _on_drag_begin(self, *_args) -> None:
        self.status_label.set_text("drag into Ableton to import")

    def _on_drag_end(self, *_args) -> None:
        self.status_label.set_text("ready")

    def _on_export_clicked(self, *_args) -> None:

        path = self.export_audio()

        if path is None:
            self.status_label.set_text("nothing loaded to export")
            return

        import subprocess
        import sys

        try:
            if sys.platform == "darwin":
                subprocess.run(["open", "-R", str(path)], check=False)
            else:
                subprocess.run(["open", str(path.parent)], check=False)

        except OSError as error:
            self.status_label.set_text(str(error))
            return

        self.status_label.set_text(f"exported {path.name}")

    # -- waveform interaction --------------------------------------------

    def _fraction_at(self, x: float) -> float:
        width = max(1, self.waveform.get_width())
        return max(0.0, min(1.0, x / width))

    def _on_waveform_click(self, _gesture, _n_press, x, _y) -> None:
        self._seek_fraction(self._fraction_at(x))

    def _on_waveform_drag(self, _gesture, _offset_x, x) -> None:
        self._seek_fraction(self._fraction_at(x))

    def _seek_fraction(self, fraction: float) -> None:

        if self.player.duration:
            self.player.seek(fraction * self.player.duration)
            self._update_labels()
            self.waveform.queue_draw()

    # -- rendering --------------------------------------------------------

    def _draw_waveform(self, _area, context, width, height) -> None:
        """SoundCloud-style waveform: grey unplayed bars, orange played bars."""

        context.set_source_rgb(0.07, 0.07, 0.08)
        context.rectangle(0, 0, width, height)
        context.fill()

        peaks = self.player.peaks(int(max(1, width / 3)))
        center = height / 2
        duration = self.player.duration
        played = (self.player.position / duration) if duration else 0.0
        played = max(0.0, min(1.0, played))

        if peaks:
            step = width / len(peaks)
            bar_width = max(1.0, step * 0.55)
            split = played * len(peaks)

            for index, value in enumerate(peaks):
                bar = max(1.5, value * (height * 0.86))
                x = index * step

                if index < split:
                    context.set_source_rgb(0.996, 0.333, 0.0)   # SoundCloud orange
                else:
                    context.set_source_rgb(0.42, 0.42, 0.45)

                context.rectangle(x, center - (bar / 2), bar_width, bar)

            context.fill()

        if duration:
            context.set_source_rgb(0.95, 0.95, 0.95)
            context.rectangle((played * width) - 1, 0, 1.5, height)
            context.fill()

    def _start_timer(self) -> None:

        if self._timer_id is not None:
            return

        self._timer_id = GLib.timeout_add(50, self._tick)

    def _stop_timer(self) -> None:

        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    def _tick(self) -> bool:

        self._update_labels()
        self.waveform.queue_draw()

        if not self.player.is_playing:
            self._timer_id = None
            return False

        return True

    def _update_labels(self) -> None:
        self.position_label.set_text(f"{_clock(self.player.position)} / {_clock(self.player.duration)}")


def _clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def open_dig_player(application) -> DigPlayer:
    """Return the shared player window, creating it on first use."""

    player = getattr(application, "dig_player", None)

    if player is None:
        player = DigPlayer(application)
        application.dig_player = player

    return player
