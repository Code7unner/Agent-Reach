# -*- coding: utf-8 -*-
"""Tests for doctor module."""

import pytest

import autoresearch.doctor as doctor
from autoresearch.config import Config


class _StubChannel:
    def __init__(self, name, description, tier, status, message, backends=None,
                 fix_result=None):
        self.name = name
        self.description = description
        self.tier = tier
        self._status = status
        self._message = message
        self.backends = backends or []
        self._fix_result = fix_result or (False, "")
        self.fix_called = False

    def check(self, config=None, offline=False):
        self.check_offline = offline
        return self._status, self._message

    def fix(self, config=None):
        self.fix_called = True
        return self._fix_result


@pytest.fixture
def tmp_config(tmp_path):
    return Config(config_path=tmp_path / "config.yaml")


class TestDoctor:
    def test_check_all_collects_channel_results(self, tmp_config, monkeypatch):
        monkeypatch.setattr(
            doctor,
            "get_all_channels",
            lambda: [
                _StubChannel("web", "Web", 0, "ok", "Can scrape web pages", ["requests"]),
                _StubChannel("github", "GitHub", 0, "warn", "gh not installed", ["gh"]),
                _StubChannel("exa_search", "Web-wide semantic search", 1, "off", "mcporter not configured", ["Exa"]),
            ],
        )

        results = doctor.check_all(tmp_config)

        assert results == {
            "web": {
                "status": "ok",
                "name": "Web",
                "message": "Can scrape web pages",
                "tier": 0,
                "backends": ["requests"],
            },
            "github": {
                "status": "warn",
                "name": "GitHub",
                "message": "gh not installed",
                "tier": 0,
                "backends": ["gh"],
            },
            "exa_search": {
                "status": "off",
                "name": "Web-wide semantic search",
                "message": "mcporter not configured",
                "tier": 1,
                "backends": ["Exa"],
            },
        }

    def test_format_report(self):
        report = doctor.format_report(
            {
                "web": {
                    "status": "ok",
                    "name": "Web",
                    "message": "Can scrape web pages",
                    "tier": 0,
                    "backends": ["requests"],
                },
                "exa_search": {
                    "status": "off",
                    "name": "Web-wide semantic search",
                    "message": "mcporter not configured",
                    "tier": 1,
                    "backends": ["Exa"],
                },
                "xiaohongshu": {
                    "status": "warn",
                    "name": "XiaoHongShu",
                    "message": "MCP configured but health check timed out",
                    "tier": 2,
                    "backends": ["mcporter"],
                },
            }
        )

        # Strip Rich markup tags for assertion (PR #170 added [bold], [yellow] etc.)
        import re
        plain = re.sub(r"\[[^\]]*\]", "", report)
        assert "autoresearch" in plain
        assert "Ready to use:" in plain
        assert "1/3 channels available" in plain
        # Inactive optional channels should be summarized in one line
        assert "channels you can unlock" in plain

    def test_warn_channels_surfaced_separately_from_off(self):
        """A configured-but-dead (warn) session must be flagged for re-auth,
        not buried in the 'unlock more channels' summary (silent-expiry fix #4)."""
        report = doctor.format_report(
            {
                "web": {"status": "ok", "name": "Web", "message": "fine",
                        "tier": 0, "backends": []},
                "linkedin": {"status": "warn", "name": "LinkedIn",
                             "message": "session expired — run `linkedin login`",
                             "tier": 2, "backends": ["mcporter"]},
                "exa_search": {"status": "off", "name": "Exa",
                               "message": "mcporter not configured",
                               "tier": 1, "backends": ["Exa"]},
            }
        )
        import re
        plain = re.sub(r"\[[^\]]*\]", "", report)

        # warn channel surfaced in a dedicated needs-attention/re-auth block
        assert "Needs attention" in plain
        attention_idx = plain.index("Needs attention")
        unlock_idx = plain.index("channels you can unlock")
        # LinkedIn (warn) appears in the attention block, with its re-auth hint
        assert "LinkedIn" in plain[attention_idx:unlock_idx]
        assert "linkedin login" in plain
        # off channel (Exa) is the one offered to unlock, not LinkedIn
        unlock_line = plain[unlock_idx:]
        assert "Exa" in unlock_line
        assert "LinkedIn" not in unlock_line


class TestOfflineProbe:
    def test_check_all_forwards_offline_flag(self, tmp_config, monkeypatch):
        ch = _StubChannel("twitter", "Twitter/X", 1, "ok", "live")
        monkeypatch.setattr(doctor, "get_all_channels", lambda: [ch])

        doctor.check_all(tmp_config, offline=True)

        assert ch.check_offline is True

    def test_check_all_defaults_to_online(self, tmp_config, monkeypatch):
        ch = _StubChannel("twitter", "Twitter/X", 1, "ok", "live")
        monkeypatch.setattr(doctor, "get_all_channels", lambda: [ch])

        doctor.check_all(tmp_config)

        assert ch.check_offline is False


class TestRunFixes:
    def test_calls_fix_on_nonok_channels_only(self, tmp_config, monkeypatch):
        ok = _StubChannel("web", "Web", 0, "ok", "fine", fix_result=(True, "should not run"))
        broken = _StubChannel("youtube", "YouTube", 0, "warn", "needs config",
                              fix_result=(True, "enabled JS runtime"))
        monkeypatch.setattr(doctor, "get_all_channels", lambda: [ok, broken])

        outcomes = doctor.run_fixes(tmp_config)

        assert ok.fix_called is False
        assert broken.fix_called is True
        names = {o["channel"]: o for o in outcomes}
        assert names["youtube"]["changed"] is True
        assert "web" not in names

    def test_silent_noop_fix_is_not_reported(self, tmp_config, monkeypatch):
        broken = _StubChannel("github", "GitHub", 0, "off", "no token",
                              fix_result=(False, ""))  # nothing actionable
        monkeypatch.setattr(doctor, "get_all_channels", lambda: [broken])
        outcomes = doctor.run_fixes(tmp_config)
        assert outcomes == []

    def test_actionable_manual_hint_reported_even_if_unchanged(self, tmp_config, monkeypatch):
        broken = _StubChannel("youtube", "YouTube", 0, "off", "no yt-dlp",
                              fix_result=(False, "install yt-dlp first"))
        monkeypatch.setattr(doctor, "get_all_channels", lambda: [broken])
        outcomes = doctor.run_fixes(tmp_config)
        assert outcomes[0]["changed"] is False
        assert "yt-dlp" in outcomes[0]["message"]

    def test_tightens_open_config_permissions(self, tmp_config, monkeypatch):
        import os
        import stat
        import sys

        if sys.platform == "win32":
            pytest.skip("POSIX permission fix")
        monkeypatch.setattr(doctor, "get_all_channels", lambda: [])
        tmp_config.set("x", "y")  # writes the file
        path = tmp_config.config_path
        os.chmod(path, 0o644)  # group/other readable — too open

        outcomes = doctor.run_fixes(tmp_config)

        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600
        assert any(o["channel"] == "config" and o["changed"] for o in outcomes)
