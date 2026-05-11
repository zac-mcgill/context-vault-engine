"""MCP Tool definitions and dispatch for Context Vault Engine.

All tools are read-only and deterministic.
No destructive, write, or mutation tools are exposed.

Tool naming convention: cve.<action>
Tool ordering: alphabetical by name (deterministic listing).

Excluded tools (not exposed in Phase 20):
  - vault delete
  - vault bootstrap
  - note edit
  - feedback create/update/delete
  - export package write
  - schema mutation
  - template mutation
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("mcp.tools")

# ---------------------------------------------------------------------------
# Tool catalogue — alphabetical order for deterministic listing
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "cve.build_context_bundle",
        "description": (
            "Build a deterministic context bundle in memory. "
            "Does not write export packages."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {"type": "string"},
                "filters": {"type": "object"},
                "include_body": {"type": "boolean"},
                "include_feedback": {"type": "boolean"},
                "include_graph": {"type": "boolean"},
                "max_notes": {"type": "integer", "minimum": 1, "maximum": 200},
                "max_chars": {"type": "integer", "minimum": 1000, "maximum": 1000000},
                "allow_partial": {"type": "boolean"},
            },
            "required": ["vault"],
            "additionalProperties": False,
        },
    },
    {
        "name": "cve.get_context_plan",
        "description": "Get deterministic next-action plan for a vault.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {"type": "string"},
                "intent": {
                    "type": "string",
                    "enum": ["review", "export", "agent-context", "quality", "security"],
                },
            },
            "required": ["vault"],
            "additionalProperties": False,
        },
    },
    {
        "name": "cve.get_context_state",
        "description": "Get deterministic vault state and readiness.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {"type": "string"},
            },
            "required": ["vault"],
            "additionalProperties": False,
        },
    },
    {
        "name": "cve.get_missing_concepts",
        "description": "Get missing expected concepts for a vault.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {"type": "string"},
            },
            "required": ["vault"],
            "additionalProperties": False,
        },
    },
    {
        "name": "cve.get_note",
        "description": "Retrieve one note by vault-relative path.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["vault", "path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "cve.get_tasks",
        "description": "Get deterministic improvement tasks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {"type": "string"},
                "min_priority": {"type": "number"},
            },
            "required": ["vault"],
            "additionalProperties": False,
        },
    },
    {
        "name": "cve.list_vaults",
        "description": "List registered vaults.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
        },
    },
    {
        "name": "cve.query_notes",
        "description": "Run deterministic lexical/filter query over notes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {"type": "string"},
                "q": {"type": "string"},
                "q_fields": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["body", "path", "frontmatter"],
                    },
                },
                "filters": {"type": "object"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["vault"],
            "additionalProperties": False,
        },
    },
    {
        "name": "cve.security_scan",
        "description": "Run deterministic security scan over vault notes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {"type": "string"},
            },
            "required": ["vault"],
            "additionalProperties": False,
        },
    },
    {
        "name": "cve.validate_vault",
        "description": "Run validation summary for a vault.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {"type": "string"},
            },
            "required": ["vault"],
            "additionalProperties": False,
        },
    },
]

_TOOL_NAMES: frozenset[str] = frozenset(t["name"] for t in TOOLS)
_TOOL_VALID_ARGS: dict[str, set[str]] = {
    t["name"]: set(t["inputSchema"].get("properties", {}).keys())
    for t in TOOLS
}
_TOOL_REQUIRED_ARGS: dict[str, set[str]] = {
    t["name"]: set(t["inputSchema"].get("required", []))
    for t in TOOLS
}


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _tool_error(text: str) -> dict:
    return {
        "content": [{"type": "text", "text": text}],
        "isError": True,
    }


def _tool_ok(data: dict, summary: str | None = None) -> dict:
    text = summary if summary else json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": data,
        "isError": False,
    }


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------

def _validate_args(tool_name: str, args: dict) -> str | None:
    """Validate arguments for a tool.

    Returns an error message string if invalid, None if valid.
    """
    required = _TOOL_REQUIRED_ARGS.get(tool_name, set())
    valid = _TOOL_VALID_ARGS.get(tool_name, set())

    for key in required:
        if key not in args:
            return f"Missing required argument: {key!r}"

    for key in args:
        if valid and key not in valid:
            return f"Unknown argument: {key!r}"

    return None


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def dispatch_tool_call(tool_name: str, args: dict) -> dict:
    """Dispatch a tool call and return the tool result.

    Never raises — errors are returned as isError=True tool results.
    """
    if tool_name not in _TOOL_NAMES:
        return _tool_error(f"Unknown tool: {tool_name!r}")

    validation_error = _validate_args(tool_name, args)
    if validation_error:
        return _tool_error(f"INVALID_PARAMS: {validation_error}")

    try:
        return _execute_tool(tool_name, args)
    except Exception as exc:
        logger.exception("tool execution error: %s", tool_name)
        return _tool_error(f"INTERNAL_ERROR: {exc}")


def _execute_tool(tool_name: str, args: dict) -> dict:
    """Execute a named tool with pre-validated args."""
    dispatch = {
        "cve.list_vaults": _tool_list_vaults,
        "cve.get_context_state": _tool_get_context_state,
        "cve.get_context_plan": _tool_get_context_plan,
        "cve.query_notes": _tool_query_notes,
        "cve.get_note": _tool_get_note,
        "cve.validate_vault": _tool_validate_vault,
        "cve.get_tasks": _tool_get_tasks,
        "cve.get_missing_concepts": _tool_get_missing_concepts,
        "cve.security_scan": _tool_security_scan,
        "cve.build_context_bundle": _tool_build_context_bundle,
    }
    fn = dispatch.get(tool_name)
    if fn is None:
        return _tool_error(f"Unknown tool: {tool_name!r}")
    return fn(args)


# ---------------------------------------------------------------------------
# Individual tool implementations
# ---------------------------------------------------------------------------

def _tool_list_vaults(args: dict) -> dict:
    from mcp.core.vault_registry import list_vaults  # noqa: PLC0415
    vaults = list_vaults()
    data = {"vaults": vaults, "count": len(vaults)}
    return _tool_ok(data, f"Found {len(vaults)} vault(s): {', '.join(vaults)}")


def _tool_get_context_state(args: dict) -> dict:
    from mcp.core.context_controller import get_context_state  # noqa: PLC0415
    vault = args["vault"]
    result = get_context_state(vault)
    if result.get("status") == "error":
        err = result["error"]
        return _tool_error(f"{err['code']}: {err['message']}")
    return _tool_ok(result)


def _tool_get_context_plan(args: dict) -> dict:
    from mcp.core.context_controller import build_context_plan  # noqa: PLC0415
    vault = args["vault"]
    intent = args.get("intent", "review")
    result = build_context_plan(vault, intent=intent)
    if result.get("status") == "error":
        err = result["error"]
        return _tool_error(f"{err['code']}: {err['message']}")
    return _tool_ok(result)


def _tool_query_notes(args: dict) -> dict:
    from mcp.core.query_engine import query  # noqa: PLC0415
    vault = args["vault"]
    q = args.get("q")
    q_fields = args.get("q_fields")
    filters = args.get("filters") or {}
    limit = args.get("limit", 20)

    kwargs: dict = {}
    if q is not None:
        kwargs["q"] = q
    if q_fields is not None:
        kwargs["q_fields"] = q_fields

    result = query(vault, filters, limit=limit, **kwargs)
    if result.get("status") == "error":
        return _tool_error(f"QUERY_ERROR: {result.get('error', 'unknown')}")
    return _tool_ok(result)


def _tool_get_note(args: dict) -> dict:
    from mcp.core.query_engine import get_note  # noqa: PLC0415
    vault = args["vault"]
    path = args["path"]
    result = get_note(vault, path)
    if result.get("status") == "error":
        error = result.get("error", {})
        if isinstance(error, dict):
            code = error.get("code", "ERROR")
            msg = error.get("message", str(error))
        else:
            code = str(error)
            msg = str(error)
        return _tool_error(f"{code}: {msg}")
    return _tool_ok(result)


def _tool_validate_vault(args: dict) -> dict:
    from mcp.core.adapters.validation_adapter import get_validation  # noqa: PLC0415
    vault = args["vault"]
    result = get_validation(vault_name=vault)
    if "error" in result:
        return _tool_error(f"VALIDATION_ERROR: {result['error']}")
    return _tool_ok(result)


def _tool_get_tasks(args: dict) -> dict:
    from mcp.core.adapters.tasks_adapter import get_tasks  # noqa: PLC0415
    vault = args["vault"]
    min_priority = args.get("min_priority")
    result = get_tasks(vault_name=vault, limit=50)
    if "error" in result:
        return _tool_error(f"TASKS_ERROR: {result['error']}")
    if min_priority is not None:
        filtered = [t for t in result["tasks"] if t.get("priority", 0) >= min_priority]
        result = dict(result)
        result["tasks"] = filtered
        result["total"] = len(filtered)
    return _tool_ok(result)


def _tool_get_missing_concepts(args: dict) -> dict:
    from mcp.core.adapters.missing_adapter import get_missing  # noqa: PLC0415
    vault = args["vault"]
    result = get_missing(vault_name=vault)
    if "error" in result:
        return _tool_error(f"MISSING_ERROR: {result['error']}")
    return _tool_ok(result)


def _tool_security_scan(args: dict) -> dict:
    from mcp.core.note_index import build_index  # noqa: PLC0415
    from core.shared.context_security import scan_vault_context  # noqa: PLC0415
    vault = args["vault"]
    # Full-vault scan defaults: include all content notes, allow partial,
    # no filter — matches the CLI security command behaviour.
    build_index(vault)
    result = scan_vault_context(
        vault_name=vault,
        filters={},
        include_sections=["Key Principles", "How It Works", "Trade-offs"],
        include_body=True,
        max_notes=1000,
        max_chars=10_000_000,
        allow_partial=True,
    )
    if result.get("status") == "error":
        return _tool_error(f"SECURITY_SCAN_ERROR: {result.get('error', 'unknown')}")
    return _tool_ok(result)


def _tool_build_context_bundle(args: dict) -> dict:
    from core.shared.context_bundle import generate_bundle  # noqa: PLC0415
    vault = args["vault"]
    filters = args.get("filters") or {}
    include_body = args.get("include_body", True)
    include_graph = args.get("include_graph", False)
    max_notes = args.get("max_notes", 50)
    max_chars = args.get("max_chars", 100_000)
    allow_partial = args.get("allow_partial", True)
    # Note: include_feedback is accepted but generate_bundle handles
    # feedback automatically; no separate parameter required.

    result = generate_bundle(
        vault_name=vault,
        filters=filters,
        include_body=include_body,
        include_related=include_graph,
        max_notes=max_notes,
        max_chars=max_chars,
        allow_partial=allow_partial,
    )
    if result.get("status") == "error":
        err = result["error"]
        return _tool_error(f"{err['code']}: {err['message']}")
    return _tool_ok(result)
