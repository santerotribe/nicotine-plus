# Independent review brief — Tribe Seek

2026-11-28 · branch `main-ours` · fork `santerotribe/nicotine-plus`

## What this is

A fork of Nicotine+ extended into a crate-digging tool for a DJ collective:
search Soulseek, walk a seller's share as bins, audition the real file, keep it
into a Sample or DJ crate, split stems, and land it in Ableton.

Two parts:

- **Engine** — Python, `pynicotine/`, with a local HTTP API in
  `pynicotine/engineapi/` (stdlib ThreadingHTTPServer, bearer token, SSE).
- **Native client** — SwiftUI in `native/TribeSeek/`, the product front end.
  GTK is frozen as a debug tool.

Repo: `/Volumes/Schema Era/Schema Apps/nicotine`
Docs: `docs/ENGINE-API.md`, `docs/UI-DIRECTION.md`, `docs/ROADMAP.md`

## State

- Tests: `XDG_CONFIG_HOME=/tmp/digcfg .venv/bin/python -m pytest pynicotine/tests -q`
  → 169 passed, 1 skipped. Swift: 10 passed.
- Recent work (review this): search tabs, the audition ribbon deck, shelf dig and
  bin grid, engine folder aggregates, crate kinds (sample/dj), Rolodex.
- The app is running locally against an engine on 8766 with an isolated profile
  in `.dev/`. Never print `.dev/config` (Soulseek password).

## Scope, in priority order

1. **Engine folder aggregates** — `pynicotine/userbrowse.py`: `_folder_info`,
   `folder_page`. Audio-only denominators, bytes, formats, duration; called from
   the HTTP thread in `engineapi/server.py` (`/users/<u>/folders`) while a
   browse may still be writing. Check correctness, races, cost.
2. **Crate kinds** — `pynicotine/digging/crate.py` (`kind`, `by_kind`,
   `set_kind`), `digging/actions.py: keep_source`, `engineapi/audition.py: keep`,
   `engineapi/server.py` (`GET /crate?kind=`, `POST /crate/<id>/kind`,
   `DELETE /crate/<id>`). Is the single-file + kind field the right model, or
   should each crate own a file?
3. **Shelf** — `native/.../BrowserModel.swift` (folders, sorting, freshness,
   paging), `Screens/BrowseDetail.swift` (two panes, bins, inspector, generic
   leaf inheritance). Freshness is a count+bytes snapshot committed on leaving
   the shelf / switching peers / quit. Is the semantics right? Is `BrowserModel`
   doing too much?
4. **Audition deck** — `Screens/AuditionDeck.swift`, `Shell/Transport.swift`.
   Replaces the old 300 pt pane + transport; 154 pt ribbon, 48 pt collapsed.
   Check the layout maths, focus/keyboard, and the fact that it re-renders at
   30 fps through `TimelineView`.
5. **Rolodex** — `RolodexModel.swift`, `Screens/RolodexViews.swift`. Groups keeps
   by peer from `/crate`, stars in UserDefaults; local only for now.
6. **Contract** — `docs/ENGINE-API.md` vs the code. The folders payload changed
   shape recently (map → array with audio fields); no versioning yet.

## Questions I want answered

- Is computing per-folder aggregates on every page request acceptable, or should
  they be cached when the browse lands? What breaks at 100k files?
- Is `folder_page` safe against a live browse mutating the same dicts?
- Is count+bytes the best "new since last visit" fingerprint Soulseek allows?
- Does the crate-kind design survive the collective ledger, or should tracks be
  stored per crate from the start?
- Where is the SwiftUI state duplication? `BrowserModel` is ~350 lines; what
  should split out first?
- Any correctness bugs in the sort/selection/scroll interactions in the bins.
- Test gaps that would actually catch regressions, not just raise a count.

## Commands

```sh
cd "/Volumes/Schema Era/Schema Apps/nicotine"
XDG_CONFIG_HOME=/tmp/digcfg .venv/bin/python -m pytest pynicotine/tests -q
(cd native/TribeSeek && swift test --disable-sandbox \
  --scratch-path /tmp/tribeseek-build --cache-path /tmp/tribeseek-cache)
native/TribeSeek/run.sh            # starts the engine if 8766 is free
```

Dev flags: `TRIBE_SECTION=crates|rolodex|shelf|search`, `TRIBE_BINS=1`,
`TRIBE_DIG=user|folder`, `TRIBE_SEARCH=term`, `TRIBE_AUTO=1`,
`TRIBE_SKIN=arca|suno`.

## Known open items (do not re-report as discoveries)

- No bulk "Keep all" yet; the keep path only exists per audition.
- No online/offline status for Rolodex peers; no shared ledger yet.
- The deck's Keep always writes to Sample; the menu is pending.
- Stale WINTER2014 test keep in the crate.
- GTK still carries the only separation-setup UI; the splitter integration is
  queued on hold.

## Deliverable

Write `docs/REVIEW-FINDINGS.md` with findings ordered by severity, each with
file:line, why it matters, and a suggested fix. Do not change code. Be
adversarial about the engine concurrency and the freshness semantics; those are
the two places I trust least.
