"""Findings of the sync review, each with a validly signed file where it matters.

Only the test sender makes the odd bytes. Signature check, authorization, planning and activation
are the real ones, so what stops these files is the check of their content.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

from tarel.cli import main
from tarel.connectors.contracts import (
    CatalogField,
    CatalogObject,
    CatalogRelationship,
    CatalogResult,
)
from tarel.graph.build import build_graph_from_catalog, object_node_id
from tarel.graph.contracts import GraphDocument, GraphEdge, GraphNode
from tarel.sdk import Tarel
from tarel.sync.contracts import SyncFailure
from tests.test_sync_file_path import OBSERVED, _catalog, _SyncCase
from tests.test_sync_security import _members, _ReceivedCase, _write_envelope

SECRET_KEY = "SYNTHETIC_KEY_NAME_MARKER"
SECRET_VALUE = "SYNTHETIC_FIELD_VALUE_MARKER"
ORDERS = object_node_id("Shop", "dbo", "orders")


def _objects(*items: tuple[str, str, str]) -> GraphDocument:
    return build_graph_from_catalog(
        "erp",
        CatalogResult(
            connector="shop",
            source_type="sqlite",
            catalog="Shop",
            dialect="sqlite",
            objects=tuple(
                CatalogObject(
                    namespace=namespace,
                    name=name,
                    kind=kind,
                    fields=(CatalogField("id", 1, "INTEGER", False),),
                )
                for namespace, name, kind in items
            ),
        ),
    )


def _set_metadata(node_type: str, key: str, value: Any) -> Any:
    def change(doc: GraphDocument) -> GraphDocument:
        return replace(
            doc,
            nodes=tuple(
                replace(node, metadata={**node.metadata, key: value})
                if node.type == node_type
                else node
                for node in doc.nodes
            ),
        )

    return change


def _keys_with_foreign_key() -> GraphDocument:
    return build_graph_from_catalog(
        "erp",
        CatalogResult(
            connector="shop",
            source_type="sqlite",
            catalog="Shop",
            dialect="sqlite",
            objects=(
                CatalogObject(
                    namespace="dbo",
                    name="orders",
                    kind="table",
                    primary_key=("id", "line"),
                    fields=(
                        CatalogField("id", 1, "INTEGER", False, None, True),
                        CatalogField("line", 2, "INTEGER", False, None, True),
                    ),
                ),
                CatalogObject(
                    namespace="dbo",
                    name="items",
                    kind="table",
                    fields=(
                        CatalogField("order_id", 1, "INTEGER", False),
                        CatalogField("order_line", 2, "INTEGER", False),
                    ),
                ),
                CatalogObject(
                    namespace="dbo",
                    name="report",
                    kind="view",
                    fields=(CatalogField("id", 1, "INTEGER", True),),
                ),
            ),
            relationships=(
                CatalogRelationship(
                    name="fk_items",
                    from_namespace="dbo",
                    from_object="items",
                    from_fields=("order_id", "order_line"),
                    to_namespace="dbo",
                    to_object="orders",
                    to_fields=("id", "line"),
                ),
            ),
        ),
    )


def _set_edge(edge_type: str, key: str, value: Any) -> Any:
    def change(doc: GraphDocument) -> GraphDocument:
        return replace(
            doc,
            edges=tuple(
                replace(edge, metadata={**edge.metadata, key: value})
                if edge.type == edge_type
                else edge
                for edge in doc.edges
            ),
        )

    return change


class EmptiedNamespaceTests(_ReceivedCase):
    """A complete snapshot must not be able to empty a namespace it still declares."""

    def only_structure(self, doc: GraphDocument) -> GraphDocument:
        nodes = tuple(node for node in doc.nodes if node.type in {"catalog", "namespace"})
        kept = {node.id for node in nodes}
        edges = tuple(
            edge for edge in doc.edges if edge.source_id in kept and edge.target_id in kept
        )
        return replace(doc, nodes=nodes, edges=edges)

    def test_a_first_takeover_of_an_empty_namespace_is_refused(self):
        self.refused("scope_namespace_missing", self.forged_with(self.only_structure))
        self.assertEqual(self.central.runtime.graph_store().list(), ())

    def test_an_update_cannot_empty_it_and_nothing_counts_as_deleted(self):
        self.take(self.signed())
        before = self.active_state()

        self.refused("scope_namespace_missing", self.forged_with(self.only_structure))

        self.assertEqual(self.active_state(), before)
        status = self.central.sync.status()[0]
        self.assertEqual(status.removals, ())
        self.assertEqual(status.last_failure["code"], "scope_namespace_missing")

    def test_one_filled_namespace_does_not_vouch_for_another(self):
        self.central.sync.set_trust_scope(self.stream.stream_id, namespaces=("dbo", "sales"))
        self.site.runtime.graph_store().save(
            _objects(("dbo", "orders", "table"), ("sales", "deals", "table"))
        )
        self.site.sync.update_stream("erp-main", namespaces=("dbo", "sales"))
        self.take(self.signed())
        before = self.active_state()

        def drop_sales(doc: GraphDocument) -> GraphDocument:
            gone = {
                node.id
                for node in doc.nodes
                if node.metadata.get("namespace") == "sales"
                or str(node.metadata.get("object_id")).startswith("object:Shop/sales")
            }
            return replace(
                doc,
                nodes=tuple(node for node in doc.nodes if node.id not in gone),
                edges=tuple(
                    edge
                    for edge in doc.edges
                    if edge.source_id not in gone and edge.target_id not in gone
                ),
            )

        self.refused("scope_namespace_missing", self.forged_with(drop_sales))

        self.assertEqual(self.active_state(), before)
        self.assertEqual(self.central.sync.status()[0].removals, ())

    def test_fields_without_their_objects_do_not_fill_it(self):
        def only_fields(doc: GraphDocument) -> GraphDocument:
            nodes = tuple(node for node in doc.nodes if node.type not in {"table", "view"})
            kept = {node.id for node in nodes}
            return replace(
                doc,
                nodes=nodes,
                edges=tuple(
                    edge for edge in doc.edges if edge.source_id in kept and edge.target_id in kept
                ),
            )

        self.refused("export_not_allowed", self.forged_with(only_fields))

    def test_a_namespace_of_views_only_is_filled(self):
        self.site.runtime.graph_store().save(_objects(("dbo", "report", "view")))

        self.assertTrue(self.take(self.signed()).applied)

    def test_a_real_deletion_in_a_namespace_that_stays_filled_still_works(self):
        self.take(self.signed())
        self.site.runtime.graph_store().save(_objects(("dbo", "report", "view")))

        result = self.take(self.signed())

        self.assertEqual(result.plan.objects_deleted, ("dbo.orders",))
        self.assertEqual(self.central.sync.status()[0].removals[0]["reason"], "source_deleted")

    def test_withdrawing_a_namespace_on_purpose_still_works(self):
        self.site.runtime.graph_store().save(
            _objects(("dbo", "orders", "table"), ("hr", "salaries", "table"))
        )
        self.site.sync.update_stream("erp-main", namespaces=("dbo", "hr"))
        self.take(self.signed())
        self.site.sync.update_stream("erp-main", namespaces=("dbo",))

        result = self.take(self.signed())

        self.assertEqual(result.plan.objects_withdrawn, ("hr.salaries",))
        self.assertEqual(result.plan.objects_deleted, ())
        self.assertEqual(self.central.sync.status()[0].removals[0]["reason"], "withdrawn")

    def test_the_sender_keeps_refusing_with_the_same_code(self):
        self.site.runtime.graph_store().save(_objects(("hr", "salaries", "table")))

        with self.assertRaises(SyncFailure) as caught:
            self.signed()

        self.assertEqual(caught.exception.code, "scope_namespace_missing")


JUNK = ([], {}, None, 1, 1.5, True, False, "bogus", "", [[]], {"a": 1})
STATEMENT_FIELDS = (
    "completeness",
    "content_revision",
    "graph_id",
    "observation_source",
    "observed_at",
    "package_sha256",
    "profile",
    "publisher_id",
    "recent_publications",
    "scope",
    "sequence",
    "signing_key",
    "stream_id",
)


class UntrustedStatementTests(_ReceivedCase):
    """Nobody has checked this sender yet, so no value may do more than fail cleanly."""

    def unsigned_with(self, source: Path, target: Path, **fields: Any) -> Path:
        members = _members(source)
        members.pop("publication.sig", None)
        statement = json.loads(members["publication.json"])
        statement.update({"signing_key": None, **fields})
        members["publication.json"] = json.dumps(statement).encode()
        _write_envelope(target, members)
        return target

    def test_every_junk_value_in_every_field_fails_as_a_sync_failure(self):
        source = self.signed()
        target = self.root / "junk.tarelpub"
        for field in STATEMENT_FIELDS:
            for value in JUNK:
                with self.subTest(field=field, value=value):
                    self.unsigned_with(source, target, **{field: value})
                    try:
                        self.central.sync.plan(target, allow_unsigned_dev=True)
                    except SyncFailure:
                        continue

    def test_a_contract_version_of_any_type_is_named_unsupported(self):
        source = self.signed()
        target = self.root / "version.tarelpub"
        for value in JUNK:
            with self.subTest(value=value):
                self.unsigned_with(source, target, contract_version=value)
                self.refused("unsupported_contract", target)

    def test_the_enum_fields_are_invalid_for_each_kind_of_value(self):
        source = self.signed()
        target = self.root / "enum.tarelpub"
        for field in ("completeness", "observation_source"):
            for value in ([], {}, None, 1, True, "bogus"):
                with self.subTest(field=field, value=value):
                    self.unsigned_with(source, target, **{field: value})
                    self.refused("invalid_publication", target)

    def test_a_bad_unsigned_file_does_not_block_the_good_one_behind_it(self):
        good = self.signed()
        inbox = self.root / "inbox"
        inbox.mkdir()
        self.unsigned_with(good, inbox / "1-bad.tarelpub", completeness=[])
        shutil.copyfile(good, inbox / "2-good.tarelpub")

        result = self.central.sync.process_inbox(inbox)

        by_name = {item.name: item for item in result.items}
        self.assertEqual(by_name["1-bad.tarelpub"].outcome, "rejected")
        self.assertEqual(by_name["1-bad.tarelpub"].code, "invalid_publication")
        self.assertEqual(by_name["2-good.tarelpub"].outcome, "applied")
        self.assertTrue((inbox / "rejected" / "1-bad.tarelpub").is_file())
        self.assertTrue((inbox / "done" / "2-good.tarelpub").is_file())
        reason = json.loads((inbox / "rejected" / "1-bad.tarelpub.reason.json").read_text())
        self.assertEqual(reason["code"], "invalid_publication")
        self.assertEqual(self.central.sync.status()[0].active_sequence, 1)
        self.assertEqual(self.central.sync.process_inbox(inbox).items, ())
        self.assertEqual(sorted(path.name for path in inbox.glob("*.tarelpub")), [])

    def test_the_command_line_reports_the_rejection_and_still_activates_the_good_file(self):
        good = self.signed()
        inbox = self.root / "inbox"
        inbox.mkdir()
        self.unsigned_with(good, inbox / "1-bad.tarelpub", observation_source={})
        shutil.copyfile(good, inbox / "2-good.tarelpub")
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            status = main(
                [
                    "sync", "inbox", "--directory", str(inbox),
                    "--state", str(self.central.root), "--format", "json",
                ]
            )

        self.assertEqual(status, 1)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["rejected"], 1)
        self.assertEqual(
            [item["outcome"] for item in payload["items"]], ["rejected", "applied"],
        )
        self.assertEqual(self.central.sync.status()[0].active_sequence, 1)

    def test_a_statement_value_is_not_repeated_in_the_refusal(self):
        target = self.root / "marker.tarelpub"
        for field in ("completeness", "observation_source", "contract_version", "publisher_id"):
            with self.subTest(field=field):
                self.unsigned_with(self.signed(), target, **{field: SECRET_VALUE})
                with self.assertRaises(SyncFailure) as caught:
                    self.central.sync.plan(target)
                self.assertNotIn(SECRET_VALUE, str(caught.exception))

    def test_a_member_name_is_not_repeated_in_the_refusal(self):
        target = self.root / "member.tarelpub"
        members = _members(self.signed())
        members[SECRET_VALUE] = b"x"
        _write_envelope(target, members)

        with self.assertRaises(SyncFailure) as caught:
            self.central.sync.plan(target)

        self.assertEqual(caught.exception.code, "invalid_package")
        self.assertNotIn(SECRET_VALUE, str(caught.exception))

    def test_a_declared_namespace_outside_the_grant_is_not_repeated(self):
        self.site.runtime.graph_store().save(
            _objects(("dbo", "orders", "table"), (SECRET_VALUE, "x", "table"))
        )
        self.central.sync.set_trust_scope(self.stream.stream_id, namespaces=("dbo",))
        self.site.sync.update_stream("erp-main", namespaces=("dbo", SECRET_VALUE))

        with self.assertRaises(SyncFailure) as caught:
            self.take(self.signed())

        self.assertEqual(caught.exception.code, "unauthorized_scope")
        self.assertNotIn(SECRET_VALUE, str(caught.exception))
        self.assertNotIn(SECRET_VALUE, json.dumps(self.central.sync.status()[0].to_dict()))


class MetadataValueTests(_ReceivedCase):
    """An allowed key must hold the value it is allowed for, not anything at all."""

    def setUp(self) -> None:
        super().setUp()
        self.site.runtime.graph_store().save(_keys_with_foreign_key())

    def test_a_payload_under_an_allowed_key_is_refused_and_stays_out(self):
        self.take(self.signed())
        before = self.active_state()
        payload = {"technical_description": SECRET_VALUE}
        cases = {
            "object as primary key": _set_metadata("table", "primary_key", payload),
            "nested in a list": _set_metadata("table", "primary_key", ["id", payload]),
            "text instead of a field name": _set_metadata("table", "primary_key", [SECRET_VALUE]),
            "edge fields as an object": _set_edge("foreign_key", "from_fields", payload),
            "edge fields nested": _set_edge("foreign_key", "to_fields", [payload]),
            "edge fields naming no field": _set_edge("foreign_key", "from_fields", [SECRET_VALUE]),
            "edge name as an object": _set_edge("foreign_key", "name", payload),
            "relationship id as an object": _set_edge(
                "foreign_key_field", "relationship_id", payload,
            ),
            "relationship id naming nothing": _set_edge(
                "foreign_key_field", "relationship_id", SECRET_VALUE,
            ),
            "data type as an object": _set_metadata("field", "data_type", payload),
            "catalog dialect as an object": _set_metadata("catalog", "dialect", payload),
        }
        for name, change in cases.items():
            with self.subTest(name):
                with self.assertRaises(SyncFailure) as caught:
                    self.take(self.forged_with(change))
                self.assertEqual(caught.exception.code, "export_not_allowed")
                self.assertNotIn(SECRET_VALUE, str(caught.exception))
                self.assertEqual(self.active_state(), before)
                self.assertNotIn(SECRET_VALUE, before[0].decode())
                status = self.central.sync.status()[0]
                self.assertNotIn(SECRET_VALUE, json.dumps(status.to_dict()))

    def test_typed_field_values_are_checked_and_a_bool_is_no_number(self):
        for key, value in (
            ("position", True),
            ("position", 0),
            ("position", -1),
            ("position", "1"),
            ("position", 1.0),
            ("position", None),
            ("nullable", "yes"),
            ("nullable", 1),
            ("nullable", None),
            ("is_primary_key", 0),
            ("is_primary_key", None),
        ):
            with self.subTest(key=key, value=value):
                self.refused(
                    "export_not_allowed", self.forged_with(_set_metadata("field", key, value)),
                )

    def test_a_null_keeps_its_own_meaning_per_field(self):
        """No blanket rule: a description may be null, a primary key may not."""
        self.refused(
            "export_not_allowed", self.forged_with(_set_metadata("table", "primary_key", None)),
        )
        self.central.sync.set_trust_scope(
            self.stream.stream_id, namespaces=("dbo",), technical_descriptions=True,
        )
        self.site.sync.update_stream(
            "erp-main", namespaces=("dbo",), technical_descriptions=True,
        )

        self.assertTrue(self.take(self.signed()).applied)

    def test_a_released_description_must_still_be_text(self):
        self.central.sync.set_trust_scope(
            self.stream.stream_id, namespaces=("dbo",), technical_descriptions=True,
        )
        self.site.sync.update_stream(
            "erp-main", namespaces=("dbo",), technical_descriptions=True,
        )

        for value in ({"a": 1}, ["a"], 1, True):
            with self.subTest(value=value):
                self.refused(
                    "export_not_allowed",
                    self.forged_with(_set_metadata("table", "technical_description", value)),
                )

    def test_annotation_keys_on_a_catalog_node_are_a_clean_refusal(self):
        self.site.sync.update_stream("erp-main", namespaces=("dbo",), annotations=True)

        self.refused("export_not_allowed", self.forged_with(_set_metadata("catalog", "grain", "x")))

    def test_a_field_cannot_hang_from_something_that_is_not_an_object(self):
        def under_a_field(doc: GraphDocument) -> GraphDocument:
            first, second = [node for node in doc.nodes if node.type == "field"][:2]
            changed = replace(second, metadata={**second.metadata, "object_id": first.id})
            return replace(
                doc,
                nodes=tuple(changed if node.id == second.id else node for node in doc.nodes),
            )

        self.refused("export_not_allowed", self.forged_with(under_a_field))

    def test_normal_composite_and_foreign_keys_still_pass(self):
        self.assertTrue(self.take(self.signed()).applied)

        nodes = self.central_graph().node_by_id()
        self.assertEqual(nodes[ORDERS].metadata["primary_key"], ["id", "line"])
        keys = [edge for edge in self.central_graph().edges if edge.type == "foreign_key"]
        self.assertEqual(keys[0].metadata["from_fields"], ["order_id", "order_line"])
        self.assertEqual(
            nodes[object_node_id("Shop", "dbo", "report")].metadata["primary_key"], [],
        )

    def test_data_type_names_a_source_might_use_still_pass(self):
        def exotic(doc: GraphDocument) -> GraphDocument:
            return _set_metadata("field", "data_type", "TIMESTAMP(6) WITH TIME ZONE; \"x\"")(doc)

        self.assertTrue(self.take(self.forged_with(exotic)).applied)


class NamespaceIdentityTests(_ReceivedCase):
    def test_a_namespace_contradicting_its_own_catalog_is_refused_and_not_repeated(self):
        self.take(self.signed())
        before = self.active_state()
        inbox = self.root / "inbox"
        inbox.mkdir()
        forged = self.forged_with(_set_metadata("namespace", "catalog", SECRET_VALUE))
        shutil.copyfile(forged, inbox / "forged.tarelpub")

        with self.assertRaises(SyncFailure) as caught:
            self.take(forged)
        result = self.central.sync.process_inbox(inbox)

        self.assertEqual(caught.exception.code, "export_not_allowed")
        self.assertNotIn(SECRET_VALUE, str(caught.exception))
        self.assertEqual(result.items[0].code, "export_not_allowed")
        self.assertEqual(self.active_state(), before)
        self.assertNotIn(SECRET_VALUE, json.dumps(self.central.sync.status()[0].to_dict()))
        reason = (inbox / "rejected" / "forged.tarelpub.reason.json").read_text("utf-8")
        self.assertNotIn(SECRET_VALUE, reason)

    def test_a_namespace_without_its_catalog_is_refused(self):
        def without(doc: GraphDocument) -> GraphDocument:
            return replace(
                doc,
                nodes=tuple(
                    replace(node, metadata={})
                    if node.type == "namespace"
                    else node
                    for node in doc.nodes
                ),
            )

        self.refused("export_not_allowed", self.forged_with(without))

    def test_names_with_spaces_unicode_and_escaped_characters_still_pass(self):
        catalog = build_graph_from_catalog(
            "erp",
            CatalogResult(
                connector="shop",
                source_type="sqlite",
                catalog="Shop Größe/1",
                dialect="sqlite",
                objects=(
                    CatalogObject(
                        namespace="Mixed Ümlaut/ns",
                        name="a b/c%d",
                        kind="table",
                        fields=(CatalogField("Col Ä/1", 1, "INTEGER", False),),
                    ),
                ),
            ),
        )
        self.site.runtime.graph_store().save(catalog)
        self.central.sync.set_trust_scope(self.stream.stream_id, namespaces=("Mixed Ümlaut/ns",))
        self.site.sync.update_stream("erp-main", namespaces=("Mixed Ümlaut/ns",))

        self.assertTrue(self.take(self.signed()).applied)


class SafeDiagnosticsTests(_ReceivedCase):
    """Distinct markers for a key name and a value, checked on every way a diagnosis can leave."""

    def assert_nothing_repeats(self, change: Any) -> None:
        forged = self.forged_with(change)
        original = forged.read_bytes()
        with self.assertRaises(SyncFailure) as caught:
            self.take(forged)
        self.assertEqual(caught.exception.code, "export_not_allowed")

        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            status = main(["sync", "apply", str(forged), "--state", str(self.central.root)])
        self.assertEqual(status, 2)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main(["sync", "status", "--state", str(self.central.root), "--format", "json"])

        inbox = self.root / "diagnostic-inbox"
        shutil.rmtree(inbox, ignore_errors=True)
        inbox.mkdir()
        (inbox / "forged.tarelpub").write_bytes(original)
        result = self.central.sync.process_inbox(inbox)
        reason = (inbox / "rejected" / "forged.tarelpub.reason.json").read_text("utf-8")

        for text in (
            str(caught.exception),
            errors.getvalue(),
            output.getvalue(),
            json.dumps(self.central.sync.status()[0].to_dict()),
            json.dumps(result.to_dict()),
            reason,
        ):
            self.assertNotIn(SECRET_KEY, text)
            self.assertNotIn(SECRET_VALUE, text)
        self.assertEqual((inbox / "rejected" / "forged.tarelpub").read_bytes(), original)

    def test_an_unknown_key_on_a_node(self):
        for node_type in ("table", "view", "field", "namespace", "catalog"):
            with self.subTest(node_type=node_type):
                self.assert_nothing_repeats(_set_metadata(node_type, SECRET_KEY, SECRET_VALUE))

    def test_an_unknown_key_on_an_edge(self):
        self.assert_nothing_repeats(_set_edge("contains", SECRET_KEY, SECRET_VALUE))

    def test_an_unknown_node_type(self):
        def add(doc: GraphDocument) -> GraphDocument:
            node = GraphNode(
                id=f"x:{SECRET_VALUE}", type=SECRET_KEY, label=SECRET_VALUE, metadata={},
            )
            return replace(doc, nodes=(*doc.nodes, node))

        self.assert_nothing_repeats(add)

    def test_an_unknown_edge_type(self):
        def add(doc: GraphDocument) -> GraphDocument:
            first = doc.nodes[0].id
            edge = GraphEdge(
                id=f"x:{SECRET_VALUE}", source_id=first, target_id=first, type=SECRET_KEY,
            )
            return replace(doc, edges=(*doc.edges, edge))

        self.assert_nothing_repeats(add)

    def test_a_key_this_schema_knows_may_be_named(self):
        with self.assertRaises(SyncFailure) as caught:
            self.take(self.forged("table"))

        self.assertIn("technical_description", str(caught.exception))
        self.assertNotIn("SYNTHETIC", str(caught.exception))


class StatusCostTests(_SyncCase):
    """A status call stays linear, without losing what it reports."""

    def build(self, *, streams: int, referenced: int) -> dict[str, Any]:
        sites = []
        for number in range(streams):
            name = f"s{number}"
            site = Tarel(self.root / f"site-{name}")
            site.runtime.graph_store().save(_catalog(("dbo", "orders")))
            publisher = site.sync.init_publisher()
            stream = site.sync.create_stream("main", graph="erp", namespaces=("dbo",))
            self.central.sync.trust(
                publisher_id=publisher,
                stream_id=stream.stream_id,
                graph_id=stream.graph_id,
                local_graph=f"{name}.erp",
                workspace="group",
                system=name,
                namespaces=("dbo",),
            )
            path = self.root / f"{name}.tarelpub"
            site.sync.publish("main", output=path, observed_at=OBSERVED, unsigned_dev=True)
            self.central.sync.apply(path, allow_unsigned_dev=True)
            sites.append(name)
        store = self.central.runtime.workspace_store()
        document = json.loads(store.path("group").read_text("utf-8"))
        for system in document["systems"][:referenced]:
            graph = system["graphs"][0]
            system["zones"] = []
            system["areas"] = [
                {
                    "name": "main",
                    "description": None,
                    "schemas": [
                        {"graph": graph, "namespace": "dbo"},
                        {"graph": graph, "namespace": "GONE"},
                    ],
                }
            ]
        store.path("group").write_text(json.dumps(document), "utf-8")
        return {"sites": sites, "document": document}

    def counted_status(self) -> tuple[tuple[Any, ...], list[str]]:
        cls = type(self.central.runtime.graph_store())
        original = cls.load
        calls: list[str] = []

        def count(store: Any, name: str, *args: Any, **kwargs: Any) -> Any:
            calls.append(name)
            return original(store, name, *args, **kwargs)

        with patch.object(cls, "load", count):
            rows = self.central.sync.status()
        return rows, calls

    def setUp(self) -> None:
        super().setUp()
        self.central = Tarel(self.root / "many-central")

    def test_many_streams_load_each_needed_graph_at_most_once(self):
        self.build(streams=6, referenced=6)

        rows, calls = self.counted_status()

        self.assertEqual(len(rows), 6)
        self.assertEqual(len(calls), len(set(calls)))
        self.assertLessEqual(len(calls), 6)
        for row in rows:
            self.assertEqual(
                [(item["kind"], item["detail"]) for item in row.dangling_references],
                [("area_schema", "GONE")],
            )

    def test_graphs_nothing_points_into_are_not_loaded_at_all(self):
        self.build(streams=4, referenced=1)

        rows, calls = self.counted_status()

        self.assertEqual(len(calls), 1)
        self.assertEqual(sum(bool(row.dangling_references) for row in rows), 1)

    def test_references_stay_with_their_workspace_and_a_shared_graph_loads_once(self):
        built = self.build(streams=2, referenced=1)
        store = self.central.runtime.workspace_store()
        graph = built["document"]["systems"][0]["graphs"][0]
        other = {
            **built["document"],
            "name": "second",
            "systems": [
                {
                    "name": "shared",
                    "description": None,
                    "graphs": [graph],
                    "zones": [],
                    "areas": [
                        {
                            "name": "gone",
                            "description": None,
                            "schemas": [{"graph": graph, "namespace": "ALSO_GONE"}],
                        }
                    ],
                }
            ],
        }
        path = store.path("second")
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(other), "utf-8")

        rows, calls = self.counted_status()

        self.assertEqual(calls, [graph])
        row = next(item for item in rows if item.local_graph == graph)
        self.assertEqual(
            sorted((item["workspace"], item["detail"]) for item in row.dangling_references),
            [("group", "GONE"), ("second", "ALSO_GONE")],
        )

    def test_a_central_edit_between_two_calls_shows_in_the_second(self):
        built = self.build(streams=2, referenced=1)
        self.assertTrue(any(row.dangling_references for row in self.central.sync.status()))
        store = self.central.runtime.workspace_store()
        document = built["document"]
        document["systems"][0]["areas"] = []
        store.path("group").write_text(json.dumps(document), "utf-8")

        self.assertFalse(any(row.dangling_references for row in self.central.sync.status()))

    def test_a_removed_object_keeps_its_reason_and_a_new_stream_is_listed(self):
        built = self.build(streams=1, referenced=0)
        graph = built["document"]["systems"][0]["graphs"][0]
        site = Tarel(self.root / "site-s0")
        document = built["document"]
        document["systems"][0]["areas"] = [
            {"name": "a", "description": None, "schemas": [{"graph": graph, "namespace": "dbo"}]}
        ]
        document["systems"][0]["zones"] = [
            {"name": "z", "description": None, "members": [{"graph": graph, "object_id": ORDERS}]}
        ]
        self.central.runtime.workspace_store().path("group").write_text(
            json.dumps(document), "utf-8",
        )
        site.runtime.graph_store().save(_catalog(("dbo", "other")))
        path = self.root / "s0-2.tarelpub"
        site.sync.publish("main", output=path, observed_at=OBSERVED, unsigned_dev=True)
        self.central.sync.apply(path, allow_unsigned_dev=True)
        self.central.sync.trust(
            publisher_id="pub_0000000000new",
            stream_id="str_0000000000new",
            graph_id="gph_0000000000new",
            local_graph="never.erp",
            workspace="group",
            system="never",
            namespaces=("dbo",),
        )

        rows = self.central.sync.status()

        by_graph = {row.local_graph: row for row in rows}
        self.assertEqual(
            [(item["kind"], item["reason"]) for item in by_graph[graph].dangling_references],
            [("zone_member", "source_deleted")],
        )
        self.assertEqual(by_graph[graph].retained_revisions, 2)
        self.assertIsNone(by_graph["never.erp"].active_sequence)
        self.assertEqual(by_graph["never.erp"].dangling_references, ())
