# TAREL CLI Reference

Command reference for the CLI shipped in this source tree. Regenerate with `python tools/generate_cli_reference.py`.

Syntax, choices, defaults, required flags, and mutually exclusive groups are generated from the CLI parser. The command notes describe behavior; the linked contracts define structured inputs and outputs. Resource names in examples must be replaced with resources in your environment.

**Coverage:** 173 executable commands in 32 groups.

## Reading this reference

- Uppercase names and `<placeholders>` denote values supplied by the caller. Examples assume the named local resources exist.
- Syntax uses brackets for optional arguments, braces for allowed alternatives, and `...` for variable-length input.
- “Not set” is the parser default `None`; a use case or provider profile may resolve an effective value later.
- `--format` is command-specific, not a global flag. Its default is listed for each command.
- Run `tarel GROUP COMMAND --help` for the help of the installed version. `tarel --version` and `tarel version` both report its version.
- The CLI uses local project state under `.tarel`. There is no global `--state-dir` option in this parser; the SDK accepts an explicit runtime/state root.

## Resource and execution model

A connector observes a source. A logical source names its configuration and policy. A graph stores technical objects and semantic claims. A workspace organizes multiple graphs. A focus is a saved upstream selection. Provider tasks propose knowledge; review changes its accepted state.

Search/context/grounding return metadata, not analytical query results. The harness executes analysis. Raw samples and profiles are separate observations; requesting them can read source data and produce ephemeral output. Review proposals and dependency claims independently.

Repeated values of a workspace scope facet form a union; different facets narrow the result. Graphs, systems, areas, schemas, and zones have explicit ownership rules. Read-only inspection can still build a local cache on supported paths.

## Exit status and errors

The main dispatcher returns 2 for recognized domain errors and writes `error [code]: message` to stderr. Argument parsing errors also normally use status 2. Successful operations normally return 0. Some operations use 1 for an incomplete/unknown outcome (for example context expansion omissions or unknown context impact). Inspect structured status and omissions, not only the exit code. This is not an exhaustive external-driver failure catalog.

## Command index

[Structured results and errors](#structured-results-and-errors) · [Python SDK](#python-sdk) · [Contracts](contracts.md)

| Group | Commands | Purpose |
| --- | ---: | --- |
| [version](#version) | 1 | Identify the installed package when reporting an issue or reproducing a run. |
| [package](#package) | 5 | Plan, pack, inspect, verify, and unpack portable metadata snapshots. |
| [bundle](#bundle) | 4 | Build an install bundle of TAREL and chosen hub packages for a computer without internet. |
| [sync](#sync) | 15 | Publish approved graph metadata from a site and take it over into a central state. |
| [demo](#demo) | 1 | Create a deterministic local source for learning and regression exercises. |
| [workspace](#workspace) | 12 | Organize independent source graphs into systems, areas, schema scopes, and overlapping object zones. |
| [source](#source) | 9 | Name a connection profile once and use it for discovery, graph creation, enrichment, and grounding. |
| [connector](#connector) | 7 | Call a connector directly, inspect its availability, or scaffold a new adapter. |
| [knowledge](#knowledge) | 4 | Attach scoped business documentation for annotation tasks. |
| [provider](#provider) | 5 | Configure an optional structured-generation endpoint or create an adapter candidate. |
| [model](#model) | 2 | Manage optional local embedding and reranker model artifacts. |
| [index](#index) | 2 | Prepare and inspect rebuildable local retrieval indexes for a graph or workspace. |
| [graph](#graph) | 10 | Build, refresh, annotate, and inspect the technical and semantic snapshot of a source. |
| [ui](#ui) | 1 | Explore graph/workspace structure, lineage, and reviewable knowledge. |
| [lineage](#lineage) | 15 | Describe data dependencies, analyze definitions, trace upstream origins, and record observed executions. |
| [semantic](#semantic) | 4 | Import and inspect external semantic definitions and their bindings to graph objects. |
| [entity](#entity) | 6 | Inspect and review evidence that different representations may denote the same entity. |
| [discovery](#discovery) | 9 | Run a bounded hypothesis, observation, and decision protocol for joins, entities, and mappings. |
| [agent](#agent) | 1 | Install the supplied agent-facing resources into a supported target. |
| [topology](#topology) | 3 | Declare derived logical objects and their physical references. |
| [family](#family) | 10 | Group compatible physical objects under an explicitly reviewed logical family. |
| [binding](#binding) | 5 | Resolve caller selections to declared physical or family members. |
| [concept](#concept) | 4 | Describe semantic concepts, representations, and declared hierarchies. |
| [logical-join](#logical-join) | 4 | Find and review discovered joins involving logical endpoints. |
| [reference-mapping](#reference-mapping) | 5 | Record and retrieve evidence about caller-owned field correspondences. |
| [focus](#focus) | 3 | Persist an upstream selection starting at one exact reference. |
| [search](#search) | 1 | Find graph anchors by technical names and business meaning. |
| [context](#context) | 6 | Build a bounded context packet, prepare a stable prefix, compare packets, or expand pinned metadata. |
| [grounding](#grounding) | 1 | Combine a context packet with source identity, dialects, and selected lineage information. |
| [annotation](#annotation) | 9 | Plan knowledge work, hand a task to the harness, apply a proposal, and review its meaning. |
| [relationship](#relationship) | 6 | Propose, probe, discover, and review physical field relationships. |
| [retrieval](#retrieval) | 3 | Select embedding and reranker models independently across local and HTTP providers. |

## version

**Version.** Identify the installed package when reporting an issue or reproducing a run.

Prints the package version. No graph or provider operation.

Example:

```bash
tarel version
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel version`](#tarel-version) | Print the installed TAREL version. |

### tarel version

Print the installed TAREL version.

**Syntax**

```text
tarel version [-h]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |

**Result:** Version text; no JSON document.

CLI entry point and delegated output renderers: [src/tarel/cli/__init__.py](../src/tarel/cli/__init__.py).

## package

**Portable packages.** Plan, pack, inspect, verify, and unpack portable metadata snapshots.

Plan lists the selection; pack writes a deterministic .tarel file with scoped knowledge and explicitly selected lineage/global knowledge. Inspect reads its manifest, verify checks every document and checksum, and unpack writes only to a destination that does not exist.

Contract and workflow: [package-format.md](package-format.md).

Example:

```bash
tarel package inspect team.tarel
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel package pack`](#tarel-package-pack) | Create a deterministic package from local state. |
 | [`tarel package plan`](#tarel-package-plan) | Show the exact document selection before sharing. |
 | [`tarel package inspect`](#tarel-package-inspect) | Read the package manifest without extraction. |
 | [`tarel package verify`](#tarel-package-verify) | Verify checksums, contracts, and references. |
 | [`tarel package unpack`](#tarel-package-unpack) | Verify and unpack into a new state directory. |

### tarel package pack

Create a deterministic package from local state.

**Syntax**

```text
tarel package pack [-h] --state STATE --workspace WORKSPACE --output OUTPUT [--replace]
                          [--lineage LINEAGE] [--knowledge KNOWLEDGE] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--state` | Path | required | not set | TAREL state root containing graphs/. |
| `--workspace` | text | required | not set | Workspace identifier or mode switch; see the parameter syntax. |
| `--output` | text | required | not set | New .tarel package path. |
| `--replace` | flag | optional | `False` | Replace an existing named definition/document where supported. |
| `--lineage` | text | optional; repeatable | `[]` | Include this lineage (repeatable). |
| `--knowledge` | text | optional; repeatable | `[]` | Include this knowledge document explicitly (repeatable). |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Package path, selected workspace, entry counts by kind, compressed and uncompressed sizes, package revision, verification state, and unpack destination when applicable.

CLI entry point and delegated output renderers: [src/tarel/cli/package.py](../src/tarel/cli/package.py).

### tarel package plan

Show the exact document selection before sharing.

**Syntax**

```text
tarel package plan [-h] --state STATE --workspace WORKSPACE [--lineage LINEAGE]
                          [--knowledge KNOWLEDGE] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--state` | Path | required | not set | Selected review state. |
| `--workspace` | text | required | not set | Workspace identifier or mode switch; see the parameter syntax. |
| `--lineage` | text | optional; repeatable | `[]` | Include this lineage (repeatable). |
| `--knowledge` | text | optional; repeatable | `[]` | Include this knowledge document explicitly (repeatable). |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Package path, selected workspace, entry counts by kind, compressed and uncompressed sizes, package revision, verification state, and unpack destination when applicable.

CLI entry point and delegated output renderers: [src/tarel/cli/package.py](../src/tarel/cli/package.py).

### tarel package inspect

Read the package manifest without extraction.

**Syntax**

```text
tarel package inspect [-h] [--format {text,json}] path
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `path` | text | required | not set | Local input/output path for this command. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Package path, selected workspace, entry counts by kind, compressed and uncompressed sizes, package revision, verification state, and unpack destination when applicable.

CLI entry point and delegated output renderers: [src/tarel/cli/package.py](../src/tarel/cli/package.py).

### tarel package verify

Verify checksums, contracts, and references.

**Syntax**

```text
tarel package verify [-h] [--format {text,json}] path
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `path` | text | required | not set | Local input/output path for this command. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Package path, selected workspace, entry counts by kind, compressed and uncompressed sizes, package revision, verification state, and unpack destination when applicable.

CLI entry point and delegated output renderers: [src/tarel/cli/package.py](../src/tarel/cli/package.py).

### tarel package unpack

Verify and unpack into a new state directory.

**Syntax**

```text
tarel package unpack [-h] --destination DESTINATION [--format {text,json}] path
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `path` | text | required | not set | Local input/output path for this command. |
| `--destination` | text | required | not set | New state root; it must not already exist. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Package path, selected workspace, entry counts by kind, compressed and uncompressed sizes, package revision, verification state, and unpack destination when applicable.

CLI entry point and delegated output renderers: [src/tarel/cli/package.py](../src/tarel/cli/package.py).

## bundle

**Offline bundles.** Build an install bundle of TAREL and chosen hub packages for a computer without internet.

Without a subcommand, a dialog asks about the target computer and the parts to include. Plan downloads nothing. Build writes a ZIP of wheels with a hash-pinned requirements.lock and, on a matching machine, installs it offline as a test.

Contract and workflow: [offline-bundles.md](offline-bundles.md).

Example:

```bash
tarel bundle plan --target windows-x86_64-py3.12 --with sqlserver
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel bundle profile`](#tarel-bundle-profile) | Show the command that describes a target computer. |
 | [`tarel bundle components`](#tarel-bundle-components) | List what a bundle can contain. |
 | [`tarel bundle plan`](#tarel-bundle-plan) | Show what a build would download; downloads nothing. |
 | [`tarel bundle build`](#tarel-bundle-build) | Build a bundle without questions. |

### tarel bundle profile

Show the command that describes a target computer.

**Syntax**

```text
tarel bundle profile [-h] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** For profile, the command to run on the target; for components, each part with its origin and status; for plan, target, wheel tags and requirements; for build, the bundle path, size, packages with licenses, and whether it was installed or resolved.

CLI entry point and delegated output renderers: [src/tarel/cli/bundle.py](../src/tarel/cli/bundle.py).

### tarel bundle components

List what a bundle can contain.

**Syntax**

```text
tarel bundle components [-h] [--hub HUB] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--hub` | Path | optional | not set | Folder of a TAREL hub checkout. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** For profile, the command to run on the target; for components, each part with its origin and status; for plan, target, wheel tags and requirements; for build, the bundle path, size, packages with licenses, and whether it was installed or resolved.

CLI entry point and delegated output renderers: [src/tarel/cli/bundle.py](../src/tarel/cli/bundle.py).

### tarel bundle plan

Show what a build would download; downloads nothing.

**Syntax**

```text
tarel bundle plan [-h] [--hub HUB] [--recipe RECIPE] [--target TARGET] [--with COMPONENTS]
                         [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--hub` | Path | optional | not set | Folder of a TAREL hub checkout. |
| `--recipe` | Path | optional | not set | Recipe file from an earlier build. |
| `--target` | text | optional | not set | host, a pasted profile line, or e.g. windows-x86_64-py3.12, linux-x86_64-py3.12-glibc2.28. |
| `--with` | text | optional; repeatable | `[]` | Component ids, comma-separated or repeated (see `tarel bundle components`). |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** For profile, the command to run on the target; for components, each part with its origin and status; for plan, target, wheel tags and requirements; for build, the bundle path, size, packages with licenses, and whether it was installed or resolved.

CLI entry point and delegated output renderers: [src/tarel/cli/bundle.py](../src/tarel/cli/bundle.py).

### tarel bundle build

Build a bundle without questions.

**Syntax**

```text
tarel bundle build [-h] [--hub HUB] [--recipe RECIPE] [--target TARGET] [--with COMPONENTS]
                          [--output OUTPUT] [--replace] [--save-recipe SAVE_RECIPE]
                          [--tarel-from TAREL_FROM] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--hub` | Path | optional | not set | Folder of a TAREL hub checkout. |
| `--recipe` | Path | optional | not set | Recipe file from an earlier build. |
| `--target` | text | optional | not set | host, a pasted profile line, or e.g. windows-x86_64-py3.12, linux-x86_64-py3.12-glibc2.28. |
| `--with` | text | optional; repeatable | `[]` | Component ids, comma-separated or repeated (see `tarel bundle components`). |
| `--output` | Path | optional | not set | Bundle .zip path (default: current folder). |
| `--replace` | flag | optional | `False` | Overwrite an existing bundle. |
| `--save-recipe` | Path | optional | not set | Also write the recipe to this file. |
| `--tarel-from` | Path | optional | not set | Use this TAREL wheel or source checkout instead of the release from PyPI. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** For profile, the command to run on the target; for components, each part with its origin and status; for plan, target, wheel tags and requirements; for build, the bundle path, size, packages with licenses, and whether it was installed or resolved.

CLI entry point and delegated output renderers: [src/tarel/cli/bundle.py](../src/tarel/cli/bundle.py).

## sync

**Metadata sync.** Publish approved graph metadata from a site and take it over into a central state.

Publish writes a .tarelpub file and advances the site's own counter. Plan changes nothing. Apply checks the file against local trust and history and activates it atomically; only the graph named in the trust entry is written. A signature proves the sender, and the trust entry alone decides what that sender may publish.

Contract and workflow: [sync.md](contracts.md).

Example:

```bash
tarel sync status --state central/.tarel
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel sync init`](#tarel-sync-init) | Give this site its publisher identity once. |
 | [`tarel sync stream-create`](#tarel-sync-stream-create) | Name one export of one graph. |
 | [`tarel sync stream-update`](#tarel-sync-stream-update) | Replace what a stream approves under a new profile version. |
 | [`tarel sync publish`](#tarel-sync-publish) | Write one .tarelpub file for a stream. |
 | [`tarel sync inspect`](#tarel-sync-inspect) | Verify and describe a file; no state involved. |
 | [`tarel sync trust-add`](#tarel-sync-trust-add) | Allow one stream to write one local graph. |
 | [`tarel sync trust-scope`](#tarel-sync-trust-scope) | Replace what a trusted stream may publish. |
 | [`tarel sync trust-key`](#tarel-sync-trust-key) | Accept one more signing key for a publisher. |
 | [`tarel sync revoke-key`](#tarel-sync-revoke-key) | Stop accepting a signing key in this state. |
 | [`tarel sync plan`](#tarel-sync-plan) | Show what applying a file would do; changes nothing. |
 | [`tarel sync apply`](#tarel-sync-apply) | Check a file and activate it atomically. |
 | [`tarel sync recover`](#tarel-sync-recover) | Finish activations a stopped process committed but did not complete. |
 | [`tarel sync inbox`](#tarel-sync-inbox) | Run one pass over a directory of delivered files, with the same checks. |
 | [`tarel sync status`](#tarel-sync-status) | Show each origin's age, receipt and failures. |
 | [`tarel sync prune`](#tarel-sync-prune) | Delete old revisions of a stream; the active view does not change. |

### tarel sync init

Give this site its publisher identity once.

**Syntax**

```text
tarel sync init [-h] [--state STATE] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--state` | Path | optional | `.tarel` | TAREL state root. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The publisher identity, stream or trust entry; for publish, the file, its publication ID and statement; for plan and apply, the action, sequence, object changes, affected central claims and warnings; for status, each origin's active publication, source age, receipt and last failure.

CLI entry point and delegated output renderers: [src/tarel/cli/sync.py](../src/tarel/cli/sync.py).

### tarel sync stream-create

Name one export of one graph.

**Syntax**

```text
tarel sync stream-create [-h] --graph GRAPH --name NAME --namespace NAMESPACES
                                [--annotations] [--technical-descriptions] [--state STATE]
                                [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `--name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--namespace` | text | required; repeatable | not set | Approve this namespace for export (repeatable). |
| `--annotations` | flag | optional | `False` | Also publish annotations. |
| `--technical-descriptions` | flag | optional | `False` | Also publish descriptions read from the source; these are free text. |
| `--state` | Path | optional | `.tarel` | TAREL state root. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The publisher identity, stream or trust entry; for publish, the file, its publication ID and statement; for plan and apply, the action, sequence, object changes, affected central claims and warnings; for status, each origin's active publication, source age, receipt and last failure.

CLI entry point and delegated output renderers: [src/tarel/cli/sync.py](../src/tarel/cli/sync.py).

### tarel sync stream-update

Replace what a stream approves under a new profile version.

**Syntax**

```text
tarel sync stream-update [-h] --name NAME --namespace NAMESPACES [--annotations]
                                [--technical-descriptions] [--state STATE] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--namespace` | text | required; repeatable | not set | Approve this namespace for export (repeatable). |
| `--annotations` | flag | optional | `False` | Also publish annotations. |
| `--technical-descriptions` | flag | optional | `False` | Also publish descriptions read from the source; these are free text. |
| `--state` | Path | optional | `.tarel` | TAREL state root. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The publisher identity, stream or trust entry; for publish, the file, its publication ID and statement; for plan and apply, the action, sequence, object changes, affected central claims and warnings; for status, each origin's active publication, source age, receipt and last failure.

CLI entry point and delegated output renderers: [src/tarel/cli/sync.py](../src/tarel/cli/sync.py).

### tarel sync publish

Write one .tarelpub file for a stream.

**Syntax**

```text
tarel sync publish [-h] --stream STREAM --output OUTPUT [--observed-at OBSERVED_AT]
                          [--completeness {complete,partial}] [--signing-key SIGNING_KEY]
                          [--unsigned-dev] [--state STATE] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--stream` | text | required | not set | Name of the stream to publish. |
| `--output` | Path | required | not set | New .tarelpub file path. |
| `--observed-at` | text | optional | not set | State the UTC read time yourself, ending in Z; default is this state's own record. |
| `--completeness` | text; `complete`, `partial` | optional | not set | State this together with --observed-at; a central state refuses partial files. |
| `--signing-key` | Path | optional | not set | Private key path, or its .pub file when the key is in an agent. It is not copied. |
| `--unsigned-dev` | flag | optional | `False` | Write an unsigned file. For local development only. |
| `--state` | Path | optional | `.tarel` | TAREL state root. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The publisher identity, stream or trust entry; for publish, the file, its publication ID and statement; for plan and apply, the action, sequence, object changes, affected central claims and warnings; for status, each origin's active publication, source age, receipt and last failure.

CLI entry point and delegated output renderers: [src/tarel/cli/sync.py](../src/tarel/cli/sync.py).

### tarel sync inspect

Verify and describe a file; no state involved.

**Syntax**

```text
tarel sync inspect [-h] [--format {text,json}] path
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `path` | Path | required | not set | Local input/output path for this command. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The publisher identity, stream or trust entry; for publish, the file, its publication ID and statement; for plan and apply, the action, sequence, object changes, affected central claims and warnings; for status, each origin's active publication, source age, receipt and last failure.

CLI entry point and delegated output renderers: [src/tarel/cli/sync.py](../src/tarel/cli/sync.py).

### tarel sync trust-add

Allow one stream to write one local graph.

**Syntax**

```text
tarel sync trust-add [-h] --publisher-id PUBLISHER_ID --stream-id STREAM_ID --graph-id
                            GRAPH_ID --local-graph LOCAL_GRAPH --workspace WORKSPACE --system SYSTEM
                            --namespace NAMESPACES [--allow-annotations]
                            [--allow-technical-descriptions] [--state STATE] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--publisher-id` | text | required | not set | The publisher allowed to write. |
| `--stream-id` | text | required | not set | The one stream this entry allows. |
| `--graph-id` | text | required | not set | The source graph that stream carries. |
| `--local-graph` | text | required | not set | Central graph this stream may write. |
| `--workspace` | text | required | not set | Workspace identifier or mode switch; see the parameter syntax. |
| `--system` | text | required | not set | Workspace system holding that graph. |
| `--namespace` | text | required; repeatable | not set | Allow this namespace (repeatable). |
| `--allow-annotations` | flag | optional | `False` | Allow annotations. |
| `--allow-technical-descriptions` | flag | optional | `False` | Allow free-text descriptions read from the source. |
| `--state` | Path | optional | `.tarel` | TAREL state root. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The publisher identity, stream or trust entry; for publish, the file, its publication ID and statement; for plan and apply, the action, sequence, object changes, affected central claims and warnings; for status, each origin's active publication, source age, receipt and last failure.

CLI entry point and delegated output renderers: [src/tarel/cli/sync.py](../src/tarel/cli/sync.py).

### tarel sync trust-scope

Replace what a trusted stream may publish.

**Syntax**

```text
tarel sync trust-scope [-h] --stream-id STREAM_ID --namespace NAMESPACES
                              [--allow-annotations] [--allow-technical-descriptions] [--state STATE]
                              [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--stream-id` | text | required | not set | The trusted stream to change. |
| `--namespace` | text | required; repeatable | not set | Allow this namespace (repeatable). |
| `--allow-annotations` | flag | optional | `False` | Allow annotations. |
| `--allow-technical-descriptions` | flag | optional | `False` | Allow free-text descriptions read from the source. |
| `--state` | Path | optional | `.tarel` | TAREL state root. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The publisher identity, stream or trust entry; for publish, the file, its publication ID and statement; for plan and apply, the action, sequence, object changes, affected central claims and warnings; for status, each origin's active publication, source age, receipt and last failure.

CLI entry point and delegated output renderers: [src/tarel/cli/sync.py](../src/tarel/cli/sync.py).

### tarel sync trust-key

Accept one more signing key for a publisher.

**Syntax**

```text
tarel sync trust-key [-h] --publisher-id PUBLISHER_ID --public-key-file PUBLIC_KEY_FILE
                            [--not-after NOT_AFTER] [--state STATE] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--publisher-id` | text | required | not set | The publisher using this key. |
| `--public-key-file` | Path | required | not set | OpenSSH Ed25519 public key file. |
| `--not-after` | text | optional | not set | Refuse this key after this UTC time, ending in Z. |
| `--state` | Path | optional | `.tarel` | TAREL state root. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The publisher identity, stream or trust entry; for publish, the file, its publication ID and statement; for plan and apply, the action, sequence, object changes, affected central claims and warnings; for status, each origin's active publication, source age, receipt and last failure.

CLI entry point and delegated output renderers: [src/tarel/cli/sync.py](../src/tarel/cli/sync.py).

### tarel sync revoke-key

Stop accepting a signing key in this state.

**Syntax**

```text
tarel sync revoke-key [-h] --publisher-id PUBLISHER_ID --fingerprint FINGERPRINT
                             [--state STATE] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--publisher-id` | text | required | not set | The publisher of the key. |
| `--fingerprint` | text | required | not set | The key's SHA256 fingerprint. |
| `--state` | Path | optional | `.tarel` | TAREL state root. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The publisher identity, stream or trust entry; for publish, the file, its publication ID and statement; for plan and apply, the action, sequence, object changes, affected central claims and warnings; for status, each origin's active publication, source age, receipt and last failure.

CLI entry point and delegated output renderers: [src/tarel/cli/sync.py](../src/tarel/cli/sync.py).

### tarel sync plan

Show what applying a file would do; changes nothing.

**Syntax**

```text
tarel sync plan [-h] [--allow-unsigned-dev] [--accept-history-gap] [--state STATE]
                       [--format {text,json}]
                       path
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `path` | Path | required | not set | Local input/output path for this command. |
| `--allow-unsigned-dev` | flag | optional | `False` | Accept an unsigned file. For local development only. |
| `--accept-history-gap` | flag | optional | `False` | Accept a file whose history no longer reaches the active publication. |
| `--state` | Path | optional | `.tarel` | TAREL state root. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The publisher identity, stream or trust entry; for publish, the file, its publication ID and statement; for plan and apply, the action, sequence, object changes, affected central claims and warnings; for status, each origin's active publication, source age, receipt and last failure.

CLI entry point and delegated output renderers: [src/tarel/cli/sync.py](../src/tarel/cli/sync.py).

### tarel sync apply

Check a file and activate it atomically.

**Syntax**

```text
tarel sync apply [-h] [--plan-id PLAN_ID] [--allow-unsigned-dev] [--accept-history-gap]
                        [--state STATE] [--format {text,json}]
                        path
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `path` | Path | required | not set | Local input/output path for this command. |
| `--plan-id` | text | optional | not set | Refuse if anything changed since this plan. |
| `--allow-unsigned-dev` | flag | optional | `False` | Accept an unsigned file. For local development only. |
| `--accept-history-gap` | flag | optional | `False` | Accept a file whose history no longer reaches the active publication. |
| `--state` | Path | optional | `.tarel` | TAREL state root. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The publisher identity, stream or trust entry; for publish, the file, its publication ID and statement; for plan and apply, the action, sequence, object changes, affected central claims and warnings; for status, each origin's active publication, source age, receipt and last failure.

CLI entry point and delegated output renderers: [src/tarel/cli/sync.py](../src/tarel/cli/sync.py).

### tarel sync recover

Finish activations a stopped process committed but did not complete.

**Syntax**

```text
tarel sync recover [-h] [--state STATE] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--state` | Path | optional | `.tarel` | TAREL state root. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The publisher identity, stream or trust entry; for publish, the file, its publication ID and statement; for plan and apply, the action, sequence, object changes, affected central claims and warnings; for status, each origin's active publication, source age, receipt and last failure.

CLI entry point and delegated output renderers: [src/tarel/cli/sync.py](../src/tarel/cli/sync.py).

### tarel sync inbox

Run one pass over a directory of delivered files, with the same checks.

**Syntax**

```text
tarel sync inbox [-h] --directory DIRECTORY [--min-age-seconds MIN_AGE_SECONDS]
                        [--allow-unsigned-dev] [--state STATE] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--directory` | Path | required | not set | The directory to read. |
| `--min-age-seconds` | float | optional | `0` | Leave files younger than this for the next pass. |
| `--allow-unsigned-dev` | flag | optional | `False` | Accept unsigned files. For local development only. |
| `--state` | Path | optional | `.tarel` | TAREL state root. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The publisher identity, stream or trust entry; for publish, the file, its publication ID and statement; for plan and apply, the action, sequence, object changes, affected central claims and warnings; for status, each origin's active publication, source age, receipt and last failure.

CLI entry point and delegated output renderers: [src/tarel/cli/sync.py](../src/tarel/cli/sync.py).

### tarel sync status

Show each origin's age, receipt and failures.

**Syntax**

```text
tarel sync status [-h] [--max-age-hours MAX_AGE_HOURS] [--state STATE] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--max-age-hours` | float | optional | not set | Mark an origin stale when its source read is older. |
| `--state` | Path | optional | `.tarel` | TAREL state root. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The publisher identity, stream or trust entry; for publish, the file, its publication ID and statement; for plan and apply, the action, sequence, object changes, affected central claims and warnings; for status, each origin's active publication, source age, receipt and last failure.

CLI entry point and delegated output renderers: [src/tarel/cli/sync.py](../src/tarel/cli/sync.py).

### tarel sync prune

Delete old revisions of a stream; the active view does not change.

**Syntax**

```text
tarel sync prune [-h] --stream-id STREAM_ID [--state STATE] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--stream-id` | text | required | not set | The stream to clean up. |
| `--state` | Path | optional | `.tarel` | TAREL state root. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The publisher identity, stream or trust entry; for publish, the file, its publication ID and statement; for plan and apply, the action, sequence, object changes, affected central claims and warnings; for status, each origin's active publication, source age, receipt and last failure.

CLI entry point and delegated output renderers: [src/tarel/cli/sync.py](../src/tarel/cli/sync.py).

## demo

**Demo warehouse.** Create a deterministic local source for learning and regression exercises.

Creates a local SQLite database and its connector configuration. Replacing a demo with --force changes that demo source.

Contract and workflow: [retail-demo.md](retail-demo.md).

Example:

```bash
tarel demo create retail-dwh
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel demo create`](#tarel-demo-create) | Create a local demo source and its private connector configuration. |

### tarel demo create

Create a local demo source and its private connector configuration.

**Syntax**

```text
tarel demo create [-h] [--path PATH] [--version {1,2}] [--force] [--format {text,json}]
                         {retail-dwh}
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text; `retail-dwh` | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--path` | Path | optional | not set | SQLite target path. |
| `--version` | int; `1`, `2` | optional | `1` | Requested demo/model format version. |
| `--force` | flag | optional | `False` | Replace an existing demo database and configuration. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Created demo paths/configuration and version information. Existing demo replacement requires the command-specific force flag.

CLI entry point and delegated output renderers: [src/tarel/cli/demo.py](../src/tarel/cli/demo.py).

## workspace

**Workspace organization.** Organize independent source graphs into systems, areas, schema scopes, and overlapping object zones.

Definitions and relationship decisions persist workspace state. A define operation replaces its named definition; supply the complete desired membership. List/show/scope inspect that state.

Contract and workflow: [workspaces.md](contracts.md#workspaces-and-scopes).

Example:

```bash
tarel workspace scope enterprise --system warehouse --format json
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel workspace create`](#tarel-workspace-create) | Create an empty local workspace. |
 | [`tarel workspace list`](#tarel-workspace-list) | List local workspaces. |
 | [`tarel workspace show`](#tarel-workspace-show) | Show one workspace hierarchy. |
 | [`tarel workspace scope`](#tarel-workspace-scope) | Resolve systems, areas, schemas, graphs, and zones to graph objects. |
 | [`tarel workspace system define`](#tarel-workspace-system-define) | Create or replace a system graph assignment. |
 | [`tarel workspace area define`](#tarel-workspace-area-define) | Create or replace an area schema assignment. |
 | [`tarel workspace zone define`](#tarel-workspace-zone-define) | Create or replace an explicit zone membership. |
 | [`tarel workspace zone show`](#tarel-workspace-zone-show) | Resolve a zone to current graph objects and their areas. |
 | [`tarel workspace relationship add`](#tarel-workspace-relationship-add) | Add a human-authored cross-graph relationship candidate. |
 | [`tarel workspace relationship list`](#tarel-workspace-relationship-list) | List persisted workspace relationships. |
 | [`tarel workspace relationship validate`](#tarel-workspace-relationship-validate) | Validate a workspace relationship. |
 | [`tarel workspace relationship reject`](#tarel-workspace-relationship-reject) | Reject a workspace relationship. |

### tarel workspace create

Create an empty local workspace.

**Syntax**

```text
tarel workspace create [-h] [--description DESCRIPTION] [--format {text,json}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--description` | text | optional | not set | Description stored with this artifact. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Workspace definition, resolved scope/zone, or relationship records according to the verb. Scope output identifies selected graph objects and its scope hash.

CLI entry point and delegated output renderers: [src/tarel/cli/workspace.py](../src/tarel/cli/workspace.py).

### tarel workspace list

List local workspaces.

**Syntax**

```text
tarel workspace list [-h] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Workspace definition, resolved scope/zone, or relationship records according to the verb. Scope output identifies selected graph objects and its scope hash.

CLI entry point and delegated output renderers: [src/tarel/cli/workspace.py](../src/tarel/cli/workspace.py).

### tarel workspace show

Show one workspace hierarchy.

**Syntax**

```text
tarel workspace show [-h] [--format {text,json}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Workspace definition, resolved scope/zone, or relationship records according to the verb. Scope output identifies selected graph objects and its scope hash.

CLI entry point and delegated output renderers: [src/tarel/cli/workspace.py](../src/tarel/cli/workspace.py).

### tarel workspace scope

Resolve systems, areas, schemas, graphs, and zones to graph objects.

**Syntax**

```text
tarel workspace scope [-h] [--system SYSTEMS] [--graph GRAPHS] [--area AREAS]
                             [--schema SCHEMAS] [--zone ZONES] [--format {text,json}]
                             name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Workspace name. |
| `--system` | text | optional; repeatable | not set | Include a system; repeat to include multiple systems. |
| `--graph` | text | optional; repeatable | not set | Limit the scope to a graph; repeat to include multiple graphs. |
| `--area` | text | optional; repeatable | not set | Limit to an area (NAME or SYSTEM:NAME); repeat for a union. |
| `--schema` | text | optional; repeatable | not set | Limit to a schema as GRAPH:NAMESPACE; repeat for a union. |
| `--zone` | text | optional; repeatable | not set | Limit to a zone (NAME or SYSTEM:NAME); repeat for a union. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Workspace definition, resolved scope/zone, or relationship records according to the verb. Scope output identifies selected graph objects and its scope hash.

CLI entry point and delegated output renderers: [src/tarel/cli/workspace.py](../src/tarel/cli/workspace.py).

### tarel workspace system define

Create or replace a system graph assignment.

**Syntax**

```text
tarel workspace system define [-h] --graph GRAPHS [--description DESCRIPTION]
                                     [--format {text,json}]
                                     workspace_name system_name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `workspace_name` | text | required | not set | Workspace name. |
| `system_name` | text | required | not set | System name within the workspace. |
| `--graph` | text | required; repeatable | not set | Graph names to include. |
| `--description` | text | optional | not set | Description stored with this artifact. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Workspace definition, resolved scope/zone, or relationship records according to the verb. Scope output identifies selected graph objects and its scope hash.

CLI entry point and delegated output renderers: [src/tarel/cli/workspace.py](../src/tarel/cli/workspace.py).

### tarel workspace area define

Create or replace an area schema assignment.

**Syntax**

```text
tarel workspace area define [-h] --schema SCHEMAS [--description DESCRIPTION]
                                   [--format {text,json}]
                                   workspace_name system_name area_name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `workspace_name` | text | required | not set | Workspace name. |
| `system_name` | text | required | not set | System name within the workspace. |
| `area_name` | text | required | not set | Area name within the system. |
| `--schema` | text | required; repeatable | not set | Schema reference as GRAPH:NAMESPACE. |
| `--description` | text | optional | not set | Description stored with this artifact. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Workspace definition, resolved scope/zone, or relationship records according to the verb. Scope output identifies selected graph objects and its scope hash.

CLI entry point and delegated output renderers: [src/tarel/cli/workspace.py](../src/tarel/cli/workspace.py).

### tarel workspace zone define

Create or replace an explicit zone membership.

A zone can span graphs and schemas inside one system. Its member schemas must already be assigned to areas. Supply the complete desired object list on every definition.

**Syntax**

```text
tarel workspace zone define [-h] --object OBJECTS [--description DESCRIPTION]
                                   [--format {text,json}]
                                   workspace_name system_name zone_name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `workspace_name` | text | required | not set | Workspace name. |
| `system_name` | text | required | not set | System name within the workspace. |
| `zone_name` | text | required | not set | Zone name within the system. |
| `--object` | text | required; repeatable | not set | Object reference as GRAPH:NAMESPACE.OBJECT. |
| `--description` | text | optional | not set | Description stored with this artifact. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Workspace definition, resolved scope/zone, or relationship records according to the verb. Scope output identifies selected graph objects and its scope hash.

CLI entry point and delegated output renderers: [src/tarel/cli/workspace.py](../src/tarel/cli/workspace.py).

### tarel workspace zone show

Resolve a zone to current graph objects and their areas.

**Syntax**

```text
tarel workspace zone show [-h] [--format {text,json}] workspace_name system_name zone_name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `workspace_name` | text | required | not set | Workspace name. |
| `system_name` | text | required | not set | System name within the workspace. |
| `zone_name` | text | required | not set | Zone name within the system. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Workspace definition, resolved scope/zone, or relationship records according to the verb. Scope output identifies selected graph objects and its scope hash.

CLI entry point and delegated output renderers: [src/tarel/cli/workspace.py](../src/tarel/cli/workspace.py).

### tarel workspace relationship add

Add a human-authored cross-graph relationship candidate.

**Syntax**

```text
tarel workspace relationship add [-h] --from SOURCE_REFERENCE --to TARGET_REFERENCE --reason
                                        REASON [--validated] [--format {text,json}]
                                        workspace_name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `workspace_name` | text | required | not set | Workspace name. |
| `--from` | text | required | not set | Source field as GRAPH:NAMESPACE.OBJECT.FIELD. |
| `--to` | text | required | not set | Target field as GRAPH:NAMESPACE.OBJECT.FIELD. |
| `--reason` | text | required | not set | Human-readable reason for the decision or mutation. |
| `--validated` | flag | optional | `False` | Persist as human-validated instead of draft. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Workspace definition, resolved scope/zone, or relationship records according to the verb. Scope output identifies selected graph objects and its scope hash.

CLI entry point and delegated output renderers: [src/tarel/cli/workspace.py](../src/tarel/cli/workspace.py).

### tarel workspace relationship list

List persisted workspace relationships.

**Syntax**

```text
tarel workspace relationship list [-h] [--format {text,json}] workspace_name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `workspace_name` | text | required | not set | Workspace name. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Workspace definition, resolved scope/zone, or relationship records according to the verb. Scope output identifies selected graph objects and its scope hash.

CLI entry point and delegated output renderers: [src/tarel/cli/workspace.py](../src/tarel/cli/workspace.py).

### tarel workspace relationship validate

Validate a workspace relationship.

**Syntax**

```text
tarel workspace relationship validate [-h] --reason REASON [--format {text,json}]
                                             workspace_name relationship_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `workspace_name` | text | required | not set | Workspace name. |
| `relationship_id` | text | required | not set | Workspace relationship identifier. |
| `--reason` | text | required | not set | Human-readable reason for the decision or mutation. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Workspace definition, resolved scope/zone, or relationship records according to the verb. Scope output identifies selected graph objects and its scope hash.

CLI entry point and delegated output renderers: [src/tarel/cli/workspace.py](../src/tarel/cli/workspace.py).

### tarel workspace relationship reject

Reject a workspace relationship.

**Syntax**

```text
tarel workspace relationship reject [-h] --reason REASON [--format {text,json}]
                                           workspace_name relationship_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `workspace_name` | text | required | not set | Workspace name. |
| `relationship_id` | text | required | not set | Workspace relationship identifier. |
| `--reason` | text | required | not set | Human-readable reason for the decision or mutation. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Workspace definition, resolved scope/zone, or relationship records according to the verb. Scope output identifies selected graph objects and its scope hash.

CLI entry point and delegated output renderers: [src/tarel/cli/workspace.py](../src/tarel/cli/workspace.py).

## source

**Logical sources.** Name a connection profile once and use it for discovery, graph creation, enrichment, and grounding.

Configure persists logical source settings; check/probe/discover have different purposes. Build/refresh update graphs. Enrich returns an ephemeral observation workfile, with persistence only for explicitly requested candidates. Source permissions independently govern aggregates, small domains, samples, and entity aliases.

Contract and workflow: [retail-demo.md](retail-demo.md).

Example:

```bash
tarel source check warehouse-prod
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel source configure`](#tarel-source-configure) | Create or explicitly replace a non-secret logical source profile. |
 | [`tarel source list`](#tarel-source-list) | List configured logical sources. |
 | [`tarel source show`](#tarel-source-show) | Show one logical source profile. |
 | [`tarel source check`](#tarel-source-check) | Check connector availability and whether the config reference resolves. |
 | [`tarel source probe`](#tarel-source-probe) | Resolve the private config reference and run a bounded read-only probe. |
 | [`tarel source discover`](#tarel-source-discover) | Discover source metadata through the configured connector. |
 | [`tarel source build`](#tarel-source-build) | Build a graph and bind it to this logical source. |
 | [`tarel source refresh`](#tarel-source-refresh) | Refresh a bound graph through this logical source. |
 | [`tarel source enrich`](#tarel-source-enrich) | Profile every graph object under the source enrichment policy. |

### tarel source configure

Create or explicitly replace a non-secret logical source profile.

**Syntax**

```text
tarel source configure [-h] --connector CONNECTOR [--config-ref CONFIG_REFERENCE]
                              [--database DATABASE] [--namespace NAMESPACE] [--graph GRAPHS]
                              [--allow-aggregates] [--allow-small-domains] [--allow-raw-samples]
                              [--allow-entity-aliases] [--replace] [--format {text,json}]
                              name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--connector` | text | required | not set | Connector identifier. |
| `--config-ref` | text | optional | not set | env:VARIABLE or state:relative/path.toml; never a connection URL. |
| `--database` | text | optional | not set | Source database override. |
| `--namespace, --schema` | text | optional | not set | Namespace/schema filter. |
| `--graph` | text | optional; repeatable | not set | Graph names to include. |
| `--allow-aggregates` | flag | optional | `False` | Permit bounded aggregate column profiles for this source. |
| `--allow-small-domains` | flag | optional | `False` | Permit complete small-domain counts; requires aggregate permission. |
| `--allow-raw-samples` | flag | optional | `False` | Permit ephemeral raw samples of at most ten rows per object. |
| `--allow-entity-aliases` | flag | optional | `False` | Permit protected complete identity inspection and durable key groups. |
| `--replace` | flag | optional | `False` | Replace an existing named definition/document where supported. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Profile, availability/probe result, observed catalog, graph summary, or enrichment workfile according to the verb. Config references remain distinct from resolved credentials.

CLI entry point and delegated output renderers: [src/tarel/cli/source.py](../src/tarel/cli/source.py).

### tarel source list

List configured logical sources.

**Syntax**

```text
tarel source list [-h] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Profile, availability/probe result, observed catalog, graph summary, or enrichment workfile according to the verb. Config references remain distinct from resolved credentials.

CLI entry point and delegated output renderers: [src/tarel/cli/source.py](../src/tarel/cli/source.py).

### tarel source show

Show one logical source profile.

**Syntax**

```text
tarel source show [-h] [--format {text,json}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Profile, availability/probe result, observed catalog, graph summary, or enrichment workfile according to the verb. Config references remain distinct from resolved credentials.

CLI entry point and delegated output renderers: [src/tarel/cli/source.py](../src/tarel/cli/source.py).

### tarel source check

Check connector availability and whether the config reference resolves.

**Syntax**

```text
tarel source check [-h] [--format {text,json}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Profile, availability/probe result, observed catalog, graph summary, or enrichment workfile according to the verb. Config references remain distinct from resolved credentials.

CLI entry point and delegated output renderers: [src/tarel/cli/source.py](../src/tarel/cli/source.py).

### tarel source probe

Resolve the private config reference and run a bounded read-only probe.

**Syntax**

```text
tarel source probe [-h] [--database DATABASE] [--format {text,json}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--database` | text | optional | not set | Source database override. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Profile, availability/probe result, observed catalog, graph summary, or enrichment workfile according to the verb. Config references remain distinct from resolved credentials.

CLI entry point and delegated output renderers: [src/tarel/cli/source.py](../src/tarel/cli/source.py).

### tarel source discover

Discover source metadata through the configured connector.

**Syntax**

```text
tarel source discover [-h] [--database DATABASE] [--namespace NAMESPACE]
                             [--format {text,json}]
                             name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--database` | text | optional | not set | Source database override. |
| `--namespace, --schema` | text | optional | not set | Namespace/schema filter. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Profile, availability/probe result, observed catalog, graph summary, or enrichment workfile according to the verb. Config references remain distinct from resolved credentials.

CLI entry point and delegated output renderers: [src/tarel/cli/source.py](../src/tarel/cli/source.py).

### tarel source build

Build a graph and bind it to this logical source.

**Syntax**

```text
tarel source build [-h] [--database DATABASE] [--namespace NAMESPACE] [--format {text,json}]
                          name graph_name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `graph_name` | text | required | not set | Local graph name. |
| `--database` | text | optional | not set | Source database override. |
| `--namespace, --schema` | text | optional | not set | Namespace/schema filter. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Profile, availability/probe result, observed catalog, graph summary, or enrichment workfile according to the verb. Config references remain distinct from resolved credentials.

CLI entry point and delegated output renderers: [src/tarel/cli/source.py](../src/tarel/cli/source.py).

### tarel source refresh

Refresh a bound graph through this logical source.

**Syntax**

```text
tarel source refresh [-h] [--namespace NAMESPACE] [--annotate-new PROVIDER]
                            [--annotation-workers ANNOTATION_WORKERS]
                            [--annotation-model ANNOTATION_MODEL]
                            [--annotation-timeout ANNOTATION_TIMEOUT] [--format {text,json}]
                            name graph_name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `graph_name` | text | required | not set | Local graph name. |
| `--namespace, --schema` | text | optional | not set | Namespace/schema filter. |
| `--annotate-new` | text | optional | not set | Annotate only object and field gaps introduced by this refresh. |
| `--annotation-workers` | int | optional | `1` | Parallel provider requests for newly introduced annotation gaps. |
| `--annotation-model` | text | optional | not set | Optional model override for the delta annotation batch. |
| `--annotation-timeout` | float | optional | `120.0` | Provider timeout in seconds for delta annotation requests. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Profile, availability/probe result, observed catalog, graph summary, or enrichment workfile according to the verb. Config references remain distinct from resolved credentials.

CLI entry point and delegated output renderers: [src/tarel/cli/source.py](../src/tarel/cli/source.py).

### tarel source enrich

Profile every graph object under the source enrichment policy.

Walks the bound graph and returns an ephemeral workfile. Authorized raw rows remain output rather than graph/context content. Persisting join candidates is explicit; zero candidates can be a valid result.

**Syntax**

```text
tarel source enrich [-h] [--profile-row-limit PROFILE_ROW_LIMIT]
                           [--sample-limit SAMPLE_LIMIT] [--persist-join-candidates]
                           [--format {text,json}]
                           name graph_name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `graph_name` | text | required | not set | Local graph name. |
| `--profile-row-limit` | int | optional | `10000` | Row budget for profiling. |
| `--sample-limit` | int | optional | `10` | Raw rows per object when allowed; maximum 10 (default: 10). |
| `--persist-join-candidates` | flag | optional | `False` | Persist aggregate transformed-join evidence, never sample rows. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Profile, availability/probe result, observed catalog, graph summary, or enrichment workfile according to the verb. Config references remain distinct from resolved credentials.

CLI entry point and delegated output renderers: [src/tarel/cli/source.py](../src/tarel/cli/source.py).

## connector

**Connectors.** Call a connector directly, inspect its availability, or scaffold a new adapter.

Probe/discover/profile/sample can read the external source. Scaffold writes an inactive candidate package; it does not implement or install it. Direct connector commands and named source policies are distinct interfaces.

Contract and workflow: [architecture.md](architecture.md).

Example:

```bash
tarel connector check sqlserver
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel connector list`](#tarel-connector-list) | List built-in and installed connectors and their availability. |
 | [`tarel connector check`](#tarel-connector-check) | Validate a connector and its dependencies. |
 | [`tarel connector probe`](#tarel-connector-probe) | Run a bounded read-only connection probe. |
 | [`tarel connector discover`](#tarel-connector-discover) | Read schemas, tables, views, and fields from a source. |
 | [`tarel connector scaffold`](#tarel-connector-scaffold) | Create an isolated connector candidate for an agent or human. |
 | [`tarel connector sample`](#tarel-connector-sample) | Explicitly read a bounded sample from one object. |
 | [`tarel connector profile`](#tarel-connector-profile) | Read bounded aggregate column profiles from one object. |

### tarel connector list

List built-in and installed connectors and their availability.

**Syntax**

```text
tarel connector list [-h] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Availability check, probe, canonical catalog, bounded sample/profile, or scaffold location according to the verb. Samples are ephemeral command output.

CLI entry point and delegated output renderers: [src/tarel/cli/connector.py](../src/tarel/cli/connector.py).

### tarel connector check

Validate a connector and its dependencies.

**Syntax**

```text
tarel connector check [-h] [--format {text,json}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Connector name, for example sqlserver. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Availability check, probe, canonical catalog, bounded sample/profile, or scaffold location according to the verb. Samples are ephemeral command output.

CLI entry point and delegated output renderers: [src/tarel/cli/connector.py](../src/tarel/cli/connector.py).

### tarel connector probe

Run a bounded read-only connection probe.

**Syntax**

```text
tarel connector probe [-h] [--config CONFIG] [--database DATABASE] [--format {text,json}]
                             name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Connector name, for example sqlserver. |
| `--config` | Path | optional | not set | Private TOML configuration file. |
| `--database` | text | optional | not set | Override the configured database. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Availability check, probe, canonical catalog, bounded sample/profile, or scaffold location according to the verb. Samples are ephemeral command output.

CLI entry point and delegated output renderers: [src/tarel/cli/connector.py](../src/tarel/cli/connector.py).

### tarel connector discover

Read schemas, tables, views, and fields from a source.

**Syntax**

```text
tarel connector discover [-h] [--config CONFIG] [--database DATABASE] [--namespace NAMESPACE]
                                [--format {text,json}]
                                name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Connector name, for example sqlserver. |
| `--config` | Path | optional | not set | Private TOML configuration file. |
| `--database` | text | optional | not set | Override the configured database. |
| `--namespace, --schema` | text | optional | not set | Limit discovery to one namespace or database schema. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Availability check, probe, canonical catalog, bounded sample/profile, or scaffold location according to the verb. Samples are ephemeral command output.

CLI entry point and delegated output renderers: [src/tarel/cli/connector.py](../src/tarel/cli/connector.py).

### tarel connector scaffold

Create an isolated connector candidate for an agent or human.

Produces CONNECTOR_TASK.md, an adapter package skeleton, a manifest, and reference notes. Implement probe/discover, test, review, and install the package before its entry point becomes available.

**Syntax**

```text
tarel connector scaffold [-h] [--output OUTPUT] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | New connector name, for example postgres. |
| `--output` | Path | optional | not set | Target directory (default: connector name). |

**Result:** Availability check, probe, canonical catalog, bounded sample/profile, or scaffold location according to the verb. Samples are ephemeral command output.

CLI entry point and delegated output renderers: [src/tarel/cli/connector.py](../src/tarel/cli/connector.py).

### tarel connector sample

Explicitly read a bounded sample from one object.

**Syntax**

```text
tarel connector sample [-h] --config CONFIG [--database DATABASE] --namespace NAMESPACE
                              --object OBJECT_NAME [--limit LIMIT] [--format {text,json}]
                              name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Connector name, for example sqlserver. |
| `--config` | Path | required | not set | Private TOML configuration. |
| `--database` | text | optional | not set | Override the configured database. |
| `--namespace, --schema` | text | required | not set | Namespace/schema filter. |
| `--object` | text | required | not set | Object name within the selected namespace. |
| `--limit` | int | optional | `3` | Maximum number of items for this operation. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Availability check, probe, canonical catalog, bounded sample/profile, or scaffold location according to the verb. Samples are ephemeral command output.

CLI entry point and delegated output renderers: [src/tarel/cli/connector.py](../src/tarel/cli/connector.py).

### tarel connector profile

Read bounded aggregate column profiles from one object.

**Syntax**

```text
tarel connector profile [-h] --config CONFIG [--database DATABASE] --namespace NAMESPACE
                               --object OBJECT_NAME [--row-limit ROW_LIMIT]
                               [--small-domain-limit SMALL_DOMAIN_LIMIT] [--include-values]
                               [--format {text,json}]
                               name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Connector name, for example sqlserver. |
| `--config` | Path | required | not set | Private TOML configuration. |
| `--database` | text | optional | not set | Override the configured database. |
| `--namespace, --schema` | text | required | not set | Namespace/schema filter. |
| `--object` | text | required | not set | Object name within the selected namespace. |
| `--row-limit` | int | optional | `10000` | Bound on source rows examined. |
| `--small-domain-limit` | int | optional | `20` | Maximum small-domain cardinality. |
| `--include-values` | flag | optional | `False` | Explicitly allow values for complete small domains in this ephemeral result. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Availability check, probe, canonical catalog, bounded sample/profile, or scaffold location according to the verb. Samples are ephemeral command output.

CLI entry point and delegated output renderers: [src/tarel/cli/connector.py](../src/tarel/cli/connector.py).

## knowledge

**Annotation documents.** Attach scoped business documentation for annotation tasks.

Add stores a knowledge document; list/show/resolve inspect documents or their resolved scope. Annotation must explicitly request scoped or named knowledge.

Contract and workflow: [sdk.md](#python-sdk).

Example:

```bash
tarel knowledge list
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel knowledge add`](#tarel-knowledge-add) | Import one local reference document into private TAREL state. |
 | [`tarel knowledge list`](#tarel-knowledge-list) | List registered knowledge without printing its content. |
 | [`tarel knowledge show`](#tarel-knowledge-show) | Show one registered document and its content. |
 | [`tarel knowledge resolve`](#tarel-knowledge-resolve) | Preview the exact bounded knowledge context for one object. |

### tarel knowledge add

Import one local reference document into private TAREL state.

**Syntax**

```text
tarel knowledge add [-h] --scope SCOPE [--title TITLE] [--state {draft,validated}]
                           [--workspace WORKSPACE] [--replace] [--format {text,json}]
                           id path
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `id` | text | required | not set | Artifact identifier. |
| `path` | Path | required | not set | Local input/output path for this command. |
| `--scope` | text | required | not set | global, system:NAME, graph:NAME, schema:GRAPH:NAMESPACE, or object:GRAPH:OBJECT |
| `--title` | text | optional | not set | Document title. |
| `--state` | text; `draft`, `validated` | optional | `draft` | Selected review state. |
| `--workspace` | text | optional | not set | Validate a system scope. |
| `--replace` | flag | optional | `False` | Replace an existing named definition/document where supported. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Knowledge document metadata/content, a document listing, or resolved scoped documents. Inspect omissions when a document budget applies.

CLI entry point and delegated output renderers: [src/tarel/cli/knowledge.py](../src/tarel/cli/knowledge.py).

### tarel knowledge list

List registered knowledge without printing its content.

**Syntax**

```text
tarel knowledge list [-h] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Knowledge document metadata/content, a document listing, or resolved scoped documents. Inspect omissions when a document budget applies.

CLI entry point and delegated output renderers: [src/tarel/cli/knowledge.py](../src/tarel/cli/knowledge.py).

### tarel knowledge show

Show one registered document and its content.

**Syntax**

```text
tarel knowledge show [-h] [--format {text,json}] id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `id` | text | required | not set | Artifact identifier. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Knowledge document metadata/content, a document listing, or resolved scoped documents. Inspect omissions when a document budget applies.

CLI entry point and delegated output renderers: [src/tarel/cli/knowledge.py](../src/tarel/cli/knowledge.py).

### tarel knowledge resolve

Preview the exact bounded knowledge context for one object.

**Syntax**

```text
tarel knowledge resolve [-h] [--workspace WORKSPACE] [--mode {none,scoped}]
                               [--document DOCUMENTS] [--max-characters MAX_CHARACTERS]
                               [--format {text,json}]
                               graph object
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `object` | text | required | not set | Object reference. |
| `--workspace` | text | optional | not set | Workspace identifier or mode switch; see the parameter syntax. |
| `--mode` | text; `none`, `scoped` | optional | `scoped` | Mode for this command; allowed values are listed separately. |
| `--document` | text | optional; repeatable | not set | Knowledge document selection. |
| `--max-characters` | int | optional | `12000` | Character budget; not a tokenizer-based token limit. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Knowledge document metadata/content, a document listing, or resolved scoped documents. Inspect omissions when a document budget applies.

CLI entry point and delegated output renderers: [src/tarel/cli/knowledge.py](../src/tarel/cli/knowledge.py).

## provider

**Model providers.** Configure an optional structured-generation endpoint or create an adapter candidate.

Configure stores a private profile. Test makes a model request. Scaffold creates inactive adapter source files. A profile using an existing OpenAI-compatible adapter usually needs configuration rather than a new adapter implementation.

Contract and workflow: [architecture.md](architecture.md).

Example:

```bash
tarel provider list
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel provider list`](#tarel-provider-list) | List supported providers. |
 | [`tarel provider check`](#tarel-provider-check) | Show redacted provider configuration status. |
 | [`tarel provider configure`](#tarel-provider-configure) | Store provider configuration in the private user config. |
 | [`tarel provider test`](#tarel-provider-test) | Make one small structured-generation provider request. |
 | [`tarel provider scaffold`](#tarel-provider-scaffold) | Create an isolated provider-adapter candidate for review. |

### tarel provider list

List supported providers.

**Syntax**

```text
tarel provider list [-h] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Provider list/check, configured-profile acknowledgement, structured test result, or scaffold location. Configuration is private rather than graph metadata.

CLI entry point and delegated output renderers: [src/tarel/cli/provider.py](../src/tarel/cli/provider.py).

### tarel provider check

Show redacted provider configuration status.

**Syntax**

```text
tarel provider check [-h] [--format {text,json}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Provider list/check, configured-profile acknowledgement, structured test result, or scaffold location. Configuration is private rather than graph metadata.

CLI entry point and delegated output renderers: [src/tarel/cli/provider.py](../src/tarel/cli/provider.py).

### tarel provider configure

Store provider configuration in the private user config.

**Syntax**

```text
tarel provider configure [-h] [--adapter ADAPTER] [--from-env | --no-api-key] [--model MODEL]
                                [--base-url BASE_URL]
                                [--reasoning-effort {none,minimal,low,medium,high,xhigh}]
                                [--structured-mode {json_schema,tool}]
                                name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--adapter` | text | optional | not set | Adapter: openrouter, openai-compatible, or an installed tarel.providers entry point. |
| `--from-env` | flag | optional | `False` | Read the API key from a supported provider environment variable. |
| `--no-api-key` | flag | optional | `False` | Configure an unauthenticated endpoint, normally a loopback server. |
| `--model` | text | optional | not set | Default provider model. |
| `--base-url` | text | optional | not set | Provider API base URL. |
| `--reasoning-effort` | text; `none`, `minimal`, `low`, `medium`, `high`, `xhigh` | optional | not set | Default reasoning mode for this provider profile. |
| `--structured-mode` | text; `json_schema`, `tool` | optional | not set | Structured-output mechanism for OpenAI-compatible endpoints. |

Mutually exclusive: `--from-env`, `--no-api-key`.

**Result:** Provider list/check, configured-profile acknowledgement, structured test result, or scaffold location. Configuration is private rather than graph metadata.

CLI entry point and delegated output renderers: [src/tarel/cli/provider.py](../src/tarel/cli/provider.py).

### tarel provider test

Make one small structured-generation provider request.

**Syntax**

```text
tarel provider test [-h] [--timeout TIMEOUT] [--format {text,json}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--timeout` | float | optional | `120.0` | Timeout in seconds. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Provider list/check, configured-profile acknowledgement, structured test result, or scaffold location. Configuration is private rather than graph metadata.

CLI entry point and delegated output renderers: [src/tarel/cli/provider.py](../src/tarel/cli/provider.py).

### tarel provider scaffold

Create an isolated provider-adapter candidate for review.

Produces PROVIDER_TASK.md and an inactive package skeleton implementing StructuredProvider. Existing OpenAI-compatible endpoints can often use provider configure --adapter openai-compatible instead.

**Syntax**

```text
tarel provider scaffold [-h] [--output OUTPUT] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--output` | Path | optional | not set | Target directory (default: .tarel/providers/NAME). |

**Result:** Provider list/check, configured-profile acknowledgement, structured test result, or scaffold location. Configuration is private rather than graph metadata.

CLI entry point and delegated output renderers: [src/tarel/cli/provider.py](../src/tarel/cli/provider.py).

## model

**Local retrieval models.** Manage optional local embedding and reranker model artifacts.

Download fetches a model artifact; status reports availability. Installation does not download weights. Model selection is separate.

Contract and workflow: [local-retrieval.md](contracts.md#local-retrieval).

Example:

```bash
tarel model status --format json
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel model download`](#tarel-model-download) | Download and verify the recommended local embedding model. |
 | [`tarel model status`](#tarel-model-status) | Check the recommended model path and checksum. |

### tarel model download

Download and verify the recommended local embedding model.

**Syntax**

```text
tarel model download [-h] [--name NAME] [--target TARGET] [--force] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--name` | text | optional | `qwen3-embedding-0.6b-q4-k-m` | Name of the resource operated on by this command; see the command purpose. |
| `--target` | Path | optional | not set | Target object, field, or reference. |
| `--force` | flag | optional | `False` | Allow the command-specific forced replacement. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Download/status information for a local retrieval model artifact.

CLI entry point and delegated output renderers: [src/tarel/cli/model.py](../src/tarel/cli/model.py).

### tarel model status

Check the recommended model path and checksum.

**Syntax**

```text
tarel model status [-h] [--name NAME] [--model MODEL_PATH] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--name` | text | optional | `qwen3-embedding-0.6b-q4-k-m` | Name of the resource operated on by this command; see the command purpose. |
| `--model` | Path | optional | not set | Local embedding model path. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Download/status information for a local retrieval model artifact.

CLI entry point and delegated output renderers: [src/tarel/cli/model.py](../src/tarel/cli/model.py).

## index

**Retrieval indexes.** Prepare and inspect rebuildable local retrieval indexes for a graph or workspace.

Build updates only changed retrieval documents using the selected local or HTTP embedding model. A workspace build processes a bounded graph batch. Resume reuses a compatible checkpoint; model changes require full re-embedding, including a replacement at the recorded path. Check ready and remaining_graphs before searching.

Contract and workflow: [local-retrieval.md](contracts.md#local-retrieval).

Example:

```bash
tarel index status --workspace enterprise
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel index build`](#tarel-index-build) | Embed safe graph metadata into a rebuildable local SQLite index. |
 | [`tarel index status`](#tarel-index-status) | Inspect one retrieval index. |

### tarel index build

Embed safe graph metadata into a rebuildable local SQLite index.

Embeds only what changed. An older index keeps vectors of documents within 256 tokens and re-embeds longer ones; see the embedding input contract. A document over 2048 tokens embeds its beginning and is listed in truncated_documents; its fields stay whole.

**Syntax**

```text
tarel index build [-h] [--workspace WORKSPACE] [--system SYSTEMS] [--graph GRAPHS]
                         [--area AREAS] [--schema SCHEMAS] [--zone ZONES] [--model MODEL_PATH]
                         [--batch-size BATCH_SIZE] [--threads N_THREADS] [--max-graphs MAX_GRAPHS]
                         [--resume]
                         [--annotation-state {draft,validated,rejected,deferred,review_required}]
                         [--validated-only] [--format {text,json}]
                         [name]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | optional; optional positional | not set | Local graph name. |
| `--workspace` | text | optional | not set | Build pending graph indexes in a workspace. |
| `--system` | text | optional; repeatable | not set | Include a system; repeat to include multiple systems. |
| `--graph` | text | optional; repeatable | not set | Limit the scope to a graph; repeat to include multiple graphs. |
| `--area` | text | optional; repeatable | not set | Limit to an area (NAME or SYSTEM:NAME); repeat for a union. |
| `--schema` | text | optional; repeatable | not set | Limit to a schema as GRAPH:NAMESPACE; repeat for a union. |
| `--zone` | text | optional; repeatable | not set | Limit to a zone (NAME or SYSTEM:NAME); repeat for a union. |
| `--model` | Path | optional | not set | Local embedding model path. |
| `--batch-size` | int | optional | `16` | Documents per index progress batch; llama.cpp decodes each document separately. |
| `--threads` | int | optional | not set | Local model thread count. |
| `--max-graphs` | int | optional | `8` | Maximum pending workspace graphs to update in one run (default: 8). |
| `--resume` | flag | optional | `False` | Checkpoint completed embedding batches and resume a matching interrupted build. |
| `--annotation-state` | text; `draft`, `validated`, `rejected`, `deferred`, `review_required` | optional; repeatable | not set | Include semantic annotations in one or more review states. |
| `--validated-only` | flag | optional | `False` | Include only human-validated semantic annotations. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Index build/status information, including checkpoint compatibility when applicable.

CLI entry point and delegated output renderers: [src/tarel/cli/index.py](../src/tarel/cli/index.py).

### tarel index status

Inspect one retrieval index.

ready does not mean the vectors were verified: read embedding_input.state as well. A workspace status counts each graph separately, so a partial index is not reported as workspace coverage.

**Syntax**

```text
tarel index status [-h] [--workspace WORKSPACE] [--system SYSTEMS] [--graph GRAPHS]
                          [--area AREAS] [--schema SCHEMAS] [--zone ZONES]
                          [--annotation-state {draft,validated,rejected,deferred,review_required}]
                          [--validated-only] [--format {text,json}]
                          [name]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | optional; optional positional | not set | Local graph name. |
| `--workspace` | text | optional | not set | Inspect index coverage for a workspace. |
| `--system` | text | optional; repeatable | not set | Include a system; repeat to include multiple systems. |
| `--graph` | text | optional; repeatable | not set | Limit the scope to a graph; repeat to include multiple graphs. |
| `--area` | text | optional; repeatable | not set | Limit to an area (NAME or SYSTEM:NAME); repeat for a union. |
| `--schema` | text | optional; repeatable | not set | Limit to a schema as GRAPH:NAMESPACE; repeat for a union. |
| `--zone` | text | optional; repeatable | not set | Limit to a zone (NAME or SYSTEM:NAME); repeat for a union. |
| `--annotation-state` | text; `draft`, `validated`, `rejected`, `deferred`, `review_required` | optional; repeatable | not set | Include semantic annotations in one or more review states. |
| `--validated-only` | flag | optional | `False` | Include only human-validated semantic annotations. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Index build/status information, including checkpoint compatibility when applicable.

CLI entry point and delegated output renderers: [src/tarel/cli/index.py](../src/tarel/cli/index.py).

## graph

**Source graphs.** Build, refresh, annotate, and inspect the technical and semantic snapshot of a source.

Build/import/refresh/annotate persist graph knowledge. Selective reads may bootstrap or rebuild a local cache; authoritative graph JSON remains the source of truth. The selective graph cache differs from the retrieval index.

Contract and workflow: [graph-storage.md](contracts.md#graph-storage-and-selective-reads).

Example:

```bash
tarel graph objects warehouse --limit 10 --format json
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel graph header`](#tarel-graph-header) | Selective graph header; graph.json stays authoritative. |
 | [`tarel graph objects`](#tarel-graph-objects) | Selective graph objects; graph.json stays authoritative. |
 | [`tarel graph slice`](#tarel-graph-slice) | Selective graph slice; graph.json stays authoritative. |
 | [`tarel graph rebuild-index`](#tarel-graph-rebuild-index) | Selective graph rebuild-index; graph.json stays authoritative. |
 | [`tarel graph build`](#tarel-graph-build) | Discover a source and persist its technical graph. |
 | [`tarel graph refresh`](#tarel-graph-refresh) | Rediscover technical structure while preserving reviewed knowledge. |
 | [`tarel graph import-catalog`](#tarel-graph-import-catalog) | Persist an already observed catalog without running discovery again. |
 | [`tarel graph list`](#tarel-graph-list) | List local graphs. |
 | [`tarel graph show`](#tarel-graph-show) | Show one local graph. |
 | [`tarel graph annotate`](#tarel-graph-annotate) | Run provider-backed annotation tasks, optionally in parallel. |

### tarel graph header

Selective graph header; graph.json stays authoritative.

**Syntax**

```text
tarel graph header [-h] [--format {text,json}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** A graph summary for build/show, change information for refresh, annotation progress/summary, or selective header/page/slice records. Selective results carry complete-source identity and read accounting.

CLI entry point and delegated output renderers: [src/tarel/cli/graph.py](../src/tarel/cli/graph.py).

### tarel graph objects

Selective graph objects; graph.json stays authoritative.

**Syntax**

```text
tarel graph objects [-h] [--format {text,json}] [--object OBJECT_IDS] [--namespace NAMESPACE]
                           [--revision REVISION] [--offset OFFSET] [--limit LIMIT]
                           name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |
| `--object` | text | optional; repeatable | not set | Object label (main.orders) or stable ID; repeatable. |
| `--namespace` | text | optional | not set | Namespace/schema filter. |
| `--revision` | text | optional | not set | Revision pin for this operation. |
| `--offset` | int | optional | `0` | Pagination starting offset. |
| `--limit` | int | optional | `100` | Maximum number of items for this operation. |

**Result:** A graph summary for build/show, change information for refresh, annotation progress/summary, or selective header/page/slice records. Selective results carry complete-source identity and read accounting.

CLI entry point and delegated output renderers: [src/tarel/cli/graph.py](../src/tarel/cli/graph.py).

### tarel graph slice

Selective graph slice; graph.json stays authoritative.

Use exact object IDs from graph objects. The returned slice is a subset: preserve the complete source revision from its header rather than persisting the slice as the original graph.

**Syntax**

```text
tarel graph slice [-h] [--format {text,json}] --object OBJECT_IDS [--namespace NAMESPACE]
                         [--revision REVISION]
                         name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |
| `--object` | text | required; repeatable | not set | Object label (main.orders) or stable ID; repeatable. |
| `--namespace` | text | optional | not set | Namespace/schema filter. |
| `--revision` | text | optional | not set | Revision pin for this operation. |

**Result:** A graph summary for build/show, change information for refresh, annotation progress/summary, or selective header/page/slice records. Selective results carry complete-source identity and read accounting.

CLI entry point and delegated output renderers: [src/tarel/cli/graph.py](../src/tarel/cli/graph.py).

### tarel graph rebuild-index

Selective graph rebuild-index; graph.json stays authoritative.

**Syntax**

```text
tarel graph rebuild-index [-h] [--format {text,json}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** A graph summary for build/show, change information for refresh, annotation progress/summary, or selective header/page/slice records. Selective results carry complete-source identity and read accounting.

CLI entry point and delegated output renderers: [src/tarel/cli/graph.py](../src/tarel/cli/graph.py).

### tarel graph build

Discover a source and persist its technical graph.

**Syntax**

```text
tarel graph build [-h] --connector CONNECTOR [--config CONFIG] [--database DATABASE]
                         [--namespace NAMESPACE] [--format {text,json}]
                         name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Local graph name. |
| `--connector` | text | required | not set | Source connector name. |
| `--config` | Path | optional | not set | Private connector configuration. |
| `--database` | text | optional | not set | Override the configured database. |
| `--namespace, --schema` | text | optional | not set | Namespace/schema filter. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** A graph summary for build/show, change information for refresh, annotation progress/summary, or selective header/page/slice records. Selective results carry complete-source identity and read accounting.

CLI entry point and delegated output renderers: [src/tarel/cli/graph.py](../src/tarel/cli/graph.py).

### tarel graph refresh

Rediscover technical structure while preserving reviewed knowledge.

**Syntax**

```text
tarel graph refresh [-h] [--config CONFIG] [--namespace NAMESPACE] [--annotate-new PROVIDER]
                           [--annotation-workers ANNOTATION_WORKERS]
                           [--annotation-model ANNOTATION_MODEL]
                           [--annotation-timeout ANNOTATION_TIMEOUT] [--format {text,json}]
                           name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Existing local graph name. |
| `--config` | Path | optional | not set | Private connector configuration. |
| `--namespace, --schema` | text | optional | not set | Namespace/schema filter. |
| `--annotate-new` | text | optional | not set | Annotate only object and field gaps introduced by this refresh. |
| `--annotation-workers` | int | optional | `1` | Parallel provider requests for newly introduced annotation gaps. |
| `--annotation-model` | text | optional | not set | Optional model override for the delta annotation batch. |
| `--annotation-timeout` | float | optional | `120.0` | Provider timeout in seconds for delta annotation requests. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** A graph summary for build/show, change information for refresh, annotation progress/summary, or selective header/page/slice records. Selective results carry complete-source identity and read accounting.

CLI entry point and delegated output renderers: [src/tarel/cli/graph.py](../src/tarel/cli/graph.py).

### tarel graph import-catalog

Persist an already observed catalog without running discovery again.

The input is a canonical CatalogResult JSON document produced by a caller/connector. It is not arbitrary catalog JSON, CSV, or a source connection configuration.

**Syntax**

```text
tarel graph import-catalog [-h] --source SOURCE [--format {text,json}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | New local graph name. |
| `--source` | Path | required | not set | CatalogResult JSON produced by a trusted caller or connector discovery. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** A graph summary for build/show, change information for refresh, annotation progress/summary, or selective header/page/slice records. Selective results carry complete-source identity and read accounting.

CLI entry point and delegated output renderers: [src/tarel/cli/graph.py](../src/tarel/cli/graph.py).

### tarel graph list

List local graphs.

**Syntax**

```text
tarel graph list [-h] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** A graph summary for build/show, change information for refresh, annotation progress/summary, or selective header/page/slice records. Selective results carry complete-source identity and read accounting.

CLI entry point and delegated output renderers: [src/tarel/cli/graph.py](../src/tarel/cli/graph.py).

### tarel graph show

Show one local graph.

**Syntax**

```text
tarel graph show [-h] [--format {text,json}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** A graph summary for build/show, change information for refresh, annotation progress/summary, or selective header/page/slice records. Selective results carry complete-source identity and read accounting.

CLI entry point and delegated output renderers: [src/tarel/cli/graph.py](../src/tarel/cli/graph.py).

### tarel graph annotate

Run provider-backed annotation tasks, optionally in parallel.

Processes eligible objects through a provider. --object is repeatable; there is no --focus option. Translate a focus to per-graph object lists in the harness. Existing annotations are skipped unless --include-annotated is selected. --workers controls this annotation runner, not the lineage runner.

**Syntax**

```text
tarel graph annotate [-h] --provider PROVIDER [--namespace NAMESPACE] [--object OBJECTS]
                            [--limit LIMIT] [--workers WORKERS] [--retry RETRY]
                            [--retry-backoff RETRY_BACKOFF] [--skip-errors]
                            [--max-errors MAX_ERRORS] [--model MODEL] [--timeout TIMEOUT]
                            [--samples SAMPLES] [--profile-rows PROFILE_ROWS]
                            [--include-small-domain-values] [--config CONFIG] [--include-annotated]
                            [--dry-run] [--knowledge {none,scoped}]
                            [--knowledge-document KNOWLEDGE_DOCUMENTS]
                            [--knowledge-workspace KNOWLEDGE_WORKSPACE]
                            [--max-knowledge-characters MAX_KNOWLEDGE_CHARACTERS]
                            [--format {text,json}]
                            name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--provider` | text | required | not set | Configured provider profile. |
| `--namespace, --schema` | text | optional | not set | Namespace/schema filter. |
| `--object` | text | optional; repeatable | not set | Selected object references. |
| `--limit` | int | optional | not set | Maximum number of items for this operation. |
| `--workers` | int | optional | `1` | Parallel worker count for this command. |
| `--retry` | int | optional | `0` | Additional retry/correction attempts. |
| `--retry-backoff` | float | optional | `2.0` | Retry backoff interval. |
| `--skip-errors` | flag | optional | `False` | Continue supported batch processing after item failures. |
| `--max-errors` | int | optional | not set | Error budget for the batch. |
| `--model` | text | optional | not set | Model override. |
| `--timeout` | float | optional | `120.0` | Timeout in seconds. |
| `--samples` | int | optional | `0` | Maximum requested sample rows; zero disables samples where supported. |
| `--profile-rows` | int | optional | `0` | Row budget for optional profiling. |
| `--include-small-domain-values` | flag | optional | `False` | Explicitly allow small-domain values in ephemeral annotation input. |
| `--config` | Path | optional | not set | Private connector configuration. |
| `--include-annotated` | flag | optional | `False` | Re-annotate complete objects instead of filling only missing annotations. |
| `--dry-run` | flag | optional | `False` | Plan/preview instead of applying this operation. |
| `--knowledge` | text; `none`, `scoped` | optional | `none` | Include no automatic documents (default) or resolve matching scopes. |
| `--knowledge-document` | text | optional; repeatable | not set | Include one document explicitly; repeat for more. |
| `--knowledge-workspace` | text | optional | not set | Workspace used to resolve system-scoped documents. |
| `--max-knowledge-characters` | int | optional | `12000` | Knowledge-document character budget. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** A graph summary for build/show, change information for refresh, annotation progress/summary, or selective header/page/slice records. Selective results carry complete-source identity and read accounting.

CLI entry point and delegated output renderers: [src/tarel/cli/graph.py](../src/tarel/cli/graph.py).

## ui

**Browser.** Explore graph/workspace structure, lineage, and reviewable knowledge.

Starts a local browser server. --edit enables explicit mutations. Opening the UI does not itself run a connector or LLM. UI display filters are not automatically context-packet constraints. --architecture-file opts an unfiltered workspace into the experimental [architecture browser](architecture-ui.md). --architecture-edit enables only sidecar edits, independently of --edit; no architecture connections become technical lineage.

Contract and workflow: [browser-workflows.md](contracts.md#browser-scope-and-review).

Example:

```bash
tarel ui --workspace enterprise --lineage sales-etl
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel ui`](#tarel-ui) | Open the optional local graph, lineage, and annotation browser. |

### tarel ui

Open the optional local graph, lineage, and annotation browser.

**Syntax**

```text
tarel ui [-h] [--workspace WORKSPACE] [--state-root STATE_ROOT] [--system SYSTEMS]
                [--graph GRAPHS] [--area AREAS] [--schema SCHEMAS] [--zone ZONES]
                [--lineage LINEAGES] [--focus FOCUSES] [--edit] [--port PORT] [--no-open]
                [--families {confirmed_only,include_candidates}]
                [--search-mode {lexical,bm25,vector,hybrid}] [--model MODEL_PATH]
                [--threads N_THREADS] [--architecture-file ARCHITECTURE_FILE] [--architecture-edit]
                [graph]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | optional; optional positional | not set | Single local graph to inspect. |
| `--workspace` | text | optional | not set | Open a workspace across one or more graphs. |
| `--state-root` | Path | optional | not set | Explicit private TAREL state root; defaults to .tarel in the current directory. |
| `--system` | text | optional; repeatable | not set | Include a system; repeat to include multiple systems. |
| `--graph` | text | optional; repeatable | not set | Limit the scope to a graph; repeat to include multiple graphs. |
| `--area` | text | optional; repeatable | not set | Limit to an area (NAME or SYSTEM:NAME); repeat for a union. |
| `--schema` | text | optional; repeatable | not set | Limit to a schema as GRAPH:NAMESPACE; repeat for a union. |
| `--zone` | text | optional; repeatable | not set | Limit to a zone (NAME or SYSTEM:NAME); repeat for a union. |
| `--lineage` | text | optional; repeatable | not set | Lineage document to include; repeat for multiple documents. |
| `--focus` | text | optional; repeatable | not set | Open one saved report or cube focus; repeat to combine focuses. |
| `--edit` | flag | optional | `False` | Allow explicit annotation, lineage, relationship, and zone changes. |
| `--port` | int | optional | `0` | Loopback port; 0 selects a free port. |
| `--no-open` | flag | optional | `False` | Do not open the browser automatically. |
| `--families` | text; `confirmed_only`, `include_candidates` | optional | not set | Family inclusion/display policy. |
| `--search-mode` | text; `lexical`, `bm25`, `vector`, `hybrid` | optional | `bm25` | Local metadata search mode; BM25 needs no model index. |
| `--model` | Path | optional | not set | Local embedding model path. |
| `--threads` | int | optional | not set | Local model thread count. |
| `--architecture-file` | Path | optional | not set | Experimental local architecture sidecar. |
| `--architecture-edit` | flag | optional | `False` | Edit architecture only, not graph annotations. |

**Result:** Local server startup information; the process serves the browser until stopped.

CLI entry point and delegated output renderers: [src/tarel/cli/ui.py](../src/tarel/cli/ui.py).

## lineage

**Static and runtime lineage.** Describe data dependencies, analyze definitions, trace upstream origins, and record observed executions.

Build consumes canonical input rather than extracting a scheduler itself. Analyze can use a provider, optional local SQLGlot, or SQLGlot with provider fallback; every path persists drafts. Next/apply supports harness-authored proposals. Runtime imports store caller observations separately from reusable static ETL definitions.

Contract and workflow: [static-lineage.md](static-lineage.md).

Example:

```bash
tarel lineage show sales-etl --view status --format json
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel lineage build`](#tarel-lineage-build) | Create or refresh lineage from a canonical input file. |
 | [`tarel lineage import-dbt`](#tarel-lineage-import-dbt) | Import declared dbt manifest v12 dependencies without SQL analysis. |
 | [`tarel lineage show`](#tarel-lineage-show) | Show the document, process, table, or coverage projection. |
 | [`tarel lineage import-runtime`](#tarel-lineage-import-runtime) | Import one immutable, sanitized runtime query run. |
 | [`tarel lineage show-runtime`](#tarel-lineage-show-runtime) | Show one sanitized runtime-lineage run. |
 | [`tarel lineage list-runtime`](#tarel-lineage-list-runtime) | List sanitized runtime-lineage runs. |
 | [`tarel lineage trace-runtime`](#tarel-lineage-trace-runtime) | Trace a successful runtime call to its graph-bound source inputs. |
 | [`tarel lineage next`](#tarel-lineage-next) | Return the next source-analysis task for the current coding agent. |
 | [`tarel lineage apply`](#tarel-lineage-apply) | Apply one coding-agent workfile as draft lineage. |
 | [`tarel lineage analyze`](#tarel-lineage-analyze) | Analyze complete definitions with a provider or optional local SQLGlot. |
 | [`tarel lineage review`](#tarel-lineage-review) | List or decide draft lineage items. |
 | [`tarel lineage find`](#tarel-lineage-find) | Find report, semantic, procedure, table, or field references. |
 | [`tarel lineage upstream`](#tarel-lineage-upstream) | Trace one reference backwards through all selected lineage documents. |
 | [`tarel lineage add-job`](#tarel-lineage-add-job) | Add a human-authored procedure or script to a manual lineage overlay. |
 | [`tarel lineage add-hop`](#tarel-lineage-add-hop) | Add a human-authored source-to-target hop through a manual job. |

### tarel lineage build

Create or refresh lineage from a canonical input file.

Requires canonical lineage input containing definitions and observations. SQL Agent order, nested procedure calls, and physical reads/writes are different evidence and must be represented accordingly.

**Syntax**

```text
tarel lineage build [-h] --source SOURCE [--format {text,json}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--source` | Path | required | not set | Input source: file, logical source, or reference as specified by this command. See its linked contract. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/cli/lineage.py](../src/tarel/cli/lineage.py).

### tarel lineage import-dbt

Import declared dbt manifest v12 dependencies without SQL analysis.

Imports model/source declarations from dbt manifest v12 through the same build/refresh path. No dbt installation, SQLGlot or provider is used. Catalog mappings are explicit; ephemeral models stay logical. This does not prove execution or column lineage. See dbt-lineage.md for capabilities, limits and tests.

**Syntax**

```text
tarel lineage import-dbt [-h] --manifest MANIFEST [--catalog-map FROM=TO]
                                [--format {text,json}]
                                name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--manifest` | Path | required | not set | Path to the dbt manifest v12 JSON artifact; read locally without running dbt. |
| `--catalog-map` | text | optional; repeatable | `[]` | Explicit database/catalog name mapping; repeat for multiple catalogs. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/cli/lineage.py](../src/tarel/cli/lineage.py).

### tarel lineage show

Show the document, process, table, or coverage projection.

**Syntax**

```text
tarel lineage show [-h] [--view {document,process,status,tables}] [--format {text,json}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--view` | text; `document`, `process`, `status`, `tables` | optional | `document` | Output projection. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/cli/lineage.py](../src/tarel/cli/lineage.py).

### tarel lineage import-runtime

Import one immutable, sanitized runtime query run.

Requires a complete runtime-lineage input with exact graph revision and resolvable inputs. Imports are create-only. Successful execution does not validate a relationship or certify the caller's metrics.

**Syntax**

```text
tarel lineage import-runtime [-h] --source SOURCE [--format {text,json}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | New local runtime-lineage name. |
| `--source` | Path | required | not set | Input source: file, logical source, or reference as specified by this command. See its linked contract. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/cli/lineage.py](../src/tarel/cli/lineage.py).

### tarel lineage show-runtime

Show one sanitized runtime-lineage run.

**Syntax**

```text
tarel lineage show-runtime [-h] [--format {text,json}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/cli/lineage.py](../src/tarel/cli/lineage.py).

### tarel lineage list-runtime

List sanitized runtime-lineage runs.

**Syntax**

```text
tarel lineage list-runtime [-h] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/cli/lineage.py](../src/tarel/cli/lineage.py).

### tarel lineage trace-runtime

Trace a successful runtime call to its graph-bound source inputs.

**Syntax**

```text
tarel lineage trace-runtime [-h] [--format {text,json}] name call_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `call_id` | text | required | not set | Recorded runtime call identifier. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/cli/lineage.py](../src/tarel/cli/lineage.py).

### tarel lineage next

Return the next source-analysis task for the current coding agent.

**Syntax**

```text
tarel lineage next [-h] --source SOURCE name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--source` | Path | required | not set | Input source: file, logical source, or reference as specified by this command. See its linked contract. |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/cli/lineage.py](../src/tarel/cli/lineage.py).

### tarel lineage apply

Apply one coding-agent workfile as draft lineage.

**Syntax**

```text
tarel lineage apply [-h] --source SOURCE --input INPUT [--format {text,json}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--source` | Path | required | not set | Input source: file, logical source, or reference as specified by this command. See its linked contract. |
| `--input` | text | required | not set | Proposal JSON file or '-' for stdin. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/cli/lineage.py](../src/tarel/cli/lineage.py).

### tarel lineage analyze

Analyze complete definitions with a provider or optional local SQLGlot.

The sqlglot strategy is local and provider-free. Auto runs SQLGlot first and sends each unresolved definition in full to the provider. Provider requests remain sequential per definition, followed by --review-passes audit requests; this is not a provider batch API. Compatible provider-cache entries can be reused. Failed work remains visible and every accepted result stays draft.

**Syntax**

```text
tarel lineage analyze [-h] --source SOURCE [--analyzer {auto,llm,sqlglot}]
                             [--provider PROVIDER] [--dialect DIALECT] [--model MODEL]
                             [--timeout TIMEOUT] [--retry RETRY] [--review-passes REVIEW_PASSES]
                             [--limit LIMIT] [--definition DEFINITIONS]
                             [--max-output-tokens MAX_OUTPUT_TOKENS]
                             [--reasoning-effort {none,minimal,low,medium,high,xhigh}]
                             [--format {text,json}]
                             name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--source` | Path | required | not set | Input source: file, logical source, or reference as specified by this command. See its linked contract. |
| `--analyzer` | text; `auto`, `llm`, `sqlglot` | optional | `llm` | Use the provider, optional SQLGlot, or SQLGlot with provider fallback. |
| `--provider` | text | optional | not set | Configured provider profile. |
| `--dialect` | text | optional | not set | Explicit SQLGlot dialect for definitions whose language is ambiguous. |
| `--model` | text | optional | not set | Model override. |
| `--timeout` | float | optional | `180.0` | Timeout in seconds. |
| `--retry` | int | optional | `1` | Additional retry/correction attempts. |
| `--review-passes` | int | optional | `1` | Additional provider audit passes. |
| `--limit` | int | optional | not set | Maximum number of items for this operation. |
| `--definition` | text | optional; repeatable | not set | Analyze only this exact definition ID, external ID, name, or qualified name. |
| `--max-output-tokens` | int | optional | not set | Provider output-token bound. |
| `--reasoning-effort` | text; `none`, `minimal`, `low`, `medium`, `high`, `xhigh` | optional | not set | Provider reasoning-effort hint. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/cli/lineage.py](../src/tarel/cli/lineage.py).

### tarel lineage review

List or decide draft lineage items.

**Syntax**

```text
tarel lineage review [-h] [--decision {validate,reject}] [--reason REASON]
                            [--state {draft,review_required,validated,rejected}]
                            [--format {text,json}]
                            name [item_id]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `item_id` | text | optional; optional positional | not set | Item identifier; omit only where listing is supported. |
| `--decision` | text; `validate`, `reject` | optional | not set | Review decision. |
| `--reason` | text | optional | not set | Human-readable reason for the decision or mutation. |
| `--state` | text; `draft`, `review_required`, `validated`, `rejected` | optional; repeatable | not set | Selected review state. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/cli/lineage.py](../src/tarel/cli/lineage.py).

### tarel lineage find

Find report, semantic, procedure, table, or field references.

**Syntax**

```text
tarel lineage find [-h] --lineage LINEAGES [--graph GRAPHS] [--limit LIMIT]
                          [--mode {lexical,bm25,vector,hybrid}] [--model MODEL_PATH]
                          [--threads N_THREADS] [--format {text,json}]
                          query
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `query` | text | required | not set | Search or analytical question text. |
| `--lineage` | text | required; repeatable | not set | Lineage documents to include. |
| `--graph` | text | optional; repeatable | not set | Graph names to include. |
| `--limit` | int | optional | `20` | Maximum number of items for this operation. |
| `--mode` | text; `lexical`, `bm25`, `vector`, `hybrid` | optional | `lexical` | Mode for this command; allowed values are listed separately. |
| `--model` | Path | optional | not set | Local embedding model path. |
| `--threads` | int | optional | not set | Local model thread count. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/cli/lineage.py](../src/tarel/cli/lineage.py).

### tarel lineage upstream

Trace one reference backwards through all selected lineage documents.

Same-named objects only stop a trace that depends on them. They are settled only by identity the referring document declares, and the trace warns when that happened; otherwise the error lists the candidates.

**Syntax**

```text
tarel lineage upstream [-h] --lineage LINEAGES [--graph GRAPHS] [--max-hops MAX_HOPS]
                              [--state {draft,review_required,validated}] [--format {text,json}]
                              reference
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `reference` | text | required | not set | Exact reference to inspect or trace. |
| `--lineage` | text | required; repeatable | not set | Lineage documents to include. |
| `--graph` | text | optional; repeatable | not set | Graph names to include. |
| `--max-hops` | int | optional | `12` | Maximum traversal/expansion depth. |
| `--state` | text; `draft`, `review_required`, `validated` | optional; repeatable | not set | Selected review state. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/cli/lineage.py](../src/tarel/cli/lineage.py).

### tarel lineage add-job

Add a human-authored procedure or script to a manual lineage overlay.

**Syntax**

```text
tarel lineage add-job [-h] --kind {procedure,script} --job-name JOB_NAME --qualified-name
                             QUALIFIED_NAME --language LANGUAGE --source-reference SOURCE_REFERENCE
                             --description DESCRIPTION [--format {text,json}]
                             name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Manual lineage overlay name; created if missing. |
| `--kind` | text; `procedure`, `script` | required | not set | Artifact/operation kind. |
| `--job-name` | text | required | not set | Job display name. |
| `--qualified-name` | text | required | not set | Fully qualified definition name. |
| `--language` | text | required | not set | Source language. |
| `--source-reference` | text | required | not set | Reference to the source evidence. |
| `--description` | text | required | not set | Description stored with this artifact. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/cli/lineage.py](../src/tarel/cli/lineage.py).

### tarel lineage add-hop

Add a human-authored source-to-target hop through a manual job.

**Syntax**

```text
tarel lineage add-hop [-h] --job JOB --source SOURCE --target TARGET --operation
                             {delete,insert,merge,select_into,truncate,update}
                             [--role {audit,business_data,control,deduplication,filter,lookup,unknown}]
                             --evidence-reference EVIDENCE_REFERENCE --reason REASON
                             [--line-start LINE_START] [--line-end LINE_END] [--format {text,json}]
                             name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Existing manual lineage overlay name. |
| `--job` | text | required | not set | Job ID or qualified name. |
| `--source` | text | required | not set | Input source: file, logical source, or reference as specified by this command. See its linked contract. |
| `--target` | text | required | not set | Target object, field, or reference. |
| `--operation` | text; `delete`, `insert`, `merge`, `select_into`, `truncate`, `update` | required | not set | Logical operation kind. |
| `--role` | text; `audit`, `business_data`, `control`, `deduplication`, `filter`, `lookup`, `unknown` | optional | `business_data` | Semantic role. |
| `--evidence-reference` | text | required | not set | Evidence identifier/reference. |
| `--reason` | text | required | not set | Human-readable reason for the decision or mutation. |
| `--line-start` | int | optional | `1` | First evidence line. |
| `--line-end` | int | optional | `1` | Last evidence line. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/cli/lineage.py](../src/tarel/cli/lineage.py).

## semantic

**Imported semantic models.** Import and inspect external semantic definitions and their bindings to graph objects.

Import stores a semantic sidecar; edits preserve the original source snapshot through the supported overlay behavior. Imported semantics do not automatically become approved TAREL annotations.

Contract and workflow: [semantic-imports.md](contracts.md#semantic-model-imports).

Example:

```bash
tarel semantic list
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel semantic import`](#tarel-semantic-import) | Import a semantic model and bind supported constructs to one TAREL graph. |
 | [`tarel semantic list`](#tarel-semantic-list) | List saved semantic imports. |
 | [`tarel semantic show`](#tarel-semantic-show) | Show one normalized semantic import. |
 | [`tarel semantic edit`](#tarel-semantic-edit) | Overlay description or synonym corrections without changing the source snapshot. |

### tarel semantic import

Import a semantic model and bind supported constructs to one TAREL graph.

**Syntax**

```text
tarel semantic import [-h] --graph GRAPH --source SOURCE
                             [--source-format {ossie,apache-ossie,sml,cube,cube-yaml}] [--replace]
                             [--format {text,json}]
                             name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `--source` | Path | required | not set | Input source: file, logical source, or reference as specified by this command. See its linked contract. |
| `--source-format` | text; `ossie`, `apache-ossie`, `sml`, `cube`, `cube-yaml` | optional | `ossie` | Semantic input format. |
| `--replace` | flag | optional | `False` | Replace an existing named definition/document where supported. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Imported semantic document, listing, or edit result. Bindings and diagnostics preserve source identity.

CLI entry point and delegated output renderers: [src/tarel/cli/semantic.py](../src/tarel/cli/semantic.py).

### tarel semantic list

List saved semantic imports.

**Syntax**

```text
tarel semantic list [-h] [--graph GRAPH] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--graph` | text | optional | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Imported semantic document, listing, or edit result. Bindings and diagnostics preserve source identity.

CLI entry point and delegated output renderers: [src/tarel/cli/semantic.py](../src/tarel/cli/semantic.py).

### tarel semantic show

Show one normalized semantic import.

**Syntax**

```text
tarel semantic show [-h] [--include-source] [--format {text,json}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--include-source` | flag | optional | `False` | Include supported source details in output. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Imported semantic document, listing, or edit result. Bindings and diagnostics preserve source identity.

CLI entry point and delegated output renderers: [src/tarel/cli/semantic.py](../src/tarel/cli/semantic.py).

### tarel semantic edit

Overlay description or synonym corrections without changing the source snapshot.

**Syntax**

```text
tarel semantic edit [-h] --input INPUT --reason REASON [--revision REVISION]
                           [--format {text,json}]
                           name target_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `target_id` | text | required | not set | Target identifier. |
| `--input` | text | required | not set | Patch JSON file or '-' for stdin. |
| `--reason` | text | required | not set | Human-readable reason for the decision or mutation. |
| `--revision` | text | optional | not set | Revision pin for this operation. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Imported semantic document, listing, or edit result. Bindings and diagnostics preserve source identity.

CLI entry point and delegated output renderers: [src/tarel/cli/semantic.py](../src/tarel/cli/semantic.py).

## entity

**Entity-resolution candidates.** Inspect and review evidence that different representations may denote the same entity.

Imports and reviews persist entity artifacts. Candidate retrieval is separate from trusted physical joins. Entity resolution is not an automatic merge of source records.

Contract and workflow: [entity-resolution-candidates.md](contracts.md#entity-resolution-candidates).

Example:

```bash
tarel entity --help
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel entity import`](#tarel-entity-import) | Import one sanitized, graph-bound candidate JSON document. |
 | [`tarel entity list`](#tarel-entity-list) | List stored candidates, including rejected review history. |
 | [`tarel entity show`](#tarel-entity-show) | Show one stored candidate. |
 | [`tarel entity find`](#tarel-entity-find) | Offer current confirmed rules or clearly labelled hypotheses. |
 | [`tarel entity resolve`](#tarel-entity-resolve) | Resolve one record key through protected same-object alias groups. |
 | [`tarel entity review`](#tarel-entity-review) | Record one explicit human approval or rejection. |

### tarel entity import

Import one sanitized, graph-bound candidate JSON document.

**Syntax**

```text
tarel entity import [-h] --source SOURCE [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--source` | text | required | not set | JSON path or '-' for stdin. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Sanitized entity candidate records, resolution results, or a review result. Candidate state and effective usage remain visible.

CLI entry point and delegated output renderers: [src/tarel/cli/entity.py](../src/tarel/cli/entity.py).

### tarel entity list

List stored candidates, including rejected review history.

**Syntax**

```text
tarel entity list [-h] [--graph GRAPH] [--state {candidate,reviewed,rejected}]
                         [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--graph` | text | optional | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `--state` | text; `candidate`, `reviewed`, `rejected` | optional; repeatable | not set | Review-state selection. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Sanitized entity candidate records, resolution results, or a review result. Candidate state and effective usage remain visible.

CLI entry point and delegated output renderers: [src/tarel/cli/entity.py](../src/tarel/cli/entity.py).

### tarel entity show

Show one stored candidate.

**Syntax**

```text
tarel entity show [-h] [--format {text,json}] candidate_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `candidate_id` | text | required | not set | Candidate identifier. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Sanitized entity candidate records, resolution results, or a review result. Candidate state and effective usage remain visible.

CLI entry point and delegated output renderers: [src/tarel/cli/entity.py](../src/tarel/cli/entity.py).

### tarel entity find

Offer current confirmed rules or clearly labelled hypotheses.

**Syntax**

```text
tarel entity find [-h] [--source-field SOURCE_FIELD] [--target-field TARGET_FIELD]
                         [--mode {confirmed_only,confirmed_then_candidates,include_candidates}]
                         [--format {text,json}]
                         graph
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `--source-field` | text | optional | not set | Source field reference. |
| `--target-field` | text | optional | not set | Target field reference. |
| `--mode` | text; `confirmed_only`, `confirmed_then_candidates`, `include_candidates` | optional | `confirmed_then_candidates` | Mode for this command; allowed values are listed separately. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Sanitized entity candidate records, resolution results, or a review result. Candidate state and effective usage remain visible.

CLI entry point and delegated output renderers: [src/tarel/cli/entity.py](../src/tarel/cli/entity.py).

### tarel entity resolve

Resolve one record key through protected same-object alias groups.

**Syntax**

```text
tarel entity resolve [-h] --object OBJECT_REFERENCE --key KEY
                            [--mode {confirmed_only,confirmed_then_candidates,include_candidates}]
                            [--format {text,json}]
                            graph
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `--object` | text | required | not set | Qualified object reference. |
| `--key` | text | required | not set | Declared key. |
| `--mode` | text; `confirmed_only`, `confirmed_then_candidates`, `include_candidates` | optional | `confirmed_then_candidates` | Mode for this command; allowed values are listed separately. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Sanitized entity candidate records, resolution results, or a review result. Candidate state and effective usage remain visible.

CLI entry point and delegated output renderers: [src/tarel/cli/entity.py](../src/tarel/cli/entity.py).

### tarel entity review

Record one explicit human approval or rejection.

**Syntax**

```text
tarel entity review [-h] --decision {approve,reject} --reason REASON [--revision REVISION]
                           [--format {text,json}]
                           candidate_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `candidate_id` | text | required | not set | Candidate identifier. |
| `--decision` | text; `approve`, `reject` | required | not set | Review decision. |
| `--reason` | text | required | not set | Human-readable reason for the decision or mutation. |
| `--revision` | text | optional | not set | Revision pin for this operation. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Sanitized entity candidate records, resolution results, or a review result. Candidate state and effective usage remain visible.

CLI entry point and delegated output renderers: [src/tarel/cli/entity.py](../src/tarel/cli/entity.py).

## discovery

**Discovery runs.** Run a bounded hypothesis, observation, and decision protocol for joins, entities, and mappings.

The harness owns probes and data execution. TAREL owns revisioned run state and validates submitted evidence. next supplies allowed_actions; submit must use the current revision. Promotion and human validation are separate operations.

Contract and workflow: [discovery-runs.md](contracts.md#discovery-protocol).

Example:

```bash
tarel discovery next run-01 --format json
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel discovery start`](#tarel-discovery-start) | Start one bounded discovery run. |
 | [`tarel discovery next`](#tarel-discovery-next) | Get the current bounded agent task. |
 | [`tarel discovery submit`](#tarel-discovery-submit) | Submit one structured discovery action. |
 | [`tarel discovery advise`](#tarel-discovery-advise) | Ask the configured provider for metadata-only hypotheses. |
 | [`tarel discovery promote`](#tarel-discovery-promote) | Promote selected joins, an entity match, or a mapping into review. |
 | [`tarel discovery show`](#tarel-discovery-show) | Show one complete sanitized run document. |
 | [`tarel discovery list`](#tarel-discovery-list) | List stored discovery runs. |
 | [`tarel discovery find`](#tarel-discovery-find) | Retrieve selected or explicitly exploratory discovery candidates. |
 | [`tarel discovery coverage`](#tarel-discovery-coverage) | Record or show one aggregate-only query-linked coverage document. |

### tarel discovery start

Start one bounded discovery run.

**Syntax**

```text
tarel discovery start [-h] --graph GRAPH [--source SOURCES] [--question QUESTION]
                             [--preset {quick,balanced,deep}] [--probe-budget PROBE_BUDGET]
                             [--candidate-budget CANDIDATE_BUDGET]
                             [--advisor-provider ADVISOR_PROVIDER] [--logical-endpoints]
                             [--identity-inspection]
                             [--scope-mode {global_population,query_linked_slice}] [--id RUN_ID]
                             [--format {text,json}]
                             {joins,entities,mappings}
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `kind` | text; `joins`, `entities`, `mappings` | required | not set | Artifact/operation kind. |
| `--graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `--source` | text | optional; repeatable | not set | Logical source selection. |
| `--question` | text | optional | not set | Goal of the run. |
| `--preset` | text; `quick`, `balanced`, `deep` | optional | `balanced` | Named budget preset. |
| `--probe-budget` | int | optional | not set | Discovery probe budget. |
| `--candidate-budget` | int | optional | not set | Discovery candidate budget. |
| `--advisor-provider` | text | optional | not set | Optional provider used for proposal advice. |
| `--logical-endpoints` | flag | optional | `False` | Opt in to revision-pinned logical join endpoints (v0.3). |
| `--identity-inspection` | flag | optional | `False` | Enable the protected, same-object key/label identity loop. |
| `--scope-mode` | text; `global_population`, `query_linked_slice` | optional | `global_population` | Declare global or question-linked entity-discovery coverage. |
| `--id` | text | optional | not set | Discovery or analysis run identifier. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Revisioned run/task/action results, advice, promotion results, or coverage. next includes allowed actions; submit consumes the current revision. Read status before choosing the next action.

CLI entry point and delegated output renderers: [src/tarel/cli/discovery.py](../src/tarel/cli/discovery.py).

### tarel discovery next

Get the current bounded agent task.

**Syntax**

```text
tarel discovery next [-h] [--format {text,json}] run_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `run_id` | text | required | not set | Discovery or analysis run identifier. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Revisioned run/task/action results, advice, promotion results, or coverage. next includes allowed actions; submit consumes the current revision. Read status before choosing the next action.

CLI entry point and delegated output renderers: [src/tarel/cli/discovery.py](../src/tarel/cli/discovery.py).

### tarel discovery submit

Submit one structured discovery action.

**Syntax**

```text
tarel discovery submit [-h] --expected-revision EXPECTED_REVISION
                              [--actor {coding_agent,human,provider}] --action
                              {complete_run,pause_run,propose_candidate,record_entity_group,record_entity_reflection,record_inventory_page,record_observation,register_identity_inventory,register_mapping_manifest,reject_candidate,resume_run,select_candidate}
                              --source SOURCE [--format {text,json}]
                              run_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `run_id` | text | required | not set | Discovery or analysis run identifier. |
| `--expected-revision` | text | required | not set | Exact current revision required for the write. |
| `--actor` | text; `coding_agent`, `human`, `provider` | optional | `coding_agent` | Actor identity for the operation. |
| `--action` | text; `complete_run`, `pause_run`, `propose_candidate`, `record_entity_group`, `record_entity_reflection`, `record_inventory_page`, `record_observation`, `register_identity_inventory`, `register_mapping_manifest`, `reject_candidate`, `resume_run`, `select_candidate` | required | not set | Action permitted by the current run phase. |
| `--source` | text | required | not set | Action JSON path or '-' for stdin. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Revisioned run/task/action results, advice, promotion results, or coverage. next includes allowed actions; submit consumes the current revision. Read status before choosing the next action.

CLI entry point and delegated output renderers: [src/tarel/cli/discovery.py](../src/tarel/cli/discovery.py).

### tarel discovery advise

Ask the configured provider for metadata-only hypotheses.

**Syntax**

```text
tarel discovery advise [-h] --expected-revision EXPECTED_REVISION [--count COUNT]
                              [--model MODEL] [--timeout TIMEOUT] [--format {text,json}]
                              run_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `run_id` | text | required | not set | Discovery or analysis run identifier. |
| `--expected-revision` | text | required | not set | Exact current revision required for the write. |
| `--count` | int | optional | `3` | Requested item count. |
| `--model` | text | optional | not set | Model override. |
| `--timeout` | float | optional | `120.0` | Timeout in seconds. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Revisioned run/task/action results, advice, promotion results, or coverage. next includes allowed actions; submit consumes the current revision. Read status before choosing the next action.

CLI entry point and delegated output renderers: [src/tarel/cli/discovery.py](../src/tarel/cli/discovery.py).

### tarel discovery promote

Promote selected joins, an entity match, or a mapping into review.

A promoted selected candidate enters the relevant review path. Completion/promotion is not human approval and does not execute or install a private matching implementation.

**Syntax**

```text
tarel discovery promote [-h] --candidate CANDIDATE_IDS --reason REASON
                               [--supersedes SUPERSEDES] [--format {text,json}]
                               run_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `run_id` | text | required | not set | Discovery or analysis run identifier. |
| `--candidate` | text | required; repeatable | not set | Selected candidate identifiers. |
| `--reason` | text | required | not set | Human-readable reason for the decision or mutation. |
| `--supersedes` | text | optional | not set | Active equivalent self-entity candidate replaced by this evidence revision. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Revisioned run/task/action results, advice, promotion results, or coverage. next includes allowed actions; submit consumes the current revision. Read status before choosing the next action.

CLI entry point and delegated output renderers: [src/tarel/cli/discovery.py](../src/tarel/cli/discovery.py).

### tarel discovery show

Show one complete sanitized run document.

**Syntax**

```text
tarel discovery show [-h] [--format {text,json}] run_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `run_id` | text | required | not set | Discovery or analysis run identifier. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Revisioned run/task/action results, advice, promotion results, or coverage. next includes allowed actions; submit consumes the current revision. Read status before choosing the next action.

CLI entry point and delegated output renderers: [src/tarel/cli/discovery.py](../src/tarel/cli/discovery.py).

### tarel discovery list

List stored discovery runs.

**Syntax**

```text
tarel discovery list [-h] [--graph GRAPH]
                            [--kind {join_discovery,entity_matching,reference_mapping}]
                            [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--graph` | text | optional | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `--kind` | text; `join_discovery`, `entity_matching`, `reference_mapping` | optional | not set | Artifact/operation kind. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Revisioned run/task/action results, advice, promotion results, or coverage. next includes allowed actions; submit consumes the current revision. Read status before choosing the next action.

CLI entry point and delegated output renderers: [src/tarel/cli/discovery.py](../src/tarel/cli/discovery.py).

### tarel discovery find

Retrieve selected or explicitly exploratory discovery candidates.

**Syntax**

```text
tarel discovery find [-h] [--graph GRAPH]
                            [--kind {join_discovery,entity_matching,reference_mapping}]
                            [--include-exploratory] [--query QUERY] [--limit LIMIT]
                            [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--graph` | text | optional | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `--kind` | text; `join_discovery`, `entity_matching`, `reference_mapping` | optional | not set | Artifact/operation kind. |
| `--include-exploratory` | flag | optional | `False` | Include exploratory candidates. |
| `--query` | text | optional | not set | Search or analytical question text. |
| `--limit` | int | optional | `20` | Maximum number of items for this operation. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Revisioned run/task/action results, advice, promotion results, or coverage. next includes allowed actions; submit consumes the current revision. Read status before choosing the next action.

CLI entry point and delegated output renderers: [src/tarel/cli/discovery.py](../src/tarel/cli/discovery.py).

### tarel discovery coverage

Record or show one aggregate-only query-linked coverage document.

**Syntax**

```text
tarel discovery coverage [-h] [--source SOURCE] [--format {text,json}] run_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `run_id` | text | required | not set | Discovery or analysis run identifier. |
| `--source` | text | optional | not set | Coverage JSON path or '-' for stdin; omit to show the stored document. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Revisioned run/task/action results, advice, promotion results, or coverage. next includes allowed actions; submit consumes the current revision. Read status before choosing the next action.

CLI entry point and delegated output renderers: [src/tarel/cli/discovery.py](../src/tarel/cli/discovery.py).

## agent

**Harness resources.** Install the supplied agent-facing resources into a supported target.

Setup writes the selected resources; it does not launch an analytical agent or grant database access.

Contract and workflow: [discovery-runs.md](contracts.md#discovery-protocol).

Example:

```bash
tarel agent setup --help
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel agent setup`](#tarel-agent-setup) | Install the TAREL discovery skill. |

### tarel agent setup

Install the TAREL discovery skill.

**Syntax**

```text
tarel agent setup [-h] [--target TARGET] [--force] [--format {text,json}] {codex}
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `agent` | text; `codex` | required | not set | Target agent integration. |
| `--target` | Path | optional | current directory | Target object, field, or reference. |
| `--force` | flag | optional | `False` | Allow the command-specific forced replacement. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Target agent, changed resource paths, and target directory.

CLI entry point and delegated output renderers: [src/tarel/cli/discovery.py](../src/tarel/cli/discovery.py).

## topology

**Logical topology.** Declare derived logical objects and their physical references.

Import and review persist logical metadata. These declarations do not execute extraction, transformation, or joins.

Contract and workflow: [logical-topology.md](contracts.md#logical-topology).

Example:

```bash
tarel topology --help
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel topology import`](#tarel-topology-import) | Import one strict graph-bound logical-topology document. |
 | [`tarel topology show`](#tarel-topology-show) | Show the current logical topology for one graph. |
 | [`tarel topology review`](#tarel-topology-review) | Record one human approval or rejection of a derived relation. |

### tarel topology import

Import one strict graph-bound logical-topology document.

**Syntax**

```text
tarel topology import [-h] --source SOURCE [--expected-revision EXPECTED_REVISION]
                             [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--source` | text | required | not set | JSON path or '-' for stdin. |
| `--expected-revision` | text | optional | not set | Exact current revision required for the write. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Logical topology document and review state. Import takes typed input.

CLI entry point and delegated output renderers: [src/tarel/cli/topology.py](../src/tarel/cli/topology.py).

### tarel topology show

Show the current logical topology for one graph.

**Syntax**

```text
tarel topology show [-h] [--format {text,json}] graph
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Logical topology document and review state. Import takes typed input.

CLI entry point and delegated output renderers: [src/tarel/cli/topology.py](../src/tarel/cli/topology.py).

### tarel topology review

Record one human approval or rejection of a derived relation.

**Syntax**

```text
tarel topology review [-h] --decision {approve,reject} --reason REASON --revision REVISION
                             [--format {text,json}]
                             graph relation_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `relation_id` | text | required | not set | Relation identifier. |
| `--decision` | text; `approve`, `reject` | required | not set | Review decision. |
| `--reason` | text | required | not set | Human-readable reason for the decision or mutation. |
| `--revision` | text | required | not set | Revision pin for this operation. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Logical topology document and review state. Import takes typed input.

CLI entry point and delegated output renderers: [src/tarel/cli/topology.py](../src/tarel/cli/topology.py).

## family

**Object families.** Group compatible physical objects under an explicitly reviewed logical family.

Plan/proposal runs and review have separate effects. Provider runs create candidates; schema compatibility does not prove safe unions or disjoint rows. Member pages preserve physical identities.

Contract and workflow: [object-families.md](contracts.md#object-families).

Example:

```bash
tarel family --help
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel family plan`](#tarel-family-plan) | Plan bounded LLM family suggestions from schema only. |
 | [`tarel family run`](#tarel-family-run) | Generate unreviewed family candidates; never read rows. |
 | [`tarel family run-show`](#tarel-family-run-show) | Inspect aggregate proposal progress and failures. |
 | [`tarel family propose`](#tarel-family-propose) | Validate and store an explicit candidate family. |
 | [`tarel family list`](#tarel-family-list) | List summaries without member lists. |
 | [`tarel family show`](#tarel-family-show) | Show one family summary, including freshness. |
 | [`tarel family export`](#tarel-family-export) | Export a complete audit artifact. |
 | [`tarel family review`](#tarel-family-review) | Record a human review at a pinned revision. |
 | [`tarel family members`](#tarel-family-members) | Resolve a bounded page of physical members. |
 | [`tarel family import`](#tarel-family-import) | Import a strict candidate artifact. |

### tarel family plan

Plan bounded LLM family suggestions from schema only.

**Syntax**

```text
tarel family plan [-h] --provider PROVIDER [--model MODEL]
                         [--objects-per-batch OBJECTS_PER_BATCH] [--max-input-chars MAX_INPUT_CHARS]
                         [--max-objects MAX_OBJECTS] [--format {text,json}]
                         graph run_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `run_id` | text | required | not set | Discovery or analysis run identifier. |
| `--provider` | text | required | not set | Configured provider profile. |
| `--model` | text | optional | not set | Model override. |
| `--objects-per-batch` | int | optional | `50` | Object budget per proposal batch. |
| `--max-input-chars` | int | optional | `40000` | Input character budget. |
| `--max-objects` | int | optional | `1000` | Maximum selected objects. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Plan/run result, family document/list, or revision-bound member page. export serializes the family document. Membership remains physical and schema compatibility is not a union guarantee.

CLI entry point and delegated output renderers: [src/tarel/cli/family.py](../src/tarel/cli/family.py).

### tarel family run

Generate unreviewed family candidates; never read rows.

**Syntax**

```text
tarel family run [-h] [--workers WORKERS] [--resume] [--timeout TIMEOUT]
                        [--format {text,json}]
                        run_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `run_id` | text | required | not set | Discovery or analysis run identifier. |
| `--workers` | int | optional | `1` | Parallel worker count for this command. |
| `--resume` | flag | optional | `False` | Resume a compatible checkpoint/run. |
| `--timeout` | float | optional | `120.0` | Timeout in seconds. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Plan/run result, family document/list, or revision-bound member page. export serializes the family document. Membership remains physical and schema compatibility is not a union guarantee.

CLI entry point and delegated output renderers: [src/tarel/cli/family.py](../src/tarel/cli/family.py).

### tarel family run-show

Inspect aggregate proposal progress and failures.

**Syntax**

```text
tarel family run-show [-h] [--format {text,json}] run_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `run_id` | text | required | not set | Discovery or analysis run identifier. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Plan/run result, family document/list, or revision-bound member page. export serializes the family document. Membership remains physical and schema compatibility is not a union guarantee.

CLI entry point and delegated output renderers: [src/tarel/cli/family.py](../src/tarel/cli/family.py).

### tarel family propose

Validate and store an explicit candidate family.

**Syntax**

```text
tarel family propose [-h] --name NAME --member MEMBERS --grain GRAIN [--attribute ATTRIBUTE]
                            [--producer PRODUCER] [--format {text,json}]
                            graph family_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `family_id` | text | required | not set | Object-family identifier. |
| `--name` | text | required | not set | Family identifier: letters, numbers, dots, underscores and hyphens. |
| `--member` | text | required; repeatable | not set | Family member references. |
| `--grain` | text | required; repeatable | not set | Declared record grain. |
| `--attribute` | text | optional; repeatable | `[]` | JSON metadata attribute. |
| `--producer` | text | optional | `coding_agent` | Producer identity. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Plan/run result, family document/list, or revision-bound member page. export serializes the family document. Membership remains physical and schema compatibility is not a union guarantee.

CLI entry point and delegated output renderers: [src/tarel/cli/family.py](../src/tarel/cli/family.py).

### tarel family list

List summaries without member lists.

**Syntax**

```text
tarel family list [-h] [--format {text,json}] graph
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Plan/run result, family document/list, or revision-bound member page. export serializes the family document. Membership remains physical and schema compatibility is not a union guarantee.

CLI entry point and delegated output renderers: [src/tarel/cli/family.py](../src/tarel/cli/family.py).

### tarel family show

Show one family summary, including freshness.

**Syntax**

```text
tarel family show [-h] [--format {text,json}] graph family_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `family_id` | text | required | not set | Object-family identifier. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Plan/run result, family document/list, or revision-bound member page. export serializes the family document. Membership remains physical and schema compatibility is not a union guarantee.

CLI entry point and delegated output renderers: [src/tarel/cli/family.py](../src/tarel/cli/family.py).

### tarel family export

Export a complete audit artifact.

**Syntax**

```text
tarel family export [-h] [--format {text,json}] graph family_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `family_id` | text | required | not set | Object-family identifier. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Plan/run result, family document/list, or revision-bound member page. export serializes the family document. Membership remains physical and schema compatibility is not a union guarantee.

CLI entry point and delegated output renderers: [src/tarel/cli/family.py](../src/tarel/cli/family.py).

### tarel family review

Record a human review at a pinned revision.

**Syntax**

```text
tarel family review [-h] --decision {approve,reject} --reason REASON --revision REVISION
                           [--format {text,json}]
                           graph family_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `family_id` | text | required | not set | Object-family identifier. |
| `--decision` | text; `approve`, `reject` | required | not set | Review decision. |
| `--reason` | text | required | not set | Human-readable reason for the decision or mutation. |
| `--revision` | text | required | not set | Revision pin for this operation. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Plan/run result, family document/list, or revision-bound member page. export serializes the family document. Membership remains physical and schema compatibility is not a union guarantee.

CLI entry point and delegated output renderers: [src/tarel/cli/family.py](../src/tarel/cli/family.py).

### tarel family members

Resolve a bounded page of physical members.

**Syntax**

```text
tarel family members [-h] --revision REVISION [--mode {confirmed_only,include_candidates}]
                            [--offset OFFSET] [--limit LIMIT] [--where WHERE]
                            [--namespace NAMESPACE] [--format {text,json}]
                            graph family_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `family_id` | text | required | not set | Object-family identifier. |
| `--revision` | text | required | not set | Revision pin for this operation. |
| `--mode` | text; `confirmed_only`, `include_candidates` | optional | `confirmed_only` | Mode for this command; allowed values are listed separately. |
| `--offset` | int | optional | `0` | Pagination starting offset. |
| `--limit` | int | optional | `50` | Maximum number of items for this operation. |
| `--where` | text | optional; repeatable | `[]` | Exact attribute NAME=VALUE. |
| `--namespace` | text | optional | not set | Namespace/schema filter. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Plan/run result, family document/list, or revision-bound member page. export serializes the family document. Membership remains physical and schema compatibility is not a union guarantee.

CLI entry point and delegated output renderers: [src/tarel/cli/family.py](../src/tarel/cli/family.py).

### tarel family import

Import a strict candidate artifact.

**Syntax**

```text
tarel family import [-h] --source SOURCE [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--source` | text | required | not set | JSON file or '-' for stdin. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Plan/run result, family document/list, or revision-bound member page. export serializes the family document. Membership remains physical and schema compatibility is not a union guarantee.

CLI entry point and delegated output renderers: [src/tarel/cli/family.py](../src/tarel/cli/family.py).

## binding

**Object-to-value bindings.** Resolve caller selections to declared physical or family members.

Bindings declare metadata routing. Private values supplied through supported stdin paths remain caller input rather than persisted graph values. Review and revision checks still apply.

Contract and workflow: [object-value-bindings.md](contracts.md#object-to-value-bindings).

Example:

```bash
tarel binding --help
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel binding import`](#tarel-binding-import) | Resolve caller selections to declared physical or family members. |
 | [`tarel binding find`](#tarel-binding-find) | Resolve caller selections to declared physical or family members. |
 | [`tarel binding show`](#tarel-binding-show) | Resolve caller selections to declared physical or family members. |
 | [`tarel binding review`](#tarel-binding-review) | Resolve caller selections to declared physical or family members. |
 | [`tarel binding resolve`](#tarel-binding-resolve) | Resolve caller selections to declared physical or family members. |

### tarel binding import

Resolve caller selections to declared physical or family members.

**Syntax**

```text
tarel binding import [-h] --source SOURCE [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--source` | text | required | not set | Candidate JSON path or '-' for stdin. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Binding metadata, review result, or resolved member/object references. Protected selections are not echoed as an ordinary catalog.

CLI entry point and delegated output renderers: [src/tarel/cli/binding.py](../src/tarel/cli/binding.py).

### tarel binding find

Resolve caller selections to declared physical or family members.

**Syntax**

```text
tarel binding find [-h] [--mode {confirmed_only,include_candidates}] [--format {text,json}]
                          graph
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `--mode` | text; `confirmed_only`, `include_candidates` | optional | `confirmed_only` | Mode for this command; allowed values are listed separately. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Binding metadata, review result, or resolved member/object references. Protected selections are not echoed as an ordinary catalog.

CLI entry point and delegated output renderers: [src/tarel/cli/binding.py](../src/tarel/cli/binding.py).

### tarel binding show

Resolve caller selections to declared physical or family members.

**Syntax**

```text
tarel binding show [-h] [--format {text,json}] graph id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `id` | text | required | not set | Artifact identifier. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Binding metadata, review result, or resolved member/object references. Protected selections are not echoed as an ordinary catalog.

CLI entry point and delegated output renderers: [src/tarel/cli/binding.py](../src/tarel/cli/binding.py).

### tarel binding review

Resolve caller selections to declared physical or family members.

**Syntax**

```text
tarel binding review [-h] --revision REVISION --decision {approve,reject} --reason REASON
                            [--format {text,json}]
                            graph id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `id` | text | required | not set | Artifact identifier. |
| `--revision` | text | required | not set | Revision pin for this operation. |
| `--decision` | text; `approve`, `reject` | required | not set | Review decision. |
| `--reason` | text | required | not set | Human-readable reason for the decision or mutation. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Binding metadata, review result, or resolved member/object references. Protected selections are not echoed as an ordinary catalog.

CLI entry point and delegated output renderers: [src/tarel/cli/binding.py](../src/tarel/cli/binding.py).

### tarel binding resolve

Resolve caller selections to declared physical or family members.

**Syntax**

```text
tarel binding resolve [-h] --revision REVISION --values-stdin [--limit LIMIT]
                             [--namespace NAMESPACE] [--mode {confirmed_only,include_candidates}]
                             [--format {text,json}]
                             graph id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `id` | text | required | not set | Artifact identifier. |
| `--revision` | text | required | not set | Revision pin for this operation. |
| `--values-stdin` | flag | required | `False` | Read an ephemeral JSON string array; never echo/persist it. |
| `--limit` | int | optional | `100` | Maximum number of items for this operation. |
| `--namespace` | text | optional | not set | Namespace/schema filter. |
| `--mode` | text; `confirmed_only`, `include_candidates` | optional | `confirmed_only` | Mode for this command; allowed values are listed separately. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Binding metadata, review result, or resolved member/object references. Protected selections are not echoed as an ordinary catalog.

CLI entry point and delegated output renderers: [src/tarel/cli/binding.py](../src/tarel/cli/binding.py).

## concept

**Semantic concepts.** Describe semantic concepts, representations, and declared hierarchies.

Import/review persist concept metadata. A hierarchy alone does not establish value equality, a join, or an analytically valid rollup.

Contract and workflow: [semantic-concepts.md](contracts.md#semantic-concepts).

Example:

```bash
tarel concept --help
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel concept import`](#tarel-concept-import) | Import a strict candidate concept document. |
 | [`tarel concept show`](#tarel-concept-show) | Export one complete concept audit document. |
 | [`tarel concept review`](#tarel-concept-review) | Record one revision-pinned human concept review. |
 | [`tarel concept find`](#tarel-concept-find) | Find current concepts with dependency review closure. |

### tarel concept import

Import a strict candidate concept document.

**Syntax**

```text
tarel concept import [-h] --source SOURCE [--expected-revision EXPECTED_REVISION]
                            [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--source` | text | required | not set | JSON file or '-' for stdin. |
| `--expected-revision` | text | optional | not set | Exact current revision required for the write. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Concept document, matching representations, or review result with current usage.

CLI entry point and delegated output renderers: [src/tarel/cli/concept.py](../src/tarel/cli/concept.py).

### tarel concept show

Export one complete concept audit document.

**Syntax**

```text
tarel concept show [-h] [--format {text,json}] graph
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Concept document, matching representations, or review result with current usage.

CLI entry point and delegated output renderers: [src/tarel/cli/concept.py](../src/tarel/cli/concept.py).

### tarel concept review

Record one revision-pinned human concept review.

**Syntax**

```text
tarel concept review [-h] --decision {approve,reject} --reason REASON --revision REVISION
                            [--format {text,json}]
                            graph concept_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `concept_id` | text | required | not set | Semantic concept identifier. |
| `--decision` | text; `approve`, `reject` | required | not set | Review decision. |
| `--reason` | text | required | not set | Human-readable reason for the decision or mutation. |
| `--revision` | text | required | not set | Revision pin for this operation. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Concept document, matching representations, or review result with current usage.

CLI entry point and delegated output renderers: [src/tarel/cli/concept.py](../src/tarel/cli/concept.py).

### tarel concept find

Find current concepts with dependency review closure.

**Syntax**

```text
tarel concept find [-h] [--concept-id CONCEPT_ID] [--endpoint ENDPOINT]
                          [--mode {confirmed_only,confirmed_then_candidates,include_candidates}]
                          [--limit LIMIT] [--format {text,json}]
                          graph [query]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `query` | text | optional; optional positional | not set | Search or analytical question text. |
| `--concept-id` | text | optional | not set | Resolve this exact concept ID, without name matching. |
| `--endpoint` | text | optional | not set | Strict logical endpoint JSON; no source values. |
| `--mode` | text; `confirmed_only`, `confirmed_then_candidates`, `include_candidates` | optional | `confirmed_only` | Mode for this command; allowed values are listed separately. |
| `--limit` | int | optional | `20` | Maximum number of items for this operation. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Concept document, matching representations, or review result with current usage.

CLI entry point and delegated output renderers: [src/tarel/cli/concept.py](../src/tarel/cli/concept.py).

## logical-join

**Logical joins.** Find and review discovered joins involving logical endpoints.

These are separate logical artifacts, not physical foreign keys. Effective usage depends on the endpoints and their review state.

Contract and workflow: [logical-join-discovery.md](contracts.md#logical-joins).

Example:

```bash
tarel logical-join --help
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel logical-join list`](#tarel-logical-join-list) | List audit summaries, including inactive records. |
 | [`tarel logical-join show`](#tarel-logical-join-show) | Show one full logical join audit artifact. |
 | [`tarel logical-join review`](#tarel-logical-join-review) | Record a revision-pinned human decision. |
 | [`tarel logical-join find`](#tarel-logical-join-find) | Find only current policy-eligible logical joins. |

### tarel logical-join list

List audit summaries, including inactive records.

**Syntax**

```text
tarel logical-join list [-h] [--graph GRAPH] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--graph` | text | optional | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Logical join records and effective review/usage state.

CLI entry point and delegated output renderers: [src/tarel/cli/logical_join.py](../src/tarel/cli/logical_join.py).

### tarel logical-join show

Show one full logical join audit artifact.

**Syntax**

```text
tarel logical-join show [-h] [--format {text,json}] join_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `join_id` | text | required | not set | Logical join identifier. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Logical join records and effective review/usage state.

CLI entry point and delegated output renderers: [src/tarel/cli/logical_join.py](../src/tarel/cli/logical_join.py).

### tarel logical-join review

Record a revision-pinned human decision.

**Syntax**

```text
tarel logical-join review [-h] --decision {approve,reject} --reason REASON --revision
                                 REVISION [--format {text,json}]
                                 join_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `join_id` | text | required | not set | Logical join identifier. |
| `--decision` | text; `approve`, `reject` | required | not set | Review decision. |
| `--reason` | text | required | not set | Human-readable reason for the decision or mutation. |
| `--revision` | text | required | not set | Revision pin for this operation. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Logical join records and effective review/usage state.

CLI entry point and delegated output renderers: [src/tarel/cli/logical_join.py](../src/tarel/cli/logical_join.py).

### tarel logical-join find

Find only current policy-eligible logical joins.

**Syntax**

```text
tarel logical-join find [-h] [--join-id JOIN_ID]
                               [--mode {confirmed_only,confirmed_then_candidates,include_candidates}]
                               [--limit LIMIT] [--format {text,json}]
                               graph
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `--join-id` | text | optional | not set | Narrow to a current policy-eligible artifact ID. |
| `--mode` | text; `confirmed_only`, `confirmed_then_candidates`, `include_candidates` | optional | `confirmed_only` | Mode for this command; allowed values are listed separately. |
| `--limit` | int | optional | `20` | Maximum number of items for this operation. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Logical join records and effective review/usage state.

CLI entry point and delegated output renderers: [src/tarel/cli/logical_join.py](../src/tarel/cli/logical_join.py).

## reference-mapping

**Reference mappings.** Record and retrieve evidence about caller-owned field correspondences.

Private mapping values remain outside the artifact. Imports and reviews persist value-free metadata and evidence; a mapping does not itself execute data transformation.

Contract and workflow: [reference-mappings.md](contracts.md#reference-mappings).

Example:

```bash
tarel reference-mapping --help
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel reference-mapping import`](#tarel-reference-mapping-import) | Import one sanitized physical-field mapping candidate. |
 | [`tarel reference-mapping list`](#tarel-reference-mapping-list) | List mapping candidates and audit history. |
 | [`tarel reference-mapping show`](#tarel-reference-mapping-show) | Show one stored reference-mapping candidate. |
 | [`tarel reference-mapping find`](#tarel-reference-mapping-find) | Offer confirmed mappings or explicitly labelled candidates. |
 | [`tarel reference-mapping review`](#tarel-reference-mapping-review) | Record one explicit human approval or rejection. |

### tarel reference-mapping import

Import one sanitized physical-field mapping candidate.

**Syntax**

```text
tarel reference-mapping import [-h] --source SOURCE [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--source` | text | required | not set | JSON path or '-' for stdin. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Value-free mapping candidates, selected matches, or review result. Mapping rows are caller-owned.

CLI entry point and delegated output renderers: [src/tarel/cli/reference_mapping.py](../src/tarel/cli/reference_mapping.py).

### tarel reference-mapping list

List mapping candidates and audit history.

**Syntax**

```text
tarel reference-mapping list [-h] [--graph GRAPH] [--state {candidate,reviewed,rejected}]
                                    [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--graph` | text | optional | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `--state` | text; `candidate`, `reviewed`, `rejected` | optional; repeatable | not set | Review-state selection. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Value-free mapping candidates, selected matches, or review result. Mapping rows are caller-owned.

CLI entry point and delegated output renderers: [src/tarel/cli/reference_mapping.py](../src/tarel/cli/reference_mapping.py).

### tarel reference-mapping show

Show one stored reference-mapping candidate.

**Syntax**

```text
tarel reference-mapping show [-h] [--format {text,json}] candidate_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `candidate_id` | text | required | not set | Candidate identifier. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Value-free mapping candidates, selected matches, or review result. Mapping rows are caller-owned.

CLI entry point and delegated output renderers: [src/tarel/cli/reference_mapping.py](../src/tarel/cli/reference_mapping.py).

### tarel reference-mapping find

Offer confirmed mappings or explicitly labelled candidates.

**Syntax**

```text
tarel reference-mapping find [-h] [--source-field SOURCE_FIELD] [--target-field TARGET_FIELD]
                                    [--mode {confirmed_only,confirmed_then_candidates,include_candidates}]
                                    [--format {text,json}]
                                    graph
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `--source-field` | text | optional | not set | Source field reference. |
| `--target-field` | text | optional | not set | Target field reference. |
| `--mode` | text; `confirmed_only`, `confirmed_then_candidates`, `include_candidates` | optional | `confirmed_then_candidates` | Mode for this command; allowed values are listed separately. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Value-free mapping candidates, selected matches, or review result. Mapping rows are caller-owned.

CLI entry point and delegated output renderers: [src/tarel/cli/reference_mapping.py](../src/tarel/cli/reference_mapping.py).

### tarel reference-mapping review

Record one explicit human approval or rejection.

**Syntax**

```text
tarel reference-mapping review [-h] --decision {approve,reject} --reason REASON --revision
                                      REVISION [--format {text,json}]
                                      candidate_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `candidate_id` | text | required | not set | Candidate identifier. |
| `--decision` | text; `approve`, `reject` | required | not set | Review decision. |
| `--reason` | text | required | not set | Human-readable reason for the decision or mutation. |
| `--revision` | text | required | not set | Revision pin for this operation. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Value-free mapping candidates, selected matches, or review result. Mapping rows are caller-owned.

CLI entry point and delegated output renderers: [src/tarel/cli/reference_mapping.py](../src/tarel/cli/reference_mapping.py).

## focus

**Report and cube focus.** Persist an upstream selection starting at one exact reference.

Build stores a revision-bound focus. A single measure seed is not automatically the full report. Inspect warnings and truncation; refresh the focus after relevant source changes.

Contract and workflow: [family-focus.md](contracts.md#families-in-report-focus).

Example:

```bash
tarel focus list
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel focus build`](#tarel-focus-build) | Trace one seed upstream through explicitly selected sources. |
 | [`tarel focus show`](#tarel-focus-show) | Show one persisted focus snapshot. |
 | [`tarel focus list`](#tarel-focus-list) | List persisted focus snapshots. |

### tarel focus build

Trace one seed upstream through explicitly selected sources.

**Syntax**

```text
tarel focus build [-h] --seed SEED [--lineage LINEAGES] [--graph GRAPHS]
                         [--max-hops MAX_HOPS] [--state {draft,review_required,validated}]
                         [--format {text,json}]
                         name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--seed` | text | required | not set | Exact upstream-trace starting reference. |
| `--lineage` | text | optional; repeatable | not set | Lineage documents to include. |
| `--graph` | text | optional; repeatable | not set | Graph names to include. |
| `--max-hops` | int | optional | `12` | Maximum traversal/expansion depth. |
| `--state` | text; `draft`, `review_required`, `validated` | optional; repeatable | not set | Selected review state. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Saved focus/listing with seed, source revisions, members, hops, warnings, and truncation.

CLI entry point and delegated output renderers: [src/tarel/cli/focus.py](../src/tarel/cli/focus.py).

### tarel focus show

Show one persisted focus snapshot.

**Syntax**

```text
tarel focus show [-h] [--format {text,json}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Saved focus/listing with seed, source revisions, members, hops, warnings, and truncation.

CLI entry point and delegated output renderers: [src/tarel/cli/focus.py](../src/tarel/cli/focus.py).

### tarel focus list

List persisted focus snapshots.

**Syntax**

```text
tarel focus list [-h] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Saved focus/listing with seed, source revisions, members, hops, warnings, and truncation.

CLI entry point and delegated output renderers: [src/tarel/cli/focus.py](../src/tarel/cli/focus.py).

## search

**Search.** Find graph anchors by technical names and business meaning.

Returns ranked metadata matches. BM25 does not require a local embedding model; vector/hybrid modes use the optional model and compatible indexes. Search results are not query results or proof of a join.

Contract and workflow: [local-retrieval.md](contracts.md#local-retrieval).

Example:

```bash
tarel search warehouse "customer revenue" --mode bm25
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel search`](#tarel-search) | Search graph metadata with lexical, BM25, vector, or hybrid retrieval. |

### tarel search

Search graph metadata with lexical, BM25, vector, or hybrid retrieval.

**Syntax**

```text
tarel search [-h] [--namespace NAMESPACE] [--limit LIMIT]
                    [--families {off,confirmed_only,include_candidates}]
                    [--mode {lexical,bm25,vector,hybrid}] [--model MODEL_PATH] [--threads N_THREADS]
                    [--bm25-weight BM25_WEIGHT] [--workspace NAME] [--system SYSTEMS]
                    [--graph GRAPHS] [--area AREAS] [--scope-schema SCHEMAS] [--zone ZONES]
                    [--scope-object SCOPE_OBJECTS] [--focus FOCUSES] [--type {table,view}]
                    [--role ROLES] [--has-field REQUIRED_FIELDS]
                    [--annotation-state {draft,validated,rejected,deferred,review_required}]
                    [--validated-only] [--format {text,json}]
                    [name] query
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | optional; optional positional | not set | Graph name; omit it with --workspace NAME. |
| `query` | text | required | not set | Words describing the required analytical objects. |
| `--namespace, --schema` | text | optional | not set | Namespace/schema filter. |
| `--limit` | int | optional | `20` | Maximum number of items for this operation. |
| `--families` | text; `off`, `confirmed_only`, `include_candidates` | optional | `confirmed_only` | Include logical family-name hits; never expand members. |
| `--mode` | text; `lexical`, `bm25`, `vector`, `hybrid` | optional | `lexical` | Mode for this command; allowed values are listed separately. |
| `--model` | Path | optional | not set | Local embedding model path. |
| `--threads` | int | optional | not set | Local model thread count. |
| `--bm25-weight` | float | optional | not set | Hybrid BM25 weight; default 1.0. |
| `--workspace` | text | optional | not set | Use this workspace's resolved scope instead of a single graph. |
| `--system` | text | optional; repeatable | not set | System scope selection. |
| `--graph` | text | optional; repeatable | not set | Graph names to include. |
| `--area` | text | optional; repeatable | not set | Area scope selection. |
| `--scope-schema` | text | optional; repeatable | not set | Workspace schema as GRAPH:NAMESPACE; repeat for a union. |
| `--zone` | text | optional; repeatable | not set | Zone scope selection. |
| `--scope-object` | text | optional; repeatable | not set | Hard workspace boundary as GRAPH:OBJECT_ID; repeat for a union. |
| `--focus` | text | optional; repeatable | not set | Limit a workspace operation to a current saved focus; repeat for a union. |
| `--type` | text; `table`, `view` | optional; repeatable | not set | Physical object types used to filter candidates before ranking. |
| `--role` | text | optional; repeatable | not set | Documented semantic roles used to filter candidates before ranking. |
| `--has-field` | text | optional; repeatable | not set | Field names every candidate object must contain. |
| `--annotation-state` | text; `draft`, `validated`, `rejected`, `deferred`, `review_required` | optional; repeatable | not set | Include semantic annotations in one or more review states. |
| `--validated-only` | flag | optional | `False` | Include only human-validated semantic annotations. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Ranked metadata matches and selection information, not data rows.

CLI entry point and delegated output renderers: [src/tarel/cli/search.py](../src/tarel/cli/search.py).

## context

**Context compilation.** Build a bounded context packet, prepare a stable prefix, compare packets, or expand pinned metadata.

Build/prefix return graph-derived knowledge; the harness handles prompt placement and provider caching. Expand respects packet scope, revision, and budgets. Diff compares packets; impact assesses graph-change effects.

Contract and workflow: [context-contract.md](contracts.md#context-packets).

Example:

```bash
tarel context build warehouse "customer revenue" --mode bm25 --validated-only --format json
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel context expand`](#tarel-context-expand) | Expand pinned metadata using an existing context scope. |
 | [`tarel context build`](#tarel-context-build) | Compile bounded context from search and reviewed graph relationships. |
 | [`tarel context prefix`](#tarel-context-prefix) | Compile a query-independent graph or workspace scope for prompt caching. |
 | [`tarel context brief`](#tarel-context-brief) | Summarize one saved context packet for a continuing conversation. |
 | [`tarel context diff`](#tarel-context-diff) | Validate and compare two serialized context packets. |
 | [`tarel context impact`](#tarel-context-impact) | Check whether one saved context packet is affected by the latest graph refresh. |

### tarel context expand

Expand pinned metadata using an existing context scope.

--requests takes a JSON file or - for stdin, never inline JSON, and the array holds 1-32 typed targets. Do not combine --requests - with --inputs-stdin: both would require stdin. Expansion returns exit code 1 when omissions are reported; inspect them rather than treating partial output as complete.

**Syntax**

```text
tarel context expand [-h] --packet PACKET --requests FILE [--inputs-stdin]
                            [--mode {confirmed_only,include_candidates}]
                            [--max-characters MAX_CHARACTERS] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--packet` | Path | required | not set | Existing context packet path. |
| `--requests` | text | required | not set | Path to a JSON file holding an array of 1-32 typed targets, or '-' for stdin. |
| `--inputs-stdin` | flag | optional | `False` | Private handle values, never saved. |
| `--mode` | text; `confirmed_only`, `include_candidates` | optional | `confirmed_only` | Mode for this command; allowed values are listed separately. |
| `--max-characters` | int | optional | `24000` | Character budget; not a tokenizer-based token limit. |
| `--format` | text; `text`, `json` | optional | `json` | Output format (default: json). |

**Result:** Context packet, metadata expansion, packet diff, or impact result. Inspect identities, budgets, and omissions; expand can return partial output with status 1.

CLI entry point and delegated output renderers: [src/tarel/cli/context.py](../src/tarel/cli/context.py).

### tarel context build

Compile bounded context from search and reviewed graph relationships.

The shorthand tarel context NAME QUERY is rewritten to this command. --validated-only filters semantic claims, not the entire physical inventory. An unchanged question is not sufficient for reuse after a graph or review revision changes.

**Syntax**

```text
tarel context build [-h] [--namespace NAMESPACE] [--seed-limit SEED_LIMIT]
                           [--max-objects MAX_OBJECTS] [--max-joins MAX_JOINS] [--max-hops MAX_HOPS]
                           [--max-fields-per-object MAX_FIELDS_PER_OBJECT]
                           [--max-characters MAX_CHARACTERS] [--mode {lexical,bm25,vector,hybrid}]
                           [--model MODEL_PATH] [--threads N_THREADS] [--bm25-weight BM25_WEIGHT]
                           [--workspace NAME] [--system SYSTEMS] [--graph GRAPHS] [--area AREAS]
                           [--scope-schema SCHEMAS] [--zone ZONES] [--scope-object SCOPE_OBJECTS]
                           [--focus FOCUSES] [--object OBJECT_IDS]
                           [--annotation-state {draft,validated,rejected,deferred,review_required}]
                           [--validated-only]
                           [--logical-hints {confirmed_only,confirmed_then_candidates,include_candidates}]
                           [--brief] [--format {text,json}]
                           [name] query
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | optional; optional positional | not set | Graph name; omit it with --workspace NAME. |
| `query` | text | required | not set | Analytical question or compact search query. |
| `--namespace, --schema` | text | optional | not set | Namespace/schema filter. |
| `--seed-limit` | int | optional | `3` | Maximum retrieval seed count. |
| `--max-objects` | int | optional | `10` | Maximum selected objects. |
| `--max-joins` | int | optional | `12` | Maximum selected joins. |
| `--max-hops` | int | optional | `2` | Maximum traversal/expansion depth. |
| `--max-fields-per-object` | int | optional | `12` | Maximum fields per object. |
| `--max-characters` | int | optional | `24000` | Maximum canonical characters in the complete context payload. |
| `--mode` | text; `lexical`, `bm25`, `vector`, `hybrid` | optional | `lexical` | Mode for this command; allowed values are listed separately. |
| `--model` | Path | optional | not set | Local embedding model path. |
| `--threads` | int | optional | not set | Local model thread count. |
| `--bm25-weight` | float | optional | not set | Hybrid BM25 weight; default 1.0. |
| `--workspace` | text | optional | not set | Use this workspace's resolved scope instead of a single graph. |
| `--system` | text | optional; repeatable | not set | System scope selection. |
| `--graph` | text | optional; repeatable | not set | Graph names to include. |
| `--area` | text | optional; repeatable | not set | Area scope selection. |
| `--scope-schema` | text | optional; repeatable | not set | Workspace schema as GRAPH:NAMESPACE; repeat for a union. |
| `--zone` | text | optional; repeatable | not set | Zone scope selection. |
| `--scope-object` | text | optional; repeatable | not set | Hard workspace boundary as GRAPH:OBJECT_ID; repeat for a union. |
| `--focus` | text | optional; repeatable | not set | Limit a workspace operation to a current saved focus; repeat for a union. |
| `--object` | text | optional; repeatable | not set | Use an exact OBJECT_ID, or GRAPH:OBJECT_ID with --workspace; repeat as needed. |
| `--annotation-state` | text; `draft`, `validated`, `rejected`, `deferred`, `review_required` | optional; repeatable | not set | Include semantic annotations in one or more review states. |
| `--validated-only` | flag | optional | `False` | Include only human-validated semantic annotations. |
| `--logical-hints` | text; `confirmed_only`, `confirmed_then_candidates`, `include_candidates` | optional | not set | Include bounded logical hints for selected objects; disabled by default. |
| `--brief` | flag | optional | `False` | Print only compact orientation, coverage, gaps, and continuity identity. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Context packet, metadata expansion, packet diff, or impact result. Inspect identities, budgets, and omissions; expand can return partial output with status 1.

CLI entry point and delegated output renderers: [src/tarel/cli/context.py](../src/tarel/cli/context.py).

### tarel context prefix

Compile a query-independent graph or workspace scope for prompt caching.

Question-independent packet for an explicit graph/workspace scope. Keep its serialization unchanged for possible prompt-prefix reuse. Budgets can omit fields/objects even when a complete database was selected. TAREL does not guarantee a provider cache hit.

**Syntax**

```text
tarel context prefix [-h] [--namespace NAMESPACE] [--max-objects MAX_OBJECTS]
                            [--max-joins MAX_JOINS] [--max-fields-per-object MAX_FIELDS_PER_OBJECT]
                            [--max-characters MAX_CHARACTERS] [--workspace NAME] [--system SYSTEMS]
                            [--graph GRAPHS] [--area AREAS] [--scope-schema SCHEMAS] [--zone ZONES]
                            [--scope-object SCOPE_OBJECTS] [--focus FOCUSES]
                            [--annotation-state {draft,validated,rejected,deferred,review_required}]
                            [--validated-only]
                            [--logical-hints {confirmed_only,confirmed_then_candidates,include_candidates}]
                            [--brief] [--format {text,json}]
                            [name]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | optional; optional positional | not set | Graph name; omit it with --workspace NAME. |
| `--namespace, --schema` | text | optional | not set | Namespace/schema filter. |
| `--max-objects` | int | optional | `250` | Maximum selected objects. |
| `--max-joins` | int | optional | `500` | Maximum selected joins. |
| `--max-fields-per-object` | int | optional | `50` | Maximum fields per object. |
| `--max-characters` | int | optional | `500000` | Character budget; not a tokenizer-based token limit. |
| `--workspace` | text | optional | not set | Use this workspace's resolved scope instead of a single graph. |
| `--system` | text | optional; repeatable | not set | System scope selection. |
| `--graph` | text | optional; repeatable | not set | Graph names to include. |
| `--area` | text | optional; repeatable | not set | Area scope selection. |
| `--scope-schema` | text | optional; repeatable | not set | Workspace schema as GRAPH:NAMESPACE; repeat for a union. |
| `--zone` | text | optional; repeatable | not set | Zone scope selection. |
| `--scope-object` | text | optional; repeatable | not set | Hard workspace boundary as GRAPH:OBJECT_ID; repeat for a union. |
| `--focus` | text | optional; repeatable | not set | Limit a workspace operation to a current saved focus; repeat for a union. |
| `--annotation-state` | text; `draft`, `validated`, `rejected`, `deferred`, `review_required` | optional; repeatable | not set | Include semantic annotations in one or more review states. |
| `--validated-only` | flag | optional | `False` | Include only human-validated semantic annotations. |
| `--logical-hints` | text; `confirmed_only`, `confirmed_then_candidates`, `include_candidates` | optional | not set | Include bounded logical hints for selected objects; disabled by default. |
| `--brief` | flag | optional | `False` | Print only compact orientation, coverage, gaps, and continuity identity. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Context packet, metadata expansion, packet diff, or impact result. Inspect identities, budgets, and omissions; expand can return partial output with status 1.

CLI entry point and delegated output renderers: [src/tarel/cli/context.py](../src/tarel/cli/context.py).

### tarel context brief

Summarize one saved context packet for a continuing conversation.

**Syntax**

```text
tarel context brief [-h] [--format {text,json}] packet
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `packet` | Path | required | not set | Existing context packet path. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Context packet, metadata expansion, packet diff, or impact result. Inspect identities, budgets, and omissions; expand can return partial output with status 1.

CLI entry point and delegated output renderers: [src/tarel/cli/context.py](../src/tarel/cli/context.py).

### tarel context diff

Validate and compare two serialized context packets.

**Syntax**

```text
tarel context diff [-h] [--format {text,json}] left right
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `left` | Path | required | not set | First comparison input. |
| `right` | Path | required | not set | Second comparison input. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Context packet, metadata expansion, packet diff, or impact result. Inspect identities, budgets, and omissions; expand can return partial output with status 1.

CLI entry point and delegated output renderers: [src/tarel/cli/context.py](../src/tarel/cli/context.py).

### tarel context impact

Check whether one saved context packet is affected by the latest graph refresh.

An unknown impact is a distinct outcome; the main CLI returns exit code 1 for that result. Inspect the reported impact instead of assuming all non-error output proves compatibility.

**Syntax**

```text
tarel context impact [-h] --graph GRAPH [--format {text,json}] packet
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `packet` | Path | required | not set | Existing context packet path. |
| `--graph` | text | required | not set | Current local graph name. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Context packet, metadata expansion, packet diff, or impact result. Inspect identities, budgets, and omissions; expand can return partial output with status 1.

CLI entry point and delegated output renderers: [src/tarel/cli/context.py](../src/tarel/cli/context.py).

## grounding

**Source-aware grounding.** Combine a context packet with source identity, dialects, and selected lineage information.

Returns a grounding bundle. Registered logical sources contribute routing metadata without credentials. The harness still executes analytical queries.

Contract and workflow: [sdk.md](#python-sdk).

Example:

```bash
tarel grounding warehouse "customer revenue" --mode bm25 --format json
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel grounding`](#tarel-grounding) | Compile agent-ready context with source, dialect, and optional lineage identity. |

### tarel grounding

Compile agent-ready context with source, dialect, and optional lineage identity.

**Syntax**

```text
tarel grounding [-h] [--namespace NAMESPACE] [--lineage LINEAGES] [--source SOURCES]
                       [--trace TRACE_REFERENCE] [--lineage-limit LINEAGE_LIMIT]
                       [--lineage-mode {lexical,bm25,vector,hybrid}]
                       [--lineage-state {draft,review_required,validated}] [--seed-limit SEED_LIMIT]
                       [--max-objects MAX_OBJECTS] [--max-joins MAX_JOINS] [--max-hops MAX_HOPS]
                       [--max-trace-hops MAX_TRACE_HOPS]
                       [--max-fields-per-object MAX_FIELDS_PER_OBJECT]
                       [--max-characters MAX_CHARACTERS] [--mode {lexical,bm25,vector,hybrid}]
                       [--model MODEL_PATH] [--threads N_THREADS] [--workspace NAME]
                       [--system SYSTEMS] [--graph GRAPHS] [--area AREAS] [--scope-schema SCHEMAS]
                       [--zone ZONES] [--scope-object SCOPE_OBJECTS] [--focus FOCUSES]
                       [--annotation-state {draft,validated,rejected,deferred,review_required}]
                       [--validated-only]
                       [--logical-hints {confirmed_only,confirmed_then_candidates,include_candidates}]
                       [--format {text,json}]
                       [name] query
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | optional; optional positional | not set | Graph name; omit it with --workspace NAME. |
| `query` | text | required | not set | Analytical question or compact search query. |
| `--namespace, --schema` | text | optional | not set | Namespace/schema filter. |
| `--lineage` | text | optional; repeatable | not set | Lineage documents to include. |
| `--source` | text | optional; repeatable | not set | Select a logical execution source; repeat for multi-graph context. |
| `--trace` | text | optional | not set | Optional exact reference to trace. |
| `--lineage-limit` | int | optional | `8` | Maximum lineage matches. |
| `--lineage-mode` | text; `lexical`, `bm25`, `vector`, `hybrid` | optional | `bm25` | Lineage retrieval mode. |
| `--lineage-state` | text; `draft`, `review_required`, `validated` | optional; repeatable | not set | Allowed lineage review states. |
| `--seed-limit` | int | optional | `3` | Maximum retrieval seed count. |
| `--max-objects` | int | optional | `10` | Maximum selected objects. |
| `--max-joins` | int | optional | `12` | Maximum selected joins. |
| `--max-hops` | int | optional | `2` | Maximum traversal/expansion depth. |
| `--max-trace-hops` | int | optional | `12` | Maximum lineage-trace depth. |
| `--max-fields-per-object` | int | optional | `12` | Maximum fields per object. |
| `--max-characters` | int | optional | `24000` | Character budget; not a tokenizer-based token limit. |
| `--mode` | text; `lexical`, `bm25`, `vector`, `hybrid` | optional | `lexical` | Mode for this command; allowed values are listed separately. |
| `--model` | Path | optional | not set | Local embedding model path. |
| `--threads` | int | optional | not set | Local model thread count. |
| `--workspace` | text | optional | not set | Use this workspace's resolved scope instead of a single graph. |
| `--system` | text | optional; repeatable | not set | System scope selection. |
| `--graph` | text | optional; repeatable | not set | Graph names to include. |
| `--area` | text | optional; repeatable | not set | Area scope selection. |
| `--scope-schema` | text | optional; repeatable | not set | Workspace schema as GRAPH:NAMESPACE; repeat for a union. |
| `--zone` | text | optional; repeatable | not set | Zone scope selection. |
| `--scope-object` | text | optional; repeatable | not set | Hard workspace boundary as GRAPH:OBJECT_ID; repeat for a union. |
| `--focus` | text | optional; repeatable | not set | Limit a workspace operation to a current saved focus; repeat for a union. |
| `--annotation-state` | text; `draft`, `validated`, `rejected`, `deferred`, `review_required` | optional; repeatable | not set | Include semantic annotations in one or more review states. |
| `--validated-only` | flag | optional | `False` | Include only human-validated semantic annotations. |
| `--logical-hints` | text; `confirmed_only`, `confirmed_then_candidates`, `include_candidates` | optional | not set | Include bounded logical hints for selected objects; disabled by default. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Grounding bundle with stable and dynamic sections, source routing metadata, context, selected lineage, and hashes.

CLI entry point and delegated output renderers: [src/tarel/cli/grounding.py](../src/tarel/cli/grounding.py).

## annotation

**Annotation tasks and review.** Plan knowledge work, hand a task to the harness, apply a proposal, and review its meaning.

Plan/next do not invoke a generation provider. Optional samples/profiles can involve source reads. Apply writes a draft; validate/reject/defer and edit change reviewable knowledge. Table and field review must be considered separately.

Contract and workflow: [retail-demo.md](retail-demo.md).

Example:

```bash
tarel annotation plan --focus report-01 --format json
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel annotation plan`](#tarel-annotation-plan) | List annotation tasks without calling an API provider. |
 | [`tarel annotation next`](#tarel-annotation-next) | Return the next scoped annotation task as JSON for the coding agent. |
 | [`tarel annotation apply`](#tarel-annotation-apply) | Validate and apply one coding-agent proposal as a draft. |
 | [`tarel annotation list`](#tarel-annotation-list) | List object and field annotation proposals for review. |
 | [`tarel annotation show`](#tarel-annotation-show) | Show one object or field annotation and its review history. |
 | [`tarel annotation edit`](#tarel-annotation-edit) | Create or update one bounded object or field annotation. |
 | [`tarel annotation validate`](#tarel-annotation-validate) | Mark one annotation as validated by a human. |
 | [`tarel annotation reject`](#tarel-annotation-reject) | Mark one annotation as rejected by a human. |
 | [`tarel annotation defer`](#tarel-annotation-defer) | Mark one annotation as deferred by a human. |

### tarel annotation plan

List annotation tasks without calling an API provider.

Supply exactly one graph NAME or --focus FOCUS. The JSON plan includes count and tasks with graph_name, id, target, target_id, and context_documents.

**Syntax**

```text
tarel annotation plan [-h] [--focus FOCUS] [--namespace NAMESPACE] [--object OBJECTS]
                             [--limit LIMIT] [--include-annotated] [--knowledge {none,scoped}]
                             [--knowledge-document KNOWLEDGE_DOCUMENTS]
                             [--knowledge-workspace KNOWLEDGE_WORKSPACE]
                             [--max-knowledge-characters MAX_KNOWLEDGE_CHARACTERS]
                             [--format {text,json}]
                             [name]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | optional; optional positional | not set | Graph name. |
| `--focus` | text | optional | not set | Plan only objects reached by this focus. |
| `--namespace, --schema` | text | optional | not set | Namespace/schema filter. |
| `--object` | text | optional; repeatable | not set | Selected object references. |
| `--limit` | int | optional | not set | Maximum number of items for this operation. |
| `--include-annotated` | flag | optional | `False` | Plan complete objects instead of filling only missing annotations. |
| `--knowledge` | text; `none`, `scoped` | optional | `none` | Include no automatic documents (default) or resolve matching scopes. |
| `--knowledge-document` | text | optional; repeatable | not set | Include one document explicitly; repeat for more. |
| `--knowledge-workspace` | text | optional | not set | Workspace used to resolve system-scoped documents. |
| `--max-knowledge-characters` | int | optional | `12000` | Knowledge-document character budget. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Task plan, next task, proposal application, review listing, or annotation record/change. An empty plan is successful and does not mean every field was human-approved.

CLI entry point and delegated output renderers: [src/tarel/cli/annotation.py](../src/tarel/cli/annotation.py).

### tarel annotation next

Return the next scoped annotation task as JSON for the coding agent.

Supply exactly one graph NAME or --focus FOCUS. The returned workfile is intended for the harness model. Use graph annotate for direct provider execution.

**Syntax**

```text
tarel annotation next [-h] [--focus FOCUS] [--namespace NAMESPACE] [--object OBJECTS]
                             [--include-annotated] [--samples SAMPLES] [--profile-rows PROFILE_ROWS]
                             [--include-small-domain-values] [--config CONFIG]
                             [--knowledge {none,scoped}] [--knowledge-document KNOWLEDGE_DOCUMENTS]
                             [--knowledge-workspace KNOWLEDGE_WORKSPACE]
                             [--max-knowledge-characters MAX_KNOWLEDGE_CHARACTERS]
                             [--format {text,json}]
                             [name]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | optional; optional positional | not set | Graph name. |
| `--focus` | text | optional | not set | Return the next task inside this focus. |
| `--namespace, --schema` | text | optional | not set | Namespace/schema filter. |
| `--object` | text | optional; repeatable | not set | Selected object references. |
| `--include-annotated` | flag | optional | `False` | Return a complete-object task instead of a missing-only delta. |
| `--samples` | int | optional | `0` | Maximum requested sample rows; zero disables samples where supported. |
| `--profile-rows` | int | optional | `0` | Row budget for optional profiling. |
| `--include-small-domain-values` | flag | optional | `False` | Explicitly allow small-domain values in ephemeral annotation input. |
| `--config` | Path | optional | not set | Private connector configuration. |
| `--knowledge` | text; `none`, `scoped` | optional | `none` | Include no automatic documents (default) or resolve matching scopes. |
| `--knowledge-document` | text | optional; repeatable | not set | Include one document explicitly; repeat for more. |
| `--knowledge-workspace` | text | optional | not set | Workspace used to resolve system-scoped documents. |
| `--max-knowledge-characters` | int | optional | `12000` | Knowledge-document character budget. |
| `--format` | text; `text`, `json` | optional | `json` | Output format (default: json). |

**Result:** Task plan, next task, proposal application, review listing, or annotation record/change. An empty plan is successful and does not mean every field was human-approved.

CLI entry point and delegated output renderers: [src/tarel/cli/annotation.py](../src/tarel/cli/annotation.py).

### tarel annotation apply

Validate and apply one coding-agent proposal as a draft.

**Syntax**

```text
tarel annotation apply [-h] --input INPUT name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--input` | text | required | not set | Proposal JSON file or '-' for stdin. |

**Result:** Task plan, next task, proposal application, review listing, or annotation record/change. An empty plan is successful and does not mean every field was human-approved.

CLI entry point and delegated output renderers: [src/tarel/cli/annotation.py](../src/tarel/cli/annotation.py).

### tarel annotation list

List object and field annotation proposals for review.

**Syntax**

```text
tarel annotation list [-h] [--state {draft,validated,rejected,deferred,review_required}]
                             [--format {text,json}]
                             name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--state` | text; `draft`, `validated`, `rejected`, `deferred`, `review_required` | optional; repeatable | not set | Limit results to one or more review states. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Task plan, next task, proposal application, review listing, or annotation record/change. An empty plan is successful and does not mean every field was human-approved.

CLI entry point and delegated output renderers: [src/tarel/cli/annotation.py](../src/tarel/cli/annotation.py).

### tarel annotation show

Show one object or field annotation and its review history.

**Syntax**

```text
tarel annotation show [-h] [--format {text,json}] name target
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `target` | text | required | not set | Object, field, or stable node ID. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Task plan, next task, proposal application, review listing, or annotation record/change. An empty plan is successful and does not mean every field was human-approved.

CLI entry point and delegated output renderers: [src/tarel/cli/annotation.py](../src/tarel/cli/annotation.py).

### tarel annotation edit

Create or update one bounded object or field annotation.

**Syntax**

```text
tarel annotation edit [-h] --input INPUT --reason REASON [--format {text,json}] name target
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `target` | text | required | not set | Object, field, or stable node ID. |
| `--input` | text | required | not set | Patch JSON file or '-' for stdin. |
| `--reason` | text | required | not set | Human-readable reason for the decision or mutation. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Task plan, next task, proposal application, review listing, or annotation record/change. An empty plan is successful and does not mean every field was human-approved.

CLI entry point and delegated output renderers: [src/tarel/cli/annotation.py](../src/tarel/cli/annotation.py).

### tarel annotation validate

Mark one annotation as validated by a human.

**Syntax**

```text
tarel annotation validate [-h] --reason REASON [--include-fields] [--format {text,json}]
                                 name target
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `target` | text | required | not set | Object, field, or stable node ID. |
| `--reason` | text | required | not set | Human-readable reason for the decision or mutation. |
| `--include-fields` | flag | optional | `False` | Apply the decision to the selected table or view and to each of its fields that has a proposal; fields without a proposal stay unchanged. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Task plan, next task, proposal application, review listing, or annotation record/change. An empty plan is successful and does not mean every field was human-approved.

CLI entry point and delegated output renderers: [src/tarel/cli/annotation.py](../src/tarel/cli/annotation.py).

### tarel annotation reject

Mark one annotation as rejected by a human.

**Syntax**

```text
tarel annotation reject [-h] --reason REASON [--include-fields] [--format {text,json}]
                               name target
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `target` | text | required | not set | Object, field, or stable node ID. |
| `--reason` | text | required | not set | Human-readable reason for the decision or mutation. |
| `--include-fields` | flag | optional | `False` | Apply the decision to the selected table or view and to each of its fields that has a proposal; fields without a proposal stay unchanged. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Task plan, next task, proposal application, review listing, or annotation record/change. An empty plan is successful and does not mean every field was human-approved.

CLI entry point and delegated output renderers: [src/tarel/cli/annotation.py](../src/tarel/cli/annotation.py).

### tarel annotation defer

Mark one annotation as deferred by a human.

**Syntax**

```text
tarel annotation defer [-h] --reason REASON [--include-fields] [--format {text,json}]
                              name target
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `target` | text | required | not set | Object, field, or stable node ID. |
| `--reason` | text | required | not set | Human-readable reason for the decision or mutation. |
| `--include-fields` | flag | optional | `False` | Apply the decision to the selected table or view and to each of its fields that has a proposal; fields without a proposal stay unchanged. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Task plan, next task, proposal application, review listing, or annotation record/change. An empty plan is successful and does not mean every field was human-approved.

CLI entry point and delegated output renderers: [src/tarel/cli/annotation.py](../src/tarel/cli/annotation.py).

## relationship

**Physical relationships.** Propose, probe, discover, and review physical field relationships.

Check/discover can query a source. Discovery candidates need separate validation. An inferred join is not ETL data flow; name similarity alone is not proof.

Contract and workflow: [retail-demo.md](retail-demo.md).

Example:

```bash
tarel relationship list warehouse
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel relationship add`](#tarel-relationship-add) | Add a human-defined relationship candidate. |
 | [`tarel relationship check`](#tarel-relationship-check) | Run one bounded aggregate probe for a selected field pair. |
 | [`tarel relationship discover`](#tarel-relationship-discover) | Search a bounded neighborhood around one object for possible joins. |
 | [`tarel relationship list`](#tarel-relationship-list) | List stored human and inferred relationship candidates. |
 | [`tarel relationship validate`](#tarel-relationship-validate) | Mark one inferred relationship as validated by a human. |
 | [`tarel relationship reject`](#tarel-relationship-reject) | Mark one inferred relationship as rejected by a human. |

### tarel relationship add

Add a human-defined relationship candidate.

**Syntax**

```text
tarel relationship add [-h] --from FROM_REFERENCE --to TO_REFERENCE --reason REASON
                              [--validated] [--format {text,json}]
                              name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Local graph name. |
| `--from` | text | required | not set | Source endpoint reference. |
| `--to` | text | required | not set | Target endpoint reference. |
| `--reason` | text | required | not set | Human-readable reason for the decision or mutation. |
| `--validated` | flag | optional | `False` | Record the explicit validated state. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Relationship records, bounded pair-profile evidence, discovery candidates, or decision result. Validation is a separate explicit state change.

CLI entry point and delegated output renderers: [src/tarel/cli/relationship.py](../src/tarel/cli/relationship.py).

### tarel relationship check

Run one bounded aggregate probe for a selected field pair.

**Syntax**

```text
tarel relationship check [-h] --from FROM_REFERENCE --to TO_REFERENCE --config CONFIG
                                [--row-limit ROW_LIMIT] [--format {text,json}]
                                name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Local graph name. |
| `--from` | text | required | not set | Source endpoint reference. |
| `--to` | text | required | not set | Target endpoint reference. |
| `--config` | Path | required | not set | Path to private connector configuration. |
| `--row-limit` | int | optional | `10000` | Bound on source rows examined. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Relationship records, bounded pair-profile evidence, discovery candidates, or decision result. Validation is a separate explicit state change.

CLI entry point and delegated output renderers: [src/tarel/cli/relationship.py](../src/tarel/cli/relationship.py).

### tarel relationship discover

Search a bounded neighborhood around one object for possible joins.

**Syntax**

```text
tarel relationship discover [-h] --object OBJECT_REFERENCE [--field FIELD_NAME] --config
                                   CONFIG [--max-pairs MAX_PAIRS] [--row-limit ROW_LIMIT]
                                   [--min-source-coverage MIN_SOURCE_COVERAGE]
                                   [--min-overlap-count MIN_OVERLAP_COUNT]
                                   [--min-target-uniqueness MIN_TARGET_UNIQUENESS] [--dry-run]
                                   [--focus FOCUS] [--expand-one-hop] [--format {text,json}]
                                   name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Local graph name. |
| `--object` | text | required | not set | Qualified object reference. |
| `--field` | text | optional | not set | Field name within the selected object. |
| `--config` | Path | required | not set | Path to private connector configuration. |
| `--max-pairs` | int | optional | `20` | Candidate pair budget. |
| `--row-limit` | int | optional | `10000` | Bound on source rows examined. |
| `--min-source-coverage` | float | optional | `0.85` | Minimum sampled source coverage. |
| `--min-overlap-count` | int | optional | `3` | Minimum observed overlapping values. |
| `--min-target-uniqueness` | float | optional | `0.9` | Minimum sampled target uniqueness. |
| `--dry-run` | flag | optional | `False` | Plan/preview instead of applying this operation. |
| `--focus` | text | optional | not set | Restrict candidate pairs to objects reached by this focus. |
| `--expand-one-hop` | flag | optional | `False` | Also include objects connected by one observed foreign-key hop. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Relationship records, bounded pair-profile evidence, discovery candidates, or decision result. Validation is a separate explicit state change.

CLI entry point and delegated output renderers: [src/tarel/cli/relationship.py](../src/tarel/cli/relationship.py).

### tarel relationship list

List stored human and inferred relationship candidates.

**Syntax**

```text
tarel relationship list [-h] [--format {text,json}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Local graph name. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Relationship records, bounded pair-profile evidence, discovery candidates, or decision result. Validation is a separate explicit state change.

CLI entry point and delegated output renderers: [src/tarel/cli/relationship.py](../src/tarel/cli/relationship.py).

### tarel relationship validate

Mark one inferred relationship as validated by a human.

**Syntax**

```text
tarel relationship validate [-h] --reason REASON [--format {text,json}] name edge_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Local graph name. |
| `edge_id` | text | required | not set | Relationship candidate ID. |
| `--reason` | text | required | not set | Human-readable reason for the decision or mutation. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Relationship records, bounded pair-profile evidence, discovery candidates, or decision result. Validation is a separate explicit state change.

CLI entry point and delegated output renderers: [src/tarel/cli/relationship.py](../src/tarel/cli/relationship.py).

### tarel relationship reject

Mark one inferred relationship as rejected by a human.

**Syntax**

```text
tarel relationship reject [-h] --reason REASON [--format {text,json}] name edge_id
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Local graph name. |
| `edge_id` | text | required | not set | Relationship candidate ID. |
| `--reason` | text | required | not set | Human-readable reason for the decision or mutation. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Relationship records, bounded pair-profile evidence, discovery candidates, or decision result. Validation is a separate explicit state change.

CLI entry point and delegated output renderers: [src/tarel/cli/relationship.py](../src/tarel/cli/relationship.py).

## retrieval

**Retrieval model selection.** Select embedding and reranker models independently across local and HTTP providers.

Configure saves credential-free project choices without model calls or downloads. Models lists local artifacts or explicitly fetches a provider catalog. Settings reports the selection; reranking is off by default.

Contract and workflow: [local-retrieval.md](contracts.md#local-retrieval).

Example:

```bash
tarel retrieval settings --format json
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel retrieval settings`](#tarel-retrieval-settings) | Show credential-free retrieval settings. |
 | [`tarel retrieval configure`](#tarel-retrieval-configure) | Save model selection; does not download or index. |
 | [`tarel retrieval models`](#tarel-retrieval-models) | List supported local models or fetch a provider catalog. |

### tarel retrieval settings

Show credential-free retrieval settings.

**Syntax**

```text
tarel retrieval settings [-h] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Credential-free embedding/reranker selection or a task-specific model catalog.

CLI entry point and delegated output renderers: [src/tarel/cli/retrieval.py](../src/tarel/cli/retrieval.py).

### tarel retrieval configure

Save model selection; does not download or index.

**Syntax**

```text
tarel retrieval configure [-h] [--embedding-provider EMBEDDING_PROVIDER]
                                 [--embedding-model EMBEDDING_MODEL]
                                 [--embedding-model-path EMBEDDING_MODEL_PATH]
                                 [--reranker-provider RERANKER_PROVIDER]
                                 [--reranker-model RERANKER_MODEL]
                                 [--reranker-model-path RERANKER_MODEL_PATH]
                                 [--rerank-depth RERANK_DEPTH] [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--embedding-provider` | text | optional | not set | local or a configured HTTP profile; none disables reranking. |
| `--embedding-model` | text | optional | not set | Model ID for embedding. |
| `--embedding-model-path` | text | optional | not set | Explicit local GGUF path. |
| `--reranker-provider` | text | optional | not set | local or a configured HTTP profile; none disables reranking. |
| `--reranker-model` | text | optional | not set | Model ID for reranker. |
| `--reranker-model-path` | text | optional | not set | Explicit local GGUF path. |
| `--rerank-depth` | int | optional | not set | Maximum candidates to rerank (1–100). |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Credential-free embedding/reranker selection or a task-specific model catalog.

CLI entry point and delegated output renderers: [src/tarel/cli/retrieval.py](../src/tarel/cli/retrieval.py).

### tarel retrieval models

List supported local models or fetch a provider catalog.

**Syntax**

```text
tarel retrieval models [-h] [--provider PROVIDER] [--task {embedding,reranker}]
                              [--format {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--provider` | text | optional | `local` | Configured provider profile. |
| `--task` | text; `embedding`, `reranker` | optional | `embedding` | Requested retrieval model capability. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Credential-free embedding/reranker selection or a task-specific model catalog.

CLI entry point and delegated output renderers: [src/tarel/cli/retrieval.py](../src/tarel/cli/retrieval.py).

## Practical sequences

### Discover and annotate a source

```bash
tarel source check warehouse-prod
tarel source build warehouse-prod warehouse
tarel annotation plan warehouse --format json
tarel graph annotate warehouse --provider openrouter --dry-run
tarel graph annotate warehouse --provider openrouter
tarel annotation list warehouse
tarel ui warehouse --edit
```

The source profile and provider must already exist. A successful provider run produces proposals; use the explicit review commands to accept knowledge.

### Analyze ETL and trace a report

```bash
tarel lineage build sales-etl --source imports/sales-etl.json
tarel lineage analyze sales-etl --source imports/sales-etl.json --provider openrouter --review-passes 1
tarel lineage show sales-etl --view status
tarel lineage review sales-etl
tarel focus build report-01 --seed "<measure-reference>" --lineage sales-etl --max-hops 40
tarel annotation plan --focus report-01 --format json
```

Prepare canonical lineage input first. Scheduler order alone is insufficient evidence for physical data flow.

### Retrieve and keep a stable prefix

```bash
tarel search warehouse "customer revenue" --mode bm25
tarel context build warehouse "customer revenue" --mode bm25 --validated-only --format json
tarel context prefix warehouse --validated-only --format json
```

The harness serializes and reuses the prefix and appends changing material separately. Validate budgets, omissions, and revisions before reuse.

### Extend TAREL through a contract

```bash
tarel connector scaffold example-source --output ./example-source
tarel provider scaffold example-provider --output ./example-provider
```

These commands generate inactive code candidates. Follow the generated task documents, implement the contract, test, review, and then install the chosen package. Configuration of a new endpoint using an existing provider adapter does not need a new scaffold.


## Structured results and errors

JSON rendering is command-specific. Inspect --format defaults: some workfile commands emit structured JSON directly, whereas progress and status can use separate output channels. The following contract guide supplies the complete worked input documents and their invariants; serializer links define the exact runtime shape, including conditional fields.

| Output / input | Contract or serializer |
| --- | --- |
| Observed catalog | [CatalogResult](../src/tarel/connectors/contracts.py) |
| Stored graph and annotation | [GraphDocument](../src/tarel/graph/contracts.py), [annotation records](../src/tarel/annotations/contracts.py) |
| Context packet | [Packet contract](contracts.md#context-packets), [serializer](../src/tarel/context/output.py) |
| Grounding bundle | [GroundingBundle](../src/tarel/context/grounding.py) |
| Static lineage input/output | [Input](../src/tarel/lineage/source.py), [stored records](../src/tarel/lineage/contracts.py) |
| Runtime lineage | [Complete input and version rules](contracts.md#runtime-lineage) |
| Discovery proposals and observations | [Complete worked payloads](contracts.md#discovery-protocol) |
| Logical topology, mappings, entities and families | [Contracts and examples](contracts.md) |

### JSON example: annotation plan

For a graph with no eligible annotation tasks, `tarel annotation plan GRAPH --format json` emits:

```json
{"count": 0, "tasks": []}
```

Nonempty entries contain `graph_name`, `id`, `target`, `target_id`, and `context_documents`. Apply proposals to their owning graph; a workspace can contain identical target labels in different graphs.

### JSON example: context identity

This is a shape excerpt, not an importable packet. A complete packet has versioned stable/dynamic records and computed hashes:

```json
{"identity": {"stable_hash": "<sha256>", "dynamic_hash": "<sha256>", "packet_hash": "<sha256>"}}
```

Do not manufacture hashes or infer completeness from the presence of an identity. Validate the packet and inspect its omissions.

### Error recovery

| Failure category | Recovery |
| --- | --- |
| Missing resource/configuration | Check the local state root, resource name and private configuration; create/import the prerequisite first. |
| Invalid input or contract version | Use the complete contract shape and allowed fields. Do not silently rename or discard rejected fields. |
| Stale revision/index | Reload the current record; regenerate the dependent artifact/index and retry against its current revision. |
| Provider authentication/timeout/output | Correct the profile or endpoint, inspect the bounded retry policy, and resume only through the supported runner. |
| Scope, policy or review failure | Inspect the resolved scope and review state. Broader privileges or candidate inclusion are explicit choices. |
| Existing artifact | Use the documented refresh/replace workflow if available; create-only imports do not overwrite existing state. |

### Error code index

The entries below are generated from explicit domain Failure constructors in this source tree. The linked source gives the exact condition and message. Dynamically forwarded connector/provider codes are not a closed enum; clients should retain an unknown code and handle failure rather than assume this list exhausts every external system.

| Code | Defined at |
| --- | --- |
| `activation_blocked` | [sync/application.py](../src/tarel/sync/application.py#L424) |
| `activation_pending` | [sync/admin_application.py](../src/tarel/sync/admin_application.py#L203), [sync/application.py](../src/tarel/sync/application.py#L74) |
| `agent_setup_failed` | [tarel/agents.py](../src/tarel/agents.py#L59) |
| `agent_skill_exists` | [tarel/agents.py](../src/tarel/agents.py#L38) |
| `agent_skill_missing` | [tarel/agents.py](../src/tarel/agents.py#L48) |
| `ambiguous_connector` | [connectors/host.py](../src/tarel/connectors/host.py#L61) |
| `ambiguous_lineage_analyzer` | [lineage/analyzers.py](../src/tarel/lineage/analyzers.py#L61) |
| `ambiguous_lineage_reference` | [lineage/traversal.py](../src/tarel/lineage/traversal.py#L805), [lineage/traversal.py](../src/tarel/lineage/traversal.py#L823) |
| `ambiguous_logical_joins` | [logical_joins/application.py](../src/tarel/logical_joins/application.py#L240) |
| `ambiguous_retrieval_plugin` | [retrieval/plugins.py](../src/tarel/retrieval/plugins.py#L122) |
| `ambiguous_scope_selector` | [workspaces/scope.py](../src/tarel/workspaces/scope.py#L286) |
| `ambiguous_source_mapping` | [context/grounding_application.py](../src/tarel/context/grounding_application.py#L369) |
| `annotation_complete` | [annotations/tasks.py](../src/tarel/annotations/tasks.py#L122) |
| `annotation_not_found` | [annotations/review.py](../src/tarel/annotations/review.py#L356) |
| `annotation_sample_field_mismatch` | [annotations/tasks.py](../src/tarel/annotations/tasks.py#L274), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L279), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L295) |
| `annotation_sample_target_mismatch` | [annotations/tasks.py](../src/tarel/annotations/tasks.py#L250) |
| `architecture_required` | [ui/backend.py](../src/tarel/ui/backend.py#L119) |
| `architecture_scope` | [ui/backend.py](../src/tarel/ui/backend.py#L123) |
| `architecture_unavailable` | [ui/backend.py](../src/tarel/ui/backend.py#L468) |
| `batch_failed` | [annotations/runner.py](../src/tarel/annotations/runner.py#L103) |
| `bundle_component_unknown` | [bundle/catalog.py](../src/tarel/bundle/catalog.py#L128) |
| `bundle_direct_reference` | [bundle/resolve.py](../src/tarel/bundle/resolve.py#L167) |
| `bundle_hub_clash` | [bundle/catalog.py](../src/tarel/bundle/catalog.py#L114) |
| `bundle_hub_invalid` | [bundle/catalog.py](../src/tarel/bundle/catalog.py#L68) |
| `bundle_hub_missing` | [bundle/catalog.py](../src/tarel/bundle/catalog.py#L64) |
| `bundle_hub_package` | [bundle/catalog.py](../src/tarel/bundle/catalog.py#L100), [bundle/catalog.py](../src/tarel/bundle/catalog.py#L105) |
| `bundle_local_source` | [bundle/builder.py](../src/tarel/bundle/builder.py#L127) |
| `bundle_not_a_wheel` | [bundle/builder.py](../src/tarel/bundle/builder.py#L158) |
| `bundle_not_interactive` | [cli/bundle.py](../src/tarel/cli/bundle.py#L93) |
| `bundle_output_exists` | [bundle/application.py](../src/tarel/bundle/application.py#L50) |
| `bundle_output_folder` | [bundle/application.py](../src/tarel/bundle/application.py#L54) |
| `bundle_output_suffix` | [bundle/application.py](../src/tarel/bundle/application.py#L48) |
| `bundle_pip_unavailable` | [bundle/pip.py](../src/tarel/bundle/pip.py#L25), [bundle/resolve.py](../src/tarel/bundle/resolve.py#L265) |
| `bundle_profile_arch` | [bundle/targets.py](../src/tarel/bundle/targets.py#L106), [bundle/targets.py](../src/tarel/bundle/targets.py#L110) |
| `bundle_profile_invalid` | [bundle/targets.py](../src/tarel/bundle/targets.py#L59) |
| `bundle_profile_libc` | [bundle/targets.py](../src/tarel/bundle/targets.py#L75) |
| `bundle_profile_os` | [bundle/targets.py](../src/tarel/bundle/targets.py#L122) |
| `bundle_profile_python` | [bundle/targets.py](../src/tarel/bundle/targets.py#L65) |
| `bundle_recipe_conflict` | [cli/bundle.py](../src/tarel/cli/bundle.py#L146) |
| `bundle_recipe_format` | [bundle/contracts.py](../src/tarel/bundle/contracts.py#L172) |
| `bundle_recipe_invalid` | [bundle/contracts.py](../src/tarel/bundle/contracts.py#L168), [bundle/contracts.py](../src/tarel/bundle/contracts.py#L177), [bundle/contracts.py](../src/tarel/bundle/contracts.py#L180) |
| `bundle_recipe_missing` | [bundle/application.py](../src/tarel/bundle/application.py#L67) |
| `bundle_resolve_conflict` | [bundle/resolve.py](../src/tarel/bundle/resolve.py#L118) |
| `bundle_resolve_incomplete` | [bundle/resolve.py](../src/tarel/bundle/resolve.py#L130) |
| `bundle_target_arch` | [bundle/contracts.py](../src/tarel/bundle/contracts.py#L47) |
| `bundle_target_glibc` | [bundle/targets.py](../src/tarel/bundle/targets.py#L167) |
| `bundle_target_invalid` | [bundle/targets.py](../src/tarel/bundle/targets.py#L141) |
| `bundle_target_missing` | [bundle/contracts.py](../src/tarel/bundle/contracts.py#L101) |
| `bundle_target_os` | [bundle/contracts.py](../src/tarel/bundle/contracts.py#L45) |
| `bundle_target_python` | [bundle/contracts.py](../src/tarel/bundle/contracts.py#L50) |
| `bundle_target_required` | [cli/bundle.py](../src/tarel/cli/bundle.py#L156) |
| `bundle_target_version` | [bundle/contracts.py](../src/tarel/bundle/contracts.py#L56), [bundle/contracts.py](../src/tarel/bundle/contracts.py#L58), [bundle/contracts.py](../src/tarel/bundle/contracts.py#L60) |
| `bundle_version_mismatch` | [bundle/application.py](../src/tarel/bundle/application.py#L21) |
| `bundle_wheel_duplicate` | [bundle/resolve.py](../src/tarel/bundle/resolve.py#L236) |
| `bundle_wheel_metadata` | [bundle/resolve.py](../src/tarel/bundle/resolve.py#L234), [bundle/resolve.py](../src/tarel/bundle/resolve.py#L252) |
| `bundle_wheel_name` | [bundle/builder.py](../src/tarel/bundle/builder.py#L171) |
| `bundle_wheel_unsafe_path` | [bundle/builder.py](../src/tarel/bundle/builder.py#L212) |
| `catalog_not_found` | [connectors/catalog.py](../src/tarel/connectors/catalog.py#L51) |
| `change_report_conflict` | [graph/change_store.py](../src/tarel/graph/change_store.py#L26) |
| `change_report_not_found` | [graph/change_store.py](../src/tarel/graph/change_store.py#L52) |
| `change_report_save_failed` | [graph/change_store.py](../src/tarel/graph/change_store.py#L36) |
| `config_not_found` | [connectors/application.py](../src/tarel/connectors/application.py#L167), [connectors/application.py](../src/tarel/connectors/application.py#L176), [sources/application.py](../src/tarel/sources/application.py#L418) |
| `conflicting_annotation_filter` | [annotations/states.py](../src/tarel/annotations/states.py#L19) |
| `conflicting_annotation_samples` | [annotations/application.py](../src/tarel/annotations/application.py#L358) |
| `conflicting_workspace_scope` | [sdk/_scope.py](../src/tarel/sdk/_scope.py#L59), [sdk/_scope.py](../src/tarel/sdk/_scope.py#L79), [sdk/_scope.py](../src/tarel/sdk/_scope.py#L93) |
| `connection_failed` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L48), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L249) |
| `context_character_budget_too_small` | [context/compiler.py](../src/tarel/context/compiler.py#L489) |
| `context_graph_mismatch` | [context/packets.py](../src/tarel/context/packets.py#L215) |
| `context_object_not_found` | [context/compiler.py](../src/tarel/context/compiler.py#L257) |
| `context_packet_hash_mismatch` | [context/packets.py](../src/tarel/context/packets.py#L162) |
| `context_packet_not_found` | [context/packets.py](../src/tarel/context/packets.py#L122) |
| `database_not_found` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L251) |
| `dbt_manifest_not_found` | [lineage/dbt.py](../src/tarel/lineage/dbt.py#L36) |
| `demo_create_failed` | [tarel/demo.py](../src/tarel/demo.py#L73) |
| `demo_exists` | [tarel/demo.py](../src/tarel/demo.py#L51) |
| `derived_relation_already_reviewed` | [topology/contracts.py](../src/tarel/topology/contracts.py#L639) |
| `derived_relation_not_found` | [topology/application.py](../src/tarel/topology/application.py#L126) |
| `discovery_action_not_allowed` | [discovery/actions.py](../src/tarel/discovery/actions.py#L124), [discovery/actions.py](../src/tarel/discovery/actions.py#L133), [discovery/actions.py](../src/tarel/discovery/actions.py#L182), [discovery/actions.py](../src/tarel/discovery/actions.py#L190), [discovery/actions.py](../src/tarel/discovery/actions.py#L293), [discovery/actions.py](../src/tarel/discovery/actions.py#L298), [discovery/actions.py](../src/tarel/discovery/actions.py#L322), [discovery/actions.py](../src/tarel/discovery/actions.py#L377), [discovery/actions.py](../src/tarel/discovery/actions.py#L385), [discovery/actions.py](../src/tarel/discovery/actions.py#L398), [discovery/advice.py](../src/tarel/discovery/advice.py#L60) |
| `discovery_aggregates_not_allowed` | [discovery/checks.py](../src/tarel/discovery/checks.py#L113) |
| `discovery_candidate_exists` | [discovery/actions.py](../src/tarel/discovery/actions.py#L251) |
| `discovery_candidate_not_found` | [discovery/actions.py](../src/tarel/discovery/actions.py#L440), [discovery/promotion.py](../src/tarel/discovery/promotion.py#L109) |
| `discovery_exists` | [discovery/application.py](../src/tarel/discovery/application.py#L147) |
| `discovery_failed` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L82), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L320) |
| `discovery_field_not_found` | [discovery/checks.py](../src/tarel/discovery/checks.py#L35), [discovery/checks.py](../src/tarel/discovery/checks.py#L52), [discovery/checks.py](../src/tarel/discovery/checks.py#L163) |
| `discovery_graph_revision_mismatch` | [discovery/checks.py](../src/tarel/discovery/checks.py#L67), [discovery/checks.py](../src/tarel/discovery/checks.py#L156), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L62) |
| `discovery_not_found` | [discovery/store.py](../src/tarel/discovery/store.py#L63) |
| `discovery_observation_exists` | [discovery/actions.py](../src/tarel/discovery/actions.py#L354) |
| `discovery_promotion_failed` | [discovery/promotion.py](../src/tarel/discovery/promotion.py#L174), [discovery/promotion.py](../src/tarel/discovery/promotion.py#L225), [entity_resolution/discovery.py](../src/tarel/entity_resolution/discovery.py#L271), [entity_resolution/discovery.py](../src/tarel/entity_resolution/discovery.py#L281), [entity_resolution/discovery.py](../src/tarel/entity_resolution/discovery.py#L297), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L95) |
| `discovery_provider_not_enabled` | [discovery/advice.py](../src/tarel/discovery/advice.py#L49) |
| `discovery_save_failed` | [discovery/store.py](../src/tarel/discovery/store.py#L54), [discovery/store.py](../src/tarel/discovery/store.py#L106) |
| `discovery_source_graph_mismatch` | [discovery/checks.py](../src/tarel/discovery/checks.py#L100), [discovery/checks.py](../src/tarel/discovery/checks.py#L151) |
| `discovery_source_not_found` | [cli/discovery.py](../src/tarel/cli/discovery.py#L184) |
| `duplicate_focus` | [ui/backend.py](../src/tarel/ui/backend.py#L888) |
| `duplicate_focus_source` | [focus/application.py](../src/tarel/focus/application.py#L136) |
| `duplicate_lineage_definition` | [lineage/analysis_application.py](../src/tarel/lineage/analysis_application.py#L353) |
| `duplicate_lineage_name` | [context/grounding_application.py](../src/tarel/context/grounding_application.py#L341) |
| `duplicate_source_name` | [context/grounding_application.py](../src/tarel/context/grounding_application.py#L350) |
| `embedding_failed` | [retrieval/index.py](../src/tarel/retrieval/index.py#L346), [retrieval/index.py](../src/tarel/retrieval/index.py#L353), [retrieval/index.py](../src/tarel/retrieval/index.py#L879), [retrieval/vectors.py](../src/tarel/retrieval/vectors.py#L103), [retrieval/vectors.py](../src/tarel/retrieval/vectors.py#L106), [retrieval/vectors.py](../src/tarel/retrieval/vectors.py#L108) |
| `embedding_input_too_long` | [retrieval/remote.py](../src/tarel/retrieval/remote.py#L150) |
| `empty_context_scope` | [context/compiler.py](../src/tarel/context/compiler.py#L329) |
| `empty_context_selection` | [context/compiler.py](../src/tarel/context/compiler.py#L240) |
| `empty_query` | [tarel/search.py](../src/tarel/search.py#L221) |
| `empty_refresh_observation` | [graph/application.py](../src/tarel/graph/application.py#L280) |
| `empty_zone` | [ui/backend.py](../src/tarel/ui/backend.py#L1074) |
| `enrichment_not_allowed` | [sources/application.py](../src/tarel/sources/application.py#L373) |
| `entity_alias_group_exists` | [discovery/identity.py](../src/tarel/discovery/identity.py#L467) |
| `entity_alias_group_required` | [discovery/actions.py](../src/tarel/discovery/actions.py#L334), [discovery/identity.py](../src/tarel/discovery/identity.py#L494) |
| `entity_aliases_not_allowed` | [discovery/checks.py](../src/tarel/discovery/checks.py#L124), [discovery/checks.py](../src/tarel/discovery/checks.py#L135), [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L430), [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L441) |
| `entity_resolution_already_reviewed` | [entity_resolution/candidates.py](../src/tarel/entity_resolution/candidates.py#L462) |
| `entity_resolution_exists` | [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L61) |
| `entity_resolution_field_not_found` | [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L450), [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L461), [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L474), [entity_resolution/projection.py](../src/tarel/entity_resolution/projection.py#L25) |
| `entity_resolution_graph_revision_mismatch` | [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L277) |
| `entity_resolution_not_found` | [entity_resolution/store.py](../src/tarel/entity_resolution/store.py#L59) |
| `entity_resolution_object_not_found` | [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L191), [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L292) |
| `entity_resolution_save_failed` | [entity_resolution/store.py](../src/tarel/entity_resolution/store.py#L49) |
| `entity_resolution_source_not_found` | [cli/entity.py](../src/tarel/cli/entity.py#L117) |
| `entity_resolution_supersede_required` | [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L387) |
| `entity_resolution_superseded` | [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L252) |
| `expansion_budget_too_small` | [expansion/application.py](../src/tarel/expansion/application.py#L133) |
| `expansion_outside_scope` | [expansion/projections.py](../src/tarel/expansion/projections.py#L161), [expansion/projections.py](../src/tarel/expansion/projections.py#L246), [expansion/projections.py](../src/tarel/expansion/projections.py#L266) |
| `expansion_policy_excluded` | [expansion/projections.py](../src/tarel/expansion/projections.py#L201), [expansion/projections.py](../src/tarel/expansion/projections.py#L221), [expansion/projections.py](../src/tarel/expansion/projections.py#L312) |
| `expansion_target_not_found` | [expansion/projections.py](../src/tarel/expansion/projections.py#L93) |
| `expected_logical_topology_revision_required` | [topology/application.py](../src/tarel/topology/application.py#L59), [topology/application.py](../src/tarel/topology/application.py#L99) |
| `expected_reference_mapping_revision_required` | [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L270) |
| `expired_signing_key` | [sync/authorization.py](../src/tarel/sync/authorization.py#L92) |
| `export_not_allowed` | [sync/export.py](../src/tarel/sync/export.py#L236) |
| `family_proposal_model_required` | [object_families/proposals.py](../src/tarel/object_families/proposals.py#L85) |
| `family_proposals_exist` | [object_families/proposals.py](../src/tarel/object_families/proposals.py#L78), [object_families/proposals.py](../src/tarel/object_families/proposals.py#L155) |
| `family_proposals_lock_failed` | [object_families/proposals.py](../src/tarel/object_families/proposals.py#L487) |
| `family_proposals_locked` | [object_families/proposals.py](../src/tarel/object_families/proposals.py#L481) |
| `family_proposals_not_found` | [object_families/proposals.py](../src/tarel/object_families/proposals.py#L173) |
| `family_proposals_save_failed` | [object_families/proposals.py](../src/tarel/object_families/proposals.py#L460) |
| `family_proposals_started` | [object_families/proposals.py](../src/tarel/object_families/proposals.py#L222) |
| `field_not_found` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L345), [relationships/core.py](../src/tarel/relationships/core.py#L219) |
| `focus_not_found` | [focus/store.py](../src/tarel/focus/store.py#L37) |
| `focus_outside_scope` | [ui/backend.py](../src/tarel/ui/backend.py#L894) |
| `focus_save_failed` | [focus/store.py](../src/tarel/focus/store.py#L27) |
| `focus_stale` | [focus/application.py](../src/tarel/focus/application.py#L120), [focus/core.py](../src/tarel/focus/core.py#L118), [ui/backend.py](../src/tarel/ui/backend.py#L902) |
| `graph_busy` | [graph/store.py](../src/tarel/graph/store.py#L49) |
| `graph_cache_build_failed` | [graph/selective.py](../src/tarel/graph/selective.py#L420) |
| `graph_cache_changed_during_read` | [graph/selective.py](../src/tarel/graph/selective.py#L324) |
| `graph_changed_during_read` | [graph/selective.py](../src/tarel/graph/selective.py#L317), [graph/selective.py](../src/tarel/graph/selective.py#L340), [graph/selective.py](../src/tarel/graph/selective.py#L407), [ui/lazy_family_view.py](../src/tarel/ui/lazy_family_view.py#L93) |
| `graph_conflict` | [graph/application.py](../src/tarel/graph/application.py#L161), [graph/store.py](../src/tarel/graph/store.py#L65) |
| `graph_exists` | [graph/application.py](../src/tarel/graph/application.py#L83), [graph/store.py](../src/tarel/graph/store.py#L71) |
| `graph_in_multiple_systems` | [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L285) |
| `graph_mismatch` | [context/compiler.py](../src/tarel/context/compiler.py#L105) |
| `graph_name_mismatch` | [workspaces/core.py](../src/tarel/workspaces/core.py#L336) |
| `graph_not_found` | [graph/selective.py](../src/tarel/graph/selective.py#L525), [graph/store.py](../src/tarel/graph/store.py#L107), [workspaces/core.py](../src/tarel/workspaces/core.py#L334), [workspaces/core.py](../src/tarel/workspaces/core.py#L391), [workspaces/core.py](../src/tarel/workspaces/core.py#L501), [workspaces/core.py](../src/tarel/workspaces/core.py#L525) |
| `graph_object_not_found` | [graph/selective.py](../src/tarel/graph/selective.py#L143), [graph/selective.py](../src/tarel/graph/selective.py#L180) |
| `graph_outside_focus` | [relationships/application.py](../src/tarel/relationships/application.py#L117) |
| `graph_outside_scope` | [ui/backend.py](../src/tarel/ui/backend.py#L1063), [ui/backend.py](../src/tarel/ui/backend.py#L1171), [workspaces/scope.py](../src/tarel/workspaces/scope.py#L101), [workspaces/scope.py](../src/tarel/workspaces/scope.py#L308) |
| `graph_outside_system` | [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L314), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L347) |
| `graph_outside_workspace` | [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L369) |
| `graph_required` | [ui/backend.py](../src/tarel/ui/backend.py#L1058) |
| `graph_revision_mismatch` | [graph/selective.py](../src/tarel/graph/selective.py#L482) |
| `graph_save_failed` | [graph/store.py](../src/tarel/graph/store.py#L51), [graph/store.py](../src/tarel/graph/store.py#L99), [graph/store.py](../src/tarel/graph/store.py#L156) |
| `history_gap` | [sync/merge.py](../src/tarel/sync/merge.py#L74) |
| `identity_artifact_exists` | [discovery/identity.py](../src/tarel/discovery/identity.py#L425), [discovery/identity.py](../src/tarel/discovery/identity.py#L489) |
| `identity_inspection_budget_exceeded` | [discovery/identity.py](../src/tarel/discovery/identity.py#L416), [discovery/identity.py](../src/tarel/discovery/identity.py#L460), [discovery/identity.py](../src/tarel/discovery/identity.py#L484) |
| `identity_inventory_exists` | [discovery/identity.py](../src/tarel/discovery/identity.py#L404) |
| `identity_inventory_incomplete` | [discovery/identity.py](../src/tarel/discovery/identity.py#L455), [discovery/runs.py](../src/tarel/discovery/runs.py#L962) |
| `identity_inventory_required` | [discovery/identity.py](../src/tarel/discovery/identity.py#L412) |
| `identity_provider_orchestrator_required` | [discovery/advice.py](../src/tarel/discovery/advice.py#L54) |
| `identity_token_budget_exceeded` | [discovery/identity.py](../src/tarel/discovery/identity.py#L141) |
| `immutable_derived_relation` | [topology/application.py](../src/tarel/topology/application.py#L294), [topology/application.py](../src/tarel/topology/application.py#L307) |
| `immutable_semantic_concept` | [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L93), [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L104) |
| `inbox_not_found` | [sync/inbox.py](../src/tarel/sync/inbox.py#L40) |
| `incomplete_entity_evidence` | [entity_resolution/discovery.py](../src/tarel/entity_resolution/discovery.py#L58), [entity_resolution/discovery.py](../src/tarel/entity_resolution/discovery.py#L74), [entity_resolution/discovery.py](../src/tarel/entity_resolution/discovery.py#L145), [entity_resolution/discovery.py](../src/tarel/entity_resolution/discovery.py#L239) |
| `incomplete_entity_execution` | [entity_resolution/discovery.py](../src/tarel/entity_resolution/discovery.py#L63), [entity_resolution/discovery.py](../src/tarel/entity_resolution/discovery.py#L68) |
| `incomplete_family_proposal` | [object_families/proposals.py](../src/tarel/object_families/proposals.py#L291) |
| `incomplete_identity_validation` | [discovery/promotion.py](../src/tarel/discovery/promotion.py#L277) |
| `incomplete_query_linked_provenance` | [discovery/coverage.py](../src/tarel/discovery/coverage.py#L396), [discovery/coverage_application.py](../src/tarel/discovery/coverage_application.py#L163) |
| `incomplete_reference_mapping_evidence` | [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L80), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L85), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L324), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L340) |
| `incomplete_reference_mapping_manifest` | [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L73) |
| `incomplete_snapshot` | [sync/merge.py](../src/tarel/sync/merge.py#L46) |
| `incomplete_write_coverage` | [lineage/core.py](../src/tarel/lineage/core.py#L661) |
| `index_build_failed` | [retrieval/index.py](../src/tarel/retrieval/index.py#L393) |
| `index_checkpoint_failed` | [retrieval/checkpoint.py](../src/tarel/retrieval/checkpoint.py#L56), [retrieval/checkpoint.py](../src/tarel/retrieval/checkpoint.py#L148) |
| `index_not_found` | [retrieval/index.py](../src/tarel/retrieval/index.py#L525) |
| `index_policy_mismatch` | [retrieval/index.py](../src/tarel/retrieval/index.py#L549), [retrieval/index.py](../src/tarel/retrieval/index.py#L567) |
| `invalid_annotation_limit` | [annotations/application.py](../src/tarel/annotations/application.py#L118) |
| `invalid_annotation_mode` | [annotations/tasks.py](../src/tarel/annotations/tasks.py#L117) |
| `invalid_annotation_patch` | [annotations/review.py](../src/tarel/annotations/review.py#L92), [annotations/review.py](../src/tarel/annotations/review.py#L97), [annotations/review.py](../src/tarel/annotations/review.py#L99), [annotations/review.py](../src/tarel/annotations/review.py#L104), [annotations/review.py](../src/tarel/annotations/review.py#L109), [annotations/review.py](../src/tarel/annotations/review.py#L375), [annotations/review.py](../src/tarel/annotations/review.py#L386), [annotations/review.py](../src/tarel/annotations/review.py#L395) |
| `invalid_annotation_review` | [annotations/review.py](../src/tarel/annotations/review.py#L305), [annotations/review.py](../src/tarel/annotations/review.py#L309), [annotations/review.py](../src/tarel/annotations/review.py#L315), [annotations/review.py](../src/tarel/annotations/review.py#L322), [annotations/review.py](../src/tarel/annotations/review.py#L328), [annotations/review.py](../src/tarel/annotations/review.py#L340) |
| `invalid_annotation_samples` | [annotations/tasks.py](../src/tarel/annotations/tasks.py#L197), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L211), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L217), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L232), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L243), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L262), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L267), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L284), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L289), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L302) |
| `invalid_annotation_scope` | [annotations/review.py](../src/tarel/annotations/review.py#L211), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L142), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L151), [cli/annotation.py](../src/tarel/cli/annotation.py#L154) |
| `invalid_annotation_state` | [annotations/review.py](../src/tarel/annotations/review.py#L185), [annotations/review.py](../src/tarel/annotations/review.py#L410), [annotations/states.py](../src/tarel/annotations/states.py#L29) |
| `invalid_annotation_target` | [annotations/review.py](../src/tarel/annotations/review.py#L69) |
| `invalid_batch` | [annotations/runner.py](../src/tarel/annotations/runner.py#L44), [annotations/runner.py](../src/tarel/annotations/runner.py#L46) |
| `invalid_batch_size` | [retrieval/application.py](../src/tarel/retrieval/application.py#L92), [retrieval/index.py](../src/tarel/retrieval/index.py#L196), [retrieval/remote.py](../src/tarel/retrieval/remote.py#L158) |
| `invalid_binding_input` | [cli/binding.py](../src/tarel/cli/binding.py#L122) |
| `invalid_binding_limit` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L189) |
| `invalid_binding_scope` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L191), [object_bindings/application.py](../src/tarel/object_bindings/application.py#L196) |
| `invalid_binding_values` | [cli/binding.py](../src/tarel/cli/binding.py#L84), [object_bindings/application.py](../src/tarel/object_bindings/application.py#L185) |
| `invalid_bm25_weight` | [retrieval/ranking.py](../src/tarel/retrieval/ranking.py#L120), [retrieval/ranking.py](../src/tarel/retrieval/ranking.py#L130) |
| `invalid_catalog` | [connectors/catalog.py](../src/tarel/connectors/catalog.py#L53), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L55), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L62), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L82), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L88), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L93), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L97), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L104), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L109), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L118), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L123), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L132), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L138), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L144), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L159), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L186), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L188), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L215), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L224), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L229), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L237), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L246), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L253), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L260), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L265), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L272), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L280), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L285), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L291), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L297) |
| `invalid_change_report` | [graph/change_store.py](../src/tarel/graph/change_store.py#L58), [graph/change_store.py](../src/tarel/graph/change_store.py#L63), [graph/changes.py](../src/tarel/graph/changes.py#L46), [graph/changes.py](../src/tarel/graph/changes.py#L335), [graph/changes.py](../src/tarel/graph/changes.py#L343), [graph/refresh.py](../src/tarel/graph/refresh.py#L52), [graph/refresh.py](../src/tarel/graph/refresh.py#L54), [graph/refresh.py](../src/tarel/graph/refresh.py#L57), [graph/refresh.py](../src/tarel/graph/refresh.py#L128), [graph/refresh.py](../src/tarel/graph/refresh.py#L132), [graph/refresh.py](../src/tarel/graph/refresh.py#L509), [graph/refresh.py](../src/tarel/graph/refresh.py#L516) |
| `invalid_completeness` | [sync/publish_application.py](../src/tarel/sync/publish_application.py#L141), [sync/publish_application.py](../src/tarel/sync/publish_application.py#L145) |
| `invalid_config` | [connectors/application.py](../src/tarel/connectors/application.py#L58), [connectors/application.py](../src/tarel/connectors/application.py#L178), [connectors/application.py](../src/tarel/connectors/application.py#L200), [connectors/contracts.py](../src/tarel/connectors/contracts.py#L36), [connectors/contracts.py](../src/tarel/connectors/contracts.py#L40), [connectors/credentials.py](../src/tarel/connectors/credentials.py#L31), [connectors/credentials.py](../src/tarel/connectors/credentials.py#L47), [connectors/credentials.py](../src/tarel/connectors/credentials.py#L52), [connectors/credentials.py](../src/tarel/connectors/credentials.py#L64), [connectors/credentials.py](../src/tarel/connectors/credentials.py#L96), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L642), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L648), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L654), [providers/config.py](../src/tarel/providers/config.py#L286), [providers/config.py](../src/tarel/providers/config.py#L289), [providers/config.py](../src/tarel/providers/config.py#L408) |
| `invalid_config_reference` | [sources/application.py](../src/tarel/sources/application.py#L410), [sources/application.py](../src/tarel/sources/application.py#L426), [sources/contracts.py](../src/tarel/sources/contracts.py#L177), [sources/contracts.py](../src/tarel/sources/contracts.py#L193) |
| `invalid_connector_name` | [connectors/authoring.py](../src/tarel/connectors/authoring.py#L22) |
| `invalid_content_type` | [ui/server.py](../src/tarel/ui/server.py#L91) |
| `invalid_context_budget` | [context/compiler.py](../src/tarel/context/compiler.py#L409), [context/compiler.py](../src/tarel/context/compiler.py#L411), [context/compiler.py](../src/tarel/context/compiler.py#L413), [context/compiler.py](../src/tarel/context/compiler.py#L415), [context/compiler.py](../src/tarel/context/compiler.py#L417), [context/compiler.py](../src/tarel/context/compiler.py#L419), [context/compiler.py](../src/tarel/context/compiler.py#L424), [context/compiler.py](../src/tarel/context/compiler.py#L438), [context/compiler.py](../src/tarel/context/compiler.py#L443), [context/compiler.py](../src/tarel/context/compiler.py#L448), [context/compiler.py](../src/tarel/context/compiler.py#L453) |
| `invalid_context_expansion` | [cli/context_expand.py](../src/tarel/cli/context_expand.py#L47), [cli/context_expand.py](../src/tarel/cli/context_expand.py#L50), [expansion/contracts.py](../src/tarel/expansion/contracts.py#L179), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L315), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L318), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L327), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L336), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L338), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L340), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L346), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L356), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L359), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L380) |
| `invalid_context_kind` | [ui/query_tools.py](../src/tarel/ui/query_tools.py#L214) |
| `invalid_context_packet` | [context/guidance.py](../src/tarel/context/guidance.py#L564), [context/guidance.py](../src/tarel/context/guidance.py#L616), [context/guidance.py](../src/tarel/context/guidance.py#L632), [context/guidance.py](../src/tarel/context/guidance.py#L665), [context/guidance.py](../src/tarel/context/guidance.py#L707), [context/guidance.py](../src/tarel/context/guidance.py#L715), [context/guidance.py](../src/tarel/context/guidance.py#L723), [context/guidance.py](../src/tarel/context/guidance.py#L731), [context/packets.py](../src/tarel/context/packets.py#L127), [context/packets.py](../src/tarel/context/packets.py#L132), [context/packets.py](../src/tarel/context/packets.py#L294), [context/packets.py](../src/tarel/context/packets.py#L304), [context/packets.py](../src/tarel/context/packets.py#L311), [context/packets.py](../src/tarel/context/packets.py#L317), [context/packets.py](../src/tarel/context/packets.py#L322), [context/packets.py](../src/tarel/context/packets.py#L351), [context/packets.py](../src/tarel/context/packets.py#L355), [context/packets.py](../src/tarel/context/packets.py#L369), [context/packets.py](../src/tarel/context/packets.py#L375) |
| `invalid_context_selection` | [ui/query_tools.py](../src/tarel/ui/query_tools.py#L223), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L225) |
| `invalid_cube` | [semantics/cube.py](../src/tarel/semantics/cube.py#L68), [semantics/cube.py](../src/tarel/semantics/cube.py#L324), [semantics/cube.py](../src/tarel/semantics/cube.py#L332), [semantics/cube.py](../src/tarel/semantics/cube.py#L338) |
| `invalid_dbt_manifest` | [lineage/dbt.py](../src/tarel/lineage/dbt.py#L38), [lineage/dbt.py](../src/tarel/lineage/dbt.py#L358) |
| `invalid_dbt_mapping` | [cli/lineage.py](../src/tarel/cli/lineage.py#L579) |
| `invalid_demo_data` | [tarel/demo.py](../src/tarel/demo.py#L94) |
| `invalid_demo_version` | [tarel/demo.py](../src/tarel/demo.py#L45) |
| `invalid_discovery` | [cli/discovery.py](../src/tarel/cli/discovery.py#L188), [cli/discovery.py](../src/tarel/cli/discovery.py#L192), [discovery/_parse.py](../src/tarel/discovery/_parse.py#L47), [discovery/_parse.py](../src/tarel/discovery/_parse.py#L54), [discovery/_parse.py](../src/tarel/discovery/_parse.py#L60), [discovery/_parse.py](../src/tarel/discovery/_parse.py#L82), [discovery/_parse.py](../src/tarel/discovery/_parse.py#L93), [discovery/_parse.py](../src/tarel/discovery/_parse.py#L99), [discovery/_parse.py](../src/tarel/discovery/_parse.py#L105), [discovery/_parse.py](../src/tarel/discovery/_parse.py#L108), [discovery/_parse.py](../src/tarel/discovery/_parse.py#L114), [discovery/_parse.py](../src/tarel/discovery/_parse.py#L117), [discovery/_parse.py](../src/tarel/discovery/_parse.py#L131), [discovery/_parse.py](../src/tarel/discovery/_parse.py#L139), [discovery/_parse.py](../src/tarel/discovery/_parse.py#L144), [discovery/_parse.py](../src/tarel/discovery/_parse.py#L156), [discovery/actions.py](../src/tarel/discovery/actions.py#L257), [discovery/actions.py](../src/tarel/discovery/actions.py#L274), [discovery/actions.py](../src/tarel/discovery/actions.py#L345), [discovery/advice.py](../src/tarel/discovery/advice.py#L38), [discovery/application.py](../src/tarel/discovery/application.py#L93), [discovery/application.py](../src/tarel/discovery/application.py#L95), [discovery/application.py](../src/tarel/discovery/application.py#L100), [discovery/application.py](../src/tarel/discovery/application.py#L106), [discovery/application.py](../src/tarel/discovery/application.py#L201), [discovery/application.py](../src/tarel/discovery/application.py#L219), [discovery/checks.py](../src/tarel/discovery/checks.py#L38), [discovery/checks.py](../src/tarel/discovery/checks.py#L56), [discovery/checks.py](../src/tarel/discovery/checks.py#L95), [discovery/programs.py](../src/tarel/discovery/programs.py#L52), [discovery/programs.py](../src/tarel/discovery/programs.py#L57), [discovery/programs.py](../src/tarel/discovery/programs.py#L145), [discovery/programs.py](../src/tarel/discovery/programs.py#L223), [discovery/programs.py](../src/tarel/discovery/programs.py#L276), [discovery/programs.py](../src/tarel/discovery/programs.py#L281), [discovery/programs.py](../src/tarel/discovery/programs.py#L285), [discovery/programs.py](../src/tarel/discovery/programs.py#L291), [discovery/programs.py](../src/tarel/discovery/programs.py#L297), [discovery/programs.py](../src/tarel/discovery/programs.py#L302), [discovery/programs.py](../src/tarel/discovery/programs.py#L306), [discovery/programs.py](../src/tarel/discovery/programs.py#L310), [discovery/programs.py](../src/tarel/discovery/programs.py#L314), [discovery/programs.py](../src/tarel/discovery/programs.py#L318), [discovery/programs.py](../src/tarel/discovery/programs.py#L324), [discovery/programs.py](../src/tarel/discovery/programs.py#L328), [discovery/programs.py](../src/tarel/discovery/programs.py#L338), [discovery/programs.py](../src/tarel/discovery/programs.py#L344), [discovery/programs.py](../src/tarel/discovery/programs.py#L349), [discovery/programs.py](../src/tarel/discovery/programs.py#L354), [discovery/programs.py](../src/tarel/discovery/programs.py#L360), [discovery/programs.py](../src/tarel/discovery/programs.py#L366), [discovery/programs.py](../src/tarel/discovery/programs.py#L372), [discovery/programs.py](../src/tarel/discovery/programs.py#L377), [discovery/programs.py](../src/tarel/discovery/programs.py#L382), [discovery/programs.py](../src/tarel/discovery/programs.py#L387), [discovery/programs.py](../src/tarel/discovery/programs.py#L395), [discovery/programs.py](../src/tarel/discovery/programs.py#L402), [discovery/programs.py](../src/tarel/discovery/programs.py#L408), [discovery/runs.py](../src/tarel/discovery/runs.py#L132), [discovery/runs.py](../src/tarel/discovery/runs.py#L139), [discovery/runs.py](../src/tarel/discovery/runs.py#L146), [discovery/runs.py](../src/tarel/discovery/runs.py#L156), [discovery/runs.py](../src/tarel/discovery/runs.py#L167), [discovery/runs.py](../src/tarel/discovery/runs.py#L276), [discovery/runs.py](../src/tarel/discovery/runs.py#L279), [discovery/runs.py](../src/tarel/discovery/runs.py#L313), [discovery/runs.py](../src/tarel/discovery/runs.py#L317), [discovery/runs.py](../src/tarel/discovery/runs.py#L321), [discovery/runs.py](../src/tarel/discovery/runs.py#L325), [discovery/runs.py](../src/tarel/discovery/runs.py#L329), [discovery/runs.py](../src/tarel/discovery/runs.py#L387), [discovery/runs.py](../src/tarel/discovery/runs.py#L394), [discovery/runs.py](../src/tarel/discovery/runs.py#L422), [discovery/runs.py](../src/tarel/discovery/runs.py#L426), [discovery/runs.py](../src/tarel/discovery/runs.py#L435), [discovery/runs.py](../src/tarel/discovery/runs.py#L442), [discovery/runs.py](../src/tarel/discovery/runs.py#L447), [discovery/runs.py](../src/tarel/discovery/runs.py#L453), [discovery/runs.py](../src/tarel/discovery/runs.py#L457), [discovery/runs.py](../src/tarel/discovery/runs.py#L461), [discovery/runs.py](../src/tarel/discovery/runs.py#L465), [discovery/runs.py](../src/tarel/discovery/runs.py#L472), [discovery/runs.py](../src/tarel/discovery/runs.py#L617), [discovery/runs.py](../src/tarel/discovery/runs.py#L621), [discovery/runs.py](../src/tarel/discovery/runs.py#L626), [discovery/runs.py](../src/tarel/discovery/runs.py#L675), [discovery/runs.py](../src/tarel/discovery/runs.py#L727), [discovery/runs.py](../src/tarel/discovery/runs.py#L734), [discovery/runs.py](../src/tarel/discovery/runs.py#L740), [discovery/runs.py](../src/tarel/discovery/runs.py#L744), [discovery/runs.py](../src/tarel/discovery/runs.py#L753), [discovery/runs.py](../src/tarel/discovery/runs.py#L759), [discovery/runs.py](../src/tarel/discovery/runs.py#L765), [discovery/runs.py](../src/tarel/discovery/runs.py#L774), [discovery/runs.py](../src/tarel/discovery/runs.py#L780), [discovery/runs.py](../src/tarel/discovery/runs.py#L788), [discovery/runs.py](../src/tarel/discovery/runs.py#L836), [discovery/runs.py](../src/tarel/discovery/runs.py#L841), [discovery/runs.py](../src/tarel/discovery/runs.py#L845), [discovery/runs.py](../src/tarel/discovery/runs.py#L855), [discovery/runs.py](../src/tarel/discovery/runs.py#L859), [discovery/runs.py](../src/tarel/discovery/runs.py#L867), [discovery/runs.py](../src/tarel/discovery/runs.py#L872), [discovery/runs.py](../src/tarel/discovery/runs.py#L883), [discovery/runs.py](../src/tarel/discovery/runs.py#L895), [discovery/runs.py](../src/tarel/discovery/runs.py#L900), [discovery/runs.py](../src/tarel/discovery/runs.py#L915), [discovery/runs.py](../src/tarel/discovery/runs.py#L922), [discovery/runs.py](../src/tarel/discovery/runs.py#L937), [discovery/runs.py](../src/tarel/discovery/runs.py#L944), [discovery/runs.py](../src/tarel/discovery/runs.py#L951), [discovery/store.py](../src/tarel/discovery/store.py#L67), [discovery/store.py](../src/tarel/discovery/store.py#L71), [discovery/store.py](../src/tarel/discovery/store.py#L74) |
| `invalid_discovery_id` | [discovery/store.py](../src/tarel/discovery/store.py#L91) |
| `invalid_discovery_promotion` | [discovery/promotion.py](../src/tarel/discovery/promotion.py#L59), [discovery/promotion.py](../src/tarel/discovery/promotion.py#L65), [discovery/promotion.py](../src/tarel/discovery/promotion.py#L76), [discovery/promotion.py](../src/tarel/discovery/promotion.py#L88), [discovery/promotion.py](../src/tarel/discovery/promotion.py#L114), [discovery/promotion.py](../src/tarel/discovery/promotion.py#L124), [discovery/promotion.py](../src/tarel/discovery/promotion.py#L197), [entity_resolution/discovery.py](../src/tarel/entity_resolution/discovery.py#L46), [entity_resolution/discovery.py](../src/tarel/entity_resolution/discovery.py#L51), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L52), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L57), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L67) |
| `invalid_enrichment_permission` | [sources/contracts.py](../src/tarel/sources/contracts.py#L70), [sources/contracts.py](../src/tarel/sources/contracts.py#L143) |
| `invalid_enrichment_policy` | [sources/contracts.py](../src/tarel/sources/contracts.py#L150), [sources/contracts.py](../src/tarel/sources/contracts.py#L157) |
| `invalid_entity_alias_evidence` | [discovery/identity.py](../src/tarel/discovery/identity.py#L473), [discovery/identity.py](../src/tarel/discovery/identity.py#L502) |
| `invalid_entity_alias_group` | [discovery/identity.py](../src/tarel/discovery/identity.py#L251), [discovery/identity.py](../src/tarel/discovery/identity.py#L257) |
| `invalid_entity_reflection` | [discovery/actions.py](../src/tarel/discovery/actions.py#L223) |
| `invalid_entity_resolution` | [cli/entity.py](../src/tarel/cli/entity.py#L122), [cli/entity.py](../src/tarel/cli/entity.py#L127), [entity_resolution/_parse.py](../src/tarel/entity_resolution/_parse.py#L32), [entity_resolution/_parse.py](../src/tarel/entity_resolution/_parse.py#L40), [entity_resolution/_parse.py](../src/tarel/entity_resolution/_parse.py#L49), [entity_resolution/_parse.py](../src/tarel/entity_resolution/_parse.py#L59), [entity_resolution/_parse.py](../src/tarel/entity_resolution/_parse.py#L69), [entity_resolution/_parse.py](../src/tarel/entity_resolution/_parse.py#L79), [entity_resolution/_parse.py](../src/tarel/entity_resolution/_parse.py#L88), [entity_resolution/_parse.py](../src/tarel/entity_resolution/_parse.py#L97), [entity_resolution/_parse.py](../src/tarel/entity_resolution/_parse.py#L103), [entity_resolution/_parse.py](../src/tarel/entity_resolution/_parse.py#L112), [entity_resolution/_parse.py](../src/tarel/entity_resolution/_parse.py#L121), [entity_resolution/_parse.py](../src/tarel/entity_resolution/_parse.py#L127), [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L177), [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L284), [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L304), [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L318), [entity_resolution/candidates.py](../src/tarel/entity_resolution/candidates.py#L138), [entity_resolution/candidates.py](../src/tarel/entity_resolution/candidates.py#L147), [entity_resolution/candidates.py](../src/tarel/entity_resolution/candidates.py#L152), [entity_resolution/candidates.py](../src/tarel/entity_resolution/candidates.py#L162), [entity_resolution/candidates.py](../src/tarel/entity_resolution/candidates.py#L208), [entity_resolution/candidates.py](../src/tarel/entity_resolution/candidates.py#L305), [entity_resolution/candidates.py](../src/tarel/entity_resolution/candidates.py#L322), [entity_resolution/candidates.py](../src/tarel/entity_resolution/candidates.py#L334), [entity_resolution/candidates.py](../src/tarel/entity_resolution/candidates.py#L342), [entity_resolution/candidates.py](../src/tarel/entity_resolution/candidates.py#L350), [entity_resolution/candidates.py](../src/tarel/entity_resolution/candidates.py#L355), [entity_resolution/candidates.py](../src/tarel/entity_resolution/candidates.py#L385), [entity_resolution/candidates.py](../src/tarel/entity_resolution/candidates.py#L393), [entity_resolution/candidates.py](../src/tarel/entity_resolution/candidates.py#L403), [entity_resolution/candidates.py](../src/tarel/entity_resolution/candidates.py#L409), [entity_resolution/candidates.py](../src/tarel/entity_resolution/candidates.py#L420), [entity_resolution/candidates.py](../src/tarel/entity_resolution/candidates.py#L434), [entity_resolution/candidates.py](../src/tarel/entity_resolution/candidates.py#L439), [entity_resolution/candidates.py](../src/tarel/entity_resolution/candidates.py#L447), [entity_resolution/evidence.py](../src/tarel/entity_resolution/evidence.py#L54), [entity_resolution/evidence.py](../src/tarel/entity_resolution/evidence.py#L59), [entity_resolution/evidence.py](../src/tarel/entity_resolution/evidence.py#L65), [entity_resolution/evidence.py](../src/tarel/entity_resolution/evidence.py#L262), [entity_resolution/evidence.py](../src/tarel/entity_resolution/evidence.py#L290), [entity_resolution/evidence.py](../src/tarel/entity_resolution/evidence.py#L347), [entity_resolution/evidence.py](../src/tarel/entity_resolution/evidence.py#L357), [entity_resolution/evidence.py](../src/tarel/entity_resolution/evidence.py#L378), [entity_resolution/evidence.py](../src/tarel/entity_resolution/evidence.py#L394), [entity_resolution/evidence.py](../src/tarel/entity_resolution/evidence.py#L399), [entity_resolution/evidence.py](../src/tarel/entity_resolution/evidence.py#L404), [entity_resolution/evidence.py](../src/tarel/entity_resolution/evidence.py#L420), [entity_resolution/evidence.py](../src/tarel/entity_resolution/evidence.py#L426), [entity_resolution/evidence.py](../src/tarel/entity_resolution/evidence.py#L437), [entity_resolution/evidence.py](../src/tarel/entity_resolution/evidence.py#L442), [entity_resolution/store.py](../src/tarel/entity_resolution/store.py#L64), [entity_resolution/store.py](../src/tarel/entity_resolution/store.py#L69), [entity_resolution/store.py](../src/tarel/entity_resolution/store.py#L75) |
| `invalid_entity_resolution_id` | [entity_resolution/store.py](../src/tarel/entity_resolution/store.py#L97) |
| `invalid_entity_resolution_import` | [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L44) |
| `invalid_entity_resolution_mode` | [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L119), [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L172) |
| `invalid_entity_resolution_supersede` | [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L395) |
| `invalid_entrypoint` | [connectors/host.py](../src/tarel/connectors/host.py#L70), [connectors/host.py](../src/tarel/connectors/host.py#L129), [connectors/host.py](../src/tarel/connectors/host.py#L141), [connectors/host.py](../src/tarel/connectors/host.py#L168) |
| `invalid_expansion_input` | [cli/context_expand.py](../src/tarel/cli/context_expand.py#L88), [expansion/projections.py](../src/tarel/expansion/projections.py#L61), [expansion/projections.py](../src/tarel/expansion/projections.py#L173) |
| `invalid_expansion_stdin` | [cli/context_expand.py](../src/tarel/cli/context_expand.py#L42) |
| `invalid_family_proposals` | [object_families/proposal_contracts.py](../src/tarel/object_families/proposal_contracts.py#L33), [object_families/proposals.py](../src/tarel/object_families/proposals.py#L177) |
| `invalid_field_reference` | [workspaces/core.py](../src/tarel/workspaces/core.py#L519) |
| `invalid_focus` | [focus/contracts.py](../src/tarel/focus/contracts.py#L140), [focus/contracts.py](../src/tarel/focus/contracts.py#L155), [focus/contracts.py](../src/tarel/focus/contracts.py#L161), [focus/contracts.py](../src/tarel/focus/contracts.py#L163), [focus/contracts.py](../src/tarel/focus/contracts.py#L165), [focus/contracts.py](../src/tarel/focus/contracts.py#L171), [focus/contracts.py](../src/tarel/focus/contracts.py#L174), [focus/contracts.py](../src/tarel/focus/contracts.py#L178), [focus/contracts.py](../src/tarel/focus/contracts.py#L180), [focus/contracts.py](../src/tarel/focus/contracts.py#L183), [focus/contracts.py](../src/tarel/focus/contracts.py#L185), [focus/contracts.py](../src/tarel/focus/contracts.py#L192), [focus/contracts.py](../src/tarel/focus/contracts.py#L197), [focus/contracts.py](../src/tarel/focus/contracts.py#L235), [focus/contracts.py](../src/tarel/focus/contracts.py#L257), [focus/contracts.py](../src/tarel/focus/contracts.py#L271), [focus/contracts.py](../src/tarel/focus/contracts.py#L276), [focus/contracts.py](../src/tarel/focus/contracts.py#L282), [focus/contracts.py](../src/tarel/focus/contracts.py#L288), [focus/contracts.py](../src/tarel/focus/contracts.py#L294), [focus/contracts.py](../src/tarel/focus/contracts.py#L300), [focus/contracts.py](../src/tarel/focus/contracts.py#L306), [focus/store.py](../src/tarel/focus/store.py#L39), [focus/store.py](../src/tarel/focus/store.py#L41), [focus/store.py](../src/tarel/focus/store.py#L44) |
| `invalid_focus_name` | [focus/store.py](../src/tarel/focus/store.py#L56) |
| `invalid_focus_scope` | [relationships/application.py](../src/tarel/relationships/application.py#L106) |
| `invalid_graph` | [graph/contracts.py](../src/tarel/graph/contracts.py#L101), [graph/contracts.py](../src/tarel/graph/contracts.py#L138), [graph/contracts.py](../src/tarel/graph/contracts.py#L140), [graph/contracts.py](../src/tarel/graph/contracts.py#L171), [graph/contracts.py](../src/tarel/graph/contracts.py#L222), [graph/contracts.py](../src/tarel/graph/contracts.py#L240), [graph/contracts.py](../src/tarel/graph/contracts.py#L244), [graph/contracts.py](../src/tarel/graph/contracts.py#L250), [graph/contracts.py](../src/tarel/graph/contracts.py#L258), [graph/contracts.py](../src/tarel/graph/contracts.py#L264), [graph/contracts.py](../src/tarel/graph/contracts.py#L272), [graph/contracts.py](../src/tarel/graph/contracts.py#L275), [graph/contracts.py](../src/tarel/graph/contracts.py#L282), [graph/selective.py](../src/tarel/graph/selective.py#L338), [graph/selective.py](../src/tarel/graph/selective.py#L527), [graph/store.py](../src/tarel/graph/store.py#L109), [graph/store.py](../src/tarel/graph/store.py#L111) |
| `invalid_graph_cache` | [graph/selective.py](../src/tarel/graph/selective.py#L568) |
| `invalid_graph_limit` | [retrieval/application.py](../src/tarel/retrieval/application.py#L334) |
| `invalid_graph_name` | [graph/change_store.py](../src/tarel/graph/change_store.py#L73), [graph/store.py](../src/tarel/graph/store.py#L86), [graph/store.py](../src/tarel/graph/store.py#L225), [retrieval/index.py](../src/tarel/retrieval/index.py#L780) |
| `invalid_graph_object` | [workspaces/core.py](../src/tarel/workspaces/core.py#L552) |
| `invalid_graph_page` | [graph/selective.py](../src/tarel/graph/selective.py#L245) |
| `invalid_graph_revision` | [graph/change_store.py](../src/tarel/graph/change_store.py#L75) |
| `invalid_graph_selection` | [graph/selective.py](../src/tarel/graph/selective.py#L128), [graph/selective.py](../src/tarel/graph/selective.py#L164), [graph/selective.py](../src/tarel/graph/selective.py#L169), [graph/selective.py](../src/tarel/graph/selective.py#L475), [graph/selective.py](../src/tarel/graph/selective.py#L477) |
| `invalid_grounding_limit` | [sdk/grounding.py](../src/tarel/sdk/grounding.py#L151) |
| `invalid_grounding_scope` | [sdk/grounding.py](../src/tarel/sdk/grounding.py#L62), [sdk/grounding.py](../src/tarel/sdk/grounding.py#L90), [sdk/grounding.py](../src/tarel/sdk/grounding.py#L101), [sdk/grounding.py](../src/tarel/sdk/grounding.py#L212), [sdk/grounding.py](../src/tarel/sdk/grounding.py#L218) |
| `invalid_identity_candidate` | [discovery/runs.py](../src/tarel/discovery/runs.py#L969), [discovery/runs.py](../src/tarel/discovery/runs.py#L974), [discovery/runs.py](../src/tarel/discovery/runs.py#L985) |
| `invalid_identity_inspection` | [discovery/identity.py](../src/tarel/discovery/identity.py#L385), [discovery/identity.py](../src/tarel/discovery/identity.py#L525), [discovery/identity.py](../src/tarel/discovery/identity.py#L532), [discovery/identity.py](../src/tarel/discovery/identity.py#L540), [discovery/identity.py](../src/tarel/discovery/identity.py#L556), [discovery/identity.py](../src/tarel/discovery/identity.py#L564), [discovery/identity.py](../src/tarel/discovery/identity.py#L572), [discovery/identity.py](../src/tarel/discovery/identity.py#L580), [discovery/identity.py](../src/tarel/discovery/identity.py#L591), [discovery/identity.py](../src/tarel/discovery/identity.py#L599), [discovery/identity.py](../src/tarel/discovery/identity.py#L604), [discovery/identity.py](../src/tarel/discovery/identity.py#L629), [discovery/identity.py](../src/tarel/discovery/identity.py#L634), [discovery/identity.py](../src/tarel/discovery/identity.py#L642), [discovery/identity.py](../src/tarel/discovery/identity.py#L647), [discovery/identity.py](../src/tarel/discovery/identity.py#L655), [discovery/runs.py](../src/tarel/discovery/runs.py#L803), [discovery/runs.py](../src/tarel/discovery/runs.py#L812), [discovery/runs.py](../src/tarel/discovery/runs.py#L827) |
| `invalid_identity_inventory` | [discovery/checks.py](../src/tarel/discovery/checks.py#L166), [discovery/identity.py](../src/tarel/discovery/identity.py#L106), [discovery/identity.py](../src/tarel/discovery/identity.py#L131), [discovery/identity.py](../src/tarel/discovery/identity.py#L136) |
| `invalid_identity_inventory_page` | [discovery/identity.py](../src/tarel/discovery/identity.py#L187), [discovery/identity.py](../src/tarel/discovery/identity.py#L192), [discovery/identity.py](../src/tarel/discovery/identity.py#L421), [discovery/identity.py](../src/tarel/discovery/identity.py#L440), [discovery/identity.py](../src/tarel/discovery/identity.py#L446) |
| `invalid_index` | [retrieval/index.py](../src/tarel/retrieval/index.py#L297), [retrieval/index.py](../src/tarel/retrieval/index.py#L446), [retrieval/index.py](../src/tarel/retrieval/index.py#L533), [retrieval/index.py](../src/tarel/retrieval/index.py#L563), [retrieval/index.py](../src/tarel/retrieval/index.py#L637), [retrieval/index.py](../src/tarel/retrieval/index.py#L651), [retrieval/index.py](../src/tarel/retrieval/index.py#L762), [retrieval/index.py](../src/tarel/retrieval/index.py#L926), [retrieval/index.py](../src/tarel/retrieval/index.py#L932), [retrieval/vectors.py](../src/tarel/retrieval/vectors.py#L52), [retrieval/vectors.py](../src/tarel/retrieval/vectors.py#L54) |
| `invalid_index_checkpoint` | [retrieval/checkpoint.py](../src/tarel/retrieval/checkpoint.py#L86), [retrieval/checkpoint.py](../src/tarel/retrieval/checkpoint.py#L104), [retrieval/checkpoint.py](../src/tarel/retrieval/checkpoint.py#L124), [retrieval/index.py](../src/tarel/retrieval/index.py#L810), [retrieval/index.py](../src/tarel/retrieval/index.py#L830) |
| `invalid_index_namespace` | [retrieval/index.py](../src/tarel/retrieval/index.py#L179) |
| `invalid_index_request` | [ui/backend.py](../src/tarel/ui/backend.py#L553) |
| `invalid_knowledge` | [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L142), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L154), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L160), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L192), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L196), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L198), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L201), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L259), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L261), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L317), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L325), [knowledge/store.py](../src/tarel/knowledge/store.py#L56), [knowledge/store.py](../src/tarel/knowledge/store.py#L61) |
| `invalid_knowledge_budget` | [knowledge/core.py](../src/tarel/knowledge/core.py#L38) |
| `invalid_knowledge_evidence` | [annotations/apply.py](../src/tarel/annotations/apply.py#L175), [annotations/apply.py](../src/tarel/annotations/apply.py#L180) |
| `invalid_knowledge_id` | [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L254), [knowledge/store.py](../src/tarel/knowledge/store.py#L73) |
| `invalid_knowledge_mode` | [knowledge/core.py](../src/tarel/knowledge/core.py#L33) |
| `invalid_knowledge_scope` | [knowledge/application.py](../src/tarel/knowledge/application.py#L210), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L40), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L47), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L51), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L280), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L283), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L290), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L295), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L301), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L306), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L311) |
| `invalid_knowledge_source` | [knowledge/application.py](../src/tarel/knowledge/application.py#L61) |
| `invalid_knowledge_state` | [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L266) |
| `invalid_limit` | [retrieval/ranking.py](../src/tarel/retrieval/ranking.py#L59), [retrieval/search_application.py](../src/tarel/retrieval/search_application.py#L58), [retrieval/search_application.py](../src/tarel/retrieval/search_application.py#L131), [tarel/search.py](../src/tarel/search.py#L218) |
| `invalid_lineage` | [lineage/contracts.py](../src/tarel/lineage/contracts.py#L367), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L414), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L438), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L443), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L459), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L462), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L475), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L478), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L480), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L490), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L496), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L507), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L526), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L528), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L535), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L537), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L541), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L562), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L570), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L597), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L599), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L602), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L607), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L609), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L620), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L672), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L694), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L791), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L809), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L811), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L824), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L826), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L830), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L839), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L841), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L846), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L852), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L858), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L871), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L879), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L889), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L898), [lineage/core.py](../src/tarel/lineage/core.py#L714), [lineage/store.py](../src/tarel/lineage/store.py#L52), [lineage/store.py](../src/tarel/lineage/store.py#L54), [lineage/store.py](../src/tarel/lineage/store.py#L57) |
| `invalid_lineage_analysis_cache` | [lineage/analysis_application.py](../src/tarel/lineage/analysis_application.py#L449), [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L64), [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L70), [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L81), [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L89), [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L117), [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L126), [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L138), [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L143), [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L201), [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L212) |
| `invalid_lineage_analysis_failure` | [lineage/core.py](../src/tarel/lineage/core.py#L329) |
| `invalid_lineage_analyzer` | [lineage/analysis_application.py](../src/tarel/lineage/analysis_application.py#L218), [lineage/analyzers.py](../src/tarel/lineage/analyzers.py#L72) |
| `invalid_lineage_change` | [lineage/refresh.py](../src/tarel/lineage/refresh.py#L105), [lineage/refresh.py](../src/tarel/lineage/refresh.py#L107), [lineage/refresh.py](../src/tarel/lineage/refresh.py#L181), [lineage/refresh.py](../src/tarel/lineage/refresh.py#L185), [lineage/refresh.py](../src/tarel/lineage/refresh.py#L943), [lineage/refresh.py](../src/tarel/lineage/refresh.py#L949), [lineage/refresh.py](../src/tarel/lineage/refresh.py#L956), [lineage/refresh.py](../src/tarel/lineage/refresh.py#L962) |
| `invalid_lineage_change_report` | [lineage/change_store.py](../src/tarel/lineage/change_store.py#L57), [lineage/change_store.py](../src/tarel/lineage/change_store.py#L62) |
| `invalid_lineage_input` | [lineage/source.py](../src/tarel/lineage/source.py#L148), [lineage/source.py](../src/tarel/lineage/source.py#L153), [lineage/source.py](../src/tarel/lineage/source.py#L173), [lineage/source.py](../src/tarel/lineage/source.py#L176), [lineage/source.py](../src/tarel/lineage/source.py#L188), [lineage/source.py](../src/tarel/lineage/source.py#L207), [lineage/source.py](../src/tarel/lineage/source.py#L210), [lineage/source.py](../src/tarel/lineage/source.py#L235), [lineage/source.py](../src/tarel/lineage/source.py#L251), [lineage/source.py](../src/tarel/lineage/source.py#L258), [lineage/source.py](../src/tarel/lineage/source.py#L274), [lineage/source.py](../src/tarel/lineage/source.py#L280), [lineage/source.py](../src/tarel/lineage/source.py#L299), [lineage/source.py](../src/tarel/lineage/source.py#L305), [lineage/source.py](../src/tarel/lineage/source.py#L312), [lineage/source.py](../src/tarel/lineage/source.py#L329), [lineage/source.py](../src/tarel/lineage/source.py#L337), [lineage/source.py](../src/tarel/lineage/source.py#L348), [lineage/source.py](../src/tarel/lineage/source.py#L354), [lineage/source.py](../src/tarel/lineage/source.py#L363), [lineage/source.py](../src/tarel/lineage/source.py#L368), [lineage/source.py](../src/tarel/lineage/source.py#L375), [lineage/source.py](../src/tarel/lineage/source.py#L381), [lineage/source.py](../src/tarel/lineage/source.py#L392), [lineage/source.py](../src/tarel/lineage/source.py#L397) |
| `invalid_lineage_limit` | [context/grounding_application.py](../src/tarel/context/grounding_application.py#L240) |
| `invalid_lineage_name` | [lineage/change_store.py](../src/tarel/lineage/change_store.py#L75), [lineage/store.py](../src/tarel/lineage/store.py#L75) |
| `invalid_lineage_proposal` | [cli/lineage.py](../src/tarel/cli/lineage.py#L297), [cli/lineage.py](../src/tarel/cli/lineage.py#L299), [lineage/core.py](../src/tarel/lineage/core.py#L230), [lineage/core.py](../src/tarel/lineage/core.py#L443), [lineage/core.py](../src/tarel/lineage/core.py#L528), [lineage/core.py](../src/tarel/lineage/core.py#L569), [lineage/core.py](../src/tarel/lineage/core.py#L592), [lineage/core.py](../src/tarel/lineage/core.py#L621), [lineage/core.py](../src/tarel/lineage/core.py#L627), [lineage/core.py](../src/tarel/lineage/core.py#L697), [lineage/core.py](../src/tarel/lineage/core.py#L763), [lineage/core.py](../src/tarel/lineage/core.py#L772), [lineage/core.py](../src/tarel/lineage/core.py#L781), [lineage/core.py](../src/tarel/lineage/core.py#L786), [lineage/core.py](../src/tarel/lineage/core.py#L795), [lineage/core.py](../src/tarel/lineage/core.py#L806), [lineage/core.py](../src/tarel/lineage/core.py#L811) |
| `invalid_lineage_review` | [cli/lineage.py](../src/tarel/cli/lineage.py#L270), [lineage/review.py](../src/tarel/lineage/review.py#L32), [lineage/review.py](../src/tarel/lineage/review.py#L52) |
| `invalid_lineage_revision` | [lineage/change_store.py](../src/tarel/lineage/change_store.py#L80) |
| `invalid_lineage_run` | [lineage/analysis_application.py](../src/tarel/lineage/analysis_application.py#L63), [lineage/analysis_application.py](../src/tarel/lineage/analysis_application.py#L216) |
| `invalid_lineage_search` | [lineage/traversal.py](../src/tarel/lineage/traversal.py#L186), [lineage/traversal.py](../src/tarel/lineage/traversal.py#L188) |
| `invalid_lineage_target` | [lineage/core.py](../src/tarel/lineage/core.py#L746) |
| `invalid_lineage_trace` | [lineage/traversal.py](../src/tarel/lineage/traversal.py#L388), [lineage/traversal.py](../src/tarel/lineage/traversal.py#L394) |
| `invalid_logical_endpoint` | [topology/endpoint_contracts.py](../src/tarel/topology/endpoint_contracts.py#L43), [topology/endpoint_contracts.py](../src/tarel/topology/endpoint_contracts.py#L51), [topology/endpoint_contracts.py](../src/tarel/topology/endpoint_contracts.py#L56), [topology/endpoint_contracts.py](../src/tarel/topology/endpoint_contracts.py#L77), [topology/endpoints.py](../src/tarel/topology/endpoints.py#L231) |
| `invalid_logical_endpoint_mode` | [topology/endpoints.py](../src/tarel/topology/endpoints.py#L229) |
| `invalid_logical_endpoint_schema` | [topology/endpoints.py](../src/tarel/topology/endpoints.py#L262) |
| `invalid_logical_hint_mode` | [context/hints_application.py](../src/tarel/context/hints_application.py#L46) |
| `invalid_logical_join` | [logical_joins/contracts.py](../src/tarel/logical_joins/contracts.py#L163), [logical_joins/contracts.py](../src/tarel/logical_joins/contracts.py#L215), [logical_joins/store.py](../src/tarel/logical_joins/store.py#L36), [logical_joins/store.py](../src/tarel/logical_joins/store.py#L38), [logical_joins/store.py](../src/tarel/logical_joins/store.py#L41) |
| `invalid_logical_join_endpoint` | [logical_joins/application.py](../src/tarel/logical_joins/application.py#L198) |
| `invalid_logical_join_limit` | [logical_joins/application.py](../src/tarel/logical_joins/application.py#L196) |
| `invalid_logical_join_mode` | [logical_joins/application.py](../src/tarel/logical_joins/application.py#L194) |
| `invalid_logical_join_path` | [logical_joins/store.py](../src/tarel/logical_joins/store.py#L19) |
| `invalid_logical_join_program` | [discovery/logical_program.py](../src/tarel/discovery/logical_program.py#L74) |
| `invalid_logical_join_promotion` | [logical_joins/application.py](../src/tarel/logical_joins/application.py#L90) |
| `invalid_logical_join_review` | [logical_joins/application.py](../src/tarel/logical_joins/application.py#L160) |
| `invalid_logical_metadata_scope` | [ui/logical_metadata.py](../src/tarel/ui/logical_metadata.py#L58) |
| `invalid_logical_topology` | [cli/topology.py](../src/tarel/cli/topology.py#L73), [cli/topology.py](../src/tarel/cli/topology.py#L78), [topology/contracts.py](../src/tarel/topology/contracts.py#L134), [topology/contracts.py](../src/tarel/topology/contracts.py#L156), [topology/contracts.py](../src/tarel/topology/contracts.py#L198), [topology/contracts.py](../src/tarel/topology/contracts.py#L217), [topology/contracts.py](../src/tarel/topology/contracts.py#L316), [topology/contracts.py](../src/tarel/topology/contracts.py#L327), [topology/contracts.py](../src/tarel/topology/contracts.py#L333), [topology/contracts.py](../src/tarel/topology/contracts.py#L341), [topology/contracts.py](../src/tarel/topology/contracts.py#L346), [topology/contracts.py](../src/tarel/topology/contracts.py#L370), [topology/contracts.py](../src/tarel/topology/contracts.py#L441), [topology/contracts.py](../src/tarel/topology/contracts.py#L461), [topology/contracts.py](../src/tarel/topology/contracts.py#L513), [topology/contracts.py](../src/tarel/topology/contracts.py#L525), [topology/contracts.py](../src/tarel/topology/contracts.py#L529), [topology/contracts.py](../src/tarel/topology/contracts.py#L534), [topology/contracts.py](../src/tarel/topology/contracts.py#L539), [topology/contracts.py](../src/tarel/topology/contracts.py#L549), [topology/contracts.py](../src/tarel/topology/contracts.py#L554), [topology/contracts.py](../src/tarel/topology/contracts.py#L559), [topology/contracts.py](../src/tarel/topology/contracts.py#L565), [topology/contracts.py](../src/tarel/topology/contracts.py#L574), [topology/contracts.py](../src/tarel/topology/contracts.py#L581), [topology/contracts.py](../src/tarel/topology/contracts.py#L589), [topology/contracts.py](../src/tarel/topology/contracts.py#L594), [topology/contracts.py](../src/tarel/topology/contracts.py#L600), [topology/contracts.py](../src/tarel/topology/contracts.py#L607), [topology/contracts.py](../src/tarel/topology/contracts.py#L612), [topology/contracts.py](../src/tarel/topology/contracts.py#L618), [topology/contracts.py](../src/tarel/topology/contracts.py#L624), [topology/contracts.py](../src/tarel/topology/contracts.py#L667), [topology/contracts.py](../src/tarel/topology/contracts.py#L700), [topology/contracts.py](../src/tarel/topology/contracts.py#L707), [topology/contracts.py](../src/tarel/topology/contracts.py#L715), [topology/contracts.py](../src/tarel/topology/contracts.py#L723), [topology/contracts.py](../src/tarel/topology/contracts.py#L728), [topology/contracts.py](../src/tarel/topology/contracts.py#L737), [topology/contracts.py](../src/tarel/topology/contracts.py#L751), [topology/contracts.py](../src/tarel/topology/contracts.py#L760), [topology/contracts.py](../src/tarel/topology/contracts.py#L769), [topology/contracts.py](../src/tarel/topology/contracts.py#L781), [topology/contracts.py](../src/tarel/topology/contracts.py#L786), [topology/contracts.py](../src/tarel/topology/contracts.py#L794), [topology/contracts.py](../src/tarel/topology/contracts.py#L802), [topology/contracts.py](../src/tarel/topology/contracts.py#L810), [topology/contracts.py](../src/tarel/topology/contracts.py#L815), [topology/contracts.py](../src/tarel/topology/contracts.py#L821), [topology/contracts.py](../src/tarel/topology/contracts.py#L826), [topology/store.py](../src/tarel/topology/store.py#L65), [topology/store.py](../src/tarel/topology/store.py#L70), [topology/store.py](../src/tarel/topology/store.py#L75) |
| `invalid_logical_topology_graph_name` | [topology/store.py](../src/tarel/topology/store.py#L97) |
| `invalid_logical_topology_import` | [topology/application.py](../src/tarel/topology/application.py#L277), [topology/application.py](../src/tarel/topology/application.py#L299) |
| `invalid_manifest` | [connectors/contracts.py](../src/tarel/connectors/contracts.py#L62), [connectors/contracts.py](../src/tarel/connectors/contracts.py#L80), [connectors/contracts.py](../src/tarel/connectors/contracts.py#L88), [connectors/contracts.py](../src/tarel/connectors/contracts.py#L93), [connectors/contracts.py](../src/tarel/connectors/contracts.py#L98), [connectors/host.py](../src/tarel/connectors/host.py#L79), [connectors/host.py](../src/tarel/connectors/host.py#L85), [connectors/host.py](../src/tarel/connectors/host.py#L92), [connectors/host.py](../src/tarel/connectors/host.py#L115) |
| `invalid_manual_hop` | [lineage/manual.py](../src/tarel/lineage/manual.py#L150), [lineage/manual.py](../src/tarel/lineage/manual.py#L155), [lineage/manual.py](../src/tarel/lineage/manual.py#L164) |
| `invalid_manual_job` | [lineage/manual.py](../src/tarel/lineage/manual.py#L62) |
| `invalid_manual_lineage` | [lineage/manual.py](../src/tarel/lineage/manual.py#L258) |
| `invalid_model` | [retrieval/local.py](../src/tarel/retrieval/local.py#L68) |
| `invalid_model_source` | [retrieval/local.py](../src/tarel/retrieval/local.py#L149) |
| `invalid_model_target` | [retrieval/local.py](../src/tarel/retrieval/local.py#L83) |
| `invalid_object_binding` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L61), [object_bindings/application.py](../src/tarel/object_bindings/application.py#L100), [object_bindings/contracts.py](../src/tarel/object_bindings/contracts.py#L132) |
| `invalid_object_binding_mode` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L270) |
| `invalid_object_binding_path` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L284) |
| `invalid_object_family` | [cli/family.py](../src/tarel/cli/family.py#L183), [cli/family.py](../src/tarel/cli/family.py#L187), [object_families/application.py](../src/tarel/object_families/application.py#L91), [object_families/application.py](../src/tarel/object_families/application.py#L109), [object_families/contracts.py](../src/tarel/object_families/contracts.py#L270), [object_families/store.py](../src/tarel/object_families/store.py#L51), [object_families/store.py](../src/tarel/object_families/store.py#L55), [object_families/store.py](../src/tarel/object_families/store.py#L60) |
| `invalid_object_family_command` | [cli/family.py](../src/tarel/cli/family.py#L148) |
| `invalid_object_family_filter` | [cli/family.py](../src/tarel/cli/family.py#L123), [object_families/application.py](../src/tarel/object_families/application.py#L365) |
| `invalid_object_family_import` | [object_families/application.py](../src/tarel/object_families/application.py#L188) |
| `invalid_object_family_mode` | [object_families/application.py](../src/tarel/object_families/application.py#L505), [ui/backend.py](../src/tarel/ui/backend.py#L615), [payloads/graph.py](../src/tarel/ui/payloads/graph.py#L151) |
| `invalid_object_family_page` | [object_families/application.py](../src/tarel/object_families/application.py#L348) |
| `invalid_object_family_path` | [object_families/store.py](../src/tarel/object_families/store.py#L98), [object_families/store.py](../src/tarel/object_families/store.py#L102), [object_families/store.py](../src/tarel/object_families/store.py#L109) |
| `invalid_object_family_scope` | [object_families/application.py](../src/tarel/object_families/application.py#L339), [object_families/application.py](../src/tarel/object_families/application.py#L344) |
| `invalid_object_reference` | [cli/_args.py](../src/tarel/cli/_args.py#L161), [context/application.py](../src/tarel/context/application.py#L377), [graph/reads.py](../src/tarel/graph/reads.py#L74), [workspaces/core.py](../src/tarel/workspaces/core.py#L495), [workspaces/scope.py](../src/tarel/workspaces/scope.py#L179) |
| `invalid_observation` | [graph/store.py](../src/tarel/graph/store.py#L128) |
| `invalid_optional_edge` | [ui/optional_metadata.py](../src/tarel/ui/optional_metadata.py#L97) |
| `invalid_optional_endpoint` | [ui/optional_metadata.py](../src/tarel/ui/optional_metadata.py#L192) |
| `invalid_optional_metadata_request` | [ui/optional_metadata.py](../src/tarel/ui/optional_metadata.py#L67) |
| `invalid_optional_request` | [ui/backend.py](../src/tarel/ui/backend.py#L391), [ui/backend.py](../src/tarel/ui/backend.py#L543), [ui/backend.py](../src/tarel/ui/backend.py#L546), [ui/backend.py](../src/tarel/ui/backend.py#L619) |
| `invalid_ossie` | [semantics/ossie.py](../src/tarel/semantics/ossie.py#L58), [semantics/ossie.py](../src/tarel/semantics/ossie.py#L490), [semantics/ossie.py](../src/tarel/semantics/ossie.py#L496), [semantics/ossie.py](../src/tarel/semantics/ossie.py#L504), [semantics/ossie.py](../src/tarel/semantics/ossie.py#L513), [semantics/ossie.py](../src/tarel/semantics/ossie.py#L519), [semantics/ossie.py](../src/tarel/semantics/ossie.py#L528), [semantics/ossie.py](../src/tarel/semantics/ossie.py#L537), [semantics/ossie.py](../src/tarel/semantics/ossie.py#L545) |
| `invalid_package` | [packages/application.py](../src/tarel/packages/application.py#L260), [packages/archive.py](../src/tarel/packages/archive.py#L60), [packages/archive.py](../src/tarel/packages/archive.py#L72), [packages/archive.py](../src/tarel/packages/archive.py#L74), [packages/archive.py](../src/tarel/packages/archive.py#L113), [packages/archive.py](../src/tarel/packages/archive.py#L115), [packages/archive.py](../src/tarel/packages/archive.py#L191), [packages/archive.py](../src/tarel/packages/archive.py#L194), [packages/archive.py](../src/tarel/packages/archive.py#L199), [packages/archive.py](../src/tarel/packages/archive.py#L212), [sync/application.py](../src/tarel/sync/application.py#L348), [sync/envelope.py](../src/tarel/sync/envelope.py#L144), [sync/envelope.py](../src/tarel/sync/envelope.py#L146), [sync/envelope.py](../src/tarel/sync/envelope.py#L157), [sync/envelope.py](../src/tarel/sync/envelope.py#L180), [sync/envelope.py](../src/tarel/sync/envelope.py#L182), [sync/envelope.py](../src/tarel/sync/envelope.py#L185), [sync/envelope.py](../src/tarel/sync/envelope.py#L191), [sync/envelope.py](../src/tarel/sync/envelope.py#L220), [sync/envelope.py](../src/tarel/sync/envelope.py#L226), [sync/envelope.py](../src/tarel/sync/envelope.py#L230), [sync/envelope.py](../src/tarel/sync/envelope.py#L247), [sync/envelope.py](../src/tarel/sync/envelope.py#L252), [sync/envelope.py](../src/tarel/sync/envelope.py#L263), [sync/envelope.py](../src/tarel/sync/envelope.py#L266) |
| `invalid_package_document` | [packages/application.py](../src/tarel/packages/application.py#L287), [packages/application.py](../src/tarel/packages/application.py#L430), [packages/application.py](../src/tarel/packages/application.py#L443) |
| `invalid_package_json` | [packages/archive.py](../src/tarel/packages/archive.py#L160), [packages/archive.py](../src/tarel/packages/archive.py#L164), [packages/archive.py](../src/tarel/packages/archive.py#L169), [packages/archive.py](../src/tarel/packages/archive.py#L173), [packages/archive.py](../src/tarel/packages/archive.py#L175) |
| `invalid_package_manifest` | [packages/archive.py](../src/tarel/packages/archive.py#L97), [packages/archive.py](../src/tarel/packages/archive.py#L101), [packages/contracts.py](../src/tarel/packages/contracts.py#L73), [packages/contracts.py](../src/tarel/packages/contracts.py#L81), [packages/contracts.py](../src/tarel/packages/contracts.py#L83), [packages/contracts.py](../src/tarel/packages/contracts.py#L87), [packages/contracts.py](../src/tarel/packages/contracts.py#L137), [packages/contracts.py](../src/tarel/packages/contracts.py#L142), [packages/contracts.py](../src/tarel/packages/contracts.py#L145), [packages/contracts.py](../src/tarel/packages/contracts.py#L149), [packages/contracts.py](../src/tarel/packages/contracts.py#L156), [packages/contracts.py](../src/tarel/packages/contracts.py#L158), [packages/contracts.py](../src/tarel/packages/contracts.py#L160), [packages/contracts.py](../src/tarel/packages/contracts.py#L164), [packages/contracts.py](../src/tarel/packages/contracts.py#L168), [packages/contracts.py](../src/tarel/packages/contracts.py#L173), [packages/contracts.py](../src/tarel/packages/contracts.py#L183), [packages/contracts.py](../src/tarel/packages/contracts.py#L323), [packages/contracts.py](../src/tarel/packages/contracts.py#L329) |
| `invalid_package_path` | [packages/application.py](../src/tarel/packages/application.py#L77), [packages/contracts.py](../src/tarel/packages/contracts.py#L253), [packages/contracts.py](../src/tarel/packages/contracts.py#L259), [packages/contracts.py](../src/tarel/packages/contracts.py#L266), [packages/contracts.py](../src/tarel/packages/contracts.py#L276) |
| `invalid_package_references` | [packages/application.py](../src/tarel/packages/application.py#L453), [packages/application.py](../src/tarel/packages/application.py#L461), [packages/application.py](../src/tarel/packages/application.py#L475), [packages/application.py](../src/tarel/packages/application.py#L486) |
| `invalid_pair_budget` | [relationships/core.py](../src/tarel/relationships/core.py#L202) |
| `invalid_port` | [ui/server.py](../src/tarel/ui/server.py#L205) |
| `invalid_previous_context` | [ui/query_tools.py](../src/tarel/ui/query_tools.py#L238), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L301) |
| `invalid_profile_row_limit` | [annotations/application.py](../src/tarel/annotations/application.py#L363), [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L205), [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L377), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L517), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L823), [sources/application.py](../src/tarel/sources/application.py#L248) |
| `invalid_proposal` | [annotations/apply.py](../src/tarel/annotations/apply.py#L74), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L87), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L116), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L119), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L126), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L132), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L137), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L143), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L170), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L187), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L191), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L206), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L214), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L220), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L229), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L232), [cli/annotation.py](../src/tarel/cli/annotation.py#L253), [cli/annotation.py](../src/tarel/cli/annotation.py#L255) |
| `invalid_provider_adapter` | [providers/application.py](../src/tarel/providers/application.py#L62), [providers/config.py](../src/tarel/providers/config.py#L106), [providers/config.py](../src/tarel/providers/config.py#L198), [providers/config.py](../src/tarel/providers/config.py#L352), [providers/host.py](../src/tarel/providers/host.py#L61), [providers/host.py](../src/tarel/providers/host.py#L66) |
| `invalid_provider_config` | [providers/application.py](../src/tarel/providers/application.py#L90), [providers/config.py](../src/tarel/providers/config.py#L121), [providers/config.py](../src/tarel/providers/config.py#L161), [providers/config.py](../src/tarel/providers/config.py#L315), [providers/config.py](../src/tarel/providers/config.py#L361), [providers/config.py](../src/tarel/providers/config.py#L370), [providers/config.py](../src/tarel/providers/config.py#L379), [providers/config.py](../src/tarel/providers/config.py#L389), [providers/config.py](../src/tarel/providers/config.py#L419) |
| `invalid_provider_name` | [providers/authoring.py](../src/tarel/providers/authoring.py#L22), [providers/config.py](../src/tarel/providers/config.py#L342) |
| `invalid_provider_request` | [providers/openai_compatible.py](../src/tarel/providers/openai_compatible.py#L66), [providers/openai_compatible.py](../src/tarel/providers/openai_compatible.py#L74), [providers/openrouter.py](../src/tarel/providers/openrouter.py#L39), [providers/openrouter.py](../src/tarel/providers/openrouter.py#L47) |
| `invalid_provider_response` | [discovery/advice.py](../src/tarel/discovery/advice.py#L82), [discovery/advice.py](../src/tarel/discovery/advice.py#L90), [discovery/advice.py](../src/tarel/discovery/advice.py#L98), [providers/application.py](../src/tarel/providers/application.py#L123), [providers/openai_compatible.py](../src/tarel/providers/openai_compatible.py#L99), [providers/openrouter.py](../src/tarel/providers/openrouter.py#L78), [providers/openrouter.py](../src/tarel/providers/openrouter.py#L89), [providers/openrouter.py](../src/tarel/providers/openrouter.py#L108), [providers/openrouter.py](../src/tarel/providers/openrouter.py#L135), [providers/openrouter.py](../src/tarel/providers/openrouter.py#L140) |
| `invalid_public_key` | [sync/signing.py](../src/tarel/sync/signing.py#L34), [sync/signing.py](../src/tarel/sync/signing.py#L42), [sync/signing.py](../src/tarel/sync/signing.py#L46) |
| `invalid_publication` | [sync/contracts.py](../src/tarel/sync/contracts.py#L126), [sync/contracts.py](../src/tarel/sync/contracts.py#L138), [sync/contracts.py](../src/tarel/sync/contracts.py#L141), [sync/contracts.py](../src/tarel/sync/contracts.py#L189), [sync/contracts.py](../src/tarel/sync/contracts.py#L192), [sync/contracts.py](../src/tarel/sync/contracts.py#L199), [sync/contracts.py](../src/tarel/sync/contracts.py#L208), [sync/contracts.py](../src/tarel/sync/contracts.py#L212), [sync/contracts.py](../src/tarel/sync/contracts.py#L217), [sync/contracts.py](../src/tarel/sync/contracts.py#L220), [sync/contracts.py](../src/tarel/sync/contracts.py#L223) |
| `invalid_publication_path` | [sync/publish_application.py](../src/tarel/sync/publish_application.py#L131) |
| `invalid_query` | [ui/query_tools.py](../src/tarel/ui/query_tools.py#L401) |
| `invalid_query_budget` | [ui/query_tools.py](../src/tarel/ui/query_tools.py#L246), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L410) |
| `invalid_query_linked_coverage` | [discovery/coverage.py](../src/tarel/discovery/coverage.py#L122), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L318), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L330), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L382), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L391), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L403), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L409), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L416), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L421), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L432), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L436), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L450), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L457), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L466), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L471), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L485), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L492), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L500), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L512), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L520), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L525), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L533), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L541), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L549), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L558), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L567), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L572), [discovery/coverage_application.py](../src/tarel/discovery/coverage_application.py#L39), [discovery/coverage_application.py](../src/tarel/discovery/coverage_application.py#L44), [discovery/coverage_application.py](../src/tarel/discovery/coverage_application.py#L172), [discovery/coverage_application.py](../src/tarel/discovery/coverage_application.py#L178), [discovery/coverage_application.py](../src/tarel/discovery/coverage_application.py#L188), [discovery/coverage_application.py](../src/tarel/discovery/coverage_application.py#L204), [discovery/coverage_application.py](../src/tarel/discovery/coverage_application.py#L218), [discovery/store.py](../src/tarel/discovery/store.py#L121), [discovery/store.py](../src/tarel/discovery/store.py#L126), [discovery/store.py](../src/tarel/discovery/store.py#L135) |
| `invalid_query_policy` | [ui/query_tools.py](../src/tarel/ui/query_tools.py#L164), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L172), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L230), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L235) |
| `invalid_query_request` | [ui/backend.py](../src/tarel/ui/backend.py#L486), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L217), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L392), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L421), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L423) |
| `invalid_query_scope` | [ui/query_tools.py](../src/tarel/ui/query_tools.py#L84), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L89), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L91), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L96), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L98), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L443), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L451) |
| `invalid_reference_mapping` | [cli/reference_mapping.py](../src/tarel/cli/reference_mapping.py#L102), [cli/reference_mapping.py](../src/tarel/cli/reference_mapping.py#L107), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L359), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L81), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L97), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L106), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L178), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L270), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L311), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L360), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L370), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L378), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L384), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L394), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L434), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L441), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L449), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L458), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L466), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L474), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L479), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L487), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L499), [reference_mapping/store.py](../src/tarel/reference_mapping/store.py#L62), [reference_mapping/store.py](../src/tarel/reference_mapping/store.py#L67), [reference_mapping/store.py](../src/tarel/reference_mapping/store.py#L73) |
| `invalid_reference_mapping_id` | [reference_mapping/store.py](../src/tarel/reference_mapping/store.py#L95) |
| `invalid_reference_mapping_import` | [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L140) |
| `invalid_reference_mapping_mode` | [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L213) |
| `invalid_relationship` | [context/compiler.py](../src/tarel/context/compiler.py#L626), [context/compiler.py](../src/tarel/context/compiler.py#L659), [context/compiler.py](../src/tarel/context/compiler.py#L670), [context/compiler.py](../src/tarel/context/compiler.py#L693) |
| `invalid_relationship_fields` | [relationships/core.py](../src/tarel/relationships/core.py#L122), [relationships/core.py](../src/tarel/relationships/core.py#L131), [relationships/core.py](../src/tarel/relationships/core.py#L138), [relationships/core.py](../src/tarel/relationships/core.py#L146) |
| `invalid_relationship_pair` | [relationships/core.py](../src/tarel/relationships/core.py#L80), [workspaces/core.py](../src/tarel/workspaces/core.py#L191) |
| `invalid_relationship_probe` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L200), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L512) |
| `invalid_relationship_state` | [relationships/core.py](../src/tarel/relationships/core.py#L423), [workspaces/core.py](../src/tarel/workspaces/core.py#L234) |
| `invalid_request` | [ui/_parse.py](../src/tarel/ui/_parse.py#L13), [ui/_parse.py](../src/tarel/ui/_parse.py#L21), [ui/_parse.py](../src/tarel/ui/_parse.py#L28), [ui/_parse.py](../src/tarel/ui/_parse.py#L37), [ui/_parse.py](../src/tarel/ui/_parse.py#L44), [ui/_parse.py](../src/tarel/ui/_parse.py#L58), [ui/backend.py](../src/tarel/ui/backend.py#L692), [ui/backend.py](../src/tarel/ui/backend.py#L704), [ui/backend.py](../src/tarel/ui/backend.py#L1178), [ui/backend.py](../src/tarel/ui/backend.py#L1183), [ui/server.py](../src/tarel/ui/server.py#L105), [ui/server.py](../src/tarel/ui/server.py#L314) |
| `invalid_rerank_candidate` | [retrieval/rerank.py](../src/tarel/retrieval/rerank.py#L62) |
| `invalid_response` | [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L263) |
| `invalid_retrieval_mode` | [retrieval/ranking.py](../src/tarel/retrieval/ranking.py#L57) |
| `invalid_retrieval_plugin` | [retrieval/plugins.py](../src/tarel/retrieval/plugins.py#L136) |
| `invalid_retrieval_response` | [retrieval/catalog.py](../src/tarel/retrieval/catalog.py#L40), [retrieval/remote.py](../src/tarel/retrieval/remote.py#L54), [retrieval/remote.py](../src/tarel/retrieval/remote.py#L70), [retrieval/remote.py](../src/tarel/retrieval/remote.py#L90), [retrieval/remote.py](../src/tarel/retrieval/remote.py#L94), [retrieval/remote.py](../src/tarel/retrieval/remote.py#L99), [retrieval/remote.py](../src/tarel/retrieval/remote.py#L119), [retrieval/remote.py](../src/tarel/retrieval/remote.py#L177), [retrieval/remote.py](../src/tarel/retrieval/remote.py#L186), [retrieval/remote.py](../src/tarel/retrieval/remote.py#L231) |
| `invalid_retrieval_settings` | [cli/retrieval.py](../src/tarel/cli/retrieval.py#L56), [cli/retrieval.py](../src/tarel/cli/retrieval.py#L96), [cli/retrieval.py](../src/tarel/cli/retrieval.py#L105), [retrieval/settings.py](../src/tarel/retrieval/settings.py#L32), [retrieval/settings.py](../src/tarel/retrieval/settings.py#L34), [retrieval/settings.py](../src/tarel/retrieval/settings.py#L41), [retrieval/settings.py](../src/tarel/retrieval/settings.py#L60), [retrieval/settings.py](../src/tarel/retrieval/settings.py#L62), [retrieval/settings.py](../src/tarel/retrieval/settings.py#L73), [retrieval/settings.py](../src/tarel/retrieval/settings.py#L97), [retrieval/settings.py](../src/tarel/retrieval/settings.py#L118), [retrieval/settings.py](../src/tarel/retrieval/settings.py#L183), [ui/backend.py](../src/tarel/ui/backend.py#L509), [ui/backend.py](../src/tarel/ui/backend.py#L512), [ui/backend.py](../src/tarel/ui/backend.py#L521), [ui/backend.py](../src/tarel/ui/backend.py#L529) |
| `invalid_retrieval_task` | [retrieval/catalog.py](../src/tarel/retrieval/catalog.py#L14) |
| `invalid_runtime_lineage` | [lineage/_runtime_parse.py](../src/tarel/lineage/_runtime_parse.py#L75), [lineage/_runtime_parse.py](../src/tarel/lineage/_runtime_parse.py#L91), [lineage/_runtime_parse.py](../src/tarel/lineage/_runtime_parse.py#L99), [lineage/_runtime_parse.py](../src/tarel/lineage/_runtime_parse.py#L105), [lineage/_runtime_parse.py](../src/tarel/lineage/_runtime_parse.py#L111), [lineage/_runtime_parse.py](../src/tarel/lineage/_runtime_parse.py#L117), [lineage/_runtime_parse.py](../src/tarel/lineage/_runtime_parse.py#L126), [lineage/_runtime_parse.py](../src/tarel/lineage/_runtime_parse.py#L135), [lineage/_runtime_parse.py](../src/tarel/lineage/_runtime_parse.py#L144), [lineage/_runtime_parse.py](../src/tarel/lineage/_runtime_parse.py#L150), [lineage/_runtime_parse.py](../src/tarel/lineage/_runtime_parse.py#L160), [lineage/_runtime_parse.py](../src/tarel/lineage/_runtime_parse.py#L169), [lineage/_runtime_parse.py](../src/tarel/lineage/_runtime_parse.py#L178), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L31), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L62), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L131), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L136), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L145), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L153), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L161), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L228), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L242), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L250), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L258), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L399), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L415), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L502), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L507), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L520), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L528), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L540), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L616), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L621), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L633), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L644), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L672), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L678), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L704), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L710), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L719), [lineage/runtime_inputs.py](../src/tarel/lineage/runtime_inputs.py#L724), [lineage/runtime_logical.py](../src/tarel/lineage/runtime_logical.py#L137), [lineage/runtime_logical.py](../src/tarel/lineage/runtime_logical.py#L151), [lineage/runtime_logical.py](../src/tarel/lineage/runtime_logical.py#L163), [lineage/runtime_logical.py](../src/tarel/lineage/runtime_logical.py#L168), [lineage/runtime_logical.py](../src/tarel/lineage/runtime_logical.py#L175), [lineage/runtime_records.py](../src/tarel/lineage/runtime_records.py#L74), [lineage/runtime_records.py](../src/tarel/lineage/runtime_records.py#L78), [lineage/runtime_records.py](../src/tarel/lineage/runtime_records.py#L365), [lineage/runtime_records.py](../src/tarel/lineage/runtime_records.py#L446), [lineage/runtime_records.py](../src/tarel/lineage/runtime_records.py#L452), [lineage/runtime_records.py](../src/tarel/lineage/runtime_records.py#L469), [lineage/runtime_records.py](../src/tarel/lineage/runtime_records.py#L474), [lineage/runtime_records.py](../src/tarel/lineage/runtime_records.py#L481), [lineage/runtime_records.py](../src/tarel/lineage/runtime_records.py#L507), [lineage/runtime_records.py](../src/tarel/lineage/runtime_records.py#L531), [lineage/runtime_store.py](../src/tarel/lineage/runtime_store.py#L81), [lineage/runtime_store.py](../src/tarel/lineage/runtime_store.py#L86), [lineage/runtime_store.py](../src/tarel/lineage/runtime_store.py#L92) |
| `invalid_runtime_lineage_graph` | [lineage/runtime_application.py](../src/tarel/lineage/runtime_application.py#L242) |
| `invalid_runtime_lineage_name` | [lineage/runtime_store.py](../src/tarel/lineage/runtime_store.py#L107) |
| `invalid_sample_limit` | [annotations/application.py](../src/tarel/annotations/application.py#L356), [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L97), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L344), [sources/application.py](../src/tarel/sources/application.py#L253) |
| `invalid_schema_reference` | [workspaces/core.py](../src/tarel/workspaces/core.py#L267), [workspaces/scope.py](../src/tarel/workspaces/scope.py#L303) |
| `invalid_scope` | [sync/contracts.py](../src/tarel/sync/contracts.py#L459), [sync/publish_application.py](../src/tarel/sync/publish_application.py#L66), [sync/publish_application.py](../src/tarel/sync/publish_application.py#L100) |
| `invalid_scope_target` | [cli/_args.py](../src/tarel/cli/_args.py#L175) |
| `invalid_search_filter` | [tarel/search.py](../src/tarel/search.py#L57), [tarel/search.py](../src/tarel/search.py#L62) |
| `invalid_semantic_concept_mode` | [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L188) |
| `invalid_semantic_concept_query` | [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L142), [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L193), [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L214) |
| `invalid_semantic_concepts` | [cli/concept.py](../src/tarel/cli/concept.py#L120), [cli/concept.py](../src/tarel/cli/concept.py#L122), [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L68), [semantic_concepts/contracts.py](../src/tarel/semantic_concepts/contracts.py#L239), [semantic_concepts/store.py](../src/tarel/semantic_concepts/store.py#L41), [semantic_concepts/store.py](../src/tarel/semantic_concepts/store.py#L46), [semantic_concepts/store.py](../src/tarel/semantic_concepts/store.py#L52) |
| `invalid_semantic_concepts_import` | [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L98) |
| `invalid_semantic_concepts_path` | [semantic_concepts/store.py](../src/tarel/semantic_concepts/store.py#L66), [semantic_concepts/store.py](../src/tarel/semantic_concepts/store.py#L74), [semantic_concepts/store.py](../src/tarel/semantic_concepts/store.py#L79) |
| `invalid_semantic_edit` | [semantics/application.py](../src/tarel/semantics/application.py#L130), [semantics/application.py](../src/tarel/semantics/application.py#L135), [semantics/application.py](../src/tarel/semantics/application.py#L172), [semantics/application.py](../src/tarel/semantics/application.py#L177), [semantics/application.py](../src/tarel/semantics/application.py#L185), [semantics/application.py](../src/tarel/semantics/application.py#L194), [semantics/application.py](../src/tarel/semantics/application.py#L200) |
| `invalid_semantic_import` | [semantics/contracts.py](../src/tarel/semantics/contracts.py#L396), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L432), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L434), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L439), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L468), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L478), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L484), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L489), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L557), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L571), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L579), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L593), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L604), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L613), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L624), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L635), [semantics/store.py](../src/tarel/semantics/store.py#L60), [semantics/store.py](../src/tarel/semantics/store.py#L65), [semantics/store.py](../src/tarel/semantics/store.py#L71) |
| `invalid_semantic_import_name` | [semantics/contracts.py](../src/tarel/semantics/contracts.py#L427) |
| `invalid_semantic_snapshot` | [semantics/contracts.py](../src/tarel/semantics/contracts.py#L445) |
| `invalid_semantic_source` | [semantics/source.py](../src/tarel/semantics/source.py#L127) |
| `invalid_semantic_source_bundle` | [semantics/source.py](../src/tarel/semantics/source.py#L53) |
| `invalid_session` | [ui/server.py](../src/tarel/ui/server.py#L126) |
| `invalid_signature` | [sync/authorization.py](../src/tarel/sync/authorization.py#L67) |
| `invalid_small_domain_limit` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L382), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L828) |
| `invalid_sml` | [semantics/sml.py](../src/tarel/semantics/sml.py#L390), [semantics/sml.py](../src/tarel/semantics/sml.py#L396), [semantics/sml.py](../src/tarel/semantics/sml.py#L404), [semantics/sml.py](../src/tarel/semantics/sml.py#L410), [semantics/sml.py](../src/tarel/semantics/sml.py#L416), [semantics/sml.py](../src/tarel/semantics/sml.py#L419), [semantics/sml.py](../src/tarel/semantics/sml.py#L425) |
| `invalid_source` | [sources/contracts.py](../src/tarel/sources/contracts.py#L131), [sources/contracts.py](../src/tarel/sources/contracts.py#L133), [sources/contracts.py](../src/tarel/sources/contracts.py#L135), [sources/contracts.py](../src/tarel/sources/contracts.py#L137), [sources/contracts.py](../src/tarel/sources/contracts.py#L163), [sources/contracts.py](../src/tarel/sources/contracts.py#L202), [sources/contracts.py](../src/tarel/sources/contracts.py#L210), [sources/contracts.py](../src/tarel/sources/contracts.py#L216), [sources/store.py](../src/tarel/sources/store.py#L48), [sources/store.py](../src/tarel/sources/store.py#L50) |
| `invalid_source_name` | [sources/contracts.py](../src/tarel/sources/contracts.py#L126) |
| `invalid_stale_claim` | [graph/refresh.py](../src/tarel/graph/refresh.py#L407) |
| `invalid_sync_identity` | [sync/contracts.py](../src/tarel/sync/contracts.py#L70), [sync/store.py](../src/tarel/sync/store.py#L213) |
| `invalid_sync_name` | [sync/contracts.py](../src/tarel/sync/contracts.py#L76) |
| `invalid_sync_state` | [sync/store.py](../src/tarel/sync/store.py#L222), [sync/store.py](../src/tarel/sync/store.py#L231), [sync/store.py](../src/tarel/sync/store.py#L233) |
| `invalid_threshold` | [relationships/core.py](../src/tarel/relationships/core.py#L291), [relationships/core.py](../src/tarel/relationships/core.py#L293), [relationships/core.py](../src/tarel/relationships/core.py#L295) |
| `invalid_timestamp` | [sync/contracts.py](../src/tarel/sync/contracts.py#L83), [sync/contracts.py](../src/tarel/sync/contracts.py#L87) |
| `invalid_url` | [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L606), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L617), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L636) |
| `invalid_vector_backend` | [retrieval/index.py](../src/tarel/retrieval/index.py#L668) |
| `invalid_workspace` | [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L99), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L276), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L299), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L309), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L332), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L342), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L358), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L363), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L375), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L381), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L390), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L401), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L416), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L426), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L443), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L453), [workspaces/store.py](../src/tarel/workspaces/store.py#L58), [workspaces/store.py](../src/tarel/workspaces/store.py#L63) |
| `invalid_workspace_identifier` | [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L435) |
| `invalid_workspace_name` | [workspaces/store.py](../src/tarel/workspaces/store.py#L80) |
| `invalid_workspace_scope` | [cli/_args.py](../src/tarel/cli/_args.py#L179) |
| `invalid_write_coverage` | [lineage/core.py](../src/tarel/lineage/core.py#L674) |
| `knowledge_document_too_large` | [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L271) |
| `knowledge_exists` | [knowledge/application.py](../src/tarel/knowledge/application.py#L43) |
| `knowledge_graph_outside_workspace` | [knowledge/application.py](../src/tarel/knowledge/application.py#L224) |
| `knowledge_not_found` | [knowledge/core.py](../src/tarel/knowledge/core.py#L45), [knowledge/store.py](../src/tarel/knowledge/store.py#L51) |
| `knowledge_save_failed` | [knowledge/store.py](../src/tarel/knowledge/store.py#L40) |
| `knowledge_scope_not_found` | [knowledge/application.py](../src/tarel/knowledge/application.py#L178), [knowledge/application.py](../src/tarel/knowledge/application.py#L203) |
| `knowledge_source_not_found` | [knowledge/application.py](../src/tarel/knowledge/application.py#L56) |
| `knowledge_workspace_required` | [knowledge/application.py](../src/tarel/knowledge/application.py#L170) |
| `lineage_analysis_cache_save_failed` | [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L188) |
| `lineage_change_report_conflict` | [lineage/change_store.py](../src/tarel/lineage/change_store.py#L26) |
| `lineage_change_report_not_found` | [lineage/change_store.py](../src/tarel/lineage/change_store.py#L52) |
| `lineage_change_report_save_failed` | [lineage/change_store.py](../src/tarel/lineage/change_store.py#L36) |
| `lineage_edge_not_found` | [ui/backend.py](../src/tarel/ui/backend.py#L698) |
| `lineage_input_not_found` | [lineage/source.py](../src/tarel/lineage/source.py#L146) |
| `lineage_item_not_found` | [lineage/review.py](../src/tarel/lineage/review.py#L68) |
| `lineage_not_found` | [lineage/application.py](../src/tarel/lineage/application.py#L334), [lineage/store.py](../src/tarel/lineage/store.py#L50) |
| `lineage_provider_required` | [lineage/analysis_application.py](../src/tarel/lineage/analysis_application.py#L220) |
| `lineage_reference_not_found` | [lineage/traversal.py](../src/tarel/lineage/traversal.py#L796), [ui/backend.py](../src/tarel/ui/backend.py#L711) |
| `lineage_refresh_mismatch` | [lineage/refresh.py](../src/tarel/lineage/refresh.py#L217) |
| `lineage_required` | [ui/backend.py](../src/tarel/ui/backend.py#L721) |
| `lineage_save_failed` | [lineage/store.py](../src/tarel/lineage/store.py#L40) |
| `lineage_source_changed` | [lineage/tasks.py](../src/tarel/lineage/tasks.py#L233) |
| `local_graph_exists` | [sync/application.py](../src/tarel/sync/application.py#L168) |
| `logical_endpoint_not_found` | [topology/endpoints.py](../src/tarel/topology/endpoints.py#L44), [topology/endpoints.py](../src/tarel/topology/endpoints.py#L87), [topology/endpoints.py](../src/tarel/topology/endpoints.py#L96), [topology/endpoints.py](../src/tarel/topology/endpoints.py#L122), [topology/endpoints.py](../src/tarel/topology/endpoints.py#L213), [topology/endpoints.py](../src/tarel/topology/endpoints.py#L245) |
| `logical_endpoint_policy_excluded` | [topology/endpoints.py](../src/tarel/topology/endpoints.py#L140), [topology/endpoints.py](../src/tarel/topology/endpoints.py#L281) |
| `logical_join_already_reviewed` | [logical_joins/application.py](../src/tarel/logical_joins/application.py#L158) |
| `logical_join_exists` | [logical_joins/application.py](../src/tarel/logical_joins/application.py#L119) |
| `logical_join_not_found` | [logical_joins/store.py](../src/tarel/logical_joins/store.py#L34) |
| `logical_join_review_conflict` | [logical_joins/application.py](../src/tarel/logical_joins/application.py#L172) |
| `logical_join_save_failed` | [logical_joins/store.py](../src/tarel/logical_joins/store.py#L51) |
| `logical_metadata_object_not_found` | [ui/logical_metadata.py](../src/tarel/ui/logical_metadata.py#L188) |
| `logical_metadata_object_outside_scope` | [ui/logical_metadata.py](../src/tarel/ui/logical_metadata.py#L196) |
| `logical_metadata_policy_excluded` | [ui/logical_metadata.py](../src/tarel/ui/logical_metadata.py#L206) |
| `logical_topology_cross_object_step` | [topology/application.py](../src/tarel/topology/application.py#L255) |
| `logical_topology_endpoint_not_found` | [topology/application.py](../src/tarel/topology/application.py#L234), [topology/application.py](../src/tarel/topology/application.py#L250) |
| `logical_topology_graph_rebase_forbidden` | [topology/application.py](../src/tarel/topology/application.py#L69) |
| `logical_topology_graph_revision_mismatch` | [topology/application.py](../src/tarel/topology/application.py#L225) |
| `logical_topology_not_found` | [topology/store.py](../src/tarel/topology/store.py#L60) |
| `logical_topology_passthrough_schema_mismatch` | [topology/application.py](../src/tarel/topology/application.py#L266) |
| `logical_topology_save_failed` | [topology/store.py](../src/tarel/topology/store.py#L47) |
| `logical_topology_source_not_found` | [cli/topology.py](../src/tarel/cli/topology.py#L68) |
| `manual_hop_exists` | [lineage/manual.py](../src/tarel/lineage/manual.py#L177) |
| `manual_job_exists` | [lineage/manual.py](../src/tarel/lineage/manual.py#L72) |
| `manual_overlay_required` | [lineage/manual.py](../src/tarel/lineage/manual.py#L233) |
| `mapping_manifest_required` | [discovery/actions.py](../src/tarel/discovery/actions.py#L326) |
| `missing_annotation_review_reason` | [annotations/review.py](../src/tarel/annotations/review.py#L366) |
| `missing_api_key` | [cli/provider.py](../src/tarel/cli/provider.py#L120), [providers/application.py](../src/tarel/providers/application.py#L67), [providers/config.py](../src/tarel/providers/config.py#L126) |
| `missing_config` | [connectors/application.py](../src/tarel/connectors/application.py#L189) |
| `missing_database` | [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L612) |
| `missing_dependency` | [connectors/host.py](../src/tarel/connectors/host.py#L109), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L227), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L284), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L349), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L427), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L525) |
| `missing_embedding_backend` | [lineage/traversal.py](../src/tarel/lineage/traversal.py#L193), [retrieval/index.py](../src/tarel/retrieval/index.py#L80), [retrieval/index.py](../src/tarel/retrieval/index.py#L201), [retrieval/index.py](../src/tarel/retrieval/index.py#L287), [retrieval/ranking.py](../src/tarel/retrieval/ranking.py#L76) |
| `missing_focus_sources` | [focus/application.py](../src/tarel/focus/application.py#L33) |
| `missing_lineage_scope` | [context/grounding_application.py](../src/tarel/context/grounding_application.py#L245) |
| `missing_local_rag_dependency` | [retrieval/local.py](../src/tarel/retrieval/local.py#L45), [retrieval/plugins.py](../src/tarel/retrieval/plugins.py#L119) |
| `missing_provider_adapter` | [providers/application.py](../src/tarel/providers/application.py#L56) |
| `missing_relationship_reason` | [relationships/core.py](../src/tarel/relationships/core.py#L115), [relationships/core.py](../src/tarel/relationships/core.py#L425), [workspaces/core.py](../src/tarel/workspaces/core.py#L184), [workspaces/core.py](../src/tarel/workspaces/core.py#L239) |
| `missing_sqlite_vec_dependency` | [retrieval/index.py](../src/tarel/retrieval/index.py#L730) |
| `model_changed_during_hash` | [tarel/runtime.py](../src/tarel/runtime.py#L143) |
| `model_changed_during_load` | [retrieval/application.py](../src/tarel/retrieval/application.py#L402), [retrieval/application.py](../src/tarel/retrieval/application.py#L408), [retrieval/application.py](../src/tarel/retrieval/application.py#L414), [tarel/runtime.py](../src/tarel/runtime.py#L109), [tarel/runtime.py](../src/tarel/runtime.py#L117) |
| `model_checksum_mismatch` | [retrieval/local.py](../src/tarel/retrieval/local.py#L86), [retrieval/local.py](../src/tarel/retrieval/local.py#L114) |
| `model_download_failed` | [retrieval/local.py](../src/tarel/retrieval/local.py#L124) |
| `model_index_mismatch` | [lineage/traversal.py](../src/tarel/lineage/traversal.py#L319), [retrieval/index.py](../src/tarel/retrieval/index.py#L604), [retrieval/index.py](../src/tarel/retrieval/index.py#L678), [retrieval/index.py](../src/tarel/retrieval/index.py#L719), [retrieval/index.py](../src/tarel/retrieval/index.py#L725), [retrieval/vectors.py](../src/tarel/retrieval/vectors.py#L23) |
| `model_not_found` | [retrieval/local.py](../src/tarel/retrieval/local.py#L63) |
| `namespace_not_found` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L264) |
| `no_profile_fields` | [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L455) |
| `no_sample_fields` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L111), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L371) |
| `object_binding_exists` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L73) |
| `object_binding_not_found` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L98) |
| `object_binding_policy_excluded` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L200) |
| `object_binding_review_final` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L117) |
| `object_binding_review_required` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L64) |
| `object_binding_save_failed` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L294) |
| `object_family_already_reviewed` | [object_families/contracts.py](../src/tarel/object_families/contracts.py#L258) |
| `object_family_attribute_mismatch` | [object_families/application.py](../src/tarel/object_families/application.py#L488), [object_families/application.py](../src/tarel/object_families/application.py#L495) |
| `object_family_exists` | [object_families/application.py](../src/tarel/object_families/application.py#L198) |
| `object_family_graph_revision_mismatch` | [object_families/application.py](../src/tarel/object_families/application.py#L149), [object_families/application.py](../src/tarel/object_families/application.py#L410) |
| `object_family_list_failed` | [object_families/store.py](../src/tarel/object_families/store.py#L75) |
| `object_family_member_not_found` | [object_families/application.py](../src/tarel/object_families/application.py#L103), [object_families/application.py](../src/tarel/object_families/application.py#L165), [topology/endpoints.py](../src/tarel/topology/endpoints.py#L183) |
| `object_family_not_found` | [cli/family.py](../src/tarel/cli/family.py#L105), [object_families/store.py](../src/tarel/object_families/store.py#L47) |
| `object_family_overlap` | [object_families/application.py](../src/tarel/object_families/application.py#L156), [object_families/application.py](../src/tarel/object_families/application.py#L210), [ui/lazy_family_view.py](../src/tarel/ui/lazy_family_view.py#L196), [payloads/families.py](../src/tarel/ui/payloads/families.py#L73) |
| `object_family_policy_excluded` | [object_families/application.py](../src/tarel/object_families/application.py#L355) |
| `object_family_save_failed` | [object_families/store.py](../src/tarel/object_families/store.py#L37) |
| `object_family_schema_mismatch` | [object_families/application.py](../src/tarel/object_families/application.py#L174), [object_families/application.py](../src/tarel/object_families/application.py#L423) |
| `object_family_schema_unavailable` | [object_families/application.py](../src/tarel/object_families/application.py#L463), [object_families/application.py](../src/tarel/object_families/application.py#L468), [topology/endpoints.py](../src/tarel/topology/endpoints.py#L194) |
| `object_family_source_unreadable` | [cli/family.py](../src/tarel/cli/family.py#L141) |
| `object_not_found` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L339), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L448), [workspaces/core.py](../src/tarel/workspaces/core.py#L506) |
| `object_outside_focus` | [relationships/core.py](../src/tarel/relationships/core.py#L208) |
| `object_outside_scope` | [context/application.py](../src/tarel/context/application.py#L382), [retrieval/search_application.py](../src/tarel/retrieval/search_application.py#L308), [retrieval/search_application.py](../src/tarel/retrieval/search_application.py#L344), [workspaces/scope.py](../src/tarel/workspaces/scope.py#L188) |
| `observation_failed` | [sync/publish_application.py](../src/tarel/sync/publish_application.py#L232) |
| `observation_missing` | [sync/publish_application.py](../src/tarel/sync/publish_application.py#L227) |
| `optional_metadata_too_large` | [ui/optional_metadata.py](../src/tarel/ui/optional_metadata.py#L168) |
| `optional_object_outside_scope` | [ui/backend.py](../src/tarel/ui/backend.py#L382), [ui/optional_metadata.py](../src/tarel/ui/optional_metadata.py#L74) |
| `overlapping_stream` | [sync/publish_application.py](../src/tarel/sync/publish_application.py#L210) |
| `package_checksum_mismatch` | [packages/application.py](../src/tarel/packages/application.py#L284) |
| `package_destination_exists` | [packages/application.py](../src/tarel/packages/application.py#L226), [packages/application.py](../src/tarel/packages/application.py#L248) |
| `package_exists` | [packages/application.py](../src/tarel/packages/application.py#L79), [packages/application.py](../src/tarel/packages/application.py#L128) |
| `package_extract_failed` | [packages/application.py](../src/tarel/packages/application.py#L253) |
| `package_not_found` | [packages/archive.py](../src/tarel/packages/archive.py#L43) |
| `package_read_failed` | [packages/archive.py](../src/tarel/packages/archive.py#L53), [packages/contracts.py](../src/tarel/packages/contracts.py#L290) |
| `package_snapshot_failed` | [packages/application.py](../src/tarel/packages/application.py#L198) |
| `package_source_missing` | [packages/application.py](../src/tarel/packages/application.py#L350), [packages/application.py](../src/tarel/packages/application.py#L409) |
| `package_source_read_failed` | [packages/application.py](../src/tarel/packages/application.py#L411) |
| `package_too_large` | [packages/application.py](../src/tarel/packages/application.py#L406), [packages/application.py](../src/tarel/packages/application.py#L415), [packages/archive.py](../src/tarel/packages/archive.py#L76), [packages/archive.py](../src/tarel/packages/archive.py#L108), [packages/archive.py](../src/tarel/packages/archive.py#L121), [packages/archive.py](../src/tarel/packages/archive.py#L182), [packages/archive.py](../src/tarel/packages/archive.py#L203), [packages/archive.py](../src/tarel/packages/archive.py#L206) |
| `package_write_failed` | [packages/application.py](../src/tarel/packages/application.py#L135) |
| `partial_refresh_scope` | [graph/application.py](../src/tarel/graph/application.py#L293) |
| `profiling_failed` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L180), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L465), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L484), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L909) |
| `proposal_not_found` | [cli/annotation.py](../src/tarel/cli/annotation.py#L248) |
| `provider_http_error` | [providers/openai_compatible.py](../src/tarel/providers/openai_compatible.py#L92), [providers/openrouter.py](../src/tarel/providers/openrouter.py#L71) |
| `provider_not_configured` | [providers/config.py](../src/tarel/providers/config.py#L77), [providers/config.py](../src/tarel/providers/config.py#L153), [providers/config.py](../src/tarel/providers/config.py#L169), [providers/config.py](../src/tarel/providers/config.py#L257), [providers/host.py](../src/tarel/providers/host.py#L27) |
| `provider_unavailable` | [providers/openai_compatible.py](../src/tarel/providers/openai_compatible.py#L97), [providers/openrouter.py](../src/tarel/providers/openrouter.py#L76) |
| `publication_conflict` | [sync/merge.py](../src/tarel/sync/merge.py#L59), [sync/merge.py](../src/tarel/sync/merge.py#L68), [sync/merge.py](../src/tarel/sync/merge.py#L93), [sync/merge.py](../src/tarel/sync/merge.py#L102) |
| `publication_exists` | [sync/publish_application.py](../src/tarel/sync/publish_application.py#L133) |
| `publication_not_found` | [sync/envelope.py](../src/tarel/sync/envelope.py#L164) |
| `publication_write_failed` | [sync/publish_application.py](../src/tarel/sync/publish_application.py#L197) |
| `publisher_not_initialized` | [sync/publish_application.py](../src/tarel/sync/publish_application.py#L69), [sync/publish_application.py](../src/tarel/sync/publish_application.py#L151) |
| `query_linked_coverage_binding_mismatch` | [discovery/coverage_application.py](../src/tarel/discovery/coverage_application.py#L59), [discovery/coverage_application.py](../src/tarel/discovery/coverage_application.py#L144), [discovery/coverage_application.py](../src/tarel/discovery/coverage_application.py#L197) |
| `query_linked_coverage_exists` | [discovery/coverage_application.py](../src/tarel/discovery/coverage_application.py#L72) |
| `query_linked_coverage_not_found` | [discovery/store.py](../src/tarel/discovery/store.py#L116) |
| `query_linked_reference_not_found` | [discovery/coverage_application.py](../src/tarel/discovery/coverage_application.py#L127), [discovery/coverage_application.py](../src/tarel/discovery/coverage_application.py#L139), [discovery/coverage_application.py](../src/tarel/discovery/coverage_application.py#L153) |
| `query_revision_required` | [ui/query_tools.py](../src/tarel/ui/query_tools.py#L468) |
| `raw_samples_not_allowed` | [sources/application.py](../src/tarel/sources/application.py#L258) |
| `read_only` | [ui/backend.py](../src/tarel/ui/backend.py#L999) |
| `reference_mapping_already_reviewed` | [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L409) |
| `reference_mapping_exists` | [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L155) |
| `reference_mapping_field_not_found` | [context/hints_application.py](../src/tarel/context/hints_application.py#L259), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L378), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L394), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L407), [payloads/logical.py](../src/tarel/ui/payloads/logical.py#L175), [payloads/logical.py](../src/tarel/ui/payloads/logical.py#L189) |
| `reference_mapping_graph_revision_mismatch` | [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L350), [payloads/logical.py](../src/tarel/ui/payloads/logical.py#L163) |
| `reference_mapping_not_found` | [reference_mapping/store.py](../src/tarel/reference_mapping/store.py#L57) |
| `reference_mapping_review_conflict` | [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L236), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L292) |
| `reference_mapping_save_failed` | [reference_mapping/store.py](../src/tarel/reference_mapping/store.py#L44) |
| `reference_mapping_source_not_found` | [cli/reference_mapping.py](../src/tarel/cli/reference_mapping.py#L97) |
| `refresh_mismatch` | [graph/refresh.py](../src/tarel/graph/refresh.py#L156), [graph/refresh.py](../src/tarel/graph/refresh.py#L158) |
| `refresh_scope_mismatch` | [graph/application.py](../src/tarel/graph/application.py#L303) |
| `relationship_exists` | [relationships/core.py](../src/tarel/relationships/core.py#L566), [workspaces/core.py](../src/tarel/workspaces/core.py#L200) |
| `relationship_field_not_found` | [workspaces/core.py](../src/tarel/workspaces/core.py#L413), [workspaces/projection.py](../src/tarel/workspaces/projection.py#L155) |
| `relationship_not_found` | [relationships/core.py](../src/tarel/relationships/core.py#L438), [workspaces/core.py](../src/tarel/workspaces/core.py#L248) |
| `relationship_object_not_found` | [workspaces/core.py](../src/tarel/workspaces/core.py#L401) |
| `relationship_probe_failed` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L218), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L548), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L566) |
| `request_too_large` | [ui/server.py](../src/tarel/ui/server.py#L102) |
| `reranking_failed` | [retrieval/rerank.py](../src/tarel/retrieval/rerank.py#L89) |
| `retrieval_provider_failed` | [retrieval/remote.py](../src/tarel/retrieval/remote.py#L62), [retrieval/remote.py](../src/tarel/retrieval/remote.py#L66) |
| `retrieval_request_too_large` | [retrieval/remote.py](../src/tarel/retrieval/remote.py#L43) |
| `retrieval_settings_override` | [retrieval/settings.py](../src/tarel/retrieval/settings.py#L154) |
| `reviewed_annotation` | [annotations/apply.py](../src/tarel/annotations/apply.py#L93) |
| `reviewed_lineage_item` | [lineage/core.py](../src/tarel/lineage/core.py#L270) |
| `revoked_signing_key` | [sync/authorization.py](../src/tarel/sync/authorization.py#L90) |
| `route_not_found` | [ui/backend.py](../src/tarel/ui/backend.py#L503), [ui/backend.py](../src/tarel/ui/backend.py#L981) |
| `runtime_call_not_evidence` | [lineage/runtime_application.py](../src/tarel/lineage/runtime_application.py#L96) |
| `runtime_call_not_found` | [lineage/runtime_application.py](../src/tarel/lineage/runtime_application.py#L91) |
| `runtime_graph_revision_mismatch` | [lineage/runtime_application.py](../src/tarel/lineage/runtime_application.py#L51) |
| `runtime_input_not_found` | [lineage/runtime_application.py](../src/tarel/lineage/runtime_application.py#L221) |
| `runtime_lineage_exists` | [lineage/runtime_store.py](../src/tarel/lineage/runtime_store.py#L30), [lineage/runtime_store.py](../src/tarel/lineage/runtime_store.py#L55) |
| `runtime_lineage_input_not_found` | [lineage/runtime.py](../src/tarel/lineage/runtime.py#L26) |
| `runtime_lineage_not_found` | [lineage/runtime_store.py](../src/tarel/lineage/runtime_store.py#L76) |
| `runtime_lineage_save_failed` | [lineage/runtime_store.py](../src/tarel/lineage/runtime_store.py#L66) |
| `sample_value_echoed` | [annotations/runner.py](../src/tarel/annotations/runner.py#L240) |
| `sampling_failed` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L130), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L395) |
| `scaffold_failed` | [connectors/authoring.py](../src/tarel/connectors/authoring.py#L40), [providers/authoring.py](../src/tarel/providers/authoring.py#L41) |
| `schema_in_multiple_areas` | [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L323) |
| `schema_not_found` | [workspaces/core.py](../src/tarel/workspaces/core.py#L350), [workspaces/scope.py](../src/tarel/workspaces/scope.py#L318) |
| `scope_namespace_missing` | [sync/export.py](../src/tarel/sync/export.py#L226) |
| `secret_not_resolved` | [connectors/credentials.py](../src/tarel/connectors/credentials.py#L71), [connectors/credentials.py](../src/tarel/connectors/credentials.py#L84), [connectors/credentials.py](../src/tarel/connectors/credentials.py#L88), [connectors/credentials.py](../src/tarel/connectors/credentials.py#L92) |
| `selected_objects_exceed_budget` | [context/compiler.py](../src/tarel/context/compiler.py#L242), [context/compiler.py](../src/tarel/context/compiler.py#L247), [context/compiler.py](../src/tarel/context/compiler.py#L291) |
| `semantic_concept_already_reviewed` | [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L153) |
| `semantic_concept_not_found` | [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L151) |
| `semantic_concept_policy_excluded` | [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L112), [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L161) |
| `semantic_concepts_graph_revision_mismatch` | [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L338) |
| `semantic_concepts_not_found` | [semantic_concepts/store.py](../src/tarel/semantic_concepts/store.py#L36) |
| `semantic_concepts_rebase_forbidden` | [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L82) |
| `semantic_concepts_save_failed` | [semantic_concepts/store.py](../src/tarel/semantic_concepts/store.py#L25) |
| `semantic_concepts_source_not_found` | [cli/concept.py](../src/tarel/cli/concept.py#L57) |
| `semantic_edit_no_change` | [semantics/application.py](../src/tarel/semantics/application.py#L143) |
| `semantic_edit_reason_required` | [semantics/application.py](../src/tarel/semantics/application.py#L127) |
| `semantic_import_exists` | [semantics/application.py](../src/tarel/semantics/application.py#L66) |
| `semantic_import_graph_mismatch` | [semantics/application.py](../src/tarel/semantics/application.py#L58) |
| `semantic_import_has_edits` | [semantics/application.py](../src/tarel/semantics/application.py#L72) |
| `semantic_import_not_found` | [semantics/store.py](../src/tarel/semantics/store.py#L55) |
| `semantic_import_outside_scope` | [ui/backend.py](../src/tarel/ui/backend.py#L750) |
| `semantic_import_save_failed` | [semantics/store.py](../src/tarel/semantics/store.py#L45) |
| `semantic_patch_not_found` | [semantics/application.py](../src/tarel/semantics/application.py#L167) |
| `semantic_source_empty` | [semantics/source.py](../src/tarel/semantics/source.py#L92) |
| `semantic_source_not_found` | [semantics/source.py](../src/tarel/semantics/source.py#L87) |
| `semantic_source_read_failed` | [semantics/source.py](../src/tarel/semantics/source.py#L132) |
| `semantic_source_too_large` | [semantics/source.py](../src/tarel/semantics/source.py#L97), [semantics/source.py](../src/tarel/semantics/source.py#L113) |
| `semantic_target_not_found` | [semantics/contracts.py](../src/tarel/semantics/contracts.py#L504), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L521) |
| `semantic_yaml_unavailable` | [semantics/structured.py](../src/tarel/semantics/structured.py#L54) |
| `signature_tool_missing` | [sync/signing.py](../src/tarel/sync/signing.py#L110) |
| `signing_key_missing` | [sync/signing.py](../src/tarel/sync/signing.py#L57) |
| `signing_key_required` | [sync/publish_application.py](../src/tarel/sync/publish_application.py#L135) |
| `small_domain_values_without_profile` | [annotations/application.py](../src/tarel/annotations/application.py#L368) |
| `source_config_not_resolved` | [sources/application.py](../src/tarel/sources/application.py#L405) |
| `source_exists` | [sources/application.py](../src/tarel/sources/application.py#L119) |
| `source_graph_mismatch` | [context/grounding_application.py](../src/tarel/context/grounding_application.py#L382), [sources/application.py](../src/tarel/sources/application.py#L218), [sources/application.py](../src/tarel/sources/application.py#L347), [sources/application.py](../src/tarel/sources/application.py#L365) |
| `source_graph_not_mapped` | [context/grounding_application.py](../src/tarel/context/grounding_application.py#L374), [sources/application.py](../src/tarel/sources/application.py#L360) |
| `source_not_found` | [sources/store.py](../src/tarel/sources/store.py#L46) |
| `source_save_failed` | [sources/store.py](../src/tarel/sources/store.py#L35) |
| `stale_discovery_run` | [discovery/advice.py](../src/tarel/discovery/advice.py#L44), [discovery/application.py](../src/tarel/discovery/application.py#L186) |
| `stale_entity_resolution_candidate` | [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L257) |
| `stale_expansion_base` | [expansion/application.py](../src/tarel/expansion/application.py#L153), [expansion/application.py](../src/tarel/expansion/application.py#L182), [expansion/projections.py](../src/tarel/expansion/projections.py#L233) |
| `stale_expansion_target` | [expansion/projections.py](../src/tarel/expansion/projections.py#L276) |
| `stale_family_proposal_request` | [object_families/proposals.py](../src/tarel/object_families/proposals.py#L238) |
| `stale_family_proposals` | [object_families/proposals.py](../src/tarel/object_families/proposals.py#L218) |
| `stale_graph` | [ui/backend.py](../src/tarel/ui/backend.py#L1019) |
| `stale_index` | [retrieval/index.py](../src/tarel/retrieval/index.py#L599), [retrieval/index.py](../src/tarel/retrieval/index.py#L713) |
| `stale_index_checkpoint` | [retrieval/checkpoint.py](../src/tarel/retrieval/checkpoint.py#L67) |
| `stale_knowledge_reference` | [knowledge/application.py](../src/tarel/knowledge/application.py#L248) |
| `stale_lineage` | [lineage/application.py](../src/tarel/lineage/application.py#L321) |
| `stale_lineage_proposal` | [lineage/core.py](../src/tarel/lineage/core.py#L235) |
| `stale_logical_endpoint` | [topology/endpoints.py](../src/tarel/topology/endpoints.py#L128), [topology/endpoints.py](../src/tarel/topology/endpoints.py#L273) |
| `stale_logical_join` | [logical_joins/application.py](../src/tarel/logical_joins/application.py#L156), [logical_joins/application.py](../src/tarel/logical_joins/application.py#L258) |
| `stale_logical_metadata_scope` | [ui/backend.py](../src/tarel/ui/backend.py#L601) |
| `stale_logical_topology` | [topology/application.py](../src/tarel/topology/application.py#L64), [topology/application.py](../src/tarel/topology/application.py#L76), [topology/application.py](../src/tarel/topology/application.py#L111) |
| `stale_object_binding` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L275) |
| `stale_object_family` | [object_families/application.py](../src/tarel/object_families/application.py#L510) |
| `stale_object_family_scope` | [ui/backend.py](../src/tarel/ui/backend.py#L652) |
| `stale_optional_scope` | [ui/backend.py](../src/tarel/ui/backend.py#L378) |
| `stale_plan` | [sync/application.py](../src/tarel/sync/application.py#L109), [sync/application.py](../src/tarel/sync/application.py#L401) |
| `stale_proposal` | [annotations/apply.py](../src/tarel/annotations/apply.py#L40), [annotations/apply.py](../src/tarel/annotations/apply.py#L58), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L156), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L161) |
| `stale_publication` | [sync/merge.py](../src/tarel/sync/merge.py#L54) |
| `stale_query_scope` | [ui/query_tools.py](../src/tarel/ui/query_tools.py#L363), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L486) |
| `stale_reference_mapping_candidate` | [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L275) |
| `stale_semantic_concepts` | [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L77), [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L145) |
| `stale_semantic_import` | [semantics/application.py](../src/tarel/semantics/application.py#L122) |
| `stale_workspace` | [ui/backend.py](../src/tarel/ui/backend.py#L1081) |
| `stream_exists` | [sync/publish_application.py](../src/tarel/sync/publish_application.py#L72) |
| `stream_not_found` | [sync/admin_application.py](../src/tarel/sync/admin_application.py#L99), [sync/admin_application.py](../src/tarel/sync/admin_application.py#L201), [sync/store.py](../src/tarel/sync/store.py#L90) |
| `sync_busy` | [sync/inbox.py](../src/tarel/sync/inbox.py#L49), [sync/store.py](../src/tarel/sync/store.py#L47), [sync/store.py](../src/tarel/sync/store.py#L56) |
| `sync_save_failed` | [sync/store.py](../src/tarel/sync/store.py#L178), [sync/store.py](../src/tarel/sync/store.py#L241) |
| `system_not_found` | [workspaces/core.py](../src/tarel/workspaces/core.py#L277), [workspaces/scope.py](../src/tarel/workspaces/scope.py#L256) |
| `target_exists` | [connectors/authoring.py](../src/tarel/connectors/authoring.py#L30), [providers/authoring.py](../src/tarel/providers/authoring.py#L32) |
| `target_not_found` | [annotations/tasks.py](../src/tarel/annotations/tasks.py#L120), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L139) |
| `trust_exists` | [sync/admin_application.py](../src/tarel/sync/admin_application.py#L78), [sync/admin_application.py](../src/tarel/sync/admin_application.py#L80), [sync/admin_application.py](../src/tarel/sync/admin_application.py#L137) |
| `ui_operation_failed` | [ui/server.py](../src/tarel/ui/server.py#L315) |
| `ui_source_required` | [ui/backend.py](../src/tarel/ui/backend.py#L1047), [ui/server.py](../src/tarel/ui/server.py#L207) |
| `unauthorized_scope` | [sync/authorization.py](../src/tarel/sync/authorization.py#L27), [sync/authorization.py](../src/tarel/sync/authorization.py#L46), [sync/authorization.py](../src/tarel/sync/authorization.py#L51), [sync/authorization.py](../src/tarel/sync/authorization.py#L55) |
| `unknown_demo` | [tarel/demo.py](../src/tarel/demo.py#L365) |
| `unknown_model` | [retrieval/local.py](../src/tarel/retrieval/local.py#L53), [retrieval/settings.py](../src/tarel/retrieval/settings.py#L69) |
| `unknown_signing_key` | [sync/admin_application.py](../src/tarel/sync/admin_application.py#L159), [sync/authorization.py](../src/tarel/sync/authorization.py#L88) |
| `unsafe_manifest` | [connectors/contracts.py](../src/tarel/connectors/contracts.py#L103) |
| `unsafe_semantic_source` | [semantics/source.py](../src/tarel/semantics/source.py#L67), [semantics/source.py](../src/tarel/semantics/source.py#L106) |
| `unsigned_publication` | [sync/authorization.py](../src/tarel/sync/authorization.py#L70) |
| `unsupported_agent_setup` | [tarel/agents.py](../src/tarel/agents.py#L31) |
| `unsupported_auth` | [connectors/contracts.py](../src/tarel/connectors/contracts.py#L34), [connectors/credentials.py](../src/tarel/connectors/credentials.py#L36), [connectors/credentials.py](../src/tarel/connectors/credentials.py#L42) |
| `unsupported_capability` | [connectors/application.py](../src/tarel/connectors/application.py#L135), [relationships/application.py](../src/tarel/relationships/application.py#L198) |
| `unsupported_change_report` | [graph/refresh.py](../src/tarel/graph/refresh.py#L124) |
| `unsupported_context_packet` | [context/packets.py](../src/tarel/context/packets.py#L139) |
| `unsupported_contract` | [connectors/contracts.py](../src/tarel/connectors/contracts.py#L83), [sync/contracts.py](../src/tarel/sync/contracts.py#L187) |
| `unsupported_dbt_manifest` | [lineage/dbt.py](../src/tarel/lineage/dbt.py#L42) |
| `unsupported_dbt_materialization` | [lineage/dbt.py](../src/tarel/lineage/dbt.py#L207) |
| `unsupported_discovery` | [discovery/runs.py](../src/tarel/discovery/runs.py#L607), [discovery/runs.py](../src/tarel/discovery/runs.py#L692), [discovery/runs.py](../src/tarel/discovery/runs.py#L699), [discovery/runs.py](../src/tarel/discovery/runs.py#L707), [discovery/runs.py](../src/tarel/discovery/runs.py#L715), [discovery/runs.py](../src/tarel/discovery/runs.py#L719) |
| `unsupported_discovery_promotion` | [discovery/promotion.py](../src/tarel/discovery/promotion.py#L204) |
| `unsupported_entity_resolution` | [entity_resolution/candidates.py](../src/tarel/entity_resolution/candidates.py#L108), [entity_resolution/candidates.py](../src/tarel/entity_resolution/candidates.py#L297), [entity_resolution/evidence.py](../src/tarel/entity_resolution/evidence.py#L255) |
| `unsupported_focus` | [focus/contracts.py](../src/tarel/focus/contracts.py#L124) |
| `unsupported_graph` | [graph/contracts.py](../src/tarel/graph/contracts.py#L220) |
| `unsupported_index` | [retrieval/index.py](../src/tarel/retrieval/index.py#L540) |
| `unsupported_knowledge` | [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L136), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L252) |
| `unsupported_knowledge_format` | [knowledge/application.py](../src/tarel/knowledge/application.py#L49) |
| `unsupported_lineage` | [lineage/contracts.py](../src/tarel/lineage/contracts.py#L292) |
| `unsupported_lineage_analysis_cache` | [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L131) |
| `unsupported_lineage_change` | [lineage/refresh.py](../src/tarel/lineage/refresh.py#L174) |
| `unsupported_lineage_input` | [lineage/source.py](../src/tarel/lineage/source.py#L156) |
| `unsupported_logical_topology` | [topology/contracts.py](../src/tarel/topology/contracts.py#L498), [topology/contracts.py](../src/tarel/topology/contracts.py#L657) |
| `unsupported_object_family` | [object_families/contracts.py](../src/tarel/object_families/contracts.py#L207) |
| `unsupported_package` | [packages/archive.py](../src/tarel/packages/archive.py#L201), [packages/contracts.py](../src/tarel/packages/contracts.py#L140) |
| `unsupported_query_linked_coverage` | [discovery/coverage.py](../src/tarel/discovery/coverage.py#L313) |
| `unsupported_reference_mapping` | [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L262), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L350) |
| `unsupported_reranker` | [retrieval/remote.py](../src/tarel/retrieval/remote.py#L37) |
| `unsupported_runtime_lineage` | [lineage/runtime.py](../src/tarel/lineage/runtime.py#L55), [lineage/runtime_records.py](../src/tarel/lineage/runtime_records.py#L68), [lineage/runtime_records.py](../src/tarel/lineage/runtime_records.py#L357) |
| `unsupported_semantic_format` | [semantics/readers.py](../src/tarel/semantics/readers.py#L25) |
| `unsupported_semantic_import` | [semantics/contracts.py](../src/tarel/semantics/contracts.py#L390), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L422) |
| `unsupported_source` | [sources/contracts.py](../src/tarel/sources/contracts.py#L79) |
| `unsupported_sync_state` | [sync/contracts.py](../src/tarel/sync/contracts.py#L469) |
| `unsupported_url` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L236), [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L245), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L601) |
| `unsupported_workspace` | [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L235), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L263) |
| `untrusted_host` | [ui/server.py](../src/tarel/ui/server.py#L119) |
| `untrusted_publisher` | [sync/authorization.py](../src/tarel/sync/authorization.py#L16) |
| `workspace_exists` | [workspaces/application.py](../src/tarel/workspaces/application.py#L59) |
| `workspace_not_found` | [workspaces/store.py](../src/tarel/workspaces/store.py#L53) |
| `workspace_required` | [ui/backend.py](../src/tarel/ui/backend.py#L1028) |
| `workspace_save_failed` | [workspaces/store.py](../src/tarel/workspaces/store.py#L42) |
| `zone_member_not_found` | [workspaces/core.py](../src/tarel/workspaces/core.py#L367) |
| `zone_not_found` | [workspaces/core.py](../src/tarel/workspaces/core.py#L295) |
| `zone_object_not_found` | [ui/backend.py](../src/tarel/ui/backend.py#L1194) |
| `zone_schema_unassigned` | [workspaces/core.py](../src/tarel/workspaces/core.py#L374) |

## Python SDK

The SDK calls the same application use cases as the CLI. It returns typed Python records and raises domain exceptions; it does not invoke CLI subprocesses. Select the state directory explicitly. Creating the client alone does not discover a source, download a model, or call a provider.

```python
from tarel.sdk import Tarel

tarel = Tarel("/srv/my-harness/.tarel")
```

### Provider and direct connector administration

Provider profiles are private user-level configuration, independent of the client's state root. `provider.test` makes one explicit network/model request and may incur provider cost. Checks and returned paths never contain the configured API key.

Direct connector methods require an explicit configuration path. They are a lower-level read-only surface and do not apply a named source's enrichment permissions. Prefer `tarel.source` when source-specific aggregate, small-domain, or raw-sample policy must be enforced. Samples returned here are ephemeral and are not persisted by the SDK.

```python
status = tarel.provider.check("local")
probe = tarel.connector.probe("sqlite", config="./private/source.toml")
sample = tarel.connector.sample(
    "sqlite", config="./private/source.toml",
    namespace="main", object="orders", limit=10,
)
```

### Graph and context example

Assumes `warehouse` already exists under that root. Returned records expose their typed fields; use their supported serializers rather than assuming every SDK result is a JSON dictionary.

```python
header = tarel.graph.header("warehouse")
page = tarel.graph.objects("warehouse", limit=10, expected_revision=header.revision)
packet = tarel.context.graph("warehouse", "customer revenue", mode="bm25")
parts = tarel.context.split(packet)
```

### Harness grounding example

Assumes the graph and logical source are already configured. The harness is responsible for model requests and authorized answer-query execution.

```python
bundle = tarel.grounding.context(
    "Explain customer revenue", graph="warehouse",
    sources=("warehouse-prod",), mode="bm25",
)
stable_text = bundle.stable_prompt()
dynamic_text = bundle.dynamic_prompt()
```

Keep the stable text unchanged only while its selected scope and revisions remain valid. The SDK does not promise provider cache acceptance.

### SDK method reference

Signatures below are generated from the public client namespaces, including default values and return types. Types refer to the definitions imported by [the SDK module](../src/tarel/sdk/client.py). Domain methods are explicit: CLI names do not always translate literally (for example `source build` is `source.build_graph`).

#### SDK annotation

```python
tarel.annotation.apply(graph: 'str', proposal: 'dict[str, Any]', *, source: 'str' = 'agent') -> 'AnnotationApplyResult'
```
```python
tarel.annotation.decide(graph: 'str', reference: 'str', *, state: 'str', reason: 'str', include_fields: 'bool' = False) -> 'AnnotationReviewResult'
```
```python
tarel.annotation.edit(graph: 'str', reference: 'str', patch: 'dict[str, Any]', *, reason: 'str') -> 'AnnotationReviewResult'
```
```python
tarel.annotation.plan_focus(name: 'str', *, namespace: 'str | None' = None, objects: 'set[str] | None' = None, limit: 'int | None' = None, missing_only: 'bool' = True, sample_limit: 'int' = 0, profile_row_limit: 'int' = 0, include_small_domain_values: 'bool' = False, config: 'str | Path | None' = None, knowledge: 'str' = 'none', knowledge_documents: 'tuple[str, ...]' = (), knowledge_workspace: 'str | None' = None, max_knowledge_characters: 'int' = 12000) -> 'tuple[AnnotationTask, ...]'
```
```python
tarel.annotation.plan_graph(name: 'str', *, namespace: 'str | None' = None, objects: 'set[str] | None' = None, limit: 'int | None' = None, missing_only: 'bool' = True, sample_limit: 'int' = 0, profile_row_limit: 'int' = 0, include_small_domain_values: 'bool' = False, config: 'str | Path | None' = None, knowledge: 'str' = 'none', knowledge_documents: 'tuple[str, ...]' = (), knowledge_workspace: 'str | None' = None, max_knowledge_characters: 'int' = 12000) -> 'tuple[AnnotationTask, ...]'
```
```python
tarel.annotation.reviews(graph: 'str', *, states: 'frozenset[str] | None' = None) -> 'tuple[AnnotationReviewRecord, ...]'
```
```python
tarel.annotation.run(graph: 'str', *, provider: 'str', namespace: 'str | None' = None, objects: 'set[str] | None' = None, limit: 'int | None' = None, missing_only: 'bool' = True, workers: 'int' = 1, retry: 'int' = 0, retry_backoff: 'float' = 2.0, skip_errors: 'bool' = False, max_errors: 'int | None' = None, model: 'str | None' = None, timeout: 'float' = 120.0, sample_limit: 'int' = 0, samples_by_target: 'Mapping[str, SampleResult] | None' = None, profile_row_limit: 'int' = 0, include_small_domain_values: 'bool' = False, config: 'str | Path | None' = None, knowledge: 'str' = 'none', knowledge_documents: 'tuple[str, ...]' = (), knowledge_workspace: 'str | None' = None, max_knowledge_characters: 'int' = 12000, progress: 'Callable[[int, int, str, str], None] | None' = None) -> 'AnnotationBatchResult'
```
```python
tarel.annotation.show(graph: 'str', reference: 'str') -> 'AnnotationReviewRecord'
```

#### SDK bindings

```python
tarel.bindings.find(graph: 'str', *, mode: 'str' = 'confirmed_only') -> 'tuple[dict[str, object], ...]'
```
```python
tarel.bindings.import_document(binding: 'ObjectValueBinding') -> 'ObjectValueBinding'
```
```python
tarel.bindings.load(graph: 'str', binding_id: 'str') -> 'ObjectValueBinding'
```
```python
tarel.bindings.resolve(graph: 'str', binding_id: 'str', *, expected_revision: 'str', values: 'tuple[str, ...]', mode: 'str' = 'confirmed_only', limit: 'int' = 100, namespace: 'str | None' = None, allowed_object_ids: 'frozenset[str] | None' = None) -> 'ObjectBindingResolution'
```
```python
tarel.bindings.review(graph: 'str', binding_id: 'str', *, expected_revision: 'str', decision: 'str', reason: 'str') -> 'ObjectValueBinding'
```

#### SDK concepts

```python
tarel.concepts.find(graph: 'str', *, query: 'str | None' = None, endpoint: 'LogicalEndpoint | None' = None, mode: 'str' = 'confirmed_only', limit: 'int' = 20, concept_id: 'str | None' = None, allowed_object_ids: 'frozenset[str] | None' = None) -> 'tuple[SemanticConceptMatch, ...]'
```
```python
tarel.concepts.import_document(document: 'SemanticConceptDocument', *, expected_revision: 'str | None' = None) -> 'SemanticConceptDocument'
```
```python
tarel.concepts.load(graph: 'str') -> 'SemanticConceptDocument'
```
```python
tarel.concepts.review(graph: 'str', concept_id: 'str', *, expected_revision: 'str', decision: 'str', reason: 'str') -> 'SemanticConceptDocument'
```

#### SDK connector

```python
tarel.connector.check(name: 'str') -> 'ConnectorCheck'
```
```python
tarel.connector.discover(name: 'str', *, config: 'str | Path', database: 'str | None' = None, namespace: 'str | None' = None) -> 'CatalogResult'
```
```python
tarel.connector.list() -> 'tuple[ConnectorCheck, ...]'
```
```python
tarel.connector.probe(name: 'str', *, config: 'str | Path', database: 'str | None' = None) -> 'ProbeResult'
```
```python
tarel.connector.profile(name: 'str', *, config: 'str | Path', namespace: 'str', object: 'str', row_limit: 'int', database: 'str | None' = None, small_domain_limit: 'int' = 20, include_values: 'bool' = False) -> 'ObjectProfileResult'
```
```python
tarel.connector.sample(name: 'str', *, config: 'str | Path', namespace: 'str', object: 'str', limit: 'int', database: 'str | None' = None) -> 'SampleResult'
```

#### SDK context

```python
tarel.context.brief(packet: 'ContextResult | ContextPacketSnapshot | dict[str, object] | str | Path') -> 'ContextBrief'
```
```python
tarel.context.compare(previous: 'ContextResult | ContextPacketSnapshot | dict[str, object] | str | Path', current: 'ContextResult | ContextPacketSnapshot | dict[str, object] | str | Path') -> 'ContextDelta'
```
```python
tarel.context.diff(left: 'str | Path', right: 'str | Path') -> 'ContextPacketDiff'
```
```python
tarel.context.expand(packet: 'ContextResult | ContextPacketSnapshot | dict[str, object]', targets: 'tuple[ExpansionTarget, ...]', *, mode: 'str' = 'confirmed_only', inputs: 'Mapping[str, ExpansionInput] | None' = None, max_characters: 'int' = 24000) -> 'ContextExpansion'
```
```python
tarel.context.graph(name: 'str', query: 'str', *, namespace: 'str | None' = None, seed_limit: 'int' = 3, max_objects: 'int' = 10, max_joins: 'int' = 12, max_hops: 'int' = 2, max_fields_per_object: 'int' = 12, max_characters: 'int' = 24000, mode: 'str' = 'lexical', model_path: 'str | Path | None' = None, n_threads: 'int | None' = None, bm25_weight: 'float | None' = None, annotation_states: 'frozenset[str] | None' = None, validated_only: 'bool' = False, logical_hints: 'str | None' = None, object_ids: 'tuple[str, ...]' = (), scope_object_ids: 'tuple[str, ...]' = (), focuses: 'tuple[str, ...]' = ()) -> 'ContextResult'
```
```python
tarel.context.impact(packet: 'str | Path', *, graph: 'str') -> 'ContextPacketImpact'
```
```python
tarel.context.prefix_graph(name: 'str', *, namespace: 'str | None' = None, max_objects: 'int' = 250, max_joins: 'int' = 500, max_fields_per_object: 'int' = 50, max_characters: 'int' = 500000, annotation_states: 'frozenset[str] | None' = None, validated_only: 'bool' = False, logical_hints: 'str | None' = None, scope_object_ids: 'tuple[str, ...]' = (), focuses: 'tuple[str, ...]' = ()) -> 'ContextResult'
```
```python
tarel.context.prefix_workspace(name: 'str', *, selection: 'ScopeSelection | None' = None, systems: 'tuple[str, ...]' = (), graphs: 'tuple[str, ...]' = (), areas: 'tuple[str, ...]' = (), schemas: 'tuple[str, ...]' = (), zones: 'tuple[str, ...]' = (), focuses: 'tuple[str, ...]' = (), scope_objects: 'tuple[str, ...]' = (), max_objects: 'int' = 250, max_joins: 'int' = 500, max_fields_per_object: 'int' = 50, max_characters: 'int' = 500000, annotation_states: 'frozenset[str] | None' = None, validated_only: 'bool' = False, logical_hints: 'str | None' = None) -> 'ContextResult'
```
```python
tarel.context.split(packet: 'ContextResult') -> 'ContextCacheParts'
```
```python
tarel.context.workspace(name: 'str', query: 'str', *, selection: 'ScopeSelection | None' = None, systems: 'tuple[str, ...]' = (), graphs: 'tuple[str, ...]' = (), areas: 'tuple[str, ...]' = (), schemas: 'tuple[str, ...]' = (), zones: 'tuple[str, ...]' = (), focuses: 'tuple[str, ...]' = (), scope_objects: 'tuple[str, ...]' = (), seed_limit: 'int' = 3, max_objects: 'int' = 10, max_joins: 'int' = 12, max_hops: 'int' = 2, max_fields_per_object: 'int' = 12, max_characters: 'int' = 24000, mode: 'str' = 'lexical', model_path: 'str | Path | None' = None, n_threads: 'int | None' = None, bm25_weight: 'float | None' = None, annotation_states: 'frozenset[str] | None' = None, validated_only: 'bool' = False, logical_hints: 'str | None' = None, object_ids: 'tuple[str, ...]' = ()) -> 'ContextResult'
```

#### SDK discovery

```python
tarel.discovery.advise(run_id: 'str', *, expected_revision: 'str', count: 'int' = 3, model: 'str | None' = None, timeout: 'float' = 120.0) -> 'DiscoveryAdviceResult'
```
```python
tarel.discovery.find(*, graph: 'str | None' = None, kind: 'str | None' = None, include_exploratory: 'bool' = False, query: 'str | None' = None, limit: 'int' = 20) -> 'tuple[DiscoveryMatch, ...]'
```
```python
tarel.discovery.list(*, graph: 'str | None' = None, kind: 'str | None' = None) -> 'tuple[DiscoveryRun, ...]'
```
```python
tarel.discovery.load(run_id: 'str') -> 'DiscoveryRun'
```
```python
tarel.discovery.load_coverage(run_id: 'str') -> 'QueryLinkedEntityCoverage'
```
```python
tarel.discovery.next(run_id: 'str') -> 'DiscoveryTask'
```
```python
tarel.discovery.promote(run_id: 'str', *, candidates: 'tuple[str, ...]', reason: 'str', supersedes: 'str | None' = None) -> 'DiscoveryPromotionResult'
```
```python
tarel.discovery.record_coverage(run_id: 'str', coverage: 'dict[str, Any]') -> 'DiscoveryCoverageResult'
```
```python
tarel.discovery.start(kind: 'str', *, graph: 'str', sources: 'tuple[str, ...]' = (), question: 'str | None' = None, probe_budget: 'int' = 40, candidate_budget: 'int' = 20, advisor_provider: 'str | None' = None, identity_inspection: 'bool' = False, logical_endpoints: 'bool' = False, scope_mode: 'str' = 'global_population', run_id: 'str | None' = None) -> 'DiscoveryChangeResult'
```
```python
tarel.discovery.submit(run_id: 'str', *, expected_revision: 'str', action: 'str', payload: 'dict[str, Any]', actor: 'str' = 'coding_agent') -> 'DiscoveryChangeResult'
```

#### SDK entity_resolution

```python
tarel.entity_resolution.decide(candidate_id: 'str', *, decision: 'str', reason: 'str', expected_revision: 'str | None' = None) -> 'EntityResolutionChangeResult'
```
```python
tarel.entity_resolution.find(graph: 'str', *, source: 'str | None' = None, target: 'str | None' = None, mode: 'str' = 'confirmed_then_candidates') -> 'tuple[EntityResolutionMatch, ...]'
```
```python
tarel.entity_resolution.import_candidate(candidate: 'EntityResolutionCandidate') -> 'EntityResolutionChangeResult'
```
```python
tarel.entity_resolution.list(*, graph: 'str | None' = None) -> 'tuple[EntityResolutionCandidate, ...]'
```
```python
tarel.entity_resolution.load(candidate_id: 'str') -> 'EntityResolutionCandidate'
```
```python
tarel.entity_resolution.resolve(graph: 'str', *, object: 'str', key: 'str', mode: 'str' = 'confirmed_then_candidates') -> 'tuple[EntityAliasMatch, ...]'
```

#### SDK families

```python
tarel.families.import_document(document: 'ObjectFamily') -> 'ObjectFamily'
```
```python
tarel.families.list(graph: 'str') -> 'tuple[dict[str, object], ...]'
```
```python
tarel.families.load(graph: 'str', family_id: 'str') -> 'ObjectFamily'
```
```python
tarel.families.load_run(run_id: 'str') -> 'FamilyProposalRun'
```
```python
tarel.families.members(graph: 'str', family_id: 'str', *, expected_revision: 'str', mode: 'str' = 'confirmed_only', offset: 'int' = 0, limit: 'int' = 50, filters: 'Mapping[str, str] | None' = None, namespace: 'str | None' = None, allowed_object_ids: 'frozenset[str] | None' = None) -> 'FamilyMemberPage'
```
```python
tarel.families.plan(graph: 'str', run_id: 'str', *, provider_name: 'str', model: 'str | None' = None, objects_per_batch: 'int' = 50, max_input_chars: 'int' = 40000, max_objects: 'int' = 1000) -> 'FamilyProposalRun'
```
```python
tarel.families.propose(graph: 'str', family_id: 'str', *, name: 'str', members: 'tuple[str, ...]', grain: 'tuple[str, ...]', attributes: 'tuple[FamilyAttribute, ...]' = (), producer: 'str' = 'coding_agent') -> 'ObjectFamily'
```
```python
tarel.families.review(graph: 'str', family_id: 'str', *, decision: 'str', reason: 'str', expected_revision: 'str') -> 'ObjectFamily'
```
```python
tarel.families.run(run_id: 'str', *, workers: 'int' = 1, resume: 'bool' = False, timeout: 'float' = 120.0) -> 'FamilyProposalRun'
```

#### SDK focus

```python
tarel.focus.build(name: 'str', *, seed: 'str', lineages: 'tuple[str, ...]', graphs: 'tuple[str, ...]', max_hops: 'int' = 12, states: 'frozenset[str] | None' = None) -> 'FocusBuildResult'
```
```python
tarel.focus.list() -> 'tuple[str, ...]'
```
```python
tarel.focus.load(name: 'str') -> 'FocusDocument'
```

#### SDK graph

```python
tarel.graph.build(name: 'str', *, connector: 'str', config: 'str | Path | None' = None, database: 'str | None' = None, namespace: 'str | None' = None) -> 'GraphBuildResult'
```
```python
tarel.graph.header(name: 'str') -> 'GraphHeader'
```
```python
tarel.graph.import_catalog(name: 'str', catalog: 'CatalogResult') -> 'GraphBuildResult'
```
```python
tarel.graph.list() -> 'tuple[str, ...]'
```
```python
tarel.graph.load(name: 'str') -> 'GraphDocument'
```
```python
tarel.graph.objects(name: 'str', *, object_ids: 'tuple[str, ...] | None' = None, namespace: 'str | None' = None, offset: 'int' = 0, limit: 'int' = 100, expected_revision: 'str | None' = None) -> 'GraphObjectPage'
```
```python
tarel.graph.rebuild_index(name: 'str') -> 'GraphHeader'
```
```python
tarel.graph.refresh(name: 'str', *, config: 'str | Path | None' = None, namespace: 'str | None' = None, annotate_new_provider: 'str | None' = None, annotation_workers: 'int' = 1, annotation_model: 'str | None' = None, annotation_timeout: 'float' = 120.0) -> 'GraphRefreshResult'
```
```python
tarel.graph.slice(name: 'str', object_ids: 'tuple[str, ...]', *, namespace: 'str | None' = None, expected_revision: 'str | None' = None) -> 'GraphSlice'
```

#### SDK grounding

```python
tarel.grounding.context(question: 'str', *, graph: 'str | None' = None, workspace: 'str | None' = None, namespace: 'str | None' = None, selection: 'ScopeSelection | None' = None, systems: 'tuple[str, ...]' = (), graphs: 'tuple[str, ...]' = (), areas: 'tuple[str, ...]' = (), schemas: 'tuple[str, ...]' = (), zones: 'tuple[str, ...]' = (), lineages: 'tuple[str, ...]' = (), sources: 'tuple[str, ...]' = (), trace: 'str | None' = None, lineage_limit: 'int' = 8, lineage_mode: 'str' = 'bm25', lineage_states: 'frozenset[str] | None' = None, seed_limit: 'int' = 3, max_objects: 'int' = 10, max_joins: 'int' = 12, max_hops: 'int' = 2, max_trace_hops: 'int' = 12, max_fields_per_object: 'int' = 12, max_characters: 'int' = 24000, mode: 'str' = 'lexical', model_path: 'str | Path | None' = None, n_threads: 'int | None' = None, annotation_states: 'frozenset[str] | None' = None, validated_only: 'bool' = False, logical_hints: 'str | None' = None) -> 'GroundingBundle'
```
```python
tarel.grounding.describe(graph: 'str', reference: 'str', *, source: 'str | None' = None) -> 'GroundingAsset'
```
```python
tarel.grounding.find(query: 'str', *, graph: 'str | None' = None, workspace: 'str | None' = None, namespace: 'str | None' = None, selection: 'ScopeSelection | None' = None, systems: 'tuple[str, ...]' = (), graphs: 'tuple[str, ...]' = (), areas: 'tuple[str, ...]' = (), schemas: 'tuple[str, ...]' = (), zones: 'tuple[str, ...]' = (), lineages: 'tuple[str, ...]' = (), sources: 'tuple[str, ...]' = (), limit: 'int' = 10, lineage_mode: 'str' = 'bm25', mode: 'str' = 'lexical', model_path: 'str | Path | None' = None, n_threads: 'int | None' = None, annotation_states: 'frozenset[str] | None' = None, validated_only: 'bool' = False, logical_hints: 'str | None' = None) -> 'GroundingBundle'
```
```python
tarel.grounding.upstream(reference: 'str', *, lineages: 'tuple[str, ...]', graph: 'str | None' = None, workspace: 'str | None' = None, selection: 'ScopeSelection | None' = None, systems: 'tuple[str, ...]' = (), graphs: 'tuple[str, ...]' = (), areas: 'tuple[str, ...]' = (), schemas: 'tuple[str, ...]' = (), zones: 'tuple[str, ...]' = (), max_hops: 'int' = 12, states: 'frozenset[str] | None' = None) -> 'UpstreamTrace'
```

#### SDK index

```python
tarel.index.build(graph: 'str', *, model_path: 'str | Path | None' = None, batch_size: 'int' = 16, n_threads: 'int | None' = None, resume: 'bool' = False, progress: 'Callable[[int, int, str], None] | None' = None, annotation_states: 'frozenset[str] | None' = None, validated_only: 'bool' = False) -> 'IndexBuildResult'
```
```python
tarel.index.build_workspace(workspace: 'str', *, systems: 'tuple[str, ...]' = (), graphs: 'tuple[str, ...]' = (), areas: 'tuple[str, ...]' = (), schemas: 'tuple[str, ...]' = (), zones: 'tuple[str, ...]' = (), model_path: 'str | Path | None' = None, batch_size: 'int' = 16, n_threads: 'int | None' = None, resume: 'bool' = False, max_graphs: 'int' = 8, progress: 'Callable[[int, int, str], None] | None' = None, annotation_states: 'frozenset[str] | None' = None, validated_only: 'bool' = False) -> 'WorkspaceIndexBuild'
```
```python
tarel.index.status(graph: 'str', *, model_path: 'str | Path | None' = None, annotation_states: 'frozenset[str] | None' = None, validated_only: 'bool' = False) -> 'IndexStatus'
```
```python
tarel.index.status_workspace(workspace: 'str', *, systems: 'tuple[str, ...]' = (), graphs: 'tuple[str, ...]' = (), areas: 'tuple[str, ...]' = (), schemas: 'tuple[str, ...]' = (), zones: 'tuple[str, ...]' = (), model_path: 'str | Path | None' = None, annotation_states: 'frozenset[str] | None' = None, validated_only: 'bool' = False) -> 'WorkspaceIndexStatus'
```

#### SDK knowledge

```python
tarel.knowledge.add(document_id: 'str', path: 'str | Path', *, scope: 'str', title: 'str | None' = None, state: 'str' = 'draft', workspace: 'str | None' = None, replace: 'bool' = False) -> 'KnowledgeChangeResult'
```
```python
tarel.knowledge.list() -> 'tuple[KnowledgeDocument, ...]'
```
```python
tarel.knowledge.load(document_id: 'str') -> 'KnowledgeDocument'
```
```python
tarel.knowledge.resolve(graph: 'str', object_reference: 'str', *, mode: 'str' = 'scoped', documents: 'tuple[str, ...]' = (), workspace: 'str | None' = None, max_characters: 'int' = 12000) -> 'KnowledgeContext'
```

#### SDK lineage

```python
tarel.lineage.add_hop(name: 'str', *, job: 'str', source: 'str', target: 'str', operation: 'str', role: 'str' = 'business_data', evidence_reference: 'str', reason: 'str', line_start: 'int' = 1, line_end: 'int' = 1, expected_revision: 'str | None' = None) -> 'ManualHopResult'
```
```python
tarel.lineage.add_job(name: 'str', *, kind: 'str', job_name: 'str', qualified_name: 'str', language: 'str', source_reference: 'str', description: 'str', expected_revision: 'str | None' = None) -> 'ManualJobResult'
```
```python
tarel.lineage.analyze(name: 'str', *, source: 'str | Path', analyzer: 'str' = 'llm', provider: 'str | None' = None, dialect: 'str | None' = None, model: 'str | None' = None, timeout: 'float' = 180.0, retry: 'int' = 1, limit: 'int | None' = None, definitions: 'tuple[str, ...]' = (), review_passes: 'int' = 1, max_output_tokens: 'int | None' = None, reasoning_effort: 'str | None' = None, progress: 'Callable[[str], None] | None' = None) -> 'LineageProviderRunResult'
```
```python
tarel.lineage.apply(name: 'str', *, source: 'str | Path', proposal: 'dict[str, Any]') -> 'LineageChangeResult'
```
```python
tarel.lineage.build(name: 'str', *, source: 'str | Path') -> 'LineageChangeResult'
```
```python
tarel.lineage.decide(name: 'str', claim_id: 'str', *, decision: 'str', reason: 'str', expected_revision: 'str | None' = None) -> 'LineageReviewResult'
```
```python
tarel.lineage.find(query: 'str', *, lineages: 'tuple[str, ...]', graphs: 'tuple[str, ...]' = (), limit: 'int' = 20, mode: 'str' = 'lexical', model_path: 'str | Path | None' = None, n_threads: 'int | None' = None) -> 'tuple[LineageReference, ...]'
```
```python
tarel.lineage.find_workspace(workspace: 'str', query: 'str', *, lineages: 'tuple[str, ...]', selection: 'ScopeSelection | None' = None, systems: 'tuple[str, ...]' = (), graphs: 'tuple[str, ...]' = (), areas: 'tuple[str, ...]' = (), schemas: 'tuple[str, ...]' = (), zones: 'tuple[str, ...]' = (), limit: 'int' = 20, mode: 'str' = 'lexical', model_path: 'str | Path | None' = None, n_threads: 'int | None' = None) -> 'tuple[LineageReference, ...]'
```
```python
tarel.lineage.import_dbt(name: 'str', *, manifest: 'str | Path', catalog_map: 'Mapping[str, str] | None' = None) -> 'LineageChangeResult'
```
```python
tarel.lineage.import_runtime(name: 'str', observed: 'RuntimeLineageInput') -> 'RuntimeLineageImportResult'
```
```python
tarel.lineage.list() -> 'tuple[str, ...]'
```
```python
tarel.lineage.list_runtime() -> 'tuple[str, ...]'
```
```python
tarel.lineage.load(name: 'str') -> 'LineageDocument'
```
```python
tarel.lineage.load_runtime(name: 'str') -> 'RuntimeLineageDocument'
```
```python
tarel.lineage.next(name: 'str', *, source: 'str | Path') -> 'LineageTask | None'
```
```python
tarel.lineage.process(name: 'str') -> 'tuple[ProcessStep, ...]'
```
```python
tarel.lineage.reviews(name: 'str', *, states: 'frozenset[str] | None' = None) -> 'tuple[LineageReviewItem, ...]'
```
```python
tarel.lineage.status(name: 'str') -> 'LineageStatus'
```
```python
tarel.lineage.tables(name: 'str') -> 'tuple[TableLineage, ...]'
```
```python
tarel.lineage.trace_runtime(name: 'str', call_id: 'str') -> 'RuntimeLineageTrace'
```
```python
tarel.lineage.upstream(reference: 'str', *, lineages: 'tuple[str, ...]', graphs: 'tuple[str, ...]' = (), max_hops: 'int' = 12, states: 'frozenset[str] | None' = None) -> 'UpstreamTrace'
```
```python
tarel.lineage.upstream_workspace(workspace: 'str', reference: 'str', *, lineages: 'tuple[str, ...]', selection: 'ScopeSelection | None' = None, systems: 'tuple[str, ...]' = (), graphs: 'tuple[str, ...]' = (), areas: 'tuple[str, ...]' = (), schemas: 'tuple[str, ...]' = (), zones: 'tuple[str, ...]' = (), max_hops: 'int' = 12, states: 'frozenset[str] | None' = None) -> 'UpstreamTrace'
```

#### SDK logical_joins

```python
tarel.logical_joins.find(graph: 'str', *, mode: 'str' = 'confirmed_only', endpoint: 'LogicalEndpoint | None' = None, join_id: 'str | None' = None, limit: 'int' = 20) -> 'tuple[LogicalJoinMatch, ...]'
```
```python
tarel.logical_joins.list(*, graph: 'str | None' = None) -> 'tuple[LogicalJoin, ...]'
```
```python
tarel.logical_joins.load(join_id: 'str') -> 'LogicalJoin'
```
```python
tarel.logical_joins.review(join_id: 'str', *, expected_revision: 'str', decision: 'str', reason: 'str') -> 'LogicalJoin'
```

#### SDK model

```python
tarel.model.download(*, name: 'str' = 'qwen3-embedding-0.6b-q4-k-m', target: 'str | Path | None' = None, force: 'bool' = False, progress: 'Callable[[int, int], None] | None' = None) -> 'ModelDownloadResult'
```
```python
tarel.model.status(*, name: 'str' = 'qwen3-embedding-0.6b-q4-k-m', model_path: 'str | Path | None' = None) -> 'ModelStatus'
```

#### SDK provider

```python
tarel.provider.check(name: 'str') -> 'ProviderCheck'
```
```python
tarel.provider.configure(name: 'str', *, adapter: 'str | None' = None, api_key: 'str | None' = None, model: 'str | None' = None, base_url: 'str | None' = None, reasoning_effort: 'str | None' = None, structured_mode: 'str | None' = None, allow_no_api_key: 'bool' = False) -> 'Path'
```
```python
tarel.provider.list() -> 'tuple[str, ...]'
```
```python
tarel.provider.test(name: 'str', *, timeout: 'float' = 120.0) -> 'ProviderTestResult'
```

#### SDK reference_mapping

```python
tarel.reference_mapping.decide(candidate_id: 'str', *, decision: 'str', reason: 'str', expected_revision: 'str') -> 'ReferenceMappingChangeResult'
```
```python
tarel.reference_mapping.find(graph: 'str', *, source: 'str | None' = None, target: 'str | None' = None, mode: 'str' = 'confirmed_then_candidates') -> 'tuple[ReferenceMappingMatch, ...]'
```
```python
tarel.reference_mapping.import_candidate(candidate: 'ReferenceMappingCandidate') -> 'ReferenceMappingChangeResult'
```
```python
tarel.reference_mapping.list(*, graph: 'str | None' = None) -> 'tuple[ReferenceMappingCandidate, ...]'
```
```python
tarel.reference_mapping.load(candidate_id: 'str') -> 'ReferenceMappingCandidate'
```

#### SDK relationship

```python
tarel.relationship.add(graph: 'str', *, source: 'str', target: 'str', reason: 'str', validated: 'bool' = False) -> 'RelationshipChangeResult'
```
```python
tarel.relationship.check(graph: 'str', *, source: 'str', target: 'str', config: 'str | Path', row_limit: 'int' = 10000) -> 'RelationshipPairProfile'
```
```python
tarel.relationship.decide(graph: 'str', edge_id: 'str', *, state: 'str', reason: 'str') -> 'RelationshipChangeResult'
```
```python
tarel.relationship.discover(graph: 'str', *, object_reference: 'str', config: 'str | Path', field: 'str | None' = None, max_pairs: 'int' = 20, row_limit: 'int' = 10000, min_source_coverage: 'float' = 0.85, min_overlap_count: 'int' = 3, min_target_uniqueness: 'float' = 0.9, persist: 'bool' = True, focus: 'str | None' = None, expand_one_hop: 'bool' = False) -> 'RelationshipDiscoveryResult'
```
```python
tarel.relationship.list(graph: 'str') -> 'tuple[GraphEdge, ...]'
```

#### SDK retrieval

```python
tarel.retrieval.configure(settings: tarel.retrieval.settings.RetrievalSettings) -> tarel.retrieval.settings.RetrievalSettings
```
```python
tarel.retrieval.models(*, provider: str = 'local', task: str = 'embedding') -> tarel.retrieval.contracts.ModelCatalog
```
```python
tarel.retrieval.settings() -> tarel.retrieval.settings.RetrievalSettings
```

#### SDK search

```python
tarel.search.graph(name: 'str', query: 'str', *, limit: 'int' = 20, namespace: 'str | None' = None, mode: 'str' = 'lexical', model_path: 'str | Path | None' = None, n_threads: 'int | None' = None, bm25_weight: 'float | None' = None, annotation_states: 'frozenset[str] | None' = None, validated_only: 'bool' = False, family_mode: 'str | None' = 'confirmed_only', filters: 'SearchFilters | None' = None, focuses: 'tuple[str, ...]' = (), scope_object_ids: 'tuple[str, ...]' = ()) -> 'SearchResults'
```
```python
tarel.search.workspace(name: 'str', query: 'str', *, selection: 'ScopeSelection | None' = None, systems: 'tuple[str, ...]' = (), graphs: 'tuple[str, ...]' = (), areas: 'tuple[str, ...]' = (), schemas: 'tuple[str, ...]' = (), zones: 'tuple[str, ...]' = (), focuses: 'tuple[str, ...]' = (), scope_objects: 'tuple[str, ...]' = (), limit: 'int' = 20, mode: 'str' = 'lexical', model_path: 'str | Path | None' = None, n_threads: 'int | None' = None, bm25_weight: 'float | None' = None, annotation_states: 'frozenset[str] | None' = None, validated_only: 'bool' = False, family_mode: 'str | None' = 'confirmed_only', filters: 'SearchFilters | None' = None) -> 'SearchResults'
```

#### SDK semantic

```python
tarel.semantic.edit(name: 'str', target_id: 'str', patch: 'dict[str, object]', *, reason: 'str', revision: 'str | None' = None) -> 'SemanticImportResult'
```
```python
tarel.semantic.import_file(name: 'str', *, graph: 'str', source: 'str | Path', format_name: 'str' = 'apache-ossie', replace: 'bool' = False) -> 'SemanticImportResult'
```
```python
tarel.semantic.list(*, graph: 'str | None' = None) -> 'tuple[SemanticImportDocument, ...]'
```
```python
tarel.semantic.load(name: 'str') -> 'SemanticImportDocument'
```

#### SDK source

```python
tarel.source.build_graph(name: 'str', graph: 'str', *, database: 'str | None' = None, namespace: 'str | None' = None) -> 'GraphBuildResult'
```
```python
tarel.source.check(name: 'str') -> 'SourceCheck'
```
```python
tarel.source.configure(name: 'str', *, connector: 'str', config_reference: 'str | None' = None, database: 'str | None' = None, namespace: 'str | None' = None, graphs: 'tuple[str, ...]' = (), enrichment_permissions: 'tuple[str, ...]' = (), replace: 'bool' = False) -> 'SourceChangeResult'
```
```python
tarel.source.discover(name: 'str', *, database: 'str | None' = None, namespace: 'str | None' = None) -> 'CatalogResult'
```
```python
tarel.source.enrich(name: 'str', graph: 'str', *, profile_row_limit: 'int' = 10000, sample_limit: 'int' = 10, persist_join_candidates: 'bool' = False) -> 'SourceEnrichmentResult'
```
```python
tarel.source.list() -> 'tuple[str, ...]'
```
```python
tarel.source.load(name: 'str') -> 'SourceProfile'
```
```python
tarel.source.probe(name: 'str', *, database: 'str | None' = None) -> 'ProbeResult'
```
```python
tarel.source.refresh_graph(name: 'str', graph: 'str', *, namespace: 'str | None' = None, annotate_new_provider: 'str | None' = None, annotation_workers: 'int' = 1, annotation_model: 'str | None' = None, annotation_timeout: 'float' = 120.0) -> 'GraphRefreshResult'
```

#### SDK sync

```python
tarel.sync.apply(path: 'str | Path', *, plan_id: 'str | None' = None, allow_unsigned_dev: 'bool' = False, accept_history_gap: 'bool' = False) -> 'ApplyResult'
```
```python
tarel.sync.create_stream(name: 'str', *, graph: 'str', namespaces: 'tuple[str, ...]', annotations: 'bool' = False, technical_descriptions: 'bool' = False) -> 'PublisherStream'
```
```python
tarel.sync.init_publisher() -> 'str'
```
```python
tarel.sync.inspect(path: 'str | Path') -> 'PublicationReport'
```
```python
tarel.sync.plan(path: 'str | Path', *, allow_unsigned_dev: 'bool' = False, accept_history_gap: 'bool' = False) -> 'SyncPlan'
```
```python
tarel.sync.process_inbox(directory: 'str | Path', *, min_age_seconds: 'float' = 0, allow_unsigned_dev: 'bool' = False) -> 'InboxResult'
```
```python
tarel.sync.prune(stream_id: 'str') -> 'PruneResult'
```
```python
tarel.sync.publish(stream: 'str', *, output: 'str | Path', observed_at: 'str | None' = None, completeness: 'str | None' = None, signing_key: 'str | Path | None' = None, unsigned_dev: 'bool' = False) -> 'PublishResult'
```
```python
tarel.sync.recover() -> 'tuple[str, ...]'
```
```python
tarel.sync.revoke_key(publisher_id: 'str', fingerprint: 'str') -> 'TrustedKey'
```
```python
tarel.sync.set_trust_scope(stream_id: 'str', *, namespaces: 'tuple[str, ...]', annotations: 'bool' = False, technical_descriptions: 'bool' = False) -> 'TrustEntry'
```
```python
tarel.sync.status(*, max_age_hours: 'float | None' = None) -> 'tuple[StreamStatus, ...]'
```
```python
tarel.sync.trust(*, publisher_id: 'str', stream_id: 'str', graph_id: 'str', local_graph: 'str', workspace: 'str', system: 'str', namespaces: 'tuple[str, ...]', annotations: 'bool' = False, technical_descriptions: 'bool' = False) -> 'TrustEntry'
```
```python
tarel.sync.trust_key(publisher_id: 'str', *, public_key: 'str', not_after: 'str | None' = None) -> 'TrustedKey'
```
```python
tarel.sync.update_stream(name: 'str', *, namespaces: 'tuple[str, ...]', annotations: 'bool' = False, technical_descriptions: 'bool' = False) -> 'PublisherStream'
```

#### SDK topology

```python
tarel.topology.document(graph: 'str', derived_relations: 'tuple[DerivedRelation, ...]') -> 'LogicalTopologyDocument'
```
```python
tarel.topology.import_document(document: 'LogicalTopologyDocument', *, expected_revision: 'str | None' = None) -> 'LogicalTopologyDocument'
```
```python
tarel.topology.list() -> 'tuple[LogicalTopologyDocument, ...]'
```
```python
tarel.topology.load(graph: 'str') -> 'LogicalTopologyDocument'
```
```python
tarel.topology.review(graph: 'str', relation_id: 'str', *, decision: 'str', reason: 'str', expected_revision: 'str') -> 'LogicalTopologyDocument'
```

#### SDK ui

```python
tarel.ui.serve(graph: 'str | None' = None, *, workspace: 'str | None' = None, systems: 'tuple[str, ...]' = (), graphs: 'tuple[str, ...]' = (), areas: 'tuple[str, ...]' = (), schemas: 'tuple[str, ...]' = (), zones: 'tuple[str, ...]' = (), lineages: 'tuple[str, ...]' = (), focuses: 'tuple[str, ...]' = (), editable: 'bool' = False, family_mode: 'str | None' = None, architecture_file: 'Path | None' = None, architecture_edit: 'bool' = False, port: 'int' = 0, open_browser: 'bool' = True, search_mode: 'str' = 'bm25', model_path: 'Path | None' = None, n_threads: 'int | None' = None, on_ready: 'Callable[[str], None] | None' = None) -> 'int'
```

#### SDK view

```python
tarel.view.graph(name: 'str', *, lineages: 'tuple[str, ...]' = (), editable: 'bool' = False, family_mode: 'str | None' = None, focuses: 'tuple[str, ...]' = ()) -> 'dict[str, object]'
```
```python
tarel.view.workspace(name: 'str', *, lineages: 'tuple[str, ...]' = (), selection: 'ScopeSelection | None' = None, systems: 'tuple[str, ...]' = (), graphs: 'tuple[str, ...]' = (), areas: 'tuple[str, ...]' = (), schemas: 'tuple[str, ...]' = (), zones: 'tuple[str, ...]' = (), editable: 'bool' = False, family_mode: 'str | None' = None, focuses: 'tuple[str, ...]' = ()) -> 'dict[str, object]'
```

#### SDK workspace

```python
tarel.workspace.add_relationship(name: 'str', *, source: 'str', target: 'str', reason: 'str', validated: 'bool' = False) -> 'WorkspaceRelationshipChangeResult'
```
```python
tarel.workspace.create(name: 'str', *, description: 'str | None' = None) -> 'WorkspaceChangeResult'
```
```python
tarel.workspace.decide_relationship(name: 'str', relationship_id: 'str', *, state: 'str', reason: 'str') -> 'WorkspaceRelationshipChangeResult'
```
```python
tarel.workspace.define_area(name: 'str', system: 'str', area: 'str', *, schemas: 'tuple[str, ...]', description: 'str | None' = None) -> 'WorkspaceChangeResult'
```
```python
tarel.workspace.define_system(name: 'str', system: 'str', *, graphs: 'tuple[str, ...]', description: 'str | None' = None) -> 'WorkspaceChangeResult'
```
```python
tarel.workspace.define_zone(name: 'str', system: 'str', zone: 'str', *, objects: 'tuple[str, ...]', description: 'str | None' = None) -> 'WorkspaceChangeResult'
```
```python
tarel.workspace.list() -> 'tuple[str, ...]'
```
```python
tarel.workspace.load(name: 'str') -> 'WorkspaceDocument'
```
```python
tarel.workspace.relationships(name: 'str') -> 'tuple[WorkspaceRelationship, ...]'
```
```python
tarel.workspace.scope(name: 'str', *, selection: 'ScopeSelection | None' = None, systems: 'tuple[str, ...]' = (), graphs: 'tuple[str, ...]' = (), areas: 'tuple[str, ...]' = (), schemas: 'tuple[str, ...]' = (), zones: 'tuple[str, ...]' = (), focuses: 'tuple[str, ...]' = (), objects: 'tuple[str, ...]' = ()) -> 'ResolvedScope'
```
```python
tarel.workspace.zone(name: 'str', system: 'str', zone: 'str') -> 'ResolvedZone'
```

### Explicit setup helpers

Development setup writes to explicit paths and stays separate from the state-bound client. These helpers share the CLI application paths. They do not install or activate generated adapters.

```python
from tarel.sdk import (
    create_demo, install_agent_skill, scaffold_connector, scaffold_provider,
)

demo = create_demo("retail-dwh", path="./private/retail.sqlite")
connector = scaffold_connector("example", output="./candidates/example-connector")
provider = scaffold_provider("example", output="./candidates/example-provider")
skill = install_agent_skill("codex", target="./agent-project")
```

The experimental architecture sidecar remains a UI-local prototype and has no stable SDK read/write contract.

### Errors and concurrency

Catch the relevant domain Failure class when integrating; preserve its code and handle stale revisions explicitly. A client root is independent of the process working directory. Concurrent reads are supported; coordinate writers targeting the same persisted document. An SDK review call changes the same knowledge that the CLI/browser reads.

[Architecture and extension contracts](architecture.md) · [Contract reference](contracts.md) · [Demo](retail-demo.md) · [Workshop](workshop.md)
