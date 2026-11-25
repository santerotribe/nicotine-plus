# Handoff prompt (paste into a fresh session)

You are continuing work on a fork of Nicotine+ that has been extended into a
crate-digging tool for sampling (browse Soulseek → audition → keep → separate
stems → Ableton Live). The long-term plan is a native SwiftUI client on macOS
that talks to this Python engine over a local HTTP API.

Start by reading, in this order:
- docs/HANDOFF.md      (state, architecture, known issues, operational notes)
- docs/ENGINE-API.md   (API contract, event stream, worked curl session)
- docs/UI-DIRECTION.md (the design brief for the native client)
- docs/DIGGING.md      (feature overview)

Repo: /Volumes/Schema Era/Schema Apps/nicotine
Branch: main-ours (44 commits ahead of origin/master; do not touch master)

Environment (already set up):
- .venv created with --system-site-packages (Python 3.14.7, GTK 4.24.2,
  PyGObject, PyObjC, sounddevice, yt-dlp)
- Dev profile: --config "$PWD/.dev/config" --user-data "$PWD/.dev/data"
- Tests: XDG_CONFIG_HOME=/tmp/digcfg .venv/bin/python -m pytest pynicotine/tests -q
  (baseline: 165 passed, 1 skipped)
- Never print the contents of .dev/config (it contains the Soulseek password).

Already done (do not redo):
- GET /events (SSE), /search with engine-side paging, /audition playback handoff.
  See docs/ENGINE-API.md; 40 tests live in pynicotine/tests/unit/engineapi.

Your tasks, in priority order:

1. Transfer controls + settings API: pause/resume/cancel/clear on
   /downloads/<user>/<path>, and read/write of the digging config
   (renderer, cache budget, export folder) behind /settings.

2. The SwiftUI spike, following docs/UI-DIRECTION.md exactly: a window with the
   rail → list → detail skeleton, paged browse over the API, a persistent 48 pt
   instrument transport playing from /audition with AVAudioEngine, and an AppKit
   NSDraggingSession for files. Launch the Python engine as a child process and
   wait for /health before showing content. Evaluate before committing to the
   full native shell.

Rules of engagement:
- Use anchored edits on large files (an earlier whole-file write truncated
  pynicotine/userbrowse.py); verify line counts and grep for key symbols after
  editing.
- events.emit() quits the client when a listener raises. Any new engine listener
  added for the API must be wrapped in engineapi.hub.guard() and accept loose
  arguments (abort-download passes three, update-download passes two).
- Do not import `log` inside a function in gtkgui/application.py — it shadows the
  module-level logger and breaks startup.
- Do not re-introduce Gtk.DragSource file drags; macOS drag is handled by an
  invisible AppKit child window (pynicotine/digging/nativedrag.py).
- Free port 2234 before restarting the app, and check 8766 too:
  lsof -nP -iTCP:2234 -sTCP:LISTEN -t | xargs kill
  lsof -nP -iTCP:8766 -sTCP:LISTEN -t | xargs kill
- If the app starts but nothing connects, run with --ci-mode to get a traceback
  instead of the critical-error dialog.
- Keep the Python engine front-end agnostic: no UI assumptions in pynicotine/*.
- The native client follows arcaNative's design system. Port its *values*, never
  its source: this repo is GPL-3.0-or-later, arcaNative is a separate product.
- Run the test suite before each commit; commit on main-ours with a focused message.

Definition of done for this session:
- the new endpoints implemented, documented in docs/ENGINE-API.md and covered by
  tests, with curl examples verified against a running instance;
- the spike builds and runs against the live engine, showing a real browse list,
  real audio through AVAudioEngine, and a real drag into Ableton;
- test suite green and the app restarted cleanly;
- a short report of what changed, what was verified live, and what remains.
