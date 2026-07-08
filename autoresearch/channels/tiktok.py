# -*- coding: utf-8 -*-
"""TikTok — check if yt-dlp is available for reading TikTok videos.

yt-dlp reads individual TikTok videos (metadata + subtitles) and a user's video
list, but has no working keyword-search extractor — `tiktok:tag` (hashtag) is
marked BROKEN upstream and there is no `ttsearch:` key. So TikTok is a read-only
channel: it does NOT set `searchable` and never joins the `research` fan-out.
Agents read a shared TikTok URL directly via `yt-dlp --dump-json URL` (see
SKILL.md); this channel only reports readiness via `check()`.
"""

import shutil

from .base import Channel


class TikTokChannel(Channel):
    name = "tiktok"
    description = "TikTok short videos and subtitles"
    backends = ["yt-dlp"]
    tier = 0
    # yt-dlp has no working TikTok keyword search (tiktok:tag is BROKEN upstream),
    # so TikTok stays read-only and does not feed the `research` fan-out.
    searchable = False

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        # Covers www.tiktok.com plus the vm./vt./m. short-link hosts.
        return "tiktok.com" in urlparse(url).netloc.lower()

    def check(self, config=None, offline: bool = False):
        if not shutil.which("yt-dlp"):
            return "off", "yt-dlp not installed. Install: pip install yt-dlp"
        if offline:
            return "ok", "yt-dlp installed (--offline: not probed); read URLs via yt-dlp --dump-json"
        return "ok", "Can read TikTok video info and subtitles via yt-dlp (read-only; no keyword search)"
