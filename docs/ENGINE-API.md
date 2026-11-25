# Engine API (native front-end migration)

The Soulseek engine `pynicotine` + the digging pipeline are front-end agnostic.
This document describes the local HTTP/JSON surface a native macOS (SwiftUI)
client talks to, so the rewrite never touches the protocol.

## Running it

```sh
NICOTINE_API_PORT=8766 NICOTINE_API_TOKEN=secret \
  .venv/bin/python -m pynicotine -n --config "$PWD/.dev/config" --user-data "$PWD/.dev/data"
```

- Binds **127.0.0.1 only** (loopback), daemon thread, no external listener.
- With `NICOTINE_API_TOKEN` set, every endpoint except `/health` requires
  `Authorization: Bearer <token>`.
- Without `NICOTINE_API_PORT` the API is not started at all, so the GTK client
  behaves exactly as before.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness, version, login flag (no token) |
| GET | `/state` | username, status, privileges, download/browsed counts |
| GET | `/users/<user>/summary` | folders/files/shared size for a browsed user |
| GET | `/users/<user>/folders?offset=&limit=` | paged folder names with file counts |
| GET | `/users/<user>/files?folder=&offset=&limit=` | paged files of one folder |
| POST | `/users/<user>/browse` | request the user's share list |
| GET | `/downloads?offset=&limit=` | transfers with raw progress |
| GET | `/crate` | kept tracks, stems, Live set paths |
| POST | `/crate/<id>/separate` | run the separation pipeline for a kept track |

### Browse paging

A native list view should never materialise a 100k-file library. Two calls:

```
GET /users/santero/summary
{"username":"santero","folders":27,"files":864,"shared_size":49281934840,"messages":1}

GET /users/santero/folders?limit=3
{"total":27,"offset":0,"limit":3,
 "folders":{"for santero":27,"for santero\\Ramoz ...":2,"for santero\\USB":1}}

GET /users/santero/files?folder=for+santero&offset=0&limit=500
{"total":27,"offset":0,"limit":500,
 "files":[{"name":"track.mp3","size":123456,"bitrate":320,"length":215,
           "vbr":0,"sample_rate":44100,"bit_depth":16}, ...]}
```

Values are raw (bytes, bps, seconds). Formatting belongs to the front end.

## Data shapes

- **File**: `name, size, bitrate, length, vbr, sample_rate, bit_depth`
- **Transfer**: `username, virtual_path, filename, folder, size, transferred,
  status, queue_position, speed, percent`
- **Crate track**: `id, username, filename, virtual_path, status, bpm,
  local_path, stems{}, als_path, error, added_at`

## Instrumentation

Browsing logs a latency split so large-library tuning has real numbers:

```
Browse: santero answered in 0.00s (27 folders, 864 files, message 1)
```

Measured on GTK with 50k files: building row data 16 ms + formatting 43 ms,
`Gtk.ListStore` insertion 751 ms, sorting 237 ms. i.e. the engine side is cheap;
the current cost is the GTK model, which a native list view replaces.

## Threading contract

- Reads (GET) touch engine state directly.
- Mutations (POST) are dispatched with `events.invoke_main_thread(...)`, which is
  how the engine keeps its own invariants.
- The HTTP server is a daemon thread; it never blocks the engine loop.

## Migration plan

1. **Engine boundary** (done): API, paged browse, raw JSON shapes, token auth,
   browse timing.
2. **Push updates**: add `GET /events` (SSE) for login state, transfer progress,
   browse completion and pipeline status, so the SwiftUI app can drop polling.
3. **Playback handoff**: expose the audition source (catalogue URL or peer file)
   plus the peer-preview lifecycle, so AVAudioEngine replaces the PortAudio
   player. The digging module already resolves both.
4. **SwiftUI shell spike**: list + player + waveform + drag (AppKit) against this
   API, still launching the Python engine as a child process.
5. **Move front ends**: GTK remains for Linux/Windows; the macOS app becomes the
   native shell. Nothing under `pynicotine/` needs to know which UI is talking.

## What stays in Python

Everything protocol- and pipeline-related: login, search, browse, transfers,
shares, the catalogue matcher, peer preview, stem separation and Live Set
generation. The native app owns presentation, audio output and macOS integration
(drag, menus, notifications).

## Next steps not yet covered

- `/search` (start a search, page results, watch them arrive)
- transfer controls (pause/resume/cancel, keep)
- settings read/write for the digging config
- SSE event stream instead of polling
