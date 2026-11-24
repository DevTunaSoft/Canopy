"""Read the existing authenticated OpenCode credential without exposing it.

The token is passed directly to worker processes through the environment.
It is never written to supervisor state, logs, dashboard or exceptions.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3


MAX_CREDENTIAL_BLOB_BYTES = 65536


class CredentialError(RuntimeError):
    """No usable OpenCode credential found."""


def _token_from_blob(value: str) -> str:
    if not isinstance(value, str) or len(value) > MAX_CREDENTIAL_BLOB_BYTES:
        raise ValueError("credential blob is not a bounded string")
    data = json.loads(value)
    if not isinstance(data, dict):
        raise ValueError("credential is not an object")
    for key in ("access", "refresh", "token", "apiKey", "key"):
        token = data.get(key)
        if isinstance(token, str) and token.strip():
            return token.strip()
    raise ValueError("credential has no token field")


def get_opencode_api_key(explicit: str | None = None, data_home: Path | None = None) -> str:
    """Return an OpenCode API token from env, auth.json or the installed DB.

    Precedence: explicit argument, OPENCODE_API_KEY, auth.json, SQLite DB.
    """
    token = explicit or os.environ.get("OPENCODE_API_KEY", "")
    if explicit is not None and not isinstance(explicit, str):
        raise CredentialError("credential argument must be a string")
    if not isinstance(token, str):
        raise CredentialError("credential value must be a string")
    if token.strip():
        return token.strip()

    if data_home is not None and not isinstance(data_home, (str, os.PathLike)):
        raise CredentialError("credential data_home must be a path")
    base = Path(data_home or os.environ.get("OPENCODE_DATA_HOME") or
                (Path.home() / ".local" / "share" / "opencode"))
    auth_file = base / "auth.json"
    if auth_file.is_file():
        try:
            raw = json.loads(auth_file.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and "opencode" in raw:
                provider = raw["opencode"]
                if isinstance(provider, dict) and isinstance(provider.get("access"), str):
                    return _token_from_blob(json.dumps(provider))
        except (OSError, ValueError):
            pass

    database = base / "opencode.db"
    if not database.is_file():
        raise CredentialError("no authenticated OpenCode installation found")
    uri = "file:" + str(database).replace("\\", "/") + "?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            rows = connection.execute(
                "select value from credential where integration_id='opencode' and active=1"
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise CredentialError(f"cannot read OpenCode credential store: {type(exc).__name__}") from exc
    for (value,) in rows:
        if not isinstance(value, str):
            continue
        try:
            return _token_from_blob(value)
        except (ValueError, TypeError):
            continue
    raise CredentialError("authenticated OpenCode account has no active token")
