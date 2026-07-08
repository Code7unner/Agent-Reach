# -*- coding: utf-8 -*-
"""PubMed — biomedical literature search via NCBI E-utilities (no auth).

Two-step: esearch returns PMIDs, esummary returns their metadata. NCBI asks for
modest request rates (≤3/s without a key); fine for interactive research."""

import urllib.parse

from autoresearch.utils.http import get_json

from .base import Channel

_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


class PubMedChannel(Channel):
    name = "pubmed"
    description = "PubMed biomedical literature"
    backends = ["NCBI E-utilities (public)"]
    tier = 0
    searchable = True

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        return "pubmed.ncbi.nlm.nih.gov" in urlparse(url).netloc.lower()

    def check(self, config=None, offline: bool = False):
        if offline:
            return "ok", "Public API, zero-config (--offline: API not probed)"
        try:
            get_json(f"{_ESEARCH}?{urllib.parse.urlencode({'db': 'pubmed', 'term': 'test', 'retmax': 1, 'retmode': 'json'})}", timeout=8)
            return "ok", "Public API available (literature search, no key required)"
        except Exception as e:
            return "warn", f"NCBI E-utilities connection failed: {e}"

    def search(self, query: str, limit: int = 5) -> list:
        """research rows from PubMed (esearch → esummary)."""
        eq = urllib.parse.urlencode({
            "db": "pubmed", "term": query, "retmax": int(limit), "retmode": "json",
        })
        ids = (get_json(f"{_ESEARCH}?{eq}")
               .get("esearchresult", {}).get("idlist") or [])[:limit]
        if not ids:
            return []
        sq = urllib.parse.urlencode({
            "db": "pubmed", "id": ",".join(ids), "retmode": "json",
        })
        result = get_json(f"{_ESUMMARY}?{sq}").get("result", {})
        rows = []
        for uid in ids:  # preserve relevance order from esearch
            r = result.get(uid)
            if not isinstance(r, dict):
                continue
            source = r.get("fulljournalname") or r.get("source") or ""
            authors = ", ".join(a.get("name", "") for a in (r.get("authors") or [])[:3])
            snippet = " · ".join(p for p in (source, authors) if p)
            pubdate = (r.get("sortpubdate") or "")[:10].replace("/", "-")
            rows.append({
                "source": "pubmed",
                "title": r.get("title") or "",
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
                "snippet": snippet[:280],
                "date": pubdate,
            })
        return rows
