# Handoff prompt (paste into a fresh session)

You are continuing work on a fork of Nicotine+ that has been extended into a
crate-digging tool for sampling (browse Soulseek → audition → keep → separate
stems → Ableton Live). The long-term plan is a native SwiftUI client on macOS
that talks to this Python engine over a local HTTP API.

Start by reading, in this order:
- docs/HANDOFF.md   (state, architecture, known issues, operational notes)
- docs/ENGINE-API.md (API contract + migration plan)
- docs/DIGGING.md    (feature overview)

Repo: /Volumes/Schema Era/Schema Apps/nicotine
Branch: main-ours (41 commits ahead of origin/master; do not touch master)

Environment (already set up):
- .venv created with --system-site-packages (Python 3.14.7, GTK 4.24.2,
  PyGObject, PyObjC, sounddevice, yt-dlp)
- Dev profile: --config "$PWD/.dev/config" --user-data "$PWD/.dev/data"
- Tests: XDG_CONFIG_HOME=/tmp/digcfg .venv/bin/python -m pytest pynicotine/tests -q
  (baseline: 131 passed, 1 skipped)
- Never print the contents of .dev/config (it contains the Soulseek password).

Your tasks, in priority order:

1. Add GET /events as Server-Sent Events to pynicotine/engineapi: login state,
   browse completion, transfer progress, crate/pipeline status. Keep the existing
   pull endpoints working. Update docs/ENGINE-API.md.

2. Add /search to the API: start a search, expose paged results, and feed new
   results to /events. Follow the paging pattern already used for browse
   (folder_page/file_page in pynicotine/userbrowse.py).

3. Playback handoff endpoint: return the resolved audition source for a file
   (catalogue URL vs peer partial file) and expose the peer-preview lifecycle, so
   a native app can use AVAudioEngine instead of the PortAudio player. Do not
   remove the existing player.

4. Only after 1-3: prototype the SwiftUI spike described in docs/HANDOFF.md
   section 6 (window + paged browse + player + drag), launching the Python engine
   as a child process.

Rules of engagement:
- Use anchored edits on large files (an earlier whole-file write truncated
  pynicotine/userbrowse.py); verify line counts and grep for key symbols after
  editing.
- Do not import `log` inside a function in gtkgui/application.py — it shadows the
  module-level logger and breaks startup (already caused one critical-error dialog).
- Do not re-introduce Gtk.DragSource file drags; macOS drag is handled by an
  invisible AppKit child window (pynicotine/digging/nativedrag.py).
- Free port 2234 before restarting the app:
  lsof -nP -iTCP:2234 -sTCP:LISTEN | tail -n +2 | awk '{print $2}' | xargs kill
- If the app starts but nothing connects, run with --ci-mode to get a traceback
  instead of the critical-error dialog.
- Keep the Python engine front-end agnostic: no UI assumptions in pynicotine/*.
- Run the test suite before each commit; commit on main-ours with a focused message.

Definition of done for this session:
- /events and /search implemented, documented, and covered by tests;
- curl examples in docs/ENGINE-API.md verified against a running instance;
- test suite green and the app restarted cleanly;
- a short report of what changed, what was verified live, and what remains.
