# Handoff prompt (paste into a fresh session)

> **Superseded in part.** The product plan changed on 2026-11-27: the app is now
> **Tribe Seek**, with a single-window search/shelf workspace, DJ and Sample
> crates, a collective Rolodex, Passage Preset 62 as the local splitter, and
> audioFabric's Remote Script for Live insertion. Read [ROADMAP.md](ROADMAP.md)
> first; this prompt's task list is history.

You are continuing a fork of Nicotine+ that has become a crate-digging tool for
sampling: browse Soulseek → audition → keep → separate stems → Ableton Live.
The Python engine is mature and exposes a local API; **`native/TribeSeek`** is a
SwiftUI client that is now the daily front end. GTK still exists and still owns
the only separation-setup UI.

Read, in this order:
- docs/HANDOFF.md — **§0 state, §4 what works, §5 blockers, §8 next steps**
- docs/ENGINE-API.md — endpoints, SSE contract (chunked; one data line = one event)
- docs/UI-DIRECTION.md — tokens, materials, the two palettes
- docs/DIGGING.md — feature overview (older, still useful for the pipeline)

Repo: /Volumes/Schema Era/Schema Apps/nicotine
Branch: main-ours (50+ commits ahead of origin/master; never touch master)
Fork: santerotribe/nicotine-plus (default branch main-ours; push main-ours and
native-client-v1 there — `origin` is upstream and read-only)

Environment:
- .venv created with --system-site-packages (Python 3.14.7, GTK 4.24.2, PyGObject)
- Native: `native/TribeSeek/run.sh` (spawns the engine if 8766 is free)
- Tests: `XDG_CONFIG_HOME=/tmp/digcfg .venv/bin/python -m pytest pynicotine/tests -q`
  (165 passed, 1 skipped) and
  `(cd native/TribeSeek && swift test --disable-sandbox --scratch-path /tmp/tribeseek-build --cache-path /tmp/tribeseek-cache)`
  (7 passed)
- Never print .dev/config (it contains the Soulseek password).

Where we are: browse, live search (50,000+ results), audition with AVAudioEngine,
Keep, drag-out, reconnect and an engine watchdog all work. **The chain stops at
separation**: .dev/digging.json is {} — renderer is mvsep with no token, Demucs
is not installed, the studio-PC URL is empty — so Keep downloads and then fails.
The native app's "Digging" tab is a placeholder, so there is no way to configure
a renderer from it.

Your tasks, in priority order:

1. **Settings API + Digging screen — the blocker.**
   - Engine: `GET /settings` returning raw DiggingSettings plus `renderer_available`
     messages for mvsep / pc / local and preview-cache usage; `PATCH /settings`
     accepting a validated subset (renderer, mvsep_token, mvsep_sep_type, preset,
     pc_url, pc_token, export_dir, preview_cache_mb, observatory_root, live_app,
     warp defaults), dispatched on the engine thread. Tests for validation.
   - App: replace the Digging placeholder with three cards — Separation (renderer
     picker, credentials, a Test key printing readiness), Output & Live (folders,
     warp mode), Cache (budget, usage, Clear).
   - Done when a fake renderer shows its real error, a token flips readiness, and
     values survive a relaunch.

2. **First real pipeline run** once a token exists: Keep a track and watch
   `kept → separating → ready`, stem lanes populate, "Open in Live" opens a
   warped set in Live 12. Ask the user for the MVSEP token; do not echo it back
   into chat or logs.

3. **Crate management**: `DELETE /crate/<id>` + a row action; remove the stale
   `winter2014` entry (kept, no local path).

4. **Transfer controls**, then polish: peer-partial reload, focus rings that do
   not depend on macOS keyboard navigation, orphan-engine cleanup on SIGTERM,
   saved searches, an export endpoint so drag carries a WAV instead of the source
   file, chip drag fallback removal, GTK3 audit, i18n.

Rules of engagement:
- events.emit() quits the client when a listener raises. Any new engine listener
  used by the API must go through `engineapi.hub.guard()` and accept loose
  arguments (abort-download passes three, update-download two).
- Use anchored edits on large files; a whole-file write once truncated
  pynicotine/userbrowse.py.
- Do not import `log` inside a function in gtkgui/application.py (it shadows the
  module logger and breaks startup).
- Do not re-introduce Gtk.DragSource file drags; macOS drag is AppKit
  (pynicotine/digging/nativedrag.py for GTK, Drag/DragOutHandle.swift for native).
- Free the ports before restarting: kill PIDs from lsof on 2234 and 8766. If the
  app starts but nothing connects, use `--ci-mode` for a traceback.
- SwiftPM needs `--disable-sandbox` and `/tmp/tribeseek-build` here; the SSD path
  breaks the compiler cache.
- Fonts are `Manrope-*` and `IBMPlexMono-Regular`/`-Medium` by Core Text name;
  the family name silently falls back to SF Mono.
- One Soulseek account only: another client on `santero` kicks this engine
  ("account in use elsewhere"). Use `POST /login` (or the Reconnect key) after
  closing it.
- Keep the engine front-end agnostic: no UI assumptions under pynicotine/*.
- Run both test suites, commit on main-ours with a focused message, and push
  main-ours + native-client-v1 to fork.

Definition of done for this session:
- /settings implemented, documented in docs/ENGINE-API.md, tested, and exercised
  with curl against a running engine;
- the Digging screen drives it, with readiness visible and values persisting;
- one Keep → separate → Live run completed (or the exact remaining blocker
  reported);
- both suites green, app relaunched cleanly, and a short report of what changed,
  what was verified live, and what remains.
