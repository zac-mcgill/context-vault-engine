"""
Missing concepts adapter — coverage gap detection for MCP.

Delegates directly to core.shared.discover_missing.  No business logic.
"""

from __future__ import annotations

from mcp.core.schema_loader import load_schema as _load_schema
from mcp.core.vault_registry import get_vault_path, list_vaults
from mcp.core.result_cache import get_cached, set_cached
from core.shared.discover_missing import (
    build_subdomain_to_domain,
    load_actual_concepts,
    detect_gaps,
    score_gaps,
)

_ENDPOINT = "missing"


def get_missing(vault_name: str | None = None) -> dict:
    """Detect missing concepts and return structured results.

    Returns:
        {
            "total_expected": int,
            "total_actual": int,
            "total_missing": int,
            "domains_assessed": int,
            "subdomains": int,
            "gaps": {
                "<subdomain>": [{"concept": str, "score": float}]
            },
            "ranked": [
                {"rank": int, "score": float, "subdomain": str, "concept": str}
            ]
        }
    """
    try:
        if vault_name is None:
            vaults = list_vaults()
            if not vaults:
                return {"error": "No vaults registered"}
            vault_name = vaults[0]

        cached = get_cached(vault_name, _ENDPOINT)
        if cached is not None:
            return cached

        vault_path = get_vault_path(vault_name)
        _schema = _load_schema(vault_path)

        if not _schema.EXPECTED_CONCEPTS:
            return {"error": "EXPECTED_CONCEPTS not defined or empty in vault_schema.py"}

        subdomain_to_domain = build_subdomain_to_domain(_schema)
        actual = load_actual_concepts(_schema.VAULT_ROOT, _schema)
        raw_gaps = detect_gaps(_schema.EXPECTED_CONCEPTS, actual)
        scored_gaps = score_gaps(raw_gaps, subdomain_to_domain, _schema)

        total_expected = sum(len(v) for v in _schema.EXPECTED_CONCEPTS.values())
        total_actual = sum(len(v) for v in actual.values())
        total_missing = sum(len(v) for v in scored_gaps.values())
        domains = {subdomain_to_domain.get(s, s) for s in _schema.EXPECTED_CONCEPTS}

        # Build gaps dict — matches CLI subdomain ordering (sorted) and per-entry
        # ordering (descending score, then ascending concept name) from score_gaps
        gaps: dict[str, list[dict]] = {
            sub: [{"concept": c, "score": s} for c, s in entries]
            for sub, entries in scored_gaps.items()
        }

        # Build ranked list — matches CLI render_ranked_list ordering
        all_entries: list[tuple[float, str, str]] = []
        for sub, entries in scored_gaps.items():
            for concept, score in entries:
                all_entries.append((score, concept, sub))
        all_entries.sort(key=lambda x: (-x[0], x[1]))

        ranked = [
            {"rank": i, "score": score, "subdomain": sub, "concept": concept}
            for i, (score, concept, sub) in enumerate(all_entries, 1)
        ]

        result = {
            "total_expected": total_expected,
            "total_actual": total_actual,
            "total_missing": total_missing,
            "domains_assessed": len(domains),
            "subdomains": len(_schema.EXPECTED_CONCEPTS),
            "gaps": gaps,
            "ranked": ranked,
        }

        set_cached(vault_name, _ENDPOINT, result)
        return result

    except Exception as exc:
        return {"error": str(exc)}
