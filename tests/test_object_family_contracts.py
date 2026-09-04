from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from tarel.object_families import (
    FAMILY_CONTRACT_VERSION,
    FamilyAttribute,
    FamilyField,
    FamilyReview,
    FileObjectFamilyStore,
    ObjectFamily,
    ObjectFamilyFailure,
    review_family,
    validate_family,
)
from tarel.runtime import TarelRuntime


def _family() -> ObjectFamily:
    return ObjectFamily(
        graph_name="commerce",
        graph_revision="a" * 64,
        id="monthly-sales",
        name="sales",
        member_ids=("table:dbo:sales_2024_02", "table:dbo:sales_2024_01"),
        schema=(
            FamilyField("order_id", "bigint", False),
            FamilyField("amount", "decimal(12, 2)", True),
        ),
        grain=("month", "order_id"),
        attributes=(FamilyAttribute("month", "object_name", prefix="sales_"),),
        producer="coding-agent",
    )


class ObjectFamilyContractTests(TestCase):
    def test_roundtrip_is_canonical_and_revision_covers_content(self) -> None:
        family = _family()
        validate_family(family)
        self.assertEqual(family.member_ids, tuple(sorted(family.member_ids)))
        self.assertEqual(ObjectFamily.from_dict(family.to_dict()), family)
        self.assertEqual(ObjectFamily.from_dict(family.to_dict(include_revision=False)), family)
        self.assertEqual(replace(family, member_ids=tuple(reversed(family.member_ids))), family)
        self.assertEqual(
            replace(family, member_ids=tuple(reversed(family.member_ids))).revision, family.revision
        )
        self.assertNotEqual(replace(family, producer="another-agent").revision, family.revision)
        payload = family.to_dict()
        payload["name"] = "renamed"
        with self.assertRaisesRegex(ObjectFamilyFailure, "revision"):
            ObjectFamily.from_dict(payload)
        with self.assertRaises(FrozenInstanceError):
            family.name = "mutated"

    def test_unknown_fields_and_arbitrary_executable_contracts_are_rejected(self) -> None:
        mutations = (
            lambda data: data.update(sql="select * from private"),
            lambda data: data["graph"].update(path="/private/database.duckdb"),
            lambda data: data["schema"][0].update(code="lambda: 1"),
            lambda data: data["attributes"][0].update(pattern="sales_(.*)"),
            lambda data: data["attributes"][0].update(source="file_path"),
            lambda data: data["attributes"][0].update(data_type="integer"),
            lambda data: data["attributes"][0].update(literal_value="secret"),
            lambda data: data.update(mapping_groups=[{"keys": [1, 2]}]),
        )
        for mutate in mutations:
            payload = _family().to_dict(include_revision=False)
            mutate(payload)
            with self.subTest(payload=payload):
                with self.assertRaises(ObjectFamilyFailure) as failure:
                    ObjectFamily.from_dict(payload)
                self.assertEqual(failure.exception.code, "invalid_object_family")

    def test_direct_construction_is_checked_at_validation_boundary(self) -> None:
        family = _family()
        invalid = (
            replace(family, contract_version="future"),
            replace(family, state="confirmed"),
            replace(family, graph_name="../escape"),
            replace(family, graph_revision="A" * 64),
            replace(family, id="bad/id"),
            replace(family, name=" sales"),
            replace(family, producer="agent with spaces"),
            replace(family, member_ids=(family.member_ids[0],)),
            replace(family, member_ids=(family.member_ids[0], family.member_ids[0])),
            replace(family, member_ids=("ok", "bad\nmember")),
            replace(family, member_ids=["one", "two"]),
            replace(family, schema=()),
            replace(family, schema=("not-a-field",)),
            replace(family, schema=(FamilyField("key", "int", 1),)),
            replace(family, schema=(FamilyField("key", "int; SELECT", False),)),
            replace(family, attributes=("not-an-attribute",)),
            replace(family, attributes=(FamilyAttribute("month", "python"),)),
            replace(family, attributes=(FamilyAttribute("month", "object_name", prefix="bad\n"),)),
            replace(family, review="not-a-review"),
        )
        for document in invalid:
            with self.subTest(document=document), self.assertRaises(ObjectFamilyFailure):
                validate_family(document)

    def test_schema_attribute_and_grain_names_are_explicit_and_disjoint(self) -> None:
        family = _family()
        for document in (
            replace(family, schema=family.schema + (family.schema[0],)),
            replace(family, attributes=family.attributes + family.attributes),
            replace(family, attributes=(FamilyAttribute("order_id", "namespace"),)),
            replace(family, grain=()),
            replace(family, grain=("month", "month")),
            replace(family, grain=("unknown",)),
            replace(family, grain=["month"]),
        ):
            with self.subTest(document=document), self.assertRaises(ObjectFamilyFailure):
                validate_family(document)
        validate_family(replace(family, attributes=(), grain=("order_id",)))

    def test_physical_field_and_grain_names_preserve_spaces_and_unicode(self) -> None:
        family = replace(
            _family(),
            schema=(FamilyField("Sale ID", "bigint", False), FamilyField("Betrag €", "int", True)),
            grain=("Sale ID", "month"),
        )
        validate_family(family)
        self.assertEqual(ObjectFamily.from_dict(family.to_dict()), family)
        self.assertEqual(family.to_dict()["grain"], ["Sale ID", "month"])
        padded = replace(family, schema=(FamilyField(" 名称 ", "text", False),), grain=(" 名称 ",))
        validate_family(padded)
        self.assertEqual(ObjectFamily.from_dict(padded.to_dict()).grain, (" 名称 ",))

    def test_literal_names_reject_controls_and_grain_is_not_an_expression(self) -> None:
        for name in ("", " ", "bad\nfield", "bad\x00field", "bad\x85field", "bad\ud800", "x" * 257):
            document = replace(_family(), schema=(FamilyField(name, "int", False),), grain=(name,))
            with self.subTest(name=repr(name)), self.assertRaises(ObjectFamilyFailure):
                validate_family(document)
        for document in (
            replace(_family(), grain=("SUM(amount)",)),
            replace(_family(), name="Logical Name"),
            replace(_family(), attributes=(FamilyAttribute("Injected Name", "namespace"),)),
        ):
            with self.assertRaises(ObjectFamilyFailure):
                validate_family(document)

    def test_review_is_human_only_terminal_and_revision_bearing(self) -> None:
        family = _family()
        for decision, state in (("approve", "reviewed"), ("reject", "rejected")):
            reviewed = review_family(
                family, decision=decision, reason="Schema and declared grain checked."
            )
            self.assertEqual(reviewed.state, state)
            self.assertEqual(reviewed.review.source, "human")
            self.assertEqual(family.state, "candidate")
            self.assertNotEqual(reviewed.revision, family.revision)
            self.assertEqual(ObjectFamily.from_dict(reviewed.to_dict()), reviewed)
            with self.assertRaises(ObjectFamilyFailure) as failure:
                review_family(reviewed, decision="reject", reason="Second decision")
            self.assertEqual(failure.exception.code, "object_family_already_reviewed")
        for document in (
            replace(family, state="reviewed"),
            replace(family, state="rejected"),
            replace(family, review=FamilyReview("approve", "Reviewed")),
            replace(family, state="reviewed", review=FamilyReview("reject", "Rejected")),
            replace(
                family, state="reviewed", review=FamilyReview("approve", "Review", source="llm")
            ),
            replace(family, state="reviewed", review=FamilyReview("approve", "")),
        ):
            with self.assertRaises(ObjectFamilyFailure):
                validate_family(document)

    def test_missing_wrong_types_and_unsupported_version_fail_visibly(self) -> None:
        for field in _family().to_dict(include_revision=False):
            payload = _family().to_dict(include_revision=False)
            del payload[field]
            with self.subTest(missing=field), self.assertRaises(ObjectFamilyFailure):
                ObjectFamily.from_dict(payload)
        for payload in ([], None, "invalid", {"contract_version": FAMILY_CONTRACT_VERSION}):
            with self.assertRaises(ObjectFamilyFailure):
                ObjectFamily.from_dict(payload)
        payload = _family().to_dict(include_revision=False)
        payload["contract_version"] = "future"
        with self.assertRaises(ObjectFamilyFailure) as failure:
            ObjectFamily.from_dict(payload)
        self.assertEqual(failure.exception.code, "unsupported_object_family")


class ObjectFamilyStoreTests(TestCase):
    def test_lazy_store_read_does_not_create_state_and_runtime_is_scoped(self) -> None:
        with TemporaryDirectory() as directory:
            runtime = TarelRuntime.local(Path(directory) / "state")
            store = runtime.object_family_store()
            self.assertEqual(store.root, runtime.root / "object-families")
            self.assertEqual(store.list("commerce"), ())
            self.assertFalse(store.exists("commerce", "monthly-sales"))
            with self.assertRaises(ObjectFamilyFailure) as failure:
                store.load("commerce", "monthly-sales")
            self.assertEqual(failure.exception.code, "object_family_not_found")
            self.assertFalse(runtime.root.exists())

    def test_store_roundtrip_is_atomic_private_and_graph_scoped(self) -> None:
        with TemporaryDirectory() as directory:
            store = FileObjectFamilyStore(Path(directory) / "families")
            family = _family()
            path = store.save(family)
            self.assertEqual(store.load(family.graph_name, family.id), family)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path, store.root / "commerce" / "monthly-sales.json")
            self.assertTrue(store.exists(family.graph_name, family.id))
            self.assertEqual(store.list("commerce"), (family.id,))
            self.assertEqual(store.list("another-graph"), ())
            self.assertEqual(tuple(path.parent.glob(".family-*.tmp")), ())
            store.save(replace(family, graph_name="another-graph"))
            self.assertEqual(store.list("another-graph"), (family.id,))
            self.assertNotEqual(
                store.load("commerce", family.id).revision,
                store.load("another-graph", family.id).revision,
            )

    def test_failed_replace_preserves_previous_content_and_cleans_temporary(self) -> None:
        with TemporaryDirectory() as directory:
            store = FileObjectFamilyStore(Path(directory))
            family = _family()
            path = store.save(family)
            previous = path.read_bytes()
            with (
                patch("tarel.object_families.store.os.replace", side_effect=OSError("failure")),
                self.assertRaises(ObjectFamilyFailure) as failure,
            ):
                store.save(replace(family, name="changed"))
            self.assertEqual(failure.exception.code, "object_family_save_failed")
            self.assertEqual(path.read_bytes(), previous)
            self.assertEqual(tuple(path.parent.glob(".family-*.tmp")), ())

    def test_duplicate_json_missing_hash_and_tampering_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            store = FileObjectFamilyStore(Path(directory))
            family = _family()
            path = store.save(family)
            valid_json = json.dumps(family.to_dict())
            invalid_payloads = (
                '{"id":"shadow",' + valid_json[1:],
                valid_json.replace('"name": "commerce"', '"name":"shadow","name":"commerce"'),
                json.dumps(family.to_dict(include_revision=False)),
                valid_json.replace('"name": "sales"', '"name": "changed"'),
                "[]",
                "{invalid-json}",
            )
            for payload in invalid_payloads:
                path.write_text(payload, encoding="utf-8")
                with self.subTest(payload=payload):
                    with self.assertRaises(ObjectFamilyFailure) as failure:
                        store.load(family.graph_name, family.id)
                    self.assertEqual(failure.exception.code, "invalid_object_family")

    def test_store_checks_payload_identity_even_when_content_hash_is_valid(self) -> None:
        with TemporaryDirectory() as directory:
            store = FileObjectFamilyStore(Path(directory))
            family = _family()
            path = store.save(family)
            for changed in (
                replace(family, id="different-id"),
                replace(family, graph_name="different-graph"),
            ):
                path.write_text(json.dumps(changed.to_dict()), encoding="utf-8")
                with self.assertRaisesRegex(ObjectFamilyFailure, "identity"):
                    store.load(family.graph_name, family.id)

    def test_traversal_and_external_symlinks_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileObjectFamilyStore(root / "families")
            for invalid in ("../outside", "/absolute", ".", "..", "a/b", "a\\b", "x\n", "", None):
                with self.subTest(identifier=invalid):
                    with self.assertRaises(ObjectFamilyFailure):
                        store.path(invalid, "ok")
                    with self.assertRaises(ObjectFamilyFailure):
                        store.path("ok", invalid)
            store.root.mkdir()
            outside = root / "outside"
            outside.mkdir()
            (store.root / "commerce").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ObjectFamilyFailure) as failure:
                store.save(_family())
            self.assertEqual(failure.exception.code, "invalid_object_family_path")
            self.assertEqual(tuple(outside.iterdir()), ())
