"""MCP stdio server for Context Vault Engine.

Implements the Model Context Protocol over stdio transport.
Reads JSON-RPC messages from stdin (one per line).
Writes JSON-RPC responses to stdout (one per line).
All logs go to stderr only — stdout is reserved for JSON-RPC.

Supported JSON-RPC methods:
  initialize
  notifications/initialized   (notification — no response)
  ping
  tools/list
  tools/call
  resources/list
  resources/read
  prompts/list
  prompts/get

Unknown methods return -32601 (Method not found).
Parse errors return -32700.
Invalid params return -32602.
Internal errors return -32603.

Launch with:
  py run.py mcp
or directly:
  py mcp/server/mcp_stdio_server.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure repo root is on sys.path so both mcp.* and core.* imports work
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Logging — stderr only, never stdout
# ---------------------------------------------------------------------------

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="ts=%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

logger = logging.getLogger("mcp.stdio_server")

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from mcp.core.mcp_protocol import (  # noqa: E402
    dispatch,
    make_error,
    make_result,
    parse_message,
    write_response,
    INVALID_PARAMS,
    INTERNAL_ERROR,
)
from mcp.core.mcp_tools import TOOLS, dispatch_tool_call  # noqa: E402
from mcp.core.mcp_resources import list_resources, read_resource  # noqa: E402
from mcp.core.mcp_prompts import PROMPTS, get_prompt, _PROMPT_NAMES  # noqa: E402


# ---------------------------------------------------------------------------
# Method handlers
# ---------------------------------------------------------------------------

def _handle_tools_list(msg: dict) -> dict:
    request_id = msg.get("id")
    return make_result(request_id, {"tools": TOOLS})


def _handle_tools_call(msg: dict) -> dict:
    request_id = msg.get("id")
    params = msg.get("params", {})

    if not isinstance(params, dict):
        return make_error(request_id, INVALID_PARAMS, "params must be an object")

    tool_name = params.get("name")
    if not tool_name or not isinstance(tool_name, str):
        return make_error(request_id, INVALID_PARAMS, "params.name is required")

    args = params.get("arguments", {})
    if not isinstance(args, dict):
        return make_error(request_id, INVALID_PARAMS, "params.arguments must be an object")

    try:
        tool_result = dispatch_tool_call(tool_name, args)
        return make_result(request_id, tool_result)
    except Exception as exc:
        logger.exception("unexpected error in tools/call")
        return make_error(request_id, INTERNAL_ERROR, f"Internal error: {exc}")


def _handle_resources_list(msg: dict) -> dict:
    request_id = msg.get("id")
    try:
        resources = list_resources()
        return make_result(request_id, {"resources": resources})
    except Exception as exc:
        logger.exception("error listing resources")
        return make_error(request_id, INTERNAL_ERROR, f"Internal error: {exc}")


def _handle_resources_read(msg: dict) -> dict:
    request_id = msg.get("id")
    params = msg.get("params", {})

    if not isinstance(params, dict):
        return make_error(request_id, INVALID_PARAMS, "params must be an object")

    uri = params.get("uri")
    if not uri or not isinstance(uri, str):
        return make_error(request_id, INVALID_PARAMS, "params.uri is required")

    try:
        resource_result = read_resource(uri)
        return make_result(request_id, resource_result)
    except Exception as exc:
        logger.exception("error reading resource %s", uri)
        return make_error(request_id, INTERNAL_ERROR, f"Internal error: {exc}")


def _handle_prompts_list(msg: dict) -> dict:
    request_id = msg.get("id")
    return make_result(request_id, {"prompts": PROMPTS})


def _handle_prompts_get(msg: dict) -> dict:
    request_id = msg.get("id")
    params = msg.get("params", {})

    if not isinstance(params, dict):
        return make_error(request_id, INVALID_PARAMS, "params must be an object")

    name = params.get("name")
    if not name or not isinstance(name, str):
        return make_error(request_id, INVALID_PARAMS, "params.name is required")

    if name not in _PROMPT_NAMES:
        return make_error(request_id, INVALID_PARAMS, f"Unknown prompt: {name!r}")

    arguments = params.get("arguments", {})
    if not isinstance(arguments, dict):
        return make_error(request_id, INVALID_PARAMS, "params.arguments must be an object")

    try:
        prompt_result = get_prompt(name, arguments)
        if prompt_result is None:
            return make_error(request_id, INVALID_PARAMS, f"Unknown prompt: {name!r}")
        return make_result(request_id, prompt_result)
    except Exception as exc:
        logger.exception("error getting prompt %s", name)
        return make_error(request_id, INTERNAL_ERROR, f"Internal error: {exc}")


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

_HANDLERS = {
    "tools/list": _handle_tools_list,
    "tools/call": _handle_tools_call,
    "resources/list": _handle_resources_list,
    "resources/read": _handle_resources_read,
    "prompts/list": _handle_prompts_list,
    "prompts/get": _handle_prompts_get,
}


# ---------------------------------------------------------------------------
# Main server loop
# ---------------------------------------------------------------------------

def run_server(stdin=None, stdout=None) -> None:
    """Run the MCP stdio server.

    Reads from stdin (default: sys.stdin), writes to stdout (default: sys.stdout).
    Exits cleanly on EOF. Does not print any banner to stdout.

    Args:
        stdin:  File-like object to read from. Defaults to sys.stdin.
        stdout: Unused — responses always go to sys.stdout via write_response().
                Accepted for test compatibility.
    """
    in_stream = stdin if stdin is not None else sys.stdin
    logger.info("MCP stdio server started (transport=stdio, version=2025-11-25)")

    try:
        for raw_line in in_stream:
            line = raw_line.rstrip("\n\r")
            if not line.strip():
                continue  # skip blank lines

            msg, parse_err = parse_message(line)
            if parse_err is not None:
                write_response(parse_err)
                continue

            try:
                response = dispatch(msg, _HANDLERS)
            except Exception as exc:
                logger.exception("dispatch error")
                request_id = msg.get("id") if isinstance(msg, dict) else None
                response = make_error(request_id, INTERNAL_ERROR, f"Internal error: {exc}")

            if response is not None:
                write_response(response)

    except KeyboardInterrupt:
        logger.info("MCP stdio server stopped (KeyboardInterrupt)")
    except EOFError:
        logger.info("MCP stdio server stopped (EOF)")
    except Exception as exc:
        logger.exception("MCP stdio server fatal error: %s", exc)
        raise


def main() -> None:
    run_server()


if __name__ == "__main__":
    main()
