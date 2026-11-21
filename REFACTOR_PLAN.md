# TAREL refactor plan

Goal: the same product — CLI and SDK behave identically — in a code base that a new contributor can
read top to bottom. Modern, typed, dependency-free Python; small modules with one job each; English
docstrings that explain *why*, not *what*.

Baseline: `mpsgitai/tarel@1d2d00e` (v0.0.3).

## Where we start

| Metric | Baseline |
| --- | --- |
| Python in `src/` | 64.4k lines in 196 modules (10.6k of them browser UI) |
| Tests | 30.5k lines, 852 passing, ~10 s with `pytest -n 8` |
| Runtime dependencies | none (optional extras for drivers, YAML, SQLGlot, embeddings) |

The domain packages (`graph/`, `lineage/`, `discovery/`, ...) are already reasonably shaped. The
problems concentrate in a handful of god modules and in the entry adapters:

| File | Lines | Problem |
| --- | ---: | --- |
| `cli.py` | 3561 | One 1050-line `build_parser` and one 1330-line `main` if-chain for 15 command groups, plus ~40 renderers. Fourteen more `*/cli.py` modules are dispatched through a hand-written chain of `x = dispatch_x(args); if x is not None: return x`. |
| `application.py` | 3041 | 110 use cases for 12 unrelated domains (connectors, providers, graph, workspaces, search, context, retrieval, relationships, knowledge, annotations, focus, demo) in one namespace. |
| `sdk/client.py` | 2888 | 25 facade classes in one file. |
| `discovery/contracts.py` | 1956 | Run, program, manifest and decision contracts in one file. |
| `discovery/application.py` | 1616 | Run lifecycle, advice, promotion and coverage use cases in one file. |
| `lineage/runtime.py`, `retrieval/index.py`, `lineage/application.py`, `entity_resolution/contracts.py` | 1000–1400 | Several responsibilities each. |
| `context.py`, `context_*.py`, `grounding*.py` | 9 flat modules | One concept spread over the top-level namespace. |
| 27 `*Failure` classes | — | Identical bodies (`code` + message), no common base, so every entry point lists all 27 in an `except`. |

## Principles

1. **Behavior is frozen.** Every step keeps the full test suite, `ruff`, the CLI reference check and
   the demo smoke test green. Commands, flags, JSON output and SDK method names do not change.
2. **Move first, improve second.** A split is a pure move (diff = deleted lines reappear elsewhere);
   cleanup happens in a separate commit so reviews stay trivial.
3. **One module, one job, ~500 lines soft limit.** A file name tells you what is inside.
4. **Dependencies point inward.** `cli/` and `sdk/` are entry adapters; domain packages never import
   them and contain no `print` or `argparse`.
5. **No compatibility shims inside the repo.** Pre-alpha: internal import paths change and the tests
   follow. Public surface (`tarel.cli:main`, `tarel.sdk.Tarel`, documented contracts) stays.
6. **Stay dependency-free.** See "Pydantic" below.

## Target layout

```
src/tarel/
  errors.py              TarelError — common base for every *Failure
  runtime.py             TarelRuntime + store resolution for "no runtime" callers
  cli/
    __init__.py          main(): parse, dispatch through COMMANDS, single error handler
    _args.py             shared argument groups (--format, scope flags, filters)
    _output.py           shared text/JSON rendering helpers
    demo.py workspace.py source.py connector.py knowledge.py provider.py model.py index.py
    graph.py search.py context.py grounding.py annotation.py relationship.py focus.py ui.py
    lineage.py discovery.py ... (former */cli.py, moved here)
  sdk/
    __init__.py          public re-exports (unchanged)
    client.py            Tarel and the _RuntimeAPI base only
    graph.py lineage.py context.py search.py workspace.py annotation.py ...  one facade each
  <domain>/application.py  use cases for that domain (split out of application.py)
  context/               compile, packets, guidance, hints, caching, output, grounding
  ...                    existing domain packages, oversized modules split by responsibility
```

Each CLI module has the same two-function shape, so `cli/__init__.py` becomes a table:

```python
def register(subcommands: Subcommands) -> None: ...   # argparse wiring
def dispatch(args: argparse.Namespace) -> int | None:  # None = not my command
```

## Phases

| # | Phase | Scope | Status |
| --- | --- | --- | --- |
| 0 | Baseline | Import upstream, Python 3.12 venv, tests/ruff/docs checks green, demo smoke script | done |
| 1 | Foundations | `tarel.errors.TarelError`; all failures subclass it; store resolution helpers move to `runtime.py` | done |
| 2 | CLI package | `cli.py` → `cli/` (one module per command group); domain `*/cli.py` move into `cli/`; dispatch table; single `except TarelError` | done |
| 3 | Use cases | `application.py` → `<domain>/application.py` (connectors, providers, graph, focus, workspaces, retrieval/search, context, relationships, knowledge, annotations) | done |
| 4 | SDK | `sdk/client.py` → one facade per module | done |
| 5 | Context package | `context*.py`, `grounding*.py` → `tarel/context/` | done |
| 6 | Large domain modules | `discovery/contracts.py`, `discovery/application.py`, `lineage/runtime.py`, `retrieval/index.py`, `lineage/application.py`, `entity_resolution/contracts.py` | done |
| 7 | Polish | Module docstrings, `CONTRIBUTING.md` architecture map, stricter ruff rules (`RUF`, `PERF`, `PTH`, `C4`), pytest as the documented runner | done: code map, smoke test, ruff C4/RUF/PTH, handler tables, `print_json`, `write_atomic` |
| — | Later | Browser UI (`ui/server.py`, `ui/presentation.py`), deliberately out of scope for now | |

Every phase ends with: `ruff check`, full test suite on Python 3.12, `tools/generate_cli_reference.py
--check`, `tools/check_docs.py`, and `tools/smoke_demo.sh` (CLI + SDK against the built-in retail demo).

## Pydantic

Not introduced. The contracts are frozen `dataclass(slots=True)` types with explicit `from_dict` /
`to_dict` and domain-specific validation errors (`code` + message) that the CLI, SDK and tests rely
on. Pydantic would replace those error codes with its own, add a compiled dependency to a project
that advertises "no mandatory runtime dependencies", and only pay off after rewriting ~150 contract
types. Revisit only if the contracts are redesigned as a public schema.

## Branching and history

All work happens in this private repository. The public `mpsgitai/tarel` repository is not touched.

The upstream `.github/workflows/` files are not part of this repository: the automation that
pushes here may not write workflow files. Copy them from upstream when CI is wanted; the commands
they run are the same checks listed under "Phases".

## Progress

| Metric | Baseline | Now |
| --- | ---: | ---: |
| Largest non-UI module | 3561 (`cli.py`) | 993 (`connectors/sqlserver/connector.py`) |
| Non-UI modules over 1000 lines | 9 | 0 |
| Non-UI Python modules | 188 | 252 |
| `except` clauses listing every failure type | 1 with 27 classes | 0 (`except TarelError`) |
| Duplicated `_x_store(runtime)` helpers | 22 in 6 modules | 0 |
| Hand-written temp-file/rename sequences | 29 | 7 (binary, SQLite, archive) + `atomic.write_atomic` |
| `print(json.dumps(...))` in the CLI | 70 | 0 (`print_json`) |
| Tests (Python 3.12; 3.11 not rerun) | 852 passing | 980 passing including the real-model, browser and estate tests; 976 and 4 reasoned skips without their optional state and Chromium libraries |
| CLI/SDK smoke transcript | baseline | identical |

How the moves were made: each split is generated from the AST (symbols are moved verbatim, imports
are pruned by `ruff`, importers and `mock.patch` targets are rewritten), then verified with the
full suite, the CLI reference check, the docs check and the smoke transcript. Every commit on this
branch is one such step and can be reviewed on its own.

## Decisions taken along the way

- **Per-contract JSON readers stay.** About 250 small readers (`_text`, `_fields`, ...) exist
  across 24 modules, but only 38 are byte-identical apart from the failure class and code. The rest
  differ in limits, whitespace handling and messages, which are user-visible error output.
  Unifying them would change behavior for little gain.
- **Remaining 800-1000 line modules stay whole.** `lineage/contracts.py`, `topology/contracts.py`,
  `lineage/refresh.py`, `context/compiler.py` and `discovery/runs.py` are records plus the
  validation that their `from_dict` calls; splitting them would only create import cycles.
- **No PERF rules.** PERF401 flags `append` loops that read better than the suggested comprehension.
- **No mass docstrings.** Modules and SDK facades are documented; one-line docstrings that restate
  a function name would be noise.

## Round three

- **CLI:** domain command groups (discovery, entity, reference-mapping, semantic, topology) and the
  nested `workspace <group> <action>` commands dispatch through handler tables.
- **Browser backend:** `ui/server.py` is split into `contracts.py`, `_parse.py`, `backend.py` and the
  HTTP adapter; `mutate()` routes through `_POST_ROUTES` and `_EDIT_ROUTES` (writes stay behind
  the edit-mode check). `ui/presentation.py` became the `ui/payloads/` package. `UIFailure` is a
  `TarelError` with an HTTP status. `TarelUIBackend` (about 1150 lines) stays one class: its
  methods share the session scope, and mixins would only hide that coupling.
- **Types:** mypy runs in CI mode over all of `src/tarel`. `cli/`, `sdk/`, `runtime.py`,
  `errors.py` and `atomic.py`: 225 of 275 modules pass; 50 modules are listed as type debt in
  `pyproject.toml` (most of their errors are JSON payloads typed as `dict[str, object]`).

## Round four

- **Type debt:** 303 → 52 mypy errors; the debt list shrank from 50 to 25 modules. All of `ui/`
  now passes. Most fixes made code clearer, not just quieter: loop variables named after the
  record they iterate instead of one `item` for seven types, read-only protocol properties, a
  `_StepShape` NamedTuple, a `TypeGuard`, explicit invariants where `None` cannot occur.
- **Typed payloads:** retrieval status, model catalog and provider test results are `TypedDict`s
  (`IndexStatus`, `WorkspaceIndexStatus`, `WorkspaceIndexBuild`, `ModelCatalog`,
  `ProviderTestResult`, ...). They stay plain dicts at runtime, so JSON output and SDK results
  are unchanged; `index`, `model` and `retrieval` commands were compared byte for byte and by exit
  code against the upstream implementation.
- Remaining `dict[str, object]` return types are `to_dict()` serializers, where that type is right.

## Round five: review findings

A hands-on review against the demo (new graph, annotated by Claude as harness, every command
group and SDK facade exercised) produced 14 findings; 11 are fixed, 2 partly, 1 deliberately not:

- Lineage resolves unqualified script tables to the single graph object of that name.
- The browser checks the Host header (DNS rebinding) and requires the session token on reads.
- `index status` reports a missing model as a state; all commands share `--format` and
  `--workspace NAME`; graph reads accept labels; empty concept/topology states exit 0.
- `runtime.resolve_runtime` replaces 14 store helpers and their inline copies; no private names
  are imported across modules.
- Seven core functions are split into named steps (lineage refresh and validation, graph
  refresh, discovery validation and promotion, entity-resolution validation).
- Not done: option records for CLI/SDK/use-case parameters, because the SDK keyword arguments
  are the public API.

## Round six: audit findings

Two audits (a CLI audit and a retrieval user test, kept locally) tested
the refactor after the code map round. Their real-runtime findings are fixed or bounded here. Both defects below are inherited
from upstream, not refactor regressions.

| Finding | Status |
| --- | --- |
| Qwen texts silently cut at 256 tokens | Fixed: whole text up to 2048 tokens. Beyond that, documents are cut and named, questions refused. Proven with the pinned GGUF on llama-cpp-python 0.3.35 and 0.3.36 |
| Reuse of vectors from the old settings | Decided in the walkthrough: see below |
| One ambiguous name blocks every global trace | Fixed: ambiguity stops only traces that depend on it |
| `context expand --requests` promised inline JSON | Fixed: help and error say file or stdin, as documented |
| `--workspace NAME` differs from upstream | Deliberate, documented in the README; not reverted |
| Read commands write rebuildable caches | Documented; no change |

**Walked through with the maintainer.** `tarel.retrieval.v0.4` adds `embedding_input`,
`unverified_documents`, `truncated_documents` and `embedding_runtime` to the index metadata, and the checkpoint identity gained `embedding_input`.
Without some persisted marker a vector cut at token 256 looks the same as a whole one, so this is the
smallest change that keeps old vectors from counting as verified. Decisions:

1. **Decided: v0.4 as drafted.** A rewritten index cannot be read by upstream, which
   rejects the unknown metadata keys. Accepted because the refactor uses its own states and the
   version number shows the changed meaning.
2. **Decided: keep them selectively.** Reused vectors are whole but not reproducible: all upstream revisions used `n_batch=256`, so
   texts within 256 tokens were not cut. Token capacity does not change a vector within one
   runtime, but decode batching and the library version do. The `lab-chinook` index is reproduced
   only by 0.3.35 with 16 documents per decode, and differs from a single decode on 0.3.36 (cosine
   0.996 to 0.999). Such vectors stay counted as unverified; the library version is not recorded.
   On that graph an update matched a full re-embedding on 8 of 8 top hits and 9 to 10 of the top 10
   (eight questions, agreement only, no relevance judgement).
3. **Decided: shorten documents visibly.** A document over 2048 tokens embeds its
   beginning and is named in `truncated_documents`; questions are still refused. Refusal would stop
   vector search for the whole graph, and annotated objects use up to 54 tokens per field, so about
   40 annotated fields can reach the limit. Each field keeps its own whole vector. Raising the
   capacity costs too much: 8192 tokens took 6.6 GB and 103 s for one text.
4. **Decided: `ready` stays, packets warn.** `unverified` and shortened documents do not
   change `ready`, since the index works. Their warnings reach context packets in
   `dynamic.retrieval.warnings` and the brief, leaving `stable` and its hash untouched.
5. **Decided: record the library version for information only.** Versions 0.3.35 and
   0.3.36 give slightly different vectors, but a patch release must not redo every index.
6. **Decided: keep the lineage resolution order.** A document naming no catalog keeps
   bare-name matches and the trace warns; such an edge can still be wrong.

The lineage resolution order (own definition, enclosing catalog, catalogs the document names) changes
nothing persisted. Without it, fixing the
global traces would have replaced an error with false lineage: the only `sales` table across 103
graphs became the origin of a Power BI measure from an unrelated system.

Not fixed, by decision: BM25 and vector ranking quality has no relevance oracle, so nothing here
asserts an order; there is no converter for the benchmark `trb.vector-index.v1` format; missing
diagnosis, billing and index-membership metadata and unconfirmed joins are source gaps, which stay
visible rather than being invented.

## Round seven: lineage as data flow

The Lineage canvas now draws tables connected to tables, with the processes on the edges. Details
load on click. CLI and SDK output is unchanged; the three audited focus traces stay byte-identical
to the code before this work.

Reference resolution moved to `lineage/resolution.py`, so the browser and `lineage upstream` agree.
That fixed the browser showing a script's `F_SLS_01` as an external asset next to the real table.

Two brief assumptions did not hold, and the design follows the code instead:

- `LineageDefinition` has no `content`; documents store only a hash, by design. The panel rereads
  the source and shows it only while the hash matches, otherwise it says why it cannot.
- Reports are `query` definitions that read and never write. Under "no phantom edges" they draw no
  edge and appear in `reads_only`; **Processes as nodes** still shows them. A selected focus filters
  the flow to its members, so a report-only focus can look empty in the default view.

Reads a process's write statement does not name still draw an edge, as requested, but dotted and
marked `indirect`, because traversal does not treat them as upstream.

Measured with `tools/measure_lineage_ui.py` (synthetic, headless Chromium):

| Flows | In bootstrap | Bootstrap | First render | Edge click first / median | Reload |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 48 | 48 | 31 ms | 366 ms | 25 / 15 ms | 52 ms |
| 498 | 498 | 48 ms | 730 ms | 119 / 78 ms | 156 ms |
| 4998 | 1500 | 1036 ms | 2540 ms | 556 / 168 ms | 1039 ms |

The targets of 150 ms per click and 500 ms per reload hold at 500 flows. At 5000 they do not. Adding
flows rebuilds the canvas from saved positions rather than extending it in place.

## Round eight: GUI review findings

An independent browser review of the round-seven state found three defects in the data-flow view. The review
and its evidence stay outside this repository.

1. **Unrelated temporary tables were joined (P1).** An unresolved name got one identity from its
   spelling and entered the shared index, so `#tmp` in two documents became one node and tracing
   reached a foreign source. Assets now carry a scope (see `docs/architecture-ui.md`), and only
   qualified names enter the index. Bare names are scoped to their document as well, which is a
   decision: a spelling is no evidence across documents. All 255 flows of the reviewed estate keep
   their endpoints.
2. **The resolver's warning was dropped (P2).** The flow view kept the node and lost the note. The
   resolver now also returns its `basis` as a value, and each contribution carries its own
   `resolutions` to the panel.
3. **A successful reject ended in an error panel (P2).** The client reopened an edge the rejection
   had removed, and the inspector decorator added the selected object's summary to whatever panel
   appeared. The decision answer now reports `edge_exists`, and the decorator reads its object from
   the heading.

4. **The same false path existed in upstream traces (P1).** `lineage upstream`, the SDK, focuses and
   the browser's object trace use `lineage/traversal.py`, which gave an unresolved name one identity
   (`external:#tmp`). The scope rules moved from the flow view into `lineage/resolution.py`, and both
   now apply them; the flow payload stayed byte-identical on all reviewed estates. This changes CLI
   and SDK output on purpose: scoped names get new ids and a scope in `name`, a name in several scopes
   can no longer start a trace, and a bare name no longer chains documents. Across 348 trace starts on
   the four reviewed estates no reachable node changed, because none shared such a name between
   documents; 162 traces differ only in the new ids and names. `tools/smoke_demo.py` does not run a
   trace and is unchanged.

**Open:** a saved focus is not marked stale by this change, so one built earlier can keep a false
upstream until it is rebuilt. `dbo.#tmp` and `#tmp` in one session remain two references in both
views, because a name is still compared with its qualifier.

## Metadata sync (first version)

Contract points agreed with the maintainer: an envelope around unchanged `.tarel` packages; an
`ssh-keygen -Y` adapter for signatures; central annotations win the annotation slot while published
ones stay word for word in metadata and are at most `draft`; graphs travel, optional knowledge was
agreed but is not implemented, lineage, focus and topology do not yet; activation commits through `head.json`; workspace documents
stay untouched and dangling references are reported in `sync/impacts.json`.

| Stage | State |
| --- | --- |
| Minimal file path: one site, one central state, first takeover, repetition, update | Done |
| Guards: scope changes, deletion versus withdrawal, dangling workspace references, recorded observations | Done |
| Security: signatures, trust scope, tighter limits | Done |
| Four instances, inbox transport, real process faults | Done, local machine only |
| Documentation and acceptance | Done, see [the guide](docs/sync.md) |

Known limits so far: power loss was not tested, only killed processes; other workspace commands take no
sync lock; no real cloud, gateway or SMB/NFS share was used; a table-level claim is flagged only for
object-level changes, as in `graph refresh`; old revisions and change reports keep withdrawn names
until pruned, or for good in the case of reports; a graph's read record only says the connector
returned without error; a file can be replayed until its sequence is passed, which history makes a
no-op or a refusal; TAREL does not encrypt, and a profile cannot vouch for free text.

Found by the sync system test: the receiver accepted a validly signed package carrying
`technical_description` while its scope released none, and the same review found namespace nodes
and fields outside the scope. Sender and receiver now apply one rule for keys and for nodes. This
proves a package consistent with itself, not truthful: node IDs must match their names, but a trusted
sender that renames an object everywhere still passes, and a test pins that limit.

The review later that day added five findings, all closed: a signed snapshot could empty a declared
namespace, an unsigned file with a list as `completeness` stopped every inbox pass, a payload could sit
in the value of an allowed key, a namespace could contradict its own catalog, and sender-chosen key
names reached `last_failure`. `sync status` went from one load per stream per graph (9,702 on the
99-stream test state) to one per referenced graph (2 there), with identical results.

Implementation note: retired claims and removals live in `sync/streams/<id>/revisions/<id>/impacts.json`
rather than one `sync/impacts.json`, so they move together with `head.json` and streams do not share
a file. Published graphs mark themselves with `sync_origin` on their catalog node; workspace reads
tolerate a missing target only for those.

## Next steps

1. The 15 modules left on the mypy debt list are mostly `X | None` values used after an implicit
   check (discovery runs, entity resolution, lineage traversal). Each needs a decision whether the
   value can really be missing; fix them one module at a time.
