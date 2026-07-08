# -*- coding: utf-8 -*-
"""Tests for autoresearch/utils/proc.py — subprocess helpers for search adapters."""

import subprocess

import pytest

from autoresearch.utils.proc import raise_on_error, run_with_retry


class _Out:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_raise_on_error_raises_with_message():
    with pytest.raises(RuntimeError) as exc:
        raise_on_error(_Out(1, stderr="not authenticated"), "gh")
    assert "gh exited 1" in str(exc.value)
    assert "not authenticated" in str(exc.value)


def test_raise_on_error_noop_on_success():
    raise_on_error(_Out(0, stdout="[]"), "gh")  # must not raise


def test_run_with_retry_recovers_after_transient_failure(monkeypatch):
    calls = {"n": 0}

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        return _Out(1, stderr="flaky") if calls["n"] == 1 else _Out(0, stdout="ok")

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = run_with_retry(["twitter"], "twitter", retries=2, _sleep=lambda s: None)
    assert out.stdout == "ok"
    assert calls["n"] == 2  # failed once, succeeded on retry


def test_run_with_retry_exhausts_and_reraises(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: _Out(1, stderr="boom"))
    with pytest.raises(RuntimeError):
        run_with_retry(["twitter"], "twitter", retries=2, _sleep=lambda s: None)


def test_run_with_retry_no_extra_calls_on_first_success(monkeypatch):
    calls = {"n": 0}

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        return _Out(0, stdout="ok")

    monkeypatch.setattr(subprocess, "run", fake_run)
    run_with_retry(["twitter"], "twitter", retries=3, _sleep=lambda s: None)
    assert calls["n"] == 1  # no wasted retries when the first call works


def test_run_with_retry_retries_on_timeout(monkeypatch):
    calls = {"n": 0}

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise subprocess.TimeoutExpired(cmd, 30)
        return _Out(0, stdout="ok")

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = run_with_retry(["twitter"], "twitter", retries=1, _sleep=lambda s: None)
    assert out.stdout == "ok"
    assert calls["n"] == 2
