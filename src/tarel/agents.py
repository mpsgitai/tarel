"""Install packaged, optional coding-agent instructions into a user project."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


class AgentSetupFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class AgentSetupResult:
    agent: str
    path: Path
    changed: bool


def setup_agent_skill_use_case(
    agent: str,
    *,
    target: Path | None = None,
    force: bool = False,
) -> AgentSetupResult:
    if agent != "codex":
        raise AgentSetupFailure(
            "unsupported_agent_setup",
            "The first discovery-skill installer supports codex only.",
        )
    project = (target or Path.cwd()).expanduser().resolve()
    destination = project / ".agents" / "skills" / "tarel-discovery"
    if destination.exists() and not force:
        raise AgentSetupFailure(
            "agent_skill_exists",
            f"TAREL discovery skill already exists: {destination}",
        )
    source = resources.files("tarel").joinpath(
        "agent_resources", "skills", "tarel-discovery"
    )
    try:
        with resources.as_file(source) as source_path:
            if not (source_path / "SKILL.md").is_file():
                raise AgentSetupFailure(
                    "agent_skill_missing",
                    "The installed TAREL package does not contain its discovery skill.",
                )
            if destination.exists():
                shutil.rmtree(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_path, destination)
    except AgentSetupFailure:
        raise
    except OSError as exc:
        raise AgentSetupFailure(
            "agent_setup_failed", "Could not install the TAREL discovery skill."
        ) from exc
    return AgentSetupResult(agent=agent, path=destination, changed=True)
