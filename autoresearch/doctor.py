# -*- coding: utf-8 -*-
"""Environment health checker — powered by channels.

Each channel knows how to check itself. Doctor just collects the results.
"""

from typing import Dict, List
from autoresearch.config import Config
from autoresearch.channels import get_all_channels


def check_all(config: Config, offline: bool = False) -> Dict[str, dict]:
    """Check all channels and return status dict.

    When ``offline`` is True, channels skip any network liveness probe and report
    install/config status only (used by ``doctor --offline``).
    """
    results = {}
    for ch in get_all_channels():
        status, message = ch.check(config, offline=offline)
        results[ch.name] = {
            "status": status,
            "name": ch.description,
            "message": message,
            "tier": ch.tier,
            "backends": ch.backends,
        }
    return results


def run_fixes(config: Config) -> List[dict]:
    """Apply the auto-fixable setup steps for any channel that isn't ``ok``.

    Each non-ok channel's ``fix(config)`` is invoked; ``ok`` channels are left
    alone. Plus an environment-level fix: tighten over-permissive ``config.yaml``.
    Returns a list of ``{channel, changed, message}`` outcomes, omitting silent
    no-ops (``changed=False`` and empty message) so the report stays uncluttered.
    """
    outcomes: List[dict] = []
    for ch in get_all_channels():
        status, _ = ch.check(config)
        if status == "ok":
            continue
        changed, message = ch.fix(config)
        if changed or message:
            outcomes.append({"channel": ch.name, "changed": changed, "message": message})

    perm = _fix_config_permissions(config)
    if perm:
        outcomes.append(perm)
    return outcomes


def _fix_config_permissions(config: Config):
    """chmod the config file to 0600 if it is group/other accessible (POSIX only)."""
    import os
    import stat
    import sys

    if sys.platform == "win32":
        return None
    path = getattr(config, "config_path", None) or Config.CONFIG_FILE
    try:
        if not path.exists():
            return None
        mode = path.stat().st_mode
        if mode & (stat.S_IRGRP | stat.S_IROTH | stat.S_IWGRP | stat.S_IWOTH):
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
            return {"channel": "config", "changed": True,
                    "message": f"tightened {path} permissions to 0600"}
    except OSError:
        return None
    return None


def format_report(results: Dict[str, dict]) -> str:
    """Format results as a readable text report (with Rich markup)."""
    try:
        from rich.markup import escape
    except ImportError:
        escape = lambda x: x

    lines = []
    lines.append("[bold cyan]autoresearch status[/bold cyan]")
    lines.append("[cyan]" + "=" * 40 + "[/cyan]")

    ok_count = sum(1 for r in results.values() if r["status"] == "ok")
    total = len(results)

    # Tier 0 — zero config
    lines.append("")
    lines.append("[bold]✅ Ready to use:[/bold]")
    for key, r in results.items():
        if r["tier"] == 0:
            name_msg = f"[bold]{escape(r['name'])}[/bold] — {escape(r['message'])}"
            if r["status"] == "ok":
                lines.append(f"  [green]✅[/green] {name_msg}")
            elif r["status"] == "warn":
                lines.append(f"  [yellow][!][/yellow]  {name_msg}")
            elif r["status"] in ("off", "error"):
                lines.append(f"  [red][X][/red]  {name_msg}")

    # Tier 1 — needs free key / login
    tier1 = {k: r for k, r in results.items() if r["tier"] == 1}
    tier1_active = {k: r for k, r in tier1.items() if r["status"] == "ok"}
    tier1_inactive = {k: r for k, r in tier1.items() if r["status"] != "ok"}
    if tier1_active:
        lines.append("")
        lines.append("[bold]Optional channels (installed):[/bold]")
        for key, r in tier1_active.items():
            name_msg = f"[bold]{escape(r['name'])}[/bold] — {escape(r['message'])}"
            lines.append(f"  [green]✅[/green] {name_msg}")

    # Tier 2 — optional complex setup
    tier2 = {k: r for k, r in results.items() if r["tier"] == 2}
    tier2_active = {k: r for k, r in tier2.items() if r["status"] == "ok"}
    tier2_inactive = {k: r for k, r in tier2.items() if r["status"] != "ok"}
    if tier2_active:
        if not tier1_active:
            lines.append("")
            lines.append("[bold]Optional channels (installed):[/bold]")
        for key, r in tier2_active.items():
            name_msg = f"[bold]{escape(r['name'])}[/bold] — {escape(r['message'])}"
            lines.append(f"  [green]✅[/green] {name_msg}")

    lines.append("")
    status_color = "green" if ok_count == total else ("yellow" if ok_count > 0 else "red")
    lines.append(f"Status: [{status_color}]{ok_count}/{total}[/{status_color}] channels available")

    # Split inactive optional channels: `warn` = configured but the live probe
    # failed (a session that silently expired — surface it loudly for re-auth);
    # `off` = the tool/credentials are absent (offer to unlock).
    all_inactive = list(tier1_inactive.values()) + list(tier2_inactive.values())
    needs_attention = [r for r in all_inactive if r["status"] != "off"]
    can_unlock = [r for r in all_inactive if r["status"] == "off"]

    if needs_attention:
        lines.append("")
        lines.append("[bold yellow]⚠ Needs attention — re-authenticate:[/bold yellow]")
        for r in needs_attention:
            lines.append(f"  [yellow][!][/yellow]  [bold]{escape(r['name'])}[/bold] — {escape(r['message'])}")

    if can_unlock:
        names = [r["name"] for r in can_unlock]
        lines.append(
            f"There are {len(names)} more optional channels you can unlock "
            f"({', '.join(names)}); just tell your Agent \"install XXX for me\""
        )

    # Security check: config file permissions (Unix only)
    import os
    import stat
    import sys

    config_path = Config.CONFIG_DIR / "config.yaml"
    if config_path.exists() and sys.platform != "win32":
        try:
            mode = config_path.stat().st_mode
            if mode & (stat.S_IRGRP | stat.S_IROTH):
                lines.append("")
                lines.append(
                    "[bold red][!]  Security warning: config.yaml permissions are too open (readable by other users)[/bold red]"
                )
                lines.append("   Fix: chmod 600 ~/.autoresearch/config.yaml")
        except OSError:
            pass

    return "\n".join(lines)
