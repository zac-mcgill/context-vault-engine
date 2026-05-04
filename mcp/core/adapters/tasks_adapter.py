"""
Tasks adapter — structured upgrade tasks for MCP.

Delegates directly to core.shared.upgrade_vault.  No sys.modules
manipulation, no os.chdir, no importlib workarounds.
"""

from __future__ import annotations

from pathlib import Path

from mcp.core.vault_registry import get_vault_path, list_vaults
from core.shared.upgrade_vault import load_all, generate_tasks
from core.shared.feedback import load_feedback, feedback_weight_for_path
from mcp.core.schema_loader import load_schema as _load_schema
from mcp.core.result_cache import get_cached, set_cached

_ENDPOINT = "tasks"


def get_tasks(
    vault_name: str | None = None,
    limit: int = 10,
    include_feedback: bool = False,
) -> dict:
    """Generate prioritised upgrade tasks.

    Args:
        vault_name:       Vault to query (defaults to first registered vault).
        limit:            Maximum tasks to return.
        include_feedback: When True, adjust task scores by feedback signals
                          loaded from <vault>/Vault Files/feedback.md.
                          The base (unweighted) result is still cached normally.

    Returns:
        {
            "total": int,
            "tasks": [
                {
                    "note": str,
                    "path": str,
                    "priority": float,
                    "difficulty": str,
                    "missing": [str],
                    "action": str,
                    "constraints": [str],
                    # only when include_feedback=True:
                    "feedback_weight": {
                        "score_delta": float,
                        "entry_count": int,
                        "summary": [str]
                    }
                }
            ],
            # only when include_feedback=True:
            "feedback_status": "ok" | "error",
            "feedback_errors": [...]
        }
    """
    try:
        if vault_name is None:
            vaults = list_vaults()
            if not vaults:
                return {"error": "No vaults registered"}
            vault_name = vaults[0]

        # Cache check — full base task list is cached; limit applied on return.
        # Feedback-weighted results are NOT cached separately; feedback is
        # applied on top of the cached base after every call.
        cached = get_cached(vault_name, _ENDPOINT)
        if cached is not None:
            base_tasks = cached["tasks"]
        else:
            vault_path = get_vault_path(vault_name)
            _schema = _load_schema(vault_path)

            records = load_all(vault_path, _schema)
            all_tasks = generate_tasks(records, _schema)

            # Build full transformed list (no early limit — enables correct caching)
            base_tasks: list[dict] = []
            for task in all_tasks:
                missing: list[str] = []
                actions: list[str] = []
                all_constraints: list[str] = []
                for issue in task["issues"]:
                    missing.extend(issue["required_sections"])
                    actions.append(issue["issue_type"])
                    all_constraints.extend(issue.get("constraints", []))

                note_path = task["path"]
                posix_path = Path(note_path).as_posix()
                note_name = Path(note_path).stem

                base_tasks.append({
                    "note": note_name,
                    "path": posix_path,
                    "priority": task["score"],
                    "difficulty": task["difficulty"],
                    "missing": missing,
                    "action": ", ".join(actions),
                    "constraints": all_constraints,
                })

            # Cache the complete base result before applying limit
            full_result = {
                "total": len(all_tasks),
                "tasks": base_tasks,
            }
            set_cached(vault_name, _ENDPOINT, full_result)

        total = len(base_tasks)

        if not include_feedback:
            return {
                "total": total,
                "tasks": base_tasks[:limit],
            }

        # ------------------------------------------------------------------
        # Feedback weighting — applied on top of cached base tasks.
        # We work on copies so the cached base is never mutated.
        # ------------------------------------------------------------------
        vault_path = get_vault_path(vault_name)
        fb_result = load_feedback(vault_path)
        fb_status = fb_result["status"]
        fb_errors = fb_result.get("errors", [])

        weighted_tasks: list[dict] = []
        for task in base_tasks:
            weight = feedback_weight_for_path(vault_path, task["path"])
            adjusted_priority = round(task["priority"] + weight["score_delta"], 4)
            weighted_task = dict(task)
            weighted_task["priority"] = adjusted_priority
            weighted_task["feedback_weight"] = weight
            weighted_tasks.append(weighted_task)

        # Re-sort: score descending, then path ascending (stable tie-break)
        weighted_tasks.sort(key=lambda t: (-t["priority"], t["path"].lower()))

        return {
            "total": total,
            "tasks": weighted_tasks[:limit],
            "feedback_status": fb_status,
            "feedback_errors": fb_errors,
        }

    except Exception as exc:
        return {"error": str(exc)}
