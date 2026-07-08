# -*- coding: utf-8 -*-
"""Tests for channel registry basics and health checks."""

import json
import shutil
import subprocess
from urllib.error import URLError

from autoresearch.channels import get_all_channels, get_channel
from autoresearch.channels.v2ex import V2EXChannel
from autoresearch.channels.xiaohongshu import XiaoHongShuChannel
from autoresearch.channels.xueqiu import XueqiuChannel
from autoresearch.channels.hackernews import HackerNewsChannel, format_hn_result
from autoresearch.channels.youtube import YouTubeChannel
from autoresearch.channels.exa_search import ExaSearchChannel


def _which_map(present):
    """Return a shutil.which stand-in that resolves only the named tools."""
    return lambda tool: f"/usr/bin/{tool}" if tool in present else None


class TestChannelSearch:
    """Channels expose a uniform `search(query, limit) -> research rows`.
    `research` routes through these (single source of truth); the per-tool
    functions that used to live in adapters.py are gone."""

    from types import SimpleNamespace as _NS

    def test_base_not_searchable(self):
        from autoresearch.channels.base import Channel
        assert Channel.searchable is False

    def test_github_search_normalizes_rows(self, monkeypatch):
        from autoresearch.channels.github import GitHubChannel
        sample = [{"fullName": "tokio-rs/tokio", "description": "async runtime",
                   "url": "https://github.com/tokio-rs/tokio", "updatedAt": "2026-01-01"}]
        monkeypatch.setattr("autoresearch.channels.github.subprocess.run",
                            lambda cmd, **kw: self._NS(returncode=0, stdout=json.dumps(sample), stderr=""))
        rows = GitHubChannel().search("async rust", 5)
        assert GitHubChannel.searchable is True
        assert rows[0]["source"] == "github"
        assert rows[0]["url"] == "https://github.com/tokio-rs/tokio"
        for k in ("source", "title", "url", "snippet", "date"):
            assert k in rows[0]

    def test_github_search_neutralizes_flag_smuggling(self, monkeypatch):
        from autoresearch.channels.github import GitHubChannel
        captured = {}

        def fake_run(cmd, **kw):
            captured["cmd"] = cmd
            return self._NS(returncode=0, stdout="[]", stderr="")

        monkeypatch.setattr("autoresearch.channels.github.subprocess.run", fake_run)
        GitHubChannel().search("--version", 5)
        cmd = captured["cmd"]
        assert "--" in cmd and cmd.index("--") < cmd.index("--version")

    def test_github_search_raises_on_nonzero_exit(self, monkeypatch):
        from autoresearch.channels.github import GitHubChannel
        monkeypatch.setattr("autoresearch.channels.github.subprocess.run",
                            lambda cmd, **kw: self._NS(returncode=1, stdout="", stderr="gh: not logged in"))
        import pytest
        with pytest.raises(Exception) as ei:
            GitHubChannel().search("anything", 5)
        assert "not logged in" in str(ei.value)

    def test_twitter_search_normalizes_rows(self, monkeypatch):
        from autoresearch.channels.twitter import TwitterChannel
        sample = [{"id": "123", "author": "@alice", "text": "tokio is great for async rust",
                   "time": "Jun 09 16:25"}]
        # twitter.search runs through utils.proc.run_with_retry, so patch the
        # subprocess.run that helper actually calls.
        monkeypatch.setattr("autoresearch.utils.proc.subprocess.run",
                            lambda cmd, **kw: self._NS(returncode=0, stdout=json.dumps(sample), stderr=""))
        rows = TwitterChannel().search("rust async", 5)
        assert rows[0]["source"] == "twitter"
        assert rows[0]["url"] == "https://x.com/alice/status/123"
        assert "tokio" in rows[0]["snippet"]

    def test_twitter_search_uses_xquik_when_configured(self, monkeypatch):
        from autoresearch.channels.twitter import TwitterChannel
        captured = {}

        class _Config:
            def get(self, key, default=None):
                values = {
                    "xquik_api_key": "test-key",
                    "xquik_base_url": "https://xquik.test",
                }
                return values.get(key, default)

        class _Response:
            status_code = 200

            def json(self):
                return {
                    "tweets": [
                        {
                            "id": "42",
                            "text": "xquik search works",
                            "created": "2026-06-21T00:00:00Z",
                            "author": {"username": "alice"},
                        }
                    ]
                }

        def fake_get(url, **kwargs):
            captured["url"] = url
            captured["kwargs"] = kwargs
            return _Response()

        monkeypatch.setattr("autoresearch.channels.twitter.Config", _Config)
        monkeypatch.setattr("autoresearch.channels.twitter.requests.get", fake_get)

        rows = TwitterChannel().search("agent tools", 500)

        assert captured["url"] == "https://xquik.test/api/v1/x/tweets/search"
        assert captured["kwargs"]["headers"] == {"x-api-key": "test-key"}
        assert captured["kwargs"]["params"] == {
            "q": "agent tools",
            "queryType": "Latest",
            "limit": "200",
        }
        assert rows == [
            {
                "source": "twitter",
                "title": "@alice: xquik search works",
                "url": "https://x.com/alice/status/42",
                "snippet": "xquik search works",
                "date": "2026-06-21T00:00:00Z",
            }
        ]

    def test_twitter_search_neutralizes_flag_smuggling(self, monkeypatch):
        from autoresearch.channels.twitter import TwitterChannel
        captured = {}

        def fake_run(cmd, **kw):
            captured["cmd"] = cmd
            return self._NS(returncode=0, stdout="[]", stderr="")

        monkeypatch.setattr("autoresearch.utils.proc.subprocess.run", fake_run)
        TwitterChannel().search("-n 9999", 5)
        cmd = captured["cmd"]
        assert "--" in cmd and cmd.index("--") < cmd.index("-n 9999")

    def test_exa_search_escapes_quotes(self, monkeypatch):
        from autoresearch.channels.exa_search import ExaSearchChannel
        captured = {}

        def fake_run(cmd, **kw):
            captured["cmd"] = cmd
            return self._NS(returncode=0, stdout="", stderr="")

        monkeypatch.setattr("autoresearch.channels.exa_search.subprocess.run", fake_run)
        ExaSearchChannel().search('foo") + evil("', 5)
        call_arg = captured["cmd"][2]
        assert '") + evil("' not in call_arg
        assert '\\"' in call_arg

    def test_hackernews_search_maps_rows(self, monkeypatch):
        from autoresearch.channels.hackernews import HackerNewsChannel
        monkeypatch.setattr(HackerNewsChannel, "search_stories",
                            lambda self, q, limit=20: [{"objectID": "42", "title": "T",
                                                        "url": "", "created_at": "2020"}])
        rows = HackerNewsChannel().search("q", 5)
        assert rows[0]["source"] == "hackernews"
        assert rows[0]["url"] == "https://news.ycombinator.com/item?id=42"
        assert rows[0]["date"] == "2020"

    def test_reddit_search_maps_rows(self, monkeypatch):
        from autoresearch.channels.reddit import RedditChannel
        envelope = {"ok": True, "schema_version": "1", "data": [
            {"title": "Async in Rust", "permalink": "/r/rust/comments/abc/async/",
             "url": "https://example.com/x", "subreddit": "rust", "author": "bob",
             "score": 42, "num_comments": 7, "created_utc": 1700000000.0,
             "selftext": "tokio vs async-std"}]}
        monkeypatch.setattr("autoresearch.channels.reddit.subprocess.run",
                            lambda cmd, **kw: self._NS(returncode=0, stdout=json.dumps(envelope), stderr=""))
        rows = RedditChannel().search("rust async", 5)
        assert RedditChannel.searchable is True
        assert rows[0]["source"] == "reddit"
        assert rows[0]["url"] == "https://www.reddit.com/r/rust/comments/abc/async/"
        assert "tokio" in rows[0]["snippet"]
        assert rows[0]["date"] == "2023-11-14"

    def test_reddit_search_neutralizes_flag_smuggling(self, monkeypatch):
        from autoresearch.channels.reddit import RedditChannel
        captured = {}

        def fake_run(cmd, **kw):
            captured["cmd"] = cmd
            return self._NS(returncode=0, stdout='{"ok":true,"data":[]}', stderr="")

        monkeypatch.setattr("autoresearch.channels.reddit.subprocess.run", fake_run)
        RedditChannel().search("--help", 5)
        cmd = captured["cmd"]
        assert "--" in cmd and cmd.index("--") < cmd.index("--help")

    def test_reddit_search_raises_on_nonzero_exit(self, monkeypatch):
        from autoresearch.channels.reddit import RedditChannel
        monkeypatch.setattr("autoresearch.channels.reddit.subprocess.run",
                            lambda cmd, **kw: self._NS(returncode=1, stdout="", stderr="not logged in"))
        import pytest
        with pytest.raises(Exception) as ei:
            RedditChannel().search("q", 5)
        assert "not logged in" in str(ei.value)

    def test_youtube_search_maps_rows(self, monkeypatch):
        from autoresearch.channels.youtube import YouTubeChannel
        data = {"entries": [{"id": "FUg1", "title": "Rust async runtime",
                             "url": "https://www.youtube.com/watch?v=FUg1",
                             "uploader": "Rusty", "description": "a deep dive talk",
                             "timestamp": 1700000000}]}
        monkeypatch.setattr("autoresearch.channels.youtube.subprocess.run",
                            lambda cmd, **kw: self._NS(returncode=0, stdout=json.dumps(data), stderr=""))
        rows = YouTubeChannel().search("rust async", 3)
        assert YouTubeChannel.searchable is True
        assert rows[0]["source"] == "youtube"
        assert rows[0]["url"] == "https://www.youtube.com/watch?v=FUg1"
        assert "deep dive" in rows[0]["snippet"]
        assert rows[0]["date"] == "2023-11-14"

    def test_youtube_search_uses_ytsearch_target(self, monkeypatch):
        from autoresearch.channels.youtube import YouTubeChannel
        captured = {}

        def fake_run(cmd, **kw):
            captured["cmd"] = cmd
            return self._NS(returncode=0, stdout='{"entries":[]}', stderr="")

        monkeypatch.setattr("autoresearch.channels.youtube.subprocess.run", fake_run)
        YouTubeChannel().search("llm agents", 4)
        assert any(str(a).startswith("ytsearch4:") for a in captured["cmd"])

    def test_arxiv_search_maps_atom_rows(self, monkeypatch):
        from autoresearch.channels.arxiv import ArxivChannel
        atom = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Attention Is All You Need</title>
    <id>http://arxiv.org/abs/1706.03762v5</id>
    <published>2017-06-12T17:57:34Z</published>
    <summary>The dominant sequence transduction models are based on RNNs.</summary>
    <author><name>Ashish Vaswani</name></author>
  </entry>
</feed>"""
        monkeypatch.setattr("autoresearch.channels.arxiv._get_text",
                            lambda url, timeout=10: atom)
        rows = ArxivChannel().search("transformers", 5)
        assert ArxivChannel.searchable is True
        assert rows[0]["source"] == "arxiv"
        assert rows[0]["url"] == "http://arxiv.org/abs/1706.03762v5"
        assert rows[0]["title"] == "Attention Is All You Need"
        assert rows[0]["date"] == "2017-06-12"
        assert "dominant" in rows[0]["snippet"]

    def test_arxiv_can_handle(self):
        from autoresearch.channels.arxiv import ArxivChannel
        ch = ArxivChannel()
        assert ch.can_handle("https://arxiv.org/abs/1706.03762") is True
        assert ch.can_handle("https://example.com") is False

    def test_stackoverflow_search_maps_rows(self, monkeypatch):
        from autoresearch.channels.stackoverflow import StackOverflowChannel
        payload = {"items": [{"title": "How to do X in Rust?",
                              "link": "https://stackoverflow.com/questions/1/x",
                              "creation_date": 1620444864, "score": 8,
                              "answer_count": 2, "tags": ["rust"]}],
                   "quota_remaining": 299}
        monkeypatch.setattr("autoresearch.channels.stackoverflow._get_json",
                            lambda url, timeout=10: payload)
        rows = StackOverflowChannel().search("rust x", 5)
        assert StackOverflowChannel.searchable is True
        assert rows[0]["source"] == "stackoverflow"
        assert rows[0]["url"] == "https://stackoverflow.com/questions/1/x"
        assert rows[0]["date"] == "2021-05-08"
        assert "rust" in rows[0]["snippet"]

    def test_stackoverflow_can_handle(self):
        from autoresearch.channels.stackoverflow import StackOverflowChannel
        ch = StackOverflowChannel()
        assert ch.can_handle("https://stackoverflow.com/questions/1/x") is True
        assert ch.can_handle("https://example.com") is False

    def test_new_channels_registered(self):
        from autoresearch.channels import get_channel
        assert get_channel("arxiv") is not None
        assert get_channel("stackoverflow") is not None

    def test_wikipedia_search_maps_rows(self, monkeypatch):
        from autoresearch.channels.wikipedia import WikipediaChannel
        payload = {"query": {"search": [{
            "title": "Transformer (deep learning)", "pageid": 61603971,
            "timestamp": "2026-06-17T19:00:42Z",
            "snippet": 'In deep learning, the <span class="searchmatch">transformer</span> is a family'}]}}
        monkeypatch.setattr("autoresearch.channels.wikipedia.get_json",
                            lambda url, timeout=10: payload)
        rows = WikipediaChannel().search("transformer", 5)
        assert WikipediaChannel.searchable is True
        assert rows[0]["source"] == "wikipedia"
        assert "61603971" in rows[0]["url"]
        assert rows[0]["date"] == "2026-06-17"
        assert "<span" not in rows[0]["snippet"]  # HTML stripped
        assert "transformer is a family" in rows[0]["snippet"]

    def test_wikipedia_can_handle(self):
        from autoresearch.channels.wikipedia import WikipediaChannel
        ch = WikipediaChannel()
        assert ch.can_handle("https://en.wikipedia.org/wiki/Transformer") is True
        assert ch.can_handle("https://example.com") is False

    def test_semanticscholar_search_maps_rows(self, monkeypatch):
        from autoresearch.channels.semanticscholar import SemanticScholarChannel
        payload = {"data": [{"paperId": "abc",
                             "url": "https://www.semanticscholar.org/paper/abc",
                             "title": "Masked-attention Mask Transformer", "year": 2021,
                             "abstract": "We present a new architecture.",
                             "authors": [{"name": "A B"}]}]}
        monkeypatch.setattr("autoresearch.channels.semanticscholar.get_json",
                            lambda url, timeout=10: payload)
        rows = SemanticScholarChannel().search("transformer", 5)
        assert SemanticScholarChannel.searchable is True
        assert rows[0]["source"] == "semanticscholar"
        assert rows[0]["url"] == "https://www.semanticscholar.org/paper/abc"
        assert rows[0]["date"] == "2021"
        assert "new architecture" in rows[0]["snippet"]

    def test_pubmed_search_maps_rows(self, monkeypatch):
        from autoresearch.channels.pubmed import PubMedChannel

        def fake_get_json(url, timeout=10):
            if "esearch" in url:
                return {"esearchresult": {"idlist": ["42324300"]}}
            return {"result": {"uids": ["42324300"], "42324300": {
                "title": "Deletion of activating transcription factor 3",
                "sortpubdate": "2026/06/21 00:00", "source": "Sci Rep",
                "authors": [{"name": "Su L"}]}}}

        monkeypatch.setattr("autoresearch.channels.pubmed.get_json", fake_get_json)
        rows = PubMedChannel().search("crispr", 5)
        assert PubMedChannel.searchable is True
        assert rows[0]["source"] == "pubmed"
        assert rows[0]["url"] == "https://pubmed.ncbi.nlm.nih.gov/42324300/"
        assert rows[0]["date"] == "2026-06-21"
        assert "Sci Rep" in rows[0]["snippet"]

    def test_pubmed_empty_idlist_returns_no_rows(self, monkeypatch):
        from autoresearch.channels.pubmed import PubMedChannel
        monkeypatch.setattr("autoresearch.channels.pubmed.get_json",
                            lambda url, timeout=10: {"esearchresult": {"idlist": []}})
        assert PubMedChannel().search("zzznoresults", 5) == []

    def test_more_channels_registered(self):
        from autoresearch.channels import get_channel
        for name in ("wikipedia", "semanticscholar", "pubmed"):
            assert get_channel(name) is not None, name


class TestChannelFix:
    """`fix()` auto-applies the fixable setup steps (doctor --fix)."""

    def test_base_fix_is_noop(self):
        # A channel with no override reports nothing to fix.
        changed, msg = V2EXChannel().fix()
        assert changed is False
        assert msg == ""

    def test_youtube_fix_writes_js_runtime(self, tmp_path, monkeypatch):
        cfg = tmp_path / "yt-dlp" / "config"
        monkeypatch.setattr("autoresearch.channels.youtube.shutil.which",
                            _which_map({"yt-dlp", "node"}))  # node present, no deno
        monkeypatch.setattr("autoresearch.channels.youtube.get_ytdlp_config_path",
                            lambda: cfg)
        changed, msg = YouTubeChannel().fix()
        assert changed is True
        assert "--js-runtimes node" in cfg.read_text(encoding="utf-8")
        # Idempotent: a second run changes nothing.
        changed2, _ = YouTubeChannel().fix()
        assert changed2 is False

    def test_youtube_fix_skips_when_deno_present(self, monkeypatch):
        monkeypatch.setattr("autoresearch.channels.youtube.shutil.which",
                            _which_map({"yt-dlp", "deno"}))
        changed, msg = YouTubeChannel().fix()
        assert changed is False  # deno works out of the box

    def test_youtube_fix_not_fixable_without_ytdlp(self, monkeypatch):
        monkeypatch.setattr("autoresearch.channels.youtube.shutil.which",
                            _which_map(set()))
        changed, msg = YouTubeChannel().fix()
        assert changed is False
        assert "yt-dlp" in msg  # actionable manual hint

    def test_exa_fix_not_fixable_without_mcporter(self, monkeypatch):
        monkeypatch.setattr("autoresearch.channels.exa_search.shutil.which",
                            _which_map(set()))
        changed, msg = ExaSearchChannel().fix()
        assert changed is False
        assert "mcporter" in msg

    def test_exa_fix_adds_entry_when_missing(self, monkeypatch):
        monkeypatch.setattr("autoresearch.channels.exa_search.shutil.which",
                            _which_map({"mcporter"}))
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)

            class R:
                returncode = 0
                stdout = "" if "list" in cmd else "added exa"
                stderr = ""
            return R()

        monkeypatch.setattr("autoresearch.channels.exa_search.subprocess.run", fake_run)
        changed, msg = ExaSearchChannel().fix()
        assert changed is True
        assert any("add" in c and "exa" in c for c in calls)


class TestChannelRegistry:
    def test_get_channel_by_name(self):
        ch = get_channel("github")
        assert ch is not None
        assert ch.name == "github"

    def test_get_unknown_channel_returns_none(self):
        assert get_channel("not-exists") is None

    def test_all_channels_registered(self):
        channels = get_all_channels()
        names = [ch.name for ch in channels]
        assert "web" in names
        assert "github" in names
        assert "twitter" in names
        assert "v2ex" in names


class TestV2EXChannel:
    def test_can_handle_v2ex_urls(self):
        ch = V2EXChannel()
        assert ch.can_handle("https://www.v2ex.com/t/1234567")
        assert ch.can_handle("https://v2ex.com/go/python")
        assert not ch.can_handle("https://github.com/user/repo")
        assert not ch.can_handle("https://reddit.com/r/Python")

    def test_check_ok_when_api_reachable(self, monkeypatch):
        import urllib.request

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return b"[]"

        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            lambda req, timeout=None: FakeResponse(),
        )
        status, msg = V2EXChannel().check()
        assert status == "ok"
        assert "Public API available" in msg

    def test_check_warn_when_api_unreachable(self, monkeypatch):
        import urllib.request

        def raise_error(req, timeout=None):
            raise URLError("connection refused")

        monkeypatch.setattr(urllib.request, "urlopen", raise_error)
        status, msg = V2EXChannel().check()
        assert status == "warn"
        assert "failed" in msg

    # ------------------------------------------------------------------ #
    # get_hot_topics
    # ------------------------------------------------------------------ #

    def test_get_hot_topics_returns_list(self, monkeypatch):
        import urllib.request

        fake_data = [
            {
                "id": 111,
                "title": "Python 3.13 发布了",
                "url": "https://www.v2ex.com/t/111",
                "replies": 42,
                "content": "发布公告内容",
                "created": 1700000000,
                "node": {"name": "python", "title": "Python"},
            },
            {
                "id": 222,
                "title": "Rust 好学吗",
                "url": "https://www.v2ex.com/t/222",
                "replies": 10,
                "content": "",
                "created": 1700000001,
                "node": {"name": "rust", "title": "Rust"},
            },
        ]

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def read(self):
                return json.dumps(fake_data).encode()

        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResponse())
        topics = V2EXChannel().get_hot_topics(limit=5)
        assert len(topics) == 2
        assert topics[0]["id"] == 111
        assert topics[0]["title"] == "Python 3.13 发布了"
        assert topics[0]["replies"] == 42
        assert topics[0]["node_name"] == "python"
        assert topics[0]["node_title"] == "Python"
        assert topics[0]["created"] == 1700000000

    def test_get_hot_topics_respects_limit(self, monkeypatch):
        import urllib.request

        fake_data = [
            {"id": i, "title": f"Topic {i}", "url": f"https://v2ex.com/t/{i}", "replies": i,
             "content": "", "created": 1700000000 + i, "node": {"name": "tech", "title": "Tech"}}
            for i in range(10)
        ]

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return json.dumps(fake_data).encode()

        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResponse())
        topics = V2EXChannel().get_hot_topics(limit=3)
        assert len(topics) == 3

    def test_get_hot_topics_truncates_content(self, monkeypatch):
        import urllib.request

        long_content = "A" * 300
        fake_data = [
            {"id": 1, "title": "Long post", "url": "https://v2ex.com/t/1", "replies": 0,
             "content": long_content, "created": 1700000000, "node": {"name": "tech", "title": "Tech"}}
        ]

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return json.dumps(fake_data).encode()

        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResponse())
        topics = V2EXChannel().get_hot_topics(limit=1)
        assert len(topics[0]["content"]) == 200

    # ------------------------------------------------------------------ #
    # get_node_topics
    # ------------------------------------------------------------------ #

    def test_get_node_topics(self, monkeypatch):
        import urllib.request

        fake_data = [
            {
                "id": 333,
                "title": "Flask 部署问题",
                "url": "https://www.v2ex.com/t/333",
                "replies": 5,
                "content": "求帮助",
                "created": 1710000000,
                "node": {"name": "python", "title": "Python"},
            }
        ]

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return json.dumps(fake_data).encode()

        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResponse())
        topics = V2EXChannel().get_node_topics("python")
        assert len(topics) == 1
        assert topics[0]["id"] == 333
        assert topics[0]["node_name"] == "python"
        assert topics[0]["title"] == "Flask 部署问题"
        assert topics[0]["created"] == 1710000000

    # ------------------------------------------------------------------ #
    # get_topic
    # ------------------------------------------------------------------ #

    def test_get_topic_returns_detail_and_replies(self, monkeypatch):
        import urllib.request

        topic_data = [
            {
                "id": 999,
                "title": "测试帖子",
                "url": "https://www.v2ex.com/t/999",
                "content": "帖子正文",
                "replies": 2,
                "node": {"name": "qna", "title": "问与答"},
                "member": {"username": "alice"},
                "created": 1700000000,
            }
        ]
        replies_data = [
            {
                "member": {"username": "bob"},
                "content": "第一条回复",
                "created": 1700000100,
            },
            {
                "member": {"username": "carol"},
                "content": "第二条回复",
                "created": 1700000200,
            },
        ]

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return json.dumps(self._payload).encode()

        def fake_urlopen(req, timeout=None):
            url = req.full_url
            if "replies" in url:
                return FakeResponse(replies_data)
            return FakeResponse(topic_data)

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        result = V2EXChannel().get_topic(999)

        assert result["id"] == 999
        assert result["title"] == "测试帖子"
        assert result["author"] == "alice"
        assert result["node_name"] == "qna"
        assert len(result["replies"]) == 2
        assert result["replies"][0]["author"] == "bob"
        assert result["replies"][1]["content"] == "第二条回复"

    def test_get_topic_handles_empty_replies(self, monkeypatch):
        import urllib.request

        topic_data = [
            {
                "id": 1,
                "title": "孤独帖子",
                "url": "https://www.v2ex.com/t/1",
                "content": "",
                "replies": 0,
                "node": {"name": "offtopic", "title": "水"},
                "member": {"username": "dave"},
                "created": 0,
            }
        ]

        class FakeResponse:
            def __init__(self, payload): self._payload = payload
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return json.dumps(self._payload).encode()

        def fake_urlopen(req, timeout=None):
            if "replies" in req.full_url:
                return FakeResponse([])
            return FakeResponse(topic_data)

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        result = V2EXChannel().get_topic(1)
        assert result["replies"] == []

    # ------------------------------------------------------------------ #
    # get_user
    # ------------------------------------------------------------------ #

    def test_get_user_returns_profile(self, monkeypatch):
        import urllib.request

        fake_user = {
            "id": 42,
            "username": "alice",
            "url": "https://www.v2ex.com/member/alice",
            "website": "https://alice.dev",
            "twitter": "alice_tw",
            "psn": "",
            "github": "alice",
            "btc": "",
            "location": "Shanghai",
            "bio": "Python dev",
            "avatar_large": "https://cdn.v2ex.com/avatars/alice_large.png",
            "created": 1500000000,
        }

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return json.dumps(fake_user).encode()

        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResponse())
        user = V2EXChannel().get_user("alice")

        assert user["id"] == 42
        assert user["username"] == "alice"
        assert user["github"] == "alice"
        assert user["location"] == "Shanghai"
        assert "alice_large.png" in user["avatar"]

    # ------------------------------------------------------------------ #
    # search
    # ------------------------------------------------------------------ #

    def test_search_returns_unavailable_notice(self):
        result = V2EXChannel().search("python asyncio")
        assert len(result) == 1
        assert "error" in result[0]
        assert "V2EX" in result[0]["error"]


class TestXueqiuChannel:
    def test_can_handle_xueqiu_urls(self):
        ch = XueqiuChannel()
        assert ch.can_handle("https://xueqiu.com/S/SH600519")
        assert ch.can_handle("https://stock.xueqiu.com/v5/stock/batch/quote.json")
        assert ch.can_handle("https://www.xueqiu.com/1234567890/12345")
        assert not ch.can_handle("https://github.com/user/repo")
        assert not ch.can_handle("https://v2ex.com/t/123")

    def test_check_ok_when_api_reachable(self, monkeypatch):
        import autoresearch.channels.xueqiu as xueqiu_mod

        monkeypatch.setattr(xueqiu_mod, "_cookies_initialized", True)

        fake_response_data = {
            "data": {
                "items": [
                    {"quote": {"symbol": "SH000001", "name": "上证指数", "current": 3200.0}}
                ]
            }
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def read(self):
                return json.dumps(fake_response_data).encode()

        monkeypatch.setattr(xueqiu_mod._opener, "open", lambda req, timeout=None: FakeResponse())
        status, msg = XueqiuChannel().check()
        assert status == "ok"
        assert "Public API available" in msg

    def test_check_warn_when_api_unreachable(self, monkeypatch):
        import autoresearch.channels.xueqiu as xueqiu_mod

        monkeypatch.setattr(xueqiu_mod, "_cookies_initialized", True)

        def raise_error(req, timeout=None):
            raise URLError("connection refused")

        monkeypatch.setattr(xueqiu_mod._opener, "open", raise_error)
        status, msg = XueqiuChannel().check()
        assert status == "warn"
        assert "failed" in msg

    # ------------------------------------------------------------------ #
    # get_stock_quote
    # ------------------------------------------------------------------ #

    def test_get_stock_quote(self, monkeypatch):
        import autoresearch.channels.xueqiu as xueqiu_mod

        monkeypatch.setattr(xueqiu_mod, "_cookies_initialized", True)

        fake_data = {
            "data": {
                "items": [
                    {
                        "quote": {
                            "symbol": "SH600519",
                            "name": "贵州茅台",
                            "current": 1800.0,
                            "percent": 1.5,
                            "chg": 26.6,
                            "high": 1810.0,
                            "low": 1770.0,
                            "open": 1775.0,
                            "last_close": 1773.4,
                            "volume": 12345678,
                            "amount": 22000000000,
                            "market_capital": 2260000000000,
                            "turnover_rate": 0.098,
                            "pe_ttm": 30.5,
                            "timestamp": 1700000000000,
                        }
                    }
                ]
            }
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def read(self):
                return json.dumps(fake_data).encode()

        monkeypatch.setattr(xueqiu_mod._opener, "open", lambda req, timeout=None: FakeResponse())
        quote = XueqiuChannel().get_stock_quote("SH600519")
        assert quote["symbol"] == "SH600519"
        assert quote["name"] == "贵州茅台"
        assert quote["current"] == 1800.0
        assert quote["percent"] == 1.5
        assert quote["volume"] == 12345678

    # ------------------------------------------------------------------ #
    # search_stock
    # ------------------------------------------------------------------ #

    def test_search_stock(self, monkeypatch):
        import autoresearch.channels.xueqiu as xueqiu_mod

        monkeypatch.setattr(xueqiu_mod, "_cookies_initialized", True)

        fake_data = {
            "stocks": [
                {"code": "SH600519", "name": "贵州茅台", "exchange": "SHA"},
                {"code": "SZ000858", "name": "五粮液", "exchange": "SZA"},
            ]
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def read(self):
                return json.dumps(fake_data).encode()

        monkeypatch.setattr(xueqiu_mod._opener, "open", lambda req, timeout=None: FakeResponse())
        results = XueqiuChannel().search_stock("茅台", limit=5)
        assert len(results) == 2
        assert results[0]["symbol"] == "SH600519"
        assert results[0]["name"] == "贵州茅台"
        assert results[1]["exchange"] == "SZA"

    # ------------------------------------------------------------------ #
    # get_hot_posts
    # ------------------------------------------------------------------ #

    def test_get_hot_posts_returns_list(self, monkeypatch):
        import autoresearch.channels.xueqiu as xueqiu_mod

        monkeypatch.setattr(xueqiu_mod, "_cookies_initialized", True)

        # v4 timeline: each item has a JSON-encoded `data` field
        def make_item(id_, title, text, author, likes, target):
            post = {
                "id": id_,
                "title": title,
                "text": text,
                "user": {"screen_name": author},
                "like_count": likes,
                "target": target,
            }
            return {"data": json.dumps(post), "original_status": None}

        fake_data = {
            "list": [
                make_item(111, "市场分析", "<p>今天大盘走势&amp;分析</p>", "投资者A", 42, "/1234567890/111"),
                make_item(222, "", "短评", "投资者B", 10, "/9876543210/222"),
            ]
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def read(self):
                return json.dumps(fake_data).encode()

        monkeypatch.setattr(xueqiu_mod._opener, "open", lambda req, timeout=None: FakeResponse())
        posts = XueqiuChannel().get_hot_posts(limit=10)
        assert len(posts) == 2
        assert posts[0]["id"] == 111
        assert posts[0]["author"] == "投资者A"
        assert posts[0]["likes"] == 42
        assert "今天大盘走势&分析" in posts[0]["text"]  # HTML stripped
        assert "<p>" not in posts[0]["text"]
        assert posts[0]["url"] == "https://xueqiu.com/1234567890/111"

    def test_get_hot_posts_respects_limit(self, monkeypatch):
        import autoresearch.channels.xueqiu as xueqiu_mod

        monkeypatch.setattr(xueqiu_mod, "_cookies_initialized", True)

        fake_data = {
            "list": [
                {
                    "data": json.dumps({
                        "id": i,
                        "title": f"Post {i}",
                        "text": f"Content {i}",
                        "user": {"screen_name": f"User {i}"},
                        "like_count": i,
                        "target": f"/user/{i}",
                    }),
                    "original_status": None,
                }
                for i in range(10)
            ]
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def read(self):
                return json.dumps(fake_data).encode()

        monkeypatch.setattr(xueqiu_mod._opener, "open", lambda req, timeout=None: FakeResponse())
        posts = XueqiuChannel().get_hot_posts(limit=3)
        assert len(posts) == 3

    # ------------------------------------------------------------------ #
    # get_hot_stocks
    # ------------------------------------------------------------------ #

    def test_get_hot_stocks(self, monkeypatch):
        import autoresearch.channels.xueqiu as xueqiu_mod

        monkeypatch.setattr(xueqiu_mod, "_cookies_initialized", True)

        fake_data = {
            "data": {
                "items": [
                    {"code": "SH600519", "name": "贵州茅台", "current": 1800.0, "percent": 1.5},
                    {"code": "SZ000858", "name": "五粮液", "current": 160.0, "percent": -0.8},
                    {"code": "SH601318", "name": "中国平安", "current": 45.0, "percent": 0.3},
                ]
            }
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def read(self):
                return json.dumps(fake_data).encode()

        monkeypatch.setattr(xueqiu_mod._opener, "open", lambda req, timeout=None: FakeResponse())
        stocks = XueqiuChannel().get_hot_stocks(limit=10, stock_type=10)
        assert len(stocks) == 3
        assert stocks[0]["symbol"] == "SH600519"
        assert stocks[0]["rank"] == 1
        assert stocks[1]["percent"] == -0.8
        assert stocks[2]["rank"] == 3

    # ------------------------------------------------------------------ #
    # Cookie loading
    # ------------------------------------------------------------------ #

    def test_ensure_cookies_loads_from_config(self, monkeypatch, tmp_path):
        """_ensure_cookies() should inject cookies from the config file."""
        import autoresearch.channels.xueqiu as xueqiu_mod

        monkeypatch.setattr(xueqiu_mod, "_cookies_initialized", False)

        # Provide a fake Config that returns a cookie string with xq_a_token
        class FakeConfig:
            def get(self, key, default=None):
                if key == "xueqiu_cookie":
                    return "xq_a_token=TESTTOKEN; xq_is_login=1"
                return default

        import autoresearch.channels.xueqiu as xq_mod
        monkeypatch.setattr(
            xq_mod,
            "_load_cookies_from_config",
            lambda: (xq_mod._inject_cookie_string("xq_a_token=TESTTOKEN; xq_is_login=1") or True),
        )
        monkeypatch.setattr(xq_mod, "_load_cookies_from_browser", lambda: False)

        # Patch opener so no real HTTP call is made
        class FakeResp:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return b'{"data":{"items":[]}}'

        monkeypatch.setattr(xq_mod._opener, "open", lambda req, timeout=None: FakeResp())

        xq_mod._ensure_cookies()
        assert xq_mod._cookies_initialized is True
        cookie_names = {c.name for c in xq_mod._cookie_jar}
        assert "xq_a_token" in cookie_names

    def test_get_json_sends_referer_and_browser_ua(self, monkeypatch):
        """_get_json() must send Referer and a browser-like User-Agent."""
        import autoresearch.channels.xueqiu as xueqiu_mod

        monkeypatch.setattr(xueqiu_mod, "_cookies_initialized", True)
        captured = {}

        class FakeResp:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return b'{"data":{"items":[]}}'

        def fake_open(req, timeout=None):
            captured["ua"] = req.get_header("User-agent")
            captured["referer"] = req.get_header("Referer")
            return FakeResp()

        monkeypatch.setattr(xueqiu_mod._opener, "open", fake_open)
        xueqiu_mod._get_json("https://stock.xueqiu.com/v5/stock/batch/quote.json?symbol=SH000001")

        assert captured["referer"] == "https://xueqiu.com/"
        assert "Mozilla" in captured["ua"]
        assert "autoresearch" not in captured["ua"]


class TestRedditChannel:
    def test_reports_off_when_not_installed(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda _: None)
        from autoresearch.channels.reddit import RedditChannel
        status, msg = RedditChannel().check()
        assert status == "off"
        assert "rdt-cli" in msg
        assert "public-clis/rdt-cli" in msg
        # Guard: the install command must be satisfiable. PyPI's latest is 0.4.1, so a
        # `>=0.4.2` pin makes `pip install` fail outright — never reintroduce it.
        assert ">=0.4.2" not in msg
        assert "pip install rdt-cli" in msg

    def test_reports_ok_when_authenticated(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda _: "/usr/local/bin/rdt")
        fake_output = json.dumps({
            "ok": True,
            "schema_version": "1",
            "data": {"authenticated": True, "username": "testuser", "cookie_count": 1},
        })

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, fake_output, "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        from autoresearch.channels.reddit import RedditChannel
        status, msg = RedditChannel().check()
        assert status == "ok"
        assert "testuser" in msg

    def test_reports_warn_when_not_authenticated(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda _: "/usr/local/bin/rdt")
        fake_output = json.dumps({
            "ok": True,
            "schema_version": "1",
            "data": {"authenticated": False, "username": None, "cookie_count": 0},
        })

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, fake_output, "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        from autoresearch.channels.reddit import RedditChannel
        status, msg = RedditChannel().check()
        assert status == "warn"
        assert "403" in msg
        assert "rdt login" in msg
        assert "Cookie-Editor" in msg
        assert "chromewebstore.google.com" in msg

    def test_reports_warn_when_status_check_fails(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda _: "/usr/local/bin/rdt")

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 1, "not valid json{{{", "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        from autoresearch.channels.reddit import RedditChannel
        status, msg = RedditChannel().check()
        assert status == "warn"

    def test_can_handle_reddit_urls(self):
        from autoresearch.channels.reddit import RedditChannel
        ch = RedditChannel()
        assert ch.can_handle("https://www.reddit.com/r/python/comments/abc123/")
        assert ch.can_handle("https://redd.it/abc123")
        assert not ch.can_handle("https://github.com/user/repo")
        assert not ch.can_handle("https://v2ex.com/t/123")


class TestXiaoHongShuChannel:
    def test_reports_ok_when_cli_authenticated(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda _: "/usr/local/bin/xhs")

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, "ok: true\nusername: testuser\n", "")

        monkeypatch.setattr(subprocess, "run", fake_run)

        status, msg = XiaoHongShuChannel().check()
        assert status == "ok"
        assert "Fully available" in msg

    def test_reports_warn_when_not_authenticated(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda _: "/usr/local/bin/xhs")

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 1, "", "ok: false\nerror:\n  code: not_authenticated\n")

        monkeypatch.setattr(subprocess, "run", fake_run)

        status, msg = XiaoHongShuChannel().check()
        assert status == "warn"
        assert "xhs login" in msg

    def test_reports_off_when_not_installed(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda _: None)
        status, msg = XiaoHongShuChannel().check()
        assert status == "off"
        assert "xiaohongshu-cli" in msg


class TestHackerNewsChannelBasics:
    def test_can_handle_hn_and_algolia_urls(self):
        ch = HackerNewsChannel()
        assert ch.can_handle("https://news.ycombinator.com/item?id=8863")
        assert ch.can_handle("http://hn.algolia.com/api/v1/items/8863")
        assert not ch.can_handle("https://github.com/user/repo")
        assert not ch.can_handle("https://reddit.com/r/Python")

    def test_registered_in_all_channels(self):
        names = [ch.name for ch in get_all_channels()]
        assert "hackernews" in names

    def test_tier_is_zero_config(self):
        assert HackerNewsChannel().tier == 0

    def test_extract_item_id_from_hn_url(self):
        ch = HackerNewsChannel()
        assert ch._extract_item_id("https://news.ycombinator.com/item?id=8863") == "8863"
        assert ch._extract_item_id("http://hn.algolia.com/api/v1/items/42") == "42"

    def test_extract_item_id_missing_returns_none(self):
        ch = HackerNewsChannel()
        assert ch._extract_item_id("https://news.ycombinator.com/newest") is None

    def test_check_ok_when_api_reachable(self, monkeypatch):
        import urllib.request

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return b'{"hits": []}'

        monkeypatch.setattr(
            urllib.request, "urlopen", lambda req, timeout=None: FakeResponse()
        )
        status, msg = HackerNewsChannel().check()
        assert status == "ok"
        assert "Public API available" in msg

    def test_check_warn_when_api_unreachable(self, monkeypatch):
        import urllib.request

        def raise_error(req, timeout=None):
            raise URLError("connection refused")

        monkeypatch.setattr(urllib.request, "urlopen", raise_error)
        status, msg = HackerNewsChannel().check()
        assert status == "warn"
        assert "failed" in msg

    def test_search_stories_maps_fields_and_respects_limit(self, monkeypatch):
        import autoresearch.channels.hackernews as hn

        fake = {
            "hits": [
                {
                    "objectID": "1",
                    "title": "Story One",
                    "url": "https://example.com/1",
                    "author": "alice",
                    "points": 100,
                    "num_comments": 20,
                    "created_at": "2026-01-01T00:00:00Z",
                    "_tags": ["story"],
                },
                {
                    "objectID": "2",
                    "title": "Story Two",
                    "url": "https://example.com/2",
                    "author": "bob",
                    "points": 50,
                    "num_comments": 5,
                    "created_at": "2026-01-02T00:00:00Z",
                },
            ]
        }
        monkeypatch.setattr(hn, "_get_json", lambda url: fake)
        results = HackerNewsChannel().search_stories("python", limit=1)
        assert len(results) == 1
        first = results[0]
        assert first["title"] == "Story One"
        assert first["objectID"] == "1"
        assert first["author"] == "alice"
        assert first["points"] == 100
        assert first["num_comments"] == 20
        assert first["url"] == "https://example.com/1"
        # structural noise dropped
        assert "_tags" not in first

    def test_get_item_returns_cleaned_truncated_story(self, monkeypatch):
        import autoresearch.channels.hackernews as hn

        fake_item = {
            "id": 8863,
            "type": "story",
            "title": "My Story",
            "url": "https://example.com",
            "author": "pg",
            "points": 200,
            "created_at": "2026-01-01T00:00:00Z",
            "children": [
                {
                    "id": 1,
                    "type": "comment",
                    "author": "u1",
                    "text": "<p>great point &amp; more</p>",
                    "created_at": "2026-01-01T01:00:00Z",
                    "parent_id": 8863,
                    "children": [],
                }
            ],
        }
        monkeypatch.setattr(hn, "_get_json", lambda url: fake_item)
        result = HackerNewsChannel().get_item("8863")
        assert result["title"] == "My Story"
        assert result["author"] == "pg"
        assert result["points"] == 200
        assert len(result["comments"]) == 1
        c = result["comments"][0]
        assert c["author"] == "u1"
        # HTML stripped & entities unescaped
        assert c["text"] == "great point & more"
        # structural noise dropped
        assert "parent_id" not in c


class TestFormatHNResult:
    def test_search_mode_returns_flat_clean_list(self):
        data = {
            "hits": [
                {
                    "objectID": "1",
                    "title": "T1",
                    "url": "https://e.com/1",
                    "author": "a",
                    "points": 9,
                    "num_comments": 3,
                    "created_at": "2026-01-01T00:00:00Z",
                    "story_text": "noise",
                    "_tags": ["story"],
                    "_highlightResult": {"junk": 1},
                }
            ]
        }
        out = format_hn_result(data)
        assert isinstance(out, list)
        assert out[0] == {
            "objectID": "1",
            "title": "T1",
            "url": "https://e.com/1",
            "author": "a",
            "points": 9,
            "num_comments": 3,
            "created_at": "2026-01-01T00:00:00Z",
        }

    def test_read_mode_caps_top_level_comments(self):
        children = [
            {"type": "comment", "author": f"u{i}", "text": f"c{i}", "children": []}
            for i in range(40)
        ]
        data = {"type": "story", "title": "S", "children": children}
        out = format_hn_result(data)
        assert len(out["comments"]) == 30
        assert out["_truncated"] == 10

    def test_read_mode_caps_children_per_node(self):
        grandkids = [
            {"type": "comment", "author": f"g{i}", "text": "x", "children": []}
            for i in range(8)
        ]
        data = {
            "type": "story",
            "title": "S",
            "children": [
                {"type": "comment", "author": "top", "text": "t", "children": grandkids}
            ],
        }
        out = format_hn_result(data)
        top = out["comments"][0]
        assert len(top["children"]) == 5
        assert top["_truncated"] == 3

    def test_read_mode_caps_depth(self):
        # depth 4 deep; HN_MAX_DEPTH=3 means level 4 children are dropped.
        level4 = {"type": "comment", "author": "d4", "text": "x", "children": []}
        level3 = {"type": "comment", "author": "d3", "text": "x", "children": [level4]}
        level2 = {"type": "comment", "author": "d2", "text": "x", "children": [level3]}
        level1 = {"type": "comment", "author": "d1", "text": "x", "children": [level2]}
        data = {"type": "story", "title": "S", "children": [level1]}
        out = format_hn_result(data)
        d1 = out["comments"][0]
        d2 = d1["children"][0]
        d3 = d2["children"][0]
        # d3 is at depth 3: its child (d4) must be dropped but counted
        assert "children" not in d3
        assert d3["_truncated"] == 1

    def test_read_mode_truncates_long_comment_text(self):
        long_text = "B" * 1500
        data = {
            "type": "story",
            "title": "S",
            "children": [
                {"type": "comment", "author": "u", "text": long_text, "children": []}
            ],
        }
        out = format_hn_result(data)
        assert len(out["comments"][0]["text"]) == 1000

    def test_read_mode_strips_html_in_comments(self):
        data = {
            "type": "story",
            "title": "S",
            "children": [
                {
                    "type": "comment",
                    "author": "u",
                    "text": '<p>see <a href="x">link</a> &gt; quote</p>',
                    "children": [],
                }
            ],
        }
        out = format_hn_result(data)
        assert out["comments"][0]["text"] == "see link > quote"
