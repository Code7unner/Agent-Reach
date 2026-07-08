# -*- coding: utf-8 -*-
"""Session/cookie liveness checks in doctor (hypothesis #4).

These tests pin the standardized status vocabulary for session channels:
  off  = tool / credentials absent
  warn = configured but the live probe says dead / unreachable (re-authenticate)
  ok   = configured and live
and the `offline=True` contract (skip network probes, report config status only).
"""

import subprocess

import pytest

from autoresearch.channels.linkedin import LinkedInChannel
from autoresearch.channels.twitter import TwitterChannel
from autoresearch.channels.xiaohongshu import XiaoHongShuChannel
from autoresearch.channels.weibo import WeiboChannel
from autoresearch.channels.douyin import DouyinChannel
from autoresearch.channels import xueqiu as xueqiu_mod
from autoresearch.channels.xueqiu import XueqiuChannel


def _fake_run(responses):
    """Build a subprocess.run stub keyed on a substring of the joined argv."""
    def run(cmd, **kwargs):
        joined = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        for needle, (stdout, rc) in responses.items():
            if needle in joined:
                class R:
                    pass
                R.stdout = stdout
                R.stderr = ""
                R.returncode = rc
                return R()
        raise AssertionError(f"unexpected subprocess call: {joined}")
    return run


class TestLinkedInLiveness:
    def test_off_when_mcporter_absent(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _c: None)
        status, msg = LinkedInChannel().check()
        assert status == "off"

    def test_ok_when_mcp_lists_tools(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda c: "/bin/mcporter" if c == "mcporter" else None)
        monkeypatch.setattr(subprocess, "run", _fake_run({
            "config list": ("linkedin  stdio", 0),
            "list linkedin": ("get_person_profile\nsearch_people", 0),
        }))
        status, msg = LinkedInChannel().check()
        assert status == "ok"

    def test_warn_when_configured_but_mcp_dead(self, monkeypatch):
        """Config entry exists but the MCP server isn't responding — a silently
        dead session. Must be warn (re-auth/restart), not ok."""
        monkeypatch.setattr("shutil.which", lambda c: "/bin/mcporter" if c == "mcporter" else None)
        monkeypatch.setattr(subprocess, "run", _fake_run({
            "config list": ("linkedin  stdio", 0),
            "list linkedin": ("Error: connection refused", 1),
        }))
        status, msg = LinkedInChannel().check()
        assert status == "warn"
        assert msg.strip()

    def test_off_when_entry_missing(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda c: "/bin/mcporter" if c == "mcporter" else None)
        monkeypatch.setattr(subprocess, "run", _fake_run({
            "config list": ("exa  https://mcp.exa.ai/mcp", 0),
        }))
        status, msg = LinkedInChannel().check()
        assert status == "off"

    def test_offline_skips_network_probe(self, monkeypatch):
        """offline=True must not invoke `mcporter list linkedin` (the network probe)."""
        monkeypatch.setattr("shutil.which", lambda c: "/bin/mcporter" if c == "mcporter" else None)

        def run(cmd, **kwargs):
            joined = " ".join(cmd)
            assert "list linkedin" not in joined, "offline must skip the liveness probe"
            class R:
                stdout = "linkedin  stdio"
                stderr = ""
                returncode = 0
            return R()

        monkeypatch.setattr(subprocess, "run", run)
        status, msg = LinkedInChannel().check(offline=True)
        assert status == "ok"
        assert "offline" in msg.lower()


class TestTwitterStatusVocabulary:
    def test_off_when_cli_not_installed(self, monkeypatch):
        """A missing CLI is 'not installed' (off), not a degraded session (warn)."""
        monkeypatch.setattr("shutil.which", lambda _c: None)
        status, msg = TwitterChannel().check()
        assert status == "off"

    def test_offline_skips_status_probe(self, monkeypatch):
        """offline=True must not invoke `twitter status` (the network probe)."""
        monkeypatch.setattr("shutil.which", lambda c: "/bin/twitter" if c == "twitter" else None)

        def run(cmd, **kwargs):
            raise AssertionError("offline must skip the twitter status probe")

        monkeypatch.setattr(subprocess, "run", run)
        status, msg = TwitterChannel().check(offline=True)
        assert status == "ok"
        assert "offline" in msg.lower()


class TestOfflineShortCircuit:
    """offline=True must never make the network liveness call for any session channel."""

    def test_xhs_offline_skips_status(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda c: "/bin/xhs" if c == "xhs" else None)

        def run(cmd, **kwargs):
            raise AssertionError("offline must skip the xhs status probe")

        monkeypatch.setattr(subprocess, "run", run)
        status, msg = XiaoHongShuChannel().check(offline=True)
        assert status == "ok"
        assert "offline" in msg.lower()

    def test_xhs_offline_off_when_not_installed(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _c: None)
        status, _ = XiaoHongShuChannel().check(offline=True)
        assert status == "off"

    def test_weibo_offline_skips_list_probe(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda c: "/bin/mcporter" if c == "mcporter" else None)

        def run(cmd, **kwargs):
            joined = " ".join(cmd)
            assert "list weibo" not in joined, "offline must skip the weibo liveness probe"
            class R:
                stdout = "weibo  --command mcp-server-weibo"
                stderr = ""
                returncode = 0
            return R()

        monkeypatch.setattr(subprocess, "run", run)
        status, msg = WeiboChannel().check(offline=True)
        assert status == "ok"
        assert "offline" in msg.lower()

    def test_douyin_offline_skips_list_probe(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda c: "/bin/mcporter" if c == "mcporter" else None)

        def run(cmd, **kwargs):
            joined = " ".join(cmd)
            assert "list douyin" not in joined, "offline must skip the douyin liveness probe"
            class R:
                stdout = "douyin  http://localhost:18070/mcp"
                stderr = ""
                returncode = 0
            return R()

        monkeypatch.setattr(subprocess, "run", run)
        status, msg = DouyinChannel().check(offline=True)
        assert status == "ok"
        assert "offline" in msg.lower()

    def test_xueqiu_offline_skips_http(self, monkeypatch):
        calls = []
        monkeypatch.setattr(xueqiu_mod, "_get_json", lambda *a, **k: calls.append(a) or {})
        status, msg = XueqiuChannel().check(offline=True)
        assert calls == [], "offline must not hit the Xueqiu API"
        assert status in {"ok", "warn", "off"}
        assert "offline" in msg.lower()
