from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase
from unittest.mock import patch

from tarel.annotations.contracts import AnnotationFailure
from tarel.annotations.tasks import plan_annotation_tasks
from tarel.application import (
    apply_annotation_use_case,
    edit_annotation_use_case,
    refresh_graph_use_case,
    run_annotation_batch_use_case,
)
from tarel.connectors.contracts import CatalogField, CatalogObject, CatalogResult
from tarel.file_lock import file_lock
from tarel.graph.build import build_graph_from_catalog
from tarel.graph.contracts import GraphFailure
from tarel.graph.revision import graph_revision
from tarel.runtime import TarelRuntime

SOURCE = str(Path(__file__).resolve().parents[1] / "src")


class GraphWriteTests(TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runtime = TarelRuntime.local(self.root / ".tarel")
        self.graph = build_graph_from_catalog("demo", _catalog())
        self.store = self.runtime.graph_store()
        self.store.save(self.graph)

    def test_parallel_real_cli_annotations_preserve_all_disjoint_objects(self) -> None:
        tasks = plan_annotation_tasks(self.graph, missing_only=False)
        children = [
            subprocess.Popen(
                [sys.executable, "-m", "tarel", "annotation", "apply", "demo", "--input", "-"],
                cwd=self.root,
                env=dict(os.environ, PYTHONPATH=SOURCE),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _task in tasks
        ]
        try:
            for child, task in zip(children, tasks, strict=True):
                child.stdin.write(json.dumps(_proposal(task)) + "\n")
                child.stdin.close()
                child.stdin = None
            for child in children:
                _out, err = child.communicate(timeout=30)
                self.assertEqual(child.returncode, 0, err)
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.communicate()
        saved = self.store.load("demo")
        self.assertTrue(
            all(n.annotation is not None for n in saved.nodes if n.type in {"table", "field"})
        )

    def test_full_proposal_rejects_intervening_annotation(self) -> None:
        proposal = _proposal(plan_annotation_tasks(self.graph, missing_only=False)[0])
        apply_annotation_use_case("demo", proposal, runtime=self.runtime)
        stale = json.loads(json.dumps(proposal))
        stale["annotation"]["description"] = "A stale competing change."
        with self.assertRaises(AnnotationFailure) as failure:
            apply_annotation_use_case("demo", stale, runtime=self.runtime)
        self.assertEqual(failure.exception.code, "stale_proposal")
        self.assertNotEqual(
            self.store.load("demo").node_by_id()[proposal["target_id"]].annotation.description,
            stale["annotation"]["description"],
        )

    def test_batch_merges_another_agents_annotation_without_holding_provider_lock(self) -> None:
        tasks = plan_annotation_tasks(self.graph)
        started, resume = Event(), Event()
        provider = _WaitingProvider(_proposal(tasks[0])["annotation"], started, resume)
        with (
            patch("tarel.application.load_provider", return_value=provider),
            ThreadPoolExecutor(1) as pool,
        ):
            future = pool.submit(
                run_annotation_batch_use_case,
                "demo",
                provider_name="fixture",
                objects={tasks[0].target_label},
                runtime=self.runtime,
            )
            try:
                self.assertTrue(started.wait(5))
                apply_annotation_use_case("demo", _proposal(tasks[1]), runtime=self.runtime)
            finally:
                resume.set()
            result = future.result(timeout=10)
        nodes = self.store.load("demo").node_by_id()
        self.assertIsNotNone(nodes[tasks[0].target_id].annotation)
        self.assertIsNotNone(nodes[tasks[1].target_id].annotation)
        self.assertEqual(nodes[tasks[0].target_id].annotation.provenance.source, "provider")
        self.assertEqual(nodes[tasks[1].target_id].annotation.provenance.source, "agent")
        self.assertEqual(result.graph, self.store.load("demo"))

    def test_human_edit_while_provider_waits_survives_stale_batch(self) -> None:
        task = plan_annotation_tasks(self.graph)[0]
        apply_annotation_use_case("demo", _proposal(task), runtime=self.runtime)
        task = plan_annotation_tasks(self.store.load("demo"), missing_only=False)[0]
        started, resume = Event(), Event()
        provider = _WaitingProvider(_proposal(task)["annotation"], started, resume)
        with (
            patch("tarel.application.load_provider", return_value=provider),
            ThreadPoolExecutor(1) as pool,
        ):
            future = pool.submit(
                run_annotation_batch_use_case,
                "demo",
                provider_name="fixture",
                objects={task.target_label},
                missing_only=False,
                runtime=self.runtime,
            )
            try:
                self.assertTrue(started.wait(5))
                edit_annotation_use_case(
                    "demo",
                    task.target_label,
                    {"description": "Human correction."},
                    reason="Verified locally.",
                    runtime=self.runtime,
                )
            finally:
                resume.set()
            with self.assertRaises(AnnotationFailure):
                future.result(timeout=10)
        self.assertEqual(
            self.store.load("demo").node_by_id()[task.target_id].annotation.description,
            "Human correction.",
        )

    def test_refresh_preserves_annotation_saved_during_observation(self) -> None:
        task = plan_annotation_tasks(self.graph)[1]

        def observe(*_args, **_kwargs):
            apply_annotation_use_case("demo", _proposal(task), runtime=self.runtime)
            return _catalog(extra=True)

        with patch("tarel.application.discover_catalog_use_case", side_effect=observe):
            result = refresh_graph_use_case("demo", runtime=self.runtime)
        saved = self.store.load("demo")
        self.assertIsNotNone(saved.node_by_id()[task.target_id].annotation)
        self.assertEqual(result.report.added_nodes, 1)
        self.assertTrue(any(n.label == "new_field" for n in saved.nodes))

    def test_refresh_rejects_observation_after_another_schema_change(self) -> None:
        changed = build_graph_from_catalog("demo", _catalog(extra=True))

        def observe(*_args, **_kwargs):
            self.store.save(changed, expected_revision=graph_revision(self.graph))
            return _catalog()

        with (
            patch("tarel.application.discover_catalog_use_case", side_effect=observe),
            self.assertRaises(GraphFailure) as failure,
        ):
            refresh_graph_use_case("demo", runtime=self.runtime)
        self.assertEqual(failure.exception.code, "graph_conflict")
        self.assertEqual(self.store.load("demo"), changed)

    def test_compare_and_swap_rejects_stale_save(self) -> None:
        before = graph_revision(self.graph)
        task = plan_annotation_tasks(self.graph)[0]
        apply_annotation_use_case("demo", _proposal(task), runtime=self.runtime)
        with self.assertRaises(GraphFailure) as failure:
            self.store.save(self.graph, expected_revision=before)
        self.assertEqual(failure.exception.code, "graph_conflict")

    def test_create_rejects_existing_graph(self) -> None:
        with self.assertRaises(GraphFailure) as failure:
            self.store.create(self.graph)
        self.assertEqual(failure.exception.code, "graph_exists")

    def test_update_failure_releases_lock_and_does_not_write(self) -> None:
        before = self.store.path("demo").read_bytes()

        def fail(_graph):
            raise ValueError("Invalid proposed transformation.")

        with self.assertRaises(ValueError):
            self.store.update("demo", fail)
        self.assertEqual(self.store.path("demo").read_bytes(), before)
        task = plan_annotation_tasks(self.graph)[0]
        apply_annotation_use_case("demo", _proposal(task), runtime=self.runtime)

    def test_process_exit_releases_os_lock_without_deleting_lock_file(self) -> None:
        lock = self.store.path("demo").with_name(".write.lock")
        script = (
            "import sys,time; from pathlib import Path; from tarel.file_lock import file_lock; "
            "ctx=file_lock(Path(sys.argv[1])); ctx.__enter__(); "
            "print('ready',flush=True); time.sleep(60)"
        )
        child = subprocess.Popen(
            [sys.executable, "-c", script, str(lock)],
            env=dict(os.environ, PYTHONPATH=SOURCE),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertEqual(child.stdout.readline().strip(), "ready")
            child.kill()
            child.communicate(timeout=5)
            with file_lock(lock, timeout=1):
                self.assertTrue(lock.exists())
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate()

    def test_state_lock_timeout_is_visible_without_publishing_graph(self) -> None:
        before = self.store.path("demo").read_bytes()
        from tarel.file_lock import state_write_lock

        def short_lock(root):
            return file_lock(root / ".state.lock", timeout=0.02)

        with (
            state_write_lock(self.runtime.root),
            patch("tarel.graph.store.state_write_lock", short_lock),
            self.assertRaises(GraphFailure),
        ):
            self.store.save(replace(self.graph, catalog="changed"))
        self.assertEqual(self.store.path("demo").read_bytes(), before)
        self.assertEqual(list(self.store.path("demo").parent.glob(".graph-*.tmp")), [])

    def test_first_lock_creation_and_many_waiters_serialize_updates(self) -> None:
        lock = self.root / "new.lock"
        counter = self.root / "counter.txt"
        counter.write_text("0")

        def increment(_index):
            with file_lock(lock, timeout=5):
                value = int(counter.read_text())
                time.sleep(0.001)
                counter.write_text(str(value + 1))

        with ThreadPoolExecutor(12) as pool:
            list(pool.map(increment, range(60)))
        self.assertEqual(counter.read_text(), "60")


class _WaitingProvider:
    name = "fixture"
    default_model = "fixture"

    def __init__(self, annotation, started, resume):
        self.annotation, self.started, self.resume = annotation, started, resume

    def generate_structured(self, _request):
        self.started.set()
        if not self.resume.wait(5):
            raise RuntimeError("Provider test was not resumed.")
        return self.annotation


def _catalog(*, extra=False):
    return CatalogResult(
        connector="fixture",
        source_type="database",
        catalog="Demo",
        dialect="ansi",
        objects=tuple(
            CatalogObject(
                namespace="main",
                name=name,
                kind="table",
                fields=(CatalogField("id", 1, "integer", False),)
                + (
                    (CatalogField("new_field", 2, "text", True),)
                    if extra and name == "Alpha"
                    else ()
                ),
            )
            for name in ("Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot")
        ),
    )


def _proposal(task):
    def annotation(description):
        return dict(
            description=description,
            role=None,
            synonyms=[],
            tags=[],
            warnings=[],
            confidence=0.7,
            confidence_reason="Synthetic test schema.",
            evidence=[dict(source="object_name", reference=task.target_label)],
        )

    return dict(
        task_id=task.id,
        target_id=task.target_id,
        mode=task.mode,
        field_names=list(task.field_names) if task.mode == "missing" else [],
        include_object=task.include_object if task.mode == "missing" else None,
        annotation=dict(
            **annotation("Synthetic object description."),
            grain=None,
            fields=[
                dict(name=name, semantic_type=None, **annotation("Synthetic field."))
                for name in task.field_names
            ],
        ),
    )
