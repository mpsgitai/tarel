"""Record the real Structure/Lineage UI with synthetic metadata on a CI runner."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import URLError
from urllib.request import urlopen

from tarel.connectors.contracts import CatalogField, CatalogObject, CatalogResult
from tarel.graph.build import build_graph_from_catalog
from tarel.graph.store import FileGraphStore
from tarel.lineage.manual import add_manual_hop, add_manual_job, create_manual_lineage
from tarel.lineage.store import FileLineageStore

GRAPH = "synthetic-sales"
LINEAGE = "synthetic-sales-flow"


def prepare_demo(root: Path) -> None:
    """Use public graph/lineage contracts; never connect to a real database."""
    objects = (
        ("source", "Orders"), ("source", "Products"), ("source", "Customers"),
        ("stage", "Sales"), ("mart", "FactSales"), ("mart", "DimCustomer"),
    )
    graph = build_graph_from_catalog(
        GRAPH,
        CatalogResult(
            connector="synthetic-demo", source_type="database", catalog="DemoDW",
            dialect="tsql",
            objects=tuple(
                CatalogObject(
                    namespace=schema, name=name, kind="table",
                    fields=(CatalogField("Id", 1, "integer", False),),
                )
                for schema, name in objects
            ),
        ),
    )
    FileGraphStore(root / ".tarel/graphs").save(graph)
    lineage = create_manual_lineage(LINEAGE)
    jobs = (
        ("ExtractSales", (("source.Orders", "stage.Sales"),
                          ("source.Products", "stage.Sales"))),
        ("LoadSales", (("stage.Sales", "mart.FactSales"),)),
        ("LoadCustomers", (("source.Customers", "mart.DimCustomer"),)),
    )
    for name, pairs in jobs:
        lineage, job = add_manual_job(
            lineage, kind="procedure", name=name, qualified_name=f"etl.{name}",
            language="sql", source_reference="synthetic-readme-demo",
            description="Synthetic example for demonstrating graph navigation.",
        )
        for source, target in pairs:
            lineage, _ = add_manual_hop(
                lineage, job_reference=job.id, source=f"DemoDW.{source}",
                target=f"DemoDW.{target}", operation="insert", role="business_data",
                evidence_reference="synthetic-readme-demo",
                reason="Illustrative relationship; not extracted from a production system.",
            )
    FileLineageStore(root / ".tarel/lineage").save(lineage)


def wait_for_ui(process: subprocess.Popen, url: str) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("TAREL UI exited before becoming ready; inspect ui.log.")
        try:
            with urlopen(f"{url}api/bootstrap", timeout=2) as response:
                data = json.load(response)
            if data.get("objects") and data.get("lineages"):
                return
        except (URLError, TimeoutError):
            pass
        time.sleep(0.2)
    raise RuntimeError("TAREL UI did not become ready within 30 seconds.")


def record(url: str, output: Path) -> tuple[Path, float, float]:
    # Optional tooling belongs to this recording script, not TAREL's runtime.
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            record_video_dir=str(output / "raw"),
            record_video_size={"width": 1440, "height": 900},
            reduced_motion="no-preference",
        )
        page = context.new_page()
        video_start = time.monotonic()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(url, wait_until="networkidle")
            expect(page.locator("#footer-status")).to_have_text("Ready")
            expect(page.locator("#graph-canvas canvas").first).to_be_visible()
            # Close the inspector with the real UI control to give the graph room.
            page.locator("#open-inspector").click()
            page.wait_for_timeout(600)
            page.locator("#show-all").click()
            page.wait_for_timeout(300)
            start = max(0, time.monotonic() - video_start)
            page.screenshot(path=str(output / "structure.png"))
            page.wait_for_timeout(2000)
            lineage = page.locator('[data-canvas-mode="lineage"]')
            expect(lineage).to_be_enabled()
            lineage.click()
            expect(lineage).to_have_class("chip is-active")
            # Dwell times are intentional for recording; the app's animation is unchanged.
            page.wait_for_timeout(3000)
            page.screenshot(path=str(output / "lineage.png"))
            structure = page.locator('[data-canvas-mode="space"]')
            structure.click()
            expect(structure).to_have_class("chip is-active")
            page.wait_for_timeout(1500)
            duration = time.monotonic() - video_start - start
            if errors:
                raise RuntimeError("Browser errors: " + "; ".join(errors))
        finally:
            context.close()
            browser.close()
        return Path(page.video.path()), start, duration


def convert(video: Path, start: float, duration: float, output: Path) -> None:
    target = output / "space-to-lineage.gif"
    filters = (
        "fps=20,scale=1120:-1:flags=lanczos,split[a][b];"
        "[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video), "-ss", str(start), "-t", str(duration),
         "-filter_complex", filters, "-loop", "0", str(target)],
        check=True, stdout=subprocess.DEVNULL,
    )
    if target.stat().st_size > 10 * 1024 * 1024:
        raise RuntimeError("GIF exceeds the 10 MiB review budget; tune before publishing.")
    (output / "README.md").write_text(
        "# TAREL Structure to Lineage recording\n\n"
        "Real GUI, synthetic metadata, original animation speed.\n\n"
        "Review space-to-lineage.gif and the two PNGs before adding the GIF to docs/assets.\n"
        "The source video is in raw/. No warehouse credentials or business data are used.\n",
        encoding="utf-8",
    )
    print(f"Created {target.name}: {target.stat().st_size:,} bytes")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="tarel-readme-demo-") as temporary:
        root = Path(temporary)
        prepare_demo(root)
        if args.prepare_only:
            print("Synthetic graph and lineage validated successfully.")
            return
        url = "http://127.0.0.1:8765/"
        with (output / "ui.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, "-u", "-m", "tarel", "ui", GRAPH, "--lineage", LINEAGE,
                 "--port", "8765", "--no-open"],
                cwd=root, stdout=log, stderr=subprocess.STDOUT,
            )
            try:
                wait_for_ui(process, url)
                video, start, duration = record(url, output)
                convert(video, start, duration, output)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
