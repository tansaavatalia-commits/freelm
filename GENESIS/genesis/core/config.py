"""Configuration: built-in defaults < ``<home>/genesis.toml`` < explicit overrides.

The configuration file lives in the data folder, outside the repository, and is
edited only by the owner. Agents never receive write access to it (enforced by
the tool sandbox from Phase 5; see documentation/SECURITY.md).
"""

from __future__ import annotations

import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from ..errors import ConfigError

CONFIG_FILENAME = "genesis.toml"
PROFILE_CHOICES = ("auto", "lite-4gb", "standard", "gpu")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
# Built-in agents may only read/analyse (level 1). Agents defined by the owner start at 0.
DEFAULT_GRANTS: Mapping[str, int] = MappingProxyType({"owner": 5, "system": 3, **{f"agent.{a}": 1 for a in (
    "director", "researcher", "developer", "analyst", "creator", "manager", "verifier", "security")}})
PRINCIPAL_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_KNOWN_KEYS = {
    "general": {"profile"},
    "logging": {"level"},
    "backup": {"keep"},
    "permissions": {"grants"},
    "intelligence": {"remote_enabled", "remote_free_verified"},
}


def default_home() -> Path:
    """Data folder: ``$GENESIS_HOME`` or the per-user application-data folder of the OS."""
    env = os.environ.get("GENESIS_HOME")
    if env:
        return Path(env).expanduser()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Local") / "GENESIS"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "GENESIS"
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else Path.home() / ".local" / "share") / "genesis"


@dataclass(frozen=True)
class Config:
    home: Path
    profile: str = "auto"
    log_level: str = "INFO"
    backup_keep: int | None = None  # None: use the execution profile's default
    grants: Mapping[str, int] = field(default_factory=lambda: DEFAULT_GRANTS)
    remote_enabled: bool = False  # online engines allowed at all
    remote_free_verified: bool = False  # owner checked their free terms (COST_POLICY.md)

    @property
    def data_dir(self) -> Path:
        return self.home / "data"

    @property
    def logs_dir(self) -> Path:
        return self.home / "logs"

    @property
    def backups_dir(self) -> Path:
        return self.home / "backups"

    @property
    def exports_dir(self) -> Path:
        return self.home / "exports"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "genesis.db"

    @property
    def config_path(self) -> Path:
        return self.home / CONFIG_FILENAME


def load_config(home: Path | str | None = None, overrides: Mapping[str, Any] | None = None) -> Config:
    root = Path(home).expanduser() if home is not None else default_home()
    path = root / CONFIG_FILENAME
    raw: dict[str, Any] = {}
    if path.is_file():
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
            raise ConfigError(f"{path}: TOML non valido ({exc})") from exc
    return _build(root, _merge(raw, dict(overrides or {})), path)


def set_online(home: Path | str | None, enabled: bool) -> Path:
    """Write [intelligence] remote_enabled/remote_free_verified into <home>/genesis.toml (owner action)."""
    root = Path(home).expanduser() if home is not None else default_home()
    path = root / CONFIG_FILENAME
    old = path.read_text(encoding="utf-8") if path.is_file() else ""
    value = "true" if enabled else "false"
    section = f"[intelligence]\nremote_enabled = {value}\nremote_free_verified = {value}\n"
    if re.search(r"^\[intelligence\]", old, re.M):
        new = re.sub(r"^\[intelligence\][^\[]*", section + "\n", old, count=1, flags=re.M)
    else:
        new = (old.rstrip() + "\n\n" if old.strip() else "") + section
    root.mkdir(parents=True, exist_ok=True)
    path.write_text(new, encoding="utf-8")
    try:
        load_config(root)
    except ConfigError:
        path.write_text(old, encoding="utf-8")  # never leave a broken configuration behind
        raise
    return path


def _merge(base: Mapping[str, Any], extra: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _build(home: Path, raw: Mapping[str, Any], source: Path) -> Config:
    for section, value in raw.items():
        if section not in _KNOWN_KEYS:
            raise ConfigError(f"{source}: sezione sconosciuta [{section}]")
        if not isinstance(value, Mapping):
            raise ConfigError(f"{source}: [{section}] deve essere una tabella")
        unknown = set(value) - _KNOWN_KEYS[section]
        if unknown:
            raise ConfigError(f"{source}: chiavi sconosciute in [{section}]: {', '.join(sorted(unknown))}")

    profile = raw.get("general", {}).get("profile", "auto")
    if profile not in PROFILE_CHOICES:
        raise ConfigError(f"{source}: profilo {profile!r} non valido (ammessi: {', '.join(PROFILE_CHOICES)})")

    level = str(raw.get("logging", {}).get("level", "INFO")).upper()
    if level not in LOG_LEVELS:
        raise ConfigError(f"{source}: livello di log {level!r} non valido (ammessi: {', '.join(LOG_LEVELS)})")

    keep = raw.get("backup", {}).get("keep")
    if keep is not None and not (_is_int(keep) and 1 <= keep <= 365):
        raise ConfigError(f"{source}: [backup] keep deve essere un intero tra 1 e 365")

    user_grants = raw.get("permissions", {}).get("grants", {})
    if not isinstance(user_grants, Mapping):
        raise ConfigError(f"{source}: [permissions] grants deve essere una tabella")
    grants = dict(DEFAULT_GRANTS)
    for principal, granted in user_grants.items():
        if not PRINCIPAL_RE.match(principal):
            raise ConfigError(f"{source}: nome di principal non valido: {principal!r}")
        if not (_is_int(granted) and 0 <= granted <= 5):
            raise ConfigError(f"{source}: il permesso di {principal!r} deve essere un intero tra 0 e 5")
        grants[principal] = granted

    intelligence = raw.get("intelligence", {})
    flags = {}
    for key in ("remote_enabled", "remote_free_verified"):
        value = intelligence.get(key, False)
        if not isinstance(value, bool):
            raise ConfigError(f"{source}: [intelligence] {key} deve essere true o false")
        flags[key] = value

    return Config(home=home, profile=profile, log_level=level, backup_keep=keep, grants=MappingProxyType(grants),
                  **flags)
