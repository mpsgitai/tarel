"""End-to-end smoke test of the CLI and SDK against the built-in retail demo.

Runs every step in a fresh temporary directory and prints a normalized transcript (temporary
paths replaced by ``<tmp>``). Diff two transcripts to prove that a refactor kept the visible
behavior of both entry points::

    python tools/smoke_demo.py > before.txt
    # ... refactor ...
    python tools/smoke_demo.py > after.txt && diff before.txt after.txt

Exit status is non-zero when any CLI command or SDK call fails.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path

from tarel.cli import main
from tarel.sdk import Tarel

CLI_STEPS: tuple[tuple[str, ...], ...] = (
    ("version",),
    ("demo", "create", "retail-dwh"),
    (
        "source", "configure", "retail-local", "--connector", "sqlite",
        "--config-ref", "state:demos/retail-dwh.toml", "--namespace", "main",
        "--allow-aggregates", "--allow-small-domains", "--allow-raw-samples",
    ),
    ("source", "list"),
    ("source", "check", "retail-local"),
    ("source", "probe", "retail-local"),
    ("source", "build", "retail-local", "retail-demo"),
    ("source", "enrich", "retail-local", "retail-demo", "--format", "json"),
    ("connector", "check", "sqlite"),
    ("connector", "sample", "sqlite", "--config", ".tarel/demos/retail-dwh.toml",
     "--schema", "main", "--object", "F_SLS_01", "--limit", "3"),
    ("connector", "profile", "sqlite", "--config", ".tarel/demos/retail-dwh.toml",
     "--schema", "main", "--object", "D_CHNL", "--row-limit", "10000"),
    ("graph", "list"),
    ("graph", "show", "retail-demo"),
    ("graph", "header", "retail-demo"),
    ("search", "retail-demo", "sales channel", "--limit", "3"),
    ("search", "retail-demo", "customer", "--format", "json", "--limit", "2"),
    ("context", "retail-demo", "revenue by channel"),
    ("context", "retail-demo", "revenue by channel", "--format", "json"),
    ("grounding", "retail-demo", "revenue by channel"),
    ("annotation", "plan", "retail-demo", "--limit", "2", "--format", "json"),
    ("annotation", "list", "retail-demo"),
    ("relationship", "list", "retail-demo"),
    ("relationship", "discover", "retail-demo", "--object", "main.F_SLS_01",
     "--config", ".tarel/demos/retail-dwh.toml", "--dry-run", "--format", "json"),
    ("workspace", "create", "shop"),
    ("workspace", "system", "define", "shop", "retail", "--graph", "retail-demo"),
    ("workspace", "show", "shop"),
    ("workspace", "scope", "shop", "--system", "retail"),
    ("focus", "list"),
    ("knowledge", "list"),
    ("provider", "list"),
    ("lineage", "-h"),
    ("discovery", "-h"),
    ("family", "-h"),
    ("graph", "show", "missing-graph"),
)


def run_cli(args: tuple[str, ...]) -> tuple[int, str]:
    """Run one CLI invocation in-process and capture stdout and stderr."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            code = main(list(args))
        except SystemExit as exc:  # argparse exits for -h and usage errors
            code = exc.code if isinstance(exc.code, int) else 1
    return code, out.getvalue()


def run_sdk(root: Path) -> list[str]:
    """Exercise the main SDK facades against the graph built by the CLI steps."""
    tarel = Tarel(root)
    header = tarel.graph.header("retail-demo")
    page = tarel.graph.objects("retail-demo", limit=3, expected_revision=header.revision)
    results = tarel.search.graph("retail-demo", "sales channel", limit=3)
    packet = tarel.context.graph("retail-demo", "revenue by channel")
    parts = tarel.context.split(packet)
    workspace = tarel.workspace.load("shop")
    return [
        f"graphs={tarel.graph.list()}",
        f"revision={header.revision}",
        f"objects={[item['id'] for item in page.to_dict()['objects']]}",
        f"search={[hit.id for hit in results.hits]}",
        f"packet={packet.packet_hash} stable={parts.stable_hash}",
        f"workspace={workspace.name} systems={[system.name for system in workspace.systems]}",
        f"sources={tarel.source.list()}",
        f"focuses={tarel.focus.list()}",
    ]


def main_() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        previous = Path.cwd()
        os.chdir(tmp)
        try:
            for step in CLI_STEPS:
                code, output = run_cli(step)
                expected_failure = step[-1] == "missing-graph"
                if (code != 0) != expected_failure:
                    failures += 1
                print(f"$ tarel {' '.join(step)}  -> {code}")
                print(output.replace(tmp, "<tmp>").replace(str(Path(tmp).resolve()), "<tmp>"))
            print("# SDK")
            try:
                for line in run_sdk(Path(tmp) / ".tarel"):
                    print(line)
            except Exception as exc:  # report, then fail the run
                failures += 1
                print(f"SDK failure: {type(exc).__name__}: {exc}")
        finally:
            os.chdir(previous)
    print(f"# failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main_())
