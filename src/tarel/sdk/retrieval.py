"""The same retrieval selection used by CLI and GUI."""

from tarel.retrieval.catalog import list_models
from tarel.retrieval.settings import RetrievalSettings, load_settings, save_settings
from tarel.runtime import TarelRuntime


class RetrievalAPI:
    def __init__(self, runtime: TarelRuntime) -> None:
        self.runtime = runtime

    def settings(self) -> RetrievalSettings:
        return load_settings(self.runtime)

    def configure(self, settings: RetrievalSettings) -> RetrievalSettings:
        save_settings(self.runtime, settings)
        return settings

    def models(self, *, provider: str = "local", task: str = "embedding") -> dict[str, object]:
        return list_models(provider=provider, task=task)
