"""Independent model choices; project settings contain no credentials."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING

from tarel.retrieval.contracts import RetrievalFailure
from tarel.retrieval.local import DEFAULT_MODEL_NAME, default_model_path, model_spec

if TYPE_CHECKING:
    from tarel.runtime import TarelRuntime

_PROVIDER = re.compile(r"^[a-z][a-z0-9_-]*$")
_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:+-]{0,255}$")


@dataclass(frozen=True, slots=True)
class ModelChoice:
    provider: str = "local"
    model: str = DEFAULT_MODEL_NAME
    model_path: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or not _PROVIDER.fullmatch(self.provider):
            raise RetrievalFailure("invalid_retrieval_settings", "Invalid provider profile name.")
        if not isinstance(self.model, str) or not _MODEL.fullmatch(self.model):
            raise RetrievalFailure("invalid_retrieval_settings", "Invalid model identifier.")
        if self.model_path is not None:
            if (
                self.provider != "local"
                or not isinstance(self.model_path, str)
                or not self.model_path
            ):
                raise RetrievalFailure("invalid_retrieval_settings", "Model paths are local only.")
            object.__setattr__(
                self, "model_path", str(Path(self.model_path).expanduser().resolve())
            )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RetrievalSettings:
    embedding: ModelChoice = field(default_factory=ModelChoice)
    reranker: ModelChoice | None = None
    rerank_depth: int = 10

    def __post_init__(self) -> None:
        if not isinstance(self.embedding, ModelChoice) or (
            self.reranker is not None and not isinstance(self.reranker, ModelChoice)
        ):
            raise RetrievalFailure("invalid_retrieval_settings", "Invalid model choice.")
        if type(self.rerank_depth) is not int or not 1 <= self.rerank_depth <= 100:
            raise RetrievalFailure("invalid_retrieval_settings", "Rerank depth must be 1–100.")
        for task, choice in (("embedding", self.embedding), ("reranker", self.reranker)):
            if (
                choice is not None and choice.provider == "local"
                and model_spec(choice.model).task != task
            ):
                raise RetrievalFailure("invalid_retrieval_settings", "Model has the wrong task.")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> RetrievalSettings:
        try:
            if set(payload) - {"embedding", "reranker", "rerank_depth"}:
                raise TypeError
            embedding = payload.get("embedding", {})
            reranker = payload.get("reranker")
            if not isinstance(embedding, dict) or (
                reranker is not None and not isinstance(reranker, dict)
            ):
                raise TypeError
            return cls(
                ModelChoice(**embedding),
                None if reranker is None else ModelChoice(**reranker),
                payload.get("rerank_depth", 10),
            )
        except TypeError as exc:
            raise RetrievalFailure(
                "invalid_retrieval_settings", "Invalid retrieval configuration."
            ) from exc


def settings_path(runtime: TarelRuntime | None) -> Path:
    return (runtime.root if runtime is not None else Path.cwd() / ".tarel") / "retrieval.json"


def load_settings(runtime: TarelRuntime | None) -> RetrievalSettings:
    if runtime is not None and runtime.retrieval_settings is not None:
        return runtime.retrieval_settings
    path = settings_path(runtime)
    if not path.is_file():
        return RetrievalSettings()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError
        return RetrievalSettings.from_dict(payload)
    except (OSError, ValueError) as exc:
        raise RetrievalFailure(
            "invalid_retrieval_settings", "Cannot read retrieval configuration."
        ) from exc


def snapshot_runtime(runtime: TarelRuntime | None) -> TarelRuntime | None:
    # A GUI selection change must not mix model/index choices within a running request.
    if runtime is not None and runtime.retrieval_settings is not None:
        return runtime
    if not settings_path(runtime).is_file():
        return runtime
    from tarel.runtime import TarelRuntime

    return replace(
        runtime or TarelRuntime.local(Path.cwd() / ".tarel"),
        retrieval_settings=load_settings(runtime),
    )


def save_settings(runtime: TarelRuntime | None, settings: RetrievalSettings) -> dict[str, object]:
    path = settings_path(runtime)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".retrieval-", suffix=".json")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(settings.to_dict(), stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return settings.to_dict()


def index_namespace(runtime: TarelRuntime | None) -> str | None:
    # Preserve existing paths until users explicitly opt into a model selection.
    if not settings_path(runtime).is_file() and (
        runtime is None or runtime.retrieval_settings is None
    ):
        return None
    choice = load_settings(runtime).embedding
    if choice == ModelChoice():
        return None
    payload = choice.to_dict()
    if choice.provider != "local":
        from tarel.providers.config import load_http_provider_config

        payload["base_url"] = load_http_provider_config(choice.provider).base_url
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]


def selected_local_path(runtime: TarelRuntime | None, override: Path | None) -> Path | None:
    choice = load_settings(runtime).embedding
    if choice.provider != "local":
        if override is not None:
            raise RetrievalFailure(
                "invalid_retrieval_settings", "A cloud embedding cannot use --model."
            )
        return None
    if override is not None:
        return override
    if choice.model_path is not None:
        return Path(choice.model_path)
    # Keep the existing environment override for the default local model.
    return None if choice.model == DEFAULT_MODEL_NAME else default_model_path(choice.model)
