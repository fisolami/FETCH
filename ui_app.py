#!/usr/bin/env python3
"""Launch the Fetch by Fisola UI in your browser."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from core import download_one, has_ffmpeg, system_status

ROOT = Path(__file__).resolve().parent
UI_DIR = ROOT / "ui"
DOWNLOADS = Path.home() / "Downloads"

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
    return jsonify(st)


@app.post("/api/reveal")
def api_reveal():
    """Open the downloads folder (or a specific file) in Finder on macOS."""
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
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
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
