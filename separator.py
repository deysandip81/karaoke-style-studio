"""Audio normalisation and stem separation for Karaoke Style Studio.

Always separates into up to 4 stems when using Demucs (vocals, drums, bass,
other) so the Style engine has per-instrument control. The Fast ffmpeg
backend only yields vocals + instrumental (style control is limited to tone
shaping on the instrumental as a whole).
"""
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / ".venv" / "bin" / "python"
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"

STEM_LABELS = {
    "vocals": "Vocals",
    "drums": "Drums",
    "bass": "Bass",
    "other": "Other (guitars, keys, pads)",
    "no_vocals": "Instrumental (whole mix)",
}


def python_bin() -> str:
    return str(VENV_PY) if VENV_PY.exists() else "python3"


def demucs_available() -> bool:
    try:
        subprocess.run([python_bin(), "-c", "import demucs"],
                        check=True, capture_output=True, timeout=60)
        return True
    except Exception:
        return False


def probe_duration(path: Path) -> float:
    try:
        out = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        return round(float(out.stdout.strip()), 2)
    except Exception:
        return 0.0


def to_wav(src: Path, dst: Path) -> Path:
    subprocess.run(
        [FFMPEG, "-y", "-i", str(src), "-vn", "-ac", "2", "-ar", "44100",
         "-c:a", "pcm_s16le", str(dst)],
        check=True, capture_output=True,
    )
    return dst


def separate_demucs(wav: Path, outdir: Path, model: str, progress):
    """Full 4-stem Demucs split: vocals, drums, bass, other."""
    cmd = [python_bin(), "-m", "demucs", "-n", model, "-o", str(outdir), str(wav)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, bufsize=1)
    tail = []
    for line in proc.stdout:
        line = line.strip()
        if line:
            tail.append(line)
            tail[:] = tail[-12:]
        m = re.search(r"(\d+(?:\.\d+)?)%", line)
        if m:
            progress(10 + float(m.group(1)) * 0.8, "Separating stems")
    if proc.wait() != 0:
        raise RuntimeError("Demucs failed:\n" + "\n".join(tail))

    produced = sorted(outdir.rglob("*.wav"))
    if not produced:
        raise RuntimeError("Demucs produced no output:\n" + "\n".join(tail))
    return {p.stem: p for p in produced}


def separate_ffmpeg(wav: Path, outdir: Path, progress):
    """Mid/side approximation. Only vocals + instrumental are available."""
    outdir.mkdir(parents=True, exist_ok=True)
    inst = outdir / "no_vocals.wav"
    voc = outdir / "vocals.wav"

    progress(25, "Extracting instrumental (side channel)")
    subprocess.run([FFMPEG, "-y", "-i", str(wav), "-af",
                    "pan=stereo|c0=c0-c1|c1=c1-c0", str(inst)],
                   check=True, capture_output=True)
    progress(65, "Extracting vocals (centre channel)")
    subprocess.run([FFMPEG, "-y", "-i", str(wav), "-af",
                    "pan=mono|c0=0.5*c0+0.5*c1,highpass=f=180,lowpass=f=6000",
                    "-ac", "2", str(voc)],
                   check=True, capture_output=True)
    return {"vocals": voc, "no_vocals": inst}


def encode(src: Path, fmt: str, dst: Path = None) -> Path:
    if fmt == "wav" and dst is None:
        return src
    dst = dst or src.with_suffix("." + fmt)
    if dst.exists():
        return dst
    codec = {
        "mp3": ["-c:a", "libmp3lame", "-b:a", "320k"],
        "m4a": ["-c:a", "aac", "-b:a", "256k"],
        "flac": ["-c:a", "flac"],
        "wav": ["-c:a", "pcm_s16le"],
    }[fmt]
    subprocess.run([FFMPEG, "-y", "-i", str(src)] + codec + [str(dst)],
                   check=True, capture_output=True)
    return dst
