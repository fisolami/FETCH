#!/usr/bin/env python3
"""Shared download logic for CLI and UI.

Prefers the bundled ``bin/yt-dlp`` binary (current releases) over the
system Python yt-dlp package, which is stuck on older versions under
Python 3.9 and breaks against modern YouTube.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import warnings
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

ProgressCb = Callable[[dict], None]

ROOT = Path(__file__).resolve().parent
_LOCAL_YTDLP = ROOT / "bin" / "yt-dlp"
_LOCAL_FFMPEG = ROOT / "bin" / "ffmpeg"

# YouTube clients that still tend to return usable HTTPS formats.
# Order matters: try VR/TV first (no PO token), then others as fallback.
_PLAYER_CLIENTS = "android_vr,tv,ios,mweb,web_safari"


@lru_cache(maxsize=1)
def resolve_ytdlp() -> str:
    """Prefer bundled binary, then PATH, then python -m yt_dlp."""
    if _LOCAL_YTDLP.is_file() and os.access(_LOCAL_YTDLP, os.X_OK):
        return str(_LOCAL_YTDLP)
    which = shutil.which("yt-dlp")
    if which:
        return which
    return "python3"


@lru_cache(maxsize=1)
def resolve_ffmpeg() -> Optional[str]:
    which = shutil.which("ffmpeg")
    if which:
        return which
    if _LOCAL_FFMPEG.is_file() and os.access(_LOCAL_FFMPEG, os.X_OK):
        return str(_LOCAL_FFMPEG)
    try:
        import imageio_ffmpeg

        path = imageio_ffmpeg.get_ffmpeg_exe()
        if path and Path(path).is_file():
            return path
    except Exception:
        pass
    return None


def has_ffmpeg() -> bool:
    return resolve_ffmpeg() is not None


def detect_js_runtime() -> Optional[str]:
    for name in ("node", "deno", "bun"):
        if shutil.which(name):
            return name
    return None


def ytdlp_version() -> str:
    cmd = _ytdlp_base_cmd() + ["--version"]
    try:
        out = subprocess.check_output(
            cmd,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=20,
        ).strip()
        return out.splitlines()[-1].strip() if out else "unknown"
    except Exception:
        # Bundled binary path is enough of a signal if --version hangs/fails
        exe = resolve_ytdlp()
        if exe.endswith("/bin/yt-dlp"):
            return "bundled"
        try:
            import yt_dlp

            return yt_dlp.version.__version__
        except Exception:
            return "unknown"


def _ytdlp_base_cmd() -> list[str]:
    exe = resolve_ytdlp()
    if exe.endswith("python3") or exe.endswith("python"):
        return [exe, "-m", "yt_dlp"]
    return [exe]


def build_format(resolution: Optional[int], audio_only: bool, ffmpeg_ok: bool) -> str:
    """Format selection.

    With an explicit resolution cap, prefer Premiere-friendly H.264 (AVC) + AAC
    in MP4. With no cap ("Best"), take the highest-resolution stream available —
    which on YouTube above 1080p means VP9/AV1 — and let the ``-S`` sort in
    :func:`download_one` prefer H.264 only among equal-resolution formats.
    """
    if audio_only:
        return "bestaudio[ext=m4a]/bestaudio/best"

    if not ffmpeg_ok:
        if resolution:
            return (
                f"best[height<={resolution}][vcodec^=avc1][ext=mp4]/"
                f"best[height<={resolution}][vcodec^=avc][ext=mp4]/"
                f"best[height<={resolution}][ext=mp4]/"
                f"best[height<={resolution}]/best"
            )
        return "best[ext=mp4]/best"

    if resolution:
        h = resolution
        return (
            f"bestvideo[height<={h}][vcodec^=avc1]+bestaudio[ext=m4a]/"
            f"bestvideo[height<={h}][vcodec^=avc]+bestaudio[ext=m4a]/"
            f"bestvideo[height<={h}][vcodec^=avc1]+bestaudio/"
            f"bestvideo[height<={h}][vcodec^=avc]+bestaudio/"
            f"best[height<={h}][vcodec^=avc1][ext=mp4]/"
            f"best[height<={h}]/bestvideo+bestaudio/best"
        )
    return "bestvideo*+bestaudio/bestvideo+bestaudio/best"


_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)%")
_SPEED_RE = re.compile(r"at\s+(\S+/s)")
_ETA_RE = re.compile(r"ETA\s+(\S+)")


def _parse_progress_line(line: str, on_progress: ProgressCb) -> None:
    if "[download]" not in line:
        return
    if "Destination:" in line or "Merging" in line:
        on_progress({"status": "downloading", "percent": None})
        return
    if "100%" in line or "has already been downloaded" in line:
        on_progress({"status": "finished"})
        return
    m = _PCT_RE.search(line)
    if not m:
        return
    pct = float(m.group(1))
    speed_m = _SPEED_RE.search(line)
    eta_m = _ETA_RE.search(line)
    payload: dict = {"status": "downloading", "percent": pct}
    if speed_m:
        # leave as string label; UI formats bytes when numeric
        payload["speed_label"] = speed_m.group(1)
    if eta_m:
        payload["eta_label"] = eta_m.group(1)
    on_progress(payload)


_INPUT_RE = re.compile(r"^Input #0,\s*([^,]+(?:,[^,]+)*?),\s*from", re.M)
_AUDIO_RE = re.compile(r"Audio:\s*(\w+)(?:\s*\(([^)]*)\))?")
_VIDEO_RE = re.compile(r"Video:\s*(\w+)")

# Codecs Premiere Pro's MP4 importer accepts. Audio must be plain AAC-LC:
# HE-AAC v1/v2 (SBR/parametric stereo, what TikTok ships at low bitrates)
# makes Premiere reject the entire file even when the video track is fine.
_PREMIERE_VIDEO = {"h264", "hevc"}


def _probe(path: Path) -> dict:
    """Container/codec summary via ``ffmpeg -i`` (imageio-ffmpeg ships no ffprobe)."""
    ffmpeg = resolve_ffmpeg()
    if not ffmpeg:
        return {}
    err = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True, text=True
    ).stderr
    info: dict = {"container": None, "video": None, "audio": None, "audio_profile": ""}
    m = _INPUT_RE.search(err)
    if m:
        info["container"] = m.group(1).strip()
    for line in err.splitlines():
        if "Stream #" not in line:
            continue
        a = _AUDIO_RE.search(line)
        if a and not info["audio"]:
            info["audio"] = a.group(1).lower()
            info["audio_profile"] = (a.group(2) or "").strip()
        v = _VIDEO_RE.search(line)
        if v and not info["video"]:
            info["video"] = v.group(1).lower()
    return info


def _top_level_boxes(path: Path, limit: int = 12) -> list[str]:
    """Names of the first top-level MP4 boxes, read by seeking (no full load)."""
    boxes: list[str] = []
    try:
        with path.open("rb") as fh:
            while len(boxes) < limit:
                head = fh.read(8)
                if len(head) < 8:
                    break
                size = int.from_bytes(head[:4], "big")
                boxes.append(head[4:8].decode("latin-1", "replace"))
                header = 8
                if size == 1:
                    ext = fh.read(8)
                    if len(ext) < 8:
                        break
                    size, header = int.from_bytes(ext, "big"), 16
                elif size == 0:
                    break
                if size < header:
                    break
                fh.seek(size - header, os.SEEK_CUR)
    except OSError:
        return []
    return boxes


def _looks_like_mpegts(path: Path) -> bool:
    """Sniff an MPEG-TS stream without ffmpeg: 0x47 sync bytes every 188."""
    try:
        with path.open("rb") as fh:
            head = fh.read(376)
    except OSError:
        return False
    if len(head) < 376:
        return False
    if head[4:8] == b"ftyp":
        return False
    return head[0] == 0x47 and head[188] == 0x47


def ensure_premiere_ready(path: Path) -> Optional[str]:
    """Rewrite a download in place so Premiere Pro will import it.

    Fixes the three things that make an otherwise-good file unimportable:
    a non-MP4 container, audio that is not AAC-LC (HE-AAC, Opus, …), and a
    ``moov`` atom sitting after ``mdat``. Video is always stream-copied, so
    this never re-encodes picture. Returns a note when something remains
    wrong that cannot be fixed losslessly, otherwise ``None``.
    """
    ffmpeg = resolve_ffmpeg()
    if not path.is_file():
        return None
    if not ffmpeg:
        # Never fail silently: without ffmpeg nothing below can run, and the
        # user ends up with an unimportable file and no idea why.
        if _looks_like_mpegts(path):
            return ("ffmpeg is missing, so this stayed MPEG-TS and Premiere Pro will "
                    "refuse it — install ffmpeg or restore bin/ffmpeg, then run "
                    "youtube_downloader.py --repair")
        return "ffmpeg is missing, so this download was not checked for Premiere Pro"

    info = _probe(path)
    if not info:
        return None

    audio_only = info.get("video") is None
    video_codec = info.get("video")
    audio_codec = info.get("audio")
    profile = (info.get("audio_profile") or "").upper()
    container = (info.get("container") or "").lower()

    if not audio_only and video_codec not in _PREMIERE_VIDEO:
        # VP9/AV1 would need a full re-encode; that is the user's call, not ours.
        return f"video is {video_codec}, which Premiere Pro cannot import"

    audio_ok = audio_codec is None or (audio_codec == "aac" and profile.startswith("LC"))
    container_ok = "mp4" in container or "mov" in container
    boxes = _top_level_boxes(path)
    faststart_ok = not ("moov" in boxes and "mdat" in boxes and boxes.index("mdat") < boxes.index("moov"))

    if audio_ok and container_ok and faststart_ok:
        return None

    tmp = path.with_name(f".{path.stem}.premiere{path.suffix}")
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", str(path)]
    cmd += ["-c:v", "copy"] if not audio_only else ["-vn"]
    cmd += ["-c:a", "copy"] if audio_ok else ["-c:a", "aac", "-profile:a", "aac_low", "-b:a", "192k"]
    cmd += ["-movflags", "+faststart", str(tmp)]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not tmp.is_file() or tmp.stat().st_size < 1024:
        tmp.unlink(missing_ok=True)
        return "could not normalise this file for Premiere Pro"

    tmp.replace(path)
    return None


_MEDIA_SUFFIXES = {".mp4", ".mkv", ".webm", ".m4a", ".mp3"}
# yt-dlp's output template ends every name with the source id in brackets.
_OUR_FILE_RE = re.compile(r"\[[A-Za-z0-9_-]{6,}\]\.[A-Za-z0-9]+$")


def repair_folder(directory: Path, *, only_ours: bool = True) -> dict:
    """Re-check downloads on disk and make them Premiere-ready.

    ``only_ours`` limits the sweep to files named by yt-dlp's template, so
    pointing this at a shared folder never rewrites unrelated videos.
    """
    directory = Path(directory).expanduser()
    report: dict = {"checked": 0, "fixed": [], "notes": []}
    if not directory.is_dir():
        return report
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _MEDIA_SUFFIXES:
            continue
        if only_ours and not _OUR_FILE_RE.search(path.name):
            continue
        report["checked"] += 1
        before = path.stat().st_size
        note = ensure_premiere_ready(path)
        if note:
            report["notes"].append((path.name, note))
        elif path.stat().st_size != before:
            report["fixed"].append(path.name)
    return report


def _finalize(result: dict, on_progress: Optional[ProgressCb] = None) -> dict:
    """Run every successful download through the Premiere-readiness pass."""
    if not result.get("ok") or not result.get("filepath"):
        return result
    path = Path(result["filepath"])
    if not path.is_file():
        return result
    if on_progress:
        on_progress({"status": "processing"})
    note = ensure_premiere_ready(path)
    if note:
        result["note"] = note
    if on_progress:
        on_progress({"status": "finished"})
    return result


_TIKTOK_HOST_RE = re.compile(r"https?://([\w-]+\.)*(tiktok\.com|douyin\.com)/", re.I)
_TIKTOK_DATA_RE = re.compile(
    r'id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', re.S
)
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)


def is_tiktok(url: str) -> bool:
    return bool(_TIKTOK_HOST_RE.match(url.strip()))


def _safe_name(text: str, limit: int = 150) -> str:
    """Mirror yt-dlp's output template: trimmed title, no path separators."""
    cleaned = re.sub(r"[\x00-\x1f/\\]+", " ", text or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned).rstrip(". ")
    return (cleaned[:limit].rstrip() or "tiktok video")


def _tiktok_direct(
    url: str,
    *,
    output_dir: Path,
    audio_only: bool = False,
    on_progress: Optional[ProgressCb] = None,
) -> dict:
    """Fallback extractor for TikTok.

    yt-dlp's TikTok extractor currently fails with "Unexpected response from
    webpage request" on both stable and nightly builds — TikTok changed its
    page structure and the parser has not caught up. The video data is still
    embedded in the page, so read it directly and fetch the stream ourselves.
    Delete this once upstream is fixed; ``download_one`` only calls it after
    yt-dlp has already failed.
    """
    import http.cookiejar
    import json
    import urllib.request

    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )
    headers = {"User-Agent": _BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"}

    req = urllib.request.Request(url, headers=headers)
    with opener.open(req, timeout=30) as resp:
        page = resp.read().decode("utf-8", "replace")

    match = _TIKTOK_DATA_RE.search(page)
    if not match:
        raise RuntimeError("TikTok returned a page without video data (captcha or private video).")

    scope = json.loads(match.group(1)).get("__DEFAULT_SCOPE__", {})
    item = (scope.get("webapp.video-detail") or {}).get("itemInfo", {}).get("itemStruct")
    if not item:
        raise RuntimeError("TikTok did not return this video (removed, private, or region-locked).")

    video = item.get("video") or {}
    title = item.get("desc") or item.get("id") or "tiktok video"
    vid = item.get("id") or video.get("id") or "tiktok"

    # Prefer H.264 for Premiere; among equal codecs take the highest bitrate.
    best: Optional[tuple] = None
    for entry in video.get("bitrateInfo") or []:
        play = entry.get("PlayAddr") or {}
        urls = play.get("UrlList") or []
        if not urls:
            continue
        codec = (entry.get("CodecType") or "").lower()
        rank = (0 if codec.startswith("h264") else -1, entry.get("Bitrate") or 0)
        if best is None or rank > best[0]:
            best = (rank, urls[-1], play.get("Width"), play.get("Height"))

    if best:
        stream_url, width, height = best[1], best[2], best[3]
    else:
        stream_url = video.get("playAddr") or video.get("downloadAddr")
        width, height = video.get("width"), video.get("height")
    if not stream_url:
        raise RuntimeError("TikTok page carried no playable stream URL.")

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{_safe_name(title)} [{vid}]"
    # In audio mode the video file is scratch and gets deleted, so keep it under
    # a hidden temp name — reusing the real .mp4 name would clobber (and then
    # delete) an existing video download of the same clip.
    target = output_dir / (f".{vid}.tmp.mp4" if audio_only else f"{stem}.mp4")
    part = target.with_suffix(".mp4.part")

    dl_headers = dict(headers, Referer="https://www.tiktok.com/")
    req = urllib.request.Request(stream_url, headers=dl_headers)
    with opener.open(req, timeout=60) as resp, part.open("wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(262144)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if on_progress:
                payload: dict = {"status": "downloading", "downloaded": done}
                if total:
                    payload["percent"] = done * 100 / total
                    payload["total"] = total
                on_progress(payload)

    if on_progress:
        on_progress({"status": "finished"})
    part.replace(target)

    if audio_only:
        ffmpeg = resolve_ffmpeg()
        if not ffmpeg:
            raise RuntimeError("Audio-only needs ffmpeg, which is not installed.")
        audio = output_dir / f"{stem}.m4a"
        try:
            for codec_args in (["-c:a", "copy"], ["-c:a", "aac", "-b:a", "192k"]):
                done_proc = subprocess.run(
                    [ffmpeg, "-y", "-loglevel", "error", "-i", str(target), "-vn",
                     *codec_args, str(audio)],
                    capture_output=True,
                    text=True,
                )
                if done_proc.returncode == 0:
                    return {"ok": True, "title": title, "filepath": str(audio),
                            "error": None, "width": None, "height": None}
            raise RuntimeError("Could not extract the audio track.")
        finally:
            target.unlink(missing_ok=True)

    return {"ok": True, "title": title, "filepath": str(target),
            "error": None, "width": width, "height": height}


def download_one(
    url: str,
    *,
    output_dir: Path,
    resolution: Optional[int] = None,
    audio_only: bool = False,
    playlist: bool = False,
    cookies_from_browser: Optional[str] = None,
    on_progress: Optional[ProgressCb] = None,
    quiet: bool = False,
) -> dict:
    """
    Download a single URL via the bundled/current yt-dlp.
    Returns {ok, title, filepath, error, width, height}.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_ok = has_ffmpeg()
    ffmpeg = resolve_ffmpeg()
    js = detect_js_runtime()

    outtmpl = str(output_dir / "%(title).200B [%(id)s].%(ext)s")
    if playlist:
        outtmpl = str(
            output_dir
            / "%(playlist_title|NA).100B"
            / "%(playlist_index)03d - %(title).150B [%(id)s].%(ext)s"
        )

    cmd = _ytdlp_base_cmd() + [
        "--no-playlist" if not playlist else "--yes-playlist",
        "-f",
        build_format(resolution, audio_only, ffmpeg_ok),
        "-S",
        "res,vcodec:h264,acodec:m4a,br",
        "-o",
        outtmpl,
        "--retries",
        "10",
        "--fragment-retries",
        "10",
        "--concurrent-fragments",
        "4",
        "--newline",
        "--progress",
        "--extractor-args",
        f"youtube:player_client={_PLAYER_CLIENTS}",
        "--print",
        "before_dl:META:%(title)s||%(width)s||%(height)s",
        "--print",
        "after_move:FILE:%(filepath)s",
        "--print",
        "after_video:FILE:%(filepath)s",
    ]

    if quiet:
        # Still show progress lines; suppress non-progress noise
        cmd += ["--no-warnings"]

    if ffmpeg_ok and not audio_only:
        # --merge-output-format only covers separate video+audio streams. HLS
        # formats arrive pre-muxed as MPEG-TS yet get an .mp4 name, which VLC
        # plays but Premiere Pro refuses to import. --remux-video rewrites any
        # non-MP4 container to real MP4 (stream copy, no re-encode).
        cmd += ["--merge-output-format", "mp4", "--remux-video", "mp4"]
    if ffmpeg:
        cmd += ["--ffmpeg-location", ffmpeg]
    if js:
        cmd += ["--js-runtimes", js]
    if cookies_from_browser:
        # android_vr ignores cookies — drop it when authenticated
        cmd = [
            c if not c.startswith("youtube:player_client=") else "youtube:player_client=tv,web,web_safari,mweb"
            for c in cmd
        ]
        cmd += ["--cookies-from-browser", cookies_from_browser]
    if audio_only and ffmpeg_ok:
        cmd += ["-x", "--audio-format", "m4a", "--audio-quality", "0"]

    cmd.append(url)

    title: Optional[str] = None
    filepath: Optional[str] = None
    width = height = None
    stderr_lines: list[str] = []

    started_at = time.time()

    try:
        env = os.environ.copy()
        # Avoid inheriting broken HTTP(S)_PROXY from tooling that 403s YouTube
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
            env.pop(k, None)

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip("\n")
            stderr_lines.append(line)
            if len(stderr_lines) > 60:
                stderr_lines.pop(0)

            if line.startswith("META:"):
                parts = line[5:].split("||")
                if parts:
                    title = parts[0] or title
                if len(parts) > 1 and parts[1].isdigit():
                    width = int(parts[1])
                if len(parts) > 2 and parts[2].isdigit():
                    height = int(parts[2])
                continue

            if line.startswith("FILE:"):
                # yt-dlp prints the literal "NA" when the template field is
                # unavailable; fall back to the mtime scan below in that case.
                candidate = line[5:].strip()
                if candidate and candidate != "NA":
                    filepath = candidate
                continue

            if on_progress:
                _parse_progress_line(line, on_progress)
            if "Merging formats" in line:
                if on_progress:
                    on_progress({"status": "finished"})

        code = proc.wait()
        if code != 0:
            if is_tiktok(url):
                try:
                    return _finalize(
                        _tiktok_direct(
                            url,
                            output_dir=output_dir,
                            audio_only=audio_only,
                            on_progress=on_progress,
                        ),
                        on_progress,
                    )
                except Exception as fallback_error:  # fall through to yt-dlp's message
                    stderr_lines.append(f"TikTok fallback failed: {fallback_error}")
            err = next(
                (l for l in reversed(stderr_lines) if "ERROR:" in l),
                "\n".join(stderr_lines[-8:]) or f"yt-dlp exited with code {code}",
            )
            hint = ""
            low = err.lower()
            if "page needs to be reloaded" in low or "sign in" in low or "not a bot" in low:
                hint = (
                    " YouTube is blocking this request. Turn on “Use browser cookies” "
                    "(Chrome recommended), make sure you’re logged into YouTube in that "
                    "browser, wait a minute, then retry."
                )
            elif "429" in low or "too many requests" in low:
                hint = " YouTube rate-limited you — wait 1–2 minutes and try again."
            return {
                "ok": False,
                "title": title,
                "filepath": None,
                "error": err + hint,
                "width": None,
                "height": None,
            }

        if on_progress:
            on_progress({"status": "finished"})

        # Fallback: newest media file written *during this run* if the print
        # template missed. The mtime guard matters because output_dir is a
        # shared folder (~/Downloads) full of unrelated files.
        if not filepath:
            media = {".mp4", ".mkv", ".webm", ".m4a", ".mp3"}
            newest: Optional[tuple[float, str]] = None
            for p in output_dir.rglob("*"):
                if not p.is_file() or p.suffix.lower() not in media:
                    continue
                mtime = p.stat().st_mtime
                if mtime < started_at:
                    continue
                if newest is None or mtime > newest[0]:
                    newest = (mtime, str(p))
            if newest:
                filepath = newest[1]

        return _finalize(
            {
                "ok": True,
                "title": title or (Path(filepath).stem if filepath else "video"),
                "filepath": filepath,
                "error": None,
                "width": width,
                "height": height,
            },
            on_progress,
        )
    except FileNotFoundError:
        return {
            "ok": False,
            "title": None,
            "filepath": None,
            "error": "yt-dlp not found. Place the binary at bin/yt-dlp or install yt-dlp.",
            "width": None,
            "height": None,
        }
    except Exception as e:
        return {
            "ok": False,
            "title": None,
            "filepath": None,
            "error": str(e),
            "width": None,
            "height": None,
        }


def system_status() -> dict:
    ffmpeg = resolve_ffmpeg()
    return {
        "ffmpeg": bool(ffmpeg),
        "ffmpeg_path": ffmpeg,
        "js_runtime": detect_js_runtime(),
        "yt_dlp": ytdlp_version(),
        "yt_dlp_bin": resolve_ytdlp(),
        "hd_ready": bool(ffmpeg),
    }
