# -*- coding: utf-8 -*-
"""YouTube — check if yt-dlp is available with JS runtime."""

import json
import shutil
import subprocess
from datetime import datetime, timezone

from autoresearch.utils.paths import get_ytdlp_config_path, render_ytdlp_fix_command
from autoresearch.utils.proc import raise_on_error
from autoresearch.utils.text import read_utf8_text

from .base import Channel


class YouTubeChannel(Channel):
    name = "youtube"
    description = "YouTube videos and subtitles"
    backends = ["yt-dlp"]
    tier = 0
    searchable = True

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "youtube.com" in d or "youtu.be" in d

    def search(self, query: str, limit: int = 5) -> list:
        """research rows from a yt-dlp `ytsearchN:` query (flat playlist, fast)."""
        target = f"ytsearch{int(limit)}:{query}"
        # `--` ends option parsing; the target itself starts with `ytsearch` so it
        # can't be read as a flag, but keep the separator for defense in depth.
        out = subprocess.run(
            ["yt-dlp", "--flat-playlist", "-J", "--", target],
            capture_output=True, encoding="utf-8", errors="replace", timeout=45,
        )
        raise_on_error(out, "yt-dlp")
        data = json.loads(out.stdout or "{}")
        rows = []
        for e in (data.get("entries") or [])[:limit]:
            vid = e.get("id")
            url = e.get("url") or (f"https://www.youtube.com/watch?v={vid}" if vid else "")
            desc = (e.get("description") or "").strip()
            snippet = desc[:280] if desc else (e.get("uploader") or e.get("channel") or "")
            ts = e.get("timestamp")
            date = (datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
                    if ts else "")
            rows.append({
                "source": "youtube",
                "title": e.get("title") or "",
                "url": url,
                "snippet": snippet,
                "date": date,
            })
        return rows

    def check(self, config=None, offline: bool = False):
        if not shutil.which("yt-dlp"):
            return "off", "yt-dlp not installed. Install: pip install yt-dlp"
        # Check JS runtime
        has_js = shutil.which("deno") or shutil.which("node")
        if not has_js:
            return "warn", (
                "yt-dlp installed but missing JS runtime (required by YouTube).\n"
                "  Install Node.js or deno, then run: autoresearch install"
            )
        # Check yt-dlp config for --js-runtimes
        # Deno works out of the box; Node.js requires explicit config
        has_deno = shutil.which("deno")
        if not has_deno:
            ytdlp_config = get_ytdlp_config_path()
            has_js_config = False
            if ytdlp_config.exists():
                has_js_config = "--js-runtimes" in read_utf8_text(ytdlp_config)
            if not has_js_config:
                return "warn", (
                    "yt-dlp installed but JS runtime not configured. Run:\n"
                    f"  {render_ytdlp_fix_command()}"
                )
        return "ok", "Can extract video info and subtitles"

    def fix(self, config=None):
        """Enable Node.js as yt-dlp's JS runtime by writing the config line.

        Only the "JS runtime not configured" case is auto-fixable here; installing
        yt-dlp or a JS runtime is left to the user (reported as a manual hint)."""
        if not shutil.which("yt-dlp"):
            return False, "yt-dlp not installed — run: pip install yt-dlp"
        if not (shutil.which("deno") or shutil.which("node")):
            return False, "no JS runtime — install Node.js or deno, then re-run"
        if shutil.which("deno"):
            return False, ""  # deno works out of the box, nothing to configure
        # Node.js present, no deno: ensure `--js-runtimes node` is in the config.
        cfg = get_ytdlp_config_path()
        existing = read_utf8_text(cfg) if cfg.exists() else ""
        if "--js-runtimes" in existing:
            return False, ""  # already configured
        cfg.parent.mkdir(parents=True, exist_ok=True)
        with open(cfg, "a", encoding="utf-8") as fh:
            if existing and not existing.endswith("\n"):
                fh.write("\n")
            fh.write("--js-runtimes node\n")
        return True, f"enabled Node.js JS runtime in {cfg}"
