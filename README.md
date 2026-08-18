# FETCH

**Fetch by Fisola** — a YouTube and TikTok downloader with a dark, hairline-drawn
UI, built so every file it saves imports straight into Premiere Pro.

## Why

Downloaders happily hand you files that play in VLC but that Premiere refuses to
import. Fetch checks every download before it calls itself done, and repairs the
three things that cause it:

| Problem | What Fetch does |
|---|---|
| MPEG-TS stream named `.mp4` (HLS sources) | Remuxes to real MP4 |
| HE-AAC / HE-AACv2 audio | Re-encodes to AAC-LC |
| `moov` atom after `mdat` | Rewrites with `+faststart` |

Video is always stream-copied, so the picture is never re-encoded. If a file
can't be fixed losslessly — VP9/AV1 above 1080p — it says so instead of handing
you something broken.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Fetch looks for `bin/ffmpeg` and `bin/yt-dlp` first, then your `PATH`. The
binaries are not in this repo. Restore them with either:

```bash
# ffmpeg — installed by requirements.txt, or system-wide:
brew install ffmpeg

# yt-dlp — current release binary:
mkdir -p bin && curl -L -o bin/yt-dlp \
  https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos
chmod +x bin/yt-dlp
```

Without ffmpeg the app still runs, but warns loudly: no HD merging, no MP4
remux, no AAC-LC audio.

## Use

```bash
python3 ui_app.py                      # UI at http://127.0.0.1:8765
python3 youtube_downloader.py URL      # CLI
python3 youtube_downloader.py --repair # re-check files already on disk
```

Saves to `~/Downloads`. Quality defaults to 1080p H.264, which is always
Premiere-native; **Best** goes higher as VP9/AV1, which Premiere cannot import.

Turn on **Use browser cookies** when YouTube throws bot checks or
"page needs to be reloaded".

### TikTok

yt-dlp's TikTok extractor is currently broken upstream. Fetch falls back to
reading the video data from the page directly, preferring H.264. It only runs
after yt-dlp fails, so it goes dormant once upstream ships a fix.

## Hosting

`wsgi.py` exposes the app for platforms that auto-detect Flask, and the
`Procfile` runs it under gunicorn. `PORT` in the environment switches the
server to `0.0.0.0` and skips opening a browser.

Be aware of what a hosted instance is and isn't: downloads are written to the
**server's** disk and nothing serves them back to your browser, so you get the
interface without a usable download. `/api/reveal` is macOS-only and does
nothing on Linux, and YouTube bot-checks cloud IPs aggressively while the
browser-cookies workaround is unavailable server-side. Fetch is a local tool;
run it on the machine you want the files on.

## Layout

| File | Role |
|---|---|
| `core.py` | Download, format selection, Premiere-readiness pass |
| `ui_app.py` | Flask server and JSON API |
| `youtube_downloader.py` | CLI |
| `ui/` | Front end (no build step, no dependencies) |
| `UI-DESIGN.md` | Visual style reference |
