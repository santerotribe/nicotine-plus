# Review fix status

2026-11-28 · against [REVIEW-FINDINGS.md](REVIEW-FINDINGS.md) · commit batch on
`main-ours`

## Fixed

| Finding | What changed |
|---|---|
| F1 | The keep owns its transfer: a running preview is cancelled/cleared, a finished one is copied and recorded; own-share keeps map to disk and kick the pipeline; keeps are idempotent. |
| F2 | Crate mutations reload under a process-wide lock, unique temp file, `Crate.update` for status writes, pipeline records `local_path`, SEPARATING inside the try. |
| F3 | Refresh forces a new browse request (`browse(force: true)`). |
| F4 | The seen baseline is only committed from a complete, non-loading share. |
| F5 | Public and private folders are merged for summary, folder pages and file pages. |
| F6 | A second keep into another kind moves the track (explicit move-only). |
| F7 | `keep_source` starts the pipeline service, so API-only sessions separate. |
| F8 | Settings paths are expanded, required absolute, created and probed for writability before saving. |
| F9 | Settings files are 0600; tokens can be cleared from the Rig. |
| F12 | Ledger paths expand `~`; settings normalises them. |
| F13 | Folder pages are built from one snapshot, never a torn page. |
| F15 | A timed-out mutation returns 503 ("may or may not apply") instead of a generic 500. |
| F16 | Malformed size/length values cannot 500 a folder page. |
| F18 | Query encoding is strict: `&` and `+` in folder names survive. |
| F19 | Folder/file pages ignore responses for a selection that moved on. |
| F20 | Freshness uses an audio-only name+size digest, not count+bytes. |
| F21 | "Crew" excludes your own keeps. |
| F22 | Status lookups are capped at 40 per load. |
| F23 | The transport no longer rebuilds its identity every frame. |
| F24 | An INCOMPLETE preview is never offered to Ableton/Finder. |
| F25 | The dig sets the scroll flag before the selection changes. |
| F26 | Bin sorts have a stable name tiebreak. |
| F27 | Peers are deduplicated before entering the list. |
| F28 | Keep all pages through the whole bin before sending. |
| F29 | Own-share keeps no longer download your own file. |
| F30 | The pipeline reloads settings per job, so Rig changes apply. |
| F31 | Rig/Rolodex no longer double-load; views depend on `activateSection`. |
| F33 | `gap` events refresh state and crate. |
| F34 | The API fails closed when no token is configured. |
| F35 | The deck frame matches its 144 pt content. |
| F36 | Literal interpolation, stems popover, FLAC label, catalogue threshold, stem LEDs, deterministic top folder. |

## Still open

| Finding | Why |
|---|---|
| F10 (part) | Unique temp + fsync + re-read are in; per-entry revisions/merge under a syncing filesystem are still a design decision. |
| F11 (part) | Stars are per-member in the ledger; a stable member identity and removing another member's star are not implemented. |
| F14 | Server-side sort + top-N and aggregate caching per browse generation. The compute is cheap (24 ms/100k); the client still materialises every folder. |
| F15 (part) | 503 is honest, but a queued mutation can still apply after the timeout; idempotency keys are the real fix. |
| F32 (part) | `/crate/keep` documented; the API still has no version field. |
