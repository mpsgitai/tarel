# TAREL CLI Reference

Command reference for the CLI shipped in this source tree. Regenerate with `python tools/generate_cli_reference.py`.

Syntax, choices, defaults, required flags, and mutually exclusive groups are generated from the CLI parser. The command notes describe behavior; the linked contracts define structured inputs and outputs. Resource names in examples must be replaced with resources in your environment.

**Coverage:** 143 executable commands in 28 groups.

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
| [demo](#demo) | 1 | Create a deterministic local source for learning and regression exercises. |
| [workspace](#workspace) | 12 | Organize independent source graphs into systems, areas, schema scopes, and overlapping object zones. |
| [source](#source) | 9 | Name a connection profile once and use it for discovery, graph creation, enrichment, and grounding. |
| [connector](#connector) | 6 | Call a connector directly, inspect its availability, or scaffold a new adapter. |
| [knowledge](#knowledge) | 4 | Attach scoped business documentation for annotation tasks. |
| [provider](#provider) | 5 | Configure an optional structured-generation endpoint or create an adapter candidate. |
| [model](#model) | 2 | Manage the optional local embedding model used by vector and hybrid retrieval. |
| [index](#index) | 2 | Prepare and inspect rebuildable local retrieval indexes for a graph. |
| [graph](#graph) | 10 | Build, refresh, annotate, and inspect the technical and semantic snapshot of a source. |
| [ui](#ui) | 1 | Explore graph/workspace structure, lineage, and reviewable knowledge. |
| [lineage](#lineage) | 14 | Describe data dependencies, analyze definitions, trace upstream origins, and record observed executions. |
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
| [context](#context) | 5 | Build a bounded context packet, prepare a stable prefix, compare packets, or expand pinned metadata. |
| [grounding](#grounding) | 1 | Combine a context packet with source identity, dialects, and selected lineage information. |
| [annotation](#annotation) | 9 | Plan knowledge work, hand a task to the harness, apply a proposal, and review its meaning. |
| [relationship](#relationship) | 6 | Propose, probe, discover, and review physical field relationships. |

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

### tarel source refresh

Refresh a bound graph through this logical source.

**Syntax**

```text
tarel source refresh [-h] [--namespace NAMESPACE] [--format {text,json}] name graph_name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `graph_name` | text | required | not set | Local graph name. |
| `--namespace, --schema` | text | optional | not set | Namespace/schema filter. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Profile, availability/probe result, observed catalog, graph summary, or enrichment workfile according to the verb. Config references remain distinct from resolved credentials.

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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
 | [`tarel connector check`](#tarel-connector-check) | Validate a connector and its dependencies. |
 | [`tarel connector probe`](#tarel-connector-probe) | Run a bounded read-only connection probe. |
 | [`tarel connector discover`](#tarel-connector-discover) | Read schemas, tables, views, and fields from a source. |
 | [`tarel connector scaffold`](#tarel-connector-scaffold) | Create an isolated connector candidate for an agent or human. |
 | [`tarel connector sample`](#tarel-connector-sample) | Explicitly read a bounded sample from one object. |
 | [`tarel connector profile`](#tarel-connector-profile) | Read bounded aggregate column profiles from one object. |

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

## model

**Local embedding model.** Manage the optional local embedding model used by vector and hybrid retrieval.

Download fetches a model artifact; status reports availability. This is an embedding model, not a local annotation/generation model.

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

**Result:** Download/status information for the embedding model artifact.

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

**Result:** Download/status information for the embedding model artifact.

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

## index

**Retrieval indexes.** Prepare and inspect rebuildable local retrieval indexes for a graph.

Build writes the index and may perform local CPU embedding computation. Resume only reuses a compatible checkpoint. Graph, review, or model changes can require rebuilding.

Contract and workflow: [local-retrieval.md](contracts.md#local-retrieval).

Example:

```bash
tarel index status warehouse
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel index build`](#tarel-index-build) | Embed safe graph metadata into a rebuildable local SQLite index. |
 | [`tarel index status`](#tarel-index-status) | Inspect one retrieval index. |

### tarel index build

Embed safe graph metadata into a rebuildable local SQLite index.

**Syntax**

```text
tarel index build [-h] [--model MODEL_PATH] [--batch-size BATCH_SIZE] [--threads N_THREADS]
                         [--resume] [--format {text,json}]
                         name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Local graph name. |
| `--model` | Path | optional | not set | Local embedding model path. |
| `--batch-size` | int | optional | `16` | Documents per index progress batch; llama.cpp decodes each document separately. |
| `--threads` | int | optional | not set | Local model thread count. |
| `--resume` | flag | optional | `False` | Checkpoint completed embedding batches and resume a matching interrupted build. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Index build/status information, including checkpoint compatibility when applicable.

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

### tarel index status

Inspect one retrieval index.

**Syntax**

```text
tarel index status [-h] [--format {text,json}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Local graph name. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Index build/status information, including checkpoint compatibility when applicable.

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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
tarel graph header [-h] [--format {json,text}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--format` | text; `json`, `text` | optional | `json` | Output rendering format. |

**Result:** A graph summary for build/show, change information for refresh, annotation progress/summary, or selective header/page/slice records. Selective results carry complete-source identity and read accounting.

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

### tarel graph objects

Selective graph objects; graph.json stays authoritative.

**Syntax**

```text
tarel graph objects [-h] [--format {json,text}] [--object OBJECT_IDS] [--namespace NAMESPACE]
                           [--revision REVISION] [--offset OFFSET] [--limit LIMIT]
                           name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--format` | text; `json`, `text` | optional | `json` | Output rendering format. |
| `--object` | text | optional; repeatable | not set | Exact object IDs. |
| `--namespace` | text | optional | not set | Namespace/schema filter. |
| `--revision` | text | optional | not set | Revision pin for this operation. |
| `--offset` | int | optional | `0` | Pagination starting offset. |
| `--limit` | int | optional | `100` | Maximum number of items for this operation. |

**Result:** A graph summary for build/show, change information for refresh, annotation progress/summary, or selective header/page/slice records. Selective results carry complete-source identity and read accounting.

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

### tarel graph slice

Selective graph slice; graph.json stays authoritative.

Use exact object IDs from graph objects. The returned slice is a subset: preserve the complete source revision from its header rather than persisting the slice as the original graph.

**Syntax**

```text
tarel graph slice [-h] [--format {json,text}] --object OBJECT_IDS [--namespace NAMESPACE]
                         [--revision REVISION]
                         name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--format` | text; `json`, `text` | optional | `json` | Output rendering format. |
| `--object` | text | required; repeatable | not set | Exact object IDs. |
| `--namespace` | text | optional | not set | Namespace/schema filter. |
| `--revision` | text | optional | not set | Revision pin for this operation. |

**Result:** A graph summary for build/show, change information for refresh, annotation progress/summary, or selective header/page/slice records. Selective results carry complete-source identity and read accounting.

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

### tarel graph rebuild-index

Selective graph rebuild-index; graph.json stays authoritative.

**Syntax**

```text
tarel graph rebuild-index [-h] [--format {json,text}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--format` | text; `json`, `text` | optional | `json` | Output rendering format. |

**Result:** A graph summary for build/show, change information for refresh, annotation progress/summary, or selective header/page/slice records. Selective results carry complete-source identity and read accounting.

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

### tarel graph refresh

Rediscover technical structure while preserving reviewed knowledge.

**Syntax**

```text
tarel graph refresh [-h] [--config CONFIG] [--namespace NAMESPACE] [--format {text,json}]
                           name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Existing local graph name. |
| `--config` | Path | optional | not set | Private connector configuration. |
| `--namespace, --schema` | text | optional | not set | Namespace/schema filter. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** A graph summary for build/show, change information for refresh, annotation progress/summary, or selective header/page/slice records. Selective results carry complete-source identity and read accounting.

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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
| `--include-annotated` | flag | optional | `False` | Include targets that already have annotations. |
| `--dry-run` | flag | optional | `False` | Plan/preview instead of applying this operation. |
| `--knowledge` | text; `none`, `scoped` | optional | `none` | Include no automatic documents (default) or resolve matching scopes. |
| `--knowledge-document` | text | optional; repeatable | not set | Include one document explicitly; repeat for more. |
| `--knowledge-workspace` | text | optional | not set | Workspace used to resolve system-scoped documents. |
| `--max-knowledge-characters` | int | optional | `12000` | Knowledge-document character budget. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** A graph summary for build/show, change information for refresh, annotation progress/summary, or selective header/page/slice records. Selective results carry complete-source identity and read accounting.

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

## ui

**Browser.** Explore graph/workspace structure, lineage, and reviewable knowledge.

Starts a local browser server. --edit enables explicit mutations. Opening the UI does not itself run a connector or LLM. UI display filters are not automatically context-packet constraints.

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
tarel ui [-h] [--workspace WORKSPACE] [--system SYSTEMS] [--graph GRAPHS] [--area AREAS]
                [--schema SCHEMAS] [--zone ZONES] [--lineage LINEAGES] [--focus FOCUSES] [--edit]
                [--port PORT] [--no-open] [--families {confirmed_only,include_candidates}]
                [graph]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `graph` | text | optional; optional positional | not set | Single local graph to inspect. |
| `--workspace` | text | optional | not set | Open a workspace across one or more graphs. |
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

**Result:** Local server startup information; the process serves the browser until stopped.

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

## lineage

**Static and runtime lineage.** Describe data dependencies, analyze definitions, trace upstream origins, and record observed executions.

Build consumes canonical input rather than extracting a scheduler itself. Analyze invokes the provider and persists drafts. Next/apply supports harness-authored proposals. Runtime imports store caller observations separately from reusable static ETL definitions.

Contract and workflow: [runtime-lineage.md](contracts.md#runtime-lineage).

Example:

```bash
tarel lineage show sales-etl --view status --format json
```

 | Command | Purpose |
 | --- | --- |
 | [`tarel lineage build`](#tarel-lineage-build) | Create or refresh lineage from a canonical input file. |
 | [`tarel lineage show`](#tarel-lineage-show) | Show the document, process, table, or coverage projection. |
 | [`tarel lineage import-runtime`](#tarel-lineage-import-runtime) | Import one immutable, sanitized runtime query run. |
 | [`tarel lineage show-runtime`](#tarel-lineage-show-runtime) | Show one sanitized runtime-lineage run. |
 | [`tarel lineage list-runtime`](#tarel-lineage-list-runtime) | List sanitized runtime-lineage runs. |
 | [`tarel lineage trace-runtime`](#tarel-lineage-trace-runtime) | Trace a successful runtime call to its graph-bound source inputs. |
 | [`tarel lineage next`](#tarel-lineage-next) | Return the next source-analysis task for the current coding agent. |
 | [`tarel lineage apply`](#tarel-lineage-apply) | Apply one coding-agent workfile as draft lineage. |
 | [`tarel lineage analyze`](#tarel-lineage-analyze) | Send complete definitions to an optional provider and apply draft workfiles. |
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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/lineage/cli.py](../src/tarel/lineage/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/lineage/cli.py](../src/tarel/lineage/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/lineage/cli.py](../src/tarel/lineage/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/lineage/cli.py](../src/tarel/lineage/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/lineage/cli.py](../src/tarel/lineage/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/lineage/cli.py](../src/tarel/lineage/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/lineage/cli.py](../src/tarel/lineage/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/lineage/cli.py](../src/tarel/lineage/cli.py).

### tarel lineage analyze

Send complete definitions to an optional provider and apply draft workfiles.

Makes sequential per-definition extraction requests, followed by --review-passes audit requests. It is not a provider batch API. Compatible analysis-cache entries can be reused. Failed work is recorded; exhausted correction attempts stop the run. A provider audit leaves the result a draft.

**Syntax**

```text
tarel lineage analyze [-h] --source SOURCE --provider PROVIDER [--model MODEL]
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
| `--provider` | text | required | not set | Configured provider profile. |
| `--model` | text | optional | not set | Model override. |
| `--timeout` | float | optional | `180.0` | Timeout in seconds. |
| `--retry` | int | optional | `1` | Additional retry/correction attempts. |
| `--review-passes` | int | optional | `1` | Additional provider audit passes. |
| `--limit` | int | optional | not set | Maximum number of items for this operation. |
| `--definition` | text | optional; repeatable | not set | Analyze only this exact definition ID, external ID, name, or qualified name. |
| `--max-output-tokens` | int | optional | not set | Provider output-token bound. |
| `--reasoning-effort` | text; `none`, `minimal`, `low`, `medium`, `high`, `xhigh` | optional | not set | Provider reasoning-effort hint. |
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/lineage/cli.py](../src/tarel/lineage/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/lineage/cli.py](../src/tarel/lineage/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/lineage/cli.py](../src/tarel/lineage/cli.py).

### tarel lineage upstream

Trace one reference backwards through all selected lineage documents.

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/lineage/cli.py](../src/tarel/lineage/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/lineage/cli.py](../src/tarel/lineage/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** The selected lineage document/projection, provider-run result, task/proposal result, review list/decision, or upstream trace. The exact envelope depends on the verb and --view. next returns a task or a completed/no-task outcome.

CLI entry point and delegated output renderers: [src/tarel/lineage/cli.py](../src/tarel/lineage/cli.py).

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
                             [--format {ossie,apache-ossie,sml,cube,cube-yaml}] [--replace]
                             [--output {text,json}]
                             name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--graph` | text | required | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `--source` | Path | required | not set | Input source: file, logical source, or reference as specified by this command. See its linked contract. |
| `--format` | text; `ossie`, `apache-ossie`, `sml`, `cube`, `cube-yaml` | optional | `ossie` | Semantic input format. |
| `--replace` | flag | optional | `False` | Replace an existing named definition/document where supported. |
| `--output` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Imported semantic document, listing, or edit result. Bindings and diagnostics preserve source identity.

CLI entry point and delegated output renderers: [src/tarel/semantics/cli.py](../src/tarel/semantics/cli.py).

### tarel semantic list

List saved semantic imports.

**Syntax**

```text
tarel semantic list [-h] [--graph GRAPH] [--output {text,json}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--graph` | text | optional | not set | Graph name; for commands supporting --workspace, that flag changes the positional scope to a workspace. |
| `--output` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Imported semantic document, listing, or edit result. Bindings and diagnostics preserve source identity.

CLI entry point and delegated output renderers: [src/tarel/semantics/cli.py](../src/tarel/semantics/cli.py).

### tarel semantic show

Show one normalized semantic import.

**Syntax**

```text
tarel semantic show [-h] [--include-source] [--output {text,json}] name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--include-source` | flag | optional | `False` | Include supported source details in output. |
| `--output` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Imported semantic document, listing, or edit result. Bindings and diagnostics preserve source identity.

CLI entry point and delegated output renderers: [src/tarel/semantics/cli.py](../src/tarel/semantics/cli.py).

### tarel semantic edit

Overlay description or synonym corrections without changing the source snapshot.

**Syntax**

```text
tarel semantic edit [-h] --input INPUT --reason REASON [--revision REVISION]
                           [--output {text,json}]
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
| `--output` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Imported semantic document, listing, or edit result. Bindings and diagnostics preserve source identity.

CLI entry point and delegated output renderers: [src/tarel/semantics/cli.py](../src/tarel/semantics/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Sanitized entity candidate records, resolution results, or a review result. Candidate state and effective usage remain visible.

CLI entry point and delegated output renderers: [src/tarel/entity_resolution/cli.py](../src/tarel/entity_resolution/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Sanitized entity candidate records, resolution results, or a review result. Candidate state and effective usage remain visible.

CLI entry point and delegated output renderers: [src/tarel/entity_resolution/cli.py](../src/tarel/entity_resolution/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Sanitized entity candidate records, resolution results, or a review result. Candidate state and effective usage remain visible.

CLI entry point and delegated output renderers: [src/tarel/entity_resolution/cli.py](../src/tarel/entity_resolution/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Sanitized entity candidate records, resolution results, or a review result. Candidate state and effective usage remain visible.

CLI entry point and delegated output renderers: [src/tarel/entity_resolution/cli.py](../src/tarel/entity_resolution/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Sanitized entity candidate records, resolution results, or a review result. Candidate state and effective usage remain visible.

CLI entry point and delegated output renderers: [src/tarel/entity_resolution/cli.py](../src/tarel/entity_resolution/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Sanitized entity candidate records, resolution results, or a review result. Candidate state and effective usage remain visible.

CLI entry point and delegated output renderers: [src/tarel/entity_resolution/cli.py](../src/tarel/entity_resolution/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Revisioned run/task/action results, advice, promotion results, or coverage. next includes allowed actions; submit consumes the current revision. Read status before choosing the next action.

CLI entry point and delegated output renderers: [src/tarel/discovery/cli.py](../src/tarel/discovery/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Revisioned run/task/action results, advice, promotion results, or coverage. next includes allowed actions; submit consumes the current revision. Read status before choosing the next action.

CLI entry point and delegated output renderers: [src/tarel/discovery/cli.py](../src/tarel/discovery/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Revisioned run/task/action results, advice, promotion results, or coverage. next includes allowed actions; submit consumes the current revision. Read status before choosing the next action.

CLI entry point and delegated output renderers: [src/tarel/discovery/cli.py](../src/tarel/discovery/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Revisioned run/task/action results, advice, promotion results, or coverage. next includes allowed actions; submit consumes the current revision. Read status before choosing the next action.

CLI entry point and delegated output renderers: [src/tarel/discovery/cli.py](../src/tarel/discovery/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Revisioned run/task/action results, advice, promotion results, or coverage. next includes allowed actions; submit consumes the current revision. Read status before choosing the next action.

CLI entry point and delegated output renderers: [src/tarel/discovery/cli.py](../src/tarel/discovery/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Revisioned run/task/action results, advice, promotion results, or coverage. next includes allowed actions; submit consumes the current revision. Read status before choosing the next action.

CLI entry point and delegated output renderers: [src/tarel/discovery/cli.py](../src/tarel/discovery/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Revisioned run/task/action results, advice, promotion results, or coverage. next includes allowed actions; submit consumes the current revision. Read status before choosing the next action.

CLI entry point and delegated output renderers: [src/tarel/discovery/cli.py](../src/tarel/discovery/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Revisioned run/task/action results, advice, promotion results, or coverage. next includes allowed actions; submit consumes the current revision. Read status before choosing the next action.

CLI entry point and delegated output renderers: [src/tarel/discovery/cli.py](../src/tarel/discovery/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Revisioned run/task/action results, advice, promotion results, or coverage. next includes allowed actions; submit consumes the current revision. Read status before choosing the next action.

CLI entry point and delegated output renderers: [src/tarel/discovery/cli.py](../src/tarel/discovery/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Target agent, changed resource paths, and target directory.

CLI entry point and delegated output renderers: [src/tarel/discovery/cli.py](../src/tarel/discovery/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Logical topology document and review state. Import takes typed input.

CLI entry point and delegated output renderers: [src/tarel/topology/cli.py](../src/tarel/topology/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Logical topology document and review state. Import takes typed input.

CLI entry point and delegated output renderers: [src/tarel/topology/cli.py](../src/tarel/topology/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Logical topology document and review state. Import takes typed input.

CLI entry point and delegated output renderers: [src/tarel/topology/cli.py](../src/tarel/topology/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Plan/run result, family document/list, or revision-bound member page. export serializes the family document. Membership remains physical and schema compatibility is not a union guarantee.

CLI entry point and delegated output renderers: [src/tarel/object_families/cli.py](../src/tarel/object_families/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Plan/run result, family document/list, or revision-bound member page. export serializes the family document. Membership remains physical and schema compatibility is not a union guarantee.

CLI entry point and delegated output renderers: [src/tarel/object_families/cli.py](../src/tarel/object_families/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Plan/run result, family document/list, or revision-bound member page. export serializes the family document. Membership remains physical and schema compatibility is not a union guarantee.

CLI entry point and delegated output renderers: [src/tarel/object_families/cli.py](../src/tarel/object_families/cli.py).

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
| `--name` | text | required | not set | Name of the resource operated on by this command; see the command purpose. |
| `--member` | text | required; repeatable | not set | Family member references. |
| `--grain` | text | required; repeatable | not set | Declared record grain. |
| `--attribute` | text | optional; repeatable | `[]` | JSON metadata attribute. |
| `--producer` | text | optional | `coding_agent` | Producer identity. |
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Plan/run result, family document/list, or revision-bound member page. export serializes the family document. Membership remains physical and schema compatibility is not a union guarantee.

CLI entry point and delegated output renderers: [src/tarel/object_families/cli.py](../src/tarel/object_families/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Plan/run result, family document/list, or revision-bound member page. export serializes the family document. Membership remains physical and schema compatibility is not a union guarantee.

CLI entry point and delegated output renderers: [src/tarel/object_families/cli.py](../src/tarel/object_families/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Plan/run result, family document/list, or revision-bound member page. export serializes the family document. Membership remains physical and schema compatibility is not a union guarantee.

CLI entry point and delegated output renderers: [src/tarel/object_families/cli.py](../src/tarel/object_families/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Plan/run result, family document/list, or revision-bound member page. export serializes the family document. Membership remains physical and schema compatibility is not a union guarantee.

CLI entry point and delegated output renderers: [src/tarel/object_families/cli.py](../src/tarel/object_families/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Plan/run result, family document/list, or revision-bound member page. export serializes the family document. Membership remains physical and schema compatibility is not a union guarantee.

CLI entry point and delegated output renderers: [src/tarel/object_families/cli.py](../src/tarel/object_families/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Plan/run result, family document/list, or revision-bound member page. export serializes the family document. Membership remains physical and schema compatibility is not a union guarantee.

CLI entry point and delegated output renderers: [src/tarel/object_families/cli.py](../src/tarel/object_families/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Plan/run result, family document/list, or revision-bound member page. export serializes the family document. Membership remains physical and schema compatibility is not a union guarantee.

CLI entry point and delegated output renderers: [src/tarel/object_families/cli.py](../src/tarel/object_families/cli.py).

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
| `--format` | text; `text`, `json` | optional | `json` | Output rendering format. |

**Result:** Binding metadata, review result, or resolved member/object references. Protected selections are not echoed as an ordinary catalog.

CLI entry point and delegated output renderers: [src/tarel/object_bindings/cli.py](../src/tarel/object_bindings/cli.py).

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
| `--format` | text; `text`, `json` | optional | `json` | Output rendering format. |

**Result:** Binding metadata, review result, or resolved member/object references. Protected selections are not echoed as an ordinary catalog.

CLI entry point and delegated output renderers: [src/tarel/object_bindings/cli.py](../src/tarel/object_bindings/cli.py).

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
| `--format` | text; `text`, `json` | optional | `json` | Output rendering format. |

**Result:** Binding metadata, review result, or resolved member/object references. Protected selections are not echoed as an ordinary catalog.

CLI entry point and delegated output renderers: [src/tarel/object_bindings/cli.py](../src/tarel/object_bindings/cli.py).

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
| `--format` | text; `text`, `json` | optional | `json` | Output rendering format. |

**Result:** Binding metadata, review result, or resolved member/object references. Protected selections are not echoed as an ordinary catalog.

CLI entry point and delegated output renderers: [src/tarel/object_bindings/cli.py](../src/tarel/object_bindings/cli.py).

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
| `--format` | text; `text`, `json` | optional | `json` | Output rendering format. |

**Result:** Binding metadata, review result, or resolved member/object references. Protected selections are not echoed as an ordinary catalog.

CLI entry point and delegated output renderers: [src/tarel/object_bindings/cli.py](../src/tarel/object_bindings/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Concept document, matching representations, or review result with current usage.

CLI entry point and delegated output renderers: [src/tarel/semantic_concepts/cli.py](../src/tarel/semantic_concepts/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Concept document, matching representations, or review result with current usage.

CLI entry point and delegated output renderers: [src/tarel/semantic_concepts/cli.py](../src/tarel/semantic_concepts/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Concept document, matching representations, or review result with current usage.

CLI entry point and delegated output renderers: [src/tarel/semantic_concepts/cli.py](../src/tarel/semantic_concepts/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Concept document, matching representations, or review result with current usage.

CLI entry point and delegated output renderers: [src/tarel/semantic_concepts/cli.py](../src/tarel/semantic_concepts/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Logical join records and effective review/usage state.

CLI entry point and delegated output renderers: [src/tarel/logical_joins/cli.py](../src/tarel/logical_joins/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Logical join records and effective review/usage state.

CLI entry point and delegated output renderers: [src/tarel/logical_joins/cli.py](../src/tarel/logical_joins/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Logical join records and effective review/usage state.

CLI entry point and delegated output renderers: [src/tarel/logical_joins/cli.py](../src/tarel/logical_joins/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Logical join records and effective review/usage state.

CLI entry point and delegated output renderers: [src/tarel/logical_joins/cli.py](../src/tarel/logical_joins/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Value-free mapping candidates, selected matches, or review result. Mapping rows are caller-owned.

CLI entry point and delegated output renderers: [src/tarel/reference_mapping/cli.py](../src/tarel/reference_mapping/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Value-free mapping candidates, selected matches, or review result. Mapping rows are caller-owned.

CLI entry point and delegated output renderers: [src/tarel/reference_mapping/cli.py](../src/tarel/reference_mapping/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Value-free mapping candidates, selected matches, or review result. Mapping rows are caller-owned.

CLI entry point and delegated output renderers: [src/tarel/reference_mapping/cli.py](../src/tarel/reference_mapping/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Value-free mapping candidates, selected matches, or review result. Mapping rows are caller-owned.

CLI entry point and delegated output renderers: [src/tarel/reference_mapping/cli.py](../src/tarel/reference_mapping/cli.py).

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
| `--format` | text; `text`, `json` | optional | `text` | Output rendering format. |

**Result:** Value-free mapping candidates, selected matches, or review result. Mapping rows are caller-owned.

CLI entry point and delegated output renderers: [src/tarel/reference_mapping/cli.py](../src/tarel/reference_mapping/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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
                    [--workspace] [--system SYSTEMS] [--graph GRAPHS] [--area AREAS]
                    [--scope-schema SCHEMAS] [--zone ZONES]
                    [--annotation-state {draft,validated,rejected,deferred,review_required}]
                    [--validated-only] [--format {text,json}]
                    name query
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Graph name, or workspace name with --workspace. |
| `query` | text | required | not set | Words describing the required analytical objects. |
| `--namespace, --schema` | text | optional | not set | Namespace/schema filter. |
| `--limit` | int | optional | `20` | Maximum number of items for this operation. |
| `--families` | text; `off`, `confirmed_only`, `include_candidates` | optional | `confirmed_only` | Include logical family-name hits; never expand members. |
| `--mode` | text; `lexical`, `bm25`, `vector`, `hybrid` | optional | `lexical` | Mode for this command; allowed values are listed separately. |
| `--model` | Path | optional | not set | Local embedding model path. |
| `--threads` | int | optional | not set | Local model thread count. |
| `--workspace` | flag | optional | `False` | Treat NAME as a workspace and search only its resolved scope. |
| `--system` | text | optional; repeatable | not set | System scope selection. |
| `--graph` | text | optional; repeatable | not set | Graph names to include. |
| `--area` | text | optional; repeatable | not set | Area scope selection. |
| `--scope-schema` | text | optional; repeatable | not set | Workspace schema as GRAPH:NAMESPACE; repeat for a union. |
| `--zone` | text | optional; repeatable | not set | Zone scope selection. |
| `--annotation-state` | text; `draft`, `validated`, `rejected`, `deferred`, `review_required` | optional; repeatable | not set | Include semantic annotations in one or more review states. |
| `--validated-only` | flag | optional | `False` | Include only human-validated semantic annotations. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Ranked metadata matches and selection information, not data rows.

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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
 | [`tarel context diff`](#tarel-context-diff) | Validate and compare two serialized context packets. |
 | [`tarel context impact`](#tarel-context-impact) | Check whether one saved context packet is affected by the latest graph refresh. |

### tarel context expand

Expand pinned metadata using an existing context scope.

--requests must describe typed targets. Do not combine --requests - with --inputs-stdin: both would require stdin. Expansion returns exit code 1 when omissions are reported; inspect them rather than treating partial output as complete.

**Syntax**

```text
tarel context expand [-h] --packet PACKET --requests REQUESTS [--inputs-stdin]
                            [--mode {confirmed_only,include_candidates}]
                            [--max-characters MAX_CHARACTERS] [--format {json,text}]
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `--packet` | Path | required | not set | Existing context packet path. |
| `--requests` | text | required | not set | Typed target JSON array, file or '-' for stdin. |
| `--inputs-stdin` | flag | optional | `False` | Private handle values, never saved. |
| `--mode` | text; `confirmed_only`, `include_candidates` | optional | `confirmed_only` | Mode for this command; allowed values are listed separately. |
| `--max-characters` | int | optional | `24000` | Character budget; not a tokenizer-based token limit. |
| `--format` | text; `json`, `text` | optional | `json` | Output rendering format. |

**Result:** Context packet, metadata expansion, packet diff, or impact result. Inspect identities, budgets, and omissions; expand can return partial output with status 1.

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

### tarel context build

Compile bounded context from search and reviewed graph relationships.

The shorthand tarel context NAME QUERY is rewritten to this command. --validated-only filters semantic claims, not the entire physical inventory. An unchanged question is not sufficient for reuse after a graph or review revision changes.

**Syntax**

```text
tarel context build [-h] [--namespace NAMESPACE] [--seed-limit SEED_LIMIT]
                           [--max-objects MAX_OBJECTS] [--max-joins MAX_JOINS] [--max-hops MAX_HOPS]
                           [--max-fields-per-object MAX_FIELDS_PER_OBJECT]
                           [--max-characters MAX_CHARACTERS] [--mode {lexical,bm25,vector,hybrid}]
                           [--model MODEL_PATH] [--threads N_THREADS] [--workspace]
                           [--system SYSTEMS] [--graph GRAPHS] [--area AREAS]
                           [--scope-schema SCHEMAS] [--zone ZONES]
                           [--annotation-state {draft,validated,rejected,deferred,review_required}]
                           [--validated-only]
                           [--logical-hints {confirmed_only,confirmed_then_candidates,include_candidates}]
                           [--format {text,json}]
                           name query
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Graph name, or workspace name with --workspace. |
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
| `--workspace` | flag | optional | `False` | Treat NAME as a workspace and search only its resolved scope. |
| `--system` | text | optional; repeatable | not set | System scope selection. |
| `--graph` | text | optional; repeatable | not set | Graph names to include. |
| `--area` | text | optional; repeatable | not set | Area scope selection. |
| `--scope-schema` | text | optional; repeatable | not set | Workspace schema as GRAPH:NAMESPACE; repeat for a union. |
| `--zone` | text | optional; repeatable | not set | Zone scope selection. |
| `--annotation-state` | text; `draft`, `validated`, `rejected`, `deferred`, `review_required` | optional; repeatable | not set | Include semantic annotations in one or more review states. |
| `--validated-only` | flag | optional | `False` | Include only human-validated semantic annotations. |
| `--logical-hints` | text; `confirmed_only`, `confirmed_then_candidates`, `include_candidates` | optional | not set | Include bounded logical hints for selected objects; disabled by default. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Context packet, metadata expansion, packet diff, or impact result. Inspect identities, budgets, and omissions; expand can return partial output with status 1.

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

### tarel context prefix

Compile a query-independent graph or workspace scope for prompt caching.

Question-independent packet for an explicit graph/workspace scope. Keep its serialization unchanged for possible prompt-prefix reuse. Budgets can omit fields/objects even when a complete database was selected. TAREL does not guarantee a provider cache hit.

**Syntax**

```text
tarel context prefix [-h] [--namespace NAMESPACE] [--max-objects MAX_OBJECTS]
                            [--max-joins MAX_JOINS] [--max-fields-per-object MAX_FIELDS_PER_OBJECT]
                            [--max-characters MAX_CHARACTERS] [--workspace] [--system SYSTEMS]
                            [--graph GRAPHS] [--area AREAS] [--scope-schema SCHEMAS] [--zone ZONES]
                            [--annotation-state {draft,validated,rejected,deferred,review_required}]
                            [--validated-only]
                            [--logical-hints {confirmed_only,confirmed_then_candidates,include_candidates}]
                            [--format {text,json}]
                            name
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Graph name, or workspace name with --workspace. |
| `--namespace, --schema` | text | optional | not set | Namespace/schema filter. |
| `--max-objects` | int | optional | `250` | Maximum selected objects. |
| `--max-joins` | int | optional | `500` | Maximum selected joins. |
| `--max-fields-per-object` | int | optional | `50` | Maximum fields per object. |
| `--max-characters` | int | optional | `500000` | Character budget; not a tokenizer-based token limit. |
| `--workspace` | flag | optional | `False` | Treat NAME as a workspace and search only its resolved scope. |
| `--system` | text | optional; repeatable | not set | System scope selection. |
| `--graph` | text | optional; repeatable | not set | Graph names to include. |
| `--area` | text | optional; repeatable | not set | Area scope selection. |
| `--scope-schema` | text | optional; repeatable | not set | Workspace schema as GRAPH:NAMESPACE; repeat for a union. |
| `--zone` | text | optional; repeatable | not set | Zone scope selection. |
| `--annotation-state` | text; `draft`, `validated`, `rejected`, `deferred`, `review_required` | optional; repeatable | not set | Include semantic annotations in one or more review states. |
| `--validated-only` | flag | optional | `False` | Include only human-validated semantic annotations. |
| `--logical-hints` | text; `confirmed_only`, `confirmed_then_candidates`, `include_candidates` | optional | not set | Include bounded logical hints for selected objects; disabled by default. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Context packet, metadata expansion, packet diff, or impact result. Inspect identities, budgets, and omissions; expand can return partial output with status 1.

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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
                       [--model MODEL_PATH] [--threads N_THREADS] [--workspace] [--system SYSTEMS]
                       [--graph GRAPHS] [--area AREAS] [--scope-schema SCHEMAS] [--zone ZONES]
                       [--annotation-state {draft,validated,rejected,deferred,review_required}]
                       [--validated-only]
                       [--logical-hints {confirmed_only,confirmed_then_candidates,include_candidates}]
                       [--format {text,json}]
                       name query
```

**Arguments and options**

| Parameter | Type / accepted values | Required / repetition | Default | Meaning |
| --- | --- | --- | --- | --- |
| `-h, --help` | flag | optional | — | show this help message and exit |
| `name` | text | required | not set | Graph name, or workspace name with --workspace. |
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
| `--workspace` | flag | optional | `False` | Treat NAME as a workspace and search only its resolved scope. |
| `--system` | text | optional; repeatable | not set | System scope selection. |
| `--graph` | text | optional; repeatable | not set | Graph names to include. |
| `--area` | text | optional; repeatable | not set | Area scope selection. |
| `--scope-schema` | text | optional; repeatable | not set | Workspace schema as GRAPH:NAMESPACE; repeat for a union. |
| `--zone` | text | optional; repeatable | not set | Zone scope selection. |
| `--annotation-state` | text; `draft`, `validated`, `rejected`, `deferred`, `review_required` | optional; repeatable | not set | Include semantic annotations in one or more review states. |
| `--validated-only` | flag | optional | `False` | Include only human-validated semantic annotations. |
| `--logical-hints` | text; `confirmed_only`, `confirmed_then_candidates`, `include_candidates` | optional | not set | Include bounded logical hints for selected objects; disabled by default. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Grounding bundle with stable and dynamic sections, source routing metadata, context, selected lineage, and hashes.

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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
 | [`tarel annotation next`](#tarel-annotation-next) | Return the next full annotation task as JSON for the coding agent. |
 | [`tarel annotation apply`](#tarel-annotation-apply) | Validate and apply one coding-agent proposal as a draft. |
 | [`tarel annotation list`](#tarel-annotation-list) | List object and field annotation proposals for review. |
 | [`tarel annotation show`](#tarel-annotation-show) | Show one object or field annotation and its review history. |
 | [`tarel annotation edit`](#tarel-annotation-edit) | Apply a bounded JSON patch to one annotation proposal. |
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
| `--include-annotated` | flag | optional | `False` | Include targets that already have annotations. |
| `--knowledge` | text; `none`, `scoped` | optional | `none` | Include no automatic documents (default) or resolve matching scopes. |
| `--knowledge-document` | text | optional; repeatable | not set | Include one document explicitly; repeat for more. |
| `--knowledge-workspace` | text | optional | not set | Workspace used to resolve system-scoped documents. |
| `--max-knowledge-characters` | int | optional | `12000` | Knowledge-document character budget. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Task plan, next task, proposal application, review listing, or annotation record/change. An empty plan is successful and does not mean every field was human-approved.

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

### tarel annotation next

Return the next full annotation task as JSON for the coding agent.

Supply exactly one graph NAME or --focus FOCUS. The returned workfile is intended for the harness model. Use graph annotate for direct provider execution.

**Syntax**

```text
tarel annotation next [-h] [--focus FOCUS] [--namespace NAMESPACE] [--object OBJECTS]
                             [--include-annotated] [--samples SAMPLES] [--profile-rows PROFILE_ROWS]
                             [--include-small-domain-values] [--config CONFIG]
                             [--knowledge {none,scoped}] [--knowledge-document KNOWLEDGE_DOCUMENTS]
                             [--knowledge-workspace KNOWLEDGE_WORKSPACE]
                             [--max-knowledge-characters MAX_KNOWLEDGE_CHARACTERS]
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
| `--include-annotated` | flag | optional | `False` | Include targets that already have annotations. |
| `--samples` | int | optional | `0` | Maximum requested sample rows; zero disables samples where supported. |
| `--profile-rows` | int | optional | `0` | Row budget for optional profiling. |
| `--include-small-domain-values` | flag | optional | `False` | Explicitly allow small-domain values in ephemeral annotation input. |
| `--config` | Path | optional | not set | Private connector configuration. |
| `--knowledge` | text; `none`, `scoped` | optional | `none` | Include no automatic documents (default) or resolve matching scopes. |
| `--knowledge-document` | text | optional; repeatable | not set | Include one document explicitly; repeat for more. |
| `--knowledge-workspace` | text | optional | not set | Workspace used to resolve system-scoped documents. |
| `--max-knowledge-characters` | int | optional | `12000` | Knowledge-document character budget. |

**Result:** Task plan, next task, proposal application, review listing, or annotation record/change. An empty plan is successful and does not mean every field was human-approved.

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

### tarel annotation edit

Apply a bounded JSON patch to one annotation proposal.

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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
| `--include-fields` | flag | optional | `False` | Apply the decision to the selected table or view and all of its fields. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Task plan, next task, proposal application, review listing, or annotation record/change. An empty plan is successful and does not mean every field was human-approved.

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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
| `--include-fields` | flag | optional | `False` | Apply the decision to the selected table or view and all of its fields. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Task plan, next task, proposal application, review listing, or annotation record/change. An empty plan is successful and does not mean every field was human-approved.

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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
| `--include-fields` | flag | optional | `False` | Apply the decision to the selected table or view and all of its fields. |
| `--format` | text; `text`, `json` | optional | `text` | Output format (default: text). |

**Result:** Task plan, next task, proposal application, review listing, or annotation record/change. An empty plan is successful and does not mean every field was human-approved.

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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

CLI entry point and delegated output renderers: [src/tarel/cli.py](../src/tarel/cli.py).

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
| Context packet | [Packet contract](contracts.md#context-packets), [serializer](../src/tarel/context_output.py) |
| Grounding bundle | [GroundingBundle](../src/tarel/grounding.py) |
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
| `agent_setup_failed` | [tarel/agents.py](../src/tarel/agents.py#L59) |
| `agent_skill_exists` | [tarel/agents.py](../src/tarel/agents.py#L38) |
| `agent_skill_missing` | [tarel/agents.py](../src/tarel/agents.py#L48) |
| `ambiguous_lineage_reference` | [lineage/traversal.py](../src/tarel/lineage/traversal.py#L661), [lineage/traversal.py](../src/tarel/lineage/traversal.py#L697) |
| `ambiguous_logical_joins` | [logical_joins/application.py](../src/tarel/logical_joins/application.py#L239) |
| `ambiguous_scope_selector` | [workspaces/scope.py](../src/tarel/workspaces/scope.py#L219) |
| `ambiguous_source_mapping` | [tarel/grounding_application.py](../src/tarel/grounding_application.py#L372) |
| `annotation_not_found` | [annotations/review.py](../src/tarel/annotations/review.py#L320) |
| `annotation_sample_field_mismatch` | [annotations/tasks.py](../src/tarel/annotations/tasks.py#L173), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L178), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L194) |
| `annotation_sample_target_mismatch` | [annotations/tasks.py](../src/tarel/annotations/tasks.py#L149) |
| `batch_failed` | [annotations/runner.py](../src/tarel/annotations/runner.py#L95) |
| `catalog_not_found` | [connectors/catalog.py](../src/tarel/connectors/catalog.py#L51) |
| `change_report_conflict` | [graph/change_store.py](../src/tarel/graph/change_store.py#L27) |
| `change_report_not_found` | [graph/change_store.py](../src/tarel/graph/change_store.py#L64) |
| `change_report_save_failed` | [graph/change_store.py](../src/tarel/graph/change_store.py#L48) |
| `config_not_found` | [tarel/application.py](../src/tarel/application.py#L2073) |
| `conflicting_annotation_filter` | [annotations/states.py](../src/tarel/annotations/states.py#L19) |
| `conflicting_annotation_samples` | [tarel/application.py](../src/tarel/application.py#L1871) |
| `conflicting_workspace_scope` | [sdk/client.py](../src/tarel/sdk/client.py#L2616) |
| `connection_failed` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L48), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L249) |
| `context_character_budget_too_small` | [tarel/context.py](../src/tarel/context.py#L409) |
| `context_graph_mismatch` | [tarel/context_packets.py](../src/tarel/context_packets.py#L209) |
| `context_packet_hash_mismatch` | [tarel/context_packets.py](../src/tarel/context_packets.py#L156) |
| `context_packet_not_found` | [tarel/context_packets.py](../src/tarel/context_packets.py#L116) |
| `database_not_found` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L251) |
| `demo_create_failed` | [tarel/demo.py](../src/tarel/demo.py#L74) |
| `demo_exists` | [tarel/demo.py](../src/tarel/demo.py#L52) |
| `derived_relation_already_reviewed` | [topology/contracts.py](../src/tarel/topology/contracts.py#L639) |
| `derived_relation_not_found` | [topology/application.py](../src/tarel/topology/application.py#L126) |
| `discovery_action_not_allowed` | [discovery/application.py](../src/tarel/discovery/application.py#L683), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1430), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1439), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1488), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1496), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1599), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1604), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1628), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1683), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1691), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1704) |
| `discovery_aggregates_not_allowed` | [discovery/application.py](../src/tarel/discovery/application.py#L889) |
| `discovery_candidate_exists` | [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1557) |
| `discovery_candidate_not_found` | [discovery/application.py](../src/tarel/discovery/application.py#L455), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1807) |
| `discovery_exists` | [discovery/application.py](../src/tarel/discovery/application.py#L248) |
| `discovery_failed` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L82), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L321) |
| `discovery_field_not_found` | [discovery/application.py](../src/tarel/discovery/application.py#L813), [discovery/application.py](../src/tarel/discovery/application.py#L830), [discovery/application.py](../src/tarel/discovery/application.py#L939) |
| `discovery_graph_revision_mismatch` | [discovery/application.py](../src/tarel/discovery/application.py#L845), [discovery/application.py](../src/tarel/discovery/application.py#L932), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L59) |
| `discovery_not_found` | [discovery/store.py](../src/tarel/discovery/store.py#L70) |
| `discovery_observation_exists` | [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1660) |
| `discovery_promotion_failed` | [discovery/application.py](../src/tarel/discovery/application.py#L524), [discovery/application.py](../src/tarel/discovery/application.py#L590), [entity_resolution/discovery.py](../src/tarel/entity_resolution/discovery.py#L263), [entity_resolution/discovery.py](../src/tarel/entity_resolution/discovery.py#L273), [entity_resolution/discovery.py](../src/tarel/entity_resolution/discovery.py#L289), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L92) |
| `discovery_provider_not_enabled` | [discovery/application.py](../src/tarel/discovery/application.py#L672) |
| `discovery_save_failed` | [discovery/store.py](../src/tarel/discovery/store.py#L61), [discovery/store.py](../src/tarel/discovery/store.py#L125) |
| `discovery_source_graph_mismatch` | [discovery/application.py](../src/tarel/discovery/application.py#L876), [discovery/application.py](../src/tarel/discovery/application.py#L927) |
| `discovery_source_not_found` | [discovery/cli.py](../src/tarel/discovery/cli.py#L313) |
| `duplicate_focus` | [ui/server.py](../src/tarel/ui/server.py#L670) |
| `duplicate_focus_source` | [tarel/application.py](../src/tarel/application.py#L2169) |
| `duplicate_lineage_definition` | [lineage/application.py](../src/tarel/lineage/application.py#L652) |
| `duplicate_lineage_name` | [tarel/grounding_application.py](../src/tarel/grounding_application.py#L344) |
| `duplicate_source_name` | [tarel/grounding_application.py](../src/tarel/grounding_application.py#L353) |
| `embedding_failed` | [retrieval/index.py](../src/tarel/retrieval/index.py#L602), [retrieval/index.py](../src/tarel/retrieval/index.py#L655), [retrieval/index.py](../src/tarel/retrieval/index.py#L658), [retrieval/index.py](../src/tarel/retrieval/index.py#L660), [retrieval/local.py](../src/tarel/retrieval/local.py#L232), [retrieval/local.py](../src/tarel/retrieval/local.py#L250), [retrieval/local.py](../src/tarel/retrieval/local.py#L254), [retrieval/local.py](../src/tarel/retrieval/local.py#L256), [retrieval/local.py](../src/tarel/retrieval/local.py#L259) |
| `empty_context_scope` | [tarel/context.py](../src/tarel/context.py#L249) |
| `empty_query` | [tarel/search.py](../src/tarel/search.py#L152) |
| `empty_zone` | [ui/server.py](../src/tarel/ui/server.py#L806) |
| `enrichment_not_allowed` | [sources/application.py](../src/tarel/sources/application.py#L367) |
| `entity_alias_group_exists` | [discovery/identity.py](../src/tarel/discovery/identity.py#L467) |
| `entity_alias_group_required` | [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1640), [discovery/identity.py](../src/tarel/discovery/identity.py#L494) |
| `entity_aliases_not_allowed` | [discovery/application.py](../src/tarel/discovery/application.py#L900), [discovery/application.py](../src/tarel/discovery/application.py#L911), [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L429), [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L440) |
| `entity_resolution_already_reviewed` | [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L812) |
| `entity_resolution_exists` | [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L60) |
| `entity_resolution_field_not_found` | [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L449), [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L460), [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L473), [entity_resolution/projection.py](../src/tarel/entity_resolution/projection.py#L20) |
| `entity_resolution_graph_revision_mismatch` | [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L276) |
| `entity_resolution_not_found` | [entity_resolution/store.py](../src/tarel/entity_resolution/store.py#L70) |
| `entity_resolution_object_not_found` | [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L190), [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L291) |
| `entity_resolution_save_failed` | [entity_resolution/store.py](../src/tarel/entity_resolution/store.py#L60) |
| `entity_resolution_source_not_found` | [entity_resolution/cli.py](../src/tarel/entity_resolution/cli.py#L191) |
| `entity_resolution_supersede_required` | [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L386) |
| `entity_resolution_superseded` | [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L251) |
| `expansion_budget_too_small` | [expansion/application.py](../src/tarel/expansion/application.py#L133) |
| `expansion_outside_scope` | [expansion/projections.py](../src/tarel/expansion/projections.py#L161), [expansion/projections.py](../src/tarel/expansion/projections.py#L246), [expansion/projections.py](../src/tarel/expansion/projections.py#L266) |
| `expansion_policy_excluded` | [expansion/projections.py](../src/tarel/expansion/projections.py#L201), [expansion/projections.py](../src/tarel/expansion/projections.py#L221), [expansion/projections.py](../src/tarel/expansion/projections.py#L312) |
| `expansion_target_not_found` | [expansion/projections.py](../src/tarel/expansion/projections.py#L93) |
| `expected_logical_topology_revision_required` | [topology/application.py](../src/tarel/topology/application.py#L59), [topology/application.py](../src/tarel/topology/application.py#L99) |
| `expected_reference_mapping_revision_required` | [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L267) |
| `family_proposals_exist` | [object_families/proposals.py](../src/tarel/object_families/proposals.py#L78), [object_families/proposals.py](../src/tarel/object_families/proposals.py#L150) |
| `family_proposals_lock_failed` | [object_families/proposals.py](../src/tarel/object_families/proposals.py#L493) |
| `family_proposals_locked` | [object_families/proposals.py](../src/tarel/object_families/proposals.py#L487) |
| `family_proposals_not_found` | [object_families/proposals.py](../src/tarel/object_families/proposals.py#L168) |
| `family_proposals_save_failed` | [object_families/proposals.py](../src/tarel/object_families/proposals.py#L466) |
| `family_proposals_started` | [object_families/proposals.py](../src/tarel/object_families/proposals.py#L217) |
| `field_not_found` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L345), [relationships/core.py](../src/tarel/relationships/core.py#L220) |
| `focus_not_found` | [focus/store.py](../src/tarel/focus/store.py#L49) |
| `focus_outside_scope` | [ui/server.py](../src/tarel/ui/server.py#L674) |
| `focus_save_failed` | [focus/store.py](../src/tarel/focus/store.py#L39) |
| `focus_stale` | [tarel/application.py](../src/tarel/application.py#L2153), [focus/core.py](../src/tarel/focus/core.py#L118), [ui/server.py](../src/tarel/ui/server.py#L682) |
| `graph_cache_build_failed` | [graph/selective.py](../src/tarel/graph/selective.py#L419) |
| `graph_cache_changed_during_read` | [graph/selective.py](../src/tarel/graph/selective.py#L323) |
| `graph_changed_during_read` | [graph/selective.py](../src/tarel/graph/selective.py#L316), [graph/selective.py](../src/tarel/graph/selective.py#L339), [graph/selective.py](../src/tarel/graph/selective.py#L406), [ui/lazy_family_view.py](../src/tarel/ui/lazy_family_view.py#L92) |
| `graph_exists` | [tarel/application.py](../src/tarel/application.py#L516) |
| `graph_in_multiple_systems` | [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L285) |
| `graph_mismatch` | [tarel/context.py](../src/tarel/context.py#L103) |
| `graph_name_mismatch` | [workspaces/core.py](../src/tarel/workspaces/core.py#L311) |
| `graph_not_found` | [graph/selective.py](../src/tarel/graph/selective.py#L524), [graph/store.py](../src/tarel/graph/store.py#L65), [workspaces/core.py](../src/tarel/workspaces/core.py#L309), [workspaces/core.py](../src/tarel/workspaces/core.py#L354), [workspaces/core.py](../src/tarel/workspaces/core.py#L391), [workspaces/core.py](../src/tarel/workspaces/core.py#L415) |
| `graph_object_not_found` | [graph/selective.py](../src/tarel/graph/selective.py#L142), [graph/selective.py](../src/tarel/graph/selective.py#L179) |
| `graph_outside_focus` | [tarel/application.py](../src/tarel/application.py#L1441) |
| `graph_outside_scope` | [ui/server.py](../src/tarel/ui/server.py#L795), [ui/server.py](../src/tarel/ui/server.py#L894), [workspaces/scope.py](../src/tarel/workspaces/scope.py#L90), [workspaces/scope.py](../src/tarel/workspaces/scope.py#L241) |
| `graph_outside_system` | [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L314), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L347) |
| `graph_outside_workspace` | [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L369) |
| `graph_required` | [ui/server.py](../src/tarel/ui/server.py#L790) |
| `graph_revision_mismatch` | [graph/selective.py](../src/tarel/graph/selective.py#L481) |
| `graph_save_failed` | [graph/store.py](../src/tarel/graph/store.py#L57) |
| `identity_artifact_exists` | [discovery/identity.py](../src/tarel/discovery/identity.py#L425), [discovery/identity.py](../src/tarel/discovery/identity.py#L489) |
| `identity_inspection_budget_exceeded` | [discovery/identity.py](../src/tarel/discovery/identity.py#L416), [discovery/identity.py](../src/tarel/discovery/identity.py#L460), [discovery/identity.py](../src/tarel/discovery/identity.py#L484) |
| `identity_inventory_exists` | [discovery/identity.py](../src/tarel/discovery/identity.py#L404) |
| `identity_inventory_incomplete` | [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1722), [discovery/identity.py](../src/tarel/discovery/identity.py#L455) |
| `identity_inventory_required` | [discovery/identity.py](../src/tarel/discovery/identity.py#L412) |
| `identity_provider_orchestrator_required` | [discovery/application.py](../src/tarel/discovery/application.py#L677) |
| `identity_token_budget_exceeded` | [discovery/identity.py](../src/tarel/discovery/identity.py#L141) |
| `immutable_derived_relation` | [topology/application.py](../src/tarel/topology/application.py#L294), [topology/application.py](../src/tarel/topology/application.py#L307) |
| `immutable_semantic_concept` | [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L95), [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L106) |
| `incomplete_entity_evidence` | [entity_resolution/discovery.py](../src/tarel/entity_resolution/discovery.py#L50), [entity_resolution/discovery.py](../src/tarel/entity_resolution/discovery.py#L66), [entity_resolution/discovery.py](../src/tarel/entity_resolution/discovery.py#L137), [entity_resolution/discovery.py](../src/tarel/entity_resolution/discovery.py#L231) |
| `incomplete_entity_execution` | [entity_resolution/discovery.py](../src/tarel/entity_resolution/discovery.py#L55), [entity_resolution/discovery.py](../src/tarel/entity_resolution/discovery.py#L60) |
| `incomplete_family_proposal` | [object_families/proposals.py](../src/tarel/object_families/proposals.py#L286) |
| `incomplete_identity_validation` | [discovery/application.py](../src/tarel/discovery/application.py#L644) |
| `incomplete_query_linked_provenance` | [discovery/application.py](../src/tarel/discovery/application.py#L1546), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L396) |
| `incomplete_reference_mapping_evidence` | [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L77), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L82), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L321), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L337) |
| `incomplete_reference_mapping_manifest` | [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L70) |
| `incomplete_write_coverage` | [lineage/core.py](../src/tarel/lineage/core.py#L639) |
| `index_build_failed` | [retrieval/index.py](../src/tarel/retrieval/index.py#L156) |
| `index_checkpoint_failed` | [retrieval/index.py](../src/tarel/retrieval/index.py#L492), [retrieval/index.py](../src/tarel/retrieval/index.py#L556) |
| `index_not_found` | [retrieval/index.py](../src/tarel/retrieval/index.py#L169) |
| `invalid_annotation_limit` | [tarel/application.py](../src/tarel/application.py#L1656) |
| `invalid_annotation_patch` | [annotations/review.py](../src/tarel/annotations/review.py#L92), [annotations/review.py](../src/tarel/annotations/review.py#L97), [annotations/review.py](../src/tarel/annotations/review.py#L99), [annotations/review.py](../src/tarel/annotations/review.py#L104), [annotations/review.py](../src/tarel/annotations/review.py#L339), [annotations/review.py](../src/tarel/annotations/review.py#L350), [annotations/review.py](../src/tarel/annotations/review.py#L359) |
| `invalid_annotation_review` | [annotations/review.py](../src/tarel/annotations/review.py#L269), [annotations/review.py](../src/tarel/annotations/review.py#L273), [annotations/review.py](../src/tarel/annotations/review.py#L279), [annotations/review.py](../src/tarel/annotations/review.py#L286), [annotations/review.py](../src/tarel/annotations/review.py#L292), [annotations/review.py](../src/tarel/annotations/review.py#L304) |
| `invalid_annotation_samples` | [annotations/tasks.py](../src/tarel/annotations/tasks.py#L96), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L110), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L116), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L131), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L142), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L161), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L166), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L183), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L188), [annotations/tasks.py](../src/tarel/annotations/tasks.py#L201) |
| `invalid_annotation_scope` | [annotations/review.py](../src/tarel/annotations/review.py#L186), [tarel/cli.py](../src/tarel/cli.py#L3100) |
| `invalid_annotation_state` | [annotations/review.py](../src/tarel/annotations/review.py#L160), [annotations/review.py](../src/tarel/annotations/review.py#L374), [annotations/states.py](../src/tarel/annotations/states.py#L29) |
| `invalid_annotation_target` | [annotations/review.py](../src/tarel/annotations/review.py#L69) |
| `invalid_batch` | [annotations/runner.py](../src/tarel/annotations/runner.py#L43), [annotations/runner.py](../src/tarel/annotations/runner.py#L45) |
| `invalid_batch_size` | [tarel/application.py](../src/tarel/application.py#L1330), [retrieval/index.py](../src/tarel/retrieval/index.py#L55), [retrieval/local.py](../src/tarel/retrieval/local.py#L222) |
| `invalid_binding_input` | [object_bindings/cli.py](../src/tarel/object_bindings/cli.py#L118) |
| `invalid_binding_limit` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L188) |
| `invalid_binding_scope` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L190), [object_bindings/application.py](../src/tarel/object_bindings/application.py#L195) |
| `invalid_binding_values` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L184), [object_bindings/cli.py](../src/tarel/object_bindings/cli.py#L81) |
| `invalid_catalog` | [connectors/catalog.py](../src/tarel/connectors/catalog.py#L53), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L55), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L62), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L82), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L88), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L93), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L97), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L104), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L109), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L118), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L123), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L132), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L138), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L144), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L159), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L186), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L188), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L215), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L224), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L229), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L237), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L246), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L253), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L260), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L265), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L272), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L280), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L285), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L291), [connectors/catalog.py](../src/tarel/connectors/catalog.py#L297) |
| `invalid_change_report` | [graph/change_store.py](../src/tarel/graph/change_store.py#L70), [graph/change_store.py](../src/tarel/graph/change_store.py#L75), [graph/changes.py](../src/tarel/graph/changes.py#L46), [graph/changes.py](../src/tarel/graph/changes.py#L335), [graph/changes.py](../src/tarel/graph/changes.py#L343), [graph/refresh.py](../src/tarel/graph/refresh.py#L51), [graph/refresh.py](../src/tarel/graph/refresh.py#L53), [graph/refresh.py](../src/tarel/graph/refresh.py#L56), [graph/refresh.py](../src/tarel/graph/refresh.py#L127), [graph/refresh.py](../src/tarel/graph/refresh.py#L131), [graph/refresh.py](../src/tarel/graph/refresh.py#L427), [graph/refresh.py](../src/tarel/graph/refresh.py#L434) |
| `invalid_config` | [tarel/application.py](../src/tarel/application.py#L287), [tarel/application.py](../src/tarel/application.py#L305), [tarel/application.py](../src/tarel/application.py#L327), [tarel/application.py](../src/tarel/application.py#L356), [tarel/application.py](../src/tarel/application.py#L2075), [tarel/application.py](../src/tarel/application.py#L2092), [tarel/application.py](../src/tarel/application.py#L2131), [providers/config.py](../src/tarel/providers/config.py#L286), [providers/config.py](../src/tarel/providers/config.py#L289), [providers/config.py](../src/tarel/providers/config.py#L408) |
| `invalid_config_reference` | [sources/application.py](../src/tarel/sources/application.py#L402), [sources/contracts.py](../src/tarel/sources/contracts.py#L177), [sources/contracts.py](../src/tarel/sources/contracts.py#L193) |
| `invalid_connector_name` | [connectors/authoring.py](../src/tarel/connectors/authoring.py#L22) |
| `invalid_content_type` | [ui/server.py](../src/tarel/ui/server.py#L950) |
| `invalid_context_budget` | [tarel/context.py](../src/tarel/context.py#L329), [tarel/context.py](../src/tarel/context.py#L331), [tarel/context.py](../src/tarel/context.py#L333), [tarel/context.py](../src/tarel/context.py#L335), [tarel/context.py](../src/tarel/context.py#L337), [tarel/context.py](../src/tarel/context.py#L339), [tarel/context.py](../src/tarel/context.py#L344), [tarel/context.py](../src/tarel/context.py#L358), [tarel/context.py](../src/tarel/context.py#L363), [tarel/context.py](../src/tarel/context.py#L368), [tarel/context.py](../src/tarel/context.py#L373) |
| `invalid_context_expansion` | [expansion/cli.py](../src/tarel/expansion/cli.py#L42), [expansion/cli.py](../src/tarel/expansion/cli.py#L45), [expansion/contracts.py](../src/tarel/expansion/contracts.py#L178) |
| `invalid_context_packet` | [tarel/context_packets.py](../src/tarel/context_packets.py#L121), [tarel/context_packets.py](../src/tarel/context_packets.py#L126), [tarel/context_packets.py](../src/tarel/context_packets.py#L288), [tarel/context_packets.py](../src/tarel/context_packets.py#L298), [tarel/context_packets.py](../src/tarel/context_packets.py#L305), [tarel/context_packets.py](../src/tarel/context_packets.py#L311), [tarel/context_packets.py](../src/tarel/context_packets.py#L316), [tarel/context_packets.py](../src/tarel/context_packets.py#L345), [tarel/context_packets.py](../src/tarel/context_packets.py#L349), [tarel/context_packets.py](../src/tarel/context_packets.py#L363), [tarel/context_packets.py](../src/tarel/context_packets.py#L369) |
| `invalid_cube` | [semantics/cube.py](../src/tarel/semantics/cube.py#L68), [semantics/cube.py](../src/tarel/semantics/cube.py#L324), [semantics/cube.py](../src/tarel/semantics/cube.py#L332), [semantics/cube.py](../src/tarel/semantics/cube.py#L338) |
| `invalid_demo_data` | [tarel/demo.py](../src/tarel/demo.py#L95) |
| `invalid_demo_version` | [tarel/demo.py](../src/tarel/demo.py#L46) |
| `invalid_discovery` | [discovery/application.py](../src/tarel/discovery/application.py#L194), [discovery/application.py](../src/tarel/discovery/application.py#L196), [discovery/application.py](../src/tarel/discovery/application.py#L201), [discovery/application.py](../src/tarel/discovery/application.py#L207), [discovery/application.py](../src/tarel/discovery/application.py#L419), [discovery/application.py](../src/tarel/discovery/application.py#L661), [discovery/application.py](../src/tarel/discovery/application.py#L750), [discovery/application.py](../src/tarel/discovery/application.py#L816), [discovery/application.py](../src/tarel/discovery/application.py#L834), [discovery/application.py](../src/tarel/discovery/application.py#L871), [discovery/cli.py](../src/tarel/discovery/cli.py#L317), [discovery/cli.py](../src/tarel/discovery/cli.py#L321), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L131), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L136), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L224), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L302), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L419), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L426), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L433), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L443), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L454), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L563), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L566), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L600), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L604), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L608), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L612), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L616), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L674), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L681), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L709), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L713), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L722), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L729), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L734), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L740), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L744), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L748), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L752), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L759), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L904), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L908), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L913), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L962), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L970), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L975), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L979), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L985), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L991), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L996), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1000), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1004), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1008), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1012), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1018), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1022), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1032), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1038), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1043), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1048), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1054), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1060), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1066), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1071), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1076), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1081), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1089), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1131), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1138), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1144), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1148), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1153), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1159), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1165), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1174), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1180), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1183), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1231), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1236), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1240), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1246), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1250), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1258), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1263), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1274), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1286), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1291), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1306), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1313), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1328), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1335), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1342), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1563), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1580), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1651), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1831), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1838), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1844), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1866), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1877), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1883), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1889), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1892), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1898), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1901), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1907), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1913), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1930), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1938), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1943), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1955), [discovery/store.py](../src/tarel/discovery/store.py#L74), [discovery/store.py](../src/tarel/discovery/store.py#L78), [discovery/store.py](../src/tarel/discovery/store.py#L81) |
| `invalid_discovery_id` | [discovery/store.py](../src/tarel/discovery/store.py#L98) |
| `invalid_discovery_promotion` | [discovery/application.py](../src/tarel/discovery/application.py#L439), [discovery/application.py](../src/tarel/discovery/application.py#L445), [discovery/application.py](../src/tarel/discovery/application.py#L460), [discovery/application.py](../src/tarel/discovery/application.py#L468), [discovery/application.py](../src/tarel/discovery/application.py#L507), [discovery/application.py](../src/tarel/discovery/application.py#L512), [discovery/application.py](../src/tarel/discovery/application.py#L534), [discovery/application.py](../src/tarel/discovery/application.py#L541), [discovery/application.py](../src/tarel/discovery/application.py#L559), [entity_resolution/discovery.py](../src/tarel/entity_resolution/discovery.py#L38), [entity_resolution/discovery.py](../src/tarel/entity_resolution/discovery.py#L43), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L49), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L54), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L64) |
| `invalid_enrichment_permission` | [sources/contracts.py](../src/tarel/sources/contracts.py#L70), [sources/contracts.py](../src/tarel/sources/contracts.py#L143) |
| `invalid_enrichment_policy` | [sources/contracts.py](../src/tarel/sources/contracts.py#L150), [sources/contracts.py](../src/tarel/sources/contracts.py#L157) |
| `invalid_entity_alias_evidence` | [discovery/identity.py](../src/tarel/discovery/identity.py#L473), [discovery/identity.py](../src/tarel/discovery/identity.py#L502) |
| `invalid_entity_alias_group` | [discovery/identity.py](../src/tarel/discovery/identity.py#L251), [discovery/identity.py](../src/tarel/discovery/identity.py#L257) |
| `invalid_entity_reflection` | [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1529) |
| `invalid_entity_resolution` | [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L176), [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L283), [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L303), [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L317), [entity_resolution/cli.py](../src/tarel/entity_resolution/cli.py#L196), [entity_resolution/cli.py](../src/tarel/entity_resolution/cli.py#L201), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L67), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L72), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L78), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L275), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L303), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L360), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L370), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L391), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L505), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L514), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L519), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L529), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L575), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L664), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L677), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L689), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L697), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L705), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L710), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L739), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L747), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L757), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L763), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L774), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L784), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L789), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L797), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L830), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L835), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L840), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L856), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L862), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L873), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L878), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L893), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L901), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L910), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L920), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L930), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L940), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L949), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L958), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L964), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L983), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L992), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L998), [entity_resolution/store.py](../src/tarel/entity_resolution/store.py#L75), [entity_resolution/store.py](../src/tarel/entity_resolution/store.py#L80), [entity_resolution/store.py](../src/tarel/entity_resolution/store.py#L86) |
| `invalid_entity_resolution_id` | [entity_resolution/store.py](../src/tarel/entity_resolution/store.py#L108) |
| `invalid_entity_resolution_import` | [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L43) |
| `invalid_entity_resolution_mode` | [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L118), [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L171) |
| `invalid_entity_resolution_supersede` | [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L394) |
| `invalid_entrypoint` | [connectors/host.py](../src/tarel/connectors/host.py#L54), [connectors/host.py](../src/tarel/connectors/host.py#L61), [connectors/host.py](../src/tarel/connectors/host.py#L66), [connectors/host.py](../src/tarel/connectors/host.py#L124) |
| `invalid_expansion_input` | [expansion/cli.py](../src/tarel/expansion/cli.py#L82), [expansion/projections.py](../src/tarel/expansion/projections.py#L61), [expansion/projections.py](../src/tarel/expansion/projections.py#L173) |
| `invalid_expansion_stdin` | [expansion/cli.py](../src/tarel/expansion/cli.py#L37) |
| `invalid_family_proposals` | [object_families/proposal_contracts.py](../src/tarel/object_families/proposal_contracts.py#L33), [object_families/proposals.py](../src/tarel/object_families/proposals.py#L172) |
| `invalid_field_reference` | [workspaces/core.py](../src/tarel/workspaces/core.py#L409) |
| `invalid_focus` | [focus/contracts.py](../src/tarel/focus/contracts.py#L140), [focus/contracts.py](../src/tarel/focus/contracts.py#L155), [focus/contracts.py](../src/tarel/focus/contracts.py#L161), [focus/contracts.py](../src/tarel/focus/contracts.py#L163), [focus/contracts.py](../src/tarel/focus/contracts.py#L165), [focus/contracts.py](../src/tarel/focus/contracts.py#L171), [focus/contracts.py](../src/tarel/focus/contracts.py#L174), [focus/contracts.py](../src/tarel/focus/contracts.py#L178), [focus/contracts.py](../src/tarel/focus/contracts.py#L180), [focus/contracts.py](../src/tarel/focus/contracts.py#L183), [focus/contracts.py](../src/tarel/focus/contracts.py#L185), [focus/contracts.py](../src/tarel/focus/contracts.py#L192), [focus/contracts.py](../src/tarel/focus/contracts.py#L197), [focus/contracts.py](../src/tarel/focus/contracts.py#L235), [focus/contracts.py](../src/tarel/focus/contracts.py#L257), [focus/contracts.py](../src/tarel/focus/contracts.py#L271), [focus/contracts.py](../src/tarel/focus/contracts.py#L276), [focus/contracts.py](../src/tarel/focus/contracts.py#L282), [focus/contracts.py](../src/tarel/focus/contracts.py#L288), [focus/contracts.py](../src/tarel/focus/contracts.py#L294), [focus/contracts.py](../src/tarel/focus/contracts.py#L300), [focus/contracts.py](../src/tarel/focus/contracts.py#L306), [focus/store.py](../src/tarel/focus/store.py#L51), [focus/store.py](../src/tarel/focus/store.py#L53), [focus/store.py](../src/tarel/focus/store.py#L56) |
| `invalid_focus_name` | [focus/store.py](../src/tarel/focus/store.py#L68) |
| `invalid_focus_scope` | [tarel/application.py](../src/tarel/application.py#L1430) |
| `invalid_graph` | [graph/contracts.py](../src/tarel/graph/contracts.py#L94), [graph/contracts.py](../src/tarel/graph/contracts.py#L130), [graph/contracts.py](../src/tarel/graph/contracts.py#L132), [graph/contracts.py](../src/tarel/graph/contracts.py#L163), [graph/contracts.py](../src/tarel/graph/contracts.py#L206), [graph/contracts.py](../src/tarel/graph/contracts.py#L224), [graph/contracts.py](../src/tarel/graph/contracts.py#L228), [graph/contracts.py](../src/tarel/graph/contracts.py#L234), [graph/contracts.py](../src/tarel/graph/contracts.py#L242), [graph/contracts.py](../src/tarel/graph/contracts.py#L248), [graph/contracts.py](../src/tarel/graph/contracts.py#L256), [graph/contracts.py](../src/tarel/graph/contracts.py#L259), [graph/contracts.py](../src/tarel/graph/contracts.py#L266), [graph/selective.py](../src/tarel/graph/selective.py#L337), [graph/selective.py](../src/tarel/graph/selective.py#L526), [graph/store.py](../src/tarel/graph/store.py#L67), [graph/store.py](../src/tarel/graph/store.py#L69) |
| `invalid_graph_cache` | [graph/selective.py](../src/tarel/graph/selective.py#L574) |
| `invalid_graph_name` | [graph/change_store.py](../src/tarel/graph/change_store.py#L85), [graph/store.py](../src/tarel/graph/store.py#L146), [retrieval/index.py](../src/tarel/retrieval/index.py#L238) |
| `invalid_graph_object` | [workspaces/core.py](../src/tarel/workspaces/core.py#L442) |
| `invalid_graph_page` | [graph/selective.py](../src/tarel/graph/selective.py#L244) |
| `invalid_graph_revision` | [graph/change_store.py](../src/tarel/graph/change_store.py#L87) |
| `invalid_graph_selection` | [graph/selective.py](../src/tarel/graph/selective.py#L127), [graph/selective.py](../src/tarel/graph/selective.py#L163), [graph/selective.py](../src/tarel/graph/selective.py#L168), [graph/selective.py](../src/tarel/graph/selective.py#L474), [graph/selective.py](../src/tarel/graph/selective.py#L476) |
| `invalid_grounding_limit` | [sdk/client.py](../src/tarel/sdk/client.py#L1308) |
| `invalid_grounding_scope` | [sdk/client.py](../src/tarel/sdk/client.py#L1219), [sdk/client.py](../src/tarel/sdk/client.py#L1247), [sdk/client.py](../src/tarel/sdk/client.py#L1258), [sdk/client.py](../src/tarel/sdk/client.py#L1369), [sdk/client.py](../src/tarel/sdk/client.py#L1375) |
| `invalid_identity_candidate` | [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1728), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1733), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1744) |
| `invalid_identity_inspection` | [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1198), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1207), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1222), [discovery/identity.py](../src/tarel/discovery/identity.py#L385), [discovery/identity.py](../src/tarel/discovery/identity.py#L525), [discovery/identity.py](../src/tarel/discovery/identity.py#L532), [discovery/identity.py](../src/tarel/discovery/identity.py#L540), [discovery/identity.py](../src/tarel/discovery/identity.py#L556), [discovery/identity.py](../src/tarel/discovery/identity.py#L564), [discovery/identity.py](../src/tarel/discovery/identity.py#L572), [discovery/identity.py](../src/tarel/discovery/identity.py#L580), [discovery/identity.py](../src/tarel/discovery/identity.py#L591), [discovery/identity.py](../src/tarel/discovery/identity.py#L599), [discovery/identity.py](../src/tarel/discovery/identity.py#L604), [discovery/identity.py](../src/tarel/discovery/identity.py#L629), [discovery/identity.py](../src/tarel/discovery/identity.py#L634), [discovery/identity.py](../src/tarel/discovery/identity.py#L642), [discovery/identity.py](../src/tarel/discovery/identity.py#L647), [discovery/identity.py](../src/tarel/discovery/identity.py#L655) |
| `invalid_identity_inventory` | [discovery/application.py](../src/tarel/discovery/application.py#L942), [discovery/identity.py](../src/tarel/discovery/identity.py#L106), [discovery/identity.py](../src/tarel/discovery/identity.py#L131), [discovery/identity.py](../src/tarel/discovery/identity.py#L136) |
| `invalid_identity_inventory_page` | [discovery/identity.py](../src/tarel/discovery/identity.py#L187), [discovery/identity.py](../src/tarel/discovery/identity.py#L192), [discovery/identity.py](../src/tarel/discovery/identity.py#L421), [discovery/identity.py](../src/tarel/discovery/identity.py#L440), [discovery/identity.py](../src/tarel/discovery/identity.py#L446) |
| `invalid_index` | [retrieval/index.py](../src/tarel/retrieval/index.py#L177), [retrieval/index.py](../src/tarel/retrieval/index.py#L184), [retrieval/index.py](../src/tarel/retrieval/index.py#L219), [retrieval/index.py](../src/tarel/retrieval/index.py#L233), [retrieval/index.py](../src/tarel/retrieval/index.py#L677) |
| `invalid_index_checkpoint` | [retrieval/index.py](../src/tarel/retrieval/index.py#L257), [retrieval/index.py](../src/tarel/retrieval/index.py#L276), [retrieval/index.py](../src/tarel/retrieval/index.py#L507), [retrieval/index.py](../src/tarel/retrieval/index.py#L525) |
| `invalid_knowledge` | [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L142), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L154), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L160), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L192), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L196), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L198), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L201), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L259), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L261), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L317), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L325), [knowledge/store.py](../src/tarel/knowledge/store.py#L68), [knowledge/store.py](../src/tarel/knowledge/store.py#L73) |
| `invalid_knowledge_budget` | [knowledge/core.py](../src/tarel/knowledge/core.py#L38) |
| `invalid_knowledge_evidence` | [annotations/apply.py](../src/tarel/annotations/apply.py#L134), [annotations/apply.py](../src/tarel/annotations/apply.py#L139) |
| `invalid_knowledge_id` | [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L254), [knowledge/store.py](../src/tarel/knowledge/store.py#L89) |
| `invalid_knowledge_mode` | [knowledge/core.py](../src/tarel/knowledge/core.py#L33) |
| `invalid_knowledge_scope` | [tarel/application.py](../src/tarel/application.py#L2022), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L40), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L47), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L51), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L280), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L283), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L290), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L295), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L301), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L306), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L311) |
| `invalid_knowledge_source` | [tarel/application.py](../src/tarel/application.py#L1538) |
| `invalid_knowledge_state` | [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L266) |
| `invalid_limit` | [tarel/application.py](../src/tarel/application.py#L932), [retrieval/index.py](../src/tarel/retrieval/index.py#L308), [tarel/search.py](../src/tarel/search.py#L149) |
| `invalid_lineage` | [lineage/contracts.py](../src/tarel/lineage/contracts.py#L344), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L375), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L395), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L400), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L411), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L414), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L420), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L423), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L425), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L435), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L441), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L452), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L468), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L470), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L477), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L479), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L483), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L499), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L504), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L526), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L528), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L531), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L536), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L538), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L549), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L607), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L705), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L723), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L725), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L738), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L740), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L744), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L753), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L755), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L760), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L766), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L772), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L785), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L793), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L803), [lineage/contracts.py](../src/tarel/lineage/contracts.py#L812), [lineage/core.py](../src/tarel/lineage/core.py#L692), [lineage/store.py](../src/tarel/lineage/store.py#L64), [lineage/store.py](../src/tarel/lineage/store.py#L66), [lineage/store.py](../src/tarel/lineage/store.py#L69) |
| `invalid_lineage_analysis_cache` | [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L64), [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L70), [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L81), [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L89), [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L117), [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L126), [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L138), [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L143), [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L201), [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L212), [lineage/application.py](../src/tarel/lineage/application.py#L735) |
| `invalid_lineage_analysis_failure` | [lineage/core.py](../src/tarel/lineage/core.py#L321) |
| `invalid_lineage_change` | [lineage/refresh.py](../src/tarel/lineage/refresh.py#L105), [lineage/refresh.py](../src/tarel/lineage/refresh.py#L107), [lineage/refresh.py](../src/tarel/lineage/refresh.py#L181), [lineage/refresh.py](../src/tarel/lineage/refresh.py#L185), [lineage/refresh.py](../src/tarel/lineage/refresh.py#L933), [lineage/refresh.py](../src/tarel/lineage/refresh.py#L939), [lineage/refresh.py](../src/tarel/lineage/refresh.py#L946), [lineage/refresh.py](../src/tarel/lineage/refresh.py#L952) |
| `invalid_lineage_change_report` | [lineage/change_store.py](../src/tarel/lineage/change_store.py#L69), [lineage/change_store.py](../src/tarel/lineage/change_store.py#L74) |
| `invalid_lineage_input` | [lineage/source.py](../src/tarel/lineage/source.py#L148), [lineage/source.py](../src/tarel/lineage/source.py#L153), [lineage/source.py](../src/tarel/lineage/source.py#L173), [lineage/source.py](../src/tarel/lineage/source.py#L176), [lineage/source.py](../src/tarel/lineage/source.py#L188), [lineage/source.py](../src/tarel/lineage/source.py#L207), [lineage/source.py](../src/tarel/lineage/source.py#L210), [lineage/source.py](../src/tarel/lineage/source.py#L235), [lineage/source.py](../src/tarel/lineage/source.py#L251), [lineage/source.py](../src/tarel/lineage/source.py#L258), [lineage/source.py](../src/tarel/lineage/source.py#L274), [lineage/source.py](../src/tarel/lineage/source.py#L280), [lineage/source.py](../src/tarel/lineage/source.py#L299), [lineage/source.py](../src/tarel/lineage/source.py#L305), [lineage/source.py](../src/tarel/lineage/source.py#L312), [lineage/source.py](../src/tarel/lineage/source.py#L329), [lineage/source.py](../src/tarel/lineage/source.py#L337), [lineage/source.py](../src/tarel/lineage/source.py#L348), [lineage/source.py](../src/tarel/lineage/source.py#L354), [lineage/source.py](../src/tarel/lineage/source.py#L363), [lineage/source.py](../src/tarel/lineage/source.py#L368), [lineage/source.py](../src/tarel/lineage/source.py#L375), [lineage/source.py](../src/tarel/lineage/source.py#L381), [lineage/source.py](../src/tarel/lineage/source.py#L392), [lineage/source.py](../src/tarel/lineage/source.py#L397) |
| `invalid_lineage_limit` | [tarel/grounding_application.py](../src/tarel/grounding_application.py#L243) |
| `invalid_lineage_name` | [lineage/change_store.py](../src/tarel/lineage/change_store.py#L87), [lineage/store.py](../src/tarel/lineage/store.py#L87) |
| `invalid_lineage_proposal` | [lineage/cli.py](../src/tarel/lineage/cli.py#L445), [lineage/cli.py](../src/tarel/lineage/cli.py#L447), [lineage/core.py](../src/tarel/lineage/core.py#L226), [lineage/core.py](../src/tarel/lineage/core.py#L430), [lineage/core.py](../src/tarel/lineage/core.py#L513), [lineage/core.py](../src/tarel/lineage/core.py#L552), [lineage/core.py](../src/tarel/lineage/core.py#L573), [lineage/core.py](../src/tarel/lineage/core.py#L600), [lineage/core.py](../src/tarel/lineage/core.py#L606), [lineage/core.py](../src/tarel/lineage/core.py#L675), [lineage/core.py](../src/tarel/lineage/core.py#L741), [lineage/core.py](../src/tarel/lineage/core.py#L750), [lineage/core.py](../src/tarel/lineage/core.py#L759), [lineage/core.py](../src/tarel/lineage/core.py#L764), [lineage/core.py](../src/tarel/lineage/core.py#L773), [lineage/core.py](../src/tarel/lineage/core.py#L784), [lineage/core.py](../src/tarel/lineage/core.py#L789) |
| `invalid_lineage_review` | [lineage/cli.py](../src/tarel/lineage/cli.py#L418), [lineage/review.py](../src/tarel/lineage/review.py#L32), [lineage/review.py](../src/tarel/lineage/review.py#L50) |
| `invalid_lineage_revision` | [lineage/change_store.py](../src/tarel/lineage/change_store.py#L92) |
| `invalid_lineage_run` | [lineage/application.py](../src/tarel/lineage/application.py#L530) |
| `invalid_lineage_search` | [lineage/traversal.py](../src/tarel/lineage/traversal.py#L156), [lineage/traversal.py](../src/tarel/lineage/traversal.py#L158) |
| `invalid_lineage_target` | [lineage/core.py](../src/tarel/lineage/core.py#L724) |
| `invalid_lineage_trace` | [lineage/traversal.py](../src/tarel/lineage/traversal.py#L358), [lineage/traversal.py](../src/tarel/lineage/traversal.py#L364) |
| `invalid_logical_endpoint` | [topology/endpoint_contracts.py](../src/tarel/topology/endpoint_contracts.py#L43), [topology/endpoint_contracts.py](../src/tarel/topology/endpoint_contracts.py#L51), [topology/endpoint_contracts.py](../src/tarel/topology/endpoint_contracts.py#L56), [topology/endpoint_contracts.py](../src/tarel/topology/endpoint_contracts.py#L77), [topology/endpoints.py](../src/tarel/topology/endpoints.py#L229) |
| `invalid_logical_endpoint_mode` | [topology/endpoints.py](../src/tarel/topology/endpoints.py#L227) |
| `invalid_logical_endpoint_schema` | [topology/endpoints.py](../src/tarel/topology/endpoints.py#L260) |
| `invalid_logical_hint_mode` | [tarel/context_hints_application.py](../src/tarel/context_hints_application.py#L48) |
| `invalid_logical_join` | [logical_joins/contracts.py](../src/tarel/logical_joins/contracts.py#L159), [logical_joins/contracts.py](../src/tarel/logical_joins/contracts.py#L211), [logical_joins/store.py](../src/tarel/logical_joins/store.py#L37), [logical_joins/store.py](../src/tarel/logical_joins/store.py#L39), [logical_joins/store.py](../src/tarel/logical_joins/store.py#L42) |
| `invalid_logical_join_endpoint` | [logical_joins/application.py](../src/tarel/logical_joins/application.py#L197) |
| `invalid_logical_join_limit` | [logical_joins/application.py](../src/tarel/logical_joins/application.py#L195) |
| `invalid_logical_join_mode` | [logical_joins/application.py](../src/tarel/logical_joins/application.py#L193) |
| `invalid_logical_join_path` | [logical_joins/store.py](../src/tarel/logical_joins/store.py#L20) |
| `invalid_logical_join_program` | [discovery/logical_program.py](../src/tarel/discovery/logical_program.py#L74) |
| `invalid_logical_join_promotion` | [logical_joins/application.py](../src/tarel/logical_joins/application.py#L89) |
| `invalid_logical_join_review` | [logical_joins/application.py](../src/tarel/logical_joins/application.py#L159) |
| `invalid_logical_metadata_scope` | [ui/logical_metadata.py](../src/tarel/ui/logical_metadata.py#L59) |
| `invalid_logical_topology` | [topology/cli.py](../src/tarel/topology/cli.py#L91), [topology/cli.py](../src/tarel/topology/cli.py#L96), [topology/contracts.py](../src/tarel/topology/contracts.py#L134), [topology/contracts.py](../src/tarel/topology/contracts.py#L156), [topology/contracts.py](../src/tarel/topology/contracts.py#L198), [topology/contracts.py](../src/tarel/topology/contracts.py#L217), [topology/contracts.py](../src/tarel/topology/contracts.py#L316), [topology/contracts.py](../src/tarel/topology/contracts.py#L327), [topology/contracts.py](../src/tarel/topology/contracts.py#L333), [topology/contracts.py](../src/tarel/topology/contracts.py#L341), [topology/contracts.py](../src/tarel/topology/contracts.py#L346), [topology/contracts.py](../src/tarel/topology/contracts.py#L370), [topology/contracts.py](../src/tarel/topology/contracts.py#L441), [topology/contracts.py](../src/tarel/topology/contracts.py#L461), [topology/contracts.py](../src/tarel/topology/contracts.py#L513), [topology/contracts.py](../src/tarel/topology/contracts.py#L525), [topology/contracts.py](../src/tarel/topology/contracts.py#L529), [topology/contracts.py](../src/tarel/topology/contracts.py#L534), [topology/contracts.py](../src/tarel/topology/contracts.py#L539), [topology/contracts.py](../src/tarel/topology/contracts.py#L549), [topology/contracts.py](../src/tarel/topology/contracts.py#L554), [topology/contracts.py](../src/tarel/topology/contracts.py#L559), [topology/contracts.py](../src/tarel/topology/contracts.py#L565), [topology/contracts.py](../src/tarel/topology/contracts.py#L574), [topology/contracts.py](../src/tarel/topology/contracts.py#L581), [topology/contracts.py](../src/tarel/topology/contracts.py#L589), [topology/contracts.py](../src/tarel/topology/contracts.py#L594), [topology/contracts.py](../src/tarel/topology/contracts.py#L600), [topology/contracts.py](../src/tarel/topology/contracts.py#L607), [topology/contracts.py](../src/tarel/topology/contracts.py#L612), [topology/contracts.py](../src/tarel/topology/contracts.py#L618), [topology/contracts.py](../src/tarel/topology/contracts.py#L624), [topology/contracts.py](../src/tarel/topology/contracts.py#L667), [topology/contracts.py](../src/tarel/topology/contracts.py#L700), [topology/contracts.py](../src/tarel/topology/contracts.py#L707), [topology/contracts.py](../src/tarel/topology/contracts.py#L715), [topology/contracts.py](../src/tarel/topology/contracts.py#L723), [topology/contracts.py](../src/tarel/topology/contracts.py#L728), [topology/contracts.py](../src/tarel/topology/contracts.py#L737), [topology/contracts.py](../src/tarel/topology/contracts.py#L751), [topology/contracts.py](../src/tarel/topology/contracts.py#L760), [topology/contracts.py](../src/tarel/topology/contracts.py#L769), [topology/contracts.py](../src/tarel/topology/contracts.py#L781), [topology/contracts.py](../src/tarel/topology/contracts.py#L786), [topology/contracts.py](../src/tarel/topology/contracts.py#L794), [topology/contracts.py](../src/tarel/topology/contracts.py#L802), [topology/contracts.py](../src/tarel/topology/contracts.py#L810), [topology/contracts.py](../src/tarel/topology/contracts.py#L815), [topology/contracts.py](../src/tarel/topology/contracts.py#L821), [topology/contracts.py](../src/tarel/topology/contracts.py#L826), [topology/store.py](../src/tarel/topology/store.py#L80), [topology/store.py](../src/tarel/topology/store.py#L85), [topology/store.py](../src/tarel/topology/store.py#L90) |
| `invalid_logical_topology_graph_name` | [topology/store.py](../src/tarel/topology/store.py#L112) |
| `invalid_logical_topology_import` | [topology/application.py](../src/tarel/topology/application.py#L277), [topology/application.py](../src/tarel/topology/application.py#L299) |
| `invalid_manifest` | [connectors/contracts.py](../src/tarel/connectors/contracts.py#L35), [connectors/contracts.py](../src/tarel/connectors/contracts.py#L52), [connectors/contracts.py](../src/tarel/connectors/contracts.py#L60), [connectors/contracts.py](../src/tarel/connectors/contracts.py#L65), [connectors/host.py](../src/tarel/connectors/host.py#L75), [connectors/host.py](../src/tarel/connectors/host.py#L81), [connectors/host.py](../src/tarel/connectors/host.py#L88), [connectors/host.py](../src/tarel/connectors/host.py#L110) |
| `invalid_manual_hop` | [lineage/manual.py](../src/tarel/lineage/manual.py#L150), [lineage/manual.py](../src/tarel/lineage/manual.py#L155), [lineage/manual.py](../src/tarel/lineage/manual.py#L164) |
| `invalid_manual_job` | [lineage/manual.py](../src/tarel/lineage/manual.py#L62) |
| `invalid_manual_lineage` | [lineage/manual.py](../src/tarel/lineage/manual.py#L258) |
| `invalid_model` | [retrieval/local.py](../src/tarel/retrieval/local.py#L93) |
| `invalid_model_source` | [retrieval/local.py](../src/tarel/retrieval/local.py#L174) |
| `invalid_model_target` | [retrieval/local.py](../src/tarel/retrieval/local.py#L108) |
| `invalid_object_binding` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L61), [object_bindings/application.py](../src/tarel/object_bindings/application.py#L99), [object_bindings/contracts.py](../src/tarel/object_bindings/contracts.py#L133) |
| `invalid_object_binding_mode` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L269) |
| `invalid_object_binding_path` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L283) |
| `invalid_object_family` | [object_families/application.py](../src/tarel/object_families/application.py#L93), [object_families/application.py](../src/tarel/object_families/application.py#L111), [object_families/cli.py](../src/tarel/object_families/cli.py#L181), [object_families/cli.py](../src/tarel/object_families/cli.py#L185), [object_families/contracts.py](../src/tarel/object_families/contracts.py#L270), [object_families/store.py](../src/tarel/object_families/store.py#L65), [object_families/store.py](../src/tarel/object_families/store.py#L69), [object_families/store.py](../src/tarel/object_families/store.py#L74) |
| `invalid_object_family_command` | [object_families/cli.py](../src/tarel/object_families/cli.py#L146) |
| `invalid_object_family_filter` | [object_families/application.py](../src/tarel/object_families/application.py#L366), [object_families/cli.py](../src/tarel/object_families/cli.py#L121) |
| `invalid_object_family_import` | [object_families/application.py](../src/tarel/object_families/application.py#L190) |
| `invalid_object_family_mode` | [object_families/application.py](../src/tarel/object_families/application.py#L495), [ui/presentation.py](../src/tarel/ui/presentation.py#L144), [ui/server.py](../src/tarel/ui/server.py#L472) |
| `invalid_object_family_page` | [object_families/application.py](../src/tarel/object_families/application.py#L349) |
| `invalid_object_family_path` | [object_families/store.py](../src/tarel/object_families/store.py#L112), [object_families/store.py](../src/tarel/object_families/store.py#L116), [object_families/store.py](../src/tarel/object_families/store.py#L123) |
| `invalid_object_family_scope` | [object_families/application.py](../src/tarel/object_families/application.py#L340), [object_families/application.py](../src/tarel/object_families/application.py#L345) |
| `invalid_object_reference` | [workspaces/core.py](../src/tarel/workspaces/core.py#L385) |
| `invalid_optional_edge` | [ui/optional_metadata.py](../src/tarel/ui/optional_metadata.py#L90) |
| `invalid_optional_endpoint` | [ui/optional_metadata.py](../src/tarel/ui/optional_metadata.py#L181) |
| `invalid_optional_metadata_request` | [ui/optional_metadata.py](../src/tarel/ui/optional_metadata.py#L60) |
| `invalid_optional_request` | [ui/server.py](../src/tarel/ui/server.py#L343), [ui/server.py](../src/tarel/ui/server.py#L418), [ui/server.py](../src/tarel/ui/server.py#L421), [ui/server.py](../src/tarel/ui/server.py#L476) |
| `invalid_ossie` | [semantics/ossie.py](../src/tarel/semantics/ossie.py#L58), [semantics/ossie.py](../src/tarel/semantics/ossie.py#L490), [semantics/ossie.py](../src/tarel/semantics/ossie.py#L496), [semantics/ossie.py](../src/tarel/semantics/ossie.py#L504), [semantics/ossie.py](../src/tarel/semantics/ossie.py#L513), [semantics/ossie.py](../src/tarel/semantics/ossie.py#L519), [semantics/ossie.py](../src/tarel/semantics/ossie.py#L528), [semantics/ossie.py](../src/tarel/semantics/ossie.py#L537), [semantics/ossie.py](../src/tarel/semantics/ossie.py#L545) |
| `invalid_pair_budget` | [relationships/core.py](../src/tarel/relationships/core.py#L203) |
| `invalid_port` | [ui/server.py](../src/tarel/ui/server.py#L1030) |
| `invalid_profile_row_limit` | [tarel/application.py](../src/tarel/application.py#L1876), [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L205), [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L377), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L520), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L792), [sources/application.py](../src/tarel/sources/application.py#L242) |
| `invalid_proposal` | [annotations/apply.py](../src/tarel/annotations/apply.py#L46), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L77), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L102), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L105), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L112), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L136), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L152), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L156), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L171), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L179), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L185), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L194), [annotations/contracts.py](../src/tarel/annotations/contracts.py#L197), [tarel/cli.py](../src/tarel/cli.py#L3202), [tarel/cli.py](../src/tarel/cli.py#L3204) |
| `invalid_provider_adapter` | [tarel/application.py](../src/tarel/application.py#L420), [providers/config.py](../src/tarel/providers/config.py#L106), [providers/config.py](../src/tarel/providers/config.py#L198), [providers/config.py](../src/tarel/providers/config.py#L352), [providers/host.py](../src/tarel/providers/host.py#L61), [providers/host.py](../src/tarel/providers/host.py#L66) |
| `invalid_provider_config` | [tarel/application.py](../src/tarel/application.py#L448), [providers/config.py](../src/tarel/providers/config.py#L121), [providers/config.py](../src/tarel/providers/config.py#L161), [providers/config.py](../src/tarel/providers/config.py#L315), [providers/config.py](../src/tarel/providers/config.py#L361), [providers/config.py](../src/tarel/providers/config.py#L370), [providers/config.py](../src/tarel/providers/config.py#L379), [providers/config.py](../src/tarel/providers/config.py#L389), [providers/config.py](../src/tarel/providers/config.py#L419) |
| `invalid_provider_name` | [providers/authoring.py](../src/tarel/providers/authoring.py#L22), [providers/config.py](../src/tarel/providers/config.py#L342) |
| `invalid_provider_request` | [providers/openai_compatible.py](../src/tarel/providers/openai_compatible.py#L66), [providers/openai_compatible.py](../src/tarel/providers/openai_compatible.py#L74), [providers/openrouter.py](../src/tarel/providers/openrouter.py#L39), [providers/openrouter.py](../src/tarel/providers/openrouter.py#L47) |
| `invalid_provider_response` | [tarel/application.py](../src/tarel/application.py#L481), [discovery/application.py](../src/tarel/discovery/application.py#L705), [discovery/application.py](../src/tarel/discovery/application.py#L713), [discovery/application.py](../src/tarel/discovery/application.py#L721), [providers/openai_compatible.py](../src/tarel/providers/openai_compatible.py#L99), [providers/openrouter.py](../src/tarel/providers/openrouter.py#L78), [providers/openrouter.py](../src/tarel/providers/openrouter.py#L89), [providers/openrouter.py](../src/tarel/providers/openrouter.py#L108), [providers/openrouter.py](../src/tarel/providers/openrouter.py#L135), [providers/openrouter.py](../src/tarel/providers/openrouter.py#L140) |
| `invalid_query` | [ui/query_tools.py](../src/tarel/ui/query_tools.py#L186) |
| `invalid_query_budget` | [ui/query_tools.py](../src/tarel/ui/query_tools.py#L157), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L195) |
| `invalid_query_linked_coverage` | [discovery/application.py](../src/tarel/discovery/application.py#L322), [discovery/application.py](../src/tarel/discovery/application.py#L327), [discovery/application.py](../src/tarel/discovery/application.py#L1555), [discovery/application.py](../src/tarel/discovery/application.py#L1561), [discovery/application.py](../src/tarel/discovery/application.py#L1571), [discovery/application.py](../src/tarel/discovery/application.py#L1587), [discovery/application.py](../src/tarel/discovery/application.py#L1601), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L122), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L318), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L330), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L382), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L391), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L403), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L409), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L416), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L421), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L432), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L436), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L450), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L457), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L466), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L471), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L485), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L492), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L500), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L512), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L520), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L525), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L533), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L541), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L549), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L558), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L567), [discovery/coverage.py](../src/tarel/discovery/coverage.py#L572), [discovery/store.py](../src/tarel/discovery/store.py#L140), [discovery/store.py](../src/tarel/discovery/store.py#L145), [discovery/store.py](../src/tarel/discovery/store.py#L154) |
| `invalid_query_policy` | [ui/query_tools.py](../src/tarel/ui/query_tools.py#L118), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L146), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L151) |
| `invalid_query_request` | [ui/query_tools.py](../src/tarel/ui/query_tools.py#L177), [ui/server.py](../src/tarel/ui/server.py#L432) |
| `invalid_query_scope` | [ui/query_tools.py](../src/tarel/ui/query_tools.py#L56), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L61), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L66), [ui/query_tools.py](../src/tarel/ui/query_tools.py#L68) |
| `invalid_reference_mapping` | [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L356), [reference_mapping/cli.py](../src/tarel/reference_mapping/cli.py#L155), [reference_mapping/cli.py](../src/tarel/reference_mapping/cli.py#L160), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L78), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L94), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L103), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L175), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L267), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L308), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L357), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L367), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L375), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L381), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L391), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L431), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L438), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L446), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L455), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L463), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L471), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L476), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L484), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L496), [reference_mapping/store.py](../src/tarel/reference_mapping/store.py#L77), [reference_mapping/store.py](../src/tarel/reference_mapping/store.py#L82), [reference_mapping/store.py](../src/tarel/reference_mapping/store.py#L88) |
| `invalid_reference_mapping_id` | [reference_mapping/store.py](../src/tarel/reference_mapping/store.py#L110) |
| `invalid_reference_mapping_import` | [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L137) |
| `invalid_reference_mapping_mode` | [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L210) |
| `invalid_relationship` | [tarel/context.py](../src/tarel/context.py#L546), [tarel/context.py](../src/tarel/context.py#L579), [tarel/context.py](../src/tarel/context.py#L590), [tarel/context.py](../src/tarel/context.py#L613) |
| `invalid_relationship_fields` | [relationships/core.py](../src/tarel/relationships/core.py#L123), [relationships/core.py](../src/tarel/relationships/core.py#L132), [relationships/core.py](../src/tarel/relationships/core.py#L139), [relationships/core.py](../src/tarel/relationships/core.py#L147) |
| `invalid_relationship_pair` | [relationships/core.py](../src/tarel/relationships/core.py#L81), [workspaces/core.py](../src/tarel/workspaces/core.py#L168) |
| `invalid_relationship_probe` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L200), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L515) |
| `invalid_relationship_state` | [relationships/core.py](../src/tarel/relationships/core.py#L424), [workspaces/core.py](../src/tarel/workspaces/core.py#L211) |
| `invalid_request` | [ui/server.py](../src/tarel/ui/server.py#L901), [ui/server.py](../src/tarel/ui/server.py#L906), [ui/server.py](../src/tarel/ui/server.py#L958), [ui/server.py](../src/tarel/ui/server.py#L1118), [ui/server.py](../src/tarel/ui/server.py#L1139), [ui/server.py](../src/tarel/ui/server.py#L1147), [ui/server.py](../src/tarel/ui/server.py#L1154), [ui/server.py](../src/tarel/ui/server.py#L1163), [ui/server.py](../src/tarel/ui/server.py#L1170), [ui/server.py](../src/tarel/ui/server.py#L1184) |
| `invalid_response` | [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L263) |
| `invalid_retrieval_mode` | [retrieval/index.py](../src/tarel/retrieval/index.py#L306) |
| `invalid_runtime_lineage` | [lineage/runtime.py](../src/tarel/lineage/runtime.py#L64), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L133), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L138), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L147), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L155), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L163), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L230), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L244), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L252), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L260), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L401), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L417), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L504), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L509), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L522), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L530), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L542), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L618), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L623), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L635), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L646), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L700), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L704), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L991), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1076), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1111), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1117), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1134), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1139), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1146), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1172), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1196), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1209), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1215), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1241), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1247), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1256), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1261), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1272), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1288), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1296), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1302), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1308), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1314), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1323), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1332), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1341), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1347), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1357), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1366), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1375), [lineage/runtime_logical.py](../src/tarel/lineage/runtime_logical.py#L133), [lineage/runtime_logical.py](../src/tarel/lineage/runtime_logical.py#L145), [lineage/runtime_logical.py](../src/tarel/lineage/runtime_logical.py#L155), [lineage/runtime_logical.py](../src/tarel/lineage/runtime_logical.py#L160), [lineage/runtime_logical.py](../src/tarel/lineage/runtime_logical.py#L167), [lineage/runtime_store.py](../src/tarel/lineage/runtime_store.py#L79), [lineage/runtime_store.py](../src/tarel/lineage/runtime_store.py#L84), [lineage/runtime_store.py](../src/tarel/lineage/runtime_store.py#L90) |
| `invalid_runtime_lineage_graph` | [lineage/application.py](../src/tarel/lineage/application.py#L384) |
| `invalid_runtime_lineage_name` | [lineage/runtime_store.py](../src/tarel/lineage/runtime_store.py#L105) |
| `invalid_sample_limit` | [tarel/application.py](../src/tarel/application.py#L1869), [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L97), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L345), [sources/application.py](../src/tarel/sources/application.py#L247) |
| `invalid_schema_reference` | [workspaces/core.py](../src/tarel/workspaces/core.py#L244), [workspaces/scope.py](../src/tarel/workspaces/scope.py#L236) |
| `invalid_semantic_concept_mode` | [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L190) |
| `invalid_semantic_concept_query` | [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L144), [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L195), [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L216) |
| `invalid_semantic_concepts` | [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L70), [semantic_concepts/cli.py](../src/tarel/semantic_concepts/cli.py#L107), [semantic_concepts/cli.py](../src/tarel/semantic_concepts/cli.py#L109), [semantic_concepts/contracts.py](../src/tarel/semantic_concepts/contracts.py#L240), [semantic_concepts/store.py](../src/tarel/semantic_concepts/store.py#L53), [semantic_concepts/store.py](../src/tarel/semantic_concepts/store.py#L58), [semantic_concepts/store.py](../src/tarel/semantic_concepts/store.py#L64) |
| `invalid_semantic_concepts_import` | [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L100) |
| `invalid_semantic_concepts_path` | [semantic_concepts/store.py](../src/tarel/semantic_concepts/store.py#L78), [semantic_concepts/store.py](../src/tarel/semantic_concepts/store.py#L86), [semantic_concepts/store.py](../src/tarel/semantic_concepts/store.py#L91) |
| `invalid_semantic_edit` | [semantics/application.py](../src/tarel/semantics/application.py#L132), [semantics/application.py](../src/tarel/semantics/application.py#L137), [semantics/application.py](../src/tarel/semantics/application.py#L174), [semantics/application.py](../src/tarel/semantics/application.py#L179), [semantics/application.py](../src/tarel/semantics/application.py#L187), [semantics/application.py](../src/tarel/semantics/application.py#L196), [semantics/application.py](../src/tarel/semantics/application.py#L202) |
| `invalid_semantic_import` | [semantics/contracts.py](../src/tarel/semantics/contracts.py#L396), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L432), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L434), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L439), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L468), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L478), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L484), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L489), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L556), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L570), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L578), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L592), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L603), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L612), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L623), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L634), [semantics/store.py](../src/tarel/semantics/store.py#L73), [semantics/store.py](../src/tarel/semantics/store.py#L78), [semantics/store.py](../src/tarel/semantics/store.py#L84) |
| `invalid_semantic_import_name` | [semantics/contracts.py](../src/tarel/semantics/contracts.py#L427) |
| `invalid_semantic_snapshot` | [semantics/contracts.py](../src/tarel/semantics/contracts.py#L445) |
| `invalid_semantic_source` | [semantics/source.py](../src/tarel/semantics/source.py#L127) |
| `invalid_semantic_source_bundle` | [semantics/source.py](../src/tarel/semantics/source.py#L53) |
| `invalid_session` | [ui/server.py](../src/tarel/ui/server.py#L947) |
| `invalid_small_domain_limit` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L382), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L797) |
| `invalid_sml` | [semantics/sml.py](../src/tarel/semantics/sml.py#L390), [semantics/sml.py](../src/tarel/semantics/sml.py#L396), [semantics/sml.py](../src/tarel/semantics/sml.py#L404), [semantics/sml.py](../src/tarel/semantics/sml.py#L410), [semantics/sml.py](../src/tarel/semantics/sml.py#L416), [semantics/sml.py](../src/tarel/semantics/sml.py#L419), [semantics/sml.py](../src/tarel/semantics/sml.py#L425) |
| `invalid_source` | [sources/contracts.py](../src/tarel/sources/contracts.py#L131), [sources/contracts.py](../src/tarel/sources/contracts.py#L133), [sources/contracts.py](../src/tarel/sources/contracts.py#L135), [sources/contracts.py](../src/tarel/sources/contracts.py#L137), [sources/contracts.py](../src/tarel/sources/contracts.py#L163), [sources/contracts.py](../src/tarel/sources/contracts.py#L202), [sources/contracts.py](../src/tarel/sources/contracts.py#L210), [sources/contracts.py](../src/tarel/sources/contracts.py#L216), [sources/store.py](../src/tarel/sources/store.py#L60), [sources/store.py](../src/tarel/sources/store.py#L62) |
| `invalid_source_name` | [sources/contracts.py](../src/tarel/sources/contracts.py#L126) |
| `invalid_stale_claim` | [graph/refresh.py](../src/tarel/graph/refresh.py#L330) |
| `invalid_threshold` | [relationships/core.py](../src/tarel/relationships/core.py#L292), [relationships/core.py](../src/tarel/relationships/core.py#L294), [relationships/core.py](../src/tarel/relationships/core.py#L296) |
| `invalid_url` | [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L610), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L623) |
| `invalid_workspace` | [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L99), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L276), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L299), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L309), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L332), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L342), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L358), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L363), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L375), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L381), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L390), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L401), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L416), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L426), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L443), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L453), [workspaces/store.py](../src/tarel/workspaces/store.py#L70), [workspaces/store.py](../src/tarel/workspaces/store.py#L75) |
| `invalid_workspace_identifier` | [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L435) |
| `invalid_workspace_name` | [workspaces/store.py](../src/tarel/workspaces/store.py#L94) |
| `invalid_workspace_scope` | [tarel/cli.py](../src/tarel/cli.py#L1837), [tarel/cli.py](../src/tarel/cli.py#L1888), [tarel/cli.py](../src/tarel/cli.py#L1932), [tarel/cli.py](../src/tarel/cli.py#L1971) |
| `invalid_write_coverage` | [lineage/core.py](../src/tarel/lineage/core.py#L652) |
| `knowledge_document_too_large` | [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L271) |
| `knowledge_exists` | [tarel/application.py](../src/tarel/application.py#L1520) |
| `knowledge_graph_outside_workspace` | [tarel/application.py](../src/tarel/application.py#L2036) |
| `knowledge_not_found` | [knowledge/core.py](../src/tarel/knowledge/core.py#L45), [knowledge/store.py](../src/tarel/knowledge/store.py#L63) |
| `knowledge_save_failed` | [knowledge/store.py](../src/tarel/knowledge/store.py#L52) |
| `knowledge_scope_not_found` | [tarel/application.py](../src/tarel/application.py#L1990), [tarel/application.py](../src/tarel/application.py#L2015) |
| `knowledge_source_not_found` | [tarel/application.py](../src/tarel/application.py#L1533) |
| `knowledge_workspace_required` | [tarel/application.py](../src/tarel/application.py#L1981) |
| `lineage_analysis_cache_save_failed` | [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L188) |
| `lineage_change_report_conflict` | [lineage/change_store.py](../src/tarel/lineage/change_store.py#L27) |
| `lineage_change_report_not_found` | [lineage/change_store.py](../src/tarel/lineage/change_store.py#L64) |
| `lineage_change_report_save_failed` | [lineage/change_store.py](../src/tarel/lineage/change_store.py#L48) |
| `lineage_input_not_found` | [lineage/source.py](../src/tarel/lineage/source.py#L146) |
| `lineage_item_not_found` | [lineage/review.py](../src/tarel/lineage/review.py#L66) |
| `lineage_not_found` | [lineage/application.py](../src/tarel/lineage/application.py#L833), [lineage/store.py](../src/tarel/lineage/store.py#L62) |
| `lineage_reference_not_found` | [lineage/traversal.py](../src/tarel/lineage/traversal.py#L688) |
| `lineage_refresh_mismatch` | [lineage/refresh.py](../src/tarel/lineage/refresh.py#L212) |
| `lineage_required` | [ui/server.py](../src/tarel/ui/server.py#L531) |
| `lineage_save_failed` | [lineage/store.py](../src/tarel/lineage/store.py#L52) |
| `lineage_source_changed` | [lineage/tasks.py](../src/tarel/lineage/tasks.py#L232) |
| `logical_endpoint_not_found` | [topology/endpoints.py](../src/tarel/topology/endpoints.py#L44), [topology/endpoints.py](../src/tarel/topology/endpoints.py#L88), [topology/endpoints.py](../src/tarel/topology/endpoints.py#L97), [topology/endpoints.py](../src/tarel/topology/endpoints.py#L123), [topology/endpoints.py](../src/tarel/topology/endpoints.py#L214), [topology/endpoints.py](../src/tarel/topology/endpoints.py#L243) |
| `logical_endpoint_policy_excluded` | [topology/endpoints.py](../src/tarel/topology/endpoints.py#L141), [topology/endpoints.py](../src/tarel/topology/endpoints.py#L279) |
| `logical_join_already_reviewed` | [logical_joins/application.py](../src/tarel/logical_joins/application.py#L157) |
| `logical_join_exists` | [logical_joins/application.py](../src/tarel/logical_joins/application.py#L118) |
| `logical_join_not_found` | [logical_joins/store.py](../src/tarel/logical_joins/store.py#L35) |
| `logical_join_review_conflict` | [logical_joins/application.py](../src/tarel/logical_joins/application.py#L171) |
| `logical_join_save_failed` | [logical_joins/store.py](../src/tarel/logical_joins/store.py#L63) |
| `logical_metadata_object_not_found` | [ui/logical_metadata.py](../src/tarel/ui/logical_metadata.py#L189) |
| `logical_metadata_object_outside_scope` | [ui/logical_metadata.py](../src/tarel/ui/logical_metadata.py#L197) |
| `logical_metadata_policy_excluded` | [ui/logical_metadata.py](../src/tarel/ui/logical_metadata.py#L207) |
| `logical_topology_cross_object_step` | [topology/application.py](../src/tarel/topology/application.py#L255) |
| `logical_topology_endpoint_not_found` | [topology/application.py](../src/tarel/topology/application.py#L234), [topology/application.py](../src/tarel/topology/application.py#L250) |
| `logical_topology_graph_rebase_forbidden` | [topology/application.py](../src/tarel/topology/application.py#L69) |
| `logical_topology_graph_revision_mismatch` | [topology/application.py](../src/tarel/topology/application.py#L225) |
| `logical_topology_not_found` | [topology/store.py](../src/tarel/topology/store.py#L75) |
| `logical_topology_passthrough_schema_mismatch` | [topology/application.py](../src/tarel/topology/application.py#L266) |
| `logical_topology_save_failed` | [topology/store.py](../src/tarel/topology/store.py#L62) |
| `logical_topology_source_not_found` | [topology/cli.py](../src/tarel/topology/cli.py#L86) |
| `manual_hop_exists` | [lineage/manual.py](../src/tarel/lineage/manual.py#L177) |
| `manual_job_exists` | [lineage/manual.py](../src/tarel/lineage/manual.py#L72) |
| `manual_overlay_required` | [lineage/manual.py](../src/tarel/lineage/manual.py#L233) |
| `mapping_manifest_required` | [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1632) |
| `missing_annotation_review_reason` | [annotations/review.py](../src/tarel/annotations/review.py#L330) |
| `missing_api_key` | [tarel/application.py](../src/tarel/application.py#L425), [tarel/cli.py](../src/tarel/cli.py#L2764), [providers/config.py](../src/tarel/providers/config.py#L126) |
| `missing_config` | [tarel/application.py](../src/tarel/application.py#L2120) |
| `missing_database` | [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L618) |
| `missing_dependency` | [connectors/host.py](../src/tarel/connectors/host.py#L100), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L226), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L284), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L350), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L429), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L528) |
| `missing_embedding_backend` | [lineage/traversal.py](../src/tarel/lineage/traversal.py#L163), [retrieval/index.py](../src/tarel/retrieval/index.py#L328) |
| `missing_focus_sources` | [tarel/application.py](../src/tarel/application.py#L602) |
| `missing_lineage_scope` | [tarel/grounding_application.py](../src/tarel/grounding_application.py#L248) |
| `missing_local_rag_dependency` | [retrieval/local.py](../src/tarel/retrieval/local.py#L194) |
| `missing_provider_adapter` | [tarel/application.py](../src/tarel/application.py#L414) |
| `missing_relationship_reason` | [relationships/core.py](../src/tarel/relationships/core.py#L116), [relationships/core.py](../src/tarel/relationships/core.py#L426), [workspaces/core.py](../src/tarel/workspaces/core.py#L161), [workspaces/core.py](../src/tarel/workspaces/core.py#L216) |
| `model_checksum_mismatch` | [retrieval/local.py](../src/tarel/retrieval/local.py#L111), [retrieval/local.py](../src/tarel/retrieval/local.py#L139) |
| `model_download_failed` | [retrieval/local.py](../src/tarel/retrieval/local.py#L149) |
| `model_index_mismatch` | [lineage/traversal.py](../src/tarel/lineage/traversal.py#L289), [retrieval/index.py](../src/tarel/retrieval/index.py#L202), [retrieval/index.py](../src/tarel/retrieval/index.py#L360) |
| `model_not_found` | [retrieval/local.py](../src/tarel/retrieval/local.py#L88) |
| `namespace_not_found` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L264) |
| `no_profile_fields` | [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L458) |
| `no_sample_fields` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L111), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L373) |
| `object_binding_exists` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L73) |
| `object_binding_not_found` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L97) |
| `object_binding_policy_excluded` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L199) |
| `object_binding_review_final` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L116) |
| `object_binding_review_required` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L64) |
| `object_binding_save_failed` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L303) |
| `object_family_already_reviewed` | [object_families/contracts.py](../src/tarel/object_families/contracts.py#L258) |
| `object_family_attribute_mismatch` | [object_families/application.py](../src/tarel/object_families/application.py#L478), [object_families/application.py](../src/tarel/object_families/application.py#L485) |
| `object_family_exists` | [object_families/application.py](../src/tarel/object_families/application.py#L200) |
| `object_family_graph_revision_mismatch` | [object_families/application.py](../src/tarel/object_families/application.py#L151), [object_families/application.py](../src/tarel/object_families/application.py#L409) |
| `object_family_list_failed` | [object_families/store.py](../src/tarel/object_families/store.py#L89) |
| `object_family_member_not_found` | [object_families/application.py](../src/tarel/object_families/application.py#L105), [object_families/application.py](../src/tarel/object_families/application.py#L167), [topology/endpoints.py](../src/tarel/topology/endpoints.py#L184) |
| `object_family_not_found` | [object_families/cli.py](../src/tarel/object_families/cli.py#L103), [object_families/store.py](../src/tarel/object_families/store.py#L61) |
| `object_family_overlap` | [object_families/application.py](../src/tarel/object_families/application.py#L158), [object_families/application.py](../src/tarel/object_families/application.py#L212), [ui/lazy_family_view.py](../src/tarel/ui/lazy_family_view.py#L195), [ui/presentation.py](../src/tarel/ui/presentation.py#L447) |
| `object_family_policy_excluded` | [object_families/application.py](../src/tarel/object_families/application.py#L356) |
| `object_family_save_failed` | [object_families/store.py](../src/tarel/object_families/store.py#L51) |
| `object_family_schema_mismatch` | [object_families/application.py](../src/tarel/object_families/application.py#L176), [object_families/application.py](../src/tarel/object_families/application.py#L420) |
| `object_family_schema_unavailable` | [object_families/application.py](../src/tarel/object_families/application.py#L455), [object_families/application.py](../src/tarel/object_families/application.py#L460), [topology/endpoints.py](../src/tarel/topology/endpoints.py#L195) |
| `object_family_source_unreadable` | [object_families/cli.py](../src/tarel/object_families/cli.py#L139) |
| `object_not_found` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L339), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L451), [workspaces/core.py](../src/tarel/workspaces/core.py#L396) |
| `object_outside_focus` | [relationships/core.py](../src/tarel/relationships/core.py#L209) |
| `optional_metadata_too_large` | [ui/optional_metadata.py](../src/tarel/ui/optional_metadata.py#L157) |
| `optional_object_outside_scope` | [ui/optional_metadata.py](../src/tarel/ui/optional_metadata.py#L67), [ui/server.py](../src/tarel/ui/server.py#L334) |
| `profiling_failed` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L180), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L468), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L487), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L878) |
| `proposal_not_found` | [tarel/cli.py](../src/tarel/cli.py#L3197) |
| `provider_http_error` | [providers/openai_compatible.py](../src/tarel/providers/openai_compatible.py#L92), [providers/openrouter.py](../src/tarel/providers/openrouter.py#L71) |
| `provider_not_configured` | [providers/config.py](../src/tarel/providers/config.py#L77), [providers/config.py](../src/tarel/providers/config.py#L153), [providers/config.py](../src/tarel/providers/config.py#L169), [providers/config.py](../src/tarel/providers/config.py#L257), [providers/host.py](../src/tarel/providers/host.py#L27) |
| `provider_unavailable` | [providers/openai_compatible.py](../src/tarel/providers/openai_compatible.py#L97), [providers/openrouter.py](../src/tarel/providers/openrouter.py#L76) |
| `query_linked_coverage_binding_mismatch` | [discovery/application.py](../src/tarel/discovery/application.py#L342), [discovery/application.py](../src/tarel/discovery/application.py#L1527), [discovery/application.py](../src/tarel/discovery/application.py#L1580) |
| `query_linked_coverage_exists` | [discovery/application.py](../src/tarel/discovery/application.py#L355) |
| `query_linked_coverage_not_found` | [discovery/store.py](../src/tarel/discovery/store.py#L135) |
| `query_linked_reference_not_found` | [discovery/application.py](../src/tarel/discovery/application.py#L1510), [discovery/application.py](../src/tarel/discovery/application.py#L1522), [discovery/application.py](../src/tarel/discovery/application.py#L1536) |
| `query_revision_required` | [ui/query_tools.py](../src/tarel/ui/query_tools.py#L212) |
| `raw_samples_not_allowed` | [sources/application.py](../src/tarel/sources/application.py#L252) |
| `read_only` | [ui/server.py](../src/tarel/ui/server.py#L745) |
| `reference_mapping_already_reviewed` | [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L406) |
| `reference_mapping_exists` | [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L152) |
| `reference_mapping_field_not_found` | [tarel/context_hints_application.py](../src/tarel/context_hints_application.py#L255), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L375), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L391), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L404), [ui/presentation.py](../src/tarel/ui/presentation.py#L1170), [ui/presentation.py](../src/tarel/ui/presentation.py#L1184) |
| `reference_mapping_graph_revision_mismatch` | [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L347), [ui/presentation.py](../src/tarel/ui/presentation.py#L1158) |
| `reference_mapping_not_found` | [reference_mapping/store.py](../src/tarel/reference_mapping/store.py#L72) |
| `reference_mapping_review_conflict` | [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L233), [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L289) |
| `reference_mapping_save_failed` | [reference_mapping/store.py](../src/tarel/reference_mapping/store.py#L59) |
| `reference_mapping_source_not_found` | [reference_mapping/cli.py](../src/tarel/reference_mapping/cli.py#L150) |
| `refresh_mismatch` | [graph/refresh.py](../src/tarel/graph/refresh.py#L154), [graph/refresh.py](../src/tarel/graph/refresh.py#L156) |
| `relationship_exists` | [relationships/core.py](../src/tarel/relationships/core.py#L567), [workspaces/core.py](../src/tarel/workspaces/core.py#L177) |
| `relationship_field_not_found` | [workspaces/core.py](../src/tarel/workspaces/core.py#L372), [workspaces/projection.py](../src/tarel/workspaces/projection.py#L144) |
| `relationship_not_found` | [relationships/core.py](../src/tarel/relationships/core.py#L439), [workspaces/core.py](../src/tarel/workspaces/core.py#L225) |
| `relationship_object_not_found` | [workspaces/core.py](../src/tarel/workspaces/core.py#L360) |
| `relationship_probe_failed` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L218), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L552), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L570) |
| `request_too_large` | [ui/server.py](../src/tarel/ui/server.py#L955) |
| `reviewed_annotation` | [annotations/apply.py](../src/tarel/annotations/apply.py#L61) |
| `reviewed_lineage_item` | [lineage/core.py](../src/tarel/lineage/core.py#L265) |
| `route_not_found` | [ui/server.py](../src/tarel/ui/server.py#L645), [ui/server.py](../src/tarel/ui/server.py#L741) |
| `runtime_call_not_evidence` | [lineage/application.py](../src/tarel/lineage/application.py#L236) |
| `runtime_call_not_found` | [lineage/application.py](../src/tarel/lineage/application.py#L231) |
| `runtime_graph_revision_mismatch` | [lineage/application.py](../src/tarel/lineage/application.py#L193) |
| `runtime_input_not_found` | [lineage/application.py](../src/tarel/lineage/application.py#L363) |
| `runtime_lineage_exists` | [lineage/runtime_store.py](../src/tarel/lineage/runtime_store.py#L28), [lineage/runtime_store.py](../src/tarel/lineage/runtime_store.py#L53) |
| `runtime_lineage_input_not_found` | [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1071) |
| `runtime_lineage_not_found` | [lineage/runtime_store.py](../src/tarel/lineage/runtime_store.py#L74) |
| `runtime_lineage_save_failed` | [lineage/runtime_store.py](../src/tarel/lineage/runtime_store.py#L64) |
| `sample_value_echoed` | [annotations/runner.py](../src/tarel/annotations/runner.py#L229) |
| `sampling_failed` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L130), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L397) |
| `scaffold_failed` | [connectors/authoring.py](../src/tarel/connectors/authoring.py#L40), [providers/authoring.py](../src/tarel/providers/authoring.py#L41) |
| `schema_in_multiple_areas` | [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L323) |
| `schema_not_found` | [workspaces/core.py](../src/tarel/workspaces/core.py#L320), [workspaces/scope.py](../src/tarel/workspaces/scope.py#L251) |
| `semantic_concept_already_reviewed` | [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L155) |
| `semantic_concept_not_found` | [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L153) |
| `semantic_concept_policy_excluded` | [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L114), [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L163) |
| `semantic_concepts_graph_revision_mismatch` | [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L340) |
| `semantic_concepts_not_found` | [semantic_concepts/store.py](../src/tarel/semantic_concepts/store.py#L48) |
| `semantic_concepts_rebase_forbidden` | [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L84) |
| `semantic_concepts_save_failed` | [semantic_concepts/store.py](../src/tarel/semantic_concepts/store.py#L37) |
| `semantic_concepts_source_not_found` | [semantic_concepts/cli.py](../src/tarel/semantic_concepts/cli.py#L54) |
| `semantic_edit_no_change` | [semantics/application.py](../src/tarel/semantics/application.py#L145) |
| `semantic_edit_reason_required` | [semantics/application.py](../src/tarel/semantics/application.py#L129) |
| `semantic_import_exists` | [semantics/application.py](../src/tarel/semantics/application.py#L68) |
| `semantic_import_graph_mismatch` | [semantics/application.py](../src/tarel/semantics/application.py#L60) |
| `semantic_import_has_edits` | [semantics/application.py](../src/tarel/semantics/application.py#L74) |
| `semantic_import_not_found` | [semantics/store.py](../src/tarel/semantics/store.py#L68) |
| `semantic_import_outside_scope` | [ui/server.py](../src/tarel/ui/server.py#L556) |
| `semantic_import_save_failed` | [semantics/store.py](../src/tarel/semantics/store.py#L58) |
| `semantic_patch_not_found` | [semantics/application.py](../src/tarel/semantics/application.py#L169) |
| `semantic_source_empty` | [semantics/source.py](../src/tarel/semantics/source.py#L92) |
| `semantic_source_not_found` | [semantics/source.py](../src/tarel/semantics/source.py#L87) |
| `semantic_source_read_failed` | [semantics/source.py](../src/tarel/semantics/source.py#L132) |
| `semantic_source_too_large` | [semantics/source.py](../src/tarel/semantics/source.py#L97), [semantics/source.py](../src/tarel/semantics/source.py#L113) |
| `semantic_target_not_found` | [semantics/contracts.py](../src/tarel/semantics/contracts.py#L504), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L521) |
| `semantic_yaml_unavailable` | [semantics/structured.py](../src/tarel/semantics/structured.py#L54) |
| `small_domain_values_without_profile` | [tarel/application.py](../src/tarel/application.py#L1881) |
| `source_config_not_resolved` | [sources/application.py](../src/tarel/sources/application.py#L394) |
| `source_exists` | [sources/application.py](../src/tarel/sources/application.py#L121) |
| `source_graph_mismatch` | [tarel/grounding_application.py](../src/tarel/grounding_application.py#L385), [sources/application.py](../src/tarel/sources/application.py#L216), [sources/application.py](../src/tarel/sources/application.py#L341), [sources/application.py](../src/tarel/sources/application.py#L359) |
| `source_graph_not_mapped` | [tarel/grounding_application.py](../src/tarel/grounding_application.py#L377), [sources/application.py](../src/tarel/sources/application.py#L354) |
| `source_not_found` | [sources/store.py](../src/tarel/sources/store.py#L58) |
| `source_save_failed` | [sources/store.py](../src/tarel/sources/store.py#L47) |
| `stale_discovery_run` | [discovery/application.py](../src/tarel/discovery/application.py#L404), [discovery/application.py](../src/tarel/discovery/application.py#L667) |
| `stale_entity_resolution_candidate` | [entity_resolution/application.py](../src/tarel/entity_resolution/application.py#L256) |
| `stale_expansion_base` | [expansion/application.py](../src/tarel/expansion/application.py#L153), [expansion/application.py](../src/tarel/expansion/application.py#L178), [expansion/projections.py](../src/tarel/expansion/projections.py#L233) |
| `stale_expansion_target` | [expansion/projections.py](../src/tarel/expansion/projections.py#L276) |
| `stale_family_proposal_request` | [object_families/proposals.py](../src/tarel/object_families/proposals.py#L233) |
| `stale_family_proposals` | [object_families/proposals.py](../src/tarel/object_families/proposals.py#L213) |
| `stale_graph` | [ui/server.py](../src/tarel/ui/server.py#L752) |
| `stale_index` | [retrieval/index.py](../src/tarel/retrieval/index.py#L197) |
| `stale_index_checkpoint` | [retrieval/index.py](../src/tarel/retrieval/index.py#L512) |
| `stale_knowledge_reference` | [tarel/application.py](../src/tarel/application.py#L2060) |
| `stale_lineage` | [lineage/application.py](../src/tarel/lineage/application.py#L820) |
| `stale_lineage_proposal` | [lineage/core.py](../src/tarel/lineage/core.py#L231) |
| `stale_logical_endpoint` | [topology/endpoints.py](../src/tarel/topology/endpoints.py#L129), [topology/endpoints.py](../src/tarel/topology/endpoints.py#L271) |
| `stale_logical_join` | [logical_joins/application.py](../src/tarel/logical_joins/application.py#L155), [logical_joins/application.py](../src/tarel/logical_joins/application.py#L257) |
| `stale_logical_metadata_scope` | [ui/server.py](../src/tarel/ui/server.py#L461) |
| `stale_logical_topology` | [topology/application.py](../src/tarel/topology/application.py#L64), [topology/application.py](../src/tarel/topology/application.py#L76), [topology/application.py](../src/tarel/topology/application.py#L111) |
| `stale_object_binding` | [object_bindings/application.py](../src/tarel/object_bindings/application.py#L274) |
| `stale_object_family` | [object_families/application.py](../src/tarel/object_families/application.py#L500) |
| `stale_object_family_scope` | [ui/server.py](../src/tarel/ui/server.py#L510) |
| `stale_optional_scope` | [ui/server.py](../src/tarel/ui/server.py#L330) |
| `stale_proposal` | [annotations/apply.py](../src/tarel/annotations/apply.py#L29) |
| `stale_query_scope` | [ui/query_tools.py](../src/tarel/ui/query_tools.py#L227) |
| `stale_reference_mapping_candidate` | [reference_mapping/application.py](../src/tarel/reference_mapping/application.py#L272) |
| `stale_semantic_concepts` | [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L79), [semantic_concepts/application.py](../src/tarel/semantic_concepts/application.py#L147) |
| `stale_semantic_import` | [semantics/application.py](../src/tarel/semantics/application.py#L124) |
| `stale_workspace` | [ui/server.py](../src/tarel/ui/server.py#L813) |
| `system_not_found` | [workspaces/core.py](../src/tarel/workspaces/core.py#L254), [workspaces/scope.py](../src/tarel/workspaces/scope.py#L189) |
| `target_exists` | [connectors/authoring.py](../src/tarel/connectors/authoring.py#L30), [providers/authoring.py](../src/tarel/providers/authoring.py#L32) |
| `target_not_found` | [annotations/tasks.py](../src/tarel/annotations/tasks.py#L87) |
| `ui_operation_failed` | [ui/server.py](../src/tarel/ui/server.py#L1119) |
| `ui_source_required` | [ui/server.py](../src/tarel/ui/server.py#L779), [ui/server.py](../src/tarel/ui/server.py#L1032) |
| `unknown_demo` | [tarel/application.py](../src/tarel/application.py#L270) |
| `unknown_model` | [retrieval/local.py](../src/tarel/retrieval/local.py#L78) |
| `unsafe_manifest` | [connectors/contracts.py](../src/tarel/connectors/contracts.py#L70) |
| `unsafe_semantic_source` | [semantics/source.py](../src/tarel/semantics/source.py#L67), [semantics/source.py](../src/tarel/semantics/source.py#L106) |
| `unsupported_agent_setup` | [tarel/agents.py](../src/tarel/agents.py#L31) |
| `unsupported_annotation_filter` | [retrieval/index.py](../src/tarel/retrieval/index.py#L310) |
| `unsupported_capability` | [tarel/application.py](../src/tarel/application.py#L363), [tarel/application.py](../src/tarel/application.py#L2100) |
| `unsupported_change_report` | [graph/refresh.py](../src/tarel/graph/refresh.py#L123) |
| `unsupported_context_packet` | [tarel/context_packets.py](../src/tarel/context_packets.py#L133) |
| `unsupported_contract` | [connectors/contracts.py](../src/tarel/connectors/contracts.py#L55) |
| `unsupported_discovery` | [discovery/contracts.py](../src/tarel/discovery/contracts.py#L894), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1096), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1103), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1111), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1119), [discovery/contracts.py](../src/tarel/discovery/contracts.py#L1123) |
| `unsupported_discovery_promotion` | [discovery/application.py](../src/tarel/discovery/application.py#L567) |
| `unsupported_entity_resolution` | [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L268), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L475), [entity_resolution/contracts.py](../src/tarel/entity_resolution/contracts.py#L656) |
| `unsupported_focus` | [focus/contracts.py](../src/tarel/focus/contracts.py#L124) |
| `unsupported_graph` | [graph/contracts.py](../src/tarel/graph/contracts.py#L204) |
| `unsupported_index` | [retrieval/index.py](../src/tarel/retrieval/index.py#L186) |
| `unsupported_knowledge` | [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L136), [knowledge/contracts.py](../src/tarel/knowledge/contracts.py#L252) |
| `unsupported_knowledge_format` | [tarel/application.py](../src/tarel/application.py#L1526) |
| `unsupported_lineage` | [lineage/contracts.py](../src/tarel/lineage/contracts.py#L286) |
| `unsupported_lineage_analysis_cache` | [lineage/analysis_cache.py](../src/tarel/lineage/analysis_cache.py#L131) |
| `unsupported_lineage_change` | [lineage/refresh.py](../src/tarel/lineage/refresh.py#L174) |
| `unsupported_lineage_input` | [lineage/source.py](../src/tarel/lineage/source.py#L156) |
| `unsupported_logical_topology` | [topology/contracts.py](../src/tarel/topology/contracts.py#L498), [topology/contracts.py](../src/tarel/topology/contracts.py#L657) |
| `unsupported_object_family` | [object_families/contracts.py](../src/tarel/object_families/contracts.py#L207) |
| `unsupported_query_linked_coverage` | [discovery/coverage.py](../src/tarel/discovery/coverage.py#L313) |
| `unsupported_reference_mapping` | [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L259), [reference_mapping/contracts.py](../src/tarel/reference_mapping/contracts.py#L347) |
| `unsupported_runtime_lineage` | [lineage/runtime.py](../src/tarel/lineage/runtime.py#L694), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L983), [lineage/runtime.py](../src/tarel/lineage/runtime.py#L1100) |
| `unsupported_semantic_format` | [semantics/readers.py](../src/tarel/semantics/readers.py#L25) |
| `unsupported_semantic_import` | [semantics/contracts.py](../src/tarel/semantics/contracts.py#L390), [semantics/contracts.py](../src/tarel/semantics/contracts.py#L422) |
| `unsupported_source` | [sources/contracts.py](../src/tarel/sources/contracts.py#L79) |
| `unsupported_url` | [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L236), [sqlite/connector.py](../src/tarel/connectors/sqlite/connector.py#L245), [sqlserver/connector.py](../src/tarel/connectors/sqlserver/connector.py#L605) |
| `unsupported_workspace` | [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L235), [workspaces/contracts.py](../src/tarel/workspaces/contracts.py#L263) |
| `workspace_exists` | [tarel/application.py](../src/tarel/application.py#L658) |
| `workspace_not_found` | [workspaces/store.py](../src/tarel/workspaces/store.py#L65) |
| `workspace_required` | [ui/server.py](../src/tarel/ui/server.py#L761) |
| `workspace_save_failed` | [workspaces/store.py](../src/tarel/workspaces/store.py#L54) |
| `zone_member_not_found` | [workspaces/core.py](../src/tarel/workspaces/core.py#L330) |
| `zone_not_found` | [workspaces/core.py](../src/tarel/workspaces/core.py#L272) |
| `zone_object_not_found` | [ui/server.py](../src/tarel/ui/server.py#L917) |
| `zone_schema_unassigned` | [workspaces/core.py](../src/tarel/workspaces/core.py#L337) |

## Python SDK

The SDK calls the same application use cases as the CLI. It returns typed Python records and raises domain exceptions; it does not invoke CLI subprocesses. Select the state directory explicitly. Creating the client alone does not discover a source, download a model, or call a provider.

```python
from tarel.sdk import Tarel

tarel = Tarel("/srv/my-harness/.tarel")
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

#### SDK context

```python
tarel.context.diff(left: 'str | Path', right: 'str | Path') -> 'ContextPacketDiff'
```
```python
tarel.context.expand(packet: 'ContextResult | ContextPacketSnapshot | dict[str, object]', targets: 'tuple[ExpansionTarget, ...]', *, mode: 'str' = 'confirmed_only', inputs: 'Mapping[str, ExpansionInput] | None' = None, max_characters: 'int' = 24000) -> 'ContextExpansion'
```
```python
tarel.context.graph(name: 'str', query: 'str', *, namespace: 'str | None' = None, seed_limit: 'int' = 3, max_objects: 'int' = 10, max_joins: 'int' = 12, max_hops: 'int' = 2, max_fields_per_object: 'int' = 12, max_characters: 'int' = 24000, mode: 'str' = 'lexical', model_path: 'str | Path | None' = None, n_threads: 'int | None' = None, annotation_states: 'frozenset[str] | None' = None, validated_only: 'bool' = False, logical_hints: 'str | None' = None) -> 'ContextResult'
```
```python
tarel.context.impact(packet: 'str | Path', *, graph: 'str') -> 'ContextPacketImpact'
```
```python
tarel.context.prefix_graph(name: 'str', *, namespace: 'str | None' = None, max_objects: 'int' = 250, max_joins: 'int' = 500, max_fields_per_object: 'int' = 50, max_characters: 'int' = 500000, annotation_states: 'frozenset[str] | None' = None, validated_only: 'bool' = False, logical_hints: 'str | None' = None) -> 'ContextResult'
```
```python
tarel.context.prefix_workspace(name: 'str', *, selection: 'ScopeSelection | None' = None, systems: 'tuple[str, ...]' = (), graphs: 'tuple[str, ...]' = (), areas: 'tuple[str, ...]' = (), schemas: 'tuple[str, ...]' = (), zones: 'tuple[str, ...]' = (), max_objects: 'int' = 250, max_joins: 'int' = 500, max_fields_per_object: 'int' = 50, max_characters: 'int' = 500000, annotation_states: 'frozenset[str] | None' = None, validated_only: 'bool' = False, logical_hints: 'str | None' = None) -> 'ContextResult'
```
```python
tarel.context.split(packet: 'ContextResult') -> 'ContextCacheParts'
```
```python
tarel.context.workspace(name: 'str', query: 'str', *, selection: 'ScopeSelection | None' = None, systems: 'tuple[str, ...]' = (), graphs: 'tuple[str, ...]' = (), areas: 'tuple[str, ...]' = (), schemas: 'tuple[str, ...]' = (), zones: 'tuple[str, ...]' = (), seed_limit: 'int' = 3, max_objects: 'int' = 10, max_joins: 'int' = 12, max_hops: 'int' = 2, max_fields_per_object: 'int' = 12, max_characters: 'int' = 24000, mode: 'str' = 'lexical', model_path: 'str | Path | None' = None, n_threads: 'int | None' = None, annotation_states: 'frozenset[str] | None' = None, validated_only: 'bool' = False, logical_hints: 'str | None' = None) -> 'ContextResult'
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
tarel.graph.refresh(name: 'str', *, config: 'str | Path | None' = None, namespace: 'str | None' = None) -> 'GraphRefreshResult'
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
tarel.index.build(graph: 'str', *, model_path: 'str | Path | None' = None, batch_size: 'int' = 16, n_threads: 'int | None' = None, resume: 'bool' = False, progress: 'Callable[[int, int, str], None] | None' = None) -> 'IndexBuildResult'
```
```python
tarel.index.status(graph: 'str') -> 'dict[str, object]'
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
tarel.lineage.analyze(name: 'str', *, source: 'str | Path', provider: 'str', model: 'str | None' = None, timeout: 'float' = 180.0, retry: 'int' = 1, limit: 'int | None' = None, definitions: 'tuple[str, ...]' = (), review_passes: 'int' = 1, max_output_tokens: 'int | None' = None, reasoning_effort: 'str | None' = None, progress: 'Callable[[str], None] | None' = None) -> 'LineageProviderRunResult'
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
tarel.model.status(*, name: 'str' = 'qwen3-embedding-0.6b-q4-k-m', model_path: 'str | Path | None' = None) -> 'dict[str, object]'
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

#### SDK search

```python
tarel.search.graph(name: 'str', query: 'str', *, limit: 'int' = 20, namespace: 'str | None' = None, mode: 'str' = 'lexical', model_path: 'str | Path | None' = None, n_threads: 'int | None' = None, annotation_states: 'frozenset[str] | None' = None, validated_only: 'bool' = False, family_mode: 'str | None' = 'confirmed_only') -> 'SearchResults'
```
```python
tarel.search.workspace(name: 'str', query: 'str', *, selection: 'ScopeSelection | None' = None, systems: 'tuple[str, ...]' = (), graphs: 'tuple[str, ...]' = (), areas: 'tuple[str, ...]' = (), schemas: 'tuple[str, ...]' = (), zones: 'tuple[str, ...]' = (), limit: 'int' = 20, mode: 'str' = 'lexical', model_path: 'str | Path | None' = None, n_threads: 'int | None' = None, annotation_states: 'frozenset[str] | None' = None, validated_only: 'bool' = False, family_mode: 'str | None' = 'confirmed_only') -> 'SearchResults'
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
tarel.source.refresh_graph(name: 'str', graph: 'str', *, namespace: 'str | None' = None) -> 'GraphRefreshResult'
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
tarel.workspace.scope(name: 'str', *, selection: 'ScopeSelection | None' = None, systems: 'tuple[str, ...]' = (), graphs: 'tuple[str, ...]' = (), areas: 'tuple[str, ...]' = (), schemas: 'tuple[str, ...]' = (), zones: 'tuple[str, ...]' = ()) -> 'ResolvedScope'
```
```python
tarel.workspace.zone(name: 'str', system: 'str', zone: 'str') -> 'ResolvedZone'
```

### Errors and concurrency

Catch the relevant domain Failure class when integrating; preserve its code and handle stale revisions explicitly. A client root is independent of the process working directory. Concurrent reads are supported; coordinate writers targeting the same persisted document. An SDK review call changes the same knowledge that the CLI/browser reads.

[Architecture and extension contracts](architecture.md) · [Contract reference](contracts.md) · [Demo](retail-demo.md) · [Workshop](workshop.md)
