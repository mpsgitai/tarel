"""Signatures through OpenSSH's ``ssh-keygen -Y``; TAREL implements no cryptography itself.

Which key may sign what is decided by the central trust file, never by a file on the system: the
allowed-signers file below exists only for one check and holds only the key already chosen. Private
keys stay wherever their owner keeps them, including an agent or a hardware token.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from tarel.sync.contracts import SyncFailure

SIGNATURE_NAMESPACE = "tarel-publication"
_PRINCIPAL = "tarel-publisher"
_TOOL = "ssh-keygen"
_TIMEOUT_SECONDS = 30
_PUBLIC_KEY = re.compile(r"^(ssh-ed25519|sk-ssh-ed25519@openssh\.com) ([A-Za-z0-9+/]+={0,3})$")


def normalize_public_key(text: str) -> str:
    """Keep type and key only. A comment or an option could change what the check means."""
    parts = text.strip().split()
    candidate = " ".join(parts[:2])
    if len(text.strip().splitlines()) != 1 or not _PUBLIC_KEY.fullmatch(candidate):
        raise SyncFailure("invalid_public_key", "Expected one Ed25519 OpenSSH public key.")
    return candidate


def key_fingerprint(public_key: str) -> str:
    """The same ``SHA256:...`` text OpenSSH shows for this key."""
    match = _PUBLIC_KEY.fullmatch(public_key)
    if match is None:
        raise SyncFailure("invalid_public_key", "Expected one Ed25519 OpenSSH public key.")
    try:
        blob = base64.b64decode(match.group(2), validate=True)
    except binascii.Error as exc:
        raise SyncFailure("invalid_public_key", "The public key is not valid base64.") from exc
    digest = base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
    return f"SHA256:{digest}"


def read_signing_identity(key_path: Path) -> tuple[Path, str]:
    """The path to sign with and its public key. Only the public file is ever read."""
    public_path = key_path if key_path.suffix == ".pub" else Path(f"{key_path}.pub")
    try:
        return key_path, normalize_public_key(public_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SyncFailure(
            "signing_key_missing", f"Could not read public key: {public_path}"
        ) from exc


def sign_statement(statement: bytes, key_path: Path) -> bytes:
    """Sign exact bytes. The agent stays reachable, and a key that needs a prompt fails instead."""
    with tempfile.TemporaryDirectory(prefix="tarel-sign-") as temporary:
        message = Path(temporary) / "publication.json"
        message.write_bytes(statement)
        _run(
            ["-Y", "sign", "-q", "-f", str(key_path), "-n", SIGNATURE_NAMESPACE, str(message)],
            environment=dict(os.environ),
            failure="signing_failed",
        )
        return Path(f"{message}.sig").read_bytes()


def verify_statement(statement: bytes, signature: bytes, public_key: str) -> None:
    """Raise unless ``signature`` over ``statement`` comes from exactly ``public_key``."""
    with tempfile.TemporaryDirectory(prefix="tarel-verify-") as temporary:
        root = Path(temporary)
        allowed = root / "allowed_signers"
        allowed.write_text(
            f'{_PRINCIPAL} namespaces="{SIGNATURE_NAMESPACE}" {public_key}\n', encoding="utf-8",
        )
        signature_path = root / "publication.sig"
        signature_path.write_bytes(signature)
        arguments = [
            "-Y", "verify",
            "-f", str(allowed),
            "-I", _PRINCIPAL,
            "-n", SIGNATURE_NAMESPACE,
            "-s", str(signature_path),
        ]
        _run(
            arguments,
            environment={"LC_ALL": "C", "PATH": os.environ.get("PATH", "")},
            failure="invalid_signature",
            stdin=statement,
        )


def _run(
    arguments: list[str],
    *,
    environment: dict[str, str],
    failure: str,
    stdin: bytes | None = None,
) -> None:
    tool = shutil.which(_TOOL)
    if tool is None:
        # Never continue without the check: that would be a silent fallback to unsigned.
        raise SyncFailure("signature_tool_missing", f"{_TOOL} is required to check signatures.")
    try:
        result = subprocess.run(
            [tool, *arguments],
            input=stdin if stdin is not None else b"",
            capture_output=True,
            env=environment,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SyncFailure(failure, f"{_TOOL} could not finish: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip().splitlines()
        raise SyncFailure(failure, detail[-1] if detail else f"{_TOOL} refused the operation.")
