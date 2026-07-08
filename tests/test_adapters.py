# -*- coding: utf-8 -*-
"""Tests for research adapter resolution (adapters.py).

The per-tool search functions now live on the channels themselves
(`Channel.search`); adapters.py only resolves WHICH channels run. The channel
search/normalization logic is tested in test_channels.py::TestChannelSearch.
"""

import autoresearch.adapters as A


class _FakeChannel:
    def __init__(self, name, searchable):
        self.name = name
        self.searchable = searchable

    def search(self, query, limit=5):
        return [{"source": self.name, "title": "x", "url": f"http://{self.name}/1"}]


def _patch(monkeypatch, channels, statuses):
    monkeypatch.setattr("autoresearch.channels.get_all_channels", lambda: channels)
    monkeypatch.setattr(
        "autoresearch.doctor.check_all",
        lambda config, offline=False: {name: {"status": st} for name, st in statuses.items()},
    )


def test_resolve_builds_adapters_from_searchable_active_channels(monkeypatch):
    channels = [_FakeChannel("github", True), _FakeChannel("reddit", False),
                _FakeChannel("exa_search", True)]
    _patch(monkeypatch, channels, {"github": "ok", "exa_search": "off", "reddit": "ok"})

    adapters, skipped, unknown = A.resolve_research()  # default = active searchable

    assert set(adapters) == {"github"}          # exa_search is searchable but inactive
    assert skipped == ["exa_search"]
    assert unknown == []
    # The adapter is the channel's own bound search method.
    assert adapters["github"]("q", 1)[0]["source"] == "github"


def test_resolve_explicit_channels_run_even_if_inactive(monkeypatch):
    channels = [_FakeChannel("github", True), _FakeChannel("exa_search", True)]
    _patch(monkeypatch, channels, {"github": "ok", "exa_search": "off"})

    adapters, skipped, unknown = A.resolve_research(["exa_search"])

    assert set(adapters) == {"exa_search"}
    assert unknown == []


def test_resolve_flags_unknown_and_nonsearchable(monkeypatch):
    channels = [_FakeChannel("github", True), _FakeChannel("reddit", False)]
    _patch(monkeypatch, channels, {"github": "ok", "reddit": "ok"})

    adapters, skipped, unknown = A.resolve_research(["github", "reddit", "bogus"])

    assert set(adapters) == {"github"}
    assert unknown == ["bogus", "reddit"]       # reddit known-but-not-searchable


def test_resolve_uses_offline_doctor_to_skip_network_probes(monkeypatch):
    """`research` resolution must call doctor with offline=True.

    Network liveness probes cost 20s+ per call and are not needed to pick
    channels.
    """
    captured = {}
    monkeypatch.setattr(
        "autoresearch.channels.get_all_channels",
        lambda: [_FakeChannel("github", True)],
    )

    def fake_check_all(config, offline=False):
        captured["offline"] = offline
        return {"github": {"status": "ok"}}

    monkeypatch.setattr("autoresearch.doctor.check_all", fake_check_all)

    A.resolve_research()
    assert captured["offline"] is True


def test_resolve_accepts_exa_input_alias(monkeypatch):
    """`--channels exa` still resolves to the exa_search channel."""
    channels = [_FakeChannel("exa_search", True)]
    _patch(monkeypatch, channels, {"exa_search": "ok"})

    adapters, _, unknown = A.resolve_research(["exa"])

    assert set(adapters) == {"exa_search"}
    assert unknown == []
