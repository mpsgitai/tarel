"""Measure agent-facing output sizes and error repair against a real TAREL state.

The state is copied into a temporary directory first; the original is never written. Each check
prints its measured value next to its target, and the script exits 1 when any target is missed,
so a regression is visible instead of averaged away.

    python tools/evals/check_agent_output_budgets.py --state ../BI_Lab/Gesamtsystem/.tarel

The checks name objects of the BI Lab estate (lakehouse and Wide World Importers); a state
without them reports the affected checks as failed, not as skipped.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

_CUSTOMER_SALES = (
    "lineage", "upstream", "bi_lab.gold.customer_sales",
    "--lineage", "lakehouse-dbt", "--graph", "lakehouse-iceberg", "--format", "json",
)
_DELTA_SCENARIO = (
    "lineage", "upstream", "bi_lab_delta.scenario.customer_scenario",
    "--lineage", "lakehouse-spark-delta", "--lineage", "lakehouse-dbt",
    "--graph", "lakehouse-delta", "--graph", "lakehouse-iceberg", "--format", "json",
)
_WWI_FOCUS = ("focus", "show", "wwi-sales-backward", "--format", "json")
_MISPLACED_GRAPH = (
    "lineage", "upstream", "bi_lab.gold.customer_sales",
    "--lineage", "lakehouse-airflow", "--graph", "lakehouse-dbt", "--format", "json",
)


@dataclass(frozen=True, slots=True)
class Run:
    code: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    measured: str
    target: str


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--state", type=Path, required=True, help="A .tarel directory to copy.")
    args = parser.parse_args(argv)
    if not args.state.is_dir():
        parser.error(f"not a directory: {args.state}")
    with TemporaryDirectory(prefix="tarel-budget-") as directory:
        root = Path(directory)
        shutil.copytree(args.state, root / ".tarel", symlinks=False)
        checks = _checks(lambda *arguments: _tarel(root, arguments))
    width = max(len(item.name) for item in checks)
    for item in checks:
        status = "PASS" if item.passed else "FAIL"
        print(f"{status}  {item.name:<{width}}  {item.measured:>22}  target {item.target}")
    failed = sum(not item.passed for item in checks)
    print(f"{len(checks)} checks, {failed} failed")
    return 1 if failed else 0


def _checks(tarel: Callable[..., Run]) -> list[Check]:
    checks = [
        _size_check("customer_sales compact", tarel, _CUSTOMER_SALES, limit=2400),
        _size_check("14-hop delta compact", tarel, _DELTA_SCENARIO, limit=3000),
    ]
    checks.extend(_focus_checks(tarel))
    checks.append(_error_check(tarel))
    checks.extend(_phase_two_checks(tarel))
    return checks


_GOLD = (
    "bi_lab.gold.customer_sales", "bi_lab.gold.delivery_performance", "bi_lab.gold.sales_daily",
    "bi_lab.gold.spark_sales_daily", "bi_lab.gold.supplier_comparison",
)
_GOLD_SLICE = tuple(
    argument for name in _GOLD for argument in ("--object", name.removeprefix("bi_lab."))
)


def _phase_two_checks(tarel: Callable[..., Run]) -> list[Check]:
    checks = []
    auto = tarel("lineage", "upstream", _GOLD[0], "--view", "compact", "--format", "json")
    unresolved = json.loads(auto.stdout)["summary"]["unresolved"] if auto.code == 0 else -1
    checks.append(Check("auto-resolved upstream unresolved", unresolved == 0, str(unresolved), "0"))

    down = tarel("lineage", "downstream", "bi_lab.bronze.lineitem", "--format", "json")
    reached = set(json.loads(down.stdout)["nodes"]) if down.code == 0 else set()
    found = sum(name in reached for name in _GOLD)
    checks.append(Check("downstream lineitem reaches gold", found == 5, f"{found}/5", "5/5"))

    objects = tarel("graph", "objects", "lakehouse-iceberg", "--format", "json")
    tables = [f"bi_lab.{item['label']}" for item in json.loads(objects.stdout)["objects"]]
    batch = tarel("lineage", "batch", *tables, "--format", "json")
    size = len(batch.stdout.encode("utf-8"))
    passed = batch.code == 0 and size <= 4000
    checks.append(Check(f"batch of {len(tables)} tables", passed, f"{size} B", "<= 4000 B"))

    base = ("graph", "slice", "lakehouse-iceberg", *_GOLD_SLICE, "--format", "json")
    full_slice, compact_slice = tarel(*base), tarel(*base, "--view", "compact")
    share = len(compact_slice.stdout) / max(len(full_slice.stdout), 1)
    checks.append(Check(
        "5-object slice compact share", share <= 0.25,
        f"{share:.1%} ({len(compact_slice.stdout)} B)", "<= 25%",
    ))

    index = tarel("workspace", "show", "gesamtsystem", "--depth", "index", "--format", "json")
    size = len(index.stdout.encode("utf-8"))
    passed = index.code == 0 and size <= 8192
    checks.append(Check("workspace index", passed, f"{size} B", "<= 8 KB"))

    search = tarel(
        "search", "--workspace", "gesamtsystem", "revenue by customer nation margin",
        "--diversity", "per_graph", "--collapse-duplicates", "--format", "json",
    )
    hits = json.loads(search.stdout)["hits"] if search.code == 0 else []
    chinook = sum("chinook" in hit["label"] for hit in hits)
    marts = sum(hit["label"].startswith(("lakehouse-", "duckdb-wwi-dbt")) for hit in hits)
    checks.append(Check(
        "search chinook variants in top 20", chinook <= 1 and marts > 0,
        f"{chinook} chinook, {marts} mart hits", "<= 1 chinook",
    ))
    return checks


def _size_check(
    name: str, tarel: Callable[..., Run], arguments: tuple[str, ...], *, limit: int,
) -> Check:
    full = tarel(*arguments)
    compact = tarel(*arguments, "--view", "compact")
    if full.code or compact.code:
        return Check(name, False, f"exit {full.code}/{compact.code}", f"<= {limit} B")
    size = len(compact.stdout.encode("utf-8"))
    full_size = len(full.stdout.encode("utf-8"))
    return Check(name, size <= limit, f"{size} B (full {full_size} B)", f"<= {limit} B")


def _focus_checks(tarel: Callable[..., Run]) -> list[Check]:
    run = tarel(*_WWI_FOCUS, "--view", "compact")
    if run.code:
        return [Check("wwi focus compact", False, f"exit {run.code}", "exit 0")]
    payload = json.loads(run.stdout)
    edges = payload["edges"]
    nodes = payload["nodes"]
    triples = Counter((item["from"], item["to"], item["rel"]) for item in edges)
    members = {member: index for index, cycle in enumerate(payload.get("cycles", ()))
               for member in cycle["members"]}
    inside = sum(
        1 for item in edges
        if item["from"] in members and members[item["from"]] == members.get(item["to"])
    )
    unknown = sum(item["from"] not in nodes or item["to"] not in nodes for item in edges)
    return [
        Check("wwi focus self-loops", not any(a == b for a, b, _ in triples),
              str(sum(a == b for a, b, _ in triples)), "0"),
        Check("wwi focus duplicate edges", max(triples.values(), default=1) == 1,
              str(sum(count - 1 for count in triples.values())), "0"),
        Check("wwi focus edges inside cycles", inside == 0, str(inside), "0"),
        Check("wwi focus edges readable", unknown == 0, f"{unknown} unknown keys", "0"),
    ]


def _error_check(tarel: Callable[..., Run]) -> Check:
    name = "misplaced --graph repaired in 1 retry"
    failed = tarel(*_MISPLACED_GRAPH)
    try:
        error = json.loads(failed.stderr)["error"]
    except (json.JSONDecodeError, KeyError):
        return Check(name, False, "stderr is not an error object", "structured error")
    if failed.code != 2 or failed.stdout or error.get("code") != "invalid_graph_role":
        return Check(name, False, f"exit {failed.code}, {error.get('code')}", "exit 2")
    suggestion = error.get("details", {}).get("suggestion", {})
    retry = [*_MISPLACED_GRAPH[:3]]
    for lineage in suggestion.get("lineages", ()):
        retry += ["--lineage", lineage]
    for graph in suggestion.get("graphs", ()):
        retry += ["--graph", graph]
    repaired = tarel(*retry, "--format", "json", "--view", "compact")
    retryable = error.get("retryable") is True
    return Check(
        name,
        retryable and repaired.code == 0,
        f"retryable={retryable}, retry exit {repaired.code}",
        "retry exit 0",
    )


def _tarel(root: Path, arguments: tuple[str, ...]) -> Run:
    result = subprocess.run(
        [sys.executable, "-m", "tarel", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return Run(result.returncode, result.stdout.rstrip("\n"), result.stderr.strip())


if __name__ == "__main__":
    raise SystemExit(main())
