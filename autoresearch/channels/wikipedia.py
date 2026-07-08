# -*- coding: utf-8 -*-
"""Wikipedia — article search via the public MediaWiki API (no auth)."""

import html
import re
import urllib.parse

from autoresearch.utils.http import get_json

from .base import Channel

_API = "https://en.wikipedia.org/w/api.php"
_TAG_RE = re.compile(r"<[^>]+>")


class WikipediaChannel(Channel):
    name = "wikipedia"
    description = "Wikipedia articles"
    backends = ["MediaWiki API (public)"]
    tier = 0
    searchable = True

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        return "wikipedia.org" in urlparse(url).netloc.lower()

    def check(self, config=None, offline: bool = False):
        if offline:
            return "ok", "Public API, zero-config (--offline: API not probed)"
        try:
            get_json(f"{_API}?{urllib.parse.urlencode({'action': 'query', 'list': 'search', 'srsearch': 'test', 'srlimit': 1, 'format': 'json'})}", timeout=8)
            return "ok", "Public API available (article search, no key required)"
        except Exception as e:
            return "warn", f"MediaWiki API connection failed: {e}"

    def search(self, query: str, limit: int = 5) -> list:
        """research rows from a MediaWiki full-text search."""
        q = urllib.parse.urlencode({
            "action": "query", "list": "search", "srsearch": query,
            "srlimit": int(limit), "format": "json",
        })
        data = get_json(f"{_API}?{q}")
        rows = []
        for hit in (data.get("query", {}).get("search") or [])[:limit]:
            pageid = hit.get("pageid")
            snippet = html.unescape(_TAG_RE.sub("", hit.get("snippet") or "")).strip()
            ts = hit.get("timestamp") or ""
            rows.append({
                "source": "wikipedia",
                "title": hit.get("title") or "",
                "url": f"https://en.wikipedia.org/?curid={pageid}" if pageid else "",
                "snippet": snippet[:280],
                "date": ts[:10],  # ISO date prefix
            })
        return rows
