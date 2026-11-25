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
from pynicotine.digging.settings import renderer_available
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
        self.peer = None
        self._peer_duration_hint = 0.0
        self._peer_extend_at = 0.0
        self._peer_resume_at = 0.0
        self._peer_last_bytes = 0
        self._drag_start_x = 0.0
        self._playing_peer = False
        self._status_until = 0.0
        self._peer_switch_pending = False
        self._peer_switch_bytes = 0
        self._peer_loaded_at = 0.0
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
        drag.connect("drag-begin", self._on_waveform_drag_begin)
        drag.connect("drag-update", self._on_waveform_drag)
        drag.connect("drag-end", self._on_waveform_drag_end)
        self.waveform.add_controller(drag)

        _append(outer, self.waveform)

        hint_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, visible=True)

        # Dragging out to a DAW needs its own handle: a DragSource on the
        # waveform would steal the drag and break scrubbing.
        self.drag_handle = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, visible=True)
        self.drag_handle.set_cursor_from_name("grab")
        self.drag_handle.set_tooltip_text("Drag into Ableton to import the audio")
        if GTK_API_VERSION >= 4:
            handle_icon = Gtk.Image.new_from_icon_name("document-send-symbolic")
        else:
            handle_icon = Gtk.Image.new_from_icon_name("document-send-symbolic", Gtk.IconSize.BUTTON)

        handle_icon.set_visible(True)
        handle_label = Gtk.Label(label="Drag to Ableton", visible=True)
        _append(self.drag_handle, handle_icon)
        _append(self.drag_handle, handle_label)

        drag_source = Gtk.DragSource(actions=Gdk.DragAction.COPY)
        drag_source.connect("prepare", self._on_drag_prepare)
        drag_source.connect("drag-begin", self._on_drag_begin)
        drag_source.connect("drag-end", self._on_drag_end)
        self.drag_handle.add_controller(drag_source)
        self.drag_source = drag_source

        self.hint_label = Gtk.Label(label="click or drag the waveform to scrub", xalign=0, visible=True)
        self.hint_label.add_css_class("dim-label")

        _append(hint_row, self.drag_handle)
        _append(hint_row, self.hint_label)
        _append(outer, hint_row)

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

        self.setup_button = Gtk.Button(label="Separation…", visible=True)
        self.setup_button.set_tooltip_text("Choose where stems are separated")
        self.setup_button.connect("clicked", self._on_setup_clicked)

        self.keep_button = Gtk.Button(label="Keep + separate", visible=True)
        self.keep_button.connect("clicked", self._on_keep_clicked)

        _append(controls, self.play_button)
        _append(controls, self.seek_back_button)
        _append(controls, self.seek_forward_button)
        _append(controls, self.position_label)
        _append(controls, Gtk.Box(hexpand=True, visible=True))
        _append(controls, self.volume)
        _append(controls, self.setup_button)
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

        # Housekeeping runs off the main thread: it touches transfers and disk
        threading.Thread(target=self._sweep_previews, daemon=True).start()

        try:
            from pynicotine.digging.service import start_service

            start_service()

        except Exception as error:  # noqa: BLE001 - never block the player
            from pynicotine.logfacility import log

            log.add(f"Digging: pipeline service unavailable: {error}")

    # -- public API -------------------------------------------------------

    def _sweep_previews(self) -> None:
        """Drop abandoned preview transfers and stale preview files."""

        try:
            from pynicotine.core import core
            from pynicotine.digging.maintenance import sweep
            from pynicotine.logfacility import log

            report = sweep(core=core)

            if report.transfers_removed or report.files_removed or report.cache_evicted:
                log.add(f"Digging: cleaned up {report.transfers_removed} preview transfers, "
                        f"{report.files_removed} files ({report.bytes_freed / (1024 * 1024):.1f} MB)")

        except Exception as error:  # noqa: BLE001 - housekeeping is best effort
            from pynicotine.logfacility import log

            log.add(f"Digging: cleanup failed: {error}")

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

        self._cancel_peer()
        self._playing_peer = False
        self._peer_duration_hint = float(duration_hint or 0.0)

        if source_path:
            self.status_label.set_text("loading local file…")
            threading.Thread(target=self._load_local, args=(source_path, token), daemon=True).start()
            return

        # The real file matters more than a catalogue stand-in: start fetching it
        if self.source is not None:
            self._start_peer(token)

        threading.Thread(target=self._match_fast, args=(filename, duration_hint, token), daemon=True).start()

    # -- peer preview -----------------------------------------------------

    def _start_peer(self, token: int) -> None:

        from pynicotine.digging.audition.peer import PeerPreview
        from pynicotine.digging.settings import DiggingSettings

        try:
            settings = DiggingSettings.load()
            cache_dir = settings.work_path / "previews"

            peer = PeerPreview(
                username=self.source.username,
                virtual_path=self.source.virtual_path,
                filename=self.source.filename,
                size=self.source.size,
                attributes=self.source.attributes,
                cache_dir=cache_dir,
            )
            peer.start(
                on_update=lambda preview: GLib.idle_add(self._on_peer_update, preview, token),
                on_audio_ready=lambda preview: GLib.idle_add(self._on_peer_audio, preview, token),
            )

        except Exception as error:  # noqa: BLE001 - catalogue path must survive
            from pynicotine.logfacility import log

            log.add(f"Digging: peer preview request failed: {error}")
            self.status_label.set_text(f"peer unavailable: {error}")
            return

        self.peer = peer
        self.status_label.set_text("asking the peer for the real file…")

    def _cancel_peer(self) -> None:

        peer = self.peer

        if peer is not None:
            peer.cancel()

        self.peer = None

    def _on_peer_update(self, preview, token: int) -> bool:

        if token != self._token:
            return False

        if not self.player.is_playing and preview.error:
            self.status_label.set_text(f"peer: {preview.error}")

        elif not self._playing_peer and not self.player.is_playing:
            self.status_label.set_text(f"peer: {preview.status_text}")

        return False

    def _on_peer_audio(self, preview, token: int) -> bool:

        if token != self._token or not preview.partial_path:
            return False

        if self._playing_peer:
            return False

        resume_at = self.player.position if self.player.duration else 0.0
        hint = self._peer_duration_hint or preview.size / (128 * 1000 / 8) or 0.0
        path = preview.partial_path

        if self.player.duration > 0:
            # Something is already playing (likely the catalogue preview): swap
            # sources underneath it so the listener hears no gap or click.
            self._set_status("switching to the peer's file…", sticky_seconds=5)
            threading.Thread(
                target=self._preload_and_adopt, args=(path, hint, resume_at, token), daemon=True
            ).start()
            return False

        try:
            self.player.load_stream(path, duration_hint=hint, start=resume_at)

        except PlayerError as error:
            self.status_label.set_text(f"peer file unreadable: {error}")
            return False

        self._peer_started(hint)
        return False

    def _preload_and_adopt(self, path: str, hint: float, resume_at: float, token: int) -> None:
        """Buffer the peer file while the catalogue plays, then crossfade over."""

        import time as _time

        try:
            buffer, decoder = self.player.preload_stream(path, duration_hint=hint, start=resume_at)

        except (PlayerError, OSError) as error:
            GLib.idle_add(self._fail, f"peer file unreadable: {error}", token)
            return

        deadline = _time.monotonic() + 6.0

        while _time.monotonic() < deadline:
            if token != self._token:
                decoder.cancel()
                return

            if buffer.frames >= int(1.0 * self.player.sample_rate):
                break

            # A failed or empty decode must not replace working playback
            if buffer.done:
                break

            _time.sleep(0.05)

        if buffer.frames <= 0:
            decoder.cancel()
            GLib.idle_add(self._defer_peer_switch, token)
            return

        GLib.idle_add(self._finish_adopt, buffer, decoder, hint, token)

    def _defer_peer_switch(self, token: int) -> bool:

        if token != self._token:
            return False

        self._peer_switch_pending = True
        self._set_status("waiting for the peer to send audio…", sticky_seconds=6)
        return False

    def _finish_adopt(self, buffer, decoder, hint: float, token: int) -> bool:

        if token != self._token:
            decoder.cancel()
            return False

        was_playing = self.player.is_playing
        position = self.player.position

        try:
            self.player.adopt(buffer, decoder, start=position, duration_hint=hint,
                              fade_seconds=0.25)

        except Exception as error:  # noqa: BLE001
            self.status_label.set_text(f"switch failed: {error}")
            return False

        self._peer_started(hint)

        if not was_playing:
            self.player.pause()

        return False

    def _peer_started(self, hint: float) -> None:

        import time as _time

        self._playing_peer = True
        self._peer_loaded_at = _time.monotonic()
        self.player.play()
        self.play_button.set_label("⏸")
        self._start_timer()
        self._notify_state()
        self._set_status("playing the peer's file (exact audio)", sticky_seconds=5)

        if self.candidate is not None:
            self.match_label.set_text(f"{self.candidate.label}  (catalogue match in background)")

    def _maybe_retry_peer_switch(self) -> None:
        """Adopt the peer file once it has actually produced audio."""

        peer = self.peer

        if not self._peer_switch_pending or self._playing_peer or peer is None:
            return

        if not peer.partial_path or peer.bytes <= self._peer_switch_bytes:
            return

        import time as _time

        now = _time.monotonic()

        if now - getattr(self, "_peer_switch_at", 0.0) < 2.0:
            return

        self._peer_switch_at = now
        self._peer_switch_bytes = peer.bytes
        self._peer_switch_pending = False
        self._on_peer_audio(peer, self._token)

    def _maybe_resume_peer(self) -> None:
        """If the growing peer file stalled playback, pick it up again."""

        peer = self.peer

        if peer is None or not self._playing_peer or self.player.is_playing:
            return

        import time as _time

        now = _time.monotonic()

        if now - getattr(self, "_peer_resume_at", 0.0) < 1.5:
            return

        if peer.bytes <= getattr(self, "_peer_last_bytes", 0):
            return

        if peer.bytes >= peer.size > 0:
            return

        self._peer_resume_at = now
        self._peer_last_bytes = peer.bytes

        try:
            self.player.load_stream(peer.partial_path, duration_hint=self.player.duration or self._peer_duration_hint,
                                    start=self.player.position)

        except (PlayerError, OSError):
            return

        self.player.play()
        self.play_button.set_label("⏸")
        self._start_timer()
        self._notify_state()

    def _maybe_extend_peer(self) -> None:
        """Re-open the growing partial file when playback reaches decoded audio."""

        peer = self.peer

        if not self._playing_peer or peer is None or not peer.partial_path:
            return

        import time as _time

        now = _time.monotonic()

        # Give a freshly opened decoder time to produce audio: without this the
        # "playhead is at the edge" check fires immediately after every seek and
        # restarts ffmpeg in a loop.
        if now - max(self._peer_extend_at, self._peer_loaded_at) < 3.0:
            return

        buffer = getattr(self.player, "_buffer", None)

        if buffer is None or buffer.frames < int(1.0 * self.player.sample_rate):
            return

        if buffer.done:
            return

        hint = self.player.duration
        decoded = self.player.buffered_fraction * hint

        if hint and self.player.position > decoded - 1.0 and self.player.position < hint - 0.5:
            self._peer_extend_at = now
            self.player.load_stream(peer.partial_path, duration_hint=hint, start=self.player.position)
            self._peer_loaded_at = now

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

        if self._playing_peer:
            # The peer's own file is already playing; do not swap it out
            return False

        self.status_label.set_text(f"loading {candidate.source} audio…")

        def work() -> None:
            try:
                if candidate.source == "youtube":
                    url = match.youtube_stream(candidate)
                else:
                    url = candidate.preview_url

                hint = candidate.duration if candidate.source == "youtube" else 30.0
                resume_at = 0.0

                if candidate.source == "youtube" and self.candidate is not None:
                    # Upgrading from the 30 s preview: keep the user's place
                    resume_at = max(0.0, self.player.position)

                self.player.load_stream(url, duration_hint=hint, start=resume_at)

            except (PlayerError, RuntimeError, OSError) as error:
                GLib.idle_add(self._fail, str(error), token)
                return

            GLib.idle_add(self._on_stream_loaded, candidate, token)

        threading.Thread(target=work, daemon=True).start()
        return False

    def _on_stream_loaded(self, candidate, token: int) -> bool:

        if token != self._token:
            return False

        if self._playing_peer:
            # The peer's own file is already playing: it wins over the catalogue
            self.match_label.set_text(
                f"{candidate.label}  ({candidate.source} · {candidate.score:.2f} match, not played)")
            self._notify_state()
            return False

        self.candidate = candidate
        self.match_label.set_text(
            f"{candidate.label}  ({candidate.source} · {candidate.score:.2f} match, buffering)")
        self.status_label.set_text("buffering…")
        self._update_labels()
        self.player.play()
        self.play_button.set_label("⏸")
        self._start_timer()
        self._notify_state()
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

        from pynicotine.logfacility import log

        log.add(f"Digging: audition failed for {self.track_name}: {message}")

        if self._playing_peer or self.player.duration:
            # The peer file is playing fine; a catalogue miss is not an error
            return False

        self._set_status(message[:220], sticky_seconds=8)
        self.match_label.set_text("no playable source yet")
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
        self._cancel_peer()

        try:
            self._cache().enforce()

        except OSError:
            pass
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

    def _on_setup_clicked(self, *_args) -> None:
        self._open_setup(self._on_keep_clicked if self.source is not None else None)

    def _open_setup(self, then=None) -> None:

        from pynicotine.gtkgui.digsetup import SeparationSetup

        def saved(settings):
            ready, reason = renderer_available(settings.renderer, settings)

            if ready:
                self._set_status(f"separation ready ({settings.renderer})")

                if then is not None:
                    then()

            else:
                self._set_status(f"separation not ready: {reason}", sticky_seconds=8)

        SeparationSetup(self.application, on_saved=saved).present()

    def _on_keep_clicked(self, *_args) -> None:

        if self.source is None:
            self._set_status("nothing to keep (no browsed file attached)")
            return

        from pynicotine.digging.settings import DiggingSettings, renderer_available

        settings = DiggingSettings.load()
        ready, reason = renderer_available(settings.renderer, settings)

        if not ready:
            self._set_status(f"{reason} — choose how to separate", sticky_seconds=8)
            self._open_setup(self._on_keep_clicked)
            return

        try:
            from pynicotine.core import core
            from pynicotine.digging.actions import keep_source

            track = keep_source(core, self.source, peer=self.peer)

        except Exception as error:  # noqa: BLE001 - surface the reason in the UI
            self.status_label.set_text(f"keep failed: {error}")
            return

        if self.peer is not None:
            def on_promoted(path, kept=track):

                def apply():
                    try:
                        from pynicotine.digging.actions import record_local_path

                        record_local_path(kept, str(path))
                        self.status_label.set_text(f"kept {kept.filename} — saved to downloads")

                    except Exception:  # noqa: BLE001
                        pass

                    return False

                GLib.idle_add(apply)

            self.peer.on_promoted = on_promoted

        try:
            from pynicotine.digging.service import start_service

            start_service().kick(track)

        except Exception:  # noqa: BLE001
            pass

        self._set_status(f"kept {track.filename} — separating when the download lands", sticky_seconds=8)

    # -- export and drag-to-DAW ------------------------------------------

    def _cache(self):

        from pynicotine.digging.cache import PreviewCache
        from pynicotine.digging.settings import DiggingSettings

        settings = DiggingSettings.load()
        folder = settings.work_path / "exports"
        folder.mkdir(parents=True, exist_ok=True)
        return PreviewCache(folder, settings.preview_cache_bytes)

    def _export_dir(self):
        return self._cache().root

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

        written = write_wav(audio, path, self.player.sample_rate)
        self._cache().enforce()
        return written

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

    def _on_waveform_drag_begin(self, _gesture, start_x, _start_y) -> None:
        self._drag_start_x = start_x

    def _on_waveform_drag(self, _gesture, offset_x, _offset_y) -> None:
        # drag-update reports displacement since drag-begin, not a position
        start_x = getattr(self, "_drag_start_x", 0.0)
        self._seek_fraction(self._fraction_at(start_x + offset_x), reload=False)

    def _on_waveform_drag_end(self, _gesture, offset_x, _offset_y) -> None:
        start_x = getattr(self, "_drag_start_x", 0.0)
        self._seek_fraction(self._fraction_at(start_x + offset_x), reload=True)

    def _seek_fraction(self, fraction: float, reload: bool = True) -> None:

        if not self.player.duration:
            return

        target = fraction * self.player.duration
        buffered = self.player.buffered_fraction * self.player.duration

        if self.peer is not None and buffered and target > buffered + 1.0:
            # The peer may have been paused when this track was left behind
            self.peer.resume()
            self.status_label.set_text("seeking — waiting for the peer to send that part")

        self.player.seek(target, reload=reload)
        self._update_labels()
        self.waveform.queue_draw()

        # SoundCloud behaviour: clicking the waveform resumes a stopped player
        if not self.player.is_playing:
            try:
                self.player.play()
                self.play_button.set_label("⏸")
                self._start_timer()
                self._notify_state()

            except PlayerError:
                pass

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

    def _set_status(self, text: str, sticky_seconds: float = 4.0) -> None:
        """Show a message that the playhead tick will not immediately overwrite."""

        import time as _time

        self.status_label.set_text(text)
        self._status_until = _time.monotonic() + sticky_seconds

    def _tick(self) -> bool:

        import time as _time

        self._update_labels()
        self.waveform.queue_draw()
        self._maybe_retry_peer_switch()
        self._maybe_extend_peer()
        self._maybe_resume_peer()

        if _time.monotonic() < self._status_until:
            return True

        if self.candidate is not None:
            fraction = self.player.buffered_fraction

            if fraction < 1.0:
                self.status_label.set_text(f"buffering {int(fraction * 100)}%")
            elif self.player.is_playing:
                self.status_label.set_text("playing")

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
