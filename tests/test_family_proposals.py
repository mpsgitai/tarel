from __future__ import annotations

import json
import os
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from tarel.cli import main
from tarel.connectors.contracts import CatalogField, CatalogObject, CatalogResult
from tarel.graph.build import build_graph_from_catalog
from tarel.object_families.application import propose_object_family_use_case
from tarel.object_families.contracts import ObjectFamilyFailure
from tarel.object_families.proposal_contracts import FamilyProposalRun, digest
from tarel.object_families.proposals import (
    load_family_proposals_use_case,
    plan_family_proposals_use_case,
    run_family_proposals_use_case,
)
from tarel.providers.config import configure_http_provider
from tarel.providers.contracts import ProviderFailure
from tarel.runtime import TarelRuntime
from tarel.sdk import Tarel


def _catalog():
    sale = (
        CatalogField("sale_id", 1, "INTEGER", False),
        CatalogField("amount", 2, "DECIMAL(12,2)", False),
    )
    event = (CatalogField("event_id", 1, "INTEGER", False),)
    return build_graph_from_catalog(
        "commerce",
        CatalogResult(
            connector="test",
            source_type="database",
            catalog="Test",
            dialect="sqlite",
            objects=(
                *(
                    CatalogObject("sales", f"sales_2024_{month:02d}", "table", sale)
                    for month in range(1, 5)
                ),
                CatalogObject("tenant_042", "events", "table", event),
                CatalogObject("tenant_043", "events", "table", event),
                CatalogObject(
                    "unrelated",
                    "singleton",
                    "table",
                    (CatalogField("unique_field", 1, "TEXT", True),),
                ),
            ),
        ),
    )


def _proposal(request):
    inventory = json.loads(request.messages[-1].content)
    ids = [item["id"] for item in inventory["objects"]]
    return {
        "families": [
            {
                "name": "logical_" + digest(ids)[:12],
                "member_ids": ids,
                "grain": [inventory["schema"][0]["name"]],
                "attributes": [],
            }
        ],
        "unassigned_object_ids": [],
    }


class _Provider:
    name = "local"
    default_model = "test-model"

    def __init__(self, response=_proposal):
        self.response = response
        self.requests = []

    def generate_structured(self, request):
        self.requests.append(request)
        return self.response(request)


class FamilyProposalTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.project = Path(self.directory.name)
        self.runtime = TarelRuntime.local(self.project / ".tarel")
        self.graph = _catalog()
        self.runtime.graph_store().save(self.graph)
        self.provider = _Provider()
        provider_patch = patch(
            "tarel.object_families.proposals.load_provider", return_value=self.provider
        )
        provider_patch.start()
        self.addCleanup(provider_patch.stop)

    def plan(self, run_id="families", **options):
        return plan_family_proposals_use_case(
            "commerce",
            run_id,
            provider_name="local",
            runtime=self.runtime,
            **options,
        )

    def execute(self, run_id="families", **options):
        return run_family_proposals_use_case(run_id, runtime=self.runtime, **options)

    def test_plan_sends_nothing_and_counts_every_object(self):
        run = self.plan()
        self.assertEqual(self.provider.requests, [])
        self.assertEqual(run.total_objects, 7)
        self.assertEqual(run.to_dict()["planned_objects"], 6)
        self.assertEqual(dict(run.omissions), {"no_compatible_peer": 1})
        self.assertEqual([len(batch.object_ids) for batch in run.batches], [4, 2])
        stored = load_family_proposals_use_case(run.id, runtime=self.runtime)
        self.assertEqual(stored, run)
        path = self.runtime.root / "family-proposals" / "families.json"
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        for forbidden in ("messages", "schema_name", "system", "prompt", "base_url", "api_key"):
            self.assertNotIn(forbidden, path.read_text())

    def test_success_persists_candidates_only_and_keeps_physical_graph_unchanged(self):
        baseline = self.runtime.graph_store().load("commerce").to_dict()
        self.plan()
        run = self.execute(workers=2)
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.to_dict()["saved_candidates"], 2)
        self.assertEqual(len(self.provider.requests), 2)
        store = self.runtime.object_family_store()
        for batch in run.batches:
            self.assertEqual(batch.attempts, 1)
            self.assertEqual(batch.status, "completed")
            family = store.load("commerce", batch.outcomes[0].family_id)
            self.assertEqual(family.state, "candidate")
            self.assertIsNone(family.review)
            self.assertEqual(family.producer, "llm_family_batch")
        self.assertEqual(self.runtime.graph_store().load("commerce").to_dict(), baseline)

    def test_provider_receives_allowlisted_metadata_not_annotations_or_samples(self):
        node = next(node for node in self.graph.nodes if node.type == "table")
        changed = replace(
            node,
            metadata={
                **node.metadata,
                "raw_rows": ["PRIVATE-ROW"],
                "connection": "password=PRIVATE-SECRET",
            },
        )
        graph = replace(
            self.graph, nodes=tuple(changed if n.id == node.id else n for n in self.graph.nodes)
        )
        self.runtime.graph_store().save(graph)
        self.plan()
        self.execute()
        content = json.dumps([request.messages[-1].content for request in self.provider.requests])
        self.assertNotIn("PRIVATE", content)
        self.assertNotIn("raw_rows", content)
        self.assertNotIn("connection", content)
        self.assertTrue(all(request.model == "test-model" for request in self.provider.requests))

    def test_llm_can_decline_all_schema_compatible_objects(self):
        def decline(request):
            ids = [item["id"] for item in json.loads(request.messages[-1].content)["objects"]]
            return {"families": [], "unassigned_object_ids": ids}

        self.provider.response = decline
        self.plan()
        run = self.execute()
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.to_dict()["saved_candidates"], 0)
        self.assertEqual(sum(batch.unassigned_count for batch in run.batches), 6)

    def test_incomplete_duplicate_foreign_and_extra_provider_fields_fail_closed(self):
        transforms = (
            lambda raw: {**raw, "families": []},
            lambda raw: {**raw, "unassigned_object_ids": [raw["families"][0]["member_ids"][0]]},
            lambda raw: {**raw, "unassigned_object_ids": ["foreign:table"]},
            lambda raw: {**raw, "review": {"source": "human", "decision": "approve"}},
        )
        for index, transform in enumerate(transforms):
            with self.subTest(index=index):
                self.provider.response = lambda req, transform=transform: transform(_proposal(req))
                self.plan(f"bad-{index}")
                run = self.execute(f"bad-{index}")
                self.assertEqual(run.status, "partial")
                self.assertTrue(all(batch.status == "failed" for batch in run.batches))
                self.assertEqual(run.to_dict()["saved_candidates"], 0)
        self.assertEqual(self.runtime.object_family_store().list("commerce"), ())

    def test_invalid_grain_is_individual_failure_and_valid_other_batch_is_saved(self):
        def mixed(request):
            raw = _proposal(request)
            if len(raw["families"][0]["member_ids"]) == 4:
                raw["families"][0]["grain"] = ["not-a-field"]
            return raw

        self.provider.response = mixed
        self.plan()
        run = self.execute()
        self.assertEqual(run.status, "partial")
        self.assertEqual(run.to_dict()["saved_candidates"], 1)
        self.assertEqual(run.batches[0].outcomes[0].error_code, "invalid_object_family")
        self.assertEqual(run.batches[1].outcomes[0].status, "saved_candidate")
        before = len(self.provider.requests)
        self.assertEqual(self.execute(resume=True), run)
        self.assertEqual(len(self.provider.requests), before)

    def test_provider_failure_is_sanitized_and_resume_retries_only_failed_batch(self):
        def flaky(request):
            if len(json.loads(request.messages[-1].content)["objects"]) == 4:
                raise ProviderFailure("SECRET-KEY", "password=PRIVATE-HTTP-BODY")
            return _proposal(request)

        self.provider.response = flaky
        self.plan()
        run = self.execute()
        self.assertEqual(run.batches[0].error_code, "provider_generation_failed")
        self.assertEqual(run.batches[1].status, "completed")
        self.assertNotIn("PRIVATE", json.dumps(run.to_dict()))
        self.assertNotIn("SECRET", json.dumps(run.to_dict()))
        self.provider.response = _proposal
        resumed = self.execute(resume=True)
        self.assertEqual(resumed.status, "completed")
        self.assertEqual([batch.attempts for batch in resumed.batches], [2, 1])
        self.assertEqual(len(self.provider.requests), 3)
        self.assertEqual(self.execute(resume=True), resumed)

    def test_resume_requires_same_graph_request_and_explicit_flag(self):
        run = self.plan()
        self.execute()
        with self.assertRaises(ObjectFamilyFailure) as failure:
            self.execute()
        self.assertEqual(failure.exception.code, "family_proposals_started")
        node = next(node for node in self.graph.nodes if node.type == "field")
        changed = replace(node, metadata={**node.metadata, "data_type": "TEXT"})
        self.runtime.graph_store().save(
            replace(
                self.graph,
                nodes=tuple(changed if item.id == node.id else item for item in self.graph.nodes),
            )
        )
        with self.assertRaises(ObjectFamilyFailure) as failure:
            self.execute(resume=True)
        self.assertEqual(failure.exception.code, "stale_family_proposals")
        self.assertEqual(run.model, "test-model")

    def test_existing_members_are_omitted_and_race_overlap_is_visible(self):
        self.plan()
        propose_object_family_use_case(
            "commerce",
            "manual",
            name="manual_sales",
            members=("sales.sales_2024_01", "sales.sales_2024_02"),
            grain=("sale_id",),
            runtime=self.runtime,
        )
        run = self.execute()
        self.assertEqual(run.batches[0].outcomes[0].error_code, "object_family_overlap")
        plan = self.plan("next")
        self.assertEqual(dict(plan.omissions)["existing_family"], 4)
        self.assertEqual(plan.to_dict()["planned_objects"], 2)

    def test_object_and_batch_budgets_are_explicit_not_global_completeness(self):
        run = self.plan(max_objects=3, objects_per_batch=2)
        self.assertEqual(run.to_dict()["planned_objects"], 2)
        self.assertGreater(dict(run.omissions)["object_limit"], 0)
        self.assertGreater(dict(run.omissions)["batch_boundary"], 0)
        self.assertEqual(sum(dict(run.omissions).values()) + 2, 7)
        result = self.execute()
        self.assertEqual(result.status, "completed")
        self.assertTrue(result.omissions)

    def test_input_budget_reports_omitted_schema_without_making_requests(self):
        run = self.plan(max_input_chars=2_000)
        self.assertEqual(run.to_dict()["planned_objects"], 0)
        self.assertEqual(dict(run.omissions)["input_budget"], 6)
        self.assertEqual(self.execute().status, "completed")
        self.assertEqual(self.provider.requests, [])

    def test_plan_limits_paths_and_existing_ids_reject_before_generation(self):
        for options in (
            {"objects_per_batch": 1},
            {"max_objects": True},
            {"max_input_chars": 2_000_001},
            {"model": "secret\npath"},
        ):
            with self.subTest(options=options), self.assertRaises(ObjectFamilyFailure):
                self.plan(**options)
        with self.assertRaises(ObjectFamilyFailure):
            self.plan("../escape")
        self.plan()
        with self.assertRaises(ObjectFamilyFailure):
            self.plan()
        for options in (
            {"workers": 0},
            {"workers": 9},
            {"timeout": float("nan")},
            {"resume": "yes"},
        ):
            with self.subTest(options=options), self.assertRaises(ObjectFamilyFailure):
                self.execute(**options)
        self.assertEqual(self.provider.requests, [])

    def test_checkpoint_integrity_rejects_unknown_fields_hashes_and_duplicate_ids(self):
        run = self.plan()
        for key, value in (
            ("prompt", "PRIVATE"),
            ("revision", "a" * 64),
            ("planned_objects", 7),
            ("total_objects", 42),
        ):
            with self.subTest(key=key), self.assertRaises(ObjectFamilyFailure):
                FamilyProposalRun.from_dict({**run.to_dict(), key: value})
        data = run.to_dict()
        data["batches"].append(data["batches"][0])
        with self.assertRaises(ObjectFamilyFailure):
            FamilyProposalRun.from_dict(data)

    def test_concurrent_runner_lock_is_visible_and_does_not_generate(self):
        self.plan()
        lock = self.runtime.root / "family-proposals" / "families.lock"
        lock.touch()
        with self.assertRaises(ObjectFamilyFailure) as failure:
            self.execute()
        self.assertEqual(failure.exception.code, "family_proposals_locked")
        self.assertEqual(self.provider.requests, [])
        lock.unlink()
        self.assertEqual(self.execute().status, "completed")

    def test_unexpected_external_provider_exception_is_failed_not_silently_skipped(self):
        def broken(_request):
            raise RuntimeError("PRIVATE-PLUGIN-SECRET")

        self.provider.response = broken
        self.plan()
        run = self.execute()
        self.assertEqual(run.status, "partial")
        self.assertTrue(all(batch.error_code == "provider_adapter_failed" for batch in run.batches))
        self.assertNotIn("PRIVATE", json.dumps(run.to_dict()))

    def test_public_cli_sdk_run_load_and_partial_exit_code(self):
        sdk = Tarel(self.runtime.root)
        plan = sdk.families.plan("commerce", "sdk", provider_name="local")
        self.assertEqual(sdk.families.load_run("sdk"), plan)
        output, errors = StringIO(), StringIO()
        previous = Path.cwd()
        try:
            os.chdir(self.project)
            with redirect_stdout(output), redirect_stderr(errors):
                status = main(["family", "run", "sdk", "--format", "json"])
            self.assertEqual(status, 0)
            self.assertEqual(errors.getvalue(), "")
            self.assertEqual(json.loads(output.getvalue()), sdk.families.load_run("sdk").to_dict())
            output = StringIO()
            with redirect_stdout(output):
                status = main(
                    ["family", "plan", "commerce", "cli", "--provider", "local", "--format", "json"]
                )
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.getvalue()), sdk.families.load_run("cli").to_dict())
            # A failed proposal run reports its machine-readable result and a nonzero exit.
            self.runtime.graph_store().save(replace(self.graph, name="fresh"))
            sdk.families.plan("fresh", "bad", provider_name="local")
            self.provider.response = lambda _request: {"families": [], "unassigned_object_ids": []}
            output = StringIO()
            with redirect_stdout(output):
                status = main(["family", "run", "bad", "--format", "json"])
            self.assertEqual(status, 2)
            self.assertEqual(json.loads(output.getvalue())["status"], "partial")
        finally:
            os.chdir(previous)

    def test_real_provider_host_and_http_adapter_path_remain_structured(self):
        from tarel.providers.host import load_provider as real_load_provider

        class Response(BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()

        seen = []

        def respond(http_request, **_options):
            payload = json.loads(http_request.data)
            seen.append(payload)
            inventory = json.loads(payload["messages"][-1]["content"])
            result = {
                "families": [],
                "unassigned_object_ids": [item["id"] for item in inventory["objects"]],
            }
            return Response(
                json.dumps({"choices": [{"message": {"content": json.dumps(result)}}]}).encode()
            )

        with (
            patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.project / "config")}),
            patch("tarel.object_families.proposals.load_provider", real_load_provider),
            patch("tarel.providers.openai_compatible.urlopen", side_effect=respond),
        ):
            configure_http_provider(
                "local",
                adapter="openai-compatible",
                api_key=None,
                model="test-model",
                base_url="http://127.0.0.1:9999/v1",
                allow_no_api_key=True,
            )
            self.plan()
            run = self.execute(workers=2)
        self.assertEqual(run.status, "completed")
        self.assertEqual(len(seen), 2)
        self.assertTrue(
            all(payload["response_format"]["json_schema"]["strict"] for payload in seen)
        )
        self.assertTrue(all(payload["model"] == "test-model" for payload in seen))
