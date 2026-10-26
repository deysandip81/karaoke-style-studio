"""Style engine: remix separated stems and reshape tone/tempo/pitch.

Built entirely from ffmpeg filters on top of Demucs/ffmpeg stems — this is
DSP remixing and tone-shaping, not generative instrument synthesis. It can
make a track feel softer/acoustic, punchier/modern, lo-fi, or spacious; it
cannot literally replay the song on a different instrument.
"""
import shutil
import subprocess
from pathlib import Path

FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"

PRESETS = {
    "soft_acoustic": {
        "label": "Soft Acoustic",
        "description": "Guitar-forward and mellow — drums dropped low, warm mid presence, light room reverb.",
        "gains": {"drums": 0.15, "bass": 0.5, "other": 1.0, "vocals": 0.0},
        "filters": [
            "highpass=f=70",
            "equalizer=f=2200:t=o:w=1.5:g=3",
            "lowpass=f=10000",
            "aecho=0.8:0.7:50:0.2",
            "compand=attacks=0.05:decays=0.3:points=-80/-80|-40/-35|-20/-18|0/-10",
        ],
    },
    "modern_punch": {
        "label": "Modern Punch",
        "description": "Tight and bright — boosted bass/presence, wider stereo, loudness-normalised.",
        "gains": {"drums": 1.1, "bass": 1.2, "other": 0.9, "vocals": 0.0},
        "filters": [
            "bass=g=4:f=90",
            "treble=g=3:f=6000",
            "extrastereo=m=1.3",
            "compand=attacks=0.01:decays=0.15:points=-80/-80|-30/-20|-15/-10|0/-3",
            "loudnorm=I=-14:TP=-1.5",
        ],
    },
    "lofi_chill": {
        "label": "Lo-fi Chill",
        "description": "Warm, hazy, slightly wobbly — rolled-off highs, soft slap, gentle vibrato.",
        "gains": {"drums": 0.6, "bass": 0.8, "other": 0.9, "vocals": 0.0},
        "filters": [
            "lowpass=f=4200",
            "vibrato=f=4:d=0.3",
            "aecho=0.6:0.5:40:0.15",
            "compand=attacks=0.1:decays=0.4:points=-80/-80|-40/-30|-20/-16|0/-12",
        ],
    },
    "cinematic_soft": {
        "label": "Cinematic Soft",
        "description": "Spacious and atmospheric — long reverb tail, softened highs, slow fade-in.",
        "gains": {"drums": 0.3, "bass": 0.7, "other": 1.0, "vocals": 0.0},
        "filters": [
            "lowpass=f=9000",
            "aecho=0.9:0.85:200:0.35",
            "afade=t=in:st=0:d=2",
        ],
    },
    "custom": {
        "label": "Custom",
        "description": "Your own stem balance and tone knobs.",
        "gains": {"drums": 1.0, "bass": 1.0, "other": 1.0, "vocals": 0.0},
        "filters": [],
    },
}

STEM_ORDER = ["drums", "bass", "other", "vocals"]


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def custom_tone_filters(tone: dict) -> list:
    """Build filters from Custom-preset tone knobs (all 0-100 unless noted)."""
    f = []
    warmth = _clamp(tone.get("warmth", 0), -100, 100)       # bass tilt
    brightness = _clamp(tone.get("brightness", 0), -100, 100)  # treble tilt
    reverb = _clamp(tone.get("reverb", 0), 0, 100)           # 0 = none
    punch = _clamp(tone.get("punch", 0), 0, 100)             # compression amount

    if warmth:
        f.append(f"bass=g={round(warmth / 100 * 8, 1)}:f=100")
    if brightness:
        f.append(f"treble=g={round(brightness / 100 * 8, 1)}:f=6000")
    if reverb > 0:
        decay = round(0.3 + reverb / 100 * 0.6, 2)
        delay = int(40 + reverb / 100 * 160)
        f.append(f"aecho=0.8:{decay}:{delay}:0.25")
    if punch > 0:
        depth = round(-3 - punch / 100 * 12, 1)
        f.append(f"compand=attacks=0.02:decays=0.2:points=-80/-80|-20/-14|0/{depth}")
    return f


def _atempo_chain(factor: float) -> list:
    """atempo only accepts 0.5-2.0; chain stages for values outside that."""
    if factor <= 0:
        return []
    stages = []
    remaining = factor
    while remaining < 0.5 or remaining > 2.0:
        step = 2.0 if remaining > 2.0 else 0.5
        stages.append(step)
        remaining /= step
    stages.append(round(remaining, 4))
    return [f"atempo={s}" for s in stages if abs(s - 1.0) > 1e-3]


def tempo_pitch_filters(tempo: float, semitones: float, sample_rate: int = 44100) -> list:
    """tempo: 0.5-1.5 playback speed. semitones: -6..+6 key shift, tempo-preserving."""
    filters = []
    tempo = _clamp(tempo or 1.0, 0.5, 1.75)
    semitones = _clamp(semitones or 0.0, -6, 6)

    if abs(semitones) > 1e-3:
        ratio = 2 ** (semitones / 12.0)
        new_rate = int(round(sample_rate * ratio))
        filters.append(f"asetrate={new_rate}")
        filters.append(f"aresample={sample_rate}")
        # asetrate changed playback speed by `ratio`; undo that, then apply
        # the user's requested tempo on top.
        filters += _atempo_chain(tempo / ratio)
    else:
        filters += _atempo_chain(tempo)
    return filters


def build_render_command(stems: dict, gains: dict, preset: str, tempo: float,
                          semitones: float, tone: dict, out_wav: Path) -> list:
    """Compose the full ffmpeg filter_complex graph and return the argv list."""
    cfg = PRESETS.get(preset, PRESETS["custom"])
    merged_gains = dict(cfg["gains"])
    merged_gains.update({k: v for k, v in (gains or {}).items() if v is not None})

    inputs = []
    vol_labels = []
    for i, stem in enumerate(STEM_ORDER):
        path = stems.get(stem)
        gain = _clamp(merged_gains.get(stem, 0.0), 0.0, 2.0)
        if not path or gain <= 0.001:
            continue
        inputs.append(str(path))
        idx = len(inputs) - 1
        vol_labels.append(f"[{idx}:a]volume={gain}[a{idx}]")

    if not inputs:
        # fall back to whatever single stem exists (e.g. ffmpeg backend)
        only = next(iter(stems.values()))
        inputs = [str(only)]
        vol_labels = ["[0:a]volume=1.0[a0]"]

    mix_labels = "".join(f"[a{i}]" for i in range(len(inputs)))
    if len(inputs) > 1:
        mix = f"{mix_labels}amix=inputs={len(inputs)}:normalize=0[mixed]"
    else:
        mix = "[a0]acopy[mixed]"

    tone_filters = (custom_tone_filters(tone) if preset == "custom"
                     else list(cfg["filters"]))
    tp_filters = tempo_pitch_filters(tempo, semitones)
    chain = tone_filters + tp_filters

    last = "mixed"
    stages = []
    for n, flt in enumerate(chain):
        nxt = f"s{n}"
        stages.append(f"[{last}]{flt}[{nxt}]")
        last = nxt

    graph = ";".join(vol_labels + [mix] + stages)
    cmd = [FFMPEG, "-y"]
    for p in inputs:
        cmd += ["-i", p]
    cmd += ["-filter_complex", graph, "-map", f"[{last}]",
            "-ar", "44100", "-c:a", "pcm_s16le", str(out_wav)]
    return cmd


def render(stems: dict, gains: dict, preset: str, tempo: float,
           semitones: float, tone: dict, out_wav: Path):
    cmd = build_render_command(stems, gains, preset, tempo, semitones, tone, out_wav)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("Render failed:\n" + proc.stderr[-1500:])
    return out_wav
