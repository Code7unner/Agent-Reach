# autoresearch — improvement session

## Context
You're working on `autoresearch` (repo: github.com/Code7unner/autoresearch), a Python
CLI + skill + library that gives AI agents read/search access to 17 internet platforms
(Twitter/X, Reddit, HN, YouTube, GitHub, Bilibili, XHS, Douyin, Weibo, WeChat,
Xiaoyuzhou, LinkedIn, V2EX, Xueqiu, RSS, Exa web search, any web page). It's a
"glue layer" / installer + doctor + router — it calls upstream tools directly, never
reimplements or modifies them. Read CLAUDE.md first; it is authoritative.

## Current state
- Version 1.0.2. ~195 tests pass (`pytest tests/ -v`). 22 channels registered.
- The project was rebranded from "Agent Reach" to "autoresearch" (CLI command,
  package `autoresearch/`, class `AutoResearch`). Rebrand is merged to main.
- Active channels depend on the machine — run `autoresearch doctor` to see status.
  On the dev machine these were active: GitHub, Twitter/X, LinkedIn, HN, V2EX, RSS,
  Exa, Web (Jina), WeChat.
- `research` fans out across up to 11 searchable channels (hackernews, github,
  exa_search, twitter, reddit, youtube, arxiv, stackoverflow, wikipedia,
  semanticscholar, pubmed), all via `Channel.search()`.

## Done (do not redo)
- **#1 `research` command** — multi-source fan-out + dedupe, grouped cited JSON. (PR #9)
  - All 6 code-review follow-ups also landed (PR #10): active-channel resolution,
    unknown-channel reporting, `_meta.channels_skipped`/`channels_unknown`,
    `--limit`/`--timeout` validation, `normalize_url` scheme detection, HN adapter
    routed through `HackerNewsChannel.search_stories`.
- **#6 Secrets via stdin/file** — `configure --stdin` / `--file PATH`, argv warning. (PR #11)
- **#7 Release + CI** — already in place: GitHub Release `v1.0.1` (check-update no longer
  404s) and `.github/workflows/pytest.yml` runs pytest on PRs.
- **#3 `doctor --fix`** — auto-applies yt-dlp JS-runtime config, Exa/mcporter entry, and
  config.yaml `chmod 0600`; manual hints for non-auto-fixable cases. New
  `Channel.fix(config) -> (changed, message)` mirrors `check()`. (PR #12)
- **#9 Expand `research` connectors** — unified `Channel.search()` contract; migrated the
  original 4 onto it (PR #15, closes follow-up #6); added Reddit + YouTube (PR #16),
  arXiv + Stack Overflow (PR #17), and Wikipedia + Semantic Scholar + PubMed (PR #19).
  Now up to 11 searchable channels. V2EX dropped (its API has no search endpoint —
  `search()` is a documented stub).
  - Known limitation: keyless **Semantic Scholar** is heavily 429-rate-limited (retries
    once, then degrades gracefully). Optional follow-on: wire a free `S2_API_KEY`
    (env/config) to make it reliable.

- **#4 Session/cookie health checks in doctor** — every session channel now does a
  real live/dead probe with a standardized status vocabulary (`off` = tool/creds
  absent, `warn` = configured-but-dead → re-auth, `ok` = live). LinkedIn gained a real
  liveness probe (`mcporter list linkedin`) instead of a bare config-entry grep; Twitter
  "not installed" fixed `warn`→`off`. `format_report` now surfaces dead sessions in a
  prominent "⚠ Needs attention — re-authenticate" block instead of burying them in the
  "unlock more channels" line. New `doctor --offline` flag skips network probes
  (`Channel.check(config, offline=False)` contract; offline → install/config status
  only). Design: docs/design/session-health-checks.md. (this session)
  - "Expiring soon" early-warning was explicitly de-scoped (liveness only).

## Hard rules (from CLAUDE.md — do not violate)
- NEVER modify upstream open-source projects. autoresearch only routes/calls.
- External upstream deps owned by "Panniantong" (mcp-server-weibo, wechat-article-for-ai)
  MUST stay as-is — they are real third-party tools, not the old repo owner. Do not
  "rebrand" or repoint them.
- Always a new branch, PR to main, never push to main directly.
- TDD: write a failing test first, then implement. Run `pytest tests/ -v` before commits.
- Version must match in 3 places: pyproject.toml, autoresearch/__init__.py,
  tests/test_cli.py — there's a guard test in tests/test_doc_consistency.py.
- There are doc<->code consistency tests (tests/test_doc_consistency.py); keep them green.

## Remaining hypotheses (brainstorm first, don't just build)
2. **First-class MCP server.** `autoresearch/integrations/mcp_server.py` exists but is
   thin. Expose 2-3 well-scoped tools (search/read/research) following MCP best
   practices: bundle workflows, sensible defaults, concrete examples, minimal tool
   count. Refs: AWS "MCP strategies" guide; Jfokus "MCP Servers Beyond 101".
   (Largest remaining item — design scope with the brainstorming skill first.)
5. **Fetch-layer robustness** — unified retry/backoff + anti-bot/proxy fallbacks shared
   across channels. Refs: DEV "Reliable Web-Connected AI Agents Start at the Fetch
   Layer"; "Rate Limits & Anti-Bots in Agentic Scraping".
8. **Bilingual docs** — docs/install.md is half-Chinese; split or localize for English
   users. (Smallest remaining item — good quick win.)

## Suggested starting point
Remaining: **#5 fetch-layer robustness**, **#2 MCP server** (largest — brainstorm tool
shape first), **#8 bilingual docs** (quick win). Confirm direction with the user.

> The #9 research-connector expansion is complete — now up to 11 searchable channels
> (see "Done" above). Possible #9 follow-ons if desired: an `S2_API_KEY` for reliable
> Semantic Scholar; more connectors (Weibo/XHS/Bilibili for China-focused research; npm;
> note PyPI has no public search API); or read-by-URL support for the new search-only
> channels (arXiv, Stack Overflow, Wikipedia, Semantic Scholar, PubMed).
