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
