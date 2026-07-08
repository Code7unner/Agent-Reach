# -*- coding: utf-8 -*-
"""Reddit — search and read via rdt-cli (public-clis/rdt-cli).

NOTE: Reddit requires authentication since 2024. All API requests
(including public subreddit reads) return HTTP 403 without a valid
session cookie. Run `rdt login` after installation to authenticate.
"""

import json
import shutil
import subprocess
from datetime import datetime, timezone

from autoresearch.utils.proc import raise_on_error

from .base import Channel

_CREDENTIAL_FILE = "~/.config/rdt-cli/credential.json"


class RedditChannel(Channel):
    name = "reddit"
    description = "Reddit posts and comments"
    backends = ["rdt-cli"]
    tier = 0
    searchable = True

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        d = urlparse(url).netloc.lower()
        return "reddit.com" in d or "redd.it" in d

    def search(self, query: str, limit: int = 5) -> list:
        """research rows from `rdt search` (compact JSON list of posts).

        Needs `rdt login`; doctor reports the channel inactive until authenticated,
        so a default research run skips it rather than erroring."""
        # `--` ends option parsing so a query starting with `-` can't smuggle a flag.
        out = subprocess.run(
            ["rdt", "search", "-n", str(limit), "--compact", "--json", "--", query],
            capture_output=True, encoding="utf-8", errors="replace", timeout=30,
        )
        raise_on_error(out, "rdt")
        payload = json.loads(out.stdout or "{}")
        posts = payload.get("data")
        if not isinstance(posts, list):
            posts = []
        rows = []
        for p in posts[:limit]:
            permalink = p.get("permalink") or ""
            url = (f"https://www.reddit.com{permalink}"
                   if permalink.startswith("/") else (p.get("url") or ""))
            ts = p.get("created_utc") or 0
            date = (datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
                    if ts else "")
            rows.append({
                "source": "reddit",
                "title": p.get("title") or "",
                "url": url,
                "snippet": (p.get("selftext") or "")[:280],
                "date": date,
            })
        return rows

    def check(self, config=None, offline: bool = False):
        rdt = shutil.which("rdt")
        if not rdt:
            return "off", (
                # NOTE: do NOT pin `>=0.4.2` here — PyPI's latest is 0.4.1, so the
                # pinned form is unsatisfiable and `pip install` fails outright. 0.4.1
                # works for search/status; point at the source for newer builds.
                "rdt-cli must be installed:\n"
                "  pip install rdt-cli\n"
                "or:\n"
                "  uv tool install rdt-cli\n"
                "For the newest build: https://github.com/public-clis/rdt-cli\n"
                "After installing, run `rdt login` to log in (log in to reddit.com in your browser first)"
            )

        try:
            r = subprocess.run(
                [rdt, "status", "--json"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            data = json.loads(r.stdout or "{}")
            authenticated = data.get("data", {}).get("authenticated", False)
            username = data.get("data", {}).get("username") or ""

            if authenticated:
                suffix = f" (logged in: {username})" if username else ""
                return "ok", (f"rdt-cli available{suffix} (search posts, read full text, view comments)")

            return "warn", (
                "rdt-cli installed but not logged in. Reddit has required authentication since 2024; "
                "all requests return 403 when not logged in.\n\n"
                "Method 1 (automatic): run `rdt login`\n"
                "  Log in to reddit.com in your browser first, then run this command to automatically extract the Cookie.\n\n"
                "Method 2 (manual, for when automatic extraction fails on Chrome/Edge 127+):\n"
                "  1. Install the Cookie-Editor extension from the Chrome Web Store:\n"
                "     https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm\n"
                "  2. Open reddit.com in your browser (make sure you are logged in)\n"
                "  3. Click the Cookie-Editor icon, find `reddit_session`, and copy its Value\n"
                f"  4. Write the following into {_CREDENTIAL_FILE}:\n"
                '     {"cookies": {"reddit_session": "<paste Value>"}, '
                '"source": "manual", "username": "<your username>", '
                '"modhash": null, "saved_at": 0, "last_verified_at": null}\n\n'
                "Verify: `rdt status --json` to confirm authenticated: true"
            )

        except (ValueError, OSError, subprocess.SubprocessError) as e:
            # ValueError covers json.JSONDecodeError; OSError covers FileNotFoundError;
            # SubprocessError covers TimeoutExpired. Surface the failure kind so a
            # transient post-install hiccup is debuggable rather than a generic warn.
            return "warn", (
                f"rdt-cli installed but status check failed ({type(e).__name__}); "
                "run `rdt status --json` to view details (if you just installed rdt, retry once)"
            )
