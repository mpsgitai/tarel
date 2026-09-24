"""Explicit filesystem-writing setup helpers for embedded integrations."""

from __future__ import annotations

from pathlib import Path

from tarel.agents import AgentSetupResult, setup_agent_skill_use_case
from tarel.application import (
    create_demo_use_case,
    scaffold_connector_use_case,
    scaffold_provider_use_case,
)
from tarel.connectors.authoring import ScaffoldResult
from tarel.demo import DemoCreateResult
from tarel.providers.authoring import ProviderScaffoldResult


def create_demo(
    name: str,
    *,
    path: str | Path,
    version: int = 1,
    force: bool = False,
) -> DemoCreateResult:
    """Create a deterministic demo at an explicit path."""
    return create_demo_use_case(name, path=Path(path), version=version, force=force)


def scaffold_connector(name: str, *, output: str | Path) -> ScaffoldResult:
    """Create an inactive connector candidate at an explicit path."""
    return scaffold_connector_use_case(name, output=Path(output))


def scaffold_provider(name: str, *, output: str | Path) -> ProviderScaffoldResult:
    """Create an inactive provider candidate at an explicit path."""
    return scaffold_provider_use_case(name, output=Path(output))


def install_agent_skill(
    agent: str,
    *,
    target: str | Path,
    force: bool = False,
) -> AgentSetupResult:
    """Install packaged agent instructions into one explicit project."""
    return setup_agent_skill_use_case(agent, target=Path(target), force=force)
