"""Explicit model download and cache helpers for local retrieval Hub plugins."""

from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

from tarel.retrieval.contracts import ModelDownloadResult, ModelSpec, RetrievalFailure
from tarel.retrieval.plugins import installed_local_model_specs

DEFAULT_MODEL_NAME = "qwen3-embedding-0.6b-q4-k-m"
_QUERY_INSTRUCTION = (
    "Instruct: Retrieve relevant DWH, BI, ERP database tables and fields for this "
    "analytics question.\nQuery: "
)


def qwen_embedding_query(text: str) -> str:
    return f"{_QUERY_INSTRUCTION}{text.strip()}"


def model_cache_root() -> Path:
    override = os.getenv("TAREL_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    xdg_cache = os.getenv("XDG_CACHE_HOME")
    if xdg_cache:
        return Path(xdg_cache).expanduser() / "tarel"
    return Path.home() / ".cache" / "tarel"


def default_model_path(name: str = DEFAULT_MODEL_NAME) -> Path:
    return model_cache_root() / "models" / model_spec(name).filename


def model_spec(name: str) -> ModelSpec:
    specs = installed_local_model_specs()
    if not specs:
        raise RetrievalFailure(
            "missing_local_rag_dependency",
            "No local retrieval plugin is installed. "
            "Install `tarel-retrieval-llamacpp` from TAREL Hub.",
        )
    try:
        return specs[name]
    except KeyError as exc:
        raise RetrievalFailure("unknown_model", f"Unknown local retrieval model: {name}") from exc


def resolve_model_path(path: Path | None = None) -> Path:
    configured = path
    if configured is None:
        environment_path = os.getenv("TAREL_EMBEDDING_MODEL")
        configured = Path(environment_path) if environment_path else default_model_path()
    resolved = configured.expanduser().resolve()
    if not resolved.is_file():
        raise RetrievalFailure(
            "model_not_found",
            f"Embedding model not found: {resolved}. Run `tarel model download` or pass --model.",
        )
    if resolved.suffix.casefold() != ".gguf":
        raise RetrievalFailure("invalid_model", "Local embedding models must be GGUF files.")
    return resolved


def download_model(
    *,
    name: str = DEFAULT_MODEL_NAME,
    target: Path | None = None,
    force: bool = False,
    progress: Callable[[int, int], None] | None = None,
) -> ModelDownloadResult:
    spec = model_spec(name)
    _validate_model_source(spec.url)
    path = (target or default_model_path(name)).expanduser().resolve()
    if path.suffix.casefold() != ".gguf":
        raise RetrievalFailure("invalid_model_target", "Model target must end with .gguf.")
    if path.exists() and not force:
        if sha256_file(path) != spec.sha256:
            raise RetrievalFailure(
                "model_checksum_mismatch",
                f"Existing model has an unexpected checksum: {path}. Use --force to replace it.",
            )
        return ModelDownloadResult(path=path, spec=spec, reused=True)

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=".model-",
        suffix=".download",
    )
    temporary_path = Path(temporary_name)
    digest = hashlib.sha256()
    downloaded = 0
    try:
        request = urllib.request.Request(spec.url, headers={"User-Agent": "tarel/0.0.5"})
        # Model registry entries are immutable, checksum-pinned HTTPS URLs.
        with os.fdopen(descriptor, "wb") as output, urllib.request.urlopen(  # nosec B310
            request
        ) as response:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
                downloaded += len(chunk)
                if progress:
                    progress(downloaded, spec.size)
        if downloaded != spec.size or digest.hexdigest() != spec.sha256:
            raise RetrievalFailure(
                "model_checksum_mismatch",
                "Downloaded model did not match the pinned size and SHA-256 checksum.",
            )
        temporary_path.replace(path)
    except RetrievalFailure:
        temporary_path.unlink(missing_ok=True)
        raise
    except (OSError, urllib.error.URLError) as exc:
        temporary_path.unlink(missing_ok=True)
        raise RetrievalFailure(
            "model_download_failed",
            "Could not download embedding model.",
        ) from exc
    return ModelDownloadResult(path=path, spec=spec, reused=False)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_model_source(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise RetrievalFailure(
            "invalid_model_source",
            "Registered embedding models require a credential-free HTTPS source URL.",
        )
