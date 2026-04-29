"""
core.shared — centralised vault scripts.

Provides _resolve_vault_path() for config-based vault resolution.
Schema loading is handled exclusively by mcp.core.schema_loader.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_vault_path() -> Path:
    """Resolve the active vault path from config/config.yaml.

    Used by standalone (non-CLI) invocations of core/shared/*.py scripts.
    Raises FileNotFoundError or ValueError on any configuration error.
    """
    config_path = _REPO_ROOT / "config" / "config.yaml"

    if not config_path.is_file():
        raise FileNotFoundError(f"Config not found: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    vault_rel = config.get("vault_root") if config else None
    if not vault_rel:
        raise ValueError("config.yaml missing 'vault_root' key")

    vault_path = (_REPO_ROOT / vault_rel).resolve()
    if not vault_path.is_dir():
        raise FileNotFoundError(f"Vault directory not found: {vault_path}")

    return vault_path
