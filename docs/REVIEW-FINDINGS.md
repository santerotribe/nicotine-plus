# Independent review — Tribe Seek

2026-11-28 · branch `main-ours` · reviewer: external pass
Scope: the engine folder aggregates, crate kinds, shelf/freshness, audition deck,
Rolodex/ledger, settings/Rig, and the documented contract.
No application code was changed.

State verified while reviewing:

- `XDG_CONFIG_HOME=/tmp/digcfg .venv/bin/python -m pytest pynicotine/tests -q`
  → **175 passed, 1 skipped**.
- Reproductions run against the checkout (no app code touched):
  - keeping an existing track with `kind="dj"` returns the original `sample`
    entry and the DJ crate stays empty;
  - a ledger path starting with `~` creates a literal `./~` directory;
  - `.dev/digging.json` is `-rw-r--r--` (0644); `save()` writes the MVSEP/PC
    tokens into it unchanged when set;
  - `"Simon & Garfunkel"` is emitted unescaped by the client's path encoder and
    splits the query string; `"C++"` decodes as `"C  "`;
  - aggregating 100 000 files costs ~24 ms of engine CPU (so raw cost is not the
    main concern; the concurrency and paging of the aggregates are).

Severity:

- **P0** — silently loses the user's work (a keep, a crate entry, a ledger entry).
- **P1** — a core gesture is broken or misleading, or secrets are exposed.
- **P2** — correctness/robustness under load, edge data, or a second writer.
- **P3** — polish, performance, ergonomics.

---

## Contents

| | Sev | Finding |
|---|---|---|
| F1 | P0 | A keep's file can be silently stranded: preview transfer is paused, never promoted |
| F2 | P0 | Crate is read-modify-written from three threads; entries and kinds are lost |
| F3 | P1 | "Refresh" never re-requests a peer's share — freshness can never change |
| F4 | P1 | The freshness baseline is committed on the wrong edges, and can commit a partial share |
| F5 | P1 | Private/buddy folders disappear whenever the peer also has public folders |
| F6 | P1 | Keeping into a second kind is silently ignored; one `kind` cannot express both crates |
| F7 | P1 | An API-only session never starts the pipeline — "separating when it lands" is false |
| F8 | P1 | Settings accept arbitrary paths; one bad `work_dir` bricks every crate call and persists |
| F9 | P1 | Secrets are stored 0644 in plaintext and cannot be cleared through the API |
| F10 | P1 | The shared ledger rewrites the whole file; a synced folder loses entries and steals credit |
| F11 | P1 | Stars: another member's star cannot be removed, and member identity collides by default |
| F12 | P1 | A `~` ledger path creates a literal `~` directory; Rig invites exactly that |
| F13 | P2 | `folder_page` can return a torn page: old `total` with zeroed folder rows |
| F14 | P2 | Aggregates are recomputed per request and the client materialises every folder |
| F15 | P2 | The `_invoke` timeout is not a cancellation: a failed POST may still have applied |
| F16 | P2 | One malformed attribute type turns a whole folder page into a 500 |
| F17 | P2 | Summary counts are overwritten per response message and disagree with the folder list |
| F18 | P2 | Folder names containing `&` or `+` open the wrong folder (verified) |
| F19 | P2 | `loadFiles`/settle races can show folder A's files under folder B |
| F20 | P2 | Count+bytes is the wrong fingerprint: it misses swaps and is tripped by cover art |
| F21 | P2 | Rolodex counts every local keep twice and reports your own keeps as "crew" |
| F22 | P2 | Rolodex statuses are fetched once and never refreshed; 120 sequential requests per load |
| F23 | P2 | The collapsed transport destroys its whole view identity 30 times a second |
| F24 | P2 | The drag handle offers a truncated `INCOMPLETE…` preview file to Ableton |
| F25 | P2 | The dig scroll never fires and a stale file selection makes Return a no-op |
| F26 | P2 | Bin sort comparators have no stable tiebreak; bins can reshuffle |
| F27 | P2 | The peer list grows duplicates, and the `ForEach` keys on the username |
| F28 | P2 | "Keep all" only keeps the first 500 loaded files and skips formats the engine counts |
| F29 | P2 | Keeping your own share downloads your own file and never records `local_path` |
| F30 | P2 | The pipeline service freezes settings at first keep; Rig changes split to the old folder |
| F31 | P3 | The Rig and Rolodex load twice and can clobber edits |
| F32 | P3 | Contract drift: `/crate/keep` undocumented, `kind` missing, no API version |
| F33 | P3 | The client ignores `gap` events, so a dropped SSE connection leaves stale state |
| F34 | P3 | The API fails open without a token and accepts text/plain state changes |
| F35 | P3 | Deck height maths: 144 pt of chrome inside a 154 pt frame |
| F36 | P3 | Minor UI/copy items (grouped) |

---

## P0 — work is lost

### F1 — A keep's file can be silently stranded: the preview transfer is paused, never promoted
`pynicotine/digging/actions.py:82-98` · `pynicotine/downloads.py:857-869` ·
`pynicotine/engineapi/audition.py:123-137` · `pynicotine/digging/audition/peer.py:204-232` ·
`pynicotine/digging/maintenance.py:66-84` · `native/TribeSeek/Sources/TribeSeek/AppModel.swift:546-552`

**Why it matters.** Three paths end with a crate row that says `kept` but whose
file will never arrive:

1. **Audition → Keep → audition the next file.** `AppModel.audition` closes the
   previous session before starting the new one (`AppModel.swift:546-552`).
   `close()` calls `peer.cancel()`, which aborts the preview transfer with
   `TransferStatus.PAUSED` (`audition.py:130-133`, `downloads.py:911-919`) and
   disconnects the only listener that would have promoted the file
   (`peer.py:194-200`). `promote_to` is still set on a now-unreachable object,
   so the copy never happens. This is the normal rhythm of the product: keep,
   then move on.
2. **Keep all from the shelf after an audition.** `crate/keep` passes
   `peer=None` (`server.py:649-700`), so `keep_source` falls through to
   `enqueue_download` with `downloads/<user>` (`actions.py:92-98`). A preview
   transfer already exists for that username+path in `previews`, so
   `enqueue_download` returns early — the folder differs but the status is not
   `FINISHED`, which is the only case it replaces (`downloads.py:862-869`).
   The download is silently not started.
3. **Keeping your own share** is F29 (separate finding): no transfer is queued
   at all, and no local path is recorded.

The preview sweep makes it worse rather than better: a transfer whose
`virtual_path` is in the crate is explicitly skipped and **never resumed**
(`maintenance.py:66-70`). The result is a permanently paused transfer and a
missing file, with the deck and crate both claiming the track is kept. The
UI's own note says "separating when the download lands"
(`AppModel.swift:634-636`).

**Suggested fix.** Give the keep ownership of the transfer rather than the
session:

- In `keep_source`, before enqueueing, look up `core.downloads.transfers`
  for `username + virtual_path`; if it is a preview transfer, **retarget** it
  (`transfer.folder_path = downloads/<user>`) and resume it, or clear it and
  enqueue into the keep folder. Do not rely on `enqueue_download`'s dedupe.
- Make promotion independent of the session: persist `promote_to` (or just the
  keep target) on the crate track, and register the promote callback with a
  component that outlives the audition (the pipeline service or a small
  "kept transfers" watcher), or copy in the `FINISHED` update handler of a
  transfer that is marked kept.
- On `AuditionSession.close`, **detach** rather than cancel a transfer whose
  track is kept (or let the keep move the transfer out of `previews` first).
- Make `keep_source` idempotent: if the track already has `local_path` or the
  target file exists, do not queue a download and do not reset the status.
- In `sweep`, resume kept-but-unfinished preview transfers instead of merely
  skipping them; a kept track with no local file and no live transfer is a
  bug, not a housekeeping decision.
- Add a regression test: keep a session with an in-flight preview, close the
  session, assert the crate track acquires a `local_path` (fake downloads).

### F2 — The crate is read-modify-written from three threads; entries and kinds are lost
`pynicotine/engineapi/server.py:520-529` and `:702-713` ·
`pynicotine/digging/service.py:131-144` and `:151-153` · `pynicotine/digging/crate.py:145-153`

**Why it matters.** `crate_for()` returns a **new** `Crate` each call
(`actions.py:45-48`), which loads `crate.json` and later rewrites all of it.
Three writers race:

- HTTP handlers load the crate on the **HTTP thread** and apply the mutation on
  the engine thread. `POST /crate/<id>/kind` (`server.py:702-713`) does
  `crate = crate_for()` on the handler thread, then
  `self._invoke(lambda: crate.set_kind(...))`. Any keep that lands between the
  load and the save is dropped by the save. `DELETE /crate/<id>` has the same
  shape (`server.py:520-529`).
- `PipelineService._set_status` runs on a pipeline **worker thread** and does a
  fresh load → mutate → `save()` (`service.py:131-144`). Two separations
  finishing together overwrite each other's status, and a keep during
  separation can vanish.
- `Crate.save` writes a **fixed** temp name `crate.json.tmp` and then
  `replace`s (`crate.py:149-153`). Two concurrent saves can collide on that
  path and raise `FileNotFoundError` from `replace`.

There is a nastier consequence in `service._process`: the first
`self._set_status(track.id, status=STATUS_SEPARATING)` is **outside** the
`try` (`service.py:151-153`). If it raises (the collision above, a read-only
folder, a settings change — see F8/F30), the thread dies before the `finally`
that discards the id from `_running`, so that track can never be separated
again for the life of the process.

**Suggested fix.** One owner for the file. E.g. a process-wide
`Crate` cached per path with a `threading.RLock`, and every mutation goes
through it; or serialize all crate I/O on the engine thread and have the
pipeline post status changes with `events.invoke_main_thread`. Use a unique
temp name (`tempfile.mkstemp(dir=...)`) and, ideally, a small append-only
journal or a per-process lockfile. Move `_set_status(SEPARATING)` inside the
`try` and clear `_running` in a `finally` that covers it.

---

## P1 — a core gesture is broken or misleading

### F3 — "Refresh" never re-requests a peer's share; freshness can never change
`native/TribeSeek/Sources/TribeSeek/BrowserModel.swift:295-345` (esp. 306-313) ·
`native/TribeSeek/Sources/TribeSeek/AppModel.swift:396-404` ·
`native/TribeSeek/Sources/TribeSeek/Screens/BrowseDetail.swift:98-100`

**Why it matters.** `browse(user:)` checks the engine's cached summary
**before** it asks the engine to browse:

~~~swift
if let cached = try? await client.summary(user: user), cached.folders > 0 {
    summary = cached; await loadFolders(user: user); return   // no client.browse
}
~~~

So for any peer the engine has already seen, `client.browse(user:)` is never
called from anywhere in the UI: the header's Refresh button
(`BrowseDetail.swift:98-100`), the peer column's refresh
(`BrowseColumn.swift:17-26`), `AppModel.browse` (`AppModel.swift:403`), and
`dig` all take the cached branch. The engine keeps browsed users in memory, so
the share is frozen for the life of the engine process. Consequences:

- New folders are never discovered, so `dig(user:folder:)` from a search result
  fails with "The peer lists N folders, but not that one"
  (`BrowserModel.swift:453-456`).
- Freshness markers compare the same snapshot to itself: the feature cannot
  ever produce a "new" flag (F4 compounds this).
- A peer whose first browse was partial can never recover.

The engine does the right thing — `POST /users/<u>/browse` with
`new_request=True` clears and re-requests (`server.py:563-571`,
`userbrowse.py:153-168`) — the client just never calls it for a cached user.

**Suggested fix.** Split the two intents explicitly. `select(user:)` may use
the cache; `refresh()` must call `client.browse` first, wait for the engine's
`browse done=true` (the hub already emits it, `hub.py:282-297`) or for a
changed generation, then reload. Have Refresh/peer-column button call
`refresh()`. Add a `generation` to the folders payload so a client can tell a
new share from the old one (see F13/F14).

### F4 — The freshness baseline is committed on the wrong edges, and can commit a partial share
`native/TribeSeek/Sources/TribeSeek/AppModel.swift:400-403` and `:207-215` ·
`native/TribeSeek/Sources/TribeSeek/BrowserModel.swift:235-260`, `:299-301`,
`:347-360`, `:372-414` · `native/TribeSeek/Sources/TribeSeek/Shell/AppShell.swift:86-90`

**Why it matters.** The baseline is a whole-share count+size snapshot, keyed by
username, advanced on "leaving the shelf / switching peers / quit". Neither of
the last two works reliably:

- **Switching peers never commits.** `AppModel.browse` sets
  `browse.selectedUser = user` *before* calling `browse.browse(user:)`
  (`AppModel.swift:400-403`). The commit inside `BrowserModel.browse` is
  guarded by `if let previous = selectedUser, previous != user`
  (`BrowserModel.swift:299-301`) — always false because `selectedUser` is
  already the new user. `select(user:)` (the Switch peer list,
  `BrowseColumn.swift:41`) never commits at all (`BrowserModel.swift:347-360`).
  The only remaining commit is leaving the section (`AppShell.swift:86-90`) and
  `shutdown()` (`AppModel.swift:213`). So in the normal workflow — dig A, dig
  B, dig C without leaving the shelf — only C is ever committed. A's changes
  are re-announced as "new" on the next visit.
- **Quit is not guaranteed.** `shutdown()` runs from `onDisappear`
  (`TribeSeek.swift:26`); `applicationWillTerminate` only kills child engines
  (`TribeSeek.swift:49-52`). ⌘Q does not have to run a SwiftUI
  `onDisappear`, so the "on quit" commit is best-effort.
- **A partial load is committed as the whole share.** `loadFolders` breaks out
  of its paging loop on any failed/empty page but still assigns
  `folders = collected`, runs `noteFresh`, and later leaves the partial set
  available to `commitSeen` (`BrowserModel.swift:380-401`). The baseline is a
  whole-share snapshot, so every folder missing from the partial fetch becomes
  "new" on the next visit and the folder counts that were captured mid-load
  become the new normal. This is the worst failure mode: it is silent and it
  persists.

Also note the commit writes a second snapshot even if the user never actually
saw the finished share: `if let first = collected.first { await loadFiles(...) }`
can happen while the peer is still answering.

**Suggested fix.** One owner for "leaving a peer". Track it in
`BrowserModel.select`/an explicit `leavePeer()` rather than mutating
`selectedUser` from `AppModel` first; or move the commit into
`selectedUser.didSet`. Add `loadComplete = (offset >= total && no error)` and
store `complete` in `SeenSnapshot`; only advance a baseline from a complete
load, otherwise keep the old one (and keep showing the old markers). Commit from
`applicationWillTerminate` too. Once F3 is fixed, add a generation check so a
baseline taken from page requests belonging to generation N is discarded if N
changed.

### F5 — Private/buddy folders disappear whenever the peer also has public folders
`pynicotine/userbrowse.py:225-233`, `:248`, `:255-258`, `:276-278` ·
`pynicotine/gtkgui/userbrowse.py:521-524`

**Why it matters.** The protocol delivers two groups: public folders, and
private/buddy/trusted folders the peer shares with you specifically
(`slskmessages.py:3300-3325`). The GTK client shows **both**
(`gtkgui/userbrowse.py:521-524`). The new API picks one:

~~~python
folders = list(browsed_user.public_folders) or list(browsed_user.private_folders)
~~~

So a peer who has any public folder has all of their private folders hidden
from the shelf, and `file_page` cannot reach them either
(`userbrowse.py:276-278`). Meanwhile `user_summary` reports
`num_folders`/`num_files`/`shared_size` computed over **both** groups
(`userbrowse.py:709-724`), so the header says "27 FOLDERS" while the shelf
lists 20. The same `or` also means a folder present in both groups silently
resolves to the public file list.

**Suggested fix.** Merge both groups for listing (public first, then private
folders whose path is not already present, or explicitly allow both and emit a
`private` flag), and make `folder_page`/`file_page` use the same resolution
rule. Derive the summary counts from the merged dicts so the header and the
shelf agree. Add a test with both dicts populated.

### F6 — Keeping into a second kind is silently ignored; one `kind` cannot express both crates
`pynicotine/digging/crate.py:85-92` and `:117-128` ·
`pynicotine/engineapi/server.py:599-608`, `:702-713` ·
`native/TribeSeek/Sources/TribeSeek/AppModel.swift:626-644`

**Why it matters.** `Crate.add` dedupes on `(username, virtual_path)` and
returns the existing track **without comparing kinds**. Verified:

~~~
c.add(sample) -> id X
c.add(..., kind="dj") -> id X, kind == "sample", by_kind("dj") == 0
~~~

So the deck's DJ button (or `keepBin(kind:"dj")`) on a track already kept as a
sample returns the sample entry, reports success, and the DJ crate stays
empty. The user has no feedback that their choice was discarded. The single
`kind` field also means "in both crates" is unrepresentable, and
`set_kind` destroys the old membership — which is fine if the product really
means "file this track in exactly one crate", but not if a track can be both a
sample and a set tool. The ledger stores the same single `kind` per track
(`rolodex.py:58-66`), so the collective cannot have different filing for
different members either.

**Suggested fix.** Decide the model and enforce it:

- If a track belongs to one crate: make `Crate.add` update `kind` when the
  existing entry differs (and return whether it changed), and have the keep
  endpoints report the change so the deck can say "moved to DJ".
- If a track can be in both: store `kinds: set[str]` (or a `(track, crate)`
  membership list) and make `set_kind` add/remove rather than replace. Keep the
  file single; it is not the file layout that is wrong, it is `kind` living on
  the track instead of on the membership. In the ledger, make `kind` a
  per-member field alongside `found_by`.

Add a test for `add(same path, kind="dj")` because the current test only
asserts id idempotence (`test_crate.py:7-14`).

### F7 — An API-only session never starts the pipeline, so "separating when it lands" is false
`pynicotine/engineapi/server.py:715-726` · `pynicotine/gtkgui/mainwindow.py:370-372` ·
`pynicotine/digging/service.py:43-52` · `docs/ENGINE-API.md:251-253` ·
`native/TribeSeek/Sources/TribeSeek/AppModel.swift:626-644`

**Why it matters.** `PipelineService.start()` is what connects the
`update-download`/`clear-download` listeners that trigger separation. It is
called from GTK startup and from the explicit
`POST /crate/<id>/separate` endpoint, and nowhere else. The native app launches
the engine headless (`run.sh`, `EngineSupervisor.swift:102-112`), never opens
the GTK window, and never calls `start_service` on keep. Therefore:

- keeping a track downloads it and stops; no stems, no Live set;
- `POST /crate/<id>/separate` is the only trigger, and pressing it before the
  download completes does nothing in the moment (`kick` bails when
  `_local_path` is missing, `service.py:54-60`), although it does start the
  listener so a later finish is caught.

The API doc promises "lets the pipeline separate when the download finishes"
(`ENGINE-API.md:251-253`) and the deck says "separating when the download
lands" (`AppModel.swift:634-636`). Neither is true until someone presses
Separate now once.

**Suggested fix.** Start the service when the API starts (in
`server.maybe_start`/`start`, on the engine thread), and/or on the first keep
inside `keep_source`. Pass it a settings **provider** rather than a snapshot
(F30). Add a test that a `FINISHED` download event for a kept track launches
the pipeline without a manual separate.

### F8 — Settings accept arbitrary paths; one bad `work_dir` bricks every crate call and persists
`pynicotine/digging/settings.py:81-125`, `:229-239`, `:287-292` ·
`pynicotine/digging/actions.py:45-48` · `pynicotine/engineapi/server.py:629-647`

**Why it matters.** `apply_settings` validates *types* and enum-like strings
but never touches the filesystem. It also never normalises: `expanduser` is
applied in `work_path`/`output_path`/`export_path` (`settings.py:260-285`),
but not to `rolodex_path`, `observatory_root`, `live_app`, or any of them at
write time. So:

~~~
POST /settings {"work_dir": "/Volumes/Gone/Work"}
200 OK  -> saved to digging.json
GET /crate  -> crate_for() -> settings.ensure_dirs() -> FileExistsError/PermissionError -> 500
POST /audition/<id>/keep -> 500
~~~

Every crate read and write goes through `crate_for()` → `ensure_dirs()`
(`actions.py:45-48`), so the Crates screen and the keep path are both dead
until the settings file is fixed by hand — and the bad value survives a restart
because it was already persisted by the successful POST. A read-only
`rolodex_path` similarly makes `POST /rolodex/star` return 500 while the star
is lost. An unwritable `export_dir` breaks exports much later.

**Suggested fix.** In `apply_settings` (or immediately after, before
`save()`): expand `~`, insist on absolute paths for `work_dir`,
`output_dir`, `export_dir`, `rolodex_path`, attempt `mkdir(parents=True,
exist_ok=True)` and a write probe, and reject with a 400 naming the path.
Validate the whole payload into a candidate dict first, then apply, so a
failed patch leaves nothing half-applied. Keep `ensure_dirs()` as a runtime
safety net, but surface its failure as a 400 at patch time, not a 500 at keep
time. Add tests for a non-writable dir and for `~`.

### F9 — Secrets are stored 0644 in plaintext and cannot be cleared through the API
`pynicotine/digging/settings.py:312-323` and `:87-91` ·
`native/TribeSeek/Sources/TribeSeek/SettingsModel.swift:79-81` ·
`native/TribeSeek/Sources/TribeSeek/Screens/RigScreen.swift:118-135`

**Why it matters.** `DiggingSettings.save` writes the whole dataclass, tokens
included, with default permissions. On this machine `.dev/digging.json` is
`-rw-r--r--` — any local process or user on the box can read the MVSEP and
studio-PC tokens once they are set. There is also no way to remove a token: the Rig sends a token
only when the field is non-empty (`SettingsModel.swift:79-80`), and the
SecureField shows the placeholder "•••••• set" with empty text, so clearing the
field and saving is indistinguishable from "leave it alone". The engine *would*
accept `""` to clear (`settings.py:87-91`), but no client sends it.

Masking on read is otherwise right: `public_settings` returns only
`*_set` flags (`settings.py:61-78`), and there is no endpoint that echoes a
token back.

**Suggested fix.**

- Write `digging.json` with `0o600` (open with `os.open(..., 0o600)` or
  `chmod` after the replace), and consider the Keychain for the tokens.
- Add an explicit clear: a `mvsep_token_clear: true` / `pc_token_clear: true`
  field (or allow the client to send `""`), plus a "Clear token" button in the
  Rig when `*_token_set` is true.
- Document the write-only contract in `ENGINE-API.md` and add a test that
  `public_settings` never contains a secret, including nested structures.
- Note the PC token travels over plain `http://` to `pc_url`
  (`renderers/pc_agent.py:36-59` sends `Authorization: Bearer` with whatever
  scheme `pc_url` uses); if the studio PC is on an untrusted LAN, that is the
  token's real exposure.

### F10 — The shared ledger rewrites the whole file; a synced folder loses entries and steals credit
`pynicotine/digging/rolodex.py:52-102` (and `:58-66`, `:100-102`) ·
`pynicotine/tests/unit/digging/test_rolodex.py:7-21`

**Why it matters.** `Ledger.add` re-reads before writing, which narrows the
window but does not close it:

- The write is a **whole-file** replacement. Two machines pointing at the same
  Dropbox/iCloud folder each compute their own file from their own read; the
  later rename wins outright, and the other member's keep is gone. Re-reading
  does not help when the other write lands after the read.
- The temp path is **fixed** (`rolodex.json.tmp`). Two processes on the same
  machine (GTK + a second engine, the CLI, two app instances) can collide on
  the temp file, producing `FileNotFoundError` from `replace` or one member's
  contents replacing the other's before the rename.
- A sync client can also surface a **conflict copy** (`rolodex 2.json`).
  `load()` reads only the exact path, so those entries become invisible.
- `save()` offers no merge and no revision. The docstring says "last-write-wins
  per (peer, virtual_path)", but the code is last-write-wins for the **whole
  file**, and it also overwrites `found_by` with the latest keeper. The test
  suite codifies that: the second member's keep changes `found_by` from
  `santero` to `mara` (`test_rolodex.py:7-21`). In a collective, the person
  who found the track losing credit to whoever re-kept it is the wrong default.

**Suggested fix.** Make the unit of merge the entry, not the file: one file per
entry (`rolodex.d/<peer-hash>-<path-hash>.json`) written with a unique temp
name, or an append-only `rolodex.log` plus periodic compaction. If one file
must stay, do a read-merge-write under an advisory lock (and accept that sync
does not honour locks): merge by key with an `updated_at`/`rev` per entry,
union `found_by` (keep a set or at least the first finder), and write with
`tempfile.mkstemp` + `fsync` before `os.replace`. On load, also read
`rolodex *.json` conflict copies and merge them. Add a test with two writers
interleaved and a test that `found_by` survives a re-keep.

### F11 — Stars: another member's star cannot be removed, and member identity collides by default
`pynicotine/digging/rolodex.py:73-93` ·
`native/TribeSeek/Sources/TribeSeek/RolodexModel.swift:103-117` and `:159-174` ·
`pynicotine/digging/settings.py:120-121` and `:246-250`

**Why it matters.** The engine's key `(peer, "star:<member>")` does let two
members star independently, and unstar removes only the caller's key. The
client breaks that contract:

- `load()` unions **every** ledger star into the local `starredPeers`
  (`RolodexModel.swift:109-110`), losing who starred it.
- `toggleStar` then sends `starred: false` with **this** member's name. If the
  star belongs to Bob, Alice's unstar deletes Alice's (nonexistent) entry, the
  UI flips for a moment, and the next load re-unions Bob's star. From Alice's
  seat, the peer cannot be unstarred.
- The one-time migration (`RolodexModel.swift:112-116`) pushes local stars to
  the ledger. Because `starredPeers` now contains Bob's stars too, any path
  that persists that set (`toggleStar` writes it to UserDefaults,
  `RolodexModel.swift:173`) can later re-push Bob's star as Alice's — undoing
  his unstar.
- Identity is weak: `member_name` defaults to `$USER` or `"unknown"`
  (`settings.py:246-250`). Two machines with the same account name, or any two
  machines that both fell back to `"unknown"`, share a star key and a
  `found_by`, so one member's unstar removes the other's star outright.
  `apply_settings` only rejects whitespace (`settings.py:120-121`).
- The key is collision-free for normal paths, but a root-level file literally
  named `star:<member>` would share the tuple.

**Suggested fix.** Model stars as first-class, attributed state:
`stars: {peer: [member]}` (or entries with `kind:"star", found_by` and no
`virtual_path`). The client should show "starred by Bob" and allow unstar only
for stars it owns, or send an explicit `member`/owner in the unstar request
and verify the server-side entry. Never union ledger stars into the local set
without attribution; remove local stars that no ledger entry holds. Give each
install a persisted member id (UUID) for keys, with the display name separate,
and reject duplicate display names when the ledger is shared. Add a test for
"A stars, B stars, A unstars, B's star remains" at the client-model level and
at the API level.

### F12 — A `~` ledger path creates a literal `~` directory; the Rig invites exactly that
`pynicotine/digging/rolodex.py:26-29` and `:95-102` ·
`native/TribeSeek/Sources/TribeSeek/Screens/RigScreen.swift:74-85`

**Why it matters.** `Ledger.__init__` does `Path(path)`, with no
`expanduser()`. `save()` then does `self.path.parent.mkdir(parents=True)`,
so a path typed as `~/Documents/Tribe Seek/rolodex.json` creates a directory
named `~` **under the engine's working directory** (verified) and writes the
ledger there. The Rig's placeholder is literally
`~/Documents/Tribe Seek/rolodex.json` (`RigScreen.swift:75`), so the
placeholder teaches the breaking input. "Reveal ledger" then passes the raw
string to `NSWorkspace` (`RigScreen.swift:81-85`), so Finder opens nothing.
The engine happily reports a path that is not where anyone expects, and pointing
it at a synced folder fails silently.

**Suggested fix.** `Path(path).expanduser()` in `Ledger.__init__` (and
resolve to absolute), plus `expanduser` in `apply_settings` for every path
field (F8). Change the placeholder to an absolute example or one without `~`.
Have "Reveal ledger" expand the path too, and prefer the resolved path the
engine reports in `GET /rolodex`.

---

## P2 — correctness and robustness

### F13 — `folder_page` can return a torn page: old `total` with zeroed folder rows
`pynicotine/userbrowse.py:235-264` · `:109-113` · `:705-724` ·
`pynicotine/engineapi/server.py:333-341`

**Why it matters.** The route runs `core.userbrowse.folder_page(...)` directly
on the HTTP thread (`server.py:333-341`); the writer runs on the engine thread
(`_shared_file_list_response`, reached via `events.emit_main_thread`,
`userbrowse.py:195-201` / `:705-724`). They are unsynchronised.

The reader takes `total = len(folders)` and a slice of the folder keys from a
snapshot, then resolves each folder's file list with `.get()`. A re-browse
calls `BrowsedUser.clear()`, which **mutates the dicts in place**
(`userbrowse.py:109-113`), so an interleaving can give a page where `total`
is the old count but every detail row is `[]` — `audio_files: 0`, `size: 0`,
`duration: 0`. The client has no way to distinguish that from an empty peer,
and `loadFolders` treats an empty page as "done" (`BrowserModel.swift:396-398`),
so a torn page can also truncate the shelf (F4). `_shared_file_list_response`'s
incremental `.update()` likewise yields aggregates that are correct for the
part of the share that has landed, which the client cannot tell from complete.

**Suggested fix.** Make the read snapshot-consistent: in
`_shared_file_list_response`/clear, build **new** dicts and swap the attribute
(`browsed_user.public_folders = {**old, **new}`) instead of mutating in place;
in `folder_page`, bind `public = browsed_user.public_folders` once and use
only that; add a `generation` integer bumped on clear/response and return it
in the payload so a client can discard pages from a superseded browse. Add a
test that clears between two `folder_page` calls (or injects a clear between
the key snapshot and the detail loop) and asserts no zeroed rows.

### F14 — Aggregates are recomputed per request and the client materialises every folder
`pynicotine/userbrowse.py:235-264` · `native/TribeSeek/Sources/TribeSeek/BrowserModel.swift:372-399`

**Why it matters.** Raw compute is cheap: 100 000 files aggregate in ~24 ms
(measured). That is not the problem. The problems are:

- It is recomputed on **every page request and every refresh**, and the cost is
  paid on the HTTP thread holding the GIL. The client's paging loop is serial
  (`BrowserModel.swift:379-399`), so a 100 000-**folder** share (500 per page)
  is 200 round-trips, ~200 × 500 rows of JSON, and 100 000 `FolderRow` structs
  with dictionaries on the main actor before anything is shown. `sortedFolders`
  then re-sorts all of them on every body pass (`BrowserModel.swift:154-182`),
  and `filteredFolders` re-filters.
- The client only needs the top N bins for the default sort, but must fetch
  everything to know which they are.

**Suggested fix.** Cache the aggregate per browse generation: a
`dict[str, dict]` on `BrowsedUser`, invalidated when a response arrives or the
user is cleared; `folder_page` then slices the cache and never re-iterates
files. Add server-side sort (`?sort=size|audio|name`) with a stable secondary
key, and a `limit`-only "top bins" mode. Have the client use the engine's sort
for the default view and fetch the rest lazily. Include `audio_size` and a
folder fingerprint in the payload (F20) while you are there.

### F15 — The `_invoke` timeout is not a cancellation: a failed POST may still have applied
`pynicotine/engineapi/server.py:154-191` · `:641-647` ·
`pynicotine/headless/application.py:52-53`

**Why it matters.** `_invoke` queues the callback on the engine thread and
waits for an `Event` with an 8 s timeout. On timeout it raises
`TimeoutError` → the handler returns a 500, but the queued `runner` is still
in the queue and **will run later**. So `POST /settings` can report failure and
then save; a keep can report 500 and still create the crate entry and start the
download. The client retries, producing duplicates (partly masked by dedupe)
and a UI that lies about what happened. The engine loop ticks every 100 ms
(`headless/application.py:52-53`, `events.py:332-354`), so the timeout is
only reached when the engine thread is blocked — for example on a synchronous
promote copy (F1) or a huge JSON body — exactly when a duplicate retry is
likely.

**Suggested fix.** Treat a timeout as "busy, retry" rather than "failed": return
503 with `Retry-After` and no side effect, or make each mutating handler
idempotent with a client-supplied request id. At minimum, distinguish
"queued but unknown" in the error text and document that a 500-mid-mutation may
have applied. Also consider lowering the timeout impact by doing the heavy work
(aggregates, crate saves) off the engine thread under a lock instead of on it.

### F16 — One malformed attribute type turns a whole folder page into a 500
`pynicotine/userbrowse.py:82-86`

**Why it matters.** `_folder_info` does `if length and length > 0: duration += length`
without checking the type. `SharedFile` attributes come from the protocol
(usually ints) but also from disk-cached shares lists, where
`_run_task_parse_disk` validates `size` but passes attribute values through
untouched (`userbrowse.py:583-629`). A single `"3:45"` in a cached list makes
`length > 0` raise `TypeError`, and the route catches it as a 500 for the
**entire page** (`server.py:286-287`). The client's `try?` then treats the
page as empty and stops paging, so one bad row hides the rest of the share.

**Suggested fix.** Coerce defensively (`isinstance(length, (int, float))`,
`float(length)` in a try), skip non-numeric values, and count them in a
`skipped` field or log once. Add a test with `length="3:45"` and `size=None`.
The same treatment is worth applying to `file.size`.

### F17 — Summary counts are overwritten per response message and disagree with the folder list
`pynicotine/userbrowse.py:709-724` · `:225-233`

**Why it matters.** `_shared_file_list_response` merges each message into the
dicts but sets `browsed_user.num_folders = len(msg.public_folders) + ...` and
`num_files = <sum for this message>` — the counts of the **last message**, not
the accumulated share. The doc and the hub both anticipate multi-message shares
(`ENGINE-API.md:97-100`, `hub.py:282-297`), so a peer answering in several
chunks ends with `summary.folders` < the real folder count while
`folder_page.total` is the merged count. The shelf header (from `summary`) and
the bin list then disagree, and `BrowserModel.browse`'s "wait until
`folders > 0`" can fire on a one-folder fragment.

**Suggested fix.** Accumulate (`+= len(msg.public_folders) + ...`) or, better,
derive the summary entirely from the merged dicts at read time (and add a
`complete`/`generation` field that the browse-settled event flips). Add a test
that feeds two responses and checks that the counts accumulate.

### F18 — Folder names containing `&` or `+` open the wrong folder (verified)
`native/TribeSeek/Sources/TribeSeek/Engine/EngineClient.swift:169-171` and `:416-418`

**Why it matters.** `files(user:folder:)` builds the query by hand and
URL-encodes the folder with `.urlPathAllowed`. That set leaves `&` and `+`
unchanged (verified with the toolchain: `"Simon & Garfunkel + Friends"` →
`Simon%20&%20Garfunkel%20+%20Friends`). The server parses the query with
`parse_qs` (`server.py:115-117`), so:

- `folder=Simon & Garfunkel` is split into `folder=Simon ` plus a stray key;
- `folder=C++` decodes to `C  ` because `+` means space.

Both are common in music shares. The lookup then returns `total: 0`, the file
pane is blank, and no error is shown — it looks like an empty folder. The
crate `kind` query uses `.urlQueryAllowed` (`:208-214`), which has the same
problem, though the values are only `sample`/`dj` today.

**Suggested fix.** Build query strings with `URLComponents`/`URLQueryItem`
(or a custom allowed set = `.urlQueryAllowed` minus `&=+?`). Never hand-roll
the query. Add a unit test for `"Simon & Garfunkel"`, `"C++"`, and a folder
with a space, asserting the server-side `_query()` sees the exact name.

### F19 — `loadFiles`/settle races can show folder A's files under folder B
`native/TribeSeek/Sources/TribeSeek/BrowserModel.swift:416-431` and `:458-468` ·
`native/TribeSeek/Sources/TribeSeek/Screens/BrowseDetail.swift:151-174` and `:312-325`

**Why it matters.** `loadFiles` sets `selectedFolder` and clears `files`
before awaiting the network. If the user clicks bin A then bin B, both requests
are in flight; whichever returns last assigns `files`, and `selectedFolder`
already says B. A slower A overwrites B's contents, so the pane, the inspector
header (`folders.first(where: name == selectedFolder)`), the audition
(`BrowseDetail.audition` uses `selectedFolder`) and the play buttons all point
at B while showing A's rows. `loadMoreFiles` then pages B with
`offset = files.count` from A's list, producing duplicates or skips.
`loadFolders` has the same shape for peer switches (two overlapping loads, no
"am I still the selected user" check after each await). `ForEach` keys rows by
`SharedFileRow.id == name` (`EngineModels.swift:106`), so duplicate pages can
also produce duplicate IDs inside one `ForEach`.

**Suggested fix.** Add a monotonically increasing `loadGeneration` to
`BrowserModel`; capture it at the start of `loadFiles`/`loadFolders` and
drop the result if it changed or if `selectedUser`/`selectedFolder` no longer
match. Cancel the previous task. Reset `selectedFile` when the folder changes.
Dedupe on append by `id` (and consider a composite id of folder+name).

### F20 — Count+bytes is the wrong fingerprint: it misses swaps and is tripped by cover art
`native/TribeSeek/Sources/TribeSeek/BrowserModel.swift:184-212` ·
`pynicotine/userbrowse.py:88-96`

**Why it matters.** Soulseek's browse gives a folder's `(name, size,
attributes)` list, so a fingerprint is available; count+bytes is the weakest
one. It:

- misses a file replaced by a different rip of exactly the same size, and any
  rename that preserves count and total size;
- is **tripped by non-audio files**: the baseline uses `folder.size` (all
  files, including cover JPEGs and cue sheets), so a peer adding `cover.jpg`
  marks a fully dug album as "new";
- ignores the audio-only counts the engine already computes
  (`audio_files`, `lossless`, `audio_formats` are in the payload but not the
  snapshot).

The brief asks whether count+bytes is the best Soulseek allows. It is not: the
file names and sizes are in hand at browse time.

**Suggested fix.** Have the engine return an audio-only `audio_size` and a
short stable `fingerprint` per folder — e.g.
`blake2b("\n".join(sorted(f"{name}\t{size}" for audio files)), digest_size=8).hexdigest()`
— computed in the same pass as `_folder_info` (cheap, and cached per F14).
Store `{audio_files, audio_size, fingerprint}` in `SeenSnapshot`; a folder is
fresh when it is new or the fingerprint changed. This catches swaps, ignores
artwork, and survives reordering. Keep count+bytes as a fallback for older
engines.

### F21 — Rolodex counts every local keep twice and reports your own keeps as "crew"
`native/TribeSeek/Sources/TribeSeek/RolodexModel.swift:180-227` (esp. 207-227)

**Why it matters.** `build()` first counts the local crate (`keeps`, `dj`,
`sample`, `folders`, `lastAdded`) and then adds **every** ledger entry,
including the ones this member wrote when they kept the same track. There is no
`found_by == member` filter and no dedupe against the crate. So a solo member
who kept one track sees "1 KEEPS · 1 CREW · 0 DJ", and `folderCount` and
`topFolder` count each keep twice, which can also flip the top folder on ties.
`testRolodexGroupsKeepsBySource` never sets `ledger`, so it cannot catch this.

**Suggested fix.** Skip ledger entries whose `found_by` is the current member
for `crew`, and/or skip entries whose `(peer, virtual_path)` is already in the
crate. Count `crew` as the number of *other* members (distinct `found_by`)
rather than entries, which is what the label "N CREW" reads as. Add the
member + ledger cases to the existing test.

### F22 — Rolodex statuses are fetched once and never refreshed; 120 sequential requests per load
`native/TribeSeek/Sources/TribeSeek/RolodexModel.swift:126-157` ·
`pynicotine/users.py:166-175` and `:423-425`

**Why it matters.** `refreshStatuses` only writes `statuses[name]` when it is
`nil` (`:145`), so once a peer has been seen the dot never changes for the
life of the model — a seller who went offline still shows green. It also
requests status for 120 peers one `await` at a time before polling, on every
load. On the engine side, `request_user_status` sends a bare `WatchUser`
without registering a watch context (`users.py:170-175`), and
`_user_status` stores every status forever (`users.py:423-425`), so the
dictionary and the server-side watch list grow for the session and can only be
released by a disconnect (`unwatch_user` only touches tracked contexts,
`users.py:221-252`).

**Suggested fix.** Re-read every name on each refresh (the engine already holds
fresh values for watched users); don't skip known keys. Ask the engine in one
batch (`POST /users/status` with a list) and poll the batch. On the engine,
record a `status-lookup` watch context and expire it (TTL or LRU, say 500
entries / 10 minutes), or drop the watch when the Rolodex unloads. Add a test
that a second refresh updates an already-known status.

### F23 — The collapsed transport destroys its whole view identity 30 times a second
`native/TribeSeek/Sources/TribeSeek/Shell/Transport.swift:12` and `:94` ·
`native/TribeSeek/Sources/TribeSeek/Screens/AuditionDeck.swift:37-47` and `:227-239`

**Why it matters.** The transport's `TimelineView` re-evaluates every 1/30 s
and the `HStack` carries `.id(timeline.date.timeIntervalSince1970)`
(`Transport.swift:94`). A changing `.id` makes SwiftUI tear down and rebuild
that subtree on every tick: the play button's pressed state, hover state, any
popover, and — critically — **keyboard focus** are destroyed 30 times a second.
The drag handle is re-created mid-drag. It also rebuilds 240 waveform bars and
the time labels per frame. The expanded ribbon avoids the `.id` but still
re-runs the entire header (including `AsyncImage`), the waveform and the
ribbon through `TimelineView` (`AuditionDeck.swift:37-47`), recomputing
`compactPeaks` (an O(peaks) allocation, `:227-239`) 30 times a second.

**Suggested fix.** Delete the `.id(...)`; it is not needed and is actively
harmful. Isolate the moving parts: a small subview whose body is only the
playhead/time/position, driven by `TimelineView`, or a `Canvas` that reads the
player position; leave the buttons, artwork and chips outside the timeline.
Cache the downsampled peaks (compute once per loaded file, store on the
player). Update the progress at 30 Hz only where it is visible. Add a manual
test: Tab into the collapsed transport, wait, confirm focus survives, and drag
the handle for several seconds.

### F24 — The drag handle offers a truncated `INCOMPLETE…` preview file to Ableton
`native/TribeSeek/Sources/TribeSeek/Audio/AuditionPlayer.swift:42-48` ·
`native/TribeSeek/Sources/TribeSeek/Shell/Transport.swift:147-169` ·
`native/TribeSeek/Sources/TribeSeek/Screens/AuditionDeck.swift:164-181` ·
`docs/ENGINE-API.md:244-249`

**Why it matters.** The engine's peer source is the growing
`INCOMPLETE…` file (`ENGINE-API.md:236-242`), and the player loads that path
so it can play partial audio. `localFileURL` returns **any** existing local
path, including that partial file, and the deck's drag handle is enabled
whenever it is non-nil, with the help "Drag into Ableton or Finder". Dragging a
partial file into Live yields a truncated/corrupt sample (or an import error)
that looks like a real track. The same applies to a finished *preview* file
before it is promoted (F1).

**Suggested fix.** Only expose the drag handle when the source is complete:
`state.source?.kind == .local`, or `kind == .peer && complete`, or the crate
track has a `local_path`. Otherwise show the handle disabled with "waiting for
the download". The player can keep playing the partial; it should not advertise
it as a deliverable.

### F25 — The dig scroll never fires and a stale file selection makes Return a no-op
`native/TribeSeek/Sources/TribeSeek/Screens/BrowseDetail.swift:197-208`, `:11`,
`:345-352` · `native/TribeSeek/Sources/TribeSeek/BrowserModel.swift:435-455`

**Why it matters.** `focus(folder:)` awaits `loadFiles` and only then sets
`scrollToSelection = true` (`BrowserModel.swift:439-451`). `selectedFolder`
changed *during* `loadFiles`, so the `.task(id: selectedFolder)` already ran
while the flag was still `false` and returned at the guard; setting the flag
does not retrigger the task because the id did not change. The grid therefore
does not scroll to the dig target in the common case — and because the flag is
never cleared, the **next** manual bin click scrolls unexpectedly.

Separately, `selectedFile` is `State` in `BrowseDetail` and is never reset
when the folder changes (`:11`, `:316-324`). After switching folders, Return
looks up the old id in the new `files` list, finds nothing, and returns
`.ignored` (`:345-352`), so Enter appears dead until the user clicks a row.
If the new folder happens to contain the same name, Return auditions a file the
user never selected.

**Suggested fix.** Set `scrollToSelection = true` **before** the `loadFiles`
await, or drive the scroll from `.task(id: scrollTarget)` / `.onChange(of:
scrollToSelection)` and clear it in the same block. Reset `selectedFile` (and
the focus) whenever `model.browse.selectedFolder` changes, and clamp it to the
new list.

### F26 — Bin sort comparators have no stable tiebreak; bins can reshuffle
`native/TribeSeek/Sources/TribeSeek/BrowserModel.swift:154-182`

**Why it matters.** `.files` sorts only by `count >` and `.fresh` falls back
to ratio then count, with no name tiebreak. Swift's `sort` is not documented as
stable, so equal items may come out in any order, and the order can change
between body passes as `fresh`/filtered values change. In a `LazyVGrid` of
`Button`s keyed by name this makes bins jump under the pointer and can lose the
scroll position while the user is aiming at a card. `.promising` does include a
name tiebreak, so it is the only deterministic one.

**Suggested fix.** Give every comparator a final
`localizedStandardCompare(name)` tiebreak (and decide whether the bin list
should be ordered by path rather than title). Precompute the sorted array once
per change in the model rather than recomputing it for each body read.

### F27 — The peer list grows duplicates, and the `ForEach` keys on the username
`native/TribeSeek/Sources/TribeSeek/AppModel.swift:400` ·
`native/TribeSeek/Sources/TribeSeek/Screens/BrowseColumn.swift:35` ·
`native/TribeSeek/Sources/TribeSeek/BrowserModel.swift:288-293`

**Why it matters.** Every `AppModel.browse(user:)` and every dig does
`browse.users.insert(user, at: 0)` with no dedupe. Digging the same seller five
times adds five rows. `adoptBrowsedUsers` dedupes, but it is only called once
at startup. The Switch peer list renders `ForEach(filteredUsers, id: \.self)`,
so duplicate IDs are explicitly undefined behaviour in SwiftUI (rows can
duplicate, disappear, or animate wrongly), and the list becomes unusable after a
digging session.

**Suggested fix.** Remove any existing entry before inserting, or keep an
ordered set: `users.removeAll { $0 == user }; users.insert(user, at: 0)`. Cap
the list or move it to the engine's browsed-user list. Key the `ForEach` by a
stable id anyway.

### F28 — "Keep all" only keeps the first 500 loaded files and skips formats the engine counts
`native/TribeSeek/Sources/TribeSeek/Screens/BrowseDetail.swift:257-266` and
`:279-286` · `pynicotine/userbrowse.py:48-52`

**Why it matters.** The inspector's "Keep all" passes `playableFiles`, which
filters `model.browse.files` — only the **currently loaded page** (500) — not
`fileTotal`. A folder with 1 200 tracks silently keeps 500 while the help text
says "Keep every audio file in this bin". The Swift extension set also omits
`wma`, `ape`, `wv`, and `alac`, which the engine counts as audio
(`userbrowse.py:48-52`), so a WMA bin reports "27 FILES / WMA 27" but Keep all
keeps nothing and reports success with count 0.

**Suggested fix.** Page the folder before keeping, or (better) add a
folder-scoped keep to the API: `POST /crate/keep` with `{username, folder,
kind}` and let the engine expand the folder's audio files from the browse cache
— which also fixes the post-audition preview-transfer loss in F1. Share the
engine's audio extension list with the client (or return a `playable` flag per
file) instead of keeping two lists.

### F29 — Keeping your own share downloads your own file and never records `local_path`
`pynicotine/engineapi/server.py:805-829` · `pynicotine/engineapi/audition.py:328-354` ·
`pynicotine/digging/actions.py:92-98`

**Why it matters.** For our own shares `_create_audition` finds the real file
on disk and sets `session.local_path` (`server.py:809-819`), so the session
plays the local file. But `AuditionSession.keep` builds a `TrackSource` with
no local path and calls `keep_source` with `peer=None` (`audition.py:336-349`),
so `keep_source` queues `enqueue_download` for our own username. Nicotine+
will either reject the self-download or fetch a copy from the network, and the
crate track has `local_path == ""` — so the pipeline's `_local_path` cannot
find the file (it looks in `downloads/<user>`, not in our share) and never
separates it. Keeping your own test file is a common debugging path, and it
appears to do nothing.

**Suggested fix.** Pass `local_path` through `TrackSource`/`keep_source`;
when it points at an existing file, set `track.local_path` and skip the
download. If the file is a local share, copy or reference the real path (do not
copy into downloads) and notify the pipeline. Add a test for a local-source
keep.

### F30 — The pipeline service freezes settings at first keep; Rig changes split to the old folder
`pynicotine/digging/service.py:35-36` and `:206-213` ·
`pynicotine/digging/actions.py:45-48` and `:103-107`

**Why it matters.** `SERVICE = PipelineService()` runs at import and captures
`DiggingSettings.load()` then. The module is first imported by `_notify`
during the first keep (`actions.py:103-107`), so the service locks in the
settings as they were at that moment. `start_service()` is only called with new
settings by GTK; the API calls `start_service()` with no argument
(`server.py:725`). After a Rig change to `work_dir`, `renderer`, or
`output_dir`:

- the service still writes status/crate to the **old** `work_path`
  (`service.py:131-144`), so the track's status updates land in a crate file
  the UI no longer reads (the track appears stuck at "kept");
- separation output goes to the old folders;
- `_local_path` looks in the old downloads folder (`service.py:105-116`).

This is invisible until a user changes the Rig and wonders why nothing happens.

**Suggested fix.** Give the service a settings provider (callable) or reload
`DiggingSettings.load()` at the start of each `_process`, and store the crate
path used on the track/result. Call `start_service(settings)` when the settings
endpoint saves, or simply have the service always read the current file.

---

## P3 — polish, contract, security posture

### F31 — The Rig and Rolodex load twice and can clobber edits
`native/TribeSeek/Sources/TribeSeek/Screens/RigScreen.swift:31` ·
`native/TribeSeek/Sources/TribeSeek/AppModel.swift:218-230` ·
`native/TribeSeek/Sources/TribeSeek/SettingsModel.swift:42-55`, `:95-115` ·
`native/TribeSeek/Sources/TribeSeek/Screens/RolodexViews.swift:40`

Entering the Rig or the Rolodex triggers both `activateSection`
(`AppModel.swift:218-230`) and the view's `.task` (`RigScreen.swift:31`,
`RolodexViews.swift:40`), so the model loads twice. Two `rolodex.load()` calls
each run the star migration (two writes per local star) and each polls 120
statuses. Two `settings.load()` calls can resolve *after* the user has started
editing, and `adopt` overwrites the fields (`SettingsModel.swift:95-115`) —
including a token the user just typed, which is not cleared by `adopt` and may
be saved later with unrelated edits. The screen's whole-object POST is a PUT, so
two clients editing the Rig overwrite each other wholesale.

**Suggested fix.** Keep loading in one place (`activateSection`), add a
`.task { if !hasLoaded { await load() } }` guard or a dirty flag, and don't
adopt over unsaved edits. Send only changed fields (a real patch) so unrelated
settings don't ride along.

### F32 — Contract drift: `/crate/keep` undocumented, `kind` missing, no API version
`docs/ENGINE-API.md:43-46`, `:263-272` · `pynicotine/engineapi/server.py:649-700` ·
`native/TribeSeek/Sources/TribeSeek/Engine/EngineClient.swift:114-116` ·
`native/TribeSeek/Sources/TribeSeek/Engine/EngineModels.swift`

- `POST /crate/keep` is used by Keep all but is not in the endpoint table
  (`ENGINE-API.md:43-46` only lists `/crate/<id>/separate`, `kind`, `DELETE`).
- The "Crate track" data shape omits `kind` (`ENGINE-API.md:268-269`) even
  though every payload includes it.
- `GET /settings` and `POST /settings` shapes are not documented (the brief's
  update introduced them); there is no documented clear-token behaviour.
- The folders payload changed from a map to an array with audio fields, and
  there is no `api_version` anywhere. The client can point at an existing
  engine (`NICOTINE_API_URL`, `EngineSupervisor.swift:48-57`), and all
  decoding goes through `try?` (`EngineClient.swift:114-116`,
  `EngineEvent.decode` `:12-14`), so a shape mismatch is an empty shelf or a
  silent no-op rather than an error.
- `GET /events`'s `crate` payload is described as "the crate track fields that
  changed" but `serialize.crate_track_dict` omits `kind`; the Swift handler
  only uses `trackId/status/error`, so it is latent.

**Suggested fix.** Document `/crate/keep`, the settings shapes and the token
clear. Add `"api": 2` (or a date) to `/health` and have the client refuse an
incompatible engine with a human message. Replace blanket `try?` for page
decodes with a surfaced error banner ("engine returned an unexpected
response — update the app or engine"). Keep the Swift models in one place and
add a decode test for the folders page.

### F33 — The client ignores `gap` events, so a dropped SSE connection leaves stale state
`native/TribeSeek/Sources/TribeSeek/Engine/EngineClient.swift:383-403` ·
`native/TribeSeek/Sources/TribeSeek/AppModel.swift:253-348` (default at 346) ·
`docs/ENGINE-API.md:109-112`

The server emits `{"type":"gap","dropped":N}` when a client falls behind
(2048-event buffer). The client decodes the event and ignores it (no `case
"gap"`), so the audition deck and transfer counters can be permanently stale
after a stall (e.g. the app was backgrounded or the engine was busy). Add a
`gap` handler that re-reads `GET /audition/<id>`, `GET /state` and the
current page set, or at least shows "reconnected — refresh".

### F34 — The API fails open without a token and accepts text/plain state changes
`pynicotine/engineapi/server.py:104-113`, `:127-151`, `:876-877`, `:894-909`

If `NICOTINE_API_TOKEN` is unset, `_authorized` returns `True` for every
request. `maybe_start` starts the server whenever the port is set, token or
not, so a manually started engine (or one launched by a script that forgets the
variable) is fully open on loopback. Because `_body` ignores `Content-Type`
and `do_POST` checks only the bearer token, a web page in the user's browser can
issue a "simple" `text/plain` POST to `127.0.0.1:8766/settings` (no preflight)
and change `work_dir`/tokens or start a login; the server parses it as JSON.
There is no `Origin`/`Host` check, so DNS rebinding also applies. The native
app always passes `devtoken` (`EngineSupervisor.swift:111`), so the exposure
is the manual/scripted engine, but it is a sharp edge for a local API that
writes files.

**Suggested fix.** Fail closed: if no token is configured, generate one at
startup and print it (or refuse to start outside tests). Require
`Content-Type: application/json` for POST/DELETE and reject other types with
415. Reject requests whose `Origin` is present and not the app, and validate
`Host` is `127.0.0.1`/`localhost`. Keep the query token only for `/events`.

### F35 — Deck height maths: 144 pt of chrome inside a 154 pt frame
`native/TribeSeek/Sources/TribeSeek/Screens/AuditionDeck.swift:14`,
`:39-46`, `:286-295`

The ribbon is header 44 + (waveform 36 + top 8) + (ribbon 38 + top 8 +
bottom 10) = **144**, but `expandedHeight` is 154. The `VStack` (with the
chrome background and the `PanelRim`) is 144 tall inside a 154 frame, so it is
centred and leaves ~5 pt of uncovered workspace above and below the deck. Either
set the frame on the content or make the constant 144. The fixed ribbon widths
(112 + 310 + 138 + 188 + rules + padding ≈ 776) fit the 1 180 pt window minimum
(deck width ~1 107), but the catalogue cell is the only flexible one; at a
narrower window it will collapse to nothing rather than degrade.

### F36 — Minor UI/copy items

| Where | Issue | Fix |
|---|---|---|
| `native/TribeSeek/Sources/TribeSeek/Screens/BrowseColumn.swift:62` | `Text("“(model.browse.filter)” filters…")` is a **literal** — the interpolation backslash is missing, so the copy shows `(model.browse.filter)` | `Text("“\(model.browse.filter)” filters…")` |
| `native/TribeSeek/Sources/TribeSeek/Screens/AuditionDeck.swift:264-277` | The STEMS cell is `.disabled` exactly when `stems.isEmpty`, so the popover explaining "Keep the track to separate it into stems" can never open | Keep it enabled with the hint, or move the hint under the cell |
| `native/TribeSeek/Sources/TribeSeek/Screens/AuditionDeck.swift:446-455` | "KBPS" is derived from `size/duration`, ignoring the known bitrate, and vanishes when duration is unknown; a FLAC reads as ~1000 KBPS | Use `state.attributes.bitrate` when present; label FLAC by depth/rate |
| `native/TribeSeek/Sources/TribeSeek/Screens/AuditionDeck.swift:437-444` | The artist line trusts `catalogue.first` even at a low score (a wrong match is presented as fact) | Only show the match above a threshold; otherwise show the folder |
| `native/TribeSeek/Sources/TribeSeek/Screens/CrateViews.swift:98-106` | Stems are always four LEDs; a 2-stem or 6-stem preset reads as partial; `sortedStems` is recomputed four times per row | Use `track.stems.count` against the preset's count, or show the names |
| `native/TribeSeek/Sources/TribeSeek/RolodexModel.swift:35-37` | `topFolder` uses `max`, which returns an arbitrary one on ties, and the count is doubled by F21 | Tiebreak by name after fixing the counts |
| `pynicotine/engineapi/hub.py:338-342` | `_on_digging_status` publishes the crate event from whatever thread emits it; the HTTP thread and a pipeline thread can interleave payloads (the hub's own sequence lock is fine, but the fields come from a mutable track) | Snapshot the fields before publishing |
| `pynicotine/digging/settings.py:32-36` | `renderer_available("pc")` reports READY whenever `pc_url` is non-empty, and `mvsep` whenever token+type are set — neither checks reachability or token validity, so the Rig shows READY for a dead agent | Call `pc_agent`'s `/health` for pc (and a cheap MVSEP check) with a short timeout, or label it "configured" rather than "ready" |

---

## Answers to the brief's questions

**Is computing per-folder aggregates on every page request acceptable, or should
they be cached when the browse lands? What breaks at 100k files?**
The raw compute is not the problem: ~24 ms per 100 000 files. Compute it **once
per browse generation** anyway (F14), because the real costs are on the client
and in the paging protocol: a folder-heavy share becomes 200 serial requests,
100 000 `FolderRow`s with dictionaries on the main actor, and a re-sort of all
of them on every body pass. At 100 000 files the failure is an unresponsive
shelf with no progress and no cancellation, not CPU. Fix paging with a
server-side sort + top-N, and cache the aggregates keyed on a generation that is
bumped on clear/response.

**Is `folder_page` safe against a live browse mutating the same dicts?**
No, in the sense that it can return an internally inconsistent page (F13). It
will not raise (CPython list/dict snapshots are atomic enough), but
`clear()` mutates the same dicts in place, so old `total` with zeroed rows is
reachable. Make the writer swap immutable dicts, take one reference in the
reader, and add a generation the client can check.

**Is count+bytes the best "new since last visit" fingerprint Soulseek allows?**
No. The browse already gives name+size per file; use an audio-only
name+size digest plus audio bytes (F20). Count+bytes misses swaps and is
falsely tripped by cover art.

**Does the crate-kind design survive the collective ledger, or should tracks be
stored per crate from the start?**
Keep one file; the model problem is that `kind` lives on the track rather than
on the membership (F6). Locally, one entry with a single kind is defensible if
the product really means "file it once"; in the ledger, the single kind is
overwritten by the last keeper, so the crew cannot disagree. Store per-member
kind and make the local membership a set (or explicitly enforce move-only
semantics and report the move).

**Where is the SwiftUI state duplication? `BrowserModel` is ~350 lines; what
should split out first?**
`BrowserModel` is 469 lines and owns four unrelated things: (1) network
paging, (2) freshness persistence (`UserDefaults`, pruning), (3) pure
sort/filter presentation, (4) view-only state (`binGrid`, `scrollToSelection`,
`note`). It also duplicates `selectedUser` ownership with `AppModel`, which
is what breaks `commitSeen` (F4). Split, in this order:
1. **`BrowsePager`** — `loadFolders`/`loadFiles`/`loadMoreFiles` with a
   request generation and cancellation (also fixes F19).
2. **`SeenStore`** — snapshot read/write/prune, pure and testable, with a
   `complete` flag (F4).
3. **`ShelfSort`** — pure functions over `[FolderRow]`, computed once per
   change (F26).
4. **`ShelfViewState`** — grid mode, scroll target, filter text.
Then `BrowserModel` becomes the facade and `AppModel` stops writing
`selectedUser` behind its back.

**Any correctness bugs in the sort/selection/scroll interactions in the bins?**
Yes: F25 (scroll no-op, stale selection kills Return), F26 (no tiebreak), F19
(races), F27 (duplicate peer ids). The selection is keyed by name only; that is
fine within a folder, but it must be reset on folder change.

**Is validating settings in `apply_settings` enough, or does a PATCH need to
create directories / verify paths exist?**
Not enough (F8). Validate and normalise every path (expand `~`, absolute),
create the directory, probe writability, and only then save; otherwise one POST
turns every crate call into a 500 that survives a restart.

**Secrets are masked on read and only sent when non-empty; is that the right
write-only contract, and how should clearing a token work?**
Write-only is right; the missing half is **clearing** (F9). Add an explicit
clear flag (or accept `""`) and a Clear button. Also fix the 0644 file mode
and consider the Keychain.

**The ledger re-reads before every write and uses a temp file; is that enough
for a synced folder, or does it need a per-entry revision?**
Not enough (F10). Re-read narrows the race but the write is still whole-file,
the temp name is fixed, and sync ignores locks. It needs per-entry units
(or a merge with per-entry `rev`/`updated_at`), unique temp names, and
`fsync`.

**Stars as `(peer, star:<member>)` entries — does that survive an unstar by a
different member, and is the key collision-free enough?**
The engine keeps per-member stars, but the client cannot unstar another
member's star and the default member name collides (F11). It needs attribution
and a stable member id.

**The status endpoint stores every requested user forever; should it expire?**
Yes (F22). Add a TTL/LRU (or a tracked `status-lookup` watch context that is
released), batch the requests, and have the client re-read known values.

---

## Test gaps that would catch real regressions

Engine (Python):

1. **`folder_page` under a clear/update**: clear between the folder-key
   snapshot and the detail loop (or inject a hook) and assert no zeroed rows;
   assert `total` matches `len(page)` for a stable share.
2. **Public + private**: a `BrowsedUser` with both dicts → both folders listed,
   `summary.folders` equals `folder_page.total`, and `file_page` resolves each.
3. **Multi-message counts**: feed two `SharedFileListResponse` messages and
   assert `num_folders`/`num_files` accumulate and `summary.files` matches the
   sum (F17).
4. **Bad attribute types**: `length="3:45"`, `size=None` → the page still
   returns, with the file counted and the duration skipped (F16).
5. **Crate concurrency**: two `_set_status` writers with a `keep` interleaved;
   assert no track is lost and no `FileNotFoundError`; `POST /crate/<id>/kind`
   while a keep lands must not drop the new track (F2).
6. **Keep kinds**: `add(same path, kind="dj")` updates the kind or reports the
   conflict; keep-all into DJ on an existing sample entry (F6).
7. **Keep with a paused preview**: create a preview transfer, call
   `keep_source` with `peer=None`, assert the download is retargeted/finished
   and `local_path` is set; close the session after keep and assert promotion
   still happens (F1).
8. **Local keep**: own-share keep sets `local_path` and queues no download
   (F29).
9. **Service auto-start**: a finished download for a kept track starts the
   pipeline without a manual `/separate` (F7).
10. **Settings paths**: `work_dir` unwritable → 400 at POST and the old value
    survives; `~/…` expands; `rolodex_path` with `~` does not create a literal
    `~` (F8/F12).
11. **Secrets**: `public_settings` contains no token substring; clearing via
    `""`/`*_clear` unsets; file mode is 0600 (F9).
12. **Ledger concurrency**: two interleaved writers preserve both entries; a
    re-keep preserves the original `found_by`; a `rolodex 2.json` conflict copy
    is merged (F10).
13. **Stars**: A stars, B stars, A unstars → B's star remains; same display
    name on two members is either rejected or namespaced (F11).
14. **API encoding**: `GET /users/<u>/files?folder=Simon%20%26%20Garfunkel`
    returns the folder; the client's escaped query for `"C++"` round-trips
    (F18). A pure-function test on the client's query builder is enough.

Swift:

15. **`noteFresh`/`commitSeen`**: a complete snapshot, a partial snapshot
    (must not advance), a new folder, a grown folder, a same-count-same-size
    replacement (must be fresh with a fingerprint), and a peer switch (must
    commit the old peer).
16. **Paging**: >500 folders merge into one list with no duplicates, and a
    failed page does not produce a "complete" shelf (F4).
17. **`loadFiles` race**: with an injectable client, resolve B before A and
    assert the pane shows B; `loadMoreFiles` does not duplicate ids (F19).
18. **Sort determinism**: equal counts/ratios produce the same order on repeated
    sorts (F26).
19. **Rolodex**: extend `testRolodexGroupsKeepsBySource` with a ledger that
    contains the member's own keeps and one other member's; assert `crew` and
    `folderCount` (F21).
20. **Settings patch**: empty tokens are omitted; a clear flag is sent when
    requested; `adopt` does not wipe an unsaved token (F9/F31).
21. **Query building**: `&` and `+` in a folder name (F18) — if `escape` is
    made a free function this is a one-liner.
22. **Deck**: a snapshot renders at the documented 154 pt; the collapsed
    transport keeps focus across a tick (hard to unit test, but a UI snapshot
    or a manual checklist item in the brief would catch F23/F35).

---

## What I did not cover

- GTK behaviour beyond using it as the reference for private folders; the GTK
  dig window, separation setup, and portaudio player were not exercised.
- Real peer traffic: all engine observations are from code + unit tests, not a
  live 100k-file browse.
- The audio pipeline itself (Demucs/MVSEP/PC renderers, Ableton set building)
  except where it touches the keep/settings paths above.
- Search and the crates UI beyond the kind/keep interactions.
- Visual QA of the deck; F23/F24/F35 are code-reading findings and need a
  manual pass on a running app.
