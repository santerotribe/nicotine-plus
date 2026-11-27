# Handoff — digging client + engine

Last updated: 2026-11-27 · branch `main-ours` · **55+ commits ahead** of
`origin/master` · fork `santerotribe/nicotine-plus` · Python 165 passed /
Swift 7 passed.

This is a working fork of [Nicotine+](https://github.com/nicotine-plus/nicotine-plus)
(Python 3.11+, GTK 4 via PyGObject, GPL-3.0-or-later) extended into a
crate-digging tool for sampling: browse Soulseek shares → audition → keep →
separate stems → Ableton Live.

Two front ends exist:

- **GTK** (original, functional, has the only separation-setup UI).
- **`native/TribeSeek`** (SwiftUI, this session's work; now the daily client) —
  browse, live search, audition with AVAudioEngine, Keep, drag-out, engine
  supervision. Its look is specified in [UI-DIRECTION.md](UI-DIRECTION.md).

The engine API contract is [ENGINE-API.md](ENGINE-API.md). Feature overview:
[DIGGING.md](DIGGING.md). Paste-ready prompt: [HANDOFF-PROMPT.md](HANDOFF-PROMPT.md).

**If context is tight, read §0 (state), §5 (blockers), §8 (next steps).**

---

## 0. Where we are, in one paragraph

The engine API is mature: paged browse, Server-Sent Events, engine-side live
search, audition sessions with a resolved playback source, login/reconnect, and
a watchdog. The native SwiftUI client is genuinely usable — you can browse a
peer, search the network, audition the real file through AVAudioEngine, keep it,
and drag it into Live. **The chain stops at separation:** no renderer is
configured (no MVSEP token, no studio-PC agent, Demucs not installed), and the
native app has no Settings screen to enter one. So Keep downloads the file and
the pipeline ends there: no stems, no stem lanes, no Live set from the app.

**The next job is the settings API + Digging screen**, then one real
Keep → separate → Live run with a token.

![The native client: auditioning a local AIF, Suno palette](assets/native-spike-2026-11-25.png)

---

## 1. Environment

| | |
|---|---|
| Repo | `/Volumes/Schema Era/Schema Apps/nicotine` (external SSD) |
| Branch | `main-ours`; `native-client-v1` mirrors it |
| Remotes | `origin` = upstream nicotine-plus (**read-only**); `fork` = `santerotribe/nicotine-plus` |
| Python | 3.14.7 in `.venv` (**created with `--system-site-packages`** so `gi` resolves) |
| GUI stack | GTK 4.24.2, libadwaita 1.10, gspell 1.14 (Homebrew) |
| Python deps | PyGObject 3.58, PyObjC 13.1, sounddevice 0.5.6, yt-dlp, pytest, pylint |
| Swift | 6.3.3, Xcode 26.6, macOS 26.3.2 |
| Media | `ffmpeg`/`ffprobe` (Homebrew); Demucs **not installed** |

GTK client (isolated dev profile):

```sh
cd "/Volumes/Schema Era/Schema Apps/nicotine"
NICOTINE_API_PORT=8766 NICOTINE_API_TOKEN=devtoken GTK_A11Y=none \
  .venv/bin/python -m pynicotine --config "$PWD/.dev/config" --user-data "$PWD/.dev/data"
```

Headless engine only:

```sh
NICOTINE_API_PORT=8766 NICOTINE_API_TOKEN=devtoken \
  .venv/bin/python -m pynicotine -n --config "$PWD/.dev/config" --user-data "$PWD/.dev/data"
```

Native client (starts the engine itself when 8766 is free):

```sh
native/TribeSeek/run.sh
```

Tests / lint:

```sh
XDG_CONFIG_HOME=/tmp/digcfg .venv/bin/python -m pytest pynicotine/tests -q   # 165 passed, 1 skipped
(cd native/TribeSeek && swift test --disable-sandbox \
   --scratch-path /tmp/tribeseek-build --cache-path /tmp/tribeseek-cache)         # 7 passed
.venv/bin/python -m pylint --rcfile=pyproject.toml pynicotine/engineapi pynicotine/digging
```

### Profile layout (never commit or print credentials)

```
.dev/config            Nicotine+ config FILE (contains the Soulseek password)
.dev/digging.json      digging settings; currently {} (no renderer configured)
.dev/data/digging/     crate.json, downloads/, previews/, exports/, stems/, sessions/
```

---

## 2. Repo, remotes, branches

- `origin` is upstream Nicotine+ — **do not push there**.
- The fork was created through the API (no interactive `gh repo fork`):
  `gh api -X POST repos/nicotine-plus/nicotine-plus/forks`.
- Fork default branch: `main-ours`. `main-ours` and `native-client-v1`
  carry the same tip (docs commits may move it); keep them in step.
- Push:

```sh
git branch -f native-client-v1 HEAD
GIT_TERMINAL_PROMPT=0 git push fork main-ours native-client-v1
```

- `gh auth setup-git` fails here (sandbox cannot write `~/.gitconfig`), but
  pushes work because credentials are already available.

---

## 3. Architecture map

### Engine — `pynicotine/digging/`

| Module | Responsibility |
|---|---|
| `analyze.py` | ffprobe metadata, onset tempo detection, waveform peaks |
| `audition/match.py` | filename parsing, iTunes + YouTube matching, duration scoring |
| `audition/player.py` | PortAudio playback, buffered streams, crossfade adoption |
| `audition/buffer.py` | growing PCM buffer + ffmpeg stream decoder |
| `audition/peer.py` | peer preview transfer, partial-file handoff, keep promotion |
| `pipeline.py` | one track → stems |
| `renderers/` | MVSEP cloud, studio-PC agent, local Demucs |
| `ableton.py` | Live Set via ALS Observatory, warp + sample collection |
| `crate.py`, `actions.py` | crate persistence, keep / promote / record path |
| `service.py` | keep → download-finished → separate → build Live Set |
| `maintenance.py`, `cache.py` | preview sweep, LRU budget |
| `settings.py` | `DiggingSettings` — renderer, tokens, paths, warp, cache |
| `nativedrag.py` | AppKit child-window drag for GTK (GTK drags never worked) |

### Engine API — `pynicotine/engineapi/`

| Module | Responsibility |
|---|---|
| `server.py` | token-protected HTTP on loopback; routing; main-thread dispatch; SSE |
| `hub.py` | SSE hub: snapshot, transfer coalescing, browse settle, listener `guard()` |
| `searchstore.py` | engine-side search results for API searches, capped at 50k |
| `audition.py` | audition sessions, resolved source, keep, throttled preview sweep |
| `serialize.py` | raw JSON shapes |

Browse paging lives in `pynicotine/userbrowse.py`
(`user_summary`/`folder_page`/`file_page`). `do_search` returns its token and
accepts `notify_frontend=False`.

### GTK — `pynicotine/gtkgui/`

`digplayer.py` (Dig window), `crateview.py` (Crate tab), `digsetup.py`
(Separation… dialog), `digprefs.py` (Preferences → Digging), plus audition
hooks in `userbrowse.py`.

### Native — `native/TribeSeek/Sources/TribeSeek/` (27 Swift files)

`TribeSeek.swift`, `AppModel.swift`, `BrowserModel.swift`,
`SearchAndCrateModels.swift`, `AuditionModel.swift`, `SelfTest.swift`;
`Theme.swift`, `Skin.swift`, `Materials.swift`, `Controls.swift`,
`Waveform.swift`; `Shell/AppShell.swift`, `Shell/Transport.swift`,
`Shell/WindowConfigurator.swift`; `Screens/{Browse,Search,Audition,Crate}*`;
`Engine/{EngineClient,EngineModels,EngineSupervisor}.swift`;
`Audio/AuditionPlayer.swift`; `Drag/DragOutHandle.swift`;
`Resources/Fonts` (Manrope woff2, IBM Plex Mono 400 woff2 + 500 ttf, OFL).

---

## 4. What works today (verified)

- **Browse**: paged folders/files (`santero` = 27 folders / 864 files); Enter or
  double-click auditions; arrows move, the list scrolls to the selection.
- **Search**: live and grouped by peer with pinned headers. `ruggier` → 420
  results / 37 peers; `italo disco` → 50,000 (cap) / 875 peers. Results keep
  arriving; footer shows `2000 OF 50,000+ RESULTS · LIVE` with **Stop**.
- **Audition**: local share → exact file; remote → peer preview starts while the
  catalogue resolves; `source` returns local, peer partial or catalogue URL.
  AVAudioEngine plays it, waveform + seek + transport track the frame clock.
- **Keep**: writes the crate row and starts the real download. Stops at
  separation (see §5).
- **Drag-out**: real AppKit `NSDraggingSession` for files (transport handle and
  stem rows). Not yet dropped into Live by the agent — needs a manual check.
- **Connection handling**: header shows `ONLINE` / `CONNECTING` /
  `SOULSEEK OFFLINE` / `ACCOUNT IN USE ELSEWHERE`; `POST /login` reconnects;
  an offline search re-runs on login.
- **Engine watchdog**: 3 failed health checks (5 s apart) → respawn. Verified by
  killing the engine: fresh one up and logged in in ~20 s, pending search re-ran.
- **UI**: Suno palette default (`TRIBE_SKIN=arca` for the old one), hardware caps,
  traffic lights clear of the rail, draggable full-bleed window.

Useful verification commands:

```sh
B='Authorization: Bearer devtoken'
curl -s -H "$B" http://127.0.0.1:8766/state
curl -sN -H "$B" http://127.0.0.1:8766/events        # SSE (chunked)
TRIBE_SELFTEST=1 NICOTINE_API_TOKEN=devtoken native/TribeSeek/run.sh
```

---

## 5. Blockers and known issues (in priority order)

1. **Separation is unconfigured — the blocker.** `.dev/digging.json` is `{}`;
   `renderer = mvsep` with no token, `pc_url` empty, Demucs missing. Readiness
   says `MVSEP token is not set`. Keep downloads, then the pipeline fails; there
   are no stems, so the stem lanes and Live set never appear.
2. **The native app has no Settings screen.** "Digging" in the rail is a
   placeholder. The only working configurator is GTK Preferences → Digging /
   Separation… (`digprefs.py`, `digsetup.py`).
3. **Live and Settings sections are placeholders** in the native client.
4. **Stem lanes are implemented but never seen with real stems** (needs §1).
5. **Drag-out into Ableton is unverified** (implemented as AppKit drag).
6. **Peer-partial playback** opens the file once; no reload as bytes arrive.
7. **Focus rings** only appear when macOS keyboard navigation is enabled.
8. **Account relogin**: another client on `santero` kicks this engine
   (`ACCOUNT IN USE ELSEWHERE`). Nicotine+ deliberately stops retrying; use the
   Reconnect key / `POST /login`.
9. **Upstream crash**: one `Fatal Python error: Bus error` in the share-search
   path (`shares.py:223` ← `search.py:817`) while answering other users'
   searches. The watchdog recovers it; the cause is upstream, not ours.
10. **Engine log path**: `~/Library/Logs` is not writable under the sandbox, so
    the child engine logs to
    `/var/folders/.../T/TribeSeek-engine.log` (NSLog prints the exact path).
11. **Orphan engine on SIGTERM**: a normal Quit terminates the child; killing the
    app can leave it. `lsof -nP -iTCP:8766 -sTCP:LISTEN -t | xargs kill`.
12. **Sandbox writes**: `~/Music` and `~/.local/share/nicotine` are denied, so
    exports fall back to the profile and the digging CLI cannot run without
    `NICOTINE_DATA_HOME`. The GTK app launched normally uses the Live library.
13. **Legacy/untested**: chip drag helper (`draghelper.py`), GTK3 paths, i18n
    (`.mo` files not built).

---

## 6. Engine API (current)

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | no token; version + login flag |
| GET | `/state` | username, status (0/1/2), privileges, counters |
| GET | `/events` | SSE, chunked; `hello`, login, disconnect (relogged), browse, transfers, search, crate, audition |
| GET | `/users/<u>/summary` `/folders` `/files` | paged browse |
| POST | `/users/<u>/browse` | request a share list |
| GET | `/downloads` `/crate` | transfers / kept tracks |
| POST | `/crate/<id>/separate` | run the pipeline for a kept track |
| GET/POST | `/search` | list / create (`{term, mode, room, users}`) |
| GET | `/search/<t>` `/results` `/users` `/files` | counters, paged results (includes `dropped`) |
| POST/DELETE | `/search/<t>/stop`, `/search/<t>` | stop / forget |
| GET/POST | `/audition`, `/audition/<id>` | start / state (source, peer, catalogue) |
| POST/DELETE | `/audition/<id>/keep`, `/audition/<id>` | keep / close |
| POST | `/login` | reconnect after a relogin kick |

Rules learnt the hard way:

- `events.emit()` quits the client when a listener raises — **every API listener
  is wrapped in `hub.guard()`** and takes loose arguments (`abort-download`
  passes three, `update-download` two).
- SSE is HTTP/1.1 **chunked**; a native client must treat each `data:` line as
  one event (`AsyncLineSequence` does not surface the blank separator).
- Mutations are dispatched to the engine thread and the HTTP thread waits
  (8 s), so a 201 means the object exists.

---

## 7. Native client specifics

Run flags (environment):

| Flag | Effect |
|---|---|
| `NICOTINE_API_URL` / `NICOTINE_API_TOKEN` | attach to a running engine |
| `TRIBE_OPEN=<user>` | browse a peer on launch |
| `TRIBE_AUTO=1` | audition the first file after the first browse |
| `TRIBE_SEARCH=<term>` | run a search on launch |
| `TRIBE_SELFTEST=1` | headless PASS/FAIL check, exits non-zero on failure |
| `TRIBE_SKIN=arca` | legacy palette (Suno is the default) |
| `TRIBE_NO_LAUNCH=1` | never spawn an engine |

Build quirks:

- SwiftPM needs `--disable-sandbox` (the harness already sandboxes us and
  `sandbox-exec` is refused) and a scratch path outside this volume
  (`/tmp/tribeseek-build`), otherwise the compiler hits I/O errors on the SSD.
- Fonts: register the woff2/TTF at launch; Core Text names them
  `Manrope-*` and `IBMPlexMono-Regular`/`-Medium` (the family name does **not**
  resolve; a silent fallback renders SF Mono).
- Window: full-bleed, hidden title, rail reserves 30 pt for traffic lights,
  `isMovableByWindowBackground`, canvas as the window background.
- macOS cache warning (`NetworkStorageDB … Cache.db`) is the sandbox refusing
  `~/Library/Caches`; harmless.

---

## 8. Next steps (in order)

1. **Settings API + Digging screen (the blocker).**
   - Engine: `GET /settings` → raw `DiggingSettings` + per-renderer readiness
     (`renderer_available` messages), cache usage; `PATCH /settings` → validated
     keys only, main-thread dispatch, token required. Suggested keys: renderer,
     mvsep_token, mvsep_sep_type, preset, pc_url, pc_token, export_dir,
     preview_cache_mb, observatory_root, live_app, warp_warp defaults.
   - App: replace the Digging placeholder with three cards — *Separation*
     (renderer picker, credentials, Test key showing readiness), *Output & Live*
     (folders, warp mode), *Cache* (budget, usage, Clear). Tests for the
     validation layer.
   - Done when: setting a fake renderer shows its real error, setting a token
     flips readiness, and the values survive a relaunch.
2. **Run one real pipeline with MVSEP:** Keep a track → watch statuses
   (`kept → separating → ready`) → stem lanes populate → "Open in Live" opens a
   warped set. This is the first end-to-end proof.
3. **Crate management**: `DELETE /crate/<id>` + row action; remove the stale
   `winter2014` row (kept, no local path).
4. **Transfer controls**: pause/resume/cancel/clear on `/downloads/<id>`, plus
   a transport/Downloads surface in the app.
5. **Polish**: peer-partial reload as bytes grow; focus rings that do not depend
   on system keyboard nav; orphan-engine cleanup on SIGTERM; log-path fix;
   saved searches; an export endpoint so drag carries a WAV rather than the
   source file.
6. **Cleanup**: remove the chip drag fallback if the AppKit overlay stays
   reliable, GTK3 audit, i18n pass.

---

## 9. Operational notes

- Free the ports before restarting:
  `lsof -nP -iTCP:2234 -sTCP:LISTEN -t | xargs kill`;
  `lsof -nP -iTCP:8766 -sTCP:LISTEN -t | xargs kill`.
- Start from a fresh terminal with `cd` into the repo; terminals in this
  environment have been taken over before.
- If the app starts but nothing connects, run with `--ci-mode` for a traceback.
- The child engine log is the fastest diagnosis:
  `tail -40 /var/folders/*/*/T/TribeSeek-engine.log`.
- Never print `.dev/config` (plaintext password).
- Only one client per Soulseek account; another `santero` session causes
  relogin kicks.
- Commit on `main-ours`, run both test suites, then push `main-ours` and
  `native-client-v1` to `fork`.

---

## 10. Session log (newest first)

**2026-11-27** — Relaunch verified; search resiliency: live SSE-driven search
with LIVE/Stop, 50,000+ cap display, connection status + Reconnect (`POST
/login`), offline search retry, engine watchdog with auto-respawn, `relogged`
and `dropped` in the API. Diagnosed the "empty search": account relogin kicks +
one upstream Bus-error crash + a 24 s client poll window.

**2026-11-25 (late)** — Suno palette studied from their CSS and made the default
(`TRIBE_SKIN=arca` keeps the old one); traffic lights cleared from the rail;
window chrome made draggable; palette comparison shots in `docs/assets`.

**2026-11-25** — Hardware control language (caps, wells, LEDs, knurling, lit
keys), ten UX upgrades (focus rings, LED fades, stem lanes, queue readout, crate
LEDs, empty states, pinned search headers, scroll-into-view, bezel, Plex Mono
Medium). UI direction written.

**2026-11-25** — Native SwiftUI spike: browse, audition via AVAudioEngine,
transport, drag, engine spawn; engine API gained SSE events, `/search`,
`/audition`, paged browse. Fixed SSE chunking and the fatal listener bug.
