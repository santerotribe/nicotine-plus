# Tribe Seek — the native client

A SwiftUI shell for the digging engine, built to the brief in
[`docs/UI-DIRECTION.md`](../../docs/UI-DIRECTION.md): arcaNative's tokens and
control registers on the reference's rail → list → detail skeleton, with a
persistent instrument transport.

This is the product's front end. GTK is frozen as a debug tool. Today it proves
the API is enough:

- browse a peer's shares through the paged endpoints, Enter to audition;
- `/audition` drives an AVAudioEngine player (local file, peer partial, or a
  catalogue URL downloaded once);
- the engine's SSE stream keeps the UI current (browse completion, audition
  progress, crate status);
- Keep adds the file to the crate; drag out is a real AppKit
  `NSDraggingSession`, the path that works with Live and Finder.

## Run it

```sh
# from the repo root, with the GTK app's engine already on 8766:
NICOTINE_API_URL=http://127.0.0.1:8766 NICOTINE_API_TOKEN=devtoken \
  native/TribeSeek/run.sh

# or let the app start the engine headless as a child process:
native/TribeSeek/run.sh
```

`run.sh` builds with SwiftPM and launches the binary. The build uses
`--disable-sandbox` because this environment forbids nested sandboxes.

## Verify without clicking

```sh
TRIBE_SELFTEST=1 NICOTINE_API_TOKEN=devtoken native/TribeSeek/run.sh
```

It browses your own shares, starts an audition, waits for a resolved source,
prints PASS/FAIL per step, closes the session and exits non-zero on failure.

`TRIBE_AUTO=1` auditions the first file after the first browse, so the transport
and waveform can be checked visually.

## What is deliberately missing

- Search, crate and live screens are thin; Live and Settings are placeholders.
- No waveform scrubbing cache beyond the file's own peaks; long mixes still read
  the whole file once.
- Peer partial playback opens the file once; if the header is not decodable yet
  it reports buffering instead of retrying when more bytes arrive.
- No separation controls or stem view yet.
