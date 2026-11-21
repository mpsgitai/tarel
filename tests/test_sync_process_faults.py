"""Real processes: killed at chosen points or at random, and running against each other.

``os._exit`` ends a process at a chosen line without any cleanup, as a crash does. It says nothing
about a power loss: what reaches the disk then depends on the machine, and these tests do not cut
power. The random kills may also miss the narrow windows, so they back up the chosen points.
"""

from __future__ import annotations

import json
import os
import random
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from tarel.sdk import Tarel
from tarel.sync.contracts import SyncFailure
from tests.test_sync_file_path import OBSERVED, _catalog

_ROOT = Path(__file__).resolve().parents[1]
_ENVIRONMENT = {**os.environ, "PYTHONPATH": f"{_ROOT / 'src'}"}
_KILL_AT = """
import os, sys
from tarel.cli import main
from tarel.sync import application
from tarel.sync.store import FileSyncStore

point = sys.argv[1]

def die(*_args, **_kwargs):
    os._exit(137)

original_save_head = FileSyncStore.save_head

if point == "before_commit":
    FileSyncStore.save_activation = die
elif point == "after_commit":
    def save_head(self, head):
        original_save_head(self, head)
        if head.pending is not None:
            os._exit(137)
    FileSyncStore.save_head = save_head
elif point == "after_graph":
    application._join_workspace = die
elif point == "before_clearing":
    def save_head(self, head):
        if head.pending is None:
            os._exit(137)
        original_save_head(self, head)
    FileSyncStore.save_head = save_head
sys.exit(main(sys.argv[2:]))
"""


def _cli(*arguments: str) -> list[str]:
    return [sys.executable, "-m", "tarel", *arguments]


class _Stream:
    """A publishing site plus trust for one central state, built once per test."""

    def __init__(self, root: Path, central: Tarel, name: str) -> None:
        self.root = root
        self.site = Tarel(root / f"{name}-site")
        self.name = name
        self.site.runtime.graph_store().save(_catalog(("dbo", "orders")))
        self.publisher_id = self.site.sync.init_publisher()
        self.stream = self.site.sync.create_stream("main", graph="erp", namespaces=("dbo",))
        self.counter = 0
        self.trust(central)

    def trust(self, central: Tarel) -> None:
        central.sync.trust(
            publisher_id=self.publisher_id,
            stream_id=self.stream.stream_id,
            graph_id=self.stream.graph_id,
            local_graph=f"{self.name}.erp",
            workspace="group",
            system=self.name,
            namespaces=("dbo",),
        )

    def publish(self, *tables: tuple[str, str]) -> Path:
        if tables:
            self.site.runtime.graph_store().save(_catalog(*tables))
        self.counter += 1
        path = self.root / f"{self.name}-{self.counter}.tarelpub"
        self.site.sync.publish("main", output=path, observed_at=OBSERVED, unsigned_dev=True)
        return path


class _FaultCase(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.central = Tarel(self.root / "central")
        self.site = _Stream(self.root, self.central, "site-a")

    def apply_args(self, path: Path, central: Tarel | None = None) -> list[str]:
        state = (central or self.central).root
        return _cli(
            "sync", "apply", str(path), "--state", str(state),
            "--allow-unsigned-dev", "--format", "json",
        )

    def run_apply(self, path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self.apply_args(path), env=_ENVIRONMENT, capture_output=True, text=True, check=False,
        )

    def graph_bytes(self, central: Tarel | None = None) -> bytes:
        state = (central or self.central).root
        return (state / "graphs" / "site-a.erp" / "graph.json").read_bytes()

    def expected_bytes(self, *paths: Path) -> bytes:
        """The graph a state reaches when nothing interrupts it."""
        clean = Tarel(self.root / f"clean-{len(list(self.root.iterdir()))}")
        self.site.trust(clean)
        for path in paths:
            clean.sync.apply(path, allow_unsigned_dev=True)
        return self.graph_bytes(clean)


class ChosenCrashPointTests(_FaultCase):
    def crash(self, point: str, path: Path) -> None:
        result = subprocess.run(
            [
                sys.executable, "-c", _KILL_AT, point, "sync", "apply", str(path),
                "--state", str(self.central.root), "--allow-unsigned-dev",
            ],
            env=_ENVIRONMENT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 137, result.stderr)

    def prepare(self) -> tuple[Path, Path, bytes]:
        first = self.site.publish()
        second = self.site.publish(("dbo", "orders"), ("dbo", "customers"))
        expected = self.expected_bytes(first, second)
        self.assertEqual(self.run_apply(first).returncode, 0)
        return first, second, expected

    def test_killed_during_preparation_leaves_the_old_state_active(self) -> None:
        _first, second, expected = self.prepare()
        before = self.graph_bytes()

        self.crash("before_commit", second)

        status = self.central.sync.status()[0]
        self.assertEqual(status.active_sequence, 1)
        self.assertFalse(status.activation_pending)
        self.assertEqual(self.graph_bytes(), before)

        self.assertEqual(self.run_apply(second).returncode, 0)
        self.assertEqual(self.graph_bytes(), expected)

    def test_killed_at_the_commit_point_is_finished_by_recover(self) -> None:
        _first, second, expected = self.prepare()
        before = self.graph_bytes()

        self.crash("after_commit", second)

        status = self.central.sync.status()[0]
        self.assertEqual(status.active_sequence, 2)
        self.assertTrue(status.activation_pending)
        self.assertEqual(self.graph_bytes(), before, "The old graph stays whole until the switch.")
        with self.assertRaises(SyncFailure) as caught:
            self.central.sync.plan(second, allow_unsigned_dev=True)
        self.assertEqual(caught.exception.code, "activation_pending")

        recovered = subprocess.run(
            _cli("sync", "recover", "--state", str(self.central.root), "--format", "json"),
            env=_ENVIRONMENT, capture_output=True, text=True, check=True,
        )

        self.assertEqual(json.loads(recovered.stdout)["finished"], [self.site.stream.stream_id])
        self.assertFalse(self.central.sync.status()[0].activation_pending)
        self.assertEqual(self.graph_bytes(), expected)

    def test_killed_after_the_graph_write_is_finished_by_repeating(self) -> None:
        _first, second, expected = self.prepare()

        self.crash("after_graph", second)
        self.assertTrue(self.central.sync.status()[0].activation_pending)
        self.assertEqual(self.graph_bytes(), expected)

        repeated = self.run_apply(second)

        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertFalse(json.loads(repeated.stdout)["applied"])
        self.assertFalse(self.central.sync.status()[0].activation_pending)

    def test_killed_just_before_clearing_the_pending_mark(self) -> None:
        _first, second, expected = self.prepare()

        self.crash("before_clearing", second)

        self.assertEqual(self.central.sync.recover(), (self.site.stream.stream_id,))
        self.assertEqual(self.central.sync.recover(), ())
        self.assertEqual(self.graph_bytes(), expected)

    def test_killed_on_the_first_takeover_still_ends_complete(self) -> None:
        first = self.site.publish()
        expected = self.expected_bytes(first)

        self.crash("after_commit", first)
        self.assertFalse((self.central.root / "graphs" / "site-a.erp" / "graph.json").exists())

        self.central.sync.recover()

        self.assertEqual(self.graph_bytes(), expected)
        workspace = self.central.runtime.workspace_store().load("group")
        self.assertEqual(workspace.systems[0].graphs, ("site-a.erp",))

    def test_a_blocked_recovery_says_so_instead_of_overwriting(self) -> None:
        _first, second, _expected = self.prepare()
        self.crash("after_commit", second)
        path = self.central.root / "graphs" / "site-a.erp" / "graph.json"
        from dataclasses import replace

        graph = self.central.runtime.graph_store().load("site-a.erp")
        self.central.runtime.graph_store().save(replace(graph, dialect="edited"))
        edited = path.read_bytes()

        with self.assertRaises(SyncFailure) as caught:
            self.central.sync.recover()

        self.assertEqual(caught.exception.code, "activation_blocked")
        self.assertEqual(path.read_bytes(), edited)


class RandomKillTests(_FaultCase):
    def test_a_kill_at_any_moment_leaves_one_whole_state_and_a_retry_finishes(self) -> None:
        generator = random.Random(4242)
        first = self.site.publish()
        second = self.site.publish(("dbo", "orders"), ("dbo", "customers"))
        expected_first = self.expected_bytes(first)
        expected_second = self.expected_bytes(first, second)
        for attempt in range(6):
            with self.subTest(attempt=attempt):
                central = Tarel(self.root / f"kill-{attempt}")
                self.site.trust(central)
                central.sync.apply(first, allow_unsigned_dev=True)
                process = subprocess.Popen(
                    self.apply_args(second, central),
                    env=_ENVIRONMENT,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                time.sleep(generator.uniform(0.0, 0.25))
                process.send_signal(signal.SIGKILL)
                process.wait()

                self.assertIn(self.graph_bytes(central), {expected_first, expected_second})

                central.sync.recover()
                central.sync.apply(second, allow_unsigned_dev=True)
                self.assertEqual(self.graph_bytes(central), expected_second)
                self.assertEqual(central.sync.status()[0].active_sequence, 2)


class ParallelTests(_FaultCase):
    def run_together(self, commands: list[list[str]]) -> list[subprocess.CompletedProcess[str]]:
        processes = [
            subprocess.Popen(
                command,
                env=_ENVIRONMENT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for command in commands
        ]
        return [
            subprocess.CompletedProcess(item.args, item.wait(), *item.communicate())
            for item in processes
        ]

    def test_parallel_takeovers_of_one_file_apply_it_exactly_once(self) -> None:
        path = self.site.publish()
        expected = self.expected_bytes(path)

        results = self.run_together([self.apply_args(path) for _ in range(5)])

        self.assertEqual([item.returncode for item in results], [0] * 5, results[0].stderr)
        applied = [json.loads(item.stdout)["applied"] for item in results]
        self.assertEqual(sum(applied), 1)
        self.assertEqual(self.graph_bytes(), expected)

    def test_parallel_publications_of_one_stream_never_roll_back(self) -> None:
        first = self.site.publish()
        second = self.site.publish(("dbo", "orders"), ("dbo", "customers"))
        third = self.site.publish(("dbo", "orders"), ("dbo", "items"))
        expected = self.expected_bytes(first, third)
        self.central.sync.apply(first, allow_unsigned_dev=True)

        results = self.run_together([self.apply_args(second), self.apply_args(third)])

        self.central.sync.apply(third, allow_unsigned_dev=True)
        self.assertEqual(self.central.sync.status()[0].active_sequence, 3)
        self.assertEqual(self.graph_bytes(), expected)
        self.assertEqual(results[1].returncode, 0, results[1].stderr)

    def test_parallel_streams_all_end_up_in_the_shared_workspace(self) -> None:
        others = [_Stream(self.root, self.central, f"site-{name}") for name in "bcdefgh"]
        files = [self.site.publish(), *(item.publish() for item in others)]

        results = self.run_together([self.apply_args(path) for path in files])

        self.assertEqual({item.returncode for item in results}, {0}, results[0].stderr)
        workspace = self.central.runtime.workspace_store().load("group")
        self.assertEqual(
            sorted(system.name for system in workspace.systems),
            sorted(["site-a", *(item.name for item in others)]),
        )
        self.assertEqual(len(self.central.runtime.graph_store().list()), 8)


class InboxTests(_FaultCase):
    def setUp(self) -> None:
        super().setUp()
        self.inbox = self.root / "inbox"
        self.inbox.mkdir()

    def deliver(self, path: Path, name: str | None = None) -> Path:
        target = self.inbox / (name or path.name)
        temporary = self.inbox / f"{target.name}.partial"
        temporary.write_bytes(path.read_bytes())
        temporary.replace(target)
        return target

    def passes(self):
        return self.central.sync.process_inbox(self.inbox, allow_unsigned_dev=True)

    def test_a_delivered_file_is_taken_over_and_moved_aside(self) -> None:
        delivered = self.deliver(self.site.publish())

        result = self.passes()

        self.assertEqual(result.items[0].outcome, "applied")
        self.assertEqual(result.items[0].action, "first_activation")
        self.assertFalse(delivered.exists())
        self.assertTrue((self.inbox / "done" / delivered.name).is_file())

    def test_an_unfinished_upload_is_left_alone(self) -> None:
        partial = self.inbox / "next.tarelpub.partial"
        partial.write_bytes(self.site.publish().read_bytes()[:100])
        hidden = self.inbox / ".next.tarelpub"
        hidden.write_bytes(b"x")

        self.assertEqual(self.passes().items, ())

        self.assertTrue(partial.exists())
        self.assertTrue(hidden.exists())

    def test_a_truncated_file_under_its_final_name_fails_its_checks(self) -> None:
        delivered = self.inbox / "cut.tarelpub"
        delivered.write_bytes(self.site.publish().read_bytes()[:100])

        result = self.passes()

        self.assertEqual((result.items[0].outcome, result.items[0].code),
                         ("rejected", "invalid_package"))
        reason = json.loads((self.inbox / "rejected" / "cut.tarelpub.reason.json").read_text())
        self.assertEqual(reason["code"], "invalid_package")
        self.assertEqual(self.central.runtime.graph_store().list(), ())

    def test_a_young_file_waits_for_the_next_pass(self) -> None:
        delivered = self.deliver(self.site.publish())

        result = self.central.sync.process_inbox(
            self.inbox, allow_unsigned_dev=True, min_age_seconds=3600,
        )

        self.assertEqual(result.items, ())
        self.assertTrue(delivered.exists())

    def test_a_transport_cannot_skip_the_signature_rule(self) -> None:
        self.deliver(self.site.publish())

        result = self.central.sync.process_inbox(self.inbox)

        self.assertEqual(result.items[0].code, "unsigned_publication")
        self.assertEqual(self.central.runtime.graph_store().list(), ())

    def test_a_symlink_is_refused_without_following_it(self) -> None:
        target = self.site.publish()
        (self.inbox / "link.tarelpub").symlink_to(target)

        result = self.passes()

        self.assertEqual(result.items[0].outcome, "rejected")
        self.assertTrue(target.exists())
        self.assertEqual(self.central.runtime.graph_store().list(), ())

    def test_a_pass_finishes_interrupted_work_first(self) -> None:
        first = self.site.publish()
        subprocess.run(
            [
                sys.executable, "-c", _KILL_AT, "after_commit", "sync", "apply", str(first),
                "--state", str(self.central.root), "--allow-unsigned-dev",
            ],
            env=_ENVIRONMENT, check=False, capture_output=True,
        )
        self.assertTrue(self.central.sync.status()[0].activation_pending)

        self.passes()

        self.assertFalse(self.central.sync.status()[0].activation_pending)

    def test_cli_exit_status_reports_a_rejected_file(self) -> None:
        (self.inbox / "cut.tarelpub").write_bytes(b"x")

        result = subprocess.run(
            _cli(
                "sync", "inbox", "--directory", str(self.inbox),
                "--state", str(self.central.root), "--format", "json",
            ),
            env=_ENVIRONMENT, capture_output=True, text=True, check=False,
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["rejected"], 1)


class AbandonedCopyTests(_FaultCase):
    def test_prune_clears_a_copy_a_killed_process_left_behind(self) -> None:
        path = self.site.publish()
        self.central.sync.apply(path, allow_unsigned_dev=True)
        incoming = self.central.runtime.sync_store().incoming_directory()
        descriptor, name = tempfile.mkstemp(dir=incoming, prefix=".incoming-", suffix=".tmp")
        os.close(descriptor)
        os.utime(name, (0, 0))

        self.central.sync.prune(self.site.stream.stream_id)

        self.assertFalse(Path(name).exists())
