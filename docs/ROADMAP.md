# Tribe Seek — product plan and roadmap

2026-11-27 · supersedes the "digging" framing in HANDOFF.md §8. Written after a
vision conversation; treat §12 (decisions) as the live list.

**Status:** 0a (rename) and 0b (rail, tray) landed. Next: the search tab strip,
then the shelf. Phase 4 (Passage) is on hold pending the cap/arm64/install
conversation.

## 1. What this is

Tribe Seek is a private instrument for one DJ collective. Soulseek is the
warehouse; the app is the shop floor. Two loops, one window:

- **Find** — search the network like Soulseek, then walk a seller's shelves
  (their share folders) the way you walk a record store's bins.
- **Keep** — file what you find into a DJ crate or a Sample crate, split it into
  stems, and land it in Ableton warped to tempo.

The collective is the third loop: what one member digs up becomes a lead for
everyone else. That is the reason to build an app instead of using SoulseekQt.

## 2. Principles

1. **The folder is the unit, not the file.** A share folder is a bin. Search
   results are a means to reach a bin.
2. **One workspace.** Search, shelf, and audition are one screen. No mode tabs,
   no second window for playback.
3. **Everything plays in place** — the real file, streamed, buffered, with a
   waveform. No YouTube bridge.
4. **Nothing blocks.** Long work shows progress in a tray, never a modal.
5. **Local-first, collective-second.** The app works alone; sharing is additive
   and must never gate a search or a keep.
6. **Honest surface.** No invented cover art, no fake metadata. Folder names,
   counts, formats, and waveforms are the visual material.
7. **Human-paced.** No scraping, no bulk harvesting, no automation that looks
   like a bot to the network. One account per member.

## 3. Naming

| Idea | Name | Notes |
|---|---|---|
| App | **Tribe Seek** | bundle `com.schemaapps.tribeseek`, target `TribeSeek` |
| Settings | **Rig** | replaces "Digging" as the settings surface |
| A peer's library | **Shelf** | "open their shelf" |
| A folder in a shelf | **Bin** | record-store bin |
| Collective sources list | **Rolodex** | index cards of trusted sellers |
| The verb | **dig** | survives as an action: "Dig this bin", "Dig deeper" |

"Digging" as a *tab* or a *settings page* goes away. The word stays in buttons.
Internal Python packages keep their names (`pynicotine/digging`) — renaming them
is churn with no user-visible payoff.

## 4. Information architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  ◉ Tribe Seek      [ italo disco × ][ Shelf: djpete × ][ + ]   ⌘K    │  top bar
├────┬─────────────────────────────────────────────────────────────────┤
│    │                                                                 │
│ ▸  │                     workspace (tab content)                     │
│ S  │      results list  ·or·  shelf bins  ·or·  crate detail         │
│ h  │                                                                 │
│ e  │                                                                 │
│ l  │                                                                 │
│ f  │                                                                 │
│    ├─────────────────────────────────────────────────────────────────┤
│ C  │  ▁▂▅▇▅▂▁  waveform            ▶ 00:42 / 03:18   [DJ] [Sample]  │  audition
│ r  │  Ruggier — "Italo Disco" · djpete/Italo/1983/ · 320 kbps        │  tray
│ a  │  [Dig bin] [Open folder] [More]                                 │
├────┴─────────────────────────────────────────────────────────────────┤
│  Search      Crates      Rolodex      Rig                  ● online  │  rail
└──────────────────────────────────────────────────────────────────────┘
```

- **Top bar** — search field, always present, focuses with ⌘K. Enter opens a new
  tab. The tab strip holds searches *and* shelves, so a shelf stays put while
  you run another search.
- **Workspace** — the active tab. Three content types: results, shelf, crate.
- **Audition tray** — docked bottom, ~150 pt, expands to a focus view with
  Space. Holds waveform, transport, keep actions, source path, metadata.
- **Rail** — Search (workspace), Crates, Rolodex, Rig. That is the whole app.

Keyboard: ↑↓ move, → / ← move between bin and track level, Space audition/stop,
Enter open, **D** dig the selected result's bin, **K** keep, Esc closes the tray.
No right-click anywhere.

## 5. The shelf — the new core surface

Opening a search result's folder is one keystroke, not a copy-paste of a
username into another tab.

**Shelf header** — peer name, online dot, share size / folder count / file count,
star toggle, refresh. Starring a peer puts them in the Rolodex.

**Path chain** — the share path of the current bin as clickable breadcrumbs.
Siblings at each level are one click away, so you can climb out of
`Italo/1983/12-inch` into `Italo/1983` and see what else is in that year.

**Bins** — a two-column grid of folder cards:

```
┌────────────────────────────┐
│ ITALO / 1983 / 12-INCH     │  folder name, big, wrapped
│ 42 files · 1.8 GB · FLAC   │  count, size, format chips
│ ▁▂▃▅▆▇▆▅▃▂▁▂▃▅▆▇▆▅▃▂▁▂▃▅ │  duration sparkline (real, from file sizes
│ lossless 96%               │   + durations if known, else size density)
└────────────────────────────┘
```

- Hover shows the first three filenames; Space auditions the first track.
- Sort: **promising** (lossless ratio, track count, name match), name, size.
- Inside a bin: track rows with per-row play, keep, drag, and "Dig all".
- A filter box narrows the current bin or the shelf (client-side, loaded data).
- The card identity (color/monogram) is derived from the folder path hash —
  consistent, not invented art.

**Performance** — browse a peer once, cache the tree engine-side with a TTL, page
the payload, virtualize both the bin grid and the track list. A 100k-file share
must not be a 100k-row SwiftUI diff.

**Search results, grouped** — the same record from 20 sellers should be one row
that expands into sellers ("20 peers have this"). Group by normalized
artist/title + duration + size. This is both the record-store metaphor and the
single biggest memory win on 50k results.

## 6. Crates

Two shelves, one screen, segmented: **DJ** and **Sample**.

- `Crate.type`: `"dj" | "sample"`. Existing `crate.json` is a single crate —
  migration default needs a decision (§12).
- `CrateTrack` gains `source_user`, `source_folder`, `found_by`, `added_at`,
  `tags[]`, `notes`. This is what makes a keep a *lead* and not just a file.
- Crate detail shows provenance (who found it, where it came from, "back to the
  bin") and, in v2, leads: MusicBrainz / Discogs / WhoSampled links, related
  artists, other bins from the same seller.

## 7. Rolodex — the collective layer

Not a leaderboard and not points. A card index of sellers the crew trusts.

- Cards come from two sources: **auto** (you kept something from them) and
  **manual** (you starred them or one of their bins).
- Each card: name, online/offline, last seen, keeps count, which members found
  them, their best bins, "Open shelf".
- Sort: online first, then recent keeps, then count. Never a score.
- Sync: **v1 is a shared ledger file** (JSON) in a synced folder (iCloud Drive /
  Dropbox / the studio machine), one record per (peer, member, keep). Additive,
  so last-write-wins per record is enough; no auth, no server. A real service is
  a later option if the file becomes the bottleneck (§12).

## 8. Separation — Passage Preset 62, local

The collective's splitter is Passage's Preset 62 "Isolate Vocal" worker. One
stereo source in, two files out: `acapella.wav` (the vocal we expose) and
`denoised-mix.wav` (the intermediate that feeds it; vocals still present).
MVSEP and Demucs leave the default path.

| | |
|---|---|
| Source | `github.com/santerotribe/passage` @ `2805451` |
| Workspace | `<passage>/examples/preset62` (models and venv under `.local/`) |
| Runtime | `.local/venv-mlx/bin/python`; mlx 0.32.5, mlx-metal 0.32.5, mlx-audio-separator 0.1.20, mlx-spectro 0.9.10 |
| Launch | `nice -n 10 <python> -E -s -B <ws>/mlx_worker/serve.py <ws>` plus all eight fusion flags (§8.1) |
| Job | one JSON line on stdin: `{"input": "/abs/in.wav", "output": "/abs/jobdir"}` |
| Reply | `{"ok": true}` on stdout; stderr is the log |
| Outputs | `acapella.wav`, `denoised-mix.wav`, `run.json` (hashes, timings, forward counts) |
| Limits | WAV/WAVEX, 44.1 kHz, stereo, ≤ 13,107,000 frames (≈4:57), result ≤ 100 MiB |
| Transport | stdin/stdout; no port, no daemon, works with Passage closed |

Resident process: the first job pays model load (`setup_s` in `run.json`), later
jobs reuse it. Cancel = SIGTERM, SIGKILL after 5 s, delete the job dir.

```
SplitterBackend.probe() -> (ready, message, model_root)
SplitterBackend.split(src, out_dir, preset) -> {vocal: Path, mix: Path, receipt: dict}
```

Discovery order: explicit Rig setting → the app's installed copy
(`~/Library/Application Support/TribeSeek/Passage`) → the dev checkout. A
missing model must surface the worker's own sentence, not "not configured".

**One output, multi-stem preserved.** Passage gives vocals. The studio-PC agent
stays selectable for drums/bass/other, and the UI names the renderer per lane.
Timing to plan against: 23.87 s of inference for a 4:16 song warm on a 48 GB M5
Pro; ~42–44 s worker wall time in the packaged build; budget 45–60 s end to end
and drive the UI from the job directory, because the worker only signals start
and finish.

### 8.1 Exact launch arguments

Launching `serve.py` with defaults selects a different backend. The
`mlx-ffn-down-norm` configuration is:

```
--fuse-denoiser --direct-fp16-norm --direct-axis-layout
--fused-residual-norm --fused-deux-qk --fused-denoiser-qk
--fused-frequency-qk --fused-ffn-down-norm
```

Environment: `MLX_ENABLE_AMP=0`, `MLX_ENABLE_COMPILE=1`,
`MLX_AUDIO_SEPARATOR_ROFORMER_FAST_NORM=0`, `OPENBLAS_NUM_THREADS=1`, and
`PYTORCH_ENABLE_MPS_FALLBACK=0` (set by the launcher). Working directory is the
workspace. Python is started with `-E -s -B`.

## 8b. Into an open Live set — copy audioFabric

Insertion is solved in `~/audioFabric/live`: a Python Control Surface installed
to `~/Music/Ableton/User Library/Remote Scripts/<name>` and enabled in Live,
reached over JSON/UDP. Copy the pattern; do not edit `.als` for this.

- Port `127.0.0.1:19871` (`AUDIOFABRIC_LIVE_PORT` overrides), one JSON object per
  datagram: `{"id", "op", "args"}` → `{"id", "ok", "result"|"error"}`.
- Live runs it on the main thread. `arca.session_clip_target` returns `pid`,
  `setPath`, `sceneIndex`, `sceneId`; `arca.place_session_clip` appends one audio
  track and fills the selected scene slot; `arca.place_simpler_sample` appends a
  MIDI track with a Simpler.
- One send = one undo step. Refuses on `target-changed` / `invalid-audio`; replays
  identical request IDs from a 256-entry cache; recovery removes only tracks it
  can prove it owns.
- Stable across Live 12 and 13 because it uses the Remote Script API, not the
  set schema.

Tribe Seek ships its own surface name (`TribeSeek`) with the same envelope, plus
`tribeseek.place_stems` (one track per stem, returns track names). Rig installs
and repairs it; verify against Live 12 Suite and Live 13 Beta.

## 9. What already exists (reuse map)

| Need | Already in the repo |
|---|---|
| Search, browse, paging, SSE | `pynicotine/engineapi/*` |
| Audition of the real file | `engineapi/audition.py` + `Audio/AuditionPlayer.swift` |
| Waveform peaks | `digging/analyze.py: waveform_peaks` |
| BPM / duration / format | `digging/analyze.py: probe, detect_tempo` |
| Warped Live sets | `digging/ableton.py` + ALS Observatory |
| Crate store | `digging/crate.py` |
| Pipeline states | `digging/pipeline.py`, `service.py` |
| Design system | `native/TribeSeek/.../Theme.swift`, `UI-DIRECTION.md` |

The gap is orchestration and interface, not core capability.

## 10. Phases

Each phase ends with both suites green, a running app, and a note in HANDOFF.

**Phase 0 — identity and spine (done, 2026-11-27).**
0a: the app, target, binary, flags and launch path are Tribe Seek
(`0d5246f45`). 0b: the rail is Search / Shelf / Crates / Rolodex / Rig; the
Audition tab is gone and its pane is the expandable tray; settings is Rig. Still
open: retiring MVSEP from the default path, which waits on the splitter.

**Phase 1 — search workspace (in progress).**
Done: the search field lives in the top bar; every query opens a tab with its own
state; inactive tabs stop polling; the strip caps at eight with an LRU close; and
closing a tab deletes its engine-side store (`DELETE /search/<id>`).
Open: result grouping by track, per-tab scroll restoration, saved searches.
Exit: five searches open at once under 400 MB, closing a tab frees its results.

**Phase 2 — shelf (3 sessions).**
`Dig` from a result opens `Shelf(peer, dir)`; breadcrumb + sibling navigation;
bin grid with sort and hover peek; bin track list; star peer/bin; keyboard flip.
Exit: from a search result to a different bin in the same share in under three
keystrokes, with the tree cached and the UI smooth on a 50k-file share.

**Phase 3 — crates (1 session).**
`type` on crates, two shelves, provenance fields, row actions (delete, move
between crates). Existing keeps are test data and get wiped, so there is no
migration. Exit: a keep lands in the crate the user chose, with source
user/folder recorded, and deleting works.

**Phase 4 — Passage and Live insertion — ON HOLD (2026-11-27).**
The user is taking the 4:57 stereo cap, the arm64-only worker and the 4.2 GB
install to Passage. Do not build the adapter until those answers land.
**When resumed (3 sessions).**
Splitter adapter + discovery + Rig card (Test key, model status) + one-output
vocal lane + cancel + multi-stem passthrough; port the audioFabric surface;
keep drag-out. Exit: Keep → playable vocal in under 90 s warm; insert into an
open set as one undo step on Live 12 and 13; cancel leaves no process or job dir.

**Phase 5 — Rolodex and distribution (3–4 sessions).**
Local ledger, cards, online status, attribution; then the packaging work:
engine embedded in the app bundle (PyInstaller/py2app), signed + notarized DMG,
first-run onboarding (Soulseek account, display name, folders), update path.
Exit: a second collective member installs the DMG and keeps a track without a
terminal.

**Phase 6 — v2.**
Related artists and sample leads (MusicBrainz/Discogs), audio fingerprint dedupe
(chromaprint) for "you already have this", key detection, transfer controls,
saved-shelf alerts ("this seller added 4 folders").

## 11. Packaging reality check

"Installable by other members" is a project of its own. Today the native app
spawns `.venv/bin/python` from this repo. Shipping that to a DJ means either
bundling CPython + deps into the .app (PyInstaller, ~120 MB, GTK excluded) or
requiring a terminal install (won't happen). It also needs a Developer ID
signature, notarization, and an update mechanism. Budget a phase for it and do
not promise a DMG before Phase 5.

Add the splitter: Passage's packaged worker is **4.2 GB** (1.2 GB venv, 1.7 GB
model cache, 1.4 GB checkpoints). Do not put it in the repo. Either ship it
inside the .app or install it into
`~/Library/Application Support/TribeSeek/Passage` on first run with a resumable
download. First run, with progress, is the recommendation.

## 12. Decisions

Settled:

1. **Splitter** — Passage Preset 62 local worker (§8); MVSEP leaves the default
   path; the studio-PC agent remains for multi-stem.
2. **Crates** — start fresh; existing keeps are test data.
3. **GTK** — frozen as a debug tool; native is the product.
4. **Live insertion** — audioFabric's UDP Remote Script pattern (§8b), on Live 12
   and 13.
5. **Collective sync** — shared JSON ledger in a synced folder for v1; a service
   only if the file becomes the bottleneck.
6. **Identity** — `com.schemaapps.tribeseek`.

Open:

7. **Result grouping** — group by normalized artist/title + size from day one, or
   add it after the shelf? Recommendation: day one; it halves the result count.
8. **Distribution of the worker** — bundle 4.2 GB or first-run install?
   Recommendation: first run.
9. **Licence** — GPL-3.0-or-later: sharing with the collective means sharing the
   source with them. Keep upstream notices; decide who holds the repo.

## 13. References

- ALS format, donor-template generation:
  [als-format notes](https://github.com/scott-fryxell/brayness/blob/71f10e2ca709d2210640622e34ffc307426f0239/skills/zoom-to-ableton/references/als-format.md)
  · [ALS Observatory](https://github.com/) (local: `~/Documents/ALS Observatory`)
- Stem separation fallbacks:
  [audio-separator](https://pypi.org/project/audio-separator/) (Demucs/MDX CLI + library)
- Duplicate detection: [AcoustID / chromaprint](https://blog.acoustid.org/)
- Key detection: [keyfinder-cli](https://github.com/evanpurkhiser/keyfinder-cli)
- Tempo/onset: [aubio](https://git.aubio.org/?p=aubio.git)
- Headless Soulseek, for shape reference: [slskd](https://hub.docker.com/r/slskd/slskd)
- Drag-to-DAW precedent: [Splice × Ableton integration](https://splice.com/blog/splice-integration-ableton-live/)
- Passage Preset 62: [repo](https://github.com/santerotribe/passage) ·
  `docs/benchmarks/preset62-reference.md`, `preset62-mac-handoff.md`,
  `preset62-closeout.json` in that checkout
- Live insertion pattern: `~/audioFabric/live` (Remote Script + UDP contract)
- In-repo: [UI-DIRECTION.md](UI-DIRECTION.md), [ENGINE-API.md](ENGINE-API.md),
  [DIGGING.md](DIGGING.md), [HANDOFF.md](HANDOFF.md)
