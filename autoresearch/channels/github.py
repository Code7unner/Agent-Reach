# -*- coding: utf-8 -*-
"""GitHub — check if gh CLI is available."""

import json
import shutil
import subprocess

from autoresearch.utils.proc import raise_on_error

from .base import Channel


class GitHubChannel(Channel):
    name = "github"
    description = "GitHub repositories and code"
    backends = ["gh CLI"]
    tier = 0
    searchable = True

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        return "github.com" in urlparse(url).netloc.lower()

    def search(self, query: str, limit: int = 5) -> list:
        """research rows from `gh search repos`."""
        # `--` ends option parsing so a query starting with `-` can't smuggle a flag.
        out = subprocess.run(
            ["gh", "search", "repos", "--limit", str(limit),
             "--json", "fullName,description,url,stargazersCount,updatedAt",
             "--", query],
            capture_output=True, encoding="utf-8", errors="replace", timeout=30,
        )
        raise_on_error(out, "gh")
        items = json.loads(out.stdout or "[]")
        return [{
            "source": "github",
            "title": it.get("fullName") or "",
            "url": it.get("url") or "",
            "snippet": (it.get("description") or "")[:280],
            "date": it.get("updatedAt") or "",
        } for it in items[:limit]]

    def check(self, config=None, offline: bool = False):
        gh = shutil.which("gh")
        if not gh:
            return "warn", "gh CLI not installed. Install: https://cli.github.com"
        if offline:
            # `gh auth status` reaches the network to verify the token; report install
            # status only when offline.
            return "ok", "gh CLI installed (--offline: auth not probed)"
        try:
            r = subprocess.run(
                [gh, "auth", "status"],
                capture_output=True, encoding="utf-8", errors="replace", timeout=5
            )
            if r.returncode == 0:
                return "ok", "Fully available (read, search, fork, issues, PRs, etc.)"
            return "warn", "gh CLI installed but not authenticated. Run gh auth login to unlock full functionality"
        except Exception:
            return "warn", "gh CLI status check failed; run gh auth status to view details"
