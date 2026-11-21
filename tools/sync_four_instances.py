"""Four isolated TAREL instances exchanging metadata through files, end to end.

``cloud-a``, ``cloud-b``, ``onprem`` and ``central`` are separate state roots driven only through
separate ``python -m tarel`` processes over real SQLite sources with synthetic metadata. The names
are labels: everything runs on this machine, so this proves the file path and its rules, not any
cloud, gateway or network integration. Where ``unshare -rn`` exists, the offline steps run in a
process without network; the report says whether they did.

    python tools/sync_four_instances.py [--keep DIR]

Prints one line per check and exits non-zero if any fails. The numbers refer to the acceptance list
of the sync assignment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT = {
    **os.environ,
    "PYTHONPATH": str(ROOT / "src"),
}
OLD_TIME = "2020-01-01T00:00:00Z"


@dataclass(slots=True)
class Result:
    code: int
    data: Any
    error: str


@dataclass(slots=True)
class Site:
    name: str
    directory: Path
    local_graph: str
    publisher_id: str = ""
    stream_id: str = ""
    graph_id: str = ""
    counter: int = 0

    @property
    def key(self) -> Path:
        return self.directory.parent / "keys" / self.name

    @property
    def database(self) -> Path:
        return self.directory / "source.sqlite"

    @property
    def config(self) -> Path:
        return self.directory / "source.toml"


@dataclass(slots=True)
class Report:
    failures: list[str] = field(default_factory=list)
    checks: int = 0

    def check(self, label: str, passed: bool, detail: object = "") -> None:
        self.checks += 1
        print(f"{'PASS' if passed else 'FAIL'}  {label}" + (f"  [{detail}]" if not passed else ""))
        if not passed:
            self.failures.append(label)


class Lab:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.central = root / "central"
        self.manual = root / "central-manual"
        self.inbox = root / "central-inbox"
        self.delivered: list[Path] = []
        self.offline_prefix = _offline_prefix()
        for directory in (self.central, self.manual, self.inbox, root / "keys", root / "wire"):
            directory.mkdir(parents=True)

    def run(self, cwd: Path, *arguments: object, offline: bool = False) -> Result:
        prefix = self.offline_prefix if offline else []
        command = [
            *prefix, sys.executable, "-m", "tarel", *(str(item) for item in arguments),
            "--format", "json",
        ]
        done = subprocess.run(
            command, cwd=cwd, env=ENVIRONMENT, capture_output=True, text=True, check=False,
        )
        try:
            data = json.loads(done.stdout) if done.stdout.strip() else None
        except json.JSONDecodeError:
            data = done.stdout
        return Result(done.returncode, data, done.stderr.strip())

    def must(self, cwd: Path, *arguments: object, offline: bool = False) -> Any:
        result = self.run(cwd, *arguments, offline=offline)
        if result.code != 0:
            raise SystemExit(f"Setup failed: {arguments}: {result.error}")
        return result.data

    def create_site(self, name: str, local_graph: str, tables: tuple[str, ...]) -> Site:
        site = Site(name, self.root / name, local_graph)
        site.directory.mkdir()
        write_tables(site.database, tables)
        site.config.write_text(_config(site.database), encoding="utf-8")
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(site.key)],
            check=True,
        )
        self.must(site.directory, "graph", "build", "erp", "--connector", "sqlite",
                  "--config", site.config)
        site.publisher_id = self.must(
            site.directory, "sync", "init", "--state", ".tarel",
        )["publisher_id"]
        stream = self.must(
            site.directory, "sync", "stream-create", "--state", ".tarel",
            "--name", "main", "--graph", "erp", "--namespace", "main",
        )
        site.stream_id, site.graph_id = stream["stream_id"], stream["graph_id"]
        for central in (self.central, self.manual):
            self.grant(central, site)
        return site

    def grant(self, central: Path, site: Site) -> None:
        self.must(central, "sync", "trust-key", "--state", ".tarel",
                  "--publisher-id", site.publisher_id, "--public-key-file", f"{site.key}.pub")
        self.must(central, "sync", "trust-add", "--state", ".tarel",
                  "--publisher-id", site.publisher_id, "--stream-id", site.stream_id,
                  "--graph-id", site.graph_id, "--local-graph", site.local_graph,
                  "--workspace", "group", "--system", site.name, "--namespace", "main")

    def publish(self, site: Site, *options: object, offline: bool = False) -> tuple[Path, Result]:
        site.counter += 1
        path = self.root / "wire" / f"{site.name}-{site.counter:03d}.tarelpub"
        result = self.run(
            site.directory, "sync", "publish", "--state", ".tarel", "--stream", "main",
            "--output", path, "--signing-key", site.key, *options, offline=offline,
        )
        return path, result

    def good_file(self, site: Site, *options: object, offline: bool = False) -> Path:
        path, result = self.publish(site, *options, offline=offline)
        if result.code != 0:
            raise SystemExit(f"Publish failed for {site.name}: {result.error}")
        self.delivered.append(path)
        return path

    def apply(self, path: Path, *, offline: bool = False) -> Result:
        return self.run(self.central, "sync", "apply", path, "--state", ".tarel", offline=offline)

    def by_inbox(self, path: Path) -> Any:
        """A transport's whole job: place the file under a temporary name, then rename it."""
        temporary = self.inbox / f".{path.name}.uploading"
        shutil.copyfile(path, temporary)
        temporary.replace(self.inbox / path.name)
        return self.run(self.central, "sync", "inbox", "--state", ".tarel",
                        "--directory", self.inbox)

    def status(self, site: Site, central: Path | None = None) -> dict[str, Any]:
        streams = self.must(central or self.central, "sync", "status", "--state", ".tarel",
                            "--max-age-hours", "1")["streams"]
        return next(item for item in streams if item["stream_id"] == site.stream_id)

    def refresh(self, site: Site) -> Result:
        return self.run(site.directory, "graph", "refresh", "erp", "--config", site.config)

    def graph_digest(self, site: Site, central: Path | None = None) -> str:
        path = (central or self.central) / ".tarel" / "graphs" / site.local_graph / "graph.json"
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def graph(self, site: Site) -> dict[str, Any]:
        path = self.central / ".tarel" / "graphs" / site.local_graph / "graph.json"
        return json.loads(path.read_text(encoding="utf-8"))


def write_tables(database: Path, tables: tuple[str, ...]) -> None:
    database.unlink(missing_ok=True)
    with sqlite3.connect(database) as connection:
        for table in tables:
            connection.execute(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY, label TEXT)')


def _config(database: Path) -> str:
    url = f"sqlite:///{database.resolve().as_posix()}"
    return f'[sqlite]\nurl = "{url}"\ndefault_database = "Shop"\n'


def _offline_prefix() -> list[str]:
    if shutil.which("unshare") is None:
        return []
    probe = subprocess.run(["unshare", "-rn", "true"], capture_output=True, check=False)
    return ["unshare", "-rn"] if probe.returncode == 0 else []


def _network_is_gone(prefix: list[str]) -> bool:
    if not prefix:
        return False
    code = (
        "import socket;s=socket.socket();s.settimeout(2);"
        "s.connect(('1.1.1.1',53))"
    )
    return subprocess.run(
        [*prefix, sys.executable, "-c", code], capture_output=True, check=False,
    ).returncode != 0


def code_of(result: Result) -> str:
    text = result.error
    return text[text.find("[") + 1 : text.find("]")] if "[" in text else text


def run(root: Path) -> Report:
    report = Report()
    lab = Lab(root)
    check = report.check
    a = lab.create_site("cloud-a", "cloud-a.erp", ("orders", "customers", "temp"))
    b = lab.create_site("cloud-b", "cloud-b.erp", ("orders", "invoices"))
    onprem = lab.create_site("onprem", "onprem.erp", ("orders", "machines"))

    isolated = _network_is_gone(lab.offline_prefix)
    print(f"Offline steps run without a network: {'yes' if isolated else 'NOT ISOLATED HERE'}")

    # First delivery: two by the inbox, one purely by file with no network in either process.
    a1 = lab.good_file(a)
    b1 = lab.good_file(b)
    onprem1 = lab.good_file(onprem, offline=True)
    lab.by_inbox(a1)
    lab.by_inbox(b1)
    applied = lab.apply(onprem1, offline=True)
    check("42 file-only takeover without network access", applied.code == 0, applied.error)
    active = [lab.status(site)["active_sequence"] for site in (a, b, onprem)]
    check("1  three sites published for the first time", active == [1, 1, 1], active)

    scope = lab.must(lab.central, "workspace", "scope", "group")
    labels = [item for item in scope["objects"] if item["label"] == "main.orders"]
    check("2  central uses their metadata together", len(scope["objects"]) == 7, scope["objects"])
    check(
        "3  same object names stay apart by origin",
        sorted(item["graph"] for item in labels) == ["cloud-a.erp", "cloud-b.erp", "onprem.erp"],
        labels,
    )
    workspace = lab.must(lab.central, "workspace", "show", "group")
    check("24 equal names create no join", not workspace.get("relationships"), workspace)

    # Update of one site only.
    others = (lab.graph_digest(b), lab.graph_digest(onprem))
    write_tables(a.database, ("orders", "customers", "temp", "newest"))
    lab.refresh(a)
    a2 = lab.good_file(a)
    updated = lab.apply(a2)
    check(
        "4  an update changes only its own origin",
        updated.data["plan"]["objects_added"] == ["main.newest"]
        and others == (lab.graph_digest(b), lab.graph_digest(onprem)),
        updated.data,
    )

    before = lab.graph_digest(a)
    repeated = lab.apply(a2)
    check(
        "6  the same publication twice changes nothing",
        repeated.code == 0 and not repeated.data["applied"] and before == lab.graph_digest(a),
        repeated,
    )

    lab.refresh(a)
    a3 = lab.good_file(a)
    fresh = lab.apply(a3)
    check(
        "7  new publication, same content: freshness only",
        fresh.data["plan"]["action"] == "confirm_freshness" and before == lab.graph_digest(a),
        fresh.data,
    )

    stale = lab.apply(a2)
    check("8  an older publication does not roll back",
          code_of(stale) == "stale_publication" and lab.status(a)["active_sequence"] == 3, stale)

    # A missing intermediate snapshot is not a fork.
    write_tables(a.database, ("orders", "customers", "temp", "newest", "skipped"))
    lab.refresh(a)
    lab.good_file(a)
    lab.delivered.pop()
    write_tables(a.database, ("orders", "customers", "temp", "newest", "latest"))
    lab.refresh(a)
    a5 = lab.good_file(a)
    jumped = lab.apply(a5)
    check("10 a missing intermediate state is accepted and reported",
          jumped.code == 0 and "Skipped publications 4..4" in jumped.data["plan"]["warnings"][0],
          jumped)

    # Restoring an old state backup reuses a number with other content.
    backup = root / "cloud-b-backup"
    shutil.copytree(b.directory, backup)
    write_tables(b.database, ("orders", "invoices", "first"))
    lab.refresh(b)
    b2 = lab.good_file(b)
    lab.apply(b2)
    shutil.rmtree(b.directory)
    shutil.copytree(backup, b.directory)
    write_tables(b.database, ("orders", "invoices", "second"))
    lab.refresh(b)
    conflict_file, _ = lab.publish(b)
    conflict = lab.apply(conflict_file)
    check("9  one sequence with other content is a visible conflict",
          code_of(conflict) == "publication_conflict"
          and lab.status(b)["last_failure"]["code"] == "publication_conflict", conflict)

    # Renaming the host or directory is no new identity.
    renamed = root / "onprem-renamed-host"
    onprem.directory.rename(renamed)
    onprem.directory = renamed
    onprem.config.write_text(_config(onprem.database), encoding="utf-8")
    write_tables(onprem.database, ("orders", "machines", "tools"))
    lab.refresh(onprem)
    onprem2 = lab.good_file(onprem, offline=True)
    moved = lab.apply(onprem2, offline=True)
    check("11 a renamed host keeps its publisher identity", moved.code == 0, moved)

    # A copied installation: both claim the same stream and drift apart.
    twin = Site("cloud-a-copy", root / "cloud-a-copy", a.local_graph, a.publisher_id,
                a.stream_id, a.graph_id, 50)
    shutil.copytree(a.directory, twin.directory)
    twin.config.write_text(_config(twin.database), encoding="utf-8")
    shutil.copy(a.key, twin.key)
    shutil.copy(f"{a.key}.pub", f"{twin.key}.pub")
    write_tables(a.database, ("orders", "customers", "temp", "newest", "latest", "ours"))
    lab.refresh(a)
    a6 = lab.good_file(a)
    lab.apply(a6)
    write_tables(twin.database, ("orders", "customers", "temp", "newest", "latest", "theirs"))
    lab.refresh(twin)
    twin_first, _ = lab.publish(twin)
    twin_clash = lab.apply(twin_first)
    lab.refresh(twin)
    twin_second, _ = lab.publish(twin)
    twin_fork = lab.apply(twin_second)
    check("12 two writers with a copied identity become visible",
          code_of(twin_clash) == "publication_conflict"
          and code_of(twin_fork) == "publication_conflict", (twin_clash, twin_fork))

    # A central relationship to something the source then deletes.
    lab.must(lab.central, "workspace", "relationship", "add", "group",
             "--from", "cloud-a.erp:main.temp.id", "--to", "onprem.erp:main.orders.id",
             "--reason", "Reviewed by hand", "--validated")
    write_tables(a.database, ("orders", "customers", "newest", "latest", "ours"))
    lab.refresh(a)
    a7 = lab.good_file(a)
    deleted = lab.apply(a7)
    check("13 a proven source deletion removes the object",
          deleted.data["plan"]["objects_deleted"] == ["main.temp"]
          and "main.temp" not in {node["label"] for node in lab.graph(a)["nodes"]}, deleted.data)
    dangling = lab.status(a)["dangling_references"]
    kept = lab.must(lab.central, "workspace", "show", "group")["relationships"][0]
    check("19 a central relationship to a removed object is reported and kept",
          [item["kind"] for item in dangling] == ["relationship_object"]
          and kept["state"] == "validated", (dangling, kept))
    still = lab.run(lab.central, "workspace", "scope", "group")
    check("19 the shared view keeps working", still.code == 0, still.error)

    # Partial and failed observation.
    digest = lab.graph_digest(a)
    partial, _ = lab.publish(
        a, "--observed-at", "2030-01-01T12:00:00Z", "--completeness", "partial",
    )
    refused = lab.apply(partial)
    check("14 a partial extract has no deleting effect",
          code_of(refused) == "incomplete_snapshot" and digest == lab.graph_digest(a), refused)

    a.database.write_bytes(b"this is no database")
    failed = lab.refresh(a)
    blocked, blocked_result = lab.publish(a)
    check("15 a failed observation blocks publishing and keeps the last state",
          failed.code != 0
          and code_of(blocked_result) == "observation_failed"
          and not blocked.exists()
          and digest == lab.graph_digest(a), blocked_result)

    # Age stays visible for a site that has gone quiet.
    old_file = lab.good_file(onprem, "--observed-at", OLD_TIME)
    lab.by_inbox(old_file)
    quiet = lab.status(onprem)
    check("41 received now, observed long ago: shown as old",
          quiet["stale"] is True and quiet["observed_at"] == OLD_TIME, quiet)

    # Same files by hand into a second central state.
    outcome = [lab.run(lab.manual, "sync", "apply", path, "--state", ".tarel")
               for path in lab.delivered]
    same = all(
        lab.status(site)["active_publication_id"] == lab.status(site, lab.manual)[
            "active_publication_id"
        ]
        and lab.status(site)["active_content_revision"]
        == lab.status(site, lab.manual)["active_content_revision"]
        for site in (a, b, onprem)
    )
    check("43 inbox and manual import reach the same active publications", same, outcome[-1:])
    check("43 and the same graph for an origin without central edits",
          lab.graph_digest(b) == lab.graph_digest(b, lab.manual)
          and lab.graph_digest(onprem) == lab.graph_digest(onprem, lab.manual))

    # Isolation: nothing secret or foreign reached the central state.
    leaked = [
        path
        for path in (lab.central / ".tarel").rglob("*")
        if path.is_file()
        and (path.name.endswith(".toml") or b"PRIVATE KEY" in path.read_bytes()
             or b"sqlite:///" in path.read_bytes())
    ]
    check("   no key, connector config or source URL reached the central state", not leaked, leaked)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keep", type=Path, help="Build in this new directory and keep it.")
    args = parser.parse_args()
    if shutil.which("ssh-keygen") is None:
        print("ssh-keygen is required.", file=sys.stderr)
        return 2
    if args.keep is not None:
        args.keep.mkdir(parents=True)
        report = run(args.keep.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix="tarel-four-instances-") as temporary:
            report = run(Path(temporary))
    print(f"{report.checks} checks, {len(report.failures)} failed")
    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
