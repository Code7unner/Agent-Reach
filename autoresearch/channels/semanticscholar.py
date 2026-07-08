# -*- coding: utf-8 -*-
"""Semantic Scholar — academic paper search via the public Graph API (no auth).

Covers all fields (broader than arXiv). The keyless endpoint is heavily rate-limited
(shared per-IP pool — 429s are common); we retry once on 429, and otherwise let it
surface as a partial failure / inactive channel rather than crash. A free API key
(https://www.semanticscholar.org/product/api) lifts the limit — wiring one in via
config is a sensible follow-up if this channel proves too throttled."""

import time
import urllib.error
import urllib.parse

from autoresearch.utils.http import get_json

from .base import Channel

_API = "https://api.semanticscholar.org/graph/v1/paper/search"
_FIELDS = "title,url,abstract,year,authors"


def _get_json_retrying(url: str, timeout: int = 10):
    """GET JSON, retrying once after a short backoff on HTTP 429 (rate limit)."""
    try:
        return get_json(url, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code != 429:
            raise
        time.sleep(1.0)
        return get_json(url, timeout=timeout)


class SemanticScholarChannel(Channel):
    name = "semanticscholar"
    description = "Semantic Scholar academic papers"
    backends = ["Semantic Scholar API (public)"]
    tier = 0
    searchable = True

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        return "semanticscholar.org" in urlparse(url).netloc.lower()

    def check(self, config=None, offline: bool = False):
        if offline:
            return "ok", "Public API, zero-config (--offline: API not probed)"
        try:
            _get_json_retrying(f"{_API}?{urllib.parse.urlencode({'query': 'test', 'limit': 1, 'fields': 'title'})}", timeout=8)
            return "ok", "Public API available (paper search, no key required; rate-limited)"
        except Exception as e:
            return "warn", f"Semantic Scholar API connection failed (rate limit?): {e}"

    def search(self, query: str, limit: int = 5) -> list:
        """research rows from Semantic Scholar paper search."""
        q = urllib.parse.urlencode({
            "query": query, "limit": int(limit), "fields": _FIELDS,
        })
        data = _get_json_retrying(f"{_API}?{q}")
        rows = []
        for p in (data.get("data") or [])[:limit]:
            abstract = (p.get("abstract") or "").strip()
            if not abstract:
                names = ", ".join(a.get("name", "") for a in (p.get("authors") or []))
                abstract = names
            year = p.get("year")
            rows.append({
                "source": "semanticscholar",
                "title": p.get("title") or "",
                "url": p.get("url") or "",
                "snippet": abstract[:280],
                "date": str(year) if year else "",
            })
        return rows
