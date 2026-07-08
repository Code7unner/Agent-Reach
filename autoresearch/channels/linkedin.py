# -*- coding: utf-8 -*-
"""LinkedIn — check if linkedin-scraper-mcp is available."""

import shutil
import subprocess
from .base import Channel


class LinkedInChannel(Channel):
    name = "linkedin"
    description = "LinkedIn professional network"
    backends = ["linkedin-scraper-mcp", "Jina Reader"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        return "linkedin.com" in urlparse(url).netloc.lower()

    def check(self, config=None, offline: bool = False):
        mcporter = shutil.which("mcporter")
        if not mcporter:
            return "off", (
                "Basic content can be read via Jina Reader. Full functionality requires:\n"
                "  pip install linkedin-scraper-mcp\n"
                "  mcporter config add linkedin http://localhost:3000/mcp\n"
                "  See https://github.com/stickerdaniel/linkedin-mcp-server"
            )
        # A configured entry alone doesn't mean the session is alive — the LinkedIn
        # cookie expires silently. Confirm the entry, then probe the live MCP.
        try:
            r = subprocess.run(
                [mcporter, "config", "list"], capture_output=True,
                encoding="utf-8", errors="replace", timeout=5
            )
            if "linkedin" not in r.stdout.lower():
                return "off", (
                    "mcporter installed but LinkedIn MCP not configured. Run:\n"
                    "  pip install linkedin-scraper-mcp\n"
                    "  mcporter config add linkedin http://localhost:3000/mcp"
                )
        except Exception:
            return "off", "mcporter connection error"

        if offline:
            return "ok", "LinkedIn MCP configured (--offline: session not probed)"

        # Liveness probe: list the live MCP's tools. If the server isn't running
        # or the session is dead, the tools won't load.
        try:
            r = subprocess.run(
                [mcporter, "list", "linkedin"], capture_output=True,
                encoding="utf-8", errors="replace", timeout=15
            )
            if r.returncode == 0 and "get_person_profile" in r.stdout:
                return "ok", "Fully available (profile, company, job search)"
            return "warn", (
                "LinkedIn MCP configured but not responding — the session may have "
                "expired or the server isn't running. Re-authenticate / restart:\n"
                "  mcporter list linkedin   # for details"
            )
        except Exception:
            return "warn", (
                "LinkedIn MCP configured but the liveness probe failed; "
                "re-authenticate / restart the linkedin-scraper-mcp server"
            )
