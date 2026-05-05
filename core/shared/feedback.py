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

import hashlib
import os
import re
import tempfile
from datetime import datetime, timezone
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
# Write-operation constants
# ---------------------------------------------------------------------------

_MAX_COMMENT_LENGTH: int = 2000

# Valid feedback entry id: 12–16 lowercase hex characters.
_FEEDBACK_ID_RE = re.compile(r"^[0-9a-f]{12,16}$")

# Control characters that must not appear in comments (except normal whitespace).
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

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
    # Include 'id' if present (Phase 14A — backward compatible; id-less entries
    # are still valid and remain readable).
    entry_id = str(entry.get("id", "")).strip()
    if entry_id:
        clean["id"] = entry_id
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


# ---------------------------------------------------------------------------
# ID generation (Phase 14A)
# ---------------------------------------------------------------------------

def _entry_id_digest(
    path: str, source: str, signal: str, severity: str, comment: str, created_at: str,
) -> str:
    """Return SHA-256 hex digest of the canonical entry key."""
    key = "|".join([path, source, signal, severity, comment[:100], created_at])
    return hashlib.sha256(key.encode()).hexdigest()


def _unique_id(
    existing_ids: set[str],
    path: str,
    source: str,
    signal: str,
    severity: str,
    comment: str,
    created_at: str,
) -> str:
    """Return a unique 12–16 hex char ID not in existing_ids.

    Tries 12-char prefix first, then 16-char, then collision-suffixed variants.
    """
    digest = _entry_id_digest(path, source, signal, severity, comment, created_at)
    # Try 12-char, then 16-char prefix of the same digest
    for length in (12, 16):
        candidate = digest[:length]
        if candidate not in existing_ids:
            return candidate
    # Collision fallback: hash with integer suffix
    for i in range(1, 1000):
        candidate = hashlib.sha256(
            f"{digest}|{i}".encode()
        ).hexdigest()[:12]
        if candidate not in existing_ids:
            return candidate
    # Extremely unlikely: use random bytes
    return os.urandom(6).hex()


def is_valid_feedback_id(fid: str) -> bool:
    """Return True if fid matches the feedback id format (12–16 lowercase hex)."""
    return bool(fid and isinstance(fid, str) and _FEEDBACK_ID_RE.match(fid))


# ---------------------------------------------------------------------------
# Raw entry loader (unvalidated — for write operations)
# ---------------------------------------------------------------------------

def _load_raw_entries(vault_path: Path) -> list[dict]:
    """Return raw entry dicts from the feedback file without strict validation.

    Used by write operations that need to preserve all existing fields.
    Returns an empty list when the file is missing, empty, or unparseable.
    """
    fb_file = feedback_path(vault_path)
    if not fb_file.is_file():
        return []
    try:
        raw = fb_file.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except (OSError, yaml.YAMLError):
        return []
    if not isinstance(data, dict):
        return []
    raw_entries = data.get("feedback")
    if not isinstance(raw_entries, list):
        return []
    return [e for e in raw_entries if isinstance(e, dict)]


# ---------------------------------------------------------------------------
# Normalisation (Phase 14A)
# ---------------------------------------------------------------------------

def normalise_entries(raw_entries: list[dict]) -> list[dict]:
    """Return a new list of entry dicts with 'id' fields guaranteed.

    Entries that already carry a valid id are preserved unchanged.
    Entries with missing or invalid ids receive a generated id.
    """
    # Collect existing valid ids
    existing_ids: set[str] = set()
    for e in raw_entries:
        eid = e.get("id", "")
        if isinstance(eid, str) and _FEEDBACK_ID_RE.match(eid):
            existing_ids.add(eid)

    result: list[dict] = []
    for e in raw_entries:
        eid = e.get("id", "")
        if not isinstance(eid, str) or not _FEEDBACK_ID_RE.match(eid):
            # Generate and assign a unique id
            new_id = _unique_id(
                existing_ids,
                str(e.get("path", "")),
                str(e.get("source", "")),
                str(e.get("signal", "")),
                str(e.get("severity", "")),
                str(e.get("comment", "")),
                str(e.get("created_at", "")),
            )
            existing_ids.add(new_id)
            entry = dict(e)
            entry["id"] = new_id
            result.append(entry)
        else:
            result.append(dict(e))
    return result


# ---------------------------------------------------------------------------
# Atomic write (Phase 14A)
# ---------------------------------------------------------------------------

def _serialise_entry(entry: dict) -> dict:
    """Return a new dict with fields in canonical YAML-friendly order."""
    ordered: dict = {}
    for field in ("id", "path", "source", "signal", "severity", "comment", "created_at"):
        if field in entry:
            ordered[field] = entry[field]
    # Preserve any unexpected extra fields at the end
    for k, v in entry.items():
        if k not in ordered:
            ordered[k] = v
    return ordered


def _write_feedback_atomic(vault_path: Path, entries: list[dict]) -> None:
    """Write feedback entries to the vault feedback file atomically.

    Writes to a temporary file in the same directory, then os.replace.
    On failure the original file is left untouched.
    Raises OSError if the write or rename fails.
    """
    fb_file = feedback_path(vault_path)
    fb_file.parent.mkdir(parents=True, exist_ok=True)

    serialised = [_serialise_entry(e) for e in entries]
    data = {"feedback": serialised}

    content = yaml.dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=4096,
    )

    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(fb_file.parent),
        suffix=".tmp",
        prefix="feedback_",
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, str(fb_file))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Write-operation validation (Phase 14A)
# ---------------------------------------------------------------------------

def validate_feedback_write(
    vault_path: Path,
    note_path: str,
    source: str,
    signal: str,
    severity: str,
    comment: str,
    check_note_exists: bool = True,
) -> list[dict]:
    """Validate all fields for a feedback write operation.

    Returns a list of ``{"code": ..., "message": ...}`` dicts.
    An empty list means all fields are valid.
    """
    errors: list[dict] = []

    # --- path ---
    if not note_path or not isinstance(note_path, str) or not note_path.strip():
        errors.append({"code": "INVALID_INPUT", "message": "'path' is required"})
    else:
        note_path_norm = note_path.strip().replace("\\", "/")
        # Check for literal traversal components before resolving
        if ".." in note_path_norm.split("/"):
            errors.append({
                "code": "PATH_TRAVERSAL",
                "message": "path must not contain '..' components",
            })
        else:
            try:
                resolved = (vault_path / note_path_norm).resolve()
                vault_resolved = vault_path.resolve()
                resolved.relative_to(vault_resolved)
            except ValueError:
                errors.append({
                    "code": "PATH_TRAVERSAL",
                    "message": "path resolves outside vault root",
                })
            else:
                if check_note_exists:
                    note_file = vault_path / note_path_norm
                    if not note_file.is_file():
                        errors.append({
                            "code": "NOTE_NOT_FOUND",
                            "message": f"No note found at {note_path_norm!r}",
                        })

    # --- source ---
    if source not in VALID_SOURCES:
        errors.append({
            "code": "INVALID_INPUT",
            "message": (
                f"'source' must be one of {sorted(VALID_SOURCES)}; got {source!r}"
            ),
        })

    # --- signal ---
    if signal not in VALID_SIGNALS:
        errors.append({
            "code": "INVALID_INPUT",
            "message": (
                f"'signal' must be one of {sorted(VALID_SIGNALS)}; got {signal!r}"
            ),
        })

    # --- severity ---
    if severity not in VALID_SEVERITIES:
        errors.append({
            "code": "INVALID_INPUT",
            "message": (
                f"'severity' must be one of {sorted(VALID_SEVERITIES)}; got {severity!r}"
            ),
        })

    # --- comment ---
    if not comment or not isinstance(comment, str):
        errors.append({"code": "INVALID_INPUT", "message": "'comment' is required"})
    else:
        if not comment.strip():
            errors.append({
                "code": "INVALID_INPUT",
                "message": "'comment' must not be blank",
            })
        elif len(comment) > _MAX_COMMENT_LENGTH:
            errors.append({
                "code": "INVALID_INPUT",
                "message": (
                    f"'comment' exceeds maximum length of {_MAX_COMMENT_LENGTH} characters"
                ),
            })
        elif _CONTROL_CHARS_RE.search(comment):
            errors.append({
                "code": "INVALID_INPUT",
                "message": "'comment' contains invalid control characters",
            })

    return errors


# ---------------------------------------------------------------------------
# Write operations (Phase 14A)
# ---------------------------------------------------------------------------

def add_feedback_entry(
    vault_path: Path,
    note_path: str,
    source: str,
    signal: str,
    severity: str,
    comment: str,
) -> dict:
    """Append a new feedback entry and rewrite the file atomically.

    Returns::

        {
            "status": "ok",
            "entry": {...},      # the new entry (includes id + created_at)
            "feedback": {...},   # updated load_feedback result
        }

    Raises:
        OSError: if the file write fails.
    """
    raw_entries = _load_raw_entries(vault_path)
    existing_normalised = normalise_entries(raw_entries)
    existing_ids = {e.get("id", "") for e in existing_normalised}

    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    new_id = _unique_id(
        existing_ids, note_path, source, signal, severity, comment, created_at,
    )

    new_entry: dict = {
        "id": new_id,
        "path": note_path,
        "source": source,
        "signal": signal,
        "severity": severity,
        "comment": comment,
        "created_at": created_at,
    }

    all_entries = existing_normalised + [new_entry]
    _write_feedback_atomic(vault_path, all_entries)

    return {
        "status": "ok",
        "entry": new_entry,
        "feedback": load_feedback(vault_path),
    }


def update_feedback_entry(
    vault_path: Path,
    feedback_id: str,
    note_path: str,
    source: str,
    signal: str,
    severity: str,
    comment: str,
) -> dict:
    """Update an existing feedback entry in place and rewrite atomically.

    Preserves the original ``created_at``.  Does not change ``id``.

    Returns::

        {
            "status": "ok",
            "entry": {...},      # the updated entry
            "feedback": {...},   # updated load_feedback result
        }

    Raises:
        KeyError:  feedback_id not found in the file.
        OSError:   if the file write fails.
    """
    raw_entries = _load_raw_entries(vault_path)
    normalised = normalise_entries(raw_entries)

    idx: int | None = None
    for i, e in enumerate(normalised):
        if e.get("id") == feedback_id:
            idx = i
            break

    if idx is None:
        raise KeyError(f"Feedback entry {feedback_id!r} not found")

    original = normalised[idx]
    updated_entry: dict = {
        "id": feedback_id,
        "path": note_path,
        "source": source,
        "signal": signal,
        "severity": severity,
        "comment": comment,
        "created_at": original.get("created_at", ""),
    }
    normalised[idx] = updated_entry

    _write_feedback_atomic(vault_path, normalised)

    return {
        "status": "ok",
        "entry": updated_entry,
        "feedback": load_feedback(vault_path),
    }


def delete_feedback_entry(vault_path: Path, feedback_id: str) -> dict:
    """Remove a feedback entry by id and rewrite the file atomically.

    Returns::

        {
            "status": "ok",
            "deleted": "<feedback_id>",
            "feedback": {...},   # updated load_feedback result
        }

    Raises:
        KeyError:  feedback_id not found in the file.
        OSError:   if the file write fails.
    """
    raw_entries = _load_raw_entries(vault_path)
    normalised = normalise_entries(raw_entries)

    remaining = [e for e in normalised if e.get("id") != feedback_id]
    if len(remaining) == len(normalised):
        raise KeyError(f"Feedback entry {feedback_id!r} not found")

    _write_feedback_atomic(vault_path, remaining)

    return {
        "status": "ok",
        "deleted": feedback_id,
        "feedback": load_feedback(vault_path),
    }


def normalise_feedback(vault_path: Path) -> dict:
    """Ensure every entry in the feedback file has an id; rewrite atomically.

    Entries that already carry valid ids are untouched.
    Returns::

        {
            "status": "ok",
            "normalised": <int>,   # count of entries that received a new id
            "feedback": {...},     # updated load_feedback result
        }

    Raises:
        OSError: if the file write fails.
    """
    raw_entries = _load_raw_entries(vault_path)
    if not raw_entries:
        return {
            "status": "ok",
            "normalised": 0,
            "feedback": load_feedback(vault_path),
        }

    normalised = normalise_entries(raw_entries)

    count_new = sum(
        1 for orig, norm in zip(raw_entries, normalised)
        if orig.get("id") != norm.get("id")
    )

    _write_feedback_atomic(vault_path, normalised)

    return {
        "status": "ok",
        "normalised": count_new,
        "feedback": load_feedback(vault_path),
    }
