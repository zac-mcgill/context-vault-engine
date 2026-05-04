"""
Feedback Engine — Phase 3

Parses, validates, and queries feedback entries stored in:
    <vault>/Vault Files/feedback.md

The feedback file lives in the excluded Vault Files/ directory and is
intentionally NOT a normal content note.  It is excluded from:
    - note discovery / validation (Vault Files/ is in EXCLUDE_DIRS)
    - graph nodes
    - bundle note selection
    - /notes and /query endpoints

Each feedback entry links to a full vault-relative POSIX note path.
Missing note paths produce warnings, not crashes.
Malformed entries produce structured errors.
Feedback never silently mutates note content or metadata.

Result shape (load_feedback):
    {
        "status": "ok" | "error",
        "entries": [...],        # valid entries only
        "warnings": [...],       # non-fatal issues (e.g. missing note path)
        "errors": [              # structured validation errors
            {"code": ..., "path": ..., "detail": ...}
        ]
    }

Task weight shape (feedback_weight_for_path):
    {
        "score_delta": float,    # positive = raise priority, negative = lower
        "entry_count": int,
        "summary": [str]         # human-readable per-entry descriptions
    }
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Allowed values
# ---------------------------------------------------------------------------

VALID_SOURCES: frozenset[str] = frozenset({"human", "agent", "system"})

VALID_SIGNALS: frozenset[str] = frozenset({
    "unclear",
    "incomplete",
    "outdated",
    "incorrect",
    "useful",
    "agent_failed",
    "agent_succeeded",
    "needs_example",
    "needs_constraints",
})

VALID_SEVERITIES: frozenset[str] = frozenset({"low", "medium", "high", "critical"})

# ---------------------------------------------------------------------------
# Score-weighting tables
# ---------------------------------------------------------------------------

# Severity multiplier applied to the signal's base delta.
_SEVERITY_MULTIPLIER: dict[str, float] = {
    "low": 0.5,
    "medium": 1.0,
    "high": 1.5,
    "critical": 2.0,
}

# Base score delta per signal (before severity multiplier).
# Positive = increase priority; negative = decrease priority.
_SIGNAL_DELTA: dict[str, float] = {
    "unclear": 0.5,
    "incomplete": 0.5,
    "outdated": 0.5,
    "incorrect": 1.0,
    "agent_failed": 1.0,
    "needs_example": 0.5,
    "needs_constraints": 0.5,
    "useful": -0.3,
    "agent_succeeded": -0.3,
}

# ---------------------------------------------------------------------------
# Path helper
# ---------------------------------------------------------------------------

_FEEDBACK_RELATIVE_PATH = Path("Vault Files") / "feedback.md"


def feedback_path(vault_path: Path) -> Path:
    """Return the absolute path to the vault's feedback file."""
    return vault_path / _FEEDBACK_RELATIVE_PATH


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def load_feedback(vault_path: Path) -> dict:
    """Load and validate feedback entries from <vault>/Vault Files/feedback.md.

    The file is optional.  Missing or empty files return ok with no entries.
    Malformed entries are reported as errors and excluded from entries[].

    Returns:
        {
            "status": "ok" | "error",
            "entries": [list of validated entry dicts],
            "warnings": [str],
            "errors": [{"code": ..., "path": ..., "detail": ...}]
        }
    """
    fb_file = feedback_path(vault_path)
    warnings: list[str] = []
    errors: list[dict] = []
    entries: list[dict] = []

    # Missing file → ok, empty
    if not fb_file.is_file():
        return {"status": "ok", "entries": [], "warnings": [], "errors": []}

    # Read
    try:
        raw = fb_file.read_text(encoding="utf-8")
    except OSError as exc:
        return {
            "status": "error",
            "entries": [],
            "warnings": [],
            "errors": [{"code": "READ_ERROR", "path": "feedback.md", "detail": str(exc)}],
        }

    # Parse YAML
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        return {
            "status": "error",
            "entries": [],
            "warnings": [],
            "errors": [{"code": "MALFORMED_YAML", "path": "feedback.md", "detail": str(exc)}],
        }

    # Empty / null file → ok, empty
    if data is None:
        return {"status": "ok", "entries": [], "warnings": [], "errors": []}

    if not isinstance(data, dict):
        return {
            "status": "error",
            "entries": [],
            "warnings": [],
            "errors": [{
                "code": "MALFORMED_YAML",
                "path": "feedback.md",
                "detail": "Root YAML value must be a mapping; got a list or scalar",
            }],
        }

    # Missing or null 'feedback' key → ok, empty
    raw_entries = data.get("feedback")
    if raw_entries is None:
        return {"status": "ok", "entries": [], "warnings": [], "errors": []}

    if not isinstance(raw_entries, list):
        return {
            "status": "error",
            "entries": [],
            "warnings": [],
            "errors": [{
                "code": "MALFORMED_YAML",
                "path": "feedback.md",
                "detail": "'feedback' key must be a YAML list",
            }],
        }

    # Validate each entry
    for i, entry in enumerate(raw_entries):
        entry_errors, entry_warnings, clean_entry = _validate_entry(i, entry, vault_path)
        errors.extend(entry_errors)
        warnings.extend(entry_warnings)
        if not entry_errors:
            entries.append(clean_entry)

    status = "error" if errors else "ok"
    return {
        "status": status,
        "entries": entries,
        "warnings": warnings,
        "errors": errors,
    }


def _validate_entry(
    idx: int,
    entry: Any,
    vault_path: Path,
) -> tuple[list[dict], list[str], dict]:
    """Validate one feedback entry dict.

    Returns (errors, warnings, clean_entry).
    clean_entry is only populated when errors is empty.
    """
    errs: list[dict] = []
    warns: list[str] = []

    if not isinstance(entry, dict):
        return (
            [{
                "code": "INVALID_ENTRY",
                "path": f"entry[{idx}]",
                "detail": f"Entry {idx} must be a YAML mapping; got {type(entry).__name__}",
            }],
            [],
            {},
        )

    note_path = entry.get("path", "")
    label = note_path or f"entry[{idx}]"

    # path is required
    if not note_path:
        errs.append({
            "code": "MISSING_PATH",
            "path": label,
            "detail": "Feedback entry is missing required 'path' field",
        })
        return errs, warns, {}

    # source
    source = entry.get("source", "")
    if source not in VALID_SOURCES:
        errs.append({
            "code": "INVALID_SOURCE",
            "path": label,
            "detail": (
                f"Unknown source {source!r}. "
                f"Must be one of: {sorted(VALID_SOURCES)}"
            ),
        })

    # signal
    signal = entry.get("signal", "")
    if signal not in VALID_SIGNALS:
        errs.append({
            "code": "INVALID_SIGNAL",
            "path": label,
            "detail": (
                f"Unknown signal {signal!r}. "
                f"Must be one of: {sorted(VALID_SIGNALS)}"
            ),
        })

    # severity
    severity = entry.get("severity", "")
    if severity not in VALID_SEVERITIES:
        errs.append({
            "code": "INVALID_SEVERITY",
            "path": label,
            "detail": (
                f"Unknown severity {severity!r}. "
                f"Must be one of: {sorted(VALID_SEVERITIES)}"
            ),
        })

    if errs:
        return errs, warns, {}

    # Warning: referenced note does not exist on disk
    note_file = vault_path / note_path
    if not note_file.is_file():
        warns.append(
            f"Feedback references missing note: {note_path!r} "
            f"(no file found at {note_file.as_posix()})"
        )

    clean: dict = {
        "path": note_path,
        "source": source,
        "signal": signal,
        "severity": severity,
        "comment": str(entry.get("comment", "")),
        "created_at": str(entry.get("created_at", "")),
    }
    return [], warns, clean


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_feedback_for_path(vault_path: Path, note_path: str) -> list[dict]:
    """Return all valid feedback entries for a specific note path.

    note_path is a vault-relative POSIX path (e.g. "Fundamentals/Algorithms.md").
    Returns an empty list when no feedback exists or the file is absent.
    """
    result = load_feedback(vault_path)
    return [e for e in result["entries"] if e["path"] == note_path]


def feedback_weight_for_path(vault_path: Path, note_path: str) -> dict:
    """Compute feedback-based score adjustment for a note.

    Returns:
        {
            "score_delta": float,    # positive = raise priority, negative = lower
            "entry_count": int,
            "summary": [str]         # human-readable per-entry descriptions
        }
    """
    entries = get_feedback_for_path(vault_path, note_path)
    if not entries:
        return {"score_delta": 0.0, "entry_count": 0, "summary": []}

    total_delta = 0.0
    summary: list[str] = []
    for entry in entries:
        signal = entry["signal"]
        severity = entry["severity"]
        base_delta = _SIGNAL_DELTA.get(signal, 0.0)
        multiplier = _SEVERITY_MULTIPLIER.get(severity, 1.0)
        delta = base_delta * multiplier
        total_delta += delta
        summary.append(f"{signal}/{severity} ({delta:+.2f})")

    return {
        "score_delta": round(total_delta, 4),
        "entry_count": len(entries),
        "summary": summary,
    }
