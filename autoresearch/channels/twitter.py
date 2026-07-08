# -*- coding: utf-8 -*-
"""Twitter/X - check if Xquik, twitter-cli, or bird CLI is available."""

import json
import shutil
import subprocess

import requests

from autoresearch.config import Config
from autoresearch.utils.proc import run_with_retry

from .base import Channel

_XQUIK_BASE_URL = "https://xquik.com"


class TwitterChannel(Channel):
    name = "twitter"
    description = "Twitter/X posts"
    backends = ["Xquik API", "twitter-cli", "bird CLI (legacy)"]
    tier = 1
    searchable = True

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "x.com" in d or "twitter.com" in d

    def search(self, query: str, limit: int = 5) -> list:
        """Research rows from recent tweets via Xquik or twitter-cli."""
        xquik = self._xquik_settings()
        if xquik:
            api_key, base_url = xquik
            return self._search_xquik(query, limit, api_key, base_url)
        return self._search_twitter_cli(query, limit)

    def check(self, config=None, offline: bool = False):
        if config is not None and config.get("xquik_api_key"):
            return "ok", "Xquik API configured for tweet search"

        # Prefer twitter-cli, fallback to bird/birdx
        twitter = shutil.which("twitter")
        bird = shutil.which("bird") or shutil.which("birdx")

        if not twitter and not bird:
            return "off", (
                "Twitter CLI not installed. Install with:\n"
                "  pipx install twitter-cli\n"
                "or:\n"
                "  uv tool install twitter-cli"
            )

        if offline:
            cli = "twitter-cli" if twitter else "bird CLI"
            return "ok", f"{cli} installed (--offline: session not probed)"

        if twitter:
            return self._check_twitter_cli(twitter)
        return self._check_bird(bird)

    def _xquik_settings(self):
        config = Config()
        api_key = config.get("xquik_api_key")
        if not api_key:
            return None
        return api_key, config.get("xquik_base_url", _XQUIK_BASE_URL).rstrip("/")

    def _search_xquik(self, query: str, limit: int, api_key: str, base_url: str) -> list:
        bounded_limit = max(1, min(int(limit), 200))
        response = requests.get(
            f"{base_url}/api/v1/x/tweets/search",
            headers={"x-api-key": api_key},
            params={"q": query, "queryType": "Latest", "limit": str(bounded_limit)},
            timeout=30,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Xquik API returned {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("Xquik API returned invalid JSON") from exc
        return [self._xquik_row(tweet) for tweet in self._xquik_tweets(payload)[:bounded_limit]]

    def _search_twitter_cli(self, query: str, limit: int = 5) -> list:
        """Research rows from recent tweets via twitter-cli. Needs cookies configured.

        twitter-cli is the flakiest search backend (cold session / transient network),
        so retry a couple of times before surfacing a per-channel error to the fan-out.
        """
        # `--` ends option parsing so a query starting with `-` can't smuggle a flag.
        out = run_with_retry(
            ["twitter", "-c", "search", "-n", str(limit), "--", query],
            "twitter", retries=2,
            capture_output=True, encoding="utf-8", errors="replace", timeout=30,
        )
        items = json.loads(out.stdout or "[]")
        rows = []
        for it in items[:limit]:
            author = (it.get("author") or "").lstrip("@")
            text = it.get("text") or ""
            rows.append({
                "source": "twitter",
                "title": f"{it.get('author', '')}: {text[:60]}".strip(),
                "url": f"https://x.com/{author}/status/{it.get('id')}" if author else "",
                "snippet": text[:280],
                "date": it.get("time") or "",
            })
        return rows

    def _xquik_tweets(self, payload) -> list:
        tweets = payload.get("tweets")
        if isinstance(tweets, list):
            return [item for item in tweets if isinstance(item, dict)]
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("tweets"), list):
            return [item for item in data["tweets"] if isinstance(item, dict)]
        return []

    def _xquik_row(self, tweet) -> dict[str, str]:
        raw_author = tweet.get("author")
        author = raw_author if isinstance(raw_author, dict) else {}
        username = self._first_text(author.get("username"), author.get("screen_name"),
                                    tweet.get("username"))
        text = self._first_text(tweet.get("text"), tweet.get("full_text"))
        tweet_id = self._first_text(tweet.get("id"), tweet.get("id_str"), tweet.get("tweet_id"))
        title_prefix = f"@{username}: " if username else ""
        return {
            "source": "twitter",
            "title": f"{title_prefix}{text[:60]}".strip(),
            "url": self._first_text(tweet.get("url")) or (
                f"https://x.com/{username}/status/{tweet_id}" if username and tweet_id else ""
            ),
            "snippet": text[:280],
            "date": self._first_text(tweet.get("created"), tweet.get("created_at"),
                                     tweet.get("createdAt")),
        }

    def _first_text(self, *values: object) -> str:
        for value in values:
            if isinstance(value, str) and value:
                return value
            if isinstance(value, (int, float)):
                return str(value)
        return ""

    def _check_twitter_cli(self, binary: str):
        try:
            r = subprocess.run(
                [binary, "status"], capture_output=True,
                encoding="utf-8", errors="replace", timeout=10
            )
            output = (r.stdout or "") + (r.stderr or "")
            if r.returncode == 0 and "ok: true" in output:
                return "ok", (
                    "twitter-cli fully available (search, read posts, timeline, long-form/Article, "
                    "user lookup, Thread)"
                )
            if "not_authenticated" in output:
                return "warn", (
                    "twitter-cli installed but not authenticated. Set up with:\n"
                    "  export TWITTER_AUTH_TOKEN=\"xxx\"\n"
                    "  export TWITTER_CT0=\"yyy\"\n"
                    "or make sure you are logged into x.com in your browser"
                )
            return "warn", (
                "twitter-cli installed but authentication check failed. Run:\n"
                "  twitter -v status for details"
            )
        except Exception:
            return "warn", "twitter-cli installed but connection failed"

    def _check_bird(self, binary: str):
        try:
            r = subprocess.run(
                [binary, "check"], capture_output=True,
                encoding="utf-8", errors="replace", timeout=10
            )
            output = (r.stdout or "") + (r.stderr or "")
            if r.returncode == 0:
                return "ok", "bird CLI available (read, search posts, including long-form/X Article)"
            if "Missing credentials" in output or "missing" in output.lower():
                return "warn", (
                    "bird CLI installed but authentication not configured. Set environment variables:\n"
                    "  export AUTH_TOKEN=\"xxx\"\n"
                    "  export CT0=\"yyy\""
                )
            return "warn", (
                "bird CLI installed but authentication check failed."
            )
        except Exception:
            return "warn", "bird CLI installed but connection failed"
