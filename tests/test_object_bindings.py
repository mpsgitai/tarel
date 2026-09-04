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

from test_object_families import _graph

from tarel.cli import main
from tarel.discovery.contracts import DiscoveryExecution, DiscoveryMetrics
from tarel.graph.revision import physical_graph_revision
from tarel.object_bindings import ObjectBindingFailure, ObjectValueBinding
from tarel.object_families import FamilyAttribute
from tarel.reference_mapping.contracts import ReferenceMappingEvidence
from tarel.sdk import Tarel
from tarel.topology.endpoint_contracts import LogicalEndpoint, LogicalEndpointFailure


class ObjectBindingTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.sdk = Tarel(self.project / ".tarel")
        self.graph = _graph()
        self.sdk.runtime.graph_store().save(self.graph)
        self.family = self.sdk.families.propose(
            "commerce",
            "tenant-events",
            name="events",
            members=("tenant_042.events_data", "tenant_043.events_data"),
            grain=("tenant", "sale_id"),
            attributes=(FamilyAttribute("tenant", "namespace", prefix="tenant_"),),
        )
        self.source = next(
            node for node in self.graph.nodes if node.type == "field" and node.label == "sale_id"
        )

    def _binding(self, *, evidence: bool = False) -> ObjectValueBinding:
        return ObjectValueBinding(
            "tenant-routing",
            "commerce",
            LogicalEndpoint(
                "graph_field",
                self.source.metadata["object_id"],
                self.source.id,
                physical_graph_revision(self.graph),
            ),
            LogicalEndpoint("family_attribute", self.family.id, "tenant", self.family.revision),
            "coding_agent",
            "route-test",
            evidence=tuple(_evidence(phase) for phase in ("support", "challenge"))
            if evidence
            else (),
        )

    def test_values_stay_ephemeral_exact_scope_counts_and_cli_sdk_agree(self) -> None:
        binding = self.sdk.bindings.import_document(self._binding())
        before = _bytes(self.sdk.root)
        values = ("042", "043", "043", "PRIVATE_UNKNOWN_SENTINEL")
        result = self.sdk.bindings.resolve(
            "commerce",
            binding.id,
            expected_revision=binding.revision,
            values=values,
            mode="include_candidates",
            limit=1,
        )
        self.assertEqual(result.input_count, 4)
        self.assertEqual(result.distinct_input_count, 3)
        self.assertEqual(result.unmatched_input_count, 1)
        self.assertEqual(result.matched_member_count, 2)
        self.assertTrue(result.to_dict()["truncated"])
        self.assertEqual(result.usage, "exploratory_only")
        # Selective cache is derived metadata, not private probe material.
        persisted = _bytes(self.sdk.root)
        self.assertTrue(
            all(b"PRIVATE_UNKNOWN_SENTINEL" not in value for value in persisted.values())
        )
        self.assertTrue(all(persisted[key] == value for key, value in before.items()))
        self.assertNotIn("PRIVATE_UNKNOWN_SENTINEL", json.dumps(result.to_dict()))
        code, out, err = self._cli(
            [
                "binding",
                "resolve",
                "commerce",
                binding.id,
                "--revision",
                binding.revision,
                "--values-stdin",
                "--mode",
                "include_candidates",
                "--limit",
                "1",
            ],
            values,
        )
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out), result.to_dict())
        self.assertEqual(
            self.sdk.bindings.resolve(
                "commerce",
                binding.id,
                expected_revision=binding.revision,
                values=("42",),
                mode="include_candidates",
            ).unmatched_input_count,
            1,
        )  # No guessed zero padding, casefold or normalization.
        scoped = self.sdk.bindings.resolve(
            "commerce",
            binding.id,
            expected_revision=binding.revision,
            values=("042", "043"),
            mode="include_candidates",
            namespace="tenant_042",
        )
        self.assertEqual((scoped.matched_member_count, scoped.unmatched_input_count), (1, 1))

    def test_confirmation_requires_reviewed_endpoint_and_measured_challenge(self) -> None:
        binding = self.sdk.bindings.import_document(self._binding(evidence=True))
        self.assertEqual(self.sdk.bindings.find("commerce"), ())
        with self.assertRaises(ObjectBindingFailure):
            self.sdk.bindings.resolve(
                "commerce", binding.id, expected_revision=binding.revision, values=("042",)
            )
        with self.assertRaises(LogicalEndpointFailure):
            self.sdk.bindings.review(
                "commerce",
                binding.id,
                expected_revision=binding.revision,
                decision="approve",
                reason="Checked.",
            )
        self.family = self.sdk.families.review(
            "commerce",
            self.family.id,
            expected_revision=self.family.revision,
            decision="approve",
            reason="Reviewed partition.",
        )
        # Old binding is correctly stale after endpoint review; no silent rebinding.
        with self.assertRaises(LogicalEndpointFailure):
            self.sdk.bindings.resolve(
                "commerce",
                binding.id,
                expected_revision=binding.revision,
                values=("042",),
                mode="include_candidates",
            )
        no_evidence = self.sdk.bindings.import_document(replace(self._binding(), id="no-evidence"))
        with self.assertRaises(ObjectBindingFailure):
            self.sdk.bindings.review(
                "commerce",
                no_evidence.id,
                expected_revision=no_evidence.revision,
                decision="approve",
                reason="No probe.",
            )
        fresh = self.sdk.bindings.import_document(replace(self._binding(evidence=True), id="fresh"))
        reviewed = self.sdk.bindings.review(
            "commerce",
            fresh.id,
            expected_revision=fresh.revision,
            decision="approve",
            reason="Evidence reviewed.",
        )
        self.assertEqual(
            self.sdk.bindings.resolve(
                "commerce", reviewed.id, expected_revision=reviewed.revision, values=("042",)
            ).usage,
            "confirmed",
        )

    def test_rejected_missing_stale_and_invalid_inputs_fail_visibly(self) -> None:
        binding = self.sdk.bindings.import_document(self._binding())
        for values in ((), ["042"], (None,), ("",), ("x" * 513,)):
            with self.subTest(values=values), self.assertRaises(ObjectBindingFailure):
                self.sdk.bindings.resolve(
                    "commerce",
                    binding.id,
                    expected_revision=binding.revision,
                    values=values,
                    mode="include_candidates",
                )
        for key in ("values", "sql", "code", "path", "mapping_groups"):
            with self.subTest(key=key), self.assertRaises(ObjectBindingFailure):
                ObjectValueBinding.from_dict({**binding.to_dict(), key: "secret"})
        with self.assertRaises(ObjectBindingFailure):
            self.sdk.bindings.resolve(
                "commerce",
                binding.id,
                expected_revision="f" * 64,
                values=("042",),
                mode="include_candidates",
            )
        rejected = self.sdk.bindings.review(
            "commerce",
            binding.id,
            expected_revision=binding.revision,
            decision="reject",
            reason="Rejected.",
        )
        self.assertEqual(self.sdk.bindings.find("commerce", mode="include_candidates"), ())
        with self.assertRaises(ObjectBindingFailure):
            self.sdk.bindings.resolve(
                "commerce",
                rejected.id,
                expected_revision=rejected.revision,
                values=("042",),
                mode="include_candidates",
            )

    def test_import_roundtrip_no_review_forgery_and_namespace_scope(self) -> None:
        binding = self._binding()
        code, out, err = self._cli(["binding", "import", "--source", "-"], binding.to_dict())
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(ObjectValueBinding.from_dict(json.loads(out)), binding)
        self.assertEqual(self.sdk.bindings.import_document(binding), binding)
        self.assertEqual(
            self.sdk.bindings.find("commerce", mode="include_candidates")[0]["usage"],
            "exploratory_only",
        )
        payload = self.sdk.bindings.resolve(
            "commerce",
            binding.id,
            expected_revision=binding.revision,
            values=("042", "043"),
            mode="include_candidates",
            allowed_object_ids=frozenset(),
        )
        self.assertEqual((payload.objects, payload.unmatched_input_count), ((), 2))
        path = next((self.sdk.root / "object-bindings").rglob("*.json"))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def _cli(self, argv: list[str], payload: object) -> tuple[int, str, str]:
        previous = Path.cwd()
        out, err = StringIO(), StringIO()
        try:
            os.chdir(self.project)
            with (
                redirect_stdout(out),
                redirect_stderr(err),
                patch("sys.stdin", StringIO(json.dumps(payload))),
            ):
                code = main(argv)
        finally:
            os.chdir(previous)
        return code, out.getvalue(), err.getvalue()


def _bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


def _evidence(phase: str) -> ReferenceMappingEvidence:
    return ReferenceMappingEvidence(
        phase,
        f"probe-{phase}",
        "population_tested",
        ("a" if phase == "support" else "b") * 64,
        DiscoveryMetrics("source_distinct", 2, 2, 2, 2, 0, 0, 1.0, 0.0, 1.0),
        DiscoveryExecution("harness", "1", "c" * 64, "exact_value", "1"),
    )
