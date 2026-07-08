# -*- coding: utf-8 -*-
"""Small subprocess helpers shared by channel search adapters."""

import subprocess
import time


def raise_on_error(out, tool: str) -> None:
    """Raise on a nonzero CLI exit so a `research` fan-out reports an honest
    per-channel error instead of a silent empty result (e.g. `gh` not
    authenticated). ``out`` is a completed ``subprocess.run`` result."""
    if out.returncode != 0:
        msg = (out.stderr or out.stdout or "").strip()[:200]
        raise RuntimeError(
            f"{tool} exited {out.returncode}: {msg}" if msg
            else f"{tool} exited {out.returncode}"
        )


def run_with_retry(cmd, tool: str, *, retries: int = 1, backoff: float = 0.5,
                   _sleep=time.sleep, **kwargs):
    """Run ``subprocess.run(cmd, **kwargs)`` then ``raise_on_error``, retrying
    transient failures.

    CLI search adapters (twitter-cli, gh) intermittently fail on a flaky network
    or a cold upstream session; one or two quick retries turn a spurious
    per-channel error into a result instead of an empty fan-out slot. Retries on
    a nonzero exit, ``TimeoutExpired``, or ``OSError`` up to ``retries`` times with
    linear backoff, then re-raises the last failure so the orchestrator still
    records an honest error. Returns the completed process on success.
    """
    last_exc = None
    for attempt in range(retries + 1):
        try:
            out = subprocess.run(cmd, **kwargs)
            raise_on_error(out, tool)
            return out
        except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
            last_exc = exc
            if attempt < retries:
                _sleep(backoff * (attempt + 1))
    raise last_exc
