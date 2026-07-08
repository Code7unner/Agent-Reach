# -*- coding: utf-8 -*-
"""
Channel base class — platform availability checking.

Each channel represents a platform (YouTube, Twitter, GitHub, etc.)
and provides:
  - can_handle(url) → does this URL belong to this platform?
  - check(config) → is the upstream tool installed and configured?

After installation, agents call upstream tools directly.
"""

import shutil
from abc import ABC, abstractmethod
from typing import List, Tuple


class Channel(ABC):
    """Base class for all channels."""

    name: str = ""                    # e.g. "youtube"
    description: str = ""             # e.g. "YouTube videos and subtitles"
    backends: List[str] = []          # e.g. ["yt-dlp"] — what upstream tool is used
    tier: int = 0                     # 0=zero-config, 1=needs free key, 2=needs setup
    searchable: bool = False          # does this channel feed the `research` fan-out?

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if this channel can handle this URL."""
        ...

    def search(self, query: str, limit: int = 5) -> List[dict]:
        """Query this channel and return rows for the `research` fan-out.

        Each row is a dict with ``source``/``title``/``url``/``snippet``/``date``.
        Channels that support query search override this and set ``searchable = True``;
        `research` resolves its adapters from these methods (single source of truth).
        Network/parse/CLI errors should propagate — the orchestrator turns them into
        per-channel partial failures. The default is not searchable.
        """
        raise NotImplementedError(f"{self.name or type(self).__name__} does not support search")

    def check(self, config=None, offline: bool = False) -> Tuple[str, str]:
        """
        Check if this channel's upstream tool is available.
        Returns (status, message) where status is 'ok'/'warn'/'off'/'error'.

        ``offline=True`` asks channels that perform a network liveness probe to skip
        it and report install/config status only. Channels with no network probe
        ignore the flag.
        """
        return "ok", f"{', '.join(self.backends) if self.backends else 'built-in'}"

    def fix(self, config=None) -> Tuple[bool, str]:
        """
        Attempt to auto-fix this channel's setup (driven by `doctor --fix`).

        Returns ``(changed, message)``. ``changed`` is True when this call mutated
        something (wrote a config, added an entry). A non-empty ``message`` with
        ``changed=False`` is an actionable manual hint (e.g. "install X first").
        ``("", False)`` means nothing to do / not auto-fixable. The default is a
        no-op; channels with a known automatic fix override this.
        """
        return False, ""
