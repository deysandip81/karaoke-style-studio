# Karaoke Style Studio

Separate a song into stems, then remix the balance and reshape the tone —
Soft Acoustic, Modern Punch, Lo-fi Chill, Cinematic Soft, or your own custom
blend — with independent tempo and key-shift controls. Runs entirely on your
own machine; no audio is uploaded anywhere.

A sibling project to **Karaoke Builder** (plain vocal/instrumental split).
This one adds a style layer on top.

## What this can and can't do

**Can:** isolate drums/bass/other/vocals, rebalance their volumes, apply
EQ/reverb/compression "mood" recipes, and independently shift tempo or pitch
(key). This genuinely changes how a track feels — softer, punchier, hazier,
more spacious.

**Can't:** literally re-perform the song on a different instrument (e.g.
regenerate it as if a guitarist played it). That's generative music
synthesis, a different technology from source separation + DSP, and isn't
something this tool — or any free local pipeline — does reliably today.

---

## Quick start

```bash
git clone <this-repo-url> karaoke-style-studio
cd karaoke-style-studio
./setup.sh     # one-time: installs prerequisites + Python environment
./run.sh       # starts the server
```

Open **http://127.0.0.1:8989**.

## Prerequisites

`setup.sh` installs these automatically (macOS via Homebrew, Linux via
apt/dnf/yum):

| Requirement | Why |
|---|---|
| Python 3.10+ | Runs the server and separation pipeline |
| ffmpeg | Decodes/encodes audio, builds the style/tone filter chains |

First Studio-engine run downloads Demucs model weights (~80 MB) once.

## Using it

1. **Upload** a song (mp3/wav/m4a/flac/aac/ogg/aiff, 300 MB max). Choose
   Studio (4-stem Demucs, best control) or Fast (2-stem ffmpeg, instant).
2. **Pick a style preset** — each is a pre-tuned stem balance plus an EQ/
   reverb/compression recipe:

   | Preset | Feel |
   |---|---|
   | Soft Acoustic | Guitar-forward, mellow — drums dropped low, warm presence, light room reverb |
   | Modern Punch | Tight, bright, loud — boosted bass/presence, wider stereo, loudness-normalised |
   | Lo-fi Chill | Warm, hazy, slightly wobbly — rolled-off highs, soft slap-back, gentle vibrato |
   | Cinematic Soft | Spacious, atmospheric — long reverb tail, softened highs, slow fade-in |
   | Custom | Your own stem gains plus warmth / brightness / reverb / punch knobs |

3. **Adjust stem sliders** (Drums, Bass, Other, Vocals) — each preset
   pre-fills sensible defaults, fully overridable per stem (0–150%).
4. **Tempo & key** — tempo 50–150% of original speed; key shift ±6
   semitones, independent of tempo (useful for singers who need a
   different key).
5. **Render** and preview/download in WAV, MP3, M4A, or FLAC.

## Project layout

```
karaoke-style-studio/
├── setup.sh / run.sh / requirements.txt
├── server.py       # stdlib HTTP server + JSON API
├── separator.py    # ffmpeg normalisation + Demucs 4-stem split
├── styler.py        # stem remix + preset/tone/tempo/pitch filter graphs
├── jobs.py          # background separation job registry
├── static/          # UI (index.html, style.css, app.js)
├── workspace/        # per-job stems + rendered output — gitignored
├── LICENSE
└── README.md
```

## API reference

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/capabilities` | GET | Demucs availability, models, formats, preset catalogue |
| `/api/upload` | POST | Raw audio; headers `X-Filename`, `X-Backend`, `X-Model`. Returns `{id}` |
| `/api/job/<id>` | GET | Separation status/progress/stems |
| `/api/stem/<id>/<stem>?format=&download=` | GET | Preview/download a raw stem |
| `/api/style/<id>` | POST | JSON `{preset, gains, tempo, semitones, tone}` → renders and returns `{token}` |
| `/api/render/<id>/<token>?format=&download=` | GET | Preview/download the rendered styled track |

## Configuration

| Env var | Default |
|---|---|
| `KSS_PORT` | `8989` |

## Troubleshooting

- **Style controls greyed out on Fast engine** — the ffmpeg 2-stem split
  only yields vocals + instrumental; drums/bass/other sliders need the
  Studio (Demucs) engine.
- **Render sounds clipped/distorted** — lower stem gains below 100%, or
  reduce the Punch/compression knob on Custom preset.
- **Key shift sounds chipmunk-y at extremes** — keep within ±6 semitones;
  the asetrate-based pitch shift degrades beyond that.

## Third-party licenses

This project's code is MIT (see `LICENSE`). Dependencies: Demucs (MIT,
Meta/FAIR), PyTorch/torchaudio (BSD-style), FFmpeg (LGPL/GPL, invoked as an
external binary, not bundled).

**Content note:** separating/remixing and redistributing commercial
copyrighted recordings is a copyright question independent of this
software's license. Built for audio you own or have rights to use.
