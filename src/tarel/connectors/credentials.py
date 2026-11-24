"""Resolve the login of a configured connector section without exposing its secret."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from tarel.connectors.contracts import AUTH_METHODS, ConnectorFailure, ConnectorManifest, Credential

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def resolve_credential(
    name: str,
    section: dict[str, Any],
    manifest: ConnectorManifest,
    *,
    config_dir: Path | None,
) -> Credential | None:
    """Return the configured login, or None when the URL alone carries it.

    ``secret`` accepts ``env:VARIABLE`` or ``file:path`` only; a relative file path is read
    next to the configuration file. Executable sources are deliberately not supported: a
    writable configuration file must not be able to run a command.
    """
    method = section.get("auth")
    if method is None:
        if "username" in section or "secret" in section:
            raise ConnectorFailure(
                "invalid_config", f"[{name}] sets username or secret without auth."
            )
        return None
    if not isinstance(method, str) or method not in AUTH_METHODS:
        raise ConnectorFailure(
            "unsupported_auth",
            f"[{name}].auth must be one of: {', '.join(AUTH_METHODS)}.",
        )
    if method not in manifest.auth:
        supported = ", ".join(manifest.auth) or "none; put the login into the URL"
        raise ConnectorFailure(
            "unsupported_auth",
            f"Connector {name} does not accept {method} login (supported: {supported}).",
        )
    if method == "integrated" and ("username" in section or "secret" in section):
        raise ConnectorFailure(
            "invalid_config", f"[{name}] integrated login takes neither username nor secret."
        )
    username = section.get("username")
    if username is not None and (not isinstance(username, str) or not username.strip()):
        raise ConnectorFailure("invalid_config", f"[{name}].username must be a non-empty string.")
    reference = section.get("secret")
    secret = None if reference is None else _resolve_secret(name, reference, config_dir)
    return Credential(
        method=method,
        username=username.strip() if isinstance(username, str) else None,
        secret=secret,
    )


def _resolve_secret(name: str, reference: object, config_dir: Path | None) -> str:
    if not isinstance(reference, str):
        raise ConnectorFailure("invalid_config", f"[{name}].secret must be a string reference.")
    kind, separator, value = reference.partition(":")
    if not separator or not value:
        kind = ""
    if kind == "env" and _ENV_NAME.fullmatch(value):
        secret = os.getenv(value)
        if not secret:
            raise ConnectorFailure(
                "secret_not_resolved",
                f"Environment variable for [{name}].secret is not set: {value}",
            )
        return secret
    if kind == "file":
        path = Path(value).expanduser()
        if not path.is_absolute() and config_dir is not None:
            path = config_dir / path
        try:
            # Only the line ending an editor adds; spaces can be part of a password.
            secret = path.read_text(encoding="utf-8").rstrip("\r\n")
        except OSError:
            raise ConnectorFailure(
                "secret_not_resolved", f"Secret file for [{name}] could not be read: {path}"
            ) from None
        if not secret:
            raise ConnectorFailure(
                "secret_not_resolved", f"Secret file for [{name}] is empty: {path}"
            )
        return secret
    raise ConnectorFailure("invalid_config", f"[{name}].secret must use env:VARIABLE or file:path.")
