#!/usr/bin/env python3
"""
Fetch by Fisola — CLI. For the graphical UI, run:
    python3 ui_app.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core import (
    detect_js_runtime,
    download_one,
    export_cookies,
    has_ffmpeg,
    repair_folder,
    system_status,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="fetch",
        description="Fetch by Fisola — download YouTube videos/audio with yt-dlp.",
    )
    p.add_argument("urls", nargs="*", help="One or more YouTube URLs (prompted if omitted)")
    p.add_argument(
        "-o",
        "--output",
        default=str(Path.home() / "Downloads"),
        help="Output directory (default: ~/Downloads)",
    )
    p.add_argument(
        "-r",
        "--res",
        type=int,
        metavar="HEIGHT",
        choices=[144, 240, 360, 480, 720, 1080, 1440, 2160],
        help="Max video height",
    )
    p.add_argument("-a", "--audio", action="store_true", help="Audio only")
    p.add_argument("-p", "--playlist", action="store_true", help="Download full playlist")
    p.add_argument("-f", "--file", metavar="PATH", help="Text file with one URL per line")
    p.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        choices=["chrome", "chromium", "brave", "edge", "firefox", "safari", "opera"],
        help="Use browser cookies",
    )
    p.add_argument("--ui", action="store_true", help="Launch the graphical UI")
    p.add_argument(
        "--repair",
        nargs="?",
        const="",
        metavar="DIR",
        help="Re-check already-downloaded files and make them Premiere-ready "
        "(defaults to the output directory; only touches files this app named)",
    )
    p.add_argument(
        "--export-cookies",
        metavar="BROWSER",
        help="Write cookies.txt from a local browser for a hosted instance "
        "(e.g. chrome, firefox, or 'chrome:Profile 2' for a specific profile)",
    )
    p.add_argument(
        "--cookies-out", default="cookies.txt", metavar="PATH", help="Where --export-cookies writes"
    )
    return p.parse_args(argv)


def collect_urls(args: argparse.Namespace) -> list[str]:
    urls: list[str] = list(args.urls)
    if args.file:
        path = Path(args.file).expanduser()
        if not path.is_file():
            print(f"URL file not found: {path}")
            sys.exit(1)
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    if not urls:
        try:
            pasted = input("Paste YouTube URL(s), space-separated: ").strip()
        except EOFError:
            pasted = ""
        urls = pasted.split()
    seen: set[str] = set()
    unique: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.ui:
        from ui_app import main as ui_main

        ui_main()
        return 0

    if args.export_cookies:
        try:
            path = export_cookies(args.export_cookies, Path(args.cookies_out))
        except Exception as e:
            print(f"Could not export cookies: {e}")
            return 1
        print(f"Wrote {path} (mode 600).\n")
        print("Set it on your host as FETCH_COOKIES_TXT, contents and all:")
        print(f"  pbcopy < {path}    # then paste into the env var\n")
        print("These are a live session for whichever account that profile is")
        print("logged into. Use a throwaway account, and re-export when it expires.")
        return 0

    if args.repair is not None:
        target = Path(args.repair or args.output).expanduser()
        print(f"Checking {target} …")
        report = repair_folder(target)
        for name in report["fixed"]:
            print(f"  fixed  {name}")
        for name, note in report["notes"]:
            print(f"  note   {name}: {note}")
        print(f"\n{report['checked']} checked, {len(report['fixed'])} repaired.")
        return 0

    urls = collect_urls(args)
    if not urls:
        print("No URL provided. Exiting.")
        return 1

    if not has_ffmpeg():
        print(
            "WARNING: ffmpeg not found — falling back to single-file formats, and\n"
            "         downloads cannot be made Premiere-ready (no MP4 remux, no\n"
            "         AAC-LC audio). Restore bin/ffmpeg or: brew install ffmpeg\n"
        )
    if not detect_js_runtime():
        print("Note: no JS runtime (node/deno/bun) found.\n")

    output_dir = Path(args.output).expanduser().resolve()
    print(f"Output: {output_dir}")
    st = system_status()
    print(f"yt-dlp {st.get('yt_dlp')}")

    failures = 0
    for i, url in enumerate(urls, 1):
        print(f"\n[{i}/{len(urls)}] {url}")

        # Use download_one but also surface console progress via build_opts path
        def on_progress(p: dict) -> None:
            if p.get("status") == "downloading":
                pct = p.get("percent")
                pct_s = f"{pct:.1f}%" if isinstance(pct, (int, float)) else "..."
                speed = p.get("speed")
                speed_s = f"{speed/1024/1024:.2f}MiB/s" if speed else ""
                eta = p.get("eta")
                eta_s = f"{eta}s" if eta is not None else "--"
                print(f"\r  {pct_s:>7}  {speed_s:>10}  ETA {eta_s:>6}   ", end="", flush=True)
            elif p.get("status") == "finished":
                print("\r  Download complete — processing...                    ")

        result = download_one(
            url,
            output_dir=output_dir,
            resolution=args.res,
            audio_only=args.audio,
            playlist=args.playlist,
            cookies_from_browser=args.cookies_from_browser,
            on_progress=on_progress,
            quiet=False,
        )
        if result["ok"]:
            print(f"  Done: '{result['title']}'")
        else:
            print(f"  Error: {result['error']}")
            failures += 1

    print(f"\nSaved under: {output_dir}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
