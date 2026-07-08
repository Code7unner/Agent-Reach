---
name: autoresearch
description: >
  Give your AI agent eyes to see the entire internet.
  Search and read 23 platforms: Twitter/X, Reddit, Hacker News, YouTube, GitHub, Bilibili,
  XiaoHongShu, Douyin, TikTok, Weibo, WeChat Articles, Xiaoyuzhou Podcast, LinkedIn,
  V2EX, Xueqiu, arXiv, Stack Overflow, Wikipedia, Semantic Scholar, PubMed,
  RSS, Exa web search, and any web page.
  Zero config for 8 channels. Use when the user asks to search, read, or interact
  on any supported platform, shares a URL, or asks to search the web.
  Triggers: "search twitter", "search xiaohongshu", "watch this video",
  "search the web", "look this up", "research", "youtube transcript",
  "search reddit", "hacker news", "hn", "ycombinator", "read this link", "bilibili", "douyin video",
  "wechat article", "wechat official account", "weibo", "V2EX",
  "xiaoyuzhou", "podcast", "xueqiu", "stock quote",
  "install autoresearch".
metadata:
  openclaw:
    homepage: https://github.com/Code7unner/autoresearch
---

# autoresearch — Usage Guide

Upstream tools for 23 platforms. Call them directly.

Run `autoresearch doctor` to check which channels are available.

## ⚠️ Workspace Rules

**Never create files in the agent workspace.** Use `/tmp/` for temporary output and `~/.autoresearch/` for persistent data.

## Web — Any URL

```bash
curl -s "https://r.jina.ai/URL"
```

## Web Search (Exa)

```bash
mcporter call 'exa.web_search_exa(query: "query", numResults: 5)'
mcporter call 'exa.get_code_context_exa(query: "code question", tokensNum: 3000)'
```

## Multi-source research (fan-out)

```bash
autoresearch research "your question" -n 5                  # fan out across the ACTIVE searchable channels
autoresearch research "your question" --channels hackernews,github,exa_search,twitter
```

Fans the query across searchable channels concurrently and returns grouped,
deduped JSON: `{query, results: {channel: [{source, title, url, snippet, date}]},
_meta: {channels_queried, channels_skipped, channels_unknown, errors}}`. Each channel
is queried through its own `search()` (single source of truth — the same upstream tool
used elsewhere), so result keys are channel names (`exa_search`, not `exa` — though
`--channels exa` is accepted as an alias).

- **Default** (no `--channels`): queries only the channels `doctor` reports active;
  searchable-but-inactive channels are listed in `_meta.channels_skipped` (not errored).
- **`--channels`**: runs exactly the names you give (active or not). Names that aren't
  searchable channels — a real but non-searchable channel like `reddit`, or a typo —
  are reported in `_meta.channels_unknown`.
- A slow/failed channel is recorded in `_meta.errors` and never blocks the others.
- Currently searchable: `hackernews`, `github`, `exa_search`, `twitter`, `reddit`
  (needs `rdt login`), `youtube`, `arxiv`, `stackoverflow`, `wikipedia`,
  `semanticscholar`, `pubmed`.

> Glue-only: `research` **gathers and dedupes** — it does NOT synthesize. You (the
> agent) read the cited JSON and write the answer. No LLM, no API key. Use this when
> the user wants to "research X", "see what people are saying about X", or compare
> sources across platforms.

## Twitter/X (twitter-cli)

```bash
twitter search "query" -n 10               # search
twitter tweet URL_OR_ID                    # read a tweet + its replies (the "thread")
twitter user-posts @username -n 20         # user timeline
twitter article URL_OR_ID                  # read a Twitter Article
```

> The installed binary is `twitter` (twitter-cli). Add `-c` for compact, LLM-friendly
> output, e.g. `twitter -c search "query" -n 10`. If you instead have the optional
> `bird` CLI (`@steipete/bird`), autoresearch also detects and uses it as a fallback.

## YouTube (yt-dlp)

```bash
yt-dlp --dump-json "URL"                     # video metadata
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --skip-download -o "/tmp/%(id)s" "URL"
                                             # download subtitles, then read the .vtt file
yt-dlp --dump-json "ytsearch5:query"         # search
```

## Bilibili (yt-dlp)

```bash
yt-dlp --dump-json "https://www.bilibili.com/video/BVxxx"
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --convert-subs vtt --skip-download -o "/tmp/%(id)s" "URL"
```

> Server IPs may get 412. Use `--cookies-from-browser chrome` or configure a proxy.

## Reddit

```bash
curl -s "https://www.reddit.com/r/SUBREDDIT/hot.json?limit=10" -H "User-Agent: autoresearch/1.0"
curl -s "https://www.reddit.com/search.json?q=QUERY&limit=10" -H "User-Agent: autoresearch/1.0"
```

> Server IPs may get 403. Search via Exa instead, or configure a proxy.

## Hacker News (public Algolia API)

```bash
# Search stories
curl -s "http://hn.algolia.com/api/v1/search?query=QUERY&tags=story" | autoresearch format hn
# Read a story + comment thread (item id from https://news.ycombinator.com/item?id=ID)
curl -s "http://hn.algolia.com/api/v1/items/ITEM_ID" | autoresearch format hn
```

> No auth required. `autoresearch format hn` strips noise and truncates huge
> threads (top 30 comments, depth ≤3) to keep token usage low.

## GitHub (gh CLI)

```bash
gh search repos "query" --sort stars --limit 10
gh repo view owner/repo
gh search code "query" --language python
gh issue list -R owner/repo --state open
gh issue view 123 -R owner/repo
```

## XiaoHongShu (mcporter)

```bash
mcporter call 'xiaohongshu.search_feeds(keyword: "query")'
mcporter call 'xiaohongshu.get_feed_detail(feed_id: "xxx", xsec_token: "yyy")'
mcporter call 'xiaohongshu.get_feed_detail(feed_id: "xxx", xsec_token: "yyy", load_all_comments: true)'
mcporter call 'xiaohongshu.publish_content(title: "Title", content: "Body text", images: ["/path/img.jpg"], tags: ["tag"])'
```

> Requires login. Use Cookie-Editor to import cookies.

> **Tip: Clean bloated output.** The XHS API returns large JSON with many unused fields.
> Pipe through the formatter to save context:
> ```bash
> mcporter call 'xiaohongshu.search_feeds(keyword: "query")' | autoresearch format xhs
> ```
> This keeps only: title, content, author, engagement counts, image URLs, and tags.

## Douyin (mcporter)

```bash
mcporter call 'douyin.parse_douyin_video_info(share_link: "https://v.douyin.com/xxx/")'
mcporter call 'douyin.get_douyin_download_link(share_link: "https://v.douyin.com/xxx/")'
```

> No login needed.

## TikTok (yt-dlp)

```bash
yt-dlp --dump-json "https://www.tiktok.com/@user/video/ID"   # video metadata
yt-dlp --write-sub --write-auto-sub --skip-download -o "/tmp/%(id)s" "URL"
                                                             # subtitles, then read the .vtt
yt-dlp --flat-playlist -J "https://www.tiktok.com/@username"  # a user's recent videos
```

> Read-only: yt-dlp has no working TikTok keyword search (`tiktok:tag` is broken
> upstream), so TikTok does not join `autoresearch research`. Share a video/profile
> URL and read it directly. Some videos are region-gated — configure a proxy or
> `--cookies-from-browser chrome` if a fetch fails.

## WeChat Articles

**Search** (`miku_ai`):
```bash
# miku_ai is installed inside the autoresearch Python environment.
# Use the same interpreter that runs autoresearch (handles pipx / venv installs):
AGENT_REACH_PYTHON=$(python3 -c "import autoresearch, sys; print(sys.executable)" 2>/dev/null || echo python3)
$AGENT_REACH_PYTHON -c "
import asyncio
from miku_ai import get_wexin_article
async def s():
    for a in await get_wexin_article('query', 5):
        print(f'{a[\"title\"]} | {a[\"url\"]}')
asyncio.run(s())
"
```

**Read** (Camoufox — bypasses WeChat anti-bot):
```bash
cd ~/.autoresearch/tools/wechat-article-for-ai && python3 main.py "https://mp.weixin.qq.com/s/ARTICLE_ID"
```

> WeChat articles cannot be read with Jina Reader or curl. Use Camoufox.

## Weibo (mcporter)

```bash
# Trending topics
mcporter call 'weibo.get_trendings(limit: 20)'

# Search users
mcporter call 'weibo.search_users(keyword: "Lei Jun", limit: 10)'

# Get a user profile
mcporter call 'weibo.get_profile(uid: "1195230310")'

# Get a user's feed
mcporter call 'weibo.get_feeds(uid: "1195230310", limit: 20)'

# Get a user's hot posts
mcporter call 'weibo.get_hot_feeds(uid: "1195230310", limit: 10)'

# Search post content
mcporter call 'weibo.search_content(keyword: "artificial intelligence", limit: 20)'

# Search topics
mcporter call 'weibo.search_topics(keyword: "AI", limit: 10)'

# Get post comments
mcporter call 'weibo.get_comments(mid: "5099916367123456", limit: 50)'

# Get fans
mcporter call 'weibo.get_fans(uid: "1195230310", limit: 20)'

# Get followings
mcporter call 'weibo.get_followers(uid: "1195230310", limit: 20)'
```

> Zero config. No login needed. Uses the mobile API with auto-generated visitor cookies.

## Xiaoyuzhou Podcast (groq-whisper + ffmpeg)

```bash
# Transcribe a single podcast episode (outputs text to /tmp/)
~/.autoresearch/tools/xiaoyuzhou/transcribe.sh "https://www.xiaoyuzhoufm.com/episode/EPISODE_ID"
```

> Requires `ffmpeg` and a Groq API key (free).
> Configure the key with `autoresearch configure groq-key YOUR_KEY`.
> On first run, install the tools with `autoresearch install --env=auto`.
> Run `autoresearch doctor` to check status.
> Output Markdown files are saved to `/tmp/` by default.

## LinkedIn (mcporter)

```bash
mcporter call 'linkedin.get_person_profile(linkedin_url: "https://linkedin.com/in/username")'
mcporter call 'linkedin.search_people(keyword: "AI engineer", limit: 10)'
```

Fallback: `curl -s "https://r.jina.ai/https://linkedin.com/in/username"`

## V2EX (public API)

```bash
# Hot topics
curl -s "https://www.v2ex.com/api/topics/hot.json" -H "User-Agent: autoresearch/1.0"

# Topics in a node (node_name examples: python, tech, jobs, qna)
curl -s "https://www.v2ex.com/api/topics/show.json?node_name=python&page=1" -H "User-Agent: autoresearch/1.0"

# Topic details (extract topic_id from URLs like https://www.v2ex.com/t/1234567)
curl -s "https://www.v2ex.com/api/topics/show.json?id=TOPIC_ID" -H "User-Agent: autoresearch/1.0"

# Topic replies
curl -s "https://www.v2ex.com/api/replies/show.json?topic_id=TOPIC_ID&page=1" -H "User-Agent: autoresearch/1.0"

# User profile
curl -s "https://www.v2ex.com/api/members/show.json?username=USERNAME" -H "User-Agent: autoresearch/1.0"
```

Python example (`V2EXChannel`):

```python
from autoresearch.channels.v2ex import V2EXChannel

ch = V2EXChannel()

# Get hot topics (default 20 items)
# Returned fields: id, title, url, replies, node_name, node_title, content(first 200 chars), created
topics = ch.get_hot_topics(limit=10)
for t in topics:
    print(f"[{t['node_title']}] {t['title']} ({t['replies']} replies) {t['url']}")
    print(f"  id={t['id']} created={t['created']}")

# Get latest topics for a specific node
# Returned fields: id, title, url, replies, node_name, node_title, content(first 200 chars), created
node_topics = ch.get_node_topics("python", limit=5)
for t in node_topics:
    print(t["id"], t["title"], t["url"])

# Get one topic plus replies
# Returned fields: id, title, url, content, replies_count, node_name, node_title,
#                  author, created, replies (list of {author, content, created})
topic = ch.get_topic(1234567)
print(topic["title"], "—", topic["author"])
for r in topic["replies"]:
    print(f"  {r['author']}: {r['content'][:80]}")

# Get user info
# Returned fields: id, username, url, website, twitter, psn, github, btc, location, bio, avatar, created
user = ch.get_user("Livid")
print(user["username"], user["bio"], user["github"])

# Search (not supported by the public V2EX API; returns guidance instead)
result = ch.search("asyncio")
print(result[0]["error"])  # Use built-in site search or the Exa channel instead
```

> No auth required. Results are public JSON. V2EX node names are listed at https://www.v2ex.com/planes

## Xueqiu (public API)

```python
from autoresearch.channels.xueqiu import XueqiuChannel

ch = XueqiuChannel()

# Get stock quotes (symbol examples: SH600519 mainland China, SZ000858 Shenzhen, AAPL US, 00700 HK)
# Returned fields: symbol, name, current, percent, chg, high, low, open, last_close,
#                  volume, amount, market_capital, turnover_rate, pe_ttm, timestamp
quote = ch.get_stock_quote("AAPL")
print(f"{quote['name']} ({quote['symbol']}): {quote['current']} ({quote['percent']}%)")

# Search stocks
# Returned fields: symbol, name, exchange
stocks = ch.search_stock("Apple", limit=5)
for s in stocks:
    print(f"{s['name']} ({s['symbol']}) - {s['exchange']}")

# Hot posts
# Returned fields: id, title, text(first 200 chars), author, likes, url
posts = ch.get_hot_posts(limit=10)
for p in posts:
    print(f"{p['author']}: {p['text'][:50]}... ({p['likes']} likes)")

# Hot stocks (stock_type=10 popularity ranking, stock_type=12 watchlist ranking)
# Returned fields: symbol, name, current, percent, rank
hot = ch.get_hot_stocks(limit=10, stock_type=10)
for s in hot:
    print(f"#{s['rank']} {s['name']} ({s['symbol']}): {s['current']} ({s['percent']}%)")
```

> No login required. autoresearch auto-fetches session cookies, and all public APIs can be used directly.

## RSS (feedparser)

```python
python3 -c "
import feedparser
for e in feedparser.parse('FEED_URL').entries[:5]:
    print(f'{e.title} — {e.link}')
"
```

## Troubleshooting

- **Channel not working?** Run `autoresearch doctor` — it shows status and fix instructions. Add `--fix` (`autoresearch doctor --fix`) to auto-apply the fixable ones (yt-dlp JS runtime, Exa/mcporter entry, config-file permissions); anything needing a new install or your credentials is left as a manual hint.
- **Session expired silently?** `doctor` probes session channels (Twitter, LinkedIn, XiaoHongShu, etc.) for liveness and lists any configured-but-dead session under "⚠ Needs attention — re-authenticate". Use `autoresearch doctor --offline` to skip the network probes and report install/config status only (fast, offline).
- **Twitter fetch failed?** Ensure `undici` is installed: `npm install -g undici`. Configure a proxy if needed: `autoresearch configure proxy URL`.

## Setting Up a Channel ("help me configure XXX")

If a channel needs setup (cookies, Docker, etc.), fetch the install guide:
https://raw.githubusercontent.com/Code7unner/autoresearch/main/docs/install.md

The user only provides cookies. Everything else is your job.
