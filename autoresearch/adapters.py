# -*- coding: utf-8 -*-
"""Resolution layer for the `research` fan-out.

`research` routes through each channel's own ``Channel.search(query, limit)`` -
the single source of truth (channels wrap the upstream tools; autoresearch only
routes, never reimplements). This module decides WHICH channels run for a given
request, given doctor-reported activity and the requested ``--channels`` list.
The per-channel search/normalization logic lives in ``autoresearch/channels/``.
"""

# `--channels` input aliases -> real channel name (so `exa` still resolves to the
# `exa_search` channel). Output keys are always the channel name.
_CHANNEL_ALIASES = {"exa": "exa_search"}


def _to_channel_name(name: str) -> str:
    return _CHANNEL_ALIASES.get(name, name)


def plan_research_channels(requested, active, searchable, known):
    """Decide which channels to query, skip, or flag - given plain name sets.

    Pure (no doctor/Config dependency) so it is unit-testable offline.

    Args:
        requested: explicit ``--channels`` list, or ``None`` for the default run.
        active:    channel names usable right now (doctor status "ok").
        searchable: channel names that expose a search adapter (``ch.searchable``).
        known:     every registered channel name (searchable or not).

    Returns ``(run, skipped, unknown)``, each a sorted list:
        run:     channels to actually query.
        skipped: searchable channels skipped because inactive (default run only).
        unknown: requested names that are not searchable channels - covers both
                 real-but-not-searchable (e.g. ``reddit``) and outright typos.
    """
    searchable, active = set(searchable), set(active)
    if requested is None:
        # Default = active searchable channels; the rest are skipped, not errored.
        run = searchable & active
        return sorted(run), sorted(searchable - active), []
    # Explicit request overrides the active filter: the user asked for these by name,
    # so run them even if doctor thinks they're inactive and let any real error surface.
    run, unknown = set(), set()
    for name in requested:
        (run if name in searchable else unknown).add(name)
    return sorted(run), [], sorted(unknown)


def resolve_research(channels=None):
    """Doctor-aware resolution of a research run into ``(adapters, skipped, unknown)``.

    Builds the adapter map from the searchable channels' own ``search`` methods,
    then probes channel health via ``doctor.check_all`` so a default run targets only
    *active* channels (the locked design) and surfaces inactive/unknown names instead
    of letting them fail with cryptic per-channel errors.
    """
    from autoresearch.channels import get_all_channels
    from autoresearch.config import Config
    from autoresearch.doctor import check_all

    by_name = {ch.name: ch for ch in get_all_channels()}
    searchable = {name for name, ch in by_name.items() if getattr(ch, "searchable", False)}
    requested = [_to_channel_name(c) for c in channels] if channels else None

    if requested is None:
        # Default run: we need the active set to drop inactive channels. Use the offline
        # doctor (install/config status, not full network liveness) - a configured-but-
        # dead session then surfaces as a per-channel error in the fan-out, not a silent
        # skip. offline=True alone cuts 20s+ of per-call liveness probing.
        results = check_all(Config(), offline=True)
        active = {n for n, r in results.items() if r.get("status") == "ok"}
        known = set(results) | set(by_name)
    else:
        # Explicit --channels: plan_research_channels ignores `active` entirely (it runs
        # exactly what was asked), so probing doctor here is pure overhead. Skip it and
        # let any genuinely broken channel report its own error inside the fan-out.
        active = set()
        known = set(by_name)

    run, skipped, unknown = plan_research_channels(requested, active, searchable, known)
    adapters = {name: by_name[name].search for name in run}
    return adapters, skipped, unknown
