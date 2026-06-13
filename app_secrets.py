"""Read config secrets from env, Streamlit secrets, or local secrets.toml."""

from __future__ import annotations

import os
import re
from pathlib import Path

_SECRETS_PATH = Path(__file__).parent / ".streamlit" / "secrets.toml"
_TOML_STRING = re.compile(
    r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"((?:\\.|[^"\\])*)"\s*$'
)


def _read_secrets_toml() -> dict[str, str]:
    if not _SECRETS_PATH.exists():
        return {}
    values: dict[str, str] = {}
    for line in _SECRETS_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _TOML_STRING.match(stripped)
        if match:
            key, value = match.groups()
            values[key] = value.replace("\\\"", "\"").replace("\\\\", "\\")
    return values


def get_secret(name: str) -> str:
    env_value = os.environ.get(name, "").strip()
    if env_value:
        return env_value
    try:
        import streamlit as st

        try:
            return str(st.secrets[name]).strip()
        except (KeyError, TypeError):
            pass
        attr = getattr(st.secrets, name, None)
        if attr is not None and not callable(attr):
            return str(attr).strip()
    except Exception:
        pass
    return _read_secrets_toml().get(name, "").strip()
