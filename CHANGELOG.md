# Changelog

All notable changes to this project will be documented in this file.

---

## [Unreleased]

### ✨ Features

- **New channel: TikTok (read-only).** Reads TikTok video metadata + subtitles and a
  user's video list via yt-dlp (`channels/tiktok.py`), bringing the registered total to
  23. It is intentionally not `searchable` — yt-dlp has no working TikTok keyword search
  (`tiktok:tag` is broken upstream) — so it does not join the `research` fan-out; agents
  read a shared URL directly. Documented in SKILL.md.

### 🐛 Bug Fixes — Reddit channel

- **Fixed an unsatisfiable install hint.** The Reddit channel told users to
  `pip install 'rdt-cli>=0.4.2'`, but PyPI's latest is `0.4.1`, so the command failed
  outright. The hint now recommends `pip install rdt-cli` (0.4.1 works for search/status)
  and points at the source repo for newer builds; a guard test prevents the pin returning.
- **More debuggable status-check failures.** When `rdt status --json` can't be parsed the
  channel now reports the failure kind and suggests retrying (transient post-install
  hiccups previously surfaced as an opaque "status check failed").

### 🐛 Bug Fixes — `research` fan-out reliability

- **`research` no longer runs a slow network doctor on every call.** Resolution now
  skips the doctor probe entirely for explicit `--channels` requests (the active set is
  unused there) and uses the offline doctor for default runs. An explicit-channel
  `research` call dropped from ~19.5s to ~4.5s.
- **Zero-result channels are reported, not silently dropped.** `_meta` now carries
  `result_counts` (per-channel row counts, including zeros) and `channels_empty`, so a
  keyword channel that legitimately returns nothing for a long natural-language query is
  distinguishable from one that errored or was dropped.
- **Flaky `twitter` searches now retry.** `twitter.search` routes through a new
  `utils.proc.run_with_retry` (retries on nonzero exit / timeout / OS error with linear
  backoff), turning transient twitter-cli failures into results instead of empty slots.
- **Fan-out deadline no longer cuts valid slow channels.** The outer `run_research`
  timeout defaulted to 20s while per-channel search subprocesses run up to ~45s, so a
  valid-but-slow channel got killed and mislabeled `TimeoutError`. The default outer
  deadline is now 45s (>= the slowest per-channel budget).
- **`offline=True` now actually skips network probes in the public-API channels.**
  HackerNews, arXiv, Stack Overflow, Wikipedia, PubMed, Semantic Scholar, V2EX, GitHub,
  and Bilibili previously accepted the `offline` flag but still hit the network in
  `check()`. They now report install/config status only when offline. `doctor --offline`
  and default `research` resolution drop from ~16s to ~0.5s.

---

## [1.3.1] - 2026-03-27

### 🐛 Bug Fixes

#### 📈 Xueqiu — Comprehensive fix

- **Fixed the root cause of the 400 error:** `_ensure_cookies()` only visited the homepage, which can only obtain `acw_tc` (an anti-DDoS token). `xq_a_token` is generated dynamically by Xueqiu's frontend JS and cannot be obtained through a pure HTTP request. Added a three-tier cookie loading strategy: (1) read from the config file (saved via `--from-browser`) → (2) automatically extract from the local Chrome browser (requires browser-cookie3) → (3) homepage fallback
- **Fixed the User-Agent:** `"autoresearch/1.0"` was detected and rejected by Xueqiu's anti-scraping system; changed to a real Chrome UA
- **Fixed the missing `Referer` header:** all API requests now include `Referer: https://xueqiu.com/`
- **Fixed the `get_hot_posts()` endpoint:** the original endpoint `/statuses/hot/listV3.json` is deprecated (returns an empty body); switched to `/v4/statuses/public_timeline_by_category.json` and correctly parse the `item.data` JSON string to extract author/likes/text
- **Fixed `urllib.request.quote` → `urllib.parse.quote`:** explicitly use the correct module
- **Fixed `configure --from-browser` not extracting Xueqiu cookies:** added Xueqiu to `PLATFORM_SPECS`, saving only when `xq_a_token` is detected
- **Corrected misleading documentation:** "no configuration required"/"public API, no login required" in README/SKILL.md → now accurately describes that a browser cookie is needed
- **Improved error messages:** when `check()` fails it now suggests `configure --from-browser chrome` instead of "a proxy may be needed"

---

## [1.3.0] - 2026-03-12

### 🆕 New Channels

#### 💻 V2EX
- Hot topics, node topics, topic detail + replies, user profile via public JSON API
- Zero config — no auth, no proxy, no API key required
- `get_hot_topics(limit)`, `get_node_topics(node_name, limit)`, `get_topic(id)`, `get_user(username)`

### 📈 Improvements

- Channel count: 14 → 15

---

## [1.1.0] - 2025-02-25

### 🆕 New Channels

#### ~~📷 Instagram~~ (removed — upstream blocked)
- ~~Read public posts and profiles via [instaloader](https://github.com/instaloader/instaloader)~~
- **Removed:** Instagram's aggressive anti-scraping measures broke all available open-source tools (instaloader, etc.). See [instaloader#2585](https://github.com/instaloader/instaloader/issues/2585). Will re-add when upstream recovers.

#### 💼 LinkedIn
- Read person profiles, company pages, and job details via [linkedin-scraper-mcp](https://github.com/stickerdaniel/linkedin-mcp-server)
- Search people and jobs via MCP, with Exa fallback
- Fallback to Jina Reader when MCP is not configured

#### 🏢 Boss Zhipin
- QR code login via [mcp-bosszp](https://github.com/mucsbr/mcp-bosszp)
- Job search and recruiter greeting via MCP
- Fallback to Jina Reader for reading job pages

### 📈 Improvements

- Channel count: 9 → 12
- `autoresearch doctor` now detects all 12 channels
- CLI: added `search-linkedin`, `search-bosszhipin` subcommands
- Updated install guide with setup instructions for new channels

---

## [1.0.0] - 2025-02-24

### 🎉 Initial Release

- 9 channels: Web, Twitter/X, YouTube, Bilibili, GitHub, Reddit, XiaoHongShu, RSS, Exa Search
- CLI with `read`, `search`, `doctor`, `install` commands
- Unified channel interface — each platform is a single pluggable Python file
- Auto-detection of local vs server environments
- Built-in diagnostics via `autoresearch doctor`
- Skill registration for Claude Code / OpenClaw / Cursor
