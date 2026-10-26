"""Karaoke Style Studio - local HTTP server. Stdlib only, no web framework.

Run:  ./run.sh        then open http://127.0.0.1:8989
"""
import hashlib
import json
import mimetypes
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import jobs
import separator
import styler

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
HOST, PORT = "127.0.0.1", int(os.environ.get("KSS_PORT", "8989"))
MAX_UPLOAD = 300 * 1024 * 1024
FORMATS = {"wav", "mp3", "m4a", "flac"}


class Handler(BaseHTTPRequestHandler):
    server_version = "KaraokeStyleStudio/1.0"

    def log_message(self, fmt, *args):
        print("[kss] " + fmt % args)

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, download_name=None):
        if not path.exists():
            return self._json({"error": "not found"}, 404)
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(path.stat().st_size))
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.end_headers()
        with path.open("rb") as fh:
            while chunk := fh.read(262144):
                self.wfile.write(chunk)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    # ---------------- GET ----------------
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        qs = urllib.parse.parse_qs(url.query)

        if not parts:
            return self._file(STATIC / "index.html")
        if len(parts) == 1 and (STATIC / parts[0]).is_file():
            return self._file(STATIC / parts[0])

        if parts[:2] == ["api", "capabilities"]:
            return self._json({
                "demucs": separator.demucs_available(),
                "formats": sorted(FORMATS),
                "models": ["htdemucs", "htdemucs_ft", "mdx_extra"],
                "presets": [
                    {"key": k, "label": v["label"], "description": v["description"],
                     "gains": v["gains"]}
                    for k, v in styler.PRESETS.items()
                ],
            })

        if parts[:2] == ["api", "job"] and len(parts) == 3:
            job = jobs.get(parts[2])
            if not job:
                return self._json({"error": "unknown job"}, 404)
            job["stem_list"] = [
                {"key": k, "label": separator.STEM_LABELS.get(k, k.title())}
                for k in sorted(job["stems"])
            ]
            job["stems"] = list(job["stems"])
            job.pop("dir", None)
            return self._json(job)

        if parts[:2] == ["api", "stem"] and len(parts) == 4:
            jid, stem = parts[2], parts[3]
            fmt = (qs.get("format", ["wav"])[0]).lower()
            dl = qs.get("download", ["0"])[0] == "1"
            if fmt not in FORMATS:
                return self._json({"error": "bad format"}, 400)
            src = jobs.stem_path(jid, stem)
            if not src:
                return self._json({"error": "unknown stem"}, 404)
            out = separator.encode(src, fmt)
            job = jobs.get(jid) or {}
            name = f"{Path(job.get('name', 'track')).stem} - {stem}.{fmt}" if dl else None
            return self._file(out, name)

        if parts[:2] == ["api", "render"] and len(parts) == 4:
            jid, token = parts[2], parts[3]
            fmt = (qs.get("format", ["wav"])[0]).lower()
            dl = qs.get("download", ["0"])[0] == "1"
            jdir = jobs.job_dir(jid)
            if not jdir:
                return self._json({"error": "unknown job"}, 404)
            wav = jdir / "renders" / f"{token}.wav"
            if not wav.exists():
                return self._json({"error": "unknown render"}, 404)
            out = separator.encode(wav, fmt, dst=wav.with_suffix("." + fmt))
            job = jobs.get(jid) or {}
            name = f"{Path(job.get('name', 'track')).stem} - styled.{fmt}" if dl else None
            return self._file(out, name)

        return self._json({"error": "not found"}, 404)

    # ---------------- POST ----------------
    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]

        if url.path == "/api/upload":
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return self._json({"error": "empty body"}, 400)
            if length > MAX_UPLOAD:
                return self._json({"error": "file too large (300 MB max)"}, 413)

            filename = urllib.parse.unquote(self.headers.get("X-Filename") or "upload.mp3")
            backend = (self.headers.get("X-Backend") or "demucs").lower()
            model = self.headers.get("X-Model") or "htdemucs"

            if backend == "demucs" and not separator.demucs_available():
                return self._json({"error": "Demucs is not installed. Use the Fast engine, "
                                             "or finish setup.sh."}, 409)

            raw = self._read_body()
            job = jobs.create(Path(filename).name, raw, backend, model)
            return self._json({"id": job["id"]}, 202)

        if parts[:2] == ["api", "style"] and len(parts) == 3:
            jid = parts[2]
            job = jobs.get(jid)
            if not job or job.get("status") != "done":
                return self._json({"error": "job not ready"}, 409)
            try:
                payload = json.loads(self._read_body() or b"{}")
            except Exception:
                return self._json({"error": "bad JSON body"}, 400)

            stems = {k: Path(v) for k, v in job["stems"].items()}
            gains = payload.get("gains") or {}
            preset = payload.get("preset") or "custom"
            tempo = float(payload.get("tempo", 1.0))
            semitones = float(payload.get("semitones", 0.0))
            tone = payload.get("tone") or {}

            token = hashlib.sha1(
                json.dumps([sorted(gains.items()), preset, tempo, semitones,
                            sorted(tone.items())], sort_keys=True).encode()
            ).hexdigest()[:16]

            jdir = jobs.job_dir(jid)
            renders = jdir / "renders"
            renders.mkdir(exist_ok=True)
            out_wav = renders / f"{token}.wav"
            if not out_wav.exists():
                try:
                    styler.render(stems, gains, preset, tempo, semitones, tone, out_wav)
                except Exception as exc:
                    return self._json({"error": str(exc)}, 500)

            return self._json({"token": token}, 200)

        return self._json({"error": "not found"}, 404)


def main():
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Karaoke Style Studio running at http://{HOST}:{PORT}")
    print(f"Demucs available: {separator.demucs_available()}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
        srv.shutdown()


if __name__ == "__main__":
    main()
