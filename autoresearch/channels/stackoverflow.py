# -*- coding: utf-8 -*-
"""Stack Overflow — technical Q&A search via the Stack Exchange API (no auth).

https://api.stackexchange.com/2.3/search/advanced?q=...&site=stackoverflow
Anonymous quota is ~300 requests/day per IP. Responses are always gzip-encoded.
Search-only research connector."""

import gzip
import html
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from .base import Channel

_API = "https://api.stackexchange.com/2.3/search/advanced"
_UA = "autoresearch/1.0 (https://github.com/Code7unner/autoresearch)"


def _get_json(url: str, timeout: int = 10) -> dict:
    """Fetch *url* and return parsed JSON. The Stack Exchange API always gzips its
    responses, so decompress when needed. Raises on HTTP/network errors."""
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


class StackOverflowChannel(Channel):
    name = "stackoverflow"
    description = "Stack Overflow technical Q&A"
    backends = ["Stack Exchange API (public)"]
    tier = 0
    searchable = True

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        return "stackoverflow.com" in urlparse(url).netloc.lower()

    def check(self, config=None, offline: bool = False):
        if offline:
            return "ok", "Public API, zero-config (--offline: API not probed)"
        try:
            data = _get_json(
                f"{_API}?{urllib.parse.urlencode({'q': 'test', 'site': 'stackoverflow', 'pagesize': 1})}",
                timeout=8,
            )
            remaining = data.get("quota_remaining")
            note = f" (quota left: {remaining})" if remaining is not None else ""
            return "ok", f"Public API available (Q&A search, no key required){note}"
        except Exception as e:
            return "warn", f"Stack Exchange API connection failed: {e}"

    def search(self, query: str, limit: int = 5) -> list:
        """research rows from Stack Overflow question search."""
        q = urllib.parse.urlencode({
            "order": "desc",
            "sort": "relevance",
            "q": query,
            "site": "stackoverflow",
            "pagesize": int(limit),
        })
        data = _get_json(f"{_API}?{q}")
        rows = []
        for it in (data.get("items") or [])[:limit]:
            ts = it.get("creation_date") or 0
            date = (datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
                    if ts else "")
            tags = ", ".join(it.get("tags") or [])
            rows.append({
                "source": "stackoverflow",
                "title": html.unescape(it.get("title") or ""),
                "url": it.get("link") or "",
                "snippet": f"score {it.get('score', 0)} · "
                           f"{it.get('answer_count', 0)} answers · tags: {tags}",
                "date": date,
            })
        return rows
