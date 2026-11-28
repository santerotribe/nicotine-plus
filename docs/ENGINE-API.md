# Engine API (native front-end migration)

The Soulseek engine `pynicotine` + the digging pipeline are front-end agnostic.
This document describes the local HTTP/JSON surface a native macOS (SwiftUI)
client talks to, so the rewrite never touches the protocol.

Everything here is raw: bytes, bits per second, seconds since epoch. Formatting
belongs to the front end.

## Running it

```sh
NICOTINE_API_PORT=8766 NICOTINE_API_TOKEN=secret \
  .venv/bin/python -m pynicotine -n --config "$PWD/.dev/config" --user-data "$PWD/.dev/data"
```

- Binds **127.0.0.1 only** (loopback), daemon thread, no external listener.
- With `NICOTINE_API_TOKEN` set, every endpoint except `/health` requires
  `Authorization: Bearer <token>`. `/events` also accepts `?token=` because
  EventSource-style clients cannot set headers.
- Without `NICOTINE_API_PORT` the API is not started at all, so the GTK client
  behaves exactly as before.
- Both the GUI and headless (`-n`) entry points start it. The API needs no UI.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness, version, login flag (no token) |
| GET | `/state` | username, status, privileges, counters |
| GET | `/events` | Server-Sent Events push channel |
| GET | `/users/<user>/summary` | folders/files/shared size for a browsed user |
| GET | `/users/<user>/folders?offset=&limit=` | paged folders with files/size/formats/lossless/duration |
| GET | `/users/<user>/files?folder=&offset=&limit=` | paged files of one folder |
| POST | `/users/<user>/browse` | request the user's share list |
| GET | `/downloads?offset=&limit=` | transfers with raw progress |
| GET | `/crate` | kept tracks, stems, Live set paths |
| POST | `/crate/<id>/separate` | run the separation pipeline for a kept track |
| GET | `/search` | searches tracked by this API |
| POST | `/search` | start a search |
| GET | `/search/<token>` | counters for one search |
| GET | `/search/<token>/results?offset=&limit=` | flat results in arrival order |
| GET | `/search/<token>/users?offset=&limit=` | results grouped by peer |
| GET | `/search/<token>/files?user=&folder=` | folders of a peer, or files of one folder |
| POST | `/search/<token>/stop` | stop the search, keep the collected results |
| DELETE | `/search/<token>` | forget the search and its results |
| GET | `/audition` | active audition sessions |
| POST | `/audition` | start auditioning a browsed file |
| GET | `/audition/<id>` | resolved playback source + peer/catalogue state |
| POST | `/audition/<id>/keep` | add to the crate (downloads the real file) |
| DELETE | `/audition/<id>` | stop the peer fetch and clean up |

## GET /events — Server-Sent Events

One ordered stream of everything the engine does. This is what removes polling
from a native app: connect once, render.

```
event: hello
data: {"type": "hello", "seq": 0, "time": 1795588324,
       "state": {"logged_in": true, "username": "santero", "status": "2",
                 "privileges_seconds": 3005822, "browsed_users": []},
       "transfers": [...], "searches": [...], "auditions": [...],
       "crate": {"total": 1, "statuses": {"kept": 1}}}
```

Every event is `id: <seq>`, `event: <type>`, `data: <json>`. `seq` is
monotonic for the lifetime of the engine; a client that reconnects should treat
the new `hello` as a full snapshot and re-read paged endpoints if it cares about
what it missed.

| Event | Payload |
|---|---|
| `hello` | state snapshot, current transfers (≤ 200), searches, auditions, crate counts |
| `login` | `username, success, reason, privileges_seconds` |
| `disconnect` | `manual, username` |
| `browse_started` | `username` |
| `browse` | `username, done, folders, files, shared_size, messages` |
| `browse_failed` | `username, offline, error` |
| `transfers` | `transfers: [Transfer, ...]` — coalesced, ≤ 200 per event, ~2.5/s |
| `search_started` | `token, term, mode` |
| `search` | `token, term, user, added, total` — one per peer response |
| `search_failed` | `token, offline` |
| `search_removed` | `token` |
| `crate` | `track_id` + the crate track fields that changed |
| `audition` | the full audition state (see below), throttled to 2/s |
| `audition_closed` | `id, username, filename` |

`browse` is sent twice for a normal browse: once with `done: false` as data
arrives, then once with `done: true` about a second after the last message
(a share list can arrive in several messages, so completion is a quiet period,
not a count). A browse that answers in one message still gets both.

Filtering, for clients that only care about part of the stream:

```
GET /events?types=transfers,browse     only these
GET /events?types=-transfers           everything but these
```

`hello` and `gap` are always delivered. If a client falls behind, the server
drops its oldest queued events (2048-event buffer) and emits
`{"type": "gap", "dropped": N}` so the client knows to re-read. The engine is
never slowed down by a slow reader: publishing is non-blocking.

Heartbeats: `": ping\n\n"` every 15 s, so proxies and URLSession keep the
connection alive. The response is `HTTP/1.1` with `Transfer-Encoding: chunked`
(an endless body has no length). Without that framing, URLSession waits for the
connection to close before delivering anything, which looks like a dead stream.

```sh
curl -N -H 'Authorization: Bearer secret' http://127.0.0.1:8766/events
```

## Browse paging

A native list view should never materialise a 100k-file library. Two calls:

```
GET /users/santero/summary
{"username":"santero","folders":27,"files":864,"shared_size":49281934840,"messages":1}

GET /users/santero/folders?limit=3
{"total":27,"offset":0,"limit":3,
 "folders":[
   {"name":"for santero","files":27,"size":4823910400,
    "formats":{"flac":20,"mp3":7},"lossless":20,"duration":6480},
   {"name":"for santero\\Ramoz ...","files":2,"size":104857600,
    "formats":{"wav":2},"lossless":2,"duration":420}]}

GET /users/santero/files?folder=for+santero&offset=0&limit=500
{"total":27,"offset":0,"limit":500,
 "files":[{"name":"track.mp3","size":123456,"bitrate":320,"length":215,
           "vbr":0,"sample_rate":44100,"bit_depth":16}, ...]}
```

## Search

```sh
curl -X POST -H 'Authorization: Bearer secret' -H 'Content-Type: application/json' \
  -d '{"term":"ruggier long ride","mode":"global"}' \
  http://127.0.0.1:8766/search

{"token": 1149429, "term": "ruggier long ride", "mode": "global",
 "total": 0, "users": 0, "dropped": 0, "created_at": 1795588335, "last_result_at": 0}
```

`mode` is `global` (default), `rooms` (needs `room`) or `user` (needs
`users: ["name", ...]`). Wishlist searches are not exposed here.

Results are stored by the engine in arrival order and grouped by peer/folder, so
one peer's 400-file response is one `search` event and three paged reads:

```
GET /search/1149429/results?offset=0&limit=500
{"token":1149429,"total":19,"offset":0,"limit":500,
 "results":[{"username":"musicmasterrdjpool",
             "virtual_path":"BEATPORT 2026\\MONTHS\\SEP\\12\\...\\Ruggier - Long Ride (Original Mix).mp3",
             "folder":"BEATPORT 2026\\MONTHS\\SEP\\12\\...",
             "filename":"Ruggier - Long Ride (Original Mix).mp3",
             "size":14488855,"bitrate":320,"length":361,"vbr":0,
             "sample_rate":null,"bit_depth":null,
             "slot_available":false,"upload_speed":4689,
             "queue_position":1055,"private":false}, ...]}

GET /search/1149429/users?limit=5
{"token":1149429,"total":4,"offset":0,"limit":5,
 "users":[{"username":"DJ-Promo","files":9,"folders":9,"total_size":202510223,
           "slot_available":false,"upload_speed":30899,"queue_position":9}, ...]}

GET /search/1149429/files?user=Geriberto              folder list of one peer
GET /search/1149429/files?user=Geriberto&folder=X     files of one folder
```

Notes:

- Results are filtered like the GTK client does: a peer sending files that do not
  contain the search words (or contain an excluded `-word`) is ignored.
- At most 50 000 results per search; the overflow is counted in `dropped` instead
  of silently vanishing. At most 32 searches are tracked, oldest evicted.
- A search started here is invisible to the GTK client (`notify_frontend=False`),
  so a native app never causes phantom tabs.
- `stop` on an unknown token returns 404, and `DELETE` forgets the results.

## Audition — playback handoff

The engine owns the peer fetch and the catalogue lookup; the native app owns
audio output. One session per auditioned file:

```sh
curl -X POST -H 'Authorization: Bearer secret' -H 'Content-Type: application/json' \
  -d '{"username":"musicmasterrdjpool",
       "virtual_path":"BEATPORT 2026\\...\\Ruggier - Long Ride (Original Mix).mp3",
       "size":14488855,"duration":361,
       "attributes":{"bitrate":320,"length":361,"vbr":0}}' \
  http://127.0.0.1:8766/audition
```

```
201
{"id":"af3d76599185","username":"musicmasterrdjpool",
 "virtual_path":"...","folder":"...","filename":"Ruggier - Long Ride (Original Mix).mp3",
 "size":14488855,"duration":361.0,"local_path":"","kept":false,"track_id":"",
 "created_at":1795588368,"catalogue_state":"pending","catalogue_error":"",
 "catalogue":[],
 "peer":{"active":true,"status":"queued","bytes":0,"size":14488855,"percent":0.0,
         "queue_position":0,"partial_path":"","finished_path":"","complete":false,"error":""},
 "source":null}
```

A few seconds later the catalogue has answered and `source` is usable:

```
"catalogue_state":"matched",
"catalogue":[{"artist":"Ruggier","title":"Long Ride","label":"Ruggier - Long Ride",
              "album":"SLW - Single","duration":360,"score":1.0,"source":"itunes",
              "preview_url":"https://audio-ssl.itunes.apple.com/...m4a",
              "stream_url":"","playback_url":"https://audio-ssl.itunes.apple.com/...m4a",
              "store_url":"https://music.apple.com/...","artwork":"https://.../100x100bb.jpg"}],
"peer":{"status":"queued","bytes":0,"percent":0.0,"queue_position":1055,...},
"source":{"kind":"catalogue","url":"https://audio-ssl.itunes.apple.com/...m4a",
          "bytes":0,"total":0,"complete":false}
```

**`source` is the file to open right now.** Resolution order:

1. `{"kind":"local","path":...}` — our own share, on disk, exact file.
2. `{"kind":"peer","path":.../INCOMPLETE...,"bytes":N,"total":M,"complete":false}`
   once enough bytes exist to decode (~192 KB). This is the real file, partial.
3. `{"kind":"catalogue","url":...}` — a 30 s iTunes preview or a resolved
   YouTube stream, while the peer is still queued.
4. `{"kind":"peer",...}` partial below the decode threshold, or `null` when
   nothing is playable yet.

For AVAudioEngine: open `source.path` (peer/local) or `source.url` (catalogue),
and treat `peer.bytes` as the readable horizon for a peer file — the file grows
while it plays, so clamp seeks there. When the peer finishes, `peer.complete`
turns true and `source.path` becomes the finished file. The GTK client crossfades
from catalogue to peer; a native client can do the same when
`peer.bytes >= 192000` and it is not yet playing the peer file.

`POST /audition/<id>/keep` promotes the preview to
`<profile>/digging/downloads/<user>/`, records the crate entry and lets the
pipeline separate when the download finishes:

```json
{"track": {"id":"...","status":"kept", ...}, "audition": {...}}
```

`DELETE /audition/<id>` pauses the preview transfer, forgets the session and
triggers a throttled preview sweep (at most once a minute) so a native-only
client still cleans up un-kept files. Sessions idle for 30 minutes are reaped.

## Data shapes

- **File**: `name, size, bitrate, length, vbr, sample_rate, bit_depth`
- **Transfer**: `username, virtual_path, filename, folder, size, transferred,
  status, queue_position, speed, percent`
- **Crate track**: `id, username, filename, virtual_path, status, bpm,
  local_path, stems{}, als_path, error, added_at`
- **Search result**: `username, virtual_path, folder, filename, size, bitrate,
  length, vbr, sample_rate, bit_depth, slot_available, upload_speed,
  queue_position, private`

## A worked session

```sh
B='Authorization: Bearer secret'
curl -s -H "$B" http://127.0.0.1:8766/state
curl -s -X POST -H "$B" http://127.0.0.1:8766/users/dj/browse
curl -s -H "$B" 'http://127.0.0.1:8766/users/dj/folders?limit=50'
curl -s -H "$B" 'http://127.0.0.1:8766/users/dj/files?folder=House&limit=200'
curl -s -X POST -H "$B" -H 'Content-Type: application/json' \
     -d '{"term":"ruggier","mode":"global"}' http://127.0.0.1:8766/search
curl -s -H "$B" 'http://127.0.0.1:8766/search/1149429/users'
curl -s -X POST -H "$B" -H 'Content-Type: application/json' \
     -d '{"username":"dj","virtual_path":"House\\track.mp3","size":12300000,"duration":300}' \
     http://127.0.0.1:8766/audition
curl -s -H "$B" http://127.0.0.1:8766/audition/<id>
curl -s -X POST -H "$B" http://127.0.0.1:8766/audition/<id>/keep
```

## Threading contract

- Reads (GET) touch engine state directly.
- Mutations (POST/DELETE) are dispatched with `events.invoke_main_thread(...)`
  and the HTTP thread waits (8 s) for the result, so a client can trust the
  response: a 201 means the search/audition exists and is registered.
- A search is registered on the engine thread *before* its first result can
  arrive, so early peer responses are never lost.
- API listeners are wrapped in `engineapi.hub.guard`: an exception in the API
  layer is logged and dropped. It must never reach `events.emit`, which treats a
  failing listener as fatal and quits the client.
- The HTTP server is a daemon thread; SSE subscribers are drained by their own
  handler threads with bounded queues; the transfer flusher is another daemon.

## What stays in Python

Everything protocol- and pipeline-related: login, search, browse, transfers,
shares, the catalogue matcher, peer preview, stem separation and Live Set
generation. The native app owns presentation, audio output and macOS integration
(drag, menus, notifications).

## Migration plan

1. **Engine boundary** — done: API, paged browse, raw JSON shapes, token auth,
   browse timing.
2. **Push updates** — done: `GET /events` with login, browse, transfer, search
   and crate events.
3. **Search** — done: `/search` with engine-side results and paging.
4. **Playback handoff** — done: `/audition` exposes the resolved source and the
   peer-preview lifecycle; the PortAudio player is untouched.
5. **SwiftUI shell spike** — window with paged browse, a player fed by
   `/audition` + AVAudioEngine, and an AppKit drag surface, still launching the
   Python engine as a child process.
6. **Transfer controls + settings** — pause/resume/cancel/keep on
   `/downloads/<id>`, read/write of the digging config.

## Known limits

- No `Last-Event-ID` replay: reconnect gives a fresh `hello` snapshot, not the
  events missed while disconnected. Paged reads cover the gap.
- One Soulseek account per process; two clients on the same account fight.
- `/search` results are engine-side only for searches started through the API.
- SSE is chunked and stays open; every other endpoint is plain HTTP/1.1 with
  keep-alive. A client that reads SSE line-by-line should treat each `data:` line
  as one event (the blank separator is not reliably surfaced by
  `AsyncLineSequence`).
