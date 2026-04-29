"""
Compare adapter — vault delta comparison for MCP.

Delegates directly to core.shared.compare_reports.  No business logic.
"""

from __future__ import annotations

from pathlib import Path

from mcp.core.schema_loader import load_schema as _load_schema
from mcp.core.vault_registry import get_vault_path, list_vaults
from core.shared.compare_reports import (
    snapshot_from_report,
    snapshot_from_vault,
    generate_delta_report,
    VaultSnapshot,
)


def _snap_to_dict(s: VaultSnapshot) -> dict:
    """Serialise a VaultSnapshot to a plain dict."""
    return {
        "total": s.total,
        "complete": s.complete,
        "partial": s.partial,
        "completion_pct": round(s.completion_pct, 1),
        "critical_gap_count": s.critical_gap_count,
        "total_section_gaps": s.total_section_gaps,
        "core_concept_count": s.core_concept_count,
        "section_missing": s.section_missing,
        "domain_stats": s.domain_stats,
    }


def get_compare(
    before: str,
    after: str | None = None,
    vault_name: str | None = None,
) -> dict:
    """Compare two vault states and return a structured delta.

    Args:
        before: Path to the BEFORE report (relative to vault root, or absolute).
        after:  Path to the AFTER report (relative to vault root, or absolute).
                If omitted, the live vault state is used as the AFTER snapshot.
        vault_name: Vault name (defaults to the first registered vault).

    Returns:
        {
            "before":  { total, complete, partial, completion_pct, ... },
            "after":   { total, complete, partial, completion_pct, ... },
            "delta":   {
                "completion_pct":       float,
                "partial_notes":        int,
                "critical_gaps":        int,
                "section_deficiencies": int
            },
            "report":  str  (full markdown delta report)
        }
    """
    try:
        if vault_name is None:
            vaults = list_vaults()
            if not vaults:
                return {"error": "No vaults registered"}
            vault_name = vaults[0]

        vault_path = get_vault_path(vault_name)
        _schema = _load_schema(vault_path)

        # Resolve BEFORE path
        before_path = Path(before)
        if not before_path.is_absolute():
            before_path = vault_path / before_path
        if not before_path.is_file():
            return {"error": f"BEFORE report not found: {before}"}

        before_snap = snapshot_from_report(before_path)

        # Resolve AFTER path or analyse live vault
        if after:
            after_path = Path(after)
            if not after_path.is_absolute():
                after_path = vault_path / after_path
            if not after_path.is_file():
                return {"error": f"AFTER report not found: {after}"}
            after_snap = snapshot_from_report(after_path)
        else:
            after_snap = snapshot_from_vault(vault_path, _schema)

        report_text = generate_delta_report(before_snap, after_snap, _schema)

        return {
            "before": _snap_to_dict(before_snap),
            "after": _snap_to_dict(after_snap),
            "delta": {
                "completion_pct": round(
                    after_snap.completion_pct - before_snap.completion_pct, 1
                ),
                "partial_notes": after_snap.partial - before_snap.partial,
                "critical_gaps": (
                    after_snap.critical_gap_count - before_snap.critical_gap_count
                ),
                "section_deficiencies": (
                    after_snap.total_section_gaps - before_snap.total_section_gaps
                ),
            },
            "report": report_text,
        }

    except Exception as exc:
        return {"error": str(exc)}
