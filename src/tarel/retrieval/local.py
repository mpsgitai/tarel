"""Explicit model download and lazy llama.cpp embedding adapter."""

from __future__ import annotations

import hashlib
import math
import os
import tempfile
import threading
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from tarel.retrieval.contracts import RetrievalFailure

DEFAULT_MODEL_NAME = "qwen3-embedding-0.6b-q4-k-m"
# The most tokens one text may occupy, including special tokens and the query instruction. llama.cpp
# caps a text at n_batch and silently cuts it at truncate=True, so both follow this value.
EMBEDDING_TOKEN_CAPACITY = 2048
# A physical batch only splits the decode: it trades no accuracy but about 1 GB of memory at the
# full capacity (measured with the pinned model on CPU), so it stays small.
_LLAMA_PHYSICAL_BATCH = 256
LOCAL_EMBEDDING_INPUT = (
    f"llama.cpp:max_tokens={EMBEDDING_TOKEN_CAPACITY}:overflow=recorded_document_cut"
)
_QUERY_INSTRUCTION = (
    "Instruct: Retrieve relevant DWH, BI, ERP database tables and fields for this "
    "analytics question.\nQuery: "
)


def qwen_embedding_query(text: str) -> str:
    return f"{_QUERY_INSTRUCTION}{text.strip()}"


@dataclass(frozen=True, slots=True)
class ModelSpec:
    name: str
    filename: str
    url: str
    sha256: str
    size: int
    source: str
    task: str = "embedding"


@dataclass(frozen=True, slots=True)
class ModelDownloadResult:
    path: Path
    spec: ModelSpec
    reused: bool


MODEL_SPECS = {
    DEFAULT_MODEL_NAME: ModelSpec(
        name=DEFAULT_MODEL_NAME,
        filename="qwen3-embedding-0.6b-q4-k-m.gguf",
        url=(
            "https://huggingface.co/enacimie/"
            "Qwen3-Embedding-0.6B-Q4_K_M-GGUF/resolve/"
            "51fe2a65af23d8cfd3c9c1d89846cf9073f8902b/"
            "qwen3-embedding-0.6b-q4_k_m.gguf"
        ),
        sha256="17c3e3f2eaabc6e321702b4a13680d042e72afc5d602f359f27a670c3e54718c",
        size=396_474_560,
        source="https://huggingface.co/enacimie/Qwen3-Embedding-0.6B-Q4_K_M-GGUF",
    ),
    "qwen3-reranker-0.6b-q4-k-m": ModelSpec(
        name="qwen3-reranker-0.6b-q4-k-m",
        filename="Qwen3-Reranker-0.6B-q4_k_m.gguf",
        url=("https://huggingface.co/Mungert/Qwen3-Reranker-0.6B-GGUF/resolve/"
             "041387f8ed7ead711b9496b153b682c5b2f5d158/Qwen3-Reranker-0.6B-q4_k_m.gguf"),
        sha256="66867f47323e058f9dbfe24a13268859a84d9e9a8bb89ad0789c7c52131267e2",
        size=394_705_248,
        source="https://huggingface.co/Mungert/Qwen3-Reranker-0.6B-GGUF",
        task="reranker",
    ),
}


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
    try:
        return MODEL_SPECS[name]
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
        request = urllib.request.Request(spec.url, headers={"User-Agent": "tarel/0.0.1"})
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


class LlamaCppEmbedding:
    """CPU-only Qwen-compatible embeddings without LlamaIndex or a server."""

    def __init__(
        self,
        model_path: Path,
        *,
        n_threads: int | None = None,
    ) -> None:
        resolved = resolve_model_path(model_path)
        try:
            import llama_cpp
            from llama_cpp import Llama
        except ImportError as exc:
            raise RetrievalFailure(
                "missing_local_rag_dependency",
                "llama-cpp-python is not installed. Install `tarel[local-rag]`.",
            ) from exc
        threads = n_threads or max(1, (os.cpu_count() or 2) - 1)
        self._model_path = resolved
        version = getattr(llama_cpp, "__version__", "")
        self._runtime_version = f"llama-cpp-python {version}" if version else ""
        self._embedding_lock = threading.Lock()
        self._model: Any = Llama(
            model_path=str(resolved),
            n_ctx=EMBEDDING_TOKEN_CAPACITY,
            n_batch=EMBEDDING_TOKEN_CAPACITY,
            n_ubatch=_LLAMA_PHYSICAL_BATCH,
            n_threads=threads,
            n_gpu_layers=0,
            embedding=True,
            verbose=False,
        )

    @property
    def model_id(self) -> str:
        return self._model_path.name

    @property
    def input_strategy(self) -> str:
        return LOCAL_EMBEDDING_INPUT

    @property
    def max_input_tokens(self) -> int:
        return EMBEDDING_TOKEN_CAPACITY

    @property
    def runtime_version(self) -> str:
        return self._runtime_version

    def token_count(self, text: str) -> int:
        """Count tokens as ``embed`` will see them, including special tokens it adds."""
        with self._embedding_lock:
            return len(self._model.tokenize(text.encode("utf-8")))

    def embed_documents(
        self,
        texts: tuple[str, ...],
        *,
        batch_size: int,
    ) -> tuple[tuple[float, ...], ...]:
        if not 1 <= batch_size <= 256:
            raise RetrievalFailure("invalid_batch_size", "Batch size must be between 1 and 256.")
        vectors: list[tuple[float, ...]] = []
        # batch_size counts documents for scheduling; token capacity applies to each document,
        # because llama.cpp decodes them one at a time here.
        for offset in range(0, len(texts), batch_size):
            batch = texts[offset : offset + batch_size]
            for position, text in enumerate(batch, start=offset + 1):
                vectors.append(self._embed(text, f"Document {position} of {len(texts)}"))
        return tuple(vectors)

    def embed_query(self, text: str) -> tuple[float, ...]:
        return self._embed(qwen_embedding_query(text), "Query with its retrieval instruction")

    def embed_cut_document(self, text: str) -> tuple[float, ...]:
        """Embed only the first tokens of a text whose caller records that it was shortened."""
        try:
            with self._embedding_lock:
                embedded = self._model.embed(text, normalize=True, truncate=True)
        except Exception as exc:
            raise RetrievalFailure(
                "embedding_failed", "llama.cpp failed while embedding a shortened document.",
            ) from exc
        return _normalized_vector(embedded)

    def _embed(self, text: str, label: str) -> tuple[float, ...]:
        """Embed the whole text or refuse it; never let llama.cpp shorten it."""
        tokens = self.token_count(text)
        if tokens > EMBEDDING_TOKEN_CAPACITY:
            raise RetrievalFailure(
                "embedding_input_too_long",
                f"{label} has {tokens} tokens; the embedding limit is "
                f"{EMBEDDING_TOKEN_CAPACITY}. Nothing was shortened.",
            )
        try:
            with self._embedding_lock:
                embedded = self._model.embed(text, normalize=True, truncate=False)
        except Exception as exc:
            raise RetrievalFailure(
                "embedding_failed", f"llama.cpp failed while embedding: {label.lower()}.",
            ) from exc
        return _normalized_vector(embedded)


def _normalized_vector(value: object) -> tuple[float, ...]:
    if not isinstance(value, list) or not value:
        raise RetrievalFailure("embedding_failed", "Embedding must be a non-empty number array.")
    try:
        vector = tuple(float(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise RetrievalFailure("embedding_failed", "Embedding contains a non-number.") from exc
    if not all(math.isfinite(item) for item in vector):
        raise RetrievalFailure("embedding_failed", "Embedding contains a non-finite number.")
    magnitude = math.sqrt(sum(item * item for item in vector))
    if magnitude == 0:
        raise RetrievalFailure("embedding_failed", "Embedding has zero magnitude.")
    return tuple(item / magnitude for item in vector)
