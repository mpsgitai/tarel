"""Task-specific model discovery; remote catalogs are fetched only on request."""

from __future__ import annotations

from tarel.retrieval.contracts import RetrievalFailure
from tarel.retrieval.local import MODEL_SPECS, default_model_path
from tarel.retrieval.remote import HTTPRetrievalClient


def list_models(*, provider: str = "local", task: str = "embedding") -> dict[str, object]:
    if task not in {"embedding", "reranker"}:
        raise RetrievalFailure("invalid_retrieval_task", "Task must be embedding or reranker.")
    if provider == "local":
        models = [
            {
                "id": spec.name,
                "task": task,
                "installed": default_model_path(spec.name).is_file(),
                "downloadable": True,
                "size_bytes": spec.size,
                "source": spec.source,
            }
            for spec in MODEL_SPECS.values()
            if spec.task == task
        ]
    else:
        client = HTTPRetrievalClient(provider)
        if task == "reranker" and client.config.adapter == "openrouter":
            # Jev uses Decisions and is absent from the ordinary chat model catalog.
            models = [{"id": "typesafe/jev-1.13", "task": task, "adapter": "decisions"}]
        else:
            route = "/embeddings/models" if client.config.adapter == "openrouter" else "/models"
            data = client.request(route).get("data")
            if not isinstance(data, list) or any(
                not isinstance(row, dict) or not isinstance(row.get("id"), str) for row in data
            ):
                raise RetrievalFailure(
                    "invalid_retrieval_response", "Invalid provider model catalog."
                )
            models = [{"id": row["id"], "task": task} for row in data]
    return {"provider": provider, "task": task, "models": sorted(models, key=lambda row: row["id"])}
