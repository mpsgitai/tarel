from __future__ import annotations

import json
import os
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from tarel.cli import main
from tarel.connectors.contracts import CatalogField, CatalogObject, CatalogResult
from tarel.graph.build import build_graph_from_catalog
from tarel.graph.contracts import GraphDocument
from tarel.object_families import FamilyAttribute, ObjectFamily, ObjectFamilyFailure
from tarel.runtime import TarelRuntime
from tarel.sdk import Tarel
from tarel.workspaces.core import create_workspace, define_system
from tarel.workspaces.projection import scoped_node_id


class ObjectFamilyApplicationTests(TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.project = Path(self.temporary_directory.name)
        self.sdk = Tarel(self.project / ".tarel")
        self.graph = _graph()
        self.sdk.runtime.graph_store().save(self.graph)

    def _propose(
        self,
        family_id: str = "monthly-sales",
        *,
        members: tuple[str, ...] = ("sales.sales_2024_01", "sales.sales_2024_02"),
        attributes: tuple[FamilyAttribute, ...] = (),
        grain: tuple[str, ...] = ("sale_id",),
    ) -> ObjectFamily:
        return self.sdk.families.propose(
            "commerce", family_id, name="monthly_sales", members=members,
            grain=grain, attributes=attributes, producer="coding_agent",
        )

    def _cli(self, args: list[str]) -> tuple[int, str, str]:
        previous = Path.cwd()
        output, errors = StringIO(), StringIO()
        try:
            os.chdir(self.project)
            with redirect_stdout(output), redirect_stderr(errors):
                status = main(args)
        finally:
            os.chdir(previous)
        return status, output.getvalue(), errors.getvalue()

    def test_propose_preserves_physical_graph_index_and_default_context(self) -> None:
        graph_before = self.sdk.graph.load("commerce").to_dict()
        model = self.project / "test-embedding.gguf"
        model.write_bytes(b"deterministic test model")
        with patch("tarel.application.LlamaCppEmbedding", return_value=_Embedding()):
            index = self.sdk.index.build("commerce", model_path=model)
            index_before = index.path.read_bytes()
            packet = self.sdk.context.graph("commerce", "sales_2024_01", model_path=model)
            family = self._propose()

            self.assertEqual(
                self.sdk.context.graph(
                    "commerce", "sales_2024_01", model_path=model
                ).canonical_json(),
                packet.canonical_json(),
            )

        self.assertEqual(family.state, "candidate")
        self.assertEqual(len(family.member_ids), 2)
        self.assertEqual(family.grain, ("sale_id",))
        self.assertEqual(self.sdk.graph.load("commerce").to_dict(), graph_before)
        self.assertEqual(index.path.read_bytes(), index_before)
        summary = self.sdk.families.list("commerce")[0]
        self.assertEqual(summary["state"], "candidate")
        self.assertFalse(summary["stale"])
        self.assertNotIn("member_ids", json.dumps(summary))
        self.assertNotIn("sales_2024_01", json.dumps(summary))

    def test_field_order_does_not_affect_exact_schema_compatibility(self) -> None:
        first = next(node.id for node in self.graph.nodes if node.label == "sales.sales_2024_01")
        family = self._propose(members=(first, "sales.sales_2024_02"))
        self.assertIn(first, family.member_ids)
        self.assertEqual({field.name for field in family.schema}, {"sale_id", "amount"})
        self.assertTrue(all(field.nullable is False for field in family.schema))

    def test_sdk_scope_and_malformed_arguments_fail_visibly(self) -> None:
        with self.assertRaises(ObjectFamilyFailure):
            self._propose(members=(None, "sales.sales_2024_02"))
        family = self._propose()
        for options in ({"namespace": 123}, {"allowed_object_ids": {family.member_ids[0]}}):
            with self.subTest(options=options), self.assertRaises(ObjectFamilyFailure):
                self.sdk.families.members(
                    "commerce", family.id, expected_revision=family.revision,
                    mode="include_candidates", **options,
                )
        page = self.sdk.families.members(
            "commerce", family.id, expected_revision=family.revision,
            mode="include_candidates", allowed_object_ids=frozenset({family.member_ids[0]}),
        )
        self.assertEqual(page.total_members, 1)
        self.assertEqual(tuple(item.object_id for item in page.members), (family.member_ids[0],))

    def test_schema_mismatches_are_errors_not_heuristic_matches(self) -> None:
        for incompatible in ("wrong_type", "wrong_nullable", "wrong_name", "extra_field"):
            with self.subTest(incompatible=incompatible), self.assertRaises(ObjectFamilyFailure):
                self._propose(
                    incompatible,
                    members=("sales.sales_2024_01", f"sales.{incompatible}"),
                )
        self.assertEqual(self.sdk.families.list("commerce"), ())

    def test_member_resolution_requires_two_distinct_physical_objects(self) -> None:
        field = next(node.id for node in self.graph.nodes if node.type == "field")
        cases = (
            ("sales.sales_2024_01",),
            ("sales.sales_2024_01", "sales.sales_2024_01"),
            ("sales.sales_2024_01", "sales.missing"),
            ("sales.sales_2024_01", field),
            ("sales.sales_2024_01", "other:sales.sales_2024_02"),
        )
        for members in cases:
            with self.subTest(members=members), self.assertRaises(ObjectFamilyFailure):
                self._propose(members=members)
        self.assertEqual(self.sdk.families.list("commerce"), ())

    def test_grain_and_attribute_name_collisions_fail_before_storage(self) -> None:
        cases = (
            ((), ()),
            (("missing",), ()),
            (("sale_id", "sale_id"), ()),
            (("sale_id",), (FamilyAttribute("sale_id", "object_name"),)),
            (("sale_id",), (
                FamilyAttribute("month", "object_name"), FamilyAttribute("month", "namespace"),
            )),
        )
        for grain, attributes in cases:
            with (
                self.subTest(grain=grain, attributes=attributes),
                self.assertRaises(ObjectFamilyFailure),
            ):
                self._propose(grain=grain, attributes=attributes)
        self.assertEqual(self.sdk.families.list("commerce"), ())

    def test_attributes_are_literal_strings_and_unknown_prefix_does_not_guess(self) -> None:
        family = self._propose(
            attributes=(FamilyAttribute("month", "object_name", prefix="sales_"),),
            grain=("month", "sale_id"),
        )
        page = self.sdk.families.members(
            "commerce", family.id, expected_revision=family.revision,
            mode="include_candidates",
        ).to_dict()
        self.assertEqual(
            [member["attributes"] for member in page["members"]],
            [{"month": "2024_01"}, {"month": "2024_02"}],
        )
        with self.assertRaises(ObjectFamilyFailure):
            self._propose(
                "bad-prefix", members=("sales.sales_2024_03", "archive.sales_2023_12"),
                attributes=(FamilyAttribute("month", "object_name", prefix="not_a_prefix"),),
            )

    def test_namespace_attribute_and_suffix_removal_are_not_numeric_casts(self) -> None:
        family = self._propose(
            members=("tenant_042.events_data", "tenant_043.events_data"),
            attributes=(
                FamilyAttribute("tenant", "namespace", prefix="tenant_"),
                FamilyAttribute("object_kind", "object_name", suffix="_data"),
            ),
            grain=("tenant", "sale_id"),
        )
        page = self.sdk.families.members(
            "commerce", family.id, expected_revision=family.revision,
            mode="include_candidates",
        ).to_dict()
        self.assertEqual(
            [member["attributes"] for member in page["members"]],
            [{"tenant": "042", "object_kind": "events"},
             {"tenant": "043", "object_kind": "events"}],
        )

    def test_candidates_require_explicit_policy_and_review_changes_the_revision(self) -> None:
        family = self._propose()
        with self.assertRaises(ObjectFamilyFailure):
            self.sdk.families.members("commerce", family.id, expected_revision=family.revision)
        exploratory = self.sdk.families.members(
            "commerce", family.id, expected_revision=family.revision,
            mode="include_candidates",
        ).to_dict()
        self.assertEqual(exploratory["usage"], "exploratory_only")
        with self.assertRaises(ObjectFamilyFailure):
            self.sdk.families.review(
                "commerce", family.id, decision="approve", reason="Reviewed.",
                expected_revision="0" * 64,
            )
        reviewed = self.sdk.families.review(
            "commerce", family.id, decision="approve", reason="Structural scope reviewed.",
            expected_revision=family.revision,
        )
        self.assertEqual(reviewed.state, "reviewed")
        self.assertNotEqual(reviewed.revision, family.revision)
        self.assertEqual(
            self.sdk.families.members(
                "commerce", family.id, expected_revision=reviewed.revision
            ).to_dict()["usage"],
            "confirmed",
        )
        with self.assertRaises(ObjectFamilyFailure):
            self.sdk.families.members(
                "commerce", family.id, expected_revision=family.revision,
                mode="include_candidates",
            )

    def test_rejected_family_is_never_usable_but_does_not_block_replacement(self) -> None:
        family = self._propose()
        rejected = self.sdk.families.review(
            "commerce", family.id, decision="reject", reason="Different business scope.",
            expected_revision=family.revision,
        )
        for mode in ("confirmed_only", "include_candidates"):
            with self.subTest(mode=mode), self.assertRaises(ObjectFamilyFailure):
                self.sdk.families.members(
                    "commerce", family.id, expected_revision=rejected.revision, mode=mode,
                )
        replacement = self._propose("replacement")
        self.assertEqual(replacement.member_ids, family.member_ids)
        self.assertEqual(self.sdk.families.load("commerce", family.id), rejected)

    def test_active_overlapping_families_are_rejected(self) -> None:
        first = self._propose()
        with self.assertRaises(ObjectFamilyFailure):
            self._propose(
                "overlapping", members=("sales.sales_2024_02", "sales.sales_2024_03")
            )
        self.assertEqual(len(self.sdk.families.list("commerce")), 1)
        self.assertEqual(self.sdk.families.load("commerce", first.id), first)

    def test_pagination_filters_and_namespace_counts_are_separate_from_data_coverage(self) -> None:
        family = self._propose(
            members=("sales.sales_2024_01", "sales.sales_2024_02", "sales.sales_2024_03",
                     "archive.sales_2023_12"),
            attributes=(FamilyAttribute("month", "object_name", prefix="sales_"),),
        )
        first = self.sdk.families.members(
            "commerce", family.id, expected_revision=family.revision,
            mode="include_candidates", namespace="sales", limit=2,
        ).to_dict()
        second = self.sdk.families.members(
            "commerce", family.id, expected_revision=family.revision,
            mode="include_candidates", namespace="sales", offset=first["next_offset"], limit=2,
        ).to_dict()
        self.assertEqual((first["total_members"], first["matched_members"]), (3, 3))
        self.assertEqual((len(first["members"]), len(second["members"])), (2, 1))
        self.assertEqual(first["next_offset"], 2)
        self.assertIsNone(second["next_offset"])
        self.assertTrue(all(
            member["reference"].startswith("sales.")
            for member in first["members"] + second["members"]
        ))
        filtered = self.sdk.families.members(
            "commerce", family.id, expected_revision=family.revision,
            mode="include_candidates", namespace="sales", filters={"month": "2024_02"},
        ).to_dict()
        self.assertEqual((filtered["total_members"], filtered["matched_members"]), (3, 1))
        self.assertEqual(filtered["members"][0]["reference"], "sales.sales_2024_02")
        empty = self.sdk.families.members(
            "commerce", family.id, expected_revision=family.revision,
            mode="include_candidates", namespace="sales", filters={"month": "2023_12"},
        ).to_dict()
        self.assertEqual(empty["matched_members"], 0)
        self.assertEqual(empty["members"], [])
        self.assertNotIn("coverage", json.dumps(first))

    def test_invalid_page_policy_revision_and_filter_are_visible_failures(self) -> None:
        family = self._propose()
        base = {"expected_revision": family.revision, "mode": "include_candidates"}
        cases = (
            {"limit": 0}, {"limit": 101}, {"offset": -1}, {"mode": "all"},
            {"expected_revision": "0" * 64}, {"filters": {"missing": "value"}},
            {"limit": True}, {"offset": False},
        )
        for arguments in cases:
            with self.subTest(arguments=arguments), self.assertRaises(ObjectFamilyFailure):
                self.sdk.families.members("commerce", family.id, **(base | arguments))

    def test_physical_drift_blocks_resolution_but_keeps_audit_and_allows_replacement(self) -> None:
        family = self._propose()
        annotated = replace(
            self.graph,
            nodes=tuple(
                replace(node, metadata={
                    **node.metadata, "annotation_review": {"state": "validated"},
                })
                if node.type == "table" else node
                for node in self.graph.nodes
            ),
        )
        self.sdk.runtime.graph_store().save(annotated)
        self.assertFalse(self.sdk.families.list("commerce")[0]["stale"])
        self.sdk.families.members(
            "commerce", family.id, expected_revision=family.revision, mode="include_candidates"
        )
        drifted = replace(
            annotated,
            nodes=tuple(
                replace(node, metadata={**node.metadata, "data_type": "BIGINT"})
                if node.type == "field" and node.label == "sale_id" else node
                for node in annotated.nodes
            ),
        )
        self.sdk.runtime.graph_store().save(drifted)
        self.assertTrue(self.sdk.families.list("commerce")[0]["stale"])
        self.assertEqual(self.sdk.families.load("commerce", family.id), family)
        with self.assertRaises(ObjectFamilyFailure):
            self.sdk.families.members(
                "commerce", family.id, expected_revision=family.revision,
                mode="include_candidates",
            )
        replacement = self._propose("new-physical-revision")
        self.assertNotEqual(replacement.graph_revision, family.graph_revision)
        self.assertEqual(replacement.member_ids, family.member_ids)

    def test_import_is_idempotent_and_cannot_overwrite_membership(self) -> None:
        family = self._propose()
        self.assertEqual(self.sdk.families.import_document(family), family)
        third = next(node.id for node in self.graph.nodes if node.label == "sales.sales_2024_03")
        changed = replace(family, member_ids=(family.member_ids[0], third))
        with self.assertRaises(ObjectFamilyFailure):
            self.sdk.families.import_document(changed)
        self.assertEqual(self.sdk.families.load("commerce", family.id), family)
        other = Tarel(self.project / "other-state")
        other.runtime.graph_store().save(self.graph)
        roundtrip = ObjectFamily.from_dict(family.to_dict())
        self.assertEqual(other.families.import_document(roundtrip), family)
        self.assertEqual(other.families.load("commerce", family.id), family)

    def test_reviewed_artifact_cannot_be_imported_to_transfer_approval(self) -> None:
        family = self._propose()
        reviewed = self.sdk.families.review(
            "commerce", family.id, decision="approve", reason="Reviewed scope.",
            expected_revision=family.revision,
        )
        other = Tarel(self.project / "other-state")
        other.runtime.graph_store().save(self.graph)
        with self.assertRaises(ObjectFamilyFailure) as failure:
            other.families.import_document(reviewed)
        self.assertEqual(failure.exception.code, "invalid_object_family_import")
        self.assertEqual(other.families.list("commerce"), ())

    def test_cli_and_sdk_propose_list_members_review_and_export_are_equivalent(self) -> None:
        status, output, errors = self._cli([
            "family", "propose", "commerce", "monthly-sales", "--name", "monthly_sales",
            "--member", "sales.sales_2024_01", "--member", "sales.sales_2024_02",
            "--grain", "month", "--grain", "sale_id",
            "--attribute", '{"name":"month","source":"object_name","prefix":"sales_"}',
            "--producer", "coding_agent", "--format", "json",
        ])
        self.assertEqual((status, errors), (0, ""))
        family = self.sdk.families.load("commerce", "monthly-sales")
        other = Tarel(self.project / "comparison")
        other.runtime.graph_store().save(self.graph)
        expected = other.families.propose(
            "commerce", "monthly-sales", name="monthly_sales",
            members=("sales.sales_2024_01", "sales.sales_2024_02"),
            grain=("month", "sale_id"),
            attributes=(FamilyAttribute("month", "object_name", prefix="sales_"),),
        )
        self.assertEqual(family, expected)
        summary = dict(self.sdk.families.list("commerce")[0])
        summary.pop("stale")
        self.assertEqual(json.loads(output), summary)
        status, output, errors = self._cli([
            "family", "members", "commerce", family.id, "--revision", family.revision,
            "--mode", "include_candidates", "--where", "month=2024_01",
            "--namespace", "sales", "--limit", "1", "--format", "json",
        ])
        self.assertEqual((status, errors), (0, ""))
        self.assertEqual(json.loads(output), self.sdk.families.members(
            "commerce", family.id, expected_revision=family.revision,
            mode="include_candidates", filters={"month": "2024_01"}, namespace="sales", limit=1,
        ).to_dict())
        status, output, errors = self._cli([
            "family", "review", "commerce", family.id, "--revision", family.revision,
            "--decision", "approve", "--reason", "Reviewed structure.", "--format", "json",
        ])
        self.assertEqual((status, errors), (0, ""))
        reviewed = self.sdk.families.load("commerce", family.id)
        summary = dict(self.sdk.families.list("commerce")[0])
        summary.pop("stale")
        self.assertEqual(json.loads(output), summary)
        status, output, errors = self._cli([
            "family", "export", "commerce", family.id, "--format", "json",
        ])
        self.assertEqual((status, errors), (0, ""))
        self.assertEqual(ObjectFamily.from_dict(json.loads(output)), reviewed)
        for operation in ("show", "list"):
            arguments = ["family", operation, "commerce"]
            if operation == "show":
                arguments.append(family.id)
            status, output, errors = self._cli(arguments + ["--format", "json"])
            self.assertEqual((status, errors), (0, ""))
            self.assertNotIn("member_ids", output)

    def test_import_rejects_unknown_data_sql_and_duplicate_json_fields(self) -> None:
        family = self._propose()
        for name, extra in (("rows", [{"private": "raw value"}]), ("sql", "select secret")):
            payload = family.to_dict()
            payload[name] = extra
            with self.subTest(name=name), self.assertRaises(ObjectFamilyFailure):
                ObjectFamily.from_dict(payload)
        source = self.project / "duplicate.json"
        encoded = json.dumps(family.to_dict())
        source.write_text('{"id":"shadow",' + encoded[1:], encoding="utf-8")
        status, output, errors = self._cli([
            "family", "import", "--source", str(source), "--format", "json",
        ])
        self.assertEqual(status, 2)
        self.assertEqual(output, "")
        self.assertTrue(errors)
        stored = list((self.project / ".tarel" / "object-families").rglob("*.json"))
        self.assertEqual(len(stored), 1)
        content = stored[0].read_text(encoding="utf-8")
        self.assertNotIn("raw value", content)
        self.assertNotIn("select secret", content)
        self.assertEqual(stored[0].stat().st_mode & 0o777, 0o600)

    def test_context_hints_are_optional_scoped_metadata_not_member_expansion(self) -> None:
        family = self._propose(
            members=("sales.sales_2024_01", "sales.sales_2024_02", "archive.sales_2023_12"),
            attributes=(FamilyAttribute("month", "object_name", prefix="sales_"),),
        )
        with patch.object(TarelRuntime, "object_family_store", side_effect=AssertionError):
            baseline = self.sdk.context.graph(
                "commerce", "sales_2024_01", namespace="sales", seed_limit=1, max_objects=1,
            )
        packet = self.sdk.context.graph(
            "commerce", "sales_2024_01", namespace="SALES", seed_limit=1, max_objects=1,
            logical_hints="include_candidates",
        )
        self.assertEqual(packet.objects, baseline.objects)
        self.assertEqual(packet.joins, baseline.joins)
        hints = packet.stable_dict()["logical_hints"]["items"]
        self.assertEqual(len(hints), 1)
        hint = hints[0]
        self.assertEqual(hint["kind"], "object_family")
        self.assertEqual(hint["artifact"]["id"], family.id)
        self.assertEqual(hint["member_count"], 2)
        self.assertEqual(hint["source_object_ids"], [packet.objects[0].id])
        self.assertEqual(hint["evidence"], {"level": "schema_only"})
        self.assertEqual(hint["usage"], "exploratory_only")
        encoded = json.dumps(hint)
        for omitted in ("member_ids", "sales_2024_02", "archive", "prefix", "suffix"):
            self.assertNotIn(omitted, encoded)
        confirmed = self.sdk.context.graph(
            "commerce", "sales_2024_01", logical_hints="confirmed_only"
        )
        self.assertEqual(confirmed.stable_dict()["logical_hints"]["items"], [])
        status, output, errors = self._cli([
            "context", "commerce", "sales_2024_01", "--namespace", "SALES",
            "--seed-limit", "1", "--max-objects", "1", "--logical-hints", "include_candidates",
            "--format", "json",
        ])
        self.assertEqual((status, errors), (0, ""))
        self.assertEqual(json.loads(output), packet.to_dict())

    def test_workspace_context_family_counts_only_selected_scope_members(self) -> None:
        family = self._propose(
            members=("sales.sales_2024_01", "sales.sales_2024_02", "archive.sales_2023_12"),
        )
        workspace = define_system(
            create_workspace("estate"), "sales", graph_names=("commerce",),
            graphs={"commerce": self.graph},
        )
        self.sdk.runtime.workspace_store().save(workspace)
        packet = self.sdk.context.workspace(
            "estate", "sales_2024_01", schemas=("commerce:sales",),
            seed_limit=1, max_objects=1, logical_hints="confirmed_then_candidates",
        )
        hints = packet.stable_dict()["logical_hints"]["items"]
        self.assertEqual(len(hints), 1)
        hint = hints[0]
        original = next(
            node.id for node in self.graph.nodes if node.label == "sales.sales_2024_01"
        )
        self.assertEqual(hint["member_count"], 2)
        self.assertEqual(hint["source_object_ids"], [scoped_node_id("commerce", original)])
        self.assertEqual(hint["artifact"]["revision"], family.revision)
        self.assertNotIn("archive", packet.canonical_json())


def _graph() -> GraphDocument:
    fields = (CatalogField("sale_id", 1, "INTEGER", False),
              CatalogField("amount", 2, "DECIMAL(12,2)", False))
    return build_graph_from_catalog(
        "commerce",
        CatalogResult(
            connector="test", source_type="database", catalog="Commerce", dialect="sqlite",
            objects=(
                CatalogObject("sales", "sales_2024_01", "table", fields),
                CatalogObject("sales", "sales_2024_02", "table", (
                    replace(fields[1], position=1), replace(fields[0], position=2),
                )),
                CatalogObject("sales", "sales_2024_03", "table", fields),
                CatalogObject("archive", "sales_2023_12", "table", fields),
                CatalogObject("tenant_042", "events_data", "table", fields),
                CatalogObject("tenant_043", "events_data", "table", fields),
                CatalogObject("sales", "wrong_type", "table", (
                    fields[0], replace(fields[1], data_type="TEXT"),
                )),
                CatalogObject("sales", "wrong_nullable", "table", (
                    fields[0], replace(fields[1], nullable=True),
                )),
                CatalogObject("sales", "wrong_name", "table", (
                    fields[0], replace(fields[1], name="price"),
                )),
                CatalogObject("sales", "extra_field", "table", (
                    *fields, CatalogField("currency", 3, "TEXT", False),
                )),
            ),
        ),
    )


class _Embedding:
    model_id = "deterministic-test-embedding"

    def embed_documents(
        self, texts: tuple[str, ...], *, batch_size: int
    ) -> tuple[tuple[float, ...], ...]:
        del batch_size
        return tuple((1.0, 0.0) for _text in texts)

    def embed_query(self, text: str) -> tuple[float, ...]:
        del text
        return (1.0, 0.0)
