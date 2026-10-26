"""Background job registry for separation runs."""
import threading
import time
import traceback
import uuid
from pathlib import Path

import separator

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "workspace"
WORK.mkdir(exist_ok=True)

_jobs = {}
_lock = threading.Lock()
_gpu_lock = threading.Lock()  # Demucs is memory hungry; serialise runs.


def create(filename: str, raw: bytes, backend: str, model: str):
    jid = uuid.uuid4().hex[:12]
    jdir = WORK / jid
    jdir.mkdir(parents=True)
    src = jdir / ("input" + Path(filename).suffix.lower())
    src.write_bytes(raw)

    job = {
        "id": jid, "name": filename, "backend": backend, "model": model,
        "status": "queued", "progress": 0, "stage": "Queued",
        "stems": {}, "error": None, "duration": 0.0,
        "created": time.time(), "elapsed": 0.0, "dir": str(jdir),
    }
    with _lock:
        _jobs[jid] = job
    threading.Thread(target=_run, args=(jid, src, jdir), daemon=True).start()
    return job


def get(jid):
    with _lock:
        job = _jobs.get(jid)
        return dict(job) if job else None


def stem_path(jid, stem):
    job = get(jid)
    if not job:
        return None
    p = job["stems"].get(stem)
    return Path(p) if p else None


def job_dir(jid):
    job = get(jid)
    return Path(job["dir"]) if job else None


def _set(jid, **kw):
    with _lock:
        if jid in _jobs:
            _jobs[jid].update(kw)
            _jobs[jid]["elapsed"] = round(time.time() - _jobs[jid]["created"], 1)


def _run(jid, src: Path, jdir: Path):
    def progress(pct, stage):
        _set(jid, progress=round(min(99.0, max(0.0, pct)), 1), stage=stage)

    try:
        _set(jid, status="running")
        progress(3, "Decoding input audio")
        wav = separator.to_wav(src, jdir / "normalised.wav")
        _set(jid, duration=separator.probe_duration(wav))

        job = get(jid)
        outdir = jdir / "stems"
        if job["backend"] == "demucs":
            progress(8, "Loading separation model")
            with _gpu_lock:
                stems = separator.separate_demucs(wav, outdir, job["model"], progress)
        else:
            stems = separator.separate_ffmpeg(wav, outdir, progress)

        progress(97, "Finalising stems")
        _set(jid, stems={k: str(v) for k, v in stems.items()},
             status="done", progress=100, stage="Complete")
    except Exception as exc:
        _set(jid, status="error", stage="Failed",
             error=str(exc) or traceback.format_exc()[-800:])
