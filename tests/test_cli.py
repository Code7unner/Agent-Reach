# -*- coding: utf-8 -*-
"""Tests for autoresearch CLI."""

import pytest
import requests
from unittest.mock import patch
import autoresearch.cli as cli
from autoresearch.cli import main


class TestCLI:
    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["autoresearch", "version"]):
                main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "autoresearch v" in captured.out

    def test_no_command_shows_help(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["autoresearch"]):
                main()
        assert exc_info.value.code == 0

    def test_doctor_runs(self, capsys):
        with patch("sys.argv", ["autoresearch", "doctor"]):
            main()
        captured = capsys.readouterr()
        assert "autoresearch" in captured.out
        assert "✅" in captured.out

    def test_parse_twitter_cookie_input_separate_values(self):
        auth_token, ct0 = cli._parse_twitter_cookie_input("token123 ct0abc")
        assert auth_token == "token123"
        assert ct0 == "ct0abc"

    def test_parse_twitter_cookie_input_cookie_header(self):
        auth_token, ct0 = cli._parse_twitter_cookie_input(
            "auth_token=token123; ct0=ct0abc; other=value"
        )
        assert auth_token == "token123"
        assert ct0 == "ct0abc"


class TestConfigureSecretInput:
    """`configure` should accept secrets via stdin/file, not just argv (no leak
    into shell history / `ps`)."""

    @staticmethod
    def _ns(**kw):
        import argparse
        defaults = dict(key="github-token", value=[], stdin=False, file=None)
        defaults.update(kw)
        return argparse.Namespace(**defaults)

    def test_resolve_value_from_stdin(self, monkeypatch):
        import io
        monkeypatch.setattr("sys.stdin", io.StringIO("ghp_fromstdin\n"))
        assert cli._resolve_config_value(self._ns(stdin=True)) == "ghp_fromstdin"

    def test_resolve_value_from_file(self, tmp_path):
        p = tmp_path / "secret.txt"
        p.write_text("ghp_fromfile\n", encoding="utf-8")
        assert cli._resolve_config_value(self._ns(file=str(p))) == "ghp_fromfile"

    def test_resolve_value_from_argv(self):
        assert cli._resolve_config_value(self._ns(value=["ghp", "argv"])) == "ghp argv"

    def test_resolve_value_rejects_multiple_sources(self, monkeypatch):
        import io
        monkeypatch.setattr("sys.stdin", io.StringIO("x"))
        with pytest.raises(SystemExit) as exc:
            cli._resolve_config_value(self._ns(stdin=True, value=["y"]))
        assert exc.value.code != 0

    def test_resolve_value_missing_file_errors(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            cli._resolve_config_value(self._ns(file=str(tmp_path / "nope.txt")))
        assert exc.value.code != 0

    def test_configure_github_token_via_stdin_stores_value(self, monkeypatch, capsys):
        import io

        class _FakeConfig:
            def __init__(self):
                self.data = {}

            def set(self, k, v):
                self.data[k] = v

            def get(self, k, default=None):
                return self.data.get(k, default)

        fake = _FakeConfig()
        monkeypatch.setattr("autoresearch.config.Config", lambda: fake)
        monkeypatch.setattr("sys.stdin", io.StringIO("ghp_secret\n"))
        with patch("sys.argv", ["autoresearch", "configure", "github-token", "--stdin"]):
            main()
        assert fake.data["github_token"] == "ghp_secret"

    def test_configure_warns_when_secret_passed_via_argv(self, monkeypatch, capsys):
        class _FakeConfig:
            def set(self, k, v):
                pass

            def get(self, k, default=None):
                return default

        monkeypatch.setattr("autoresearch.config.Config", lambda: _FakeConfig())
        with patch("sys.argv", ["autoresearch", "configure", "github-token", "ghp_x"]):
            main()
        assert "--stdin" in capsys.readouterr().err


class TestDoctorFix:
    def test_doctor_fix_runs_fixes_and_reports(self, monkeypatch, capsys):
        import autoresearch.doctor as doctor

        monkeypatch.setattr(doctor, "check_all", lambda config, offline=False: {})
        monkeypatch.setattr(doctor, "format_report", lambda results: "REPORT")
        called = {}

        def fake_run_fixes(config):
            called["yes"] = True
            return [{"channel": "youtube", "changed": True, "message": "enabled JS runtime"},
                    {"channel": "exa_search", "changed": False, "message": "mcporter not installed"}]

        monkeypatch.setattr(doctor, "run_fixes", fake_run_fixes)
        monkeypatch.setattr(cli, "_install_skill", lambda: None)

        with patch("sys.argv", ["autoresearch", "doctor", "--fix"]):
            main()

        out = capsys.readouterr().out
        assert called.get("yes") is True
        assert "youtube" in out and "enabled JS runtime" in out
        assert "exa_search" in out  # unchanged-but-actionable still surfaced

    def test_doctor_offline_forwards_offline_flag(self, monkeypatch):
        import autoresearch.doctor as doctor

        seen = {}

        def fake_check_all(config, offline=False):
            seen["offline"] = offline
            return {}

        monkeypatch.setattr(doctor, "check_all", fake_check_all)
        monkeypatch.setattr(doctor, "format_report", lambda results: "REPORT")
        monkeypatch.setattr(cli, "_install_skill", lambda: None)

        with patch("sys.argv", ["autoresearch", "doctor", "--offline"]):
            main()

        assert seen["offline"] is True

    def test_doctor_default_is_online(self, monkeypatch):
        import autoresearch.doctor as doctor

        seen = {}

        def fake_check_all(config, offline=False):
            seen["offline"] = offline
            return {}

        monkeypatch.setattr(doctor, "check_all", fake_check_all)
        monkeypatch.setattr(doctor, "format_report", lambda results: "REPORT")
        monkeypatch.setattr(cli, "_install_skill", lambda: None)

        with patch("sys.argv", ["autoresearch", "doctor"]):
            main()

        assert seen["offline"] is False

    def test_doctor_without_fix_does_not_run_fixes(self, monkeypatch):
        import autoresearch.doctor as doctor

        monkeypatch.setattr(doctor, "check_all", lambda config, offline=False: {})
        monkeypatch.setattr(doctor, "format_report", lambda results: "REPORT")
        monkeypatch.setattr(cli, "_install_skill", lambda: None)

        def boom(config):
            raise AssertionError("run_fixes must not be called without --fix")

        monkeypatch.setattr(doctor, "run_fixes", boom)
        with patch("sys.argv", ["autoresearch", "doctor"]):
            main()


class TestCheckUpdateRetry:
    def test_retry_timeout_classification(self):
        sleeps = []

        def fake_sleep(seconds):
            sleeps.append(seconds)

        with patch("requests.get", side_effect=requests.exceptions.Timeout("timed out")):
            resp, err, attempts = cli._github_get_with_retry(
                "https://api.github.com/test",
                timeout=1,
                retries=3,
                sleeper=fake_sleep,
            )

        assert resp is None
        assert err == "timeout"
        assert attempts == 3
        assert sleeps == [1, 2]

    def test_retry_dns_classification(self):
        error = requests.exceptions.ConnectionError("getaddrinfo failed for api.github.com")
        with patch("requests.get", side_effect=error):
            resp, err, attempts = cli._github_get_with_retry(
                "https://api.github.com/test",
                retries=1,
                sleeper=lambda _x: None,
            )
        assert resp is None
        assert err == "dns"
        assert attempts == 1

    def test_retry_rate_limit_then_success(self):
        sleeps = []

        class R:
            def __init__(self, code, payload=None, headers=None):
                self.status_code = code
                self._payload = payload or {}
                self.headers = headers or {}

            def json(self):
                return self._payload

        sequence = [
            R(429, headers={"Retry-After": "3"}),
            R(200, payload={"tag_name": "v1.0.2"}),
        ]

        with patch("requests.get", side_effect=sequence):
            resp, err, attempts = cli._github_get_with_retry(
                "https://api.github.com/test",
                retries=3,
                sleeper=lambda s: sleeps.append(s),
            )

        assert err is None
        assert resp is not None
        assert resp.status_code == 200
        assert attempts == 2
        assert sleeps == [3.0]

    def test_classify_rate_limit_from_403(self):
        class R:
            status_code = 403
            headers = {"X-RateLimit-Remaining": "0"}

            @staticmethod
            def json():
                return {"message": "API rate limit exceeded"}

        assert cli._classify_github_response_error(R()) == "rate_limit"

    def test_check_update_reports_classified_error(self, capsys):
        with patch("autoresearch.cli._github_get_with_retry", return_value=(None, "timeout", 3)):
            result = cli._cmd_check_update()

        captured = capsys.readouterr()
        assert result == "error"
        assert "Network timeout" in captured.out
        assert "retried 3 times" in captured.out


class TestFormatCommand:
    def _run_format(self, platform, stdin_text, capsys):
        import io
        import json as _json

        with patch("sys.stdin", io.StringIO(stdin_text)):
            with patch("sys.argv", ["autoresearch", "format", platform]):
                main()
        out = capsys.readouterr().out
        return _json.loads(out)

    def test_format_hn_item_returns_cleaned_story(self, capsys):
        import json as _json

        payload = _json.dumps(
            {
                "type": "story",
                "title": "HN Story",
                "url": "https://example.com",
                "author": "pg",
                "points": 123,
                "created_at": "2026-01-01T00:00:00Z",
                "children": [
                    {
                        "type": "comment",
                        "author": "u1",
                        "text": "<p>hi &amp; bye</p>",
                        "created_at": "2026-01-01T01:00:00Z",
                        "children": [],
                    }
                ],
            }
        )
        result = self._run_format("hn", payload, capsys)
        assert result["title"] == "HN Story"
        assert result["author"] == "pg"
        assert result["comments"][0]["text"] == "hi & bye"

    def test_format_hn_search_returns_flat_list(self, capsys):
        import json as _json

        payload = _json.dumps(
            {
                "hits": [
                    {
                        "objectID": "1",
                        "title": "T1",
                        "url": "https://e.com/1",
                        "author": "a",
                        "points": 9,
                        "num_comments": 3,
                        "created_at": "2026-01-01T00:00:00Z",
                    }
                ]
            }
        )
        result = self._run_format("hn", payload, capsys)
        assert isinstance(result, list)
        assert result[0]["title"] == "T1"
        assert result[0]["objectID"] == "1"
