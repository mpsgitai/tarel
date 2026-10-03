"""The same retrieval selection used by CLI and GUI."""

from tarel.retrieval.catalog import list_models
from tarel.retrieval.contracts import RetrievalFailure
from tarel.retrieval.settings import RetrievalSettings, load_settings, save_settings
from tarel.runtime import TarelRuntime


class RetrievalAPI:
    def __init__(self, runtime: TarelRuntime) -> None:
        self.runtime = runtime

    def settings(self) -> RetrievalSettings:
        return load_settings(self.runtime)

    def configure(self, settings: RetrievalSettings) -> RetrievalSettings:
        if self.runtime.retrieval_settings is not None:
            raise RetrievalFailure(
                "retrieval_settings_override", "This client has an explicit retrieval override. "
                "Use a client without an override to save project settings."
            )
        save_settings(self.runtime, settings)
        return settings

    def models(self, *, provider: str = "local", task: str = "embedding") -> dict[str, object]:
        return list_models(provider=provider, task=task)
