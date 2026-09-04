from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from tarel.connectors.contracts import CatalogField, CatalogObject, CatalogResult
from tarel.graph.build import build_graph_from_catalog
from tarel.graph.contracts import GraphDocument
from tarel.graph.revision import physical_graph_revision
from tarel.object_families import FamilyField, ObjectFamily, ObjectFamilyFailure, review_family
from tarel.object_families.application import (
    _physical_schemas,
    list_object_families_use_case,
    project_families_for_graphs_use_case,
    validate_object_families_against_graph,
    validate_object_family_against_graph,
)
from tarel.runtime import TarelRuntime


def _fixture(count: int = 10) -> tuple[GraphDocument, tuple[ObjectFamily, ...]]:
    fields = (CatalogField("id", 1, "bigint", False), CatalogField("amount", 2, "int", True))
    graph = build_graph_from_catalog(
        "synthetic",
        CatalogResult(
            "fixture",
            "relational",
            "synthetic",
            "sqlite",
            tuple(
                CatalogObject("dbo", f"shard_{index}", "table", fields)
                for index in range(count * 2)
            ),
        ),
    )
    revision = physical_graph_revision(graph)
    members = tuple(node.id for node in graph.nodes if node.type == "table")
    families = tuple(
        ObjectFamily(
            graph_name=graph.name,
            graph_revision=revision,
            id=f"family-{index}",
            name=f"family-{index}",
            member_ids=members[index * 2 : index * 2 + 2],
            schema=tuple(
                FamilyField(field.name, field.data_type, field.nullable) for field in fields
            ),
            grain=("id",),
            attributes=(),
            producer="fixture",
        )
        for index in range(count)
    )
    return graph, families


class FamilyValidationScaleTests(TestCase):
    def test_batch_hashes_and_scans_graph_once_not_per_family(self) -> None:
        graph, families = _fixture(100)
        with (
            patch(
                "tarel.object_families.application.physical_graph_revision",
                wraps=physical_graph_revision,
            ) as hashes,
            patch(
                "tarel.object_families.application._physical_schemas", wraps=_physical_schemas
            ) as schemas,
        ):
            validate_object_families_against_graph(families, graph)
        self.assertEqual(hashes.call_count, 1)
        self.assertEqual(schemas.call_count, 1)

    def test_list_and_projection_each_hash_and_scan_once(self) -> None:
        graph, families = _fixture(20)
        with TemporaryDirectory() as directory:
            runtime = TarelRuntime.local(Path(directory) / "state")
            runtime.graph_store().save(graph)
            for family in families:
                runtime.object_family_store().save(family)
            for operation in (
                lambda: list_object_families_use_case(graph.name, runtime=runtime),
                lambda: (
                    project_families_for_graphs_use_case(
                        (graph,), mode="include_candidates", runtime=runtime
                    ).families
                ),
            ):
                with (
                    patch(
                        "tarel.object_families.application.physical_graph_revision",
                        wraps=physical_graph_revision,
                    ) as hashes,
                    patch(
                        "tarel.object_families.application._physical_schemas",
                        wraps=_physical_schemas,
                    ) as schemas,
                ):
                    result = operation()
                self.assertEqual(len(result), len(families))
                self.assertEqual(hashes.call_count, 1)
                self.assertEqual(schemas.call_count, 1)

    def test_batch_preserves_schema_types_nullability_and_member_invariants(self) -> None:
        graph, families = _fixture(2)
        first, second = families
        changes = (
            (replace(second, graph_revision="f" * 64), "object_family_graph_revision_mismatch"),
            (replace(second, graph_name="another"), "object_family_graph_revision_mismatch"),
            (
                replace(second, member_ids=("missing-one", "missing-two")),
                "object_family_member_not_found",
            ),
            (
                replace(
                    second,
                    schema=(FamilyField("id", "bigint", True), FamilyField("amount", "int", True)),
                ),
                "object_family_schema_mismatch",
            ),
            (
                replace(
                    second,
                    schema=(FamilyField("id", "int", False), FamilyField("amount", "int", True)),
                ),
                "object_family_schema_mismatch",
            ),
            (
                replace(second, schema=(FamilyField("id", "bigint", False),)),
                "object_family_schema_mismatch",
            ),
        )
        for changed, code in changes:
            with self.subTest(code=code):
                with self.assertRaises(ObjectFamilyFailure) as failure:
                    validate_object_families_against_graph((first, changed), graph)
                self.assertEqual(failure.exception.code, code)
        validate_object_family_against_graph(first, graph)

    def test_batch_rejects_active_name_and_member_overlap_but_not_rejected_history(self) -> None:
        graph, families = _fixture(2)
        first, second = families
        for changed in (
            replace(second, name=first.name),
            replace(second, member_ids=first.member_ids),
        ):
            with self.assertRaises(ObjectFamilyFailure) as failure:
                validate_object_families_against_graph((first, changed), graph)
            self.assertEqual(failure.exception.code, "object_family_overlap")
            rejected = review_family(changed, decision="reject", reason="Not an active grouping.")
            validate_object_families_against_graph((first, rejected), graph)

    def test_confirmed_projection_fails_closed_on_hidden_candidate_overlap(self) -> None:
        graph, families = _fixture(2)
        reviewed = review_family(families[0], decision="approve", reason="Declared schema checked.")
        hidden = replace(families[1], member_ids=reviewed.member_ids)
        with TemporaryDirectory() as directory:
            runtime = TarelRuntime.local(Path(directory) / "state")
            for family in (reviewed, hidden):
                runtime.object_family_store().save(family)
            with self.assertRaises(ObjectFamilyFailure) as failure:
                project_families_for_graphs_use_case(
                    (graph,), mode="confirmed_only", runtime=runtime
                )
            self.assertEqual(failure.exception.code, "object_family_overlap")
