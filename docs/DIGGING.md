# Digging pipeline (our extension)

Turns the Nicotine+ client into a crate-digging tool for house production:

1. browse a user's shares and audition tracks without leaving the app
2. keep the ones that work, download them
3. separate the stems (MVSEP cloud, studio PC, or local Demucs)
4. build an Ableton Live Set with one warped track per stem, tempo-matched
   to the sampled record

Everything below runs today from the CLI; the GUI wiring reuses the same
modules.

## Layout

| Module | Responsibility |
|---|---|
| [analyze.py](../pynicotine/digging/analyze.py) | ffprobe metadata, tempo detection, waveform peaks |
| [crate.py](../pynicotine/digging/crate.py) | the persisted list of candidate/kept tracks |
| [renderers/](../pynicotine/digging/renderers) | separation backends: MVSEP, studio PC agent, local Demucs |
| [ableton.py](../pynicotine/digging/ableton.py) | Live Set generation through ALS Observatory + warp/loudness finishing |
| [pipeline.py](../pynicotine/digging/pipeline.py) | one track in, stems and a Live Set out |
| [agent.py](../pynicotine/digging/agent.py) | the studio-PC side HTTP/Demucs worker |

## The Ableton step

We deliberately do not hand-write track XML. ALS Observatory
(`~/Documents/ALS Observatory`) builds the set from Live-saved schema
templates, and [ableton.py](../pynicotine/digging/ableton.py) then:

- writes one audio track per stem, named after the stem
- sets the project tempo to the detected tempo of the sampled record
- enables warping with a two-point tempo map at that tempo, so the stems
  stay aligned when the set tempo moves later
- picks a sensible warp mode per stem (drums -> Beats, bass -> Tones,
  tonal material -> Complex Pro)

## Auditioning: catalogue first, peer second

Soulseek has no streaming: bytes only arrive from one peer, through their
queue. So a click first tries to identify the track against a public
catalogue (iTunes Search, no token, 30 s official preview) and streams that
instantly, with a full waveform and instant seeking. Only when there is no
match -- white labels, promos, edits -- do we fall back to a ranged peer
fetch (a 1.5 MB window via FileOffset, 6 s budget before moving on).

```sh
python -m pynicotine.digging match "01 Ruggier - Long Ride (Original Mix).aiff"
python -m pynicotine.digging preview "01 Ruggier - Long Ride (Original Mix).aiff" --seconds 20
```

Playback uses PortAudio (`sounddevice`) so the app owns the buffer: instant
seeks, sample-accurate playhead for the waveform, no external player.

A native front end does not use that player. `POST /audition` starts the same
peer preview and catalogue lookup headlessly and answers `GET /audition/<id>`
with the file to open right now (`local` → `peer` partial → `catalogue` URL) plus
the peer's byte horizon, so AVAudioEngine can stream it without the engine ever
touching audio output. See [ENGINE-API.md](ENGINE-API.md#audition--playback-handoff).

## First run

Press **Separation…** in the Dig window once and pick one of:

- **MVSEP** — paste an API token and a separation type id
- **Studio PC** — the agent URL and its token
- **This Mac** — local Demucs, if installed

Keeping a track before this is configured opens the same dialog instead of
failing later: keep downloads the file, separation runs when it lands, the Live
Set is built and opened, and the crate records the result.

## Setup

### MVSEP

```sh
python -m pynicotine.digging settings set mvsep_token=YOUR_TOKEN
python -m pynicotine.digging types          # list render_id values
python -m pynicotine.digging settings set mvsep_sep_type=<render_id> preset=4
```

### Studio PC

On the PC that owns the GPU:

```sh
python -m pynicotine.digging agent --token SECRET --port 8765
```

On the Mac:

```sh
python -m pynicotine.digging settings set renderer=pc pc_url=http://studio-pc.local:8765 pc_token=SECRET
```

### Local Demucs

```sh
pip install demucs
python -m pynicotine.digging settings set renderer=local
```

## Use

```sh
python -m pynicotine.digging analyze "/path/to/record.flac"
python -m pynicotine.digging run "/path/to/record.flac" --preset 4 --name "Night Drive"
python -m pynicotine.digging build ./stems --bpm 92 --name "Night Drive"
```

Settings live in `~/.config/nicotine/digging.json` (override the config root
with `XDG_CONFIG_HOME`).

## Tests

```sh
python -m pytest pynicotine/tests/unit/digging -q
```
