# -*- coding: utf-8 -*-
"""Exa Search — check if mcporter + Exa MCP is available."""

import shutil
import subprocess

from autoresearch.utils.proc import raise_on_error

from .base import Channel


class ExaSearchChannel(Channel):
    name = "exa_search"
    description = "Web-wide semantic search"
    backends = ["Exa via mcporter"]
    tier = 0
    searchable = True

    def can_handle(self, url: str) -> bool:
        return False  # Search-only channel

    def search(self, query: str, limit: int = 5) -> list:
        """research rows from Exa web search via mcporter (parses text output)."""
        # Escape backslash + double-quote so the query can't break out of the DSL string.
        safe_q = query.replace("\\", "\\\\").replace('"', '\\"')
        out = subprocess.run(
            ["mcporter", "call",
             f'exa.web_search_exa(query: "{safe_q}", numResults: {int(limit)})'],
            capture_output=True, encoding="utf-8", errors="replace", timeout=40,
        )
        raise_on_error(out, "mcporter")
        rows, cur = [], {}
        for line in (out.stdout or "").splitlines():
            if line.startswith("Title:"):
                if cur.get("url"):
                    rows.append(cur)
                cur = {"source": "exa_search", "title": line[6:].strip(),
                       "url": "", "snippet": "", "date": ""}
            elif line.startswith("URL:"):
                cur["url"] = line[4:].strip()
            elif line.startswith("Published:"):
                cur["date"] = line[10:].strip()
        if cur.get("url"):
            rows.append(cur)
        return rows[:limit]

    def check(self, config=None, offline: bool = False):
        mcporter = shutil.which("mcporter")
        if not mcporter:
            return "off", (
                "mcporter + Exa MCP required. Install:\n"
                "  npm install -g mcporter\n"
                "  mcporter config add exa https://mcp.exa.ai/mcp"
            )
        try:
            r = subprocess.run(
                [mcporter, "config", "list"], capture_output=True,
                encoding="utf-8", errors="replace", timeout=5
            )
            if "exa" in r.stdout.lower():
                return "ok", "Web-wide semantic search available (free, no API Key required)"
            return "off", (
                "mcporter installed but Exa not configured. Run:\n"
                "  mcporter config add exa https://mcp.exa.ai/mcp"
            )
        except Exception:
            return "off", "mcporter connection error"

    def fix(self, config=None):
        """Add the Exa MCP entry via mcporter (the one fixable case).

        Installing mcporter itself needs npm and is left to the user."""
        mcporter = shutil.which("mcporter")
        if not mcporter:
            return False, "mcporter not installed — run: npm install -g mcporter"
        # Already configured? Then there's nothing to do.
        try:
            r = subprocess.run(
                [mcporter, "config", "list"], capture_output=True,
                encoding="utf-8", errors="replace", timeout=5,
            )
            if "exa" in (r.stdout or "").lower():
                return False, ""
        except Exception:
            pass  # fall through and try to add it anyway
        try:
            r = subprocess.run(
                [mcporter, "config", "add", "exa", "https://mcp.exa.ai/mcp"],
                capture_output=True, encoding="utf-8", errors="replace", timeout=30,
            )
        except Exception as exc:
            return False, f"mcporter config add failed: {exc}"
        if r.returncode != 0:
            detail = (r.stderr or r.stdout or "").strip()[:200]
            return False, f"mcporter config add failed: {detail}" if detail else "mcporter config add failed"
        return True, "configured Exa MCP (mcporter config add exa)"
