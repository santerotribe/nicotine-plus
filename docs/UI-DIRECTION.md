# UI direction — the digging client

**Status:** note for the SwiftUI spike. Nothing here is implemented yet; this file
is the brief the spike must follow.

**Two sources, in this order:**

1. **arcaNative** (`/Users/santero-tribe/Schema Apps/arcaNative`) is the family
   look and the architecture precedent. It is a SwiftUI shell driving a Python
   engine over HTTP — the same shape this project is moving to.
2. **The attached reference** (the dark community app: icon rail, list column,
   detail pane, empty-state card) is the **skeleton only**: navigation model,
   column rhythm, list-row anatomy, calm empty states.

Where they disagree, arca wins on type, colour, spacing, depth and control
behaviour. The reference wins on structure.

---

## 1. Precedent: arcaNative is us, later

| | arcaNative | this project |
|---|---|---|
| Shell | SwiftUI + AppKit | SwiftUI (spike), GTK today |
| Engine | Python sidecar over HTTP | `pynicotine` + `digging` over `engineapi` |
| Engine start | app launches it as a child | same |
| Audio | AVAudioEngine in-process | PortAudio today, AVAudioEngine in the native app |
| Drag out | `DragOutHost` + `NSDraggingSession` | `nativedrag.py` overlay → AppKit in the native app |

Read these arca files before writing SwiftUI; they are the vocabulary:

- `Sources/ArcaApp/Theme.swift` — the token table and the font registration trick.
- `Sources/ArcaApp/Controls/ArcaControls.swift` — the control system (two registers).
- `Sources/ArcaApp/Controls/ArcaBrand.swift` — mark-as-path technique.
- `docs/look/` — captures and the audit that names exact CSS values.
- `Package.swift` — how fonts are bundled (`Resources/Fonts`).

## 2. Tokens

Port the **values**, not the code (see §10). A single `Theme.swift` of our own,
structurally identical to arca's: computed statics, token-name overrides ready for
a future personal-theme feature.

### Surfaces (dark, the only skin for now)

| Token | Hex | Use |
|---|---|---|
| `bgCanvas` | `#1A1D1F` | window canvas behind everything |
| `bgBase` | `#1C1E20` | rail, top strip, transport strip |
| `bgWorkspace` | `#202224` | detail pane background |
| `bgCard` | `#202224` | cards inside the detail pane (empty state, stem list) |
| `bgElevated` | `#26292B` | popovers, hovered surfaces |
| `bgRowSelected` | `#2D3134` | selected list row, open menu owner |
| `bgHover` | `#26292B` | row / key hover |
| `border` | `#2C2F31` | hairlines, dividers, card edges |
| `borderMedium` | `#3A3E40` | control edges, focus-adjacent |

Depth is **a ladder of four surfaces plus a 1px line**, never a shadow. The one
exception is the pressed key: an inset black hairline along the top edge.

If the spike wants the reference's deeper black, change `bgCanvas` to `#141617`
and `bgBase` to `#111314` — one token each, nothing else moves.

### Ink

| Token | Hex | Use |
|---|---|---|
| `textPrimary` | `#EEECE6` | titles, selected row, playing track |
| `textSecondary` | `#B6BCB9` | body, key labels, metadata |
| `textTertiary` | `#A8AEAB` | column headers, timestamps |
| `textMuted` | `#9AA19D` | disabled, placeholder, empty-state body |
| `statusSaved` | `#8FBFAE` | "ready", "separated" |
| `statusError` | `#D8938C` | failures (never pure red) |

### Accent

| Token | Hex | Use |
|---|---|---|
| `accent` | `#FFCD52` | playhead, progress, the single primary action |
| `accentHover` | `#FFE093` | primary key hover |
| `accentDeep` | `#BD902C` | primary key pressed / gradient floor |
| `accentSoft` | `#FFCD52` @ 12 % | selection wash, drag target |

Accent budget: **one primary action per screen** and the playhead. Everything else
is ink, hairline and surface. No purple: the reference's violet is replaced by
arca's gold, which is what makes it read as the same family.

### Waveform (do not invent new colours)

`waveGraphite #4A4A4C` for the unplayed body, `waveGraphitePeak #737472` for peaks,
`waveAmber #FFCD52` for played, `bgWaveCanvas #1A1D1F` behind it. Stem lanes use
`sourceSand #B1A286`, `sourceSage #83907E`, `sourceLilac #93839F`,
`sourceClay #B8877B`, `sourceSlate #718292` — one per stem, stable across sessions.

### Radius, size, rhythm

| | |
|---|---|
| Window / shell | 16 |
| Card / panel | 8 |
| Row | 8 |
| Key (library) | 6 |
| Key (instrument) | 3 |
| Rail width | 88 |
| Rail item height | 72 (icon 18 + label 10) |
| Top strip | 52 |
| List column | 380–440 (default 400) |
| Detail pane | min 520 |
| Row height | 48 |
| Transport strip | 48 |
| Key height | 28 (dense 24), instrument 30 |

Spacing rhythm: **4 · 8 · 12 · 16 · 24 · 32**. Panel padding 16, row padding 12
horizontal, column gutters are a **1px hairline**, never a gap with a border.

### Type

Two faces only, both OFL and already bundled in arca (`Resources/Fonts`):

- **Manrope** (variable woff2, cv11 + ss01 alternates on) — UI and library.
- **IBM Plex Mono** 400 — instrument register: transport, tempo, time, stem chips.

| Role | Face | Size / weight |
|---|---|---|
| Detail heading | Manrope | 20 semibold |
| Section title | Manrope | 13 semibold |
| List row title | Manrope | 13 medium |
| List row subtitle | Manrope | 11 regular |
| Key label | Manrope | 12 medium |
| Column header / tag | Manrope | 10 medium, tertiary |
| Instrument label | Mono | 10, UPPERCASE, +0.8 tracking |
| Numeric readout (BPM, clock) | Mono | 11 |

Gotcha, documented in arca's `Theme.swift`: Manrope's family name resolves as
`Manrope ExtraLight`, so look faces up by **instance name**
(`Manrope-Regular`, `-Medium`, `-SemiBold`, `-Bold`) and register the woff2 files
with CoreText at launch. Cache `CTFont` per (name, size); do not build a font per
row per redraw.

### Motion

- Controls: **120 ms easeInOut**. Hover is a colour change, not a transform.
- Panel / detail swap: 200 ms crossfade, no slide.
- Press: 100 ms to the recessed face + inset top hairline.
- The playhead and waveform move with the audio clock, never animated with springs.
- No bounces, no scale-on-hover, no glow. Arca's calm is the point.

## 3. The two registers

Arca splits its controls in two and our app should too — it maps perfectly onto
digging:

| Register | Type | Used for |
|---|---|---|
| **Library** | Manrope 12, sentence case, 28 pt keys, 6 pt corners | rail, search, browse, crate, settings |
| **Instrument** | Mono 10, UPPERCASE, 30 pt keys, 3 pt corners | transport, waveform, stems, tempo, Live set |

A screen declares its register at the root (`controlRegister(.library)`); the
transport strip is always instrument. This is what will make the app feel
"produced" rather than like a generic Mac list.

## 4. Skeleton (from the reference)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  rail 88 │  list column 400        ┃  detail pane (flex, min 520)          │
│          │                         ┃                                       │
│  Browse  │  ┌───────────────────┐  ┃  ┌─────────────────────────────────┐  │
│  Search  │  │ search field      │  ┃  │  card / content                 │  │
│  Audition│  └───────────────────┘  ┃  │                                 │  │
│  Crate   │  row 48 · title/sub     ┃  └─────────────────────────────────┘  │
│  Live    │  row 48 · title/sub     ┃                                       │
│  Digging │  …                      ┃  empty state when nothing selected    │
│          │                         ┃                                       │
├──────────┴─────────────────────────┴───────────────────────────────────────┤
│ transport 48: waveform · time · play · Keep · drag handle   (instrument)   │
└─────────────────────────────────────────────────────────────────────────────┘
```

- **Rail**: icon over a 10 pt label, 72 pt tall, hairline separators between
  groups, account/privileges at the bottom (arca's avatar slot), `+` equivalent is
  "Add peer" / "Open slsk:// link".
- **Top strip 52**: section name centred (13 semibold), right cluster of 3 icon
  keys (transfers, activity, settings) in a shared rounded key group — exactly the
  reference's top-right cluster, in arca surfaces.
- **List column**: search field 28 high with leading magnifier; rows 48 with a
  40 pt leading monogram/artwork, title 13 medium, subtitle 11 regular; trailing
  play glyph appears on hover or when playing; 1px separator only between groups,
  never between rows (hover fill does that job).
- **Detail**: 16 pt inset, cards on `bgWorkspace`, headings 20 semibold; empty
  state is a card with a 40 pt glyph, title, one sentence, and **one** gold key.
- **Transport 48**: always present, instrument register. This is the family
  element the reference lacks and the one that makes auditioning feel continuous
  while browsing.
- The reference's violet pill at the top of the rail is a *space switcher*, not a
  navigation item. Do not copy it as chrome; the account/privileges chip at the
  bottom takes that job, in ink and hairline.

## 5. Screens

1. **Browse** — middle: peers (recently browsed first, `filter` field, row shows
   `864 files · 49.2 GB`, online dot). Detail: folders column (240) + files table,
   or the user's summary header with size/folder counts. Enter auditions, ⌘-drag
   exports, ↑/↓ moves, no right-click.
2. **Search** — middle: query field + recent searches; results arrive live (SSE)
   and are grouped by peer with sticky 32 pt group headers; rows show quality
   (mono 10: `320 · 6:01`) and queue state (`#1055`). Detail: the picked file,
   with **Audition** and **Keep**.
3. **Audition** — detail becomes the listening surface: 20 semibold title, mono
   10 source badge (`PEER · PARTIAL` / `CATALOGUE · ITUNES` / `LOCAL`), full-width
   waveform 120–160 high, instrument transport, BPM/key readouts, stem chips once
   separated. Catalogue→peer handoff is invisible: the badge changes, the playhead
   does not move.
4. **Crate** — rows with a status chip (`kept`, `separating`, `ready`,
   `scheduled`, `failed` in statusSaved/statusError), right detail: stem list with
   durations, "Open in Live", "Separate now".
5. **Live** — generated sets: name, tempo, track/stem count, path; "Reveal" and
   "Open in Live".
6. **Settings** — Soulseek account/network, Digging (renderer, token fields, cache
   budget, export folder), Appearance (future personal tokens).

## 6. Components

- **Rail item**: 64×72, icon 18, label 10 medium; hover `bgHover`; selected
  `bgRowSelected` + `textPrimary`; no accent bar, no glow.
- **Key**: hairline box, 28/30 high, 12/10 pad; hover fills `bgHover`; pressed
  recesses to `bgWaveCanvas` with the inset hairline.
- **Primary key**: the one gold gradient (`#FFDC7D → #FFCB4C → #EEB735`), dark ink
  `#1A1D1F`, 6 pt corners; used for Keep / New conversation equivalent. At most
  one per screen.
- **Search field**: 28 high, 6 pt corners, `bgControl`, 1px border, leading
  magnifier, placeholder `textMuted`.
- **Monogram**: 40 pt circle, `bgSecondary`, 13 medium initials; artwork replaces
  it when the catalogue has a match (same size, 2 pt inner border).
- **Status chip**: 10 medium, uppercase only when instrument; 4×8 padding; 3 pt
  corners; colour from status tokens at 12 % wash with a 1px border.
- **Waveform**: Canvas-drawn, 1px per bar at 60 fps, played = amber, unplayed =
  graphite, peak line lighter; no gradient fills.
- **Empty state**: card, 40 pt glyph (hairline, not filled), 20 semibold title,
  11 muted body, one gold key.
- **Drag handle**: 24 pt icon on the transport's right, `⌘` hints in a popover on
  first use only.

## 7. Interaction rules (non-negotiable)

- **Keyboard first**: ↑/↓ move, Enter auditions, Space toggles transport, ⌘F focuses
  the list filter, ⌘K search, Esc closes the detail. No right-click as the only
  path to anything.
- **No floating windows** for drag; the drag is a real `NSDraggingSession` from the
  row/handle (arca's `DragOutHost` and our `nativedrag.py` are the two references).
- **Hover is quiet**: fill only, no lift, no border colour change beyond 1 px.
- **Focus**: 2 pt `borderSelected` ring at 58 % instead of macOS's blue.
- **Loading**: skeleton rows at 48 pt with a 12 % ink shimmer; no spinners over
  content.
- **Offline peers**: shown, not hidden — queue position in mono, retry key enabled.

## 8. SwiftUI shape

```
Sources/DigApp/
  Theme.swift             tokens + font registration (port of arca's Theme.swift)
  Controls/Keys.swift     DigKeyStyle, DigPrimaryKeyStyle, chips
  Shell/AppShell.swift    HStack: Rail · List · Detail; transport overlay
  Shell/Transport.swift   instrument register, waveform, drag handle
  Screens/Browse/*.swift
  Screens/Search/*.swift
  Screens/Audition/*.swift
  Screens/Crate/*.swift
  Screens/Live/*.swift
  Engine/EngineClient.swift   async HTTP + URLSession SSE (/events)
  Engine/Player.swift         AVAudioEngine fed by /audition source
  Drag/DragOutHost.swift      NSDraggingSession for files
```

- Custom `HStack` shell, **not** `NavigationSplitView` — we need 1px hairlines and
  exact widths.
- Lists: `List` with `.listStyle(.plain)` and manual row insets, or a
  `ScrollView + LazyVStack` when rows get heavy; never build a row's Font or
  formatter inside `body`.
- Engine: keep the Python process as a child (`Process`), wait for `/health`, then
  open `/events`. Browse/search pages are already paged for virtualisation.
- Audio: `AVAudioEngine` + `AVAudioPlayerNode` reading the file from
  `/audition/<id>.source`; clamp seeks to `peer.bytes`; swap to the finished peer
  file when `peer.complete`.

## 9. What must not change

- Enter audition, ⌘-drag to Ableton, no right-click dependency, peer-first playback
  with catalogue bridging, automatic preview cleanup — the product behaviour is
  settled; only the skin changes.
- No new accent colours, no icon set of our own: SF Symbols plus the family's
  hairline geometry.

## 10. Licensing

arcaNative is a separate product; this repo is GPL-3.0-or-later. **Port values and
techniques, never paste Arca source.** The token table, metric numbers and font
loading approach are facts and methods; a `Theme.swift` written against them is
ours. The two fonts (Manrope, IBM Plex Mono) are OFL — bundle them with their
licence files, as arca does.

## 11. Open decisions (want a yes/no before the spike)

1. **Accent**: gold `#FFCD52` (family, recommended) or the reference's violet?
2. **Rail**: 88 pt icon rail (reference structure, recommended) or arca's 206 pt
   labelled sidebar?
3. **Transport**: persistent 48 pt bottom strip (recommended) or only inside the
   Audition screen?
4. **Canvas depth**: arca's `#1A1D1F` (recommended) or the reference's near-black
   `#141617`?
5. **Scope**: should the spike cover Browse + Audition + transport only, or all six
   screens with placeholder content?
