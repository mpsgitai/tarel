# TAREL

**Help your agents understand your data estate.**

```bash
pip install tarel
# or
uv tool install tarel
```

[![PyPI](https://img.shields.io/pypi/v/tarel)](https://pypi.org/project/tarel/)
[![Python](https://img.shields.io/pypi/pyversions/tarel)](https://pypi.org/project/tarel/)
[![CI](https://github.com/mpsgitai/tarel/actions/workflows/ci.yml/badge.svg)](https://github.com/mpsgitai/tarel/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A coding agent can read a stored procedure. Understanding an entire warehouse takes a map.

The **TAREL Graph** is a simple data structure designed for navigating huge information systems.
It connects technical objects, business meaning, and data dependencies into reusable knowledge
for engineers and agents.

Create, annotate, and refresh graphs through the CLI or Python SDK.

## Let agents build knowledge you can review

**Self-annotation** lets models and agents propose descriptions and relationships from available
evidence. You review and refine them. The graph preserves provenance and separates proposals from
accepted knowledge.

The browser keeps exploration and review prominent, with optional metadata available on demand.
See [Focused browser workflows](docs/browser-workflows.md) for scope, review, and layout behavior.

![TAREL field annotation inspector with semantic descriptions, evidence, and review state](https://raw.githubusercontent.com/mpsgitai/tarel/master/docs/assets/tarel-field-annotation-inspector.png)

*Inspect field meanings and supporting evidence, then review, edit, approve, defer, or reject proposals.*

## Explore through Space and Lineage

**Space** shows what exists and what it means: tables, fields, relationships, and annotations.

**Lineage** traces reports and measures through transformations to their sources, with evidence
behind each connection.

![TAREL Space view of an annotated TPC-DS information system](https://raw.githubusercontent.com/mpsgitai/tarel/master/docs/assets/semantic-space.png)

*Navigate an annotated TPC-DS information space in the local browser.*

## Give agents the relevant slice

TAREL retrieves focused graph context for each task, with uncertainty visible and credentials and
raw sample rows excluded.

Runs locally. No mandatory third-party runtime dependencies.

## Follow a report back to its sources

Start with what the business knows: a report, visual, or measure. Trace its dependencies through
semantic models, ETL steps, and stored procedures to source tables and fields.

Each connection retains its evidence and review state. Workflow order and actual data flow remain
distinct, so a scheduled dependency never silently becomes table lineage.

![TAREL lineage trace from a Power BI report measure to DWH source tables](https://raw.githubusercontent.com/mpsgitai/tarel/master/docs/assets/report-lineage.png)

*A Power BI measure traced through a semantic column, physical mart, dbt models, and an extract to
five DWH origin tables. Draft state and changes in lineage granularity remain visible.*

## Retrieve what matters

Search the graph by technical name or business meaning using built-in BM25 or optional local
embeddings. Expand along relevant relationships within explicit context budgets.

Your agent receives a focused slice with source identity, SQL dialect, evidence, and visible gaps.
The same graph supports many questions without sending the entire estate into every conversation.

## Extend TAREL to fit your systems

Every data selection, documentation source, and ETL orchestration can contribute knowledge to
the graph.

**Self-modification through reviewed extensions:** When an interface is missing, a coding agent can
implement a connector or importer against TAREL's contracts. You review, test, and activate it.

This lets the graph grow into your actual environment—including custom scripts, legacy systems,
and internal frameworks.

## Get started and go deeper

Try the synthetic [Retail DWH walkthrough](docs/retail-demo.md) without credentials.

- [Python SDK](docs/sdk.md)
- [Graph storage](docs/graph-storage.md) and [architecture](docs/architecture.md)
- [Local retrieval](docs/local-retrieval.md) and [context contract](docs/context-contract.md)
- [Discovery runs](docs/discovery-runs.md) and [runtime lineage](docs/runtime-lineage.md)
- [All documentation](docs/)

TAREL is pre-alpha. SQLite and SQL Server connectors are included. TAREL does not execute
analytical answer queries; your harness does.

[Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [MIT License](LICENSE)
