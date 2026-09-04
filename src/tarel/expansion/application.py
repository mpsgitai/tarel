"""Validated base scope and bounded delta compilation shared by CLI and SDK."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from tarel.context import ContextResult
from tarel.context_output import canonical_json
from tarel.context_packets import (
    ContextPacketSnapshot,
    context_packet_from_dict,
    context_packet_graph_identity,
)
from tarel.expansion.contracts import (
    ContextExpansion,
    ContextExpansionFailure,
    ExpansionInput,
    ExpansionTarget,
    invalid,
)
from tarel.graph.revision import graph_revision
from tarel.runtime import TarelRuntime


def expand_context_use_case(
    packet: ContextResult | ContextPacketSnapshot | dict[str, object],
    targets: tuple[ExpansionTarget, ...],
    *,
    mode: str = "confirmed_only",
    inputs: Mapping[str, ExpansionInput] | None = None,
    max_characters: int = 24_000,
    runtime: TarelRuntime | None = None,
) -> ContextExpansion:
    if (
        not isinstance(targets, tuple)
        or not 1 <= len(targets) <= 32
        or any(not isinstance(item, ExpansionTarget) for item in targets)
    ):
        invalid("Supply 1–32 typed expansion targets.")
    if mode not in ("confirmed_only", "include_candidates"):
        invalid("Choose confirmed_only or explicitly include_candidates.")
    if type(max_characters) is not int or not 1000 <= max_characters <= 1_000_000:
        invalid("Expansion character budget must be 1000–1000000.")
    if inputs is not None and (
        not isinstance(inputs, Mapping)
        or any(
            not isinstance(key, str) or not isinstance(value, ExpansionInput)
            for key, value in inputs.items()
        )
    ):
        invalid("Inputs must map private handles to typed ephemeral ExpansionInput values.")
    if isinstance(packet, ContextResult):
        snapshot = context_packet_from_dict(packet.to_dict())
    elif isinstance(packet, ContextPacketSnapshot):
        snapshot = context_packet_from_dict(
            {
                "contract_version": packet.contract_version,
                "stable": packet.stable,
                "dynamic": packet.dynamic,
                "identity": {
                    "stable_hash": packet.stable_hash,
                    "dynamic_hash": packet.dynamic_hash,
                    "packet_hash": packet.packet_hash,
                },
            }
        )
    elif isinstance(packet, dict):
        snapshot = context_packet_from_dict(packet)
    else:
        invalid("Supply a real context packet, not an asserted packet hash.")
    runtime = runtime or TarelRuntime.local(Path.cwd() / ".tarel")
    boundaries, validation = _scope(snapshot, runtime)
    items, omissions = [], []
    from tarel.expansion.projections import project_expansion_target

    for index, target in enumerate(targets):
        if target.graph not in boundaries:
            omissions.append((index, "expansion_outside_scope"))
            continue
        private = (inputs or {}).get(target.handle) if target.handle is not None else None
        if target.handle is not None and private is None:
            omissions.append((index, "expansion_input_missing"))
            continue
        try:
            expected, allowed, namespace = boundaries[target.graph]
            item = project_expansion_target(
                target,
                expected_revision=expected,
                allowed=allowed,
                namespace=namespace,
                mode=mode,
                private=private,
                runtime=runtime,
            )
        except RuntimeError as exc:
            # Only known TAREL failures have a sanitized stable code. Programming and
            # infrastructure exceptions without this contract remain visible exceptions.
            code = getattr(exc, "code", None)
            if not isinstance(code, str) or not code.replace("_", "").isalnum():
                raise
            omissions.append((index, code))
            continue
        trial = ContextExpansion(
            snapshot.packet_hash,
            tuple((*items, item)),
            tuple(omissions),
            max_characters,
            validation,
        )
        # Reserve enough envelope space for one explicit omission per remaining target.
        reserved = replace(
            trial,
            omissions=tuple(
                (
                    *omissions,
                    *(
                        (remaining, "expansion_character_budget")
                        for remaining in range(index + 1, len(targets))
                    ),
                )
            ),
        )
        if len(canonical_json(reserved.to_dict())) > max_characters:
            omissions.append((index, "expansion_character_budget"))
        else:
            items.append(item)
    result = ContextExpansion(
        snapshot.packet_hash, tuple(items), tuple(omissions), max_characters, validation
    )
    if len(canonical_json(result.to_dict())) > max_characters:
        raise ContextExpansionFailure(
            "expansion_budget_too_small", "Budget cannot fit the result envelope."
        )
    return result


def _scope(
    packet: ContextPacketSnapshot,
    runtime: TarelRuntime,
) -> tuple[
    dict[str, tuple[str, frozenset[str] | None, str | None]], tuple[tuple[str, str, bool], ...]
]:
    name, revision = context_packet_graph_identity(packet)
    scope = packet.stable.get("scope")
    if not isinstance(scope, dict):
        invalid("Base packet requires an explicit scope.")
    workspace_name = scope.get("workspace")
    if workspace_name is None:
        header = runtime.graph_store().header(name)
        if header.revision != revision:
            raise ContextExpansionFailure(
                "stale_expansion_base", "Base graph changed; rebuild its context."
            )
        namespace = scope.get("namespace")
        if namespace is not None and not isinstance(namespace, str):
            invalid("Base namespace is invalid.")
        return {name: (revision, None, namespace)}, (
            (name, header.read_stats.mode, header.read_stats.full_document_read),
        )
    # Workspace scope includes zones/relationships; revalidate using its existing authoritative
    # compiler. This path may read complete graphs; single-graph expansion stays selective.
    from tarel.application import _load_workspace_scope
    from tarel.workspaces.projection import project_workspace_scope

    selections = {}
    for key in ("systems", "graphs", "areas", "schemas", "zones"):
        values = scope.get(key, [])
        if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
            invalid("Base workspace selection is invalid.")
        selections[key] = tuple(values)
    workspace, graphs, resolved = _load_workspace_scope(
        workspace_name, runtime=runtime, **selections
    )
    projection = project_workspace_scope(workspace, graphs, resolved)
    if projection.name != name or graph_revision(projection) != revision:
        raise ContextExpansionFailure(
            "stale_expansion_base", "Workspace context changed; rebuild it."
        )
    return {
        name: (
            graph_revision(graphs[name]),
            frozenset(item.object_id for item in resolved.objects if item.graph == name),
            None,
        )
        for name in resolved.graph_names
    }, tuple((name, "full_workspace_scope_validation", True) for name in resolved.graph_names)
