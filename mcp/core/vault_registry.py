"""
Vault registry — loads config, resolves paths, caches schemas.

Single source of truth for vault name → path → schema mappings.
Reads vaults from config/config.yaml (shared with run.py).

Multi-vault support: if ``vault_roots`` (list) is present in config.yaml all
listed paths are registered.  Falls back to single ``vault_root`` when
``vault_roots`` is absent or empty, preserving backward compatibility.
"""

import yaml
from pathlib import Path
from types import ModuleType

from mcp.core.schema_loader import load_schema

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _REPO_ROOT / "config" / "config.yaml"

_vaults: dict[str, Path] = {}
_schemas: dict[str, ModuleType] = {}


def _load_config() -> None:
    """Parse config.yaml and register all configured vaults."""
    global _vaults

    if _vaults:
        return

    if not _CONFIG_PATH.is_file():
        raise FileNotFoundError(f"Config not found: {_CONFIG_PATH}")

    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # Multi-vault: prefer vault_roots list; fall back to single vault_root.
    raw_roots: list[str] = data.get("vault_roots") or []
    if not raw_roots:
        single = data.get("vault_root")
        if not single:
            raise ValueError(f"config.yaml missing 'vault_root': {_CONFIG_PATH}")
        raw_roots = [single]

    loaded: dict[str, Path] = {}
    for raw in raw_roots:
        p = Path(raw)
        if not p.is_absolute():
            p = (_REPO_ROOT / raw).resolve()
        if not p.is_dir():
            # Skip missing directories rather than aborting — a vault may have
            # been deleted manually while remaining in vault_roots.
            continue
        loaded[p.name] = p

    if not loaded:
        raise FileNotFoundError(
            f"No vault directories found for configured roots: {raw_roots}"
        )

    _vaults = loaded


def list_vaults() -> list[str]:
    """Return sorted list of registered vault names."""
    _load_config()
    return sorted(_vaults.keys())


def get_vault_path(name: str) -> Path:
    """Return absolute path for a vault name.

    Raises:
        KeyError: If the vault name is not registered.
    """
    _load_config()
    if name not in _vaults:
        raise KeyError(f"Unknown vault: {name!r}. Available: {sorted(_vaults.keys())}")
    return _vaults[name]


def get_schema(name: str) -> ModuleType:
    """Return the cached schema module for a vault.

    Loads the schema on first call, then caches it.

    Raises:
        KeyError: If the vault name is not registered.
        FileNotFoundError: If the schema file is missing.
        ImportError: If the schema cannot be loaded.
    """
    _load_config()
    if name not in _vaults:
        raise KeyError(f"Unknown vault: {name!r}. Available: {sorted(_vaults.keys())}")

    if name not in _schemas:
        _schemas[name] = load_schema(_vaults[name], vault_name=name)

    return _schemas[name]


def reload_config() -> None:
    """Clear the vault and schema cache and reload from config.yaml.

    Safe to call at runtime — clears the in-memory registry and reloads vault
    paths from the current state of config/config.yaml.  Schema modules cached
    in sys.modules are NOT removed (they remain importable but the registry
    will reload them fresh on next get_schema() call).

    Use this after a vault bootstrap to make the new vault discoverable without
    restarting the process.
    """
    global _vaults, _schemas
    _vaults = {}
    _schemas = {}
    _load_config()
