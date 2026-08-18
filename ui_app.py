#!/usr/bin/env python3
"""Launch the Fetch by Fisola UI in your browser."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path

from flask import Flask, Response, abort, jsonify, request, send_file, send_from_directory

from core import download_one, has_ffmpeg, system_status

ROOT = Path(__file__).resolve().parent
UI_DIR = ROOT / "ui"


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return os.access(path, os.W_OK)


def resolve_download_dir() -> Path:
    """Where downloads land.

    Locally that is ~/Downloads. On a host it usually cannot be: serverless
    sandboxes (AWS Lambda's /home/sbx_user*, for one) mount everything except
    the temp directory read-only, so writing there fails with Errno 30.
    """
    override = os.environ.get("FETCH_DOWNLOAD_DIR")
    if override:
        candidate = Path(override).expanduser()
        if _writable(candidate):
            return candidate
    home = Path.home() / "Downloads"
    if _writable(home):
        return home
    return Path(tempfile.gettempdir()) / "fetch-downloads"


DOWNLOADS = resolve_download_dir()
# Only a local macOS run can reveal a file in Finder; anywhere else the browser
# has to be handed the bytes instead.
IS_LOCAL = sys.platform == "darwin" and DOWNLOADS == Path.home() / "Downloads"

app = Flask(__name__, static_folder=None)

_job_lock = threading.Lock()
_busy = False


@app.get("/")
def index():
    return send_from_directory(UI_DIR, "index.html")


@app.get("/assets/<path:filename>")
def assets(filename: str):
    return send_from_directory(UI_DIR, filename)


@app.get("/api/status")
def api_status():
    st = system_status()
    st["downloads"] = str(DOWNLOADS)
    st["local"] = IS_LOCAL
    return jsonify(st)


def _inside_downloads(raw: str) -> Path:
    """Resolve a client-supplied path, refusing anything outside DOWNLOADS."""
    try:
        target = Path(raw).expanduser().resolve()
        root = DOWNLOADS.resolve()
    except OSError:
        abort(400)
    if not target.is_relative_to(root) or not target.is_file():
        abort(404)
    return target


@app.get("/api/file")
def api_file():
    """Hand a finished download to the browser (the hosted equivalent of Reveal)."""
    target = _inside_downloads(request.args.get("path", ""))
    return send_file(target, as_attachment=True, download_name=target.name)


@app.post("/api/reveal")
def api_reveal():
    """Open the downloads folder (or a specific file) in Finder on macOS."""
    if not IS_LOCAL:
        return jsonify({"ok": False, "error": "Reveal only works on the local macOS app."}), 400
    data = request.get_json(force=True, silent=True) or {}
    target = Path(data.get("path") or DOWNLOADS).expanduser()
    if not target.exists():
        target = DOWNLOADS
    try:
        if target.is_file():
            subprocess.run(["open", "-R", str(target)], check=False)
        else:
            subprocess.run(["open", str(target)], check=False)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _purge_stale_downloads(max_age_seconds: int = 3600) -> None:
    """Hosted disks are small and ephemeral; drop anything an hour old."""
    cutoff = time.time() - max_age_seconds
    try:
        for path in DOWNLOADS.rglob("*"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
    except OSError:
        pass


@app.post("/api/download")
def api_download():
    global _busy
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"ok": False, "error": "Paste a YouTube URL first."}), 400

    mode = data.get("mode") or "video"
    audio_only = mode == "audio"
    res = data.get("resolution")
    resolution = int(res) if res not in (None, "", "best", "auto") else None
    playlist = bool(data.get("playlist"))
    cookies_from_browser = data.get("cookies_from_browser") or None
    if cookies_from_browser:
        cookies_from_browser = str(cookies_from_browser).strip().lower() or None

    if not IS_LOCAL:
        _purge_stale_downloads()

    with _job_lock:
        if _busy:
            return jsonify({"ok": False, "error": "A download is already running."}), 409
        _busy = True

    events: queue.Queue = queue.Queue()

    def emit(obj: dict) -> None:
        events.put(obj)

    def worker() -> None:
        global _busy
        try:
            emit({"type": "started", "url": url})

            def on_progress(p: dict) -> None:
                emit({"type": "progress", **p})

            result = download_one(
                url,
                output_dir=DOWNLOADS,
                resolution=resolution,
                audio_only=audio_only,
                playlist=playlist,
                cookies_from_browser=cookies_from_browser,
                on_progress=on_progress,
                quiet=True,
            )
            emit({"type": "done", **result})
        except Exception as e:
            emit({"type": "done", "ok": False, "error": str(e), "title": None, "filepath": None})
        finally:
            with _job_lock:
                _busy = False
            events.put(None)  # stream end

    threading.Thread(target=worker, daemon=True).start()

    def stream():
        while True:
            item = events.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"
            # Keep Safari happy with occasional padding if needed
            time.sleep(0.01)

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def main() -> None:
    _writable(DOWNLOADS)
    if not has_ffmpeg():
        print(
            "WARNING: ffmpeg not found, so downloads cannot be made Premiere-ready\n"
            "         (no HD merging, no MP4 remux, no AAC-LC audio).\n"
            "         Restore bin/ffmpeg or run: brew install ffmpeg\n"
        )
    # A host sets $PORT; locally we keep loopback and open a browser tab.
    hosted = "PORT" in os.environ
    port = int(os.environ.get("PORT", 8765))
    host = os.environ.get("HOST", "0.0.0.0" if hosted else "127.0.0.1")
    print(f"Fetch by Fisola → http://{host}:{port}")
    if not hosted:
        threading.Timer(0.6, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
