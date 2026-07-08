# -*- coding: utf-8 -*-
"""Tiny HTTP GET helpers for public-API research channels (no auth).

Handles a User-Agent and transparent gzip (some APIs always gzip). Network/parse
errors propagate so the research orchestrator can turn them into partial failures.
"""

import gzip
import json
import urllib.request

_UA = "autoresearch/1.0 (https://github.com/Code7unner/autoresearch)"


def get_text(url: str, timeout: int = 10) -> str:
    """GET *url* and return the decoded body (gzip-decompressed when needed)."""
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    return raw.decode("utf-8")


def get_json(url: str, timeout: int = 10):
    """GET *url* and return parsed JSON."""
    return json.loads(get_text(url, timeout))
