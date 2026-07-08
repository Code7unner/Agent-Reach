# -*- coding: utf-8 -*-
"""arXiv — scientific paper search via the public arXiv API (no auth).

Atom feed: https://export.arxiv.org/api/query?search_query=...&max_results=N
arXiv asks clients to keep request rate modest (~1 request / 3s); for interactive
research fan-out that's fine. Search-only research connector."""

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .base import Channel

_API = "https://export.arxiv.org/api/query"
_UA = "autoresearch/1.0 (https://github.com/Code7unner/autoresearch)"
_NS = {"a": "http://www.w3.org/2005/Atom"}


def _get_text(url: str, timeout: int = 10) -> str:
    """Fetch *url* and return the response body as text. Raises on HTTP/network errors."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


class ArxivChannel(Channel):
    name = "arxiv"
    description = "arXiv scientific papers"
    backends = ["arXiv API (public)"]
    tier = 0
    searchable = True

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        return "arxiv.org" in urlparse(url).netloc.lower()

    def check(self, config=None, offline: bool = False):
        if offline:
            return "ok", "Public API, zero-config (--offline: API not probed)"
        try:
            _get_text(f"{_API}?search_query=all:test&max_results=0", timeout=8)
            return "ok", "Public API available (paper search, no key required)"
        except Exception as e:
            return "warn", f"arXiv API connection failed: {e}"

    def search(self, query: str, limit: int = 5) -> list:
        """research rows from arXiv paper search (Atom feed)."""
        q = urllib.parse.urlencode({
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": int(limit),
        })
        root = ET.fromstring(_get_text(f"{_API}?{q}"))
        rows = []
        for entry in root.findall("a:entry", _NS)[:limit]:
            def _text(tag):
                el = entry.find(f"a:{tag}", _NS)
                return (el.text or "").strip() if el is not None else ""
            published = _text("published")
            rows.append({
                "source": "arxiv",
                "title": " ".join(_text("title").split()),
                "url": _text("id"),
                "snippet": " ".join(_text("summary").split())[:280],
                "date": published[:10],  # ISO date prefix (YYYY-MM-DD)
            })
        return rows
