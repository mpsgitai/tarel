"""Manifest declarations, shared interfaces, refresh safety and visible failure cases."""

import builtins
import copy
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from tarel.cli import main
from tarel.lineage.contracts import LineageFailure
from tarel.lineage.core import build_lineage, table_lineage
from tarel.lineage.dbt import load_dbt_manifest
from tarel.sdk import Tarel

_FIXTURE = Path(__file__).parent / "fixtures/lineage/dbt/manifest-v12.json"
_DAILY = "model.shop.daily_sales"
_STAGE = "model.shop.stg_orders"


class DbtLineageTests(TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manifest = self.root / "manifest.json"
        self.payload = json.loads(_FIXTURE.read_text())
        self.sdk = Tarel(self.root / ".tarel")
        self.write()

    def write(self) -> None:
        self.manifest.write_text(json.dumps(self.payload), encoding="utf-8")

    def assert_import_fails(self, code: str = "invalid_dbt_manifest") -> None:
        self.write()
        with self.assertRaises(LineageFailure) as error:
            self.sdk.lineage.import_dbt("shop", manifest=self.manifest)
        self.assertEqual(error.exception.code, code)
        self.assertFalse((self.root / ".tarel/lineage/shop").exists())

    def test_manifest_maps_sources_aliases_and_all_supported_materializations(self) -> None:
        source = load_dbt_manifest(self.manifest)
        document = build_lineage("shop", source)
        modes = {m.target: m.mode for m in document.materializations}
        self.assertEqual(len(source.definitions), 6)
        self.assertEqual(len(source.observations), 6)
        self.assertEqual(
            modes,
            {
                "Warehouse.silver.orders_clean": "view",
                "Warehouse.gold.sales_by_day": "table",
                "Warehouse.gold.sales_history": "incremental",
                "Warehouse.raw.country_codes": "table",
                "Warehouse.history.orders_history": "incremental",
            },
        )
        self.assertTrue(all(c.state == "draft" for c in document.claims))
        self.assertTrue(all(m.state == "draft" for m in document.materializations))
        self.assertTrue(all(c.evidence.source == "declared_reference" for c in document.claims))
        self.assertFalse(document.analyses or document.write_units)
        self.assertFalse(any("test.shop" in d.external_id for d in document.definitions))
        self.assertFalse(any("report" in d.external_id for d in document.definitions))
        steps = {s.external_id: s for s in source.steps}
        self.assertEqual(steps[_DAILY].depends_on_external_ids, ("model.shop.filtered",))

    def test_ephemeral_is_a_logical_input_and_trace_reaches_physical_origin(self) -> None:
        result = self.sdk.lineage.import_dbt("shop", manifest=self.manifest)
        self.assertFalse(any("filtered" in m.target for m in result.document.materializations))
        trace = self.sdk.lineage.upstream(
            "Warehouse.gold.sales_by_day", lineages=("shop",), max_hops=30
        )
        self.assertFalse(trace.truncated)
        self.assertEqual([o.reference for o in trace.origins], ["Warehouse.raw.orders"])
        logical = next(h for h in trace.hops if h.source.reference == "dbt.model.shop.filtered")
        self.assertEqual(logical.source.source, "lineage:shop")
        self.assertIn("logical ephemeral", logical.evidence.reason)

    def test_catalog_mapping_is_explicit_and_respects_case_and_quoting(self) -> None:
        source = load_dbt_manifest(self.manifest, catalog_map={"Warehouse": "physical-lake"})
        self.assertIn(
            '"physical-lake".gold.sales_by_day', {m.target for m in source.materializations}
        )
        self.assertIn('"physical-lake".raw.orders', {o.target for o in source.observations})
        for mapping in ({"typo": "physical"}, {"Warehouse": ""}, {"Warehouse": 0}, []):
            with self.subTest(mapping=mapping), self.assertRaises(LineageFailure):
                load_dbt_manifest(self.manifest, catalog_map=mapping)

    def test_no_hardcoded_project_or_model_count_and_long_chain_is_iterative(self) -> None:
        template = self.payload["nodes"][_DAILY]
        self.payload["nodes"] = {}
        self.payload["metadata"]["project_name"] = "other_project"
        for i in range(1200):
            key = f"model.other_project.m{i}"
            node = copy.deepcopy(template)
            node.update(unique_id=key, name=f"m{i}", alias=f"m{i}", relation_name=None)
            node["depends_on"]["nodes"] = [f"model.other_project.m{i - 1}"] if i else []
            self.payload["nodes"][key] = node
        self.write()
        source = load_dbt_manifest(self.manifest)
        self.assertEqual(len(source.definitions), 1200)
        self.assertEqual(source.workflow_external_id, "dbt:other_project")
        self.assertEqual(source.steps[-1].external_id, "model.other_project.m1199")

    def test_compiled_raw_and_metadata_only_content_never_persist_code_or_seed_rows(self) -> None:
        self.payload["nodes"][_DAILY]["raw_code"] = "select 'private_sql_marker'"
        self.payload["nodes"]["seed.shop.country_codes"]["raw_code"] = "private_csv_marker,123"
        self.payload["metadata"]["env"] = {"unused": "private_env_marker"}
        self.write()
        source = load_dbt_manifest(self.manifest)
        definitions = source.definition_by_external_id()
        self.assertIn("private_sql_marker", definitions[_DAILY].content)
        self.assertNotIn("private_csv_marker", definitions["seed.shop.country_codes"].content)
        self.assertEqual(definitions["snapshot.shop.orders_history"].language, "dbt-declaration")
        result = self.sdk.lineage.import_dbt("shop", manifest=self.manifest)
        serialized = result.path.read_text()
        for marker in (
            "private_sql_marker",
            "private_csv_marker",
            "private_env_marker",
            "select order_id",
        ):
            self.assertNotIn(marker, serialized)

    def test_determinism_ignores_json_order_and_volatile_metadata(self) -> None:
        first = self.sdk.lineage.import_dbt("shop", manifest=self.manifest)
        before = first.path.stat().st_mtime_ns
        self.payload["metadata"].update(generated_at="later", invocation_id="new")
        self.payload["nodes"] = dict(reversed(list(self.payload["nodes"].items())))
        self.payload["nodes"]["model.shop.sales_history"]["depends_on"]["nodes"].reverse()
        self.write()
        second = self.sdk.lineage.import_dbt("shop", manifest=self.manifest)
        self.assertEqual(first.document, second.document)
        self.assertIsNone(second.report)
        self.assertEqual(before, second.path.stat().st_mtime_ns)

    def test_repeat_import_preserves_human_validation_and_rejection(self) -> None:
        result = self.sdk.lineage.import_dbt("shop", manifest=self.manifest)
        for item, decision in (
            (result.document.claims[0], "validate"),
            (result.document.materializations[0], "reject"),
        ):
            self.sdk.lineage.decide("shop", item.id, decision=decision, reason="Human checked.")
        before = self.sdk.lineage.load("shop")
        self.payload["metadata"]["generated_at"] = "new"
        self.write()
        after = self.sdk.lineage.import_dbt("shop", manifest=self.manifest)
        self.assertEqual(after.document, before)

    def test_refresh_changed_code_dependency_and_target_preserves_review_history(self) -> None:
        result = self.sdk.lineage.import_dbt("shop", manifest=self.manifest)
        definition = next(d for d in result.document.definitions if d.external_id == _STAGE)
        claim = next(c for c in result.document.claims if c.definition_id == definition.id)
        materialization = next(
            m for m in result.document.materializations if m.definition_id == definition.id
        )
        for item in (claim, materialization):
            self.sdk.lineage.decide("shop", item.id, decision="validate", reason="Human checked.")
        self.payload["nodes"][_STAGE].update(
            alias="orders_v2", relation_name=None, compiled_code="select 1"
        )
        self.payload["nodes"][_STAGE]["depends_on"]["nodes"].append("seed.shop.country_codes")
        self.write()
        updated = self.sdk.lineage.import_dbt("shop", manifest=self.manifest)
        self.assertIsNotNone(updated.report)
        carried = next(c for c in updated.document.claims if c.id == claim.id)
        self.assertEqual(carried.state, "review_required")
        self.assertEqual(carried.reviews[-1].decision, "validate")
        changed = next(
            m for m in updated.document.materializations if m.definition_id == definition.id
        )
        self.assertEqual(changed.target, "Warehouse.silver.orders_v2")
        self.assertEqual(changed.state, "review_required")
        self.assertEqual(changed.reviews[-1].decision, "validate")
        self.assertTrue(updated.report_path.exists())

    def test_removed_dependency_has_stale_review_evidence(self) -> None:
        result = self.sdk.lineage.import_dbt("shop", manifest=self.manifest)
        claim = next(c for c in result.document.claims if c.target == "Warehouse.raw.orders")
        self.sdk.lineage.decide("shop", claim.id, decision="validate", reason="Human checked.")
        self.payload["nodes"][_STAGE]["depends_on"]["nodes"] = []
        self.write()
        result = self.sdk.lineage.import_dbt("shop", manifest=self.manifest)
        self.assertNotIn(claim.id, {c.id for c in result.document.claims})
        stale = next(i for i in result.report.stale_items if i.item["id"] == claim.id)
        self.assertEqual(stale.previous_state, "validated")

    def test_new_artifact_path_preserves_stable_ids_and_review_history(self) -> None:
        result = self.sdk.lineage.import_dbt("shop", manifest=self.manifest)
        claim = result.document.claims[0]
        self.sdk.lineage.decide("shop", claim.id, decision="validate", reason="Human checked.")
        before = self.sdk.lineage.load("shop")
        other = self.root / "new-run.json"
        other.write_bytes(self.manifest.read_bytes())
        result = self.sdk.lineage.import_dbt("shop", manifest=other)
        self.assertEqual(result.document.claims, before.claims)
        self.assertEqual(result.document.definitions, before.definitions)
        self.assertEqual(result.document.source_reference, other.as_posix())

    def test_sdk_cli_parity_and_no_optional_imports_or_provider_calls(self) -> None:
        original = builtins.__import__

        def guarded(name, *args, **kwargs):
            if name.split(".")[0] in {"dbt", "sqlglot"}:
                raise AssertionError("dbt import must not load optional libraries")
            return original(name, *args, **kwargs)

        output, errors = StringIO(), StringIO()
        previous = Path.cwd()
        with (
            patch("builtins.__import__", side_effect=guarded),
            patch(
                "tarel.lineage.application.load_provider", side_effect=AssertionError("No provider")
            ),
        ):
            sdk_result = self.sdk.lineage.import_dbt(
                "shop", manifest=self.manifest, catalog_map={"Warehouse": "physical"}
            )
            try:
                os.chdir(self.root)
                with redirect_stdout(output), redirect_stderr(errors):
                    code = main(
                        [
                            "lineage",
                            "import-dbt",
                            "shop",
                            "--manifest",
                            str(self.manifest),
                            "--catalog-map",
                            "Warehouse=physical",
                            "--format",
                            "json",
                        ]
                    )
            finally:
                os.chdir(previous)
        self.assertEqual(code, 0, errors.getvalue())
        self.assertEqual(sdk_result.document, self.sdk.lineage.load("shop"))
        self.assertEqual(json.loads(output.getvalue())["lineage"], sdk_result.document.to_dict())
        self.assertEqual(Tarel(self.root / "other-state").lineage.list(), ())

    def test_unsupported_version_and_materialization_fail_before_state_write(self) -> None:
        self.payload["metadata"]["dbt_schema_version"] = (
            "https://schemas.getdbt.com/dbt/manifest/v11.json"
        )
        self.assert_import_fails("unsupported_dbt_manifest")
        self.payload["metadata"]["dbt_schema_version"] = (
            "https://schemas.getdbt.com/dbt/manifest/v12.json"
        )
        self.payload["nodes"][_DAILY]["config"]["materialized"] = "custom_unknown"
        self.assert_import_fails("unsupported_dbt_materialization")

    def test_unknown_disabled_test_dependency_duplicate_or_cycle_is_visible(self) -> None:
        original = copy.deepcopy(self.payload)
        for parents in (
            ["model.absent.orders"],
            ["test.shop.unique_orders"],
            [_DAILY],
            ["model.shop.filtered", "model.shop.filtered"],
        ):
            self.payload = copy.deepcopy(original)
            self.payload["nodes"][_DAILY]["depends_on"]["nodes"] = parents
            with self.subTest(parents=parents):
                self.assert_import_fails()
        self.payload = copy.deepcopy(original)
        self.payload["nodes"][_STAGE]["depends_on"]["nodes"] = [_DAILY]
        self.assert_import_fails()
        self.payload = copy.deepcopy(original)
        self.payload["nodes"][_DAILY]["config"]["enabled"] = False
        self.assert_import_fails()

    def test_bad_relation_missing_qualifiers_and_duplicate_targets_are_visible(self) -> None:
        original = copy.deepcopy(self.payload)
        for field, value in (
            ("database", None),
            ("schema", []),
            ("alias", ""),
            ("relation_name", '"Warehouse"."gold"."wrong"'),
            ("relation_name", '"unclosed'),
            ("relation_name", "Warehouse.gold."),
        ):
            self.payload = copy.deepcopy(original)
            self.payload["nodes"][_DAILY][field] = value
            with self.subTest(field=field, value=value):
                self.assert_import_fails()
        self.payload = copy.deepcopy(original)
        other = self.payload["nodes"]["model.shop.sales_history"]
        other.update(alias="sales_by_day", relation_name=None)
        self.assert_import_fails()

    def test_quoted_relation_components_and_bigquery_paths(self) -> None:
        for adapter, relation in (
            ("postgres", '"Warehouse"."gold"."sales.by.day"'),
            ("sqlserver", "[Warehouse].[gold].[sales.by.day]"),
            ("spark", "`Warehouse`.`gold`.`sales.by.day`"),
        ):
            self.payload["metadata"]["adapter_type"] = adapter
            self.payload["nodes"][_DAILY].update(alias="sales.by.day", relation_name=relation)
            self.write()
            source = load_dbt_manifest(self.manifest)
            self.assertIn(
                'Warehouse.gold."sales.by.day"', {m.target for m in source.materializations}
            )
        self.payload["metadata"]["adapter_type"] = "bigquery"
        self.payload["nodes"][_DAILY].update(
            alias="sales_by_day", relation_name="`Warehouse.gold.sales_by_day`"
        )
        self.write()
        self.assertIn(
            "Warehouse.gold.sales_by_day",
            {m.target for m in load_dbt_manifest(self.manifest).materializations},
        )

    def test_invalid_json_root_identity_and_code_types_are_visible(self) -> None:
        for field, value in (
            ("unique_id", "model.wrong.id"),
            ("compiled_code", 0),
            ("raw_code", []),
            ("depends_on", {}),
            ("config", None),
        ):
            original = copy.deepcopy(self.payload)
            self.payload["nodes"][_DAILY][field] = value
            with self.subTest(field=field):
                self.assert_import_fails()
            self.payload = original
        for raw in ("{broken", "[]", '{"metadata": {}, "metadata": {}}', "\ufffd"):
            self.manifest.write_text(raw)
            with self.subTest(raw=raw), self.assertRaises(LineageFailure):
                load_dbt_manifest(self.manifest)
        self.manifest.unlink()
        with self.assertRaises(LineageFailure) as error:
            load_dbt_manifest(self.manifest)
        self.assertEqual(error.exception.code, "dbt_manifest_not_found")

    def test_bigquery_accepts_component_and_partial_quoting(self) -> None:
        self.payload["metadata"]["adapter_type"] = "bigquery"
        for relation in (
            "`Warehouse`.`gold`.`sales_by_day`",
            "`Warehouse`.gold.`sales_by_day`",
            "Warehouse.`gold`.sales_by_day",
        ):
            self.payload["nodes"][_DAILY]["relation_name"] = relation
            self.write()
            with self.subTest(relation=relation):
                result = self.sdk.lineage.import_dbt("shop", manifest=self.manifest)
                self.assertIn(
                    "Warehouse.gold.sales_by_day",
                    {m.target for m in result.document.materializations},
                )

    def test_source_aliases_keep_distinct_dependency_evidence_and_reviews(self) -> None:
        original = "source.shop.raw.orders"
        alias = "source.shop.alias.orders"
        self.payload["sources"][alias] = {
            **self.payload["sources"][original],
            "unique_id": alias,
        }
        self.payload["nodes"][_STAGE]["depends_on"]["nodes"].append(alias)
        self.write()
        result = self.sdk.lineage.import_dbt("shop", manifest=self.manifest)
        reads = [c for c in result.document.claims if c.target == "Warehouse.raw.orders"]
        self.assertEqual(len(reads), 2)
        self.assertEqual(len({c.id for c in reads}), 2)
        self.assertEqual(len({c.evidence.reference for c in reads}), 2)
        for parent in (alias, original):
            self.assertTrue(any(parent in c.evidence.reason for c in reads))
        for claim, decision in zip(reads, ("validate", "reject"), strict=True):
            self.sdk.lineage.decide("shop", claim.id, decision=decision, reason="Human checked.")
        before = self.sdk.lineage.load("shop")
        self.payload["nodes"][_STAGE]["depends_on"]["nodes"].reverse()
        self.write()
        moved = self.root / "new-alias-run.json"
        moved.write_bytes(self.manifest.read_bytes())
        refreshed = self.sdk.lineage.import_dbt("shop", manifest=moved)
        self.assertEqual(before.claims, refreshed.document.claims)
        links = [
            link
            for link in table_lineage(refreshed.document)
            if link.source == "Warehouse.raw.orders"
        ]
        self.assertEqual(len(links), 1)

    def test_failed_refresh_does_not_mutate_existing_lineage_or_reviews(self) -> None:
        result = self.sdk.lineage.import_dbt("shop", manifest=self.manifest)
        self.sdk.lineage.decide(
            "shop", result.document.claims[0].id, decision="reject", reason="Human rejected."
        )
        before = result.path.read_bytes()
        self.payload["nodes"][_DAILY]["depends_on"]["nodes"] = ["unknown"]
        self.write()
        with self.assertRaises(LineageFailure):
            self.sdk.lineage.import_dbt("shop", manifest=self.manifest)
        self.assertEqual(before, result.path.read_bytes())

    def test_table_projection_contains_declared_materialization_edges(self) -> None:
        result = self.sdk.lineage.import_dbt("shop", manifest=self.manifest)
        rows = table_lineage(result.document)
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(r.derivation == "declared_materialization" for r in rows))

    def test_seed_macro_dependencies_are_not_data_reads(self) -> None:
        seed = self.payload["nodes"]["seed.shop.country_codes"]
        seed["depends_on"]["macros"] = ["macro.shop.custom_seed_loader"]
        self.write()
        source = load_dbt_manifest(self.manifest)
        self.assertFalse(
            any(o.definition_external_id == "seed.shop.country_codes" for o in source.observations)
        )
        seed["depends_on"]["nodes"] = ["source.shop.raw.orders"]
        self.assert_import_fails()

    def test_cli_rejects_duplicate_mapping_entries(self) -> None:
        output, errors = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(
                [
                    "lineage",
                    "import-dbt",
                    "shop",
                    "--manifest",
                    str(self.manifest),
                    "--catalog-map",
                    "Warehouse=a",
                    "--catalog-map",
                    "Warehouse=b",
                ]
            )
        self.assertNotEqual(code, 0)
        self.assertIn("invalid_dbt_mapping", errors.getvalue())
