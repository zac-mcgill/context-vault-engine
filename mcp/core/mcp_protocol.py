"""MCP JSON-RPC 2.0 protocol handler.

Handles initialization, method dispatch, and error formatting for the
MCP stdio compatibility layer.

All responses are written to stdout as newline-delimited JSON.
All logs go to stderr only - stdout is reserved for JSON-RPC messages.

JSON-RPC 2.0 error codes:
  -32700  Parse error
  -32600  Invalid request
  -32601  Method not found
  -32602  Invalid params
  -32603  Internal error
"""

from __future__ import annotations

import json
import logging
import sys

logger = logging.getLogger("mcp.protocol")

# JSON-RPC 2.0 error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

MCP_PROTOCOL_VERSION = "2025-11-25"
SERVER_NAME = "context-vault-engine"
SERVER_VERSION = "0.1.0"


def make_result(request_id, result: dict) -> dict:
    """Build a JSON-RPC 2.0 success response."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }


def make_error(request_id, code: int, message: str, data=None) -> dict:
    """Build a JSON-RPC 2.0 error response."""
    error: dict = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": error,
    }


def write_response(response: dict) -> None:
    """Write a JSON-RPC response to stdout as a single line."""
    line = json.dumps(response, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def parse_message(line: str) -> tuple[dict | None, dict | None]:
    """Parse a JSON-RPC message from a line of text.

    Returns (message, error_response).
    If parse succeeds: (msg_dict, None).
    If parse fails: (None, error_response_dict).
    """
    try:
        msg = json.loads(line)
        if not isinstance(msg, dict):
            return None, make_error(None, INVALID_REQUEST, "Request must be a JSON object")
        return msg, None
    except json.JSONDecodeError as exc:
        return None, make_error(None, PARSE_ERROR, f"Parse error: {exc.msg}")


def dispatch(msg: dict, handlers: dict) -> dict | None:
    """Dispatch a JSON-RPC message to the appropriate handler.

    Returns a response dict or None for notifications (no id, no response needed).

    Args:
        msg:      Parsed JSON-RPC message dict.
        handlers: Dict mapping method name -> callable(msg) -> dict.

    Returns:
        dict: JSON-RPC response to send, or None if no response required.
    """
    method = msg.get("method", "")
    request_id = msg.get("id")

    # Notifications have no id - must not receive a response
    if request_id is None:
        logger.debug("notification: %s", method)
        return None

    if method == "initialize":
        return _handle_initialize(msg)

    if method == "ping":
        return make_result(request_id, {})

    if method in handlers:
        try:
            return handlers[method](msg)
        except Exception as exc:
            logger.exception("internal error handling %s", method)
            return make_error(request_id, INTERNAL_ERROR, f"Internal error: {exc}")

    return make_error(request_id, METHOD_NOT_FOUND, f"Method not found: {method!r}")


def _handle_initialize(msg: dict) -> dict:
    """Handle the initialize request."""
    request_id = msg.get("id")
    return make_result(request_id, {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "serverInfo": {
            "name": SERVER_NAME,
            "version": SERVER_VERSION,
        },
        "capabilities": {
            "tools": {"listChanged": False},
            "resources": {"subscribe": False, "listChanged": False},
            "prompts": {"listChanged": False},
        },
    })
