"""The discovery state machine: which actions a run allows next and how each changes it."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from tarel.discovery._parse import (
    identifier_array,
    require_choice,
    require_fields,
    require_identifier,
    require_object,
    require_text,
)
from tarel.discovery.contracts import DISCOVERY_ACTIONS, DISCOVERY_ACTORS, DiscoveryFailure
from tarel.discovery.identity import (
    IDENTITY_ACTIONS,
    EntityGroupReflection,
    IdentityFailure,
    add_group,
    add_manifest,
    add_page,
    add_reflection,
)
from tarel.discovery.programs import (
    DiscoveryProgram,
    ReferenceMappingManifest,
    discovery_program_from_dict,
)
from tarel.discovery.runs import (
    DiscoveryCandidate,
    DiscoveryObservation,
    DiscoveryRun,
    DiscoveryStep,
    latest_identity_reflection,
    validate_discovery_run,
    validate_identity_candidate,
)


def allowed_discovery_actions(run: DiscoveryRun) -> tuple[str, ...]:
    if run.status == "completed":
        return ()
    if run.status == "paused":
        return ("resume_run",)
    inspection = run.identity_inspection
    if inspection is not None:
        if inspection.manifest is None:
            return ("register_identity_inventory", "pause_run")
        if not inspection.coverage_complete:
            return ("record_inventory_page", "pause_run")
    actions: list[str] = []
    if len(run.candidates) < run.candidate_budget:
        actions.append("propose_candidate")
    active = [item for item in run.candidates if item.state not in {"selected", "rejected"}]
    if inspection is None:
        if run.kind == "reference_mapping" and any(
            item.mapping_manifest is None for item in active
        ):
            actions.append("register_mapping_manifest")
        observable = [
            item
            for item in active
            if run.kind != "reference_mapping" or item.mapping_manifest is not None
        ]
        if observable and run.probes_used < run.probe_budget:
            actions.append("record_observation")
        if any(item.state == "challenged" for item in active):
            actions.extend(("select_candidate", "reject_candidate"))
    else:
        missing_groups = [
            item for item in active if inspection.group_for_candidate(item.id) is None
        ]
        if missing_groups:
            actions.append("record_entity_group")
        if any(
            inspection.group_for_candidate(item.id) is not None for item in active
        ) and run.probes_used < run.probe_budget:
            actions.append("record_observation")
        challenged = [item for item in active if item.state == "challenged"]
        if any(latest_identity_reflection(run, item) is None for item in challenged):
            actions.append("record_entity_reflection")
        decisions = {
            item.id: (
                reflection.decision
                if (reflection := latest_identity_reflection(run, item))
                else None
            )
            for item in challenged
        }
        if any(
            decision in {"accept_as_exploratory", "recommend_promotion"}
            for decision in decisions.values()
        ):
            actions.append("select_candidate")
        if any(decision == "reject_group" for decision in decisions.values()):
            actions.append("reject_candidate")
    actions.append("pause_run")
    if (
        inspection is None
        and (run.candidates or run.scope_mode == "query_linked_slice")
    ) or (
        inspection is not None
        and (
            not run.candidates
            or any(item.state in {"rejected", "selected"} for item in run.candidates)
        )
    ):
        actions.append("complete_run")
    return tuple(actions)


def apply_discovery_action(
    run: DiscoveryRun,
    *,
    action: str,
    actor: str,
    payload: dict[str, Any],
) -> DiscoveryRun:
    action = require_choice(action, "action", DISCOVERY_ACTIONS)
    actor = require_choice(actor, "actor", DISCOVERY_ACTORS)
    if action not in allowed_discovery_actions(run):
        raise DiscoveryFailure(
            "discovery_action_not_allowed",
            f"Action {action} is not allowed for the current discovery state.",
        )
    if actor == "provider" and action not in {
        "propose_candidate",
        "record_entity_group",
        "record_entity_reflection",
    }:
        raise DiscoveryFailure(
            "discovery_action_not_allowed",
            "Providers may propose hypotheses, but cannot report evidence or make decisions.",
        )
    if action in IDENTITY_ACTIONS:
        return _apply_identity_action(run, action=action, actor=actor, payload=payload)
    if action == "propose_candidate":
        updated, candidate_id = _propose_candidate(run, payload)
        return _append_step(updated, actor, action, candidate_id=candidate_id)
    if action == "register_mapping_manifest":
        updated, candidate_id = _register_mapping_manifest(run, payload)
        return _append_step(updated, actor, action, candidate_id=candidate_id)
    if action == "record_observation":
        updated, candidate_id, observation_id = _record_observation(run, payload)
        return _append_step(
            updated,
            actor,
            action,
            candidate_id=candidate_id,
            observation_id=observation_id,
        )
    if action in {"select_candidate", "reject_candidate"}:
        updated, candidate_id, reason = _assess_candidate(run, action, payload)
        return _append_step(
            updated, actor, action, candidate_id=candidate_id, note=reason
        )
    require_fields(payload, {"reason"}, f"{action} payload")
    reason = require_text(payload.get("reason"), "reason")
    if action == "pause_run":
        return _append_step(replace(run, status="paused"), actor, action, note=reason)
    if action == "resume_run":
        return _append_step(replace(run, status="open"), actor, action, note=reason)
    return _append_step(
        replace(run, status="completed", completion_reason=reason),
        actor,
        action,
        note=reason,
    )


def _apply_identity_action(
    run: DiscoveryRun,
    *,
    action: str,
    actor: str,
    payload: dict[str, Any],
) -> DiscoveryRun:
    inspection = run.identity_inspection
    if inspection is None:
        raise DiscoveryFailure(
            "discovery_action_not_allowed",
            "This discovery run did not enable identity inspection.",
        )
    if actor == "provider" and action in {
        "record_inventory_page",
        "register_identity_inventory",
    }:
        raise DiscoveryFailure(
            "discovery_action_not_allowed",
            "Providers cannot attest inventory coverage or source execution.",
        )
    try:
        if action == "register_identity_inventory":
            changed_inspection = add_manifest(inspection, payload)
            candidate_id = None
            reference = None
        elif action == "record_inventory_page":
            changed_inspection = add_page(inspection, payload)
            candidate_id = None
            reference = changed_inspection.pages[-1].id
        elif action == "record_entity_group":
            changed_inspection = add_group(inspection, payload)
            group = changed_inspection.groups[-1]
            _candidate(run, group.candidate_id)
            candidate_id = group.candidate_id
            reference = group.id
        else:
            reflection = EntityGroupReflection.from_dict(payload)
            candidate = _candidate(run, reflection.candidate_id)
            challenge = next(
                (
                    item
                    for item in candidate.observations
                    if item.id == reflection.observation_id
                    and item.phase == "challenge"
                    and item.status == "succeeded"
                ),
                None,
            )
            if candidate.state != "challenged" or challenge is None:
                raise DiscoveryFailure(
                    "invalid_entity_reflection",
                    "Entity reflection requires a successful challenge observation.",
                )
            changed_inspection = add_reflection(inspection, payload)
            candidate_id = reflection.candidate_id
            reference = reflection.id
    except IdentityFailure as exc:
        raise DiscoveryFailure(exc.code, str(exc)) from exc
    return _append_step(
        replace(run, identity_inspection=changed_inspection),
        actor,
        action,
        candidate_id=candidate_id,
        observation_id=reference,
    )


def _propose_candidate(
    run: DiscoveryRun, payload: dict[str, Any]
) -> tuple[DiscoveryRun, str]:
    require_fields(
        payload,
        {"candidate_id", "parent_ids", "program", "variation_operator"},
        "propose_candidate payload",
    )
    candidate_id = require_identifier(payload.get("candidate_id"), "candidate_id")
    if any(item.id == candidate_id for item in run.candidates):
        raise DiscoveryFailure(
            "discovery_candidate_exists", f"Discovery candidate already exists: {candidate_id}"
        )
    parent_ids = identifier_array(payload.get("parent_ids"), "parent_ids")
    parents = {item.id: item for item in run.candidates}
    if any(parent not in parents for parent in parent_ids):
        raise DiscoveryFailure(
            "invalid_discovery", "Candidate parent does not exist in the current run."
        )
    generation = 0 if not parent_ids else max(parents[item].generation for item in parent_ids) + 1
    candidate = DiscoveryCandidate(
        id=candidate_id,
        kind=run.kind,
        generation=generation,
        parent_ids=parent_ids,
        variation_operator=require_identifier(
            payload.get("variation_operator"), "variation_operator"
        ),
        program=discovery_program_from_dict(
            require_object(payload.get("program"), "program")
        ),
    )
    if candidate.program.kind != run.kind:
        raise DiscoveryFailure(
            "invalid_discovery", "Candidate program does not match the run kind."
        )
    if run.identity_inspection is not None:
        validate_identity_candidate(run, candidate)
    return replace(run, candidates=(*run.candidates, candidate)), candidate.id


def _register_mapping_manifest(
    run: DiscoveryRun, payload: dict[str, Any]
) -> tuple[DiscoveryRun, str]:
    require_fields(
        payload,
        {"candidate_id", "mapping_count", "mapping_manifest_hash"},
        "register_mapping_manifest payload",
    )
    candidate_id = require_identifier(payload.get("candidate_id"), "candidate_id")
    candidate = _candidate(run, candidate_id)
    if candidate.kind != "reference_mapping":
        raise DiscoveryFailure(
            "discovery_action_not_allowed",
            "Mapping manifests belong only to reference-mapping candidates.",
        )
    if candidate.state != "proposed" or candidate.mapping_manifest is not None:
        raise DiscoveryFailure(
            "discovery_action_not_allowed",
            "A mapping manifest can be registered once before observations begin.",
        )
    manifest = ReferenceMappingManifest.from_dict(
        {
            "mapping_count": payload.get("mapping_count"),
            "mapping_manifest_hash": payload.get("mapping_manifest_hash"),
        }
    )
    changed = replace(candidate, mapping_manifest=manifest)
    return _replace_candidate(run, changed), candidate_id


def _record_observation(
    run: DiscoveryRun, payload: dict[str, Any]
) -> tuple[DiscoveryRun, str, str]:
    require_fields(payload, {"candidate_id", "observation"}, "record_observation payload")
    candidate_id = require_identifier(payload.get("candidate_id"), "candidate_id")
    observation = DiscoveryObservation.from_dict(
        require_object(payload.get("observation"), "observation")
    )
    candidate = _candidate(run, candidate_id)
    if candidate.state in {"selected", "rejected"}:
        raise DiscoveryFailure(
            "discovery_action_not_allowed", "Terminal candidates cannot receive observations."
        )
    if candidate.kind == "reference_mapping" and candidate.mapping_manifest is None:
        raise DiscoveryFailure(
            "mapping_manifest_required",
            "Register the value-free mapping manifest before executing probes.",
        )
    if (
        run.identity_inspection is not None
        and run.identity_inspection.group_for_candidate(candidate_id) is None
    ):
        raise DiscoveryFailure(
            "entity_alias_group_required",
            "Register the concrete entity alias group before executing probes.",
        )
    if (
        isinstance(candidate.program, DiscoveryProgram)
        and candidate.program.self_match is not None
        and observation.status == "succeeded"
        and observation.metrics is not None
        and observation.metrics.basis != "pairs"
    ):
        raise DiscoveryFailure(
            "invalid_discovery",
            "Self-entity observations must report canonical distinct-record pairs.",
        )
    if any(
        observation.id == current.id
        for current_candidate in run.candidates
        for current in current_candidate.observations
    ):
        raise DiscoveryFailure(
            "discovery_observation_exists",
            f"Discovery observation already exists: {observation.id}",
        )
    state = "challenged" if observation.phase == "challenge" else "tested"
    if candidate.state == "challenged" and observation.phase == "support":
        state = "challenged"
    changed = replace(
        candidate,
        state=state,
        observations=(*candidate.observations, observation),
    )
    return _replace_candidate(run, changed), candidate_id, observation.id


def _assess_candidate(
    run: DiscoveryRun, action: str, payload: dict[str, Any]
) -> tuple[DiscoveryRun, str, str]:
    require_fields(payload, {"candidate_id", "reason"}, f"{action} payload")
    candidate_id = require_identifier(payload.get("candidate_id"), "candidate_id")
    reason = require_text(payload.get("reason"), "reason")
    candidate = _candidate(run, candidate_id)
    if candidate.state != "challenged":
        raise DiscoveryFailure(
            "discovery_action_not_allowed",
            "Candidates must receive a challenge observation before assessment.",
        )
    if action == "select_candidate" and not any(
        item.phase == "challenge" and item.status == "succeeded"
        for item in candidate.observations
    ):
        raise DiscoveryFailure(
            "discovery_action_not_allowed",
            "Selection requires one successful challenge observation.",
        )
    if run.identity_inspection is not None:
        reflection = latest_identity_reflection(run, candidate)
        decision = reflection.decision if reflection else None
        allowed = (
            {"accept_as_exploratory", "recommend_promotion"}
            if action == "select_candidate"
            else {"reject_group"}
        )
        if decision not in allowed:
            raise DiscoveryFailure(
                "discovery_action_not_allowed",
                "Candidate assessment must follow its latest structured entity reflection.",
            )
    changed = replace(
        candidate,
        state="selected" if action == "select_candidate" else "rejected",
        assessment_reason=reason,
    )
    return _replace_candidate(run, changed), candidate_id, reason


def _append_step(
    run: DiscoveryRun,
    actor: str,
    action: str,
    *,
    candidate_id: str | None = None,
    observation_id: str | None = None,
    note: str | None = None,
) -> DiscoveryRun:
    changed = replace(
        run,
        steps=(
            *run.steps,
            DiscoveryStep(
                sequence=len(run.steps) + 1,
                actor=actor,
                action=action,
                candidate_id=candidate_id,
                observation_id=observation_id,
                note=note,
            ),
        ),
    )
    validate_discovery_run(changed)
    return changed


def _candidate(run: DiscoveryRun, candidate_id: str) -> DiscoveryCandidate:
    candidate = next((item for item in run.candidates if item.id == candidate_id), None)
    if candidate is None:
        raise DiscoveryFailure(
            "discovery_candidate_not_found", f"Discovery candidate not found: {candidate_id}"
        )
    return candidate


def _replace_candidate(run: DiscoveryRun, candidate: DiscoveryCandidate) -> DiscoveryRun:
    return replace(
        run,
        candidates=tuple(
            candidate if item.id == candidate.id else item for item in run.candidates
        ),
    )
