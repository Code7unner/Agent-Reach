# Design — Session/cookie health checks in `doctor` (hypothesis #4)

Status: accepted (brainstorming complete) · 2026-06-22

## Understanding summary

- **What:** Make `autoresearch doctor` reliably distinguish a *live* session from a
  *silently-dead* one for every session/cookie channel, and surface dead sessions
  prominently instead of burying them in the "unlock more channels" line.
- **Why:** Twitter/LinkedIn/XHS sessions expire silently. Today doctor reports
  "configured/installed" even when the session is dead, so `research` fails mid-run
  with no warning.
- **Who:** Agents/users running `doctor` to know what is actually usable right now.
- **In scope:** Uniform live/dead probing in `check()` for the channels that lack it
  (LinkedIn, weibo, douyin, xueqiu — Twitter & XHS already probe); consistent status
  semantics; a `doctor --offline` flag to skip network probes; report surfaces
  dead-but-configured sessions distinctly.
- **Non-goals:** Cookie-expiry "expiring soon" early-warning (explicitly dropped). No
  auto-re-auth. No new network dependencies. No upstream tool modifications.

## Status vocabulary (reuse existing 4-value enum, no new status)

- `ok`   — installed/configured **and** the live probe succeeded.
- `warn` — installed/configured but the session is **dead or the probe failed**
  (actionable: re-authenticate).
- `off`  — the upstream tool or its credentials are **absent**.
- `error`— unchanged (unexpected failure).

This requires small semantic cleanups where a channel currently mislabels (e.g. Twitter
returns `warn` for "CLI not installed" — should be `off`).

## Design

### §1 Channel layer (probes)
Standardize each session channel's `check(config, offline=False)` to the vocabulary above.
- **LinkedIn**: add a cheap MCP liveness probe (lightweight tool call via `mcporter`,
  short timeout). Configured-but-dead → `warn` + re-login hint; not configured → `off`.
- **weibo / douyin**: after confirming the MCP entry exists, do a cheap tool-list/ping;
  tools present → `ok`, entry-but-unreachable → `warn`.
- **xueqiu** (cookie-only): tighten so an authed probe distinguishes valid cookie (`ok`)
  from missing/invalid (`warn`/`off`).
- **Twitter**: keep `twitter status` probe but fix "CLI not installed" branch → `off`.
- **XHS**: already correct — leave as-is.
All probes honor `offline` and use a short timeout so doctor never hangs.

### §2 Doctor / report layer
`check_all` unchanged in shape. `format_report` splits the lumped "inactive" group:
- `off` → existing **"unlock more"** summary line.
- `warn` → new prominent **"⚠ Needs attention — re-authenticate"** block listing each
  channel + its hint. This makes silent expiry loud.
`run_fixes` already calls `fix()` on non-`ok` channels; ensure relevant channels' `fix()`
returns a useful re-auth manual hint.

### §3 `--offline` flag & plumbing
- `cli.py`: add `--offline` to `doctor` subparser → `_cmd_doctor(fix, offline)` →
  `check_all(config, offline=offline)`.
- `check_all(config, offline=False)` forwards to `ch.check(config, offline=offline)`.
- Contract change: `Channel.check(self, config=None, offline=False)`. Default keeps
  existing overrides working; network-probing channels short-circuit when `offline`.
- Update `test_doctor.py` stub + channel-contract test for the new optional param.

### Edge cases
Probe timeout → `warn` ("probe timed out"), never a hang. CLI/mcporter missing mid-probe
→ `off`. `--offline` never touches the network.

### Testing strategy (TDD, failing test first)
1. `format_report` splits warn vs off into the two sections.
2. `check_all` forwards `offline`.
3. Each updated channel: live/dead/absent/offline statuses (subprocess & mcporter mocked).
4. CLI `--offline` wiring.
Keep existing doc-consistency/contract tests green.

## Decision log

| Decision | Alternatives | Why |
|---|---|---|
| Liveness only; drop "expiring soon" | Best-effort expiry from extracted cookies; probe-based inference | User chose liveness-only; expiry is an upper-bound at best and adds capture/persist complexity. |
| Probe inside `check()`, opt-out via `--offline` | New `probe()` method + `--probe` opt-in; always-on no flag | Matches today's Twitter/XHS pattern; smallest change; keeps a fast/offline escape hatch. |
| Reuse `warn` (no new status) | New `expired` status value | Less ripple through `format_report`/`run_fixes`/tests; `warn`/`off` semantics already fit. |
| Split report: warn="needs attention", off="unlock" | Keep single lumped inactive line | The lumped line hid dead sessions as "unlock more" — the exact silent-failure #4 targets. |
| Flag name `--offline` | `--quick` | Says what it does (skip network). |
