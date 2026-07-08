# -*- coding: utf-8 -*-
"""Hacker News — public Algolia HN API channel for stories and comment threads.

Zero-config (tier 0): the agent calls the public Algolia HN API directly, e.g.

    curl -s "http://hn.algolia.com/api/v1/items/ID"                | autoresearch format hn
    curl -s "http://hn.algolia.com/api/v1/search?query=Q&tags=story" | autoresearch format hn

The ``format_hn_result`` helper trims the response to keep token usage low,
mirroring ``format_xhs_result`` for XiaoHongShu.
"""

import html
import json
import re
import urllib.request
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from .base import Channel

_BASE = "http://hn.algolia.com/api/v1"
_UA = "autoresearch/1.0"
_TIMEOUT = 10

# Truncation defaults for the comment tree (read mode) — named for testability.
HN_MAX_DEPTH = 3          # nesting depth of the comment tree
HN_MAX_TOP_LEVEL = 30     # top-level comments kept
HN_MAX_CHILDREN = 5       # children kept per comment node
HN_TEXT_LIMIT = 1000      # characters kept per comment


def _get_json(url: str) -> Any:
    """Fetch *url* and return parsed JSON. Raises on HTTP/network errors."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Strip HTML tags and unescape entities from Algolia comment text."""
    if not text:
        return ""
    return html.unescape(_TAG_RE.sub("", text)).strip()


# --------------------------------------------------------------------------- #
# Token-economy formatting (mirrors format_xhs_result)
# --------------------------------------------------------------------------- #

def format_hn_result(data: Any) -> Any:
    """Clean an Algolia HN API response, keeping only useful fields.

    Auto-detects the input shape:
      - ``{"hits": [...]}``    → search mode: flat list of stories.
      - item with children     → read mode: story head + truncated comment tree.
    """
    if isinstance(data, dict):
        if isinstance(data.get("hits"), list):
            return [_clean_hit(h) for h in data["hits"]]
        return _clean_story(data)
    return data


def _clean_hit(hit: dict) -> dict:
    """Extract useful fields from a single Algolia search hit (story)."""
    if not isinstance(hit, dict):
        return hit
    return {
        "objectID": hit.get("objectID", ""),
        "title": hit.get("title", ""),
        "url": hit.get("url", ""),
        "author": hit.get("author", ""),
        "points": hit.get("points", 0),
        "num_comments": hit.get("num_comments", 0),
        "created_at": hit.get("created_at", ""),
    }


def _clean_story(item: dict) -> dict:
    """Extract a story head + a depth/width-truncated comment tree."""
    if not isinstance(item, dict):
        return item

    result = {
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "author": item.get("author", ""),
        "points": item.get("points", 0),
        "created_at": item.get("created_at", ""),
    }
    text = _strip_html(item.get("text") or "")
    if text:
        result["text"] = text[:HN_TEXT_LIMIT]

    children = [c for c in (item.get("children") or []) if isinstance(c, dict)]
    shown = children[:HN_MAX_TOP_LEVEL]
    result["comments"] = [_clean_comment(c, 1) for c in shown]
    if len(children) > HN_MAX_TOP_LEVEL:
        result["_truncated"] = len(children) - HN_MAX_TOP_LEVEL
    return result


def _clean_comment(node: dict, depth: int) -> dict:
    """Clean a single comment node, recursing up to HN_MAX_DEPTH."""
    cleaned = {
        "author": node.get("author") or "",
        "text": _strip_html(node.get("text") or "")[:HN_TEXT_LIMIT],
        "created_at": node.get("created_at", ""),
    }

    children = [c for c in (node.get("children") or []) if isinstance(c, dict)]
    if not children:
        return cleaned

    if depth >= HN_MAX_DEPTH:
        cleaned["_truncated"] = len(children)
        return cleaned

    shown = children[:HN_MAX_CHILDREN]
    cleaned["children"] = [_clean_comment(c, depth + 1) for c in shown]
    if len(children) > HN_MAX_CHILDREN:
        cleaned["_truncated"] = len(children) - HN_MAX_CHILDREN
    return cleaned


# --------------------------------------------------------------------------- #
# Channel
# --------------------------------------------------------------------------- #

class HackerNewsChannel(Channel):
    name = "hackernews"
    description = "Hacker News stories and comment threads"
    backends = ["Algolia HN API (public)"]
    tier = 0
    searchable = True

    # ------------------------------------------------------------------ #
    # URL routing
    # ------------------------------------------------------------------ #

    def can_handle(self, url: str) -> bool:
        d = urlparse(url).netloc.lower()
        return "news.ycombinator.com" in d or "hn.algolia.com" in d

    def _extract_item_id(self, url: str) -> Optional[str]:
        """Extract the HN item id from a story URL or Algolia items URL."""
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "id" in qs and qs["id"]:
            return qs["id"][0]
        m = re.search(r"/items/(\d+)", parsed.path)
        if m:
            return m.group(1)
        return None

    # ------------------------------------------------------------------ #
    # Health check
    # ------------------------------------------------------------------ #

    def check(self, config=None, offline: bool = False):
        if offline:
            return "ok", "Public API, zero-config (--offline: API not probed)"
        try:
            _get_json(f"{_BASE}/search?query=test&tags=story")
            return "ok", "Public API available (story search, comment threads via Algolia)"
        except Exception as e:
            return "warn", f"Algolia HN API connection failed (proxy may be required): {e}"

    # ------------------------------------------------------------------ #
    # Data-fetching methods
    # ------------------------------------------------------------------ #

    def search(self, query: str, limit: int = 5) -> list:
        """research rows from HN story search (wraps `search_stories`)."""
        rows = []
        for hit in self.search_stories(query, limit)[:limit]:
            object_id = hit.get("objectID")
            url = hit.get("url") or (
                f"https://news.ycombinator.com/item?id={object_id}" if object_id else "")
            rows.append({
                "source": "hackernews",
                "title": hit.get("title") or "",
                "url": url,
                "snippet": "",
                "date": hit.get("created_at") or "",
            })
        return rows

    def search_stories(self, query: str, limit: int = 20) -> list:
        """Search stories.

        Returns a list of dicts with keys:
          objectID, title, url, author, points, num_comments, created_at
        """
        from urllib.parse import quote

        data = _get_json(f"{_BASE}/search?query={quote(query)}&tags=story")
        hits = data.get("hits", []) if isinstance(data, dict) else []
        return [_clean_hit(h) for h in hits[:limit]]

    def get_item(self, item_id: str) -> dict:
        """Get a story and its truncated comment tree.

        Returns a dict with keys:
          title, url, author, points, created_at, text (optional), comments
        """
        data = _get_json(f"{_BASE}/items/{item_id}")
        return _clean_story(data)
