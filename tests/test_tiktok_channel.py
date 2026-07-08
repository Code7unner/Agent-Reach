# -*- coding: utf-8 -*-
"""Tests for the read-only TikTok channel (autoresearch/channels/tiktok.py)."""

import pytest

from autoresearch.channels import get_all_channels, get_channel
from autoresearch.channels.tiktok import TikTokChannel


@pytest.mark.parametrize("url", [
    "https://www.tiktok.com/@user/video/7300000000000000000",
    "https://tiktok.com/@user",
    "https://vm.tiktok.com/ZMabcdef/",
    "https://vt.tiktok.com/ZSabcdef/",
    "https://m.tiktok.com/v/123.html",
])
def test_can_handle_tiktok_urls(url):
    assert TikTokChannel().can_handle(url) is True


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=abc",
    "https://www.douyin.com/video/123",
    "https://example.com/tiktok",
])
def test_does_not_handle_other_urls(url):
    assert TikTokChannel().can_handle(url) is False


def test_check_ok_when_ytdlp_installed(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda c: "/usr/bin/yt-dlp" if c == "yt-dlp" else None)
    status, message = TikTokChannel().check()
    assert status == "ok"
    assert "yt-dlp" in message


def test_check_off_when_ytdlp_missing(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda c: None)
    status, message = TikTokChannel().check()
    assert status == "off"
    assert "yt-dlp not installed" in message


def test_check_offline_reports_install_only(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda c: "/usr/bin/yt-dlp" if c == "yt-dlp" else None)
    status, message = TikTokChannel().check(offline=True)
    assert status == "ok"
    assert "offline" in message.lower()


def test_registered_and_read_only():
    ch = get_channel("tiktok")
    assert ch is not None
    assert ch in get_all_channels()
    # yt-dlp can't keyword-search TikTok, so it must not join the research fan-out.
    assert getattr(ch, "searchable", False) is False
