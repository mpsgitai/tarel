import argparse
import ast
import collections
import contextlib
import inspect
import re
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tarel.cli import build_parser  # noqa: E402
from tarel.sdk import Tarel  # noqa: E402

OUT = ROOT / "docs/cli-reference.md"
URL = "../"
GROUPS = {
    "version": (
        "Version",
        "Identify the installed package when reporting an issue or reproducing a run.",
        "Prints the package version. No graph or provider operation.",
        "",
        "tarel version",
    ),
    "demo": (
        "Demo warehouse",
        "Create a deterministic local source for learning and regression exercises.",
        (
            "Creates a local SQLite database and its connector configuration."
            " Replacing a demo with --force changes that demo source."
        ),
        "retail-demo.md",
        "tarel demo create retail-dwh",
    ),
    "workspace": (
        "Workspace organization",
        (
            "Organize independent source graphs into systems, areas, schema s"
            "copes, and overlapping object zones."
        ),
        (
            "Definitions and relationship decisions persist workspace state. "
            "A define operation replaces its named definition; supply the com"
            "plete desired membership. List/show/scope inspect that state."
        ),
        "workspaces.md",
        "tarel workspace scope enterprise --system warehouse --format json",
    ),
    "source": (
        "Logical sources",
        (
            "Name a connection profile once and use it for discovery, graph c"
            "reation, enrichment, and grounding."
        ),
        (
            "Configure persists logical source settings; check/probe/discover"
            " have different purposes. Build/refresh update graphs. Enrich re"
            "turns an ephemeral observation workfile, with persistence only f"
            "or explicitly requested candidates. Source permissions independe"
            "ntly govern aggregates, small domains, samples, and entity alias"
            "es."
        ),
        "retail-demo.md",
        "tarel source check warehouse-prod",
    ),
    "connector": (
        "Connectors",
        "Call a connector directly, inspect its availability, or scaffold a new adapter.",
        (
            "Probe/discover/profile/sample can read the external source. Scaf"
            "fold writes an inactive candidate package; it does not implement"
            " or install it. Direct connector commands and named source polic"
            "ies are distinct interfaces."
        ),
        "architecture.md",
        "tarel connector check sqlserver",
    ),
    "knowledge": (
        "Annotation documents",
        "Attach scoped business documentation for annotation tasks.",
        (
            "Add stores a knowledge document; list/show/resolve inspect docum"
            "ents or their resolved scope. Annotation must explicitly request"
            " scoped or named knowledge."
        ),
        "sdk.md",
        "tarel knowledge list",
    ),
    "provider": (
        "Model providers",
        "Configure an optional structured-generation endpoint or create an adapter candidate.",
        (
            "Configure stores a private profile. Test makes a model request. "
            "Scaffold creates inactive adapter source files. A profile using "
            "an existing OpenAI-compatible adapter usually needs configuratio"
            "n rather than a new adapter implementation."
        ),
        "architecture.md",
        "tarel provider list",
    ),
    "model": (
        "Local embedding model",
        "Manage the optional local embedding model used by vector and hybrid retrieval.",
        (
            "Download fetches a model artifact; status reports availability. "
            "This is an embedding model, not a local annotation/generation mo"
            "del."
        ),
        "local-retrieval.md",
        "tarel model status --format json",
    ),
    "index": (
        "Retrieval indexes",
        "Prepare and inspect rebuildable local retrieval indexes for a graph.",
        (
            "Build writes the index and may perform local CPU embedding compu"
            "tation. Resume only reuses a compatible checkpoint. Graph, revie"
            "w, or model changes can require rebuilding."
        ),
        "local-retrieval.md",
        "tarel index status warehouse",
    ),
    "graph": (
        "Source graphs",
        "Build, refresh, annotate, and inspect the technical and semantic snapshot of a source.",
        (
            "Build/import/refresh/annotate persist graph knowledge. Selective"
            " reads may bootstrap or rebuild a local cache; authoritative gra"
            "ph JSON remains the source of truth. The selective graph cache d"
            "iffers from the retrieval index."
        ),
        "graph-storage.md",
        "tarel graph objects warehouse --limit 10 --format json",
    ),
    "ui": (
        "Browser",
        "Explore graph/workspace structure, lineage, and reviewable knowledge.",
        (
            "Starts a local browser server. --edit enables explicit mutations"
            ". Opening the UI does not itself run a connector or LLM. UI disp"
            "lay filters are not automatically context-packet constraints."
        ),
        "browser-workflows.md",
        "tarel ui --workspace enterprise --lineage sales-etl",
    ),
    "lineage": (
        "Static and runtime lineage",
        (
            "Describe data dependencies, analyze definitions, trace upstream "
            "origins, and record observed executions."
        ),
        (
            "Build consumes canonical input rather than extracting a schedule"
            "r itself. Analyze invokes the provider and persists drafts. Next"
            "/apply supports harness-authored proposals. Runtime imports stor"
            "e caller observations separately from reusable static ETL defini"
            "tions."
        ),
        "runtime-lineage.md",
        "tarel lineage show sales-etl --view status --format json",
    ),
    "semantic": (
        "Imported semantic models",
        "Import and inspect external semantic definitions and their bindings to graph objects.",
        (
            "Import stores a semantic sidecar; edits preserve the original so"
            "urce snapshot through the supported overlay behavior. Imported s"
            "emantics do not automatically become approved TAREL annotations."
        ),
        "semantic-imports.md",
        "tarel semantic list",
    ),
    "entity": (
        "Entity-resolution candidates",
        "Inspect and review evidence that different representations may denote the same entity.",
        (
            "Imports and reviews persist entity artifacts. Candidate retrieva"
            "l is separate from trusted physical joins. Entity resolution is "
            "not an automatic merge of source records."
        ),
        "entity-resolution-candidates.md",
        "tarel entity --help",
    ),
    "discovery": (
        "Discovery runs",
        (
            "Run a bounded hypothesis, observation, and decision protocol for"
            " joins, entities, and mappings."
        ),
        (
            "The harness owns probes and data execution. TAREL owns revisione"
            "d run state and validates submitted evidence. next supplies allo"
            "wed_actions; submit must use the current revision. Promotion and"
            " human validation are separate operations."
        ),
        "discovery-runs.md",
        "tarel discovery next run-01 --format json",
    ),
    "agent": (
        "Harness resources",
        "Install the supplied agent-facing resources into a supported target.",
        (
            "Setup writes the selected resources; it does not launch an analy"
            "tical agent or grant database access."
        ),
        "discovery-runs.md",
        "tarel agent setup --help",
    ),
    "topology": (
        "Logical topology",
        "Declare derived logical objects and their physical references.",
        (
            "Import and review persist logical metadata. These declarations d"
            "o not execute extraction, transformation, or joins."
        ),
        "logical-topology.md",
        "tarel topology --help",
    ),
    "family": (
        "Object families",
        "Group compatible physical objects under an explicitly reviewed logical family.",
        (
            "Plan/proposal runs and review have separate effects. Provider ru"
            "ns create candidates; schema compatibility does not prove safe u"
            "nions or disjoint rows. Member pages preserve physical identitie"
            "s."
        ),
        "object-families.md",
        "tarel family --help",
    ),
    "binding": (
        "Object-to-value bindings",
        "Resolve caller selections to declared physical or family members.",
        (
            "Bindings declare metadata routing. Private values supplied throu"
            "gh supported stdin paths remain caller input rather than persist"
            "ed graph values. Review and revision checks still apply."
        ),
        "object-value-bindings.md",
        "tarel binding --help",
    ),
    "concept": (
        "Semantic concepts",
        "Describe semantic concepts, representations, and declared hierarchies.",
        (
            "Import/review persist concept metadata. A hierarchy alone does n"
            "ot establish value equality, a join, or an analytically valid ro"
            "llup."
        ),
        "semantic-concepts.md",
        "tarel concept --help",
    ),
    "logical-join": (
        "Logical joins",
        "Find and review discovered joins involving logical endpoints.",
        (
            "These are separate logical artifacts, not physical foreign keys."
            " Effective usage depends on the endpoints and their review state"
            "."
        ),
        "logical-join-discovery.md",
        "tarel logical-join --help",
    ),
    "reference-mapping": (
        "Reference mappings",
        "Record and retrieve evidence about caller-owned field correspondences.",
        (
            "Private mapping values remain outside the artifact. Imports and "
            "reviews persist value-free metadata and evidence; a mapping does"
            " not itself execute data transformation."
        ),
        "reference-mappings.md",
        "tarel reference-mapping --help",
    ),
    "focus": (
        "Report and cube focus",
        "Persist an upstream selection starting at one exact reference.",
        (
            "Build stores a revision-bound focus. A single measure seed is no"
            "t automatically the full report. Inspect warnings and truncation"
            "; refresh the focus after relevant source changes."
        ),
        "family-focus.md",
        "tarel focus list",
    ),
    "search": (
        "Search",
        "Find graph anchors by technical names and business meaning.",
        (
            "Returns ranked metadata matches. BM25 does not require a local e"
            "mbedding model; vector/hybrid modes use the optional model and c"
            "ompatible indexes. Search results are not query results or proof"
            " of a join."
        ),
        "local-retrieval.md",
        'tarel search warehouse "customer revenue" --mode bm25',
    ),
    "context": (
        "Context compilation",
        (
            "Build a bounded context packet, prepare a stable prefix, compare"
            " packets, or expand pinned metadata."
        ),
        (
            "Build/prefix return graph-derived knowledge; the harness handles"
            " prompt placement and provider caching. Expand respects packet s"
            "cope, revision, and budgets. Diff compares packets; impact asses"
            "ses graph-change effects."
        ),
        "context-contract.md",
        (
            'tarel context build warehouse "customer revenue" --mode bm25 --v'
            "alidated-only --format json"
        ),
    ),
    "grounding": (
        "Source-aware grounding",
        (
            "Combine a context packet with source identity, dialects, and sel"
            "ected lineage information."
        ),
        (
            "Returns a grounding bundle. Registered logical sources contribut"
            "e routing metadata without credentials. The harness still execut"
            "es analytical queries."
        ),
        "sdk.md",
        'tarel grounding warehouse "customer revenue" --mode bm25 --format json',
    ),
    "annotation": (
        "Annotation tasks and review",
        (
            "Plan knowledge work, hand a task to the harness, apply a proposa"
            "l, and review its meaning."
        ),
        (
            "Plan/next do not invoke a generation provider. Optional samples/"
            "profiles can involve source reads. Apply writes a draft; validat"
            "e/reject/defer and edit change reviewable knowledge. Table and f"
            "ield review must be considered separately."
        ),
        "retail-demo.md",
        "tarel annotation plan --focus report-01 --format json",
    ),
    "relationship": (
        "Physical relationships",
        "Propose, probe, discover, and review physical field relationships.",
        (
            "Check/discover can query a source. Discovery candidates need sep"
            "arate validation. An inferred join is not ETL data flow; name si"
            "milarity alone is not proof."
        ),
        "retail-demo.md",
        "tarel relationship list warehouse",
    ),
}
NOTES = {
    "graph annotate": (
        "Processes eligible objects through a provider. --object is repea"
        "table; there is no --focus option. Translate a focus to per-grap"
        "h object lists in the harness. Existing annotations are skipped "
        "unless --include-annotated is selected. --workers controls this "
        "annotation runner, not the lineage runner."
    ),
    "lineage analyze": (
        "Makes sequential per-definition extraction requests, followed by"
        " --review-passes audit requests. It is not a provider batch API."
        " Compatible analysis-cache entries can be reused. Failed work is"
        " recorded; exhausted correction attempts stop the run. A provide"
        "r audit leaves the result a draft."
    ),
    "context prefix": (
        "Question-independent packet for an explicit graph/workspace scop"
        "e. Keep its serialization unchanged for possible prompt-prefix r"
        "euse. Budgets can omit fields/objects even when a complete datab"
        "ase was selected. TAREL does not guarantee a provider cache hit."
    ),
    "context expand": (
        "--requests must describe typed targets. Do not combine --request"
        "s - with --inputs-stdin: both would require stdin. Expansion ret"
        "urns exit code 1 when omissions are reported; inspect them rathe"
        "r than treating partial output as complete."
    ),
    "context build": (
        "The shorthand tarel context NAME QUERY is rewritten to this comm"
        "and. --validated-only filters semantic claims, not the entire ph"
        "ysical inventory. An unchanged question is not sufficient for re"
        "use after a graph or review revision changes."
    ),
    "context impact": (
        "An unknown impact is a distinct outcome; the main CLI returns ex"
        "it code 1 for that result. Inspect the reported impact instead o"
        "f assuming all non-error output proves compatibility."
    ),
    "source enrich": (
        "Walks the bound graph and returns an ephemeral workfile. Authori"
        "zed raw rows remain output rather than graph/context content. Pe"
        "rsisting join candidates is explicit; zero candidates can be a v"
        "alid result."
    ),
    "graph import-catalog": (
        "The input is a canonical CatalogResult JSON document produced by"
        " a caller/connector. It is not arbitrary catalog JSON, CSV, or a"
        " source connection configuration."
    ),
    "lineage build": (
        "Requires canonical lineage input containing definitions and obse"
        "rvations. SQL Agent order, nested procedure calls, and physical "
        "reads/writes are different evidence and must be represented acco"
        "rdingly."
    ),
    "lineage import-runtime": (
        "Requires a complete runtime-lineage input with exact graph revis"
        "ion and resolvable inputs. Imports are create-only. Successful e"
        "xecution does not validate a relationship or certify the caller'"
        "s metrics."
    ),
    "annotation plan": (
        "Supply exactly one graph NAME or --focus FOCUS. The JSON plan in"
        "cludes count and tasks with graph_name, id, target, target_id, a"
        "nd context_documents."
    ),
    "annotation next": (
        "Supply exactly one graph NAME or --focus FOCUS. The returned wor"
        "kfile is intended for the harness model. Use graph annotate for "
        "direct provider execution."
    ),
    "connector scaffold": (
        "Produces CONNECTOR_TASK.md, an adapter package skeleton, a manif"
        "est, and reference notes. Implement probe/discover, test, review"
        ", and install the package before its entry point becomes availab"
        "le."
    ),
    "provider scaffold": (
        "Produces PROVIDER_TASK.md and an inactive package skeleton imple"
        "menting StructuredProvider. Existing OpenAI-compatible endpoints"
        " can often use provider configure --adapter openai-compatible in"
        "stead."
    ),
    "workspace zone define": (
        "A zone can span graphs and schemas inside one system. Its member"
        " schemas must already be assigned to areas. Supply the complete "
        "desired object list on every definition."
    ),
    "discovery promote": (
        "A promoted selected candidate enters the relevant review path. C"
        "ompletion/promotion is not human approval and does not execute o"
        "r install a private matching implementation."
    ),
    "graph slice": (
        "Use exact object IDs from graph objects. The returned slice is a"
        " subset: preserve the complete source revision from its header r"
        "ather than persisting the slice as the original graph."
    ),
}
MEANINGS = {
    "name": "Name of the resource operated on by this command; see the command purpose.",
    "graph": (
        "Graph name; for commands supporting --workspace, that flag chang"
        "es the positional scope to a workspace."
    ),
    "graph_name": "Local graph name.",
    "graphs": "Graph names to include.",
    "workspace": ("Workspace identifier or mode switch; see the parameter syntax."),
    "workspace_name": "Workspace name.",
    "system_name": "System name within the workspace.",
    "area_name": "Area name within the system.",
    "zone_name": "Zone name within the system.",
    "systems": "System scope selection.",
    "areas": "Area scope selection.",
    "zones": "Zone scope selection.",
    "namespace": "Namespace/schema filter.",
    "database": "Source database override.",
    "config": "Path to private connector configuration.",
    "connector": "Connector identifier.",
    "source": (
        "Input source: file, logical source, or reference as specified by"
        " this command. See its linked contract."
    ),
    "sources": "Logical source selection.",
    "path": "Local input/output path for this command.",
    "id": "Artifact identifier.",
    "run_id": "Discovery or analysis run identifier.",
    "target": "Target object, field, or reference.",
    "target_id": "Target identifier.",
    "object": "Object reference.",
    "objects": "Selected object references.",
    "object_ids": "Exact object IDs.",
    "object_name": "Object name within the selected namespace.",
    "object_reference": "Qualified object reference.",
    "reference": "Exact reference to inspect or trace.",
    "from_reference": "Source endpoint reference.",
    "to_reference": "Target endpoint reference.",
    "source_field": "Source field reference.",
    "target_field": "Target field reference.",
    "field_name": "Field name within the selected object.",
    "members": "Family member references.",
    "family_id": "Object-family identifier.",
    "candidate_id": "Candidate identifier.",
    "candidate_ids": "Selected candidate identifiers.",
    "concept_id": "Semantic concept identifier.",
    "join_id": "Logical join identifier.",
    "item_id": "Item identifier; omit only where listing is supported.",
    "relationship_id": "Workspace relationship identifier.",
    "relation_id": "Relation identifier.",
    "call_id": "Recorded runtime call identifier.",
    "provider": "Configured provider profile.",
    "advisor_provider": "Optional provider used for proposal advice.",
    "model": "Model override.",
    "model_path": "Local embedding model path.",
    "n_threads": "Local model thread count.",
    "query": "Search or analytical question text.",
    "question": "Goal of the run.",
    "seed": "Exact upstream-trace starting reference.",
    "seed_limit": "Maximum retrieval seed count.",
    "limit": "Maximum number of items for this operation.",
    "offset": "Pagination starting offset.",
    "count": "Requested item count.",
    "row_limit": "Bound on source rows examined.",
    "profile_rows": "Row budget for optional profiling.",
    "profile_row_limit": "Row budget for profiling.",
    "samples": "Maximum requested sample rows; zero disables samples where supported.",
    "max_objects": "Maximum selected objects.",
    "max_fields_per_object": "Maximum fields per object.",
    "max_joins": "Maximum selected joins.",
    "max_hops": "Maximum traversal/expansion depth.",
    "max_trace_hops": "Maximum lineage-trace depth.",
    "max_characters": "Character budget; not a tokenizer-based token limit.",
    "max_input_chars": "Input character budget.",
    "max_knowledge_characters": "Knowledge-document character budget.",
    "max_output_tokens": "Provider output-token bound.",
    "max_pairs": "Candidate pair budget.",
    "candidate_budget": "Discovery candidate budget.",
    "probe_budget": "Discovery probe budget.",
    "min_overlap_count": "Minimum observed overlapping values.",
    "min_source_coverage": "Minimum sampled source coverage.",
    "min_target_uniqueness": "Minimum sampled target uniqueness.",
    "small_domain_limit": "Maximum small-domain cardinality.",
    "workers": "Parallel worker count for this command.",
    "objects_per_batch": "Object budget per proposal batch.",
    "retry": "Additional retry/correction attempts.",
    "retry_backoff": "Retry backoff interval.",
    "review_passes": "Additional provider audit passes.",
    "timeout": "Timeout in seconds.",
    "max_errors": "Error budget for the batch.",
    "skip_errors": "Continue supported batch processing after item failures.",
    "include_annotated": "Include targets that already have annotations.",
    "dry_run": "Plan/preview instead of applying this operation.",
    "resume": "Resume a compatible checkpoint/run.",
    "force": "Allow the command-specific forced replacement.",
    "replace": "Replace an existing named definition/document where supported.",
    "validated": "Record the explicit validated state.",
    "include_exploratory": "Include exploratory candidates.",
    "include_source": "Include supported source details in output.",
    "expected_revision": "Exact current revision required for the write.",
    "revision": "Revision pin for this operation.",
    "state": "Selected review state.",
    "states": "Review-state selection.",
    "lineage_states": "Allowed lineage review states.",
    "decision": "Review decision.",
    "reason": "Human-readable reason for the decision or mutation.",
    "description": "Description stored with this artifact.",
    "title": "Document title.",
    "role": "Semantic role.",
    "grain": "Declared record grain.",
    "kind": "Artifact/operation kind.",
    "language": "Source language.",
    "qualified_name": "Fully qualified definition name.",
    "job_name": "Job display name.",
    "source_reference": "Reference to the source evidence.",
    "evidence_reference": "Evidence identifier/reference.",
    "line_start": "First evidence line.",
    "line_end": "Last evidence line.",
    "lineages": "Lineage documents to include.",
    "lineage_limit": "Maximum lineage matches.",
    "lineage_mode": "Lineage retrieval mode.",
    "trace_reference": "Optional exact reference to trace.",
    "mode": "Mode for this command; allowed values are listed separately.",
    "view": "Output projection.",
    "families": "Family inclusion/display policy.",
    "preset": "Named budget preset.",
    "reasoning_effort": "Provider reasoning-effort hint.",
    "format": "Output rendering format.",
    "output_format": "Output rendering format.",
    "semantic_format": "Semantic input format.",
    "left": "First comparison input.",
    "right": "Second comparison input.",
    "packet": "Existing context packet path.",
    "documents": "Knowledge document selection.",
    "action": "Action permitted by the current run phase.",
    "actor": "Actor identity for the operation.",
    "producer": "Producer identity.",
    "operation": "Logical operation kind.",
    "key": "Declared key.",
    "agent": "Target agent integration.",
    "version": "Requested demo/model format version.",
}


DOC_TARGETS = {
    "architecture.md": "architecture.md",
    "retail-demo.md": "retail-demo.md",
    "sdk.md": "#python-sdk",
    "workspaces.md": "contracts.md#workspaces-and-scopes",
    "graph-storage.md": "contracts.md#graph-storage-and-selective-reads",
    "context-contract.md": "contracts.md#context-packets",
    "local-retrieval.md": "contracts.md#local-retrieval",
    "runtime-lineage.md": "contracts.md#runtime-lineage",
    "semantic-imports.md": "contracts.md#semantic-model-imports",
    "discovery-runs.md": "contracts.md#discovery-protocol",
    "entity-resolution-candidates.md": "contracts.md#entity-resolution-candidates",
    "logical-topology.md": "contracts.md#logical-topology",
    "object-families.md": "contracts.md#object-families",
    "object-value-bindings.md": "contracts.md#object-to-value-bindings",
    "semantic-concepts.md": "contracts.md#semantic-concepts",
    "logical-join-discovery.md": "contracts.md#logical-joins",
    "reference-mappings.md": "contracts.md#reference-mappings",
    "family-focus.md": "contracts.md#families-in-report-focus",
    "browser-workflows.md": "contracts.md#browser-scope-and-review",
}
RESULTS = {
    "version": "Version text; no JSON document.",
    "demo": (
        "Created demo paths/configuration and version information. Existi"
        "ng demo replacement requires the command-specific force flag."
    ),
    "workspace": (
        "Workspace definition, resolved scope/zone, or relationship recor"
        "ds according to the verb. Scope output identifies selected graph"
        " objects and its scope hash."
    ),
    "source": (
        "Profile, availability/probe result, observed catalog, graph summ"
        "ary, or enrichment workfile according to the verb. Config refere"
        "nces remain distinct from resolved credentials."
    ),
    "connector": (
        "Availability check, probe, canonical catalog, bounded sample/pro"
        "file, or scaffold location according to the verb. Samples are ep"
        "hemeral command output."
    ),
    "knowledge": (
        "Knowledge document metadata/content, a document listing, or reso"
        "lved scoped documents. Inspect omissions when a document budget "
        "applies."
    ),
    "provider": (
        "Provider list/check, configured-profile acknowledgement, structu"
        "red test result, or scaffold location. Configuration is private "
        "rather than graph metadata."
    ),
    "model": "Download/status information for the embedding model artifact.",
    "index": "Index build/status information, including checkpoint compatibility when applicable.",
    "graph": (
        "A graph summary for build/show, change information for refresh, "
        "annotation progress/summary, or selective header/page/slice reco"
        "rds. Selective results carry complete-source identity and read a"
        "ccounting."
    ),
    "ui": "Local server startup information; the process serves the browser until stopped.",
    "lineage": (
        "The selected lineage document/projection, provider-run result, t"
        "ask/proposal result, review list/decision, or upstream trace. Th"
        "e exact envelope depends on the verb and --view. next returns a "
        "task or a completed/no-task outcome."
    ),
    "semantic": (
        "Imported semantic document, listing, or edit result. Bindings an"
        "d diagnostics preserve source identity."
    ),
    "entity": (
        "Sanitized entity candidate records, resolution results, or a rev"
        "iew result. Candidate state and effective usage remain visible."
    ),
    "discovery": (
        "Revisioned run/task/action results, advice, promotion results, o"
        "r coverage. next includes allowed actions; submit consumes the c"
        "urrent revision. Read status before choosing the next action."
    ),
    "agent": "Target agent, changed resource paths, and target directory.",
    "topology": ("Logical topology document and review state. Import takes typed input."),
    "family": (
        "Plan/run result, family document/list, or revision-bound member "
        "page. export serializes the family document. Membership remains "
        "physical and schema compatibility is not a union guarantee."
    ),
    "binding": (
        "Binding metadata, review result, or resolved member/object refer"
        "ences. Protected selections are not echoed as an ordinary catalo"
        "g."
    ),
    "concept": "Concept document, matching representations, or review result with current usage.",
    "logical-join": "Logical join records and effective review/usage state.",
    "reference-mapping": (
        "Value-free mapping candidates, selected matches, or review resul"
        "t. Mapping rows are caller-owned."
    ),
    "focus": (
        "Saved focus/listing with seed, source revisions, members, hops, warnings, and truncation."
    ),
    "search": ("Ranked metadata matches and selection information, not data rows."),
    "context": (
        "Context packet, metadata expansion, packet diff, or impact resul"
        "t. Inspect identities, budgets, and omissions; expand can return"
        " partial output with status 1."
    ),
    "grounding": (
        "Grounding bundle with stable and dynamic sections, source routin"
        "g metadata, context, selected lineage, and hashes."
    ),
    "annotation": (
        "Task plan, next task, proposal application, review listing, or a"
        "nnotation record/change. An empty plan is successful and does no"
        "t mean every field was human-approved."
    ),
    "relationship": (
        "Relationship records, bounded pair-profile evidence, discovery c"
        "andidates, or decision result. Validation is a separate explicit"
        " state change."
    ),
}
DOMAIN_CLI = {
    "lineage": "lineage/cli.py",
    "semantic": "semantics/cli.py",
    "entity": "entity_resolution/cli.py",
    "discovery": "discovery/cli.py",
    "agent": "discovery/cli.py",
    "topology": "topology/cli.py",
    "family": "object_families/cli.py",
    "binding": "object_bindings/cli.py",
    "concept": "semantic_concepts/cli.py",
    "logical-join": "logical_joins/cli.py",
    "reference-mapping": "reference_mapping/cli.py",
}


def source_for(group):
    return "src/tarel/" + DOMAIN_CLI.get(group, "cli.py")


def appendices():
    result = [
        "",
        "## Structured results and errors",
        "",
        (
            "JSON rendering is command-specific. Inspect --format defaults: s"
            "ome workfile commands emit structured JSON directly, whereas pro"
            "gress and status can use separate output channels. The following"
            " contract guide supplies the complete worked input documents and"
            " their invariants; serializer links define the exact runtime sha"
            "pe, including conditional fields."
        ),
        "",
        "| Output / input | Contract or serializer |",
        "| --- | --- |",
        "| Observed catalog | [CatalogResult](../src/tarel/connectors/contracts.py) |",
        (
            "| Stored graph and annotation | [GraphDocument](../src/tarel/gra"
            "ph/contracts.py), [annotation records](../src/tarel/annotations/"
            "contracts.py) |"
        ),
        (
            "| Context packet | [Packet contract](contracts.md#context-packet"
            "s), [serializer](../src/tarel/context_output.py) |"
        ),
        "| Grounding bundle | [GroundingBundle](../src/tarel/grounding.py) |",
        (
            "| Static lineage input/output | [Input](../src/tarel/lineage/sou"
            "rce.py), [stored records](../src/tarel/lineage/contracts.py) |"
        ),
        "| Runtime lineage | [Complete input and version rules](contracts.md#runtime-lineage) |",
        (
            "| Discovery proposals and observations | [Complete worked payloa"
            "ds](contracts.md#discovery-protocol) |"
        ),
        (
            "| Logical topology, mappings, entities and families | [Contracts"
            " and examples](contracts.md) |"
        ),
        "",
        "### JSON example: annotation plan",
        "",
        (
            "For a graph with no eligible annotation tasks, `tarel annotation"
            " plan GRAPH --format json` emits:"
        ),
        "",
        "```json",
        '{"count": 0, "tasks": []}',
        "```",
        "",
        (
            "Nonempty entries contain `graph_name`, `id`, `target`, `target_i"
            "d`, and `context_documents`. Apply proposals to their owning gra"
            "ph; a workspace can contain identical target labels in different"
            " graphs."
        ),
        "",
        "### JSON example: context identity",
        "",
        (
            "This is a shape excerpt, not an importable packet. A complete pa"
            "cket has versioned stable/dynamic records and computed hashes:"
        ),
        "",
        "```json",
        (
            '{"identity": {"stable_hash": "<sha256>", "dynamic_hash": "<sha25'
            '6>", "packet_hash": "<sha256>"}}'
        ),
        "```",
        "",
        (
            "Do not manufacture hashes or infer completeness from the presenc"
            "e of an identity. Validate the packet and inspect its omissions."
        ),
        "",
        "### Error recovery",
        "",
        "| Failure category | Recovery |",
        "| --- | --- |",
        (
            "| Missing resource/configuration | Check the local state root, r"
            "esource name and private configuration; create/import the prereq"
            "uisite first. |"
        ),
        (
            "| Invalid input or contract version | Use the complete contract "
            "shape and allowed fields. Do not silently rename or discard reje"
            "cted fields. |"
        ),
        (
            "| Stale revision/index | Reload the current record; regenerate t"
            "he dependent artifact/index and retry against its current revisi"
            "on. |"
        ),
        (
            "| Provider authentication/timeout/output | Correct the profile o"
            "r endpoint, inspect the bounded retry policy, and resume only th"
            "rough the supported runner. |"
        ),
        (
            "| Scope, policy or review failure | Inspect the resolved scope a"
            "nd review state. Broader privileges or candidate inclusion are e"
            "xplicit choices. |"
        ),
        (
            "| Existing artifact | Use the documented refresh/replace workflo"
            "w if available; create-only imports do not overwrite existing st"
            "ate. |"
        ),
        "",
        "### Error code index",
        "",
        (
            "The entries below are generated from explicit domain Failure con"
            "structors in this source tree. The linked source gives the exact"
            " condition and message. Dynamically forwarded connector/provider"
            " codes are not a closed enum; clients should retain an unknown c"
            "ode and handle failure rather than assume this list exhausts eve"
            "ry external system."
        ),
        "",
        "| Code | Defined at |",
        "| --- | --- |",
    ]
    errors = collections.defaultdict(set)
    for path in sorted((ROOT / "src/tarel").rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func.id if isinstance(node.func, ast.Name) else ""
            if (
                func.endswith("Failure")
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                errors[node.args[0].value].add((str(path.relative_to(ROOT)), node.lineno))
    for code_name, locations in sorted(errors.items()):
        refs = ", ".join(
            f"[{Path(p).parent.name}/{Path(p).name}](../{p}#L{n})" for p, n in sorted(locations)
        )
        result.append(f"| `{code_name}` | {refs} |")
    result += [
        "",
        "## Python SDK",
        "",
        (
            "The SDK calls the same application use cases as the CLI. It retu"
            "rns typed Python records and raises domain exceptions; it does n"
            "ot invoke CLI subprocesses. Select the state directory explicitl"
            "y. Creating the client alone does not discover a source, downloa"
            "d a model, or call a provider."
        ),
        "",
        "```python",
        "from tarel.sdk import Tarel",
        "",
        'tarel = Tarel("/srv/my-harness/.tarel")',
        "```",
        "",
        "### Graph and context example",
        "",
        (
            "Assumes `warehouse` already exists under that root. Returned rec"
            "ords expose their typed fields; use their supported serializers "
            "rather than assuming every SDK result is a JSON dictionary."
        ),
        "",
        "```python",
        'header = tarel.graph.header("warehouse")',
        'page = tarel.graph.objects("warehouse", limit=10, expected_revision=header.revision)',
        'packet = tarel.context.graph("warehouse", "customer revenue", mode="bm25")',
        "parts = tarel.context.split(packet)",
        "```",
        "",
        "### Harness grounding example",
        "",
        (
            "Assumes the graph and logical source are already configured. The"
            " harness is responsible for model requests and authorized answer"
            "-query execution."
        ),
        "",
        "```python",
        "bundle = tarel.grounding.context(",
        '    "Explain customer revenue", graph="warehouse",',
        '    sources=("warehouse-prod",), mode="bm25",',
        ")",
        "stable_text = bundle.stable_prompt()",
        "dynamic_text = bundle.dynamic_prompt()",
        "```",
        "",
        (
            "Keep the stable text unchanged only while its selected scope and"
            " revisions remain valid. The SDK does not promise provider cache"
            " acceptance."
        ),
        "",
        "### SDK method reference",
        "",
        (
            "Signatures below are generated from the public client namespaces"
            ", including default values and return types. Types refer to the "
            "definitions imported by [the SDK module](../src/tarel/sdk/client"
            ".py). Domain methods are explicit: CLI names do not always trans"
            "late literally (for example `source build` is `source.build_grap"
            "h`)."
        ),
        "",
    ]
    client = Tarel(ROOT / ".tarel-doc-reference-unused")
    for namespace in Tarel.__slots__:
        if namespace == "runtime":
            continue
        api = getattr(client, namespace)
        methods = [
            (n, m) for n, m in inspect.getmembers(api, inspect.ismethod) if not n.startswith("_")
        ]
        result += [f"#### SDK {namespace}", ""]
        for name, method in methods:
            result += ["```python", f"tarel.{namespace}.{name}{inspect.signature(method)}", "```"]
        result += [""]
    result += [
        "### Errors and concurrency",
        "",
        (
            "Catch the relevant domain Failure class when integrating; preser"
            "ve its code and handle stale revisions explicitly. A client root"
            " is independent of the process working directory. Concurrent rea"
            "ds are supported; coordinate writers targeting the same persiste"
            "d document. An SDK review call changes the same knowledge that t"
            "he CLI/browser reads."
        ),
        "",
        (
            "[Architecture and extension contracts](architecture.md) · [Contr"
            "act reference](contracts.md) · [Demo](retail-demo.md) · [Worksho"
            "p](workshop.md)"
        ),
        "",
    ]
    return result


def cell(x):
    return str(x).replace("|", "\\|").replace("\n", " ")


def code(x):
    return "`" + cell(x) + "`"


def anchor(s):
    return s.replace(" ", "-")


root = build_parser()
leaves = []


def walk(p, path=(), helptext=""):
    subs = [a for a in p._actions if isinstance(a, argparse._SubParsersAction)]
    if not subs:
        leaves.append((path, p, helptext))
        return
    for sub in subs:
        helps = {a.dest: a.help for a in sub._choices_actions}
        for n, c in sub.choices.items():
            walk(c, path + (n,), helps.get(n, ""))


walk(root)
groups = collections.defaultdict(list)
for item in leaves:
    groups[item[0][0]].append(item)
lines = [
    "# TAREL CLI Reference",
    "",
    (
        "Command reference for the CLI shipped in this source tree. Regen"
        "erate with `python tools/generate_cli_reference.py`."
    ),
    "",
    (
        "Syntax, choices, defaults, required flags, and mutually exclusiv"
        "e groups are generated from the CLI parser. The command notes de"
        "scribe behavior; the linked contracts define structured inputs a"
        "nd outputs. Resource names in examples must be replaced with res"
        "ources in your environment."
    ),
    "",
    f"**Coverage:** {len(leaves)} executable commands in {len(groups)} groups.",
    "",
    "## Reading this reference",
    "",
    (
        "- Uppercase names and `<placeholders>` denote values supplied by"
        " the caller. Examples assume the named local resources exist."
    ),
    (
        "- Syntax uses brackets for optional arguments, braces for allowe"
        "d alternatives, and `...` for variable-length input."
    ),
    (
        "- “Not set” is the parser default `None`; a use case or provider"
        " profile may resolve an effective value later."
    ),
    (
        "- `--format` is command-specific, not a global flag. Its default"
        " is listed for each command."
    ),
    (
        "- Run `tarel GROUP COMMAND --help` for the help of the installed"
        " version. `tarel --version` and `tarel version` both report its "
        "version."
    ),
    (
        "- The CLI uses local project state under `.tarel`. There is no g"
        "lobal `--state-dir` option in this parser; the SDK accepts an ex"
        "plicit runtime/state root."
    ),
    "",
    "## Resource and execution model",
    "",
    (
        "A connector observes a source. A logical source names its config"
        "uration and policy. A graph stores technical objects and semanti"
        "c claims. A workspace organizes multiple graphs. A focus is a sa"
        "ved upstream selection. Provider tasks propose knowledge; review"
        " changes its accepted state."
    ),
    "",
    (
        "Search/context/grounding return metadata, not analytical query r"
        "esults. The harness executes analysis. Raw samples and profiles "
        "are separate observations; requesting them can read source data "
        "and produce ephemeral output. Review proposals and dependency cl"
        "aims independently."
    ),
    "",
    (
        "Repeated values of a workspace scope facet form a union; differe"
        "nt facets narrow the result. Graphs, systems, areas, schemas, an"
        "d zones have explicit ownership rules. Read-only inspection can "
        "still build a local cache on supported paths."
    ),
    "",
    "## Exit status and errors",
    "",
    (
        "The main dispatcher returns 2 for recognized domain errors and w"
        "rites `error [code]: message` to stderr. Argument parsing errors"
        " also normally use status 2. Successful operations normally retu"
        "rn 0. Some operations use 1 for an incomplete/unknown outcome (f"
        "or example context expansion omissions or unknown context impact"
        "). Inspect structured status and omissions, not only the exit co"
        "de. This is not an exhaustive external-driver failure catalog."
    ),
    "",
    "## Command index",
    "",
    (
        "[Structured results and errors](#structured-results-and-errors) "
        "· [Python SDK](#python-sdk) · [Contracts](contracts.md)"
    ),
    "",
    "| Group | Commands | Purpose |",
    "| --- | ---: | --- |",
]
for g, items in groups.items():
    title, purpose, _, _, _ = GROUPS[g]
    lines.append(f"| [{g}](#{g}) | {len(items)} | {purpose} |")
checked = 0
missing = []
for g, items in groups.items():
    title, purpose, effect, doc, example = GROUPS[g]
    lines += ["", f"## {g}", "", f"**{title}.** {purpose}", "", effect, ""]
    if doc:
        lines += [f"Contract and workflow: [{doc}]({DOC_TARGETS.get(doc, 'contracts.md')}).", ""]
    lines += ["Example:", "", "```bash", example, "```", ""]
    root.parse_args(shlex.split(example)[1:]) if not example.endswith("--help") else None
    lines += [" | Command | Purpose |", " | --- | --- |"]
    for path, p, h in items:
        name = " ".join(path)
        lines.append(
            f" | [{code('tarel ' + name)}](#tarel-{anchor(name)}) | "
            f"{cell(h or p.description or purpose)} |"
        )
    for path, p, h in items:
        name = " ".join(path)
        lines += ["", f"### tarel {name}", "", h or p.description or purpose, ""]
        if name in NOTES:
            lines += [NOTES[name], ""]
        p.formatter_class = lambda prog: argparse.HelpFormatter(prog, width=100)
        usage = p.format_usage().strip()
        if usage.startswith("usage: "):
            usage = usage[7:]
        lines += [
            "**Syntax**",
            "",
            "```text",
            usage,
            "```",
            "",
            "**Arguments and options**",
            "",
            "| Parameter | Type / accepted values | Required / repetition | Default | Meaning |",
            "| --- | --- | --- | --- | --- |",
        ]
        for a in p._actions:
            if isinstance(a, argparse._SubParsersAction) or a.help == argparse.SUPPRESS:
                continue
            flag = ", ".join(a.option_strings) if a.option_strings else a.dest
            typ = (
                "flag"
                if a.nargs == 0
                else getattr(a.type, "__name__", "text")
                if a.type
                else "text"
            )
            if a.choices is not None:
                typ += "; " + ", ".join(code(c) for c in a.choices)
            req = "required" if a.required else "optional"
            if isinstance(a, argparse._AppendAction):
                req += "; repeatable"
            if a.nargs in ("+", "*"):
                req += f"; multiple values ({a.nargs})"
            if a.nargs == "?":
                req += "; optional value" if a.option_strings else "; optional positional"
            default = (
                "not set"
                if a.default is None
                else "—"
                if a.default == argparse.SUPPRESS
                else code(a.default)
            )
            if isinstance(a.default, Path) and a.default == Path.cwd():
                default = "current directory"
            if isinstance(a, argparse._HelpAction):
                default = "—"
            desc = a.help or MEANINGS.get(a.dest)
            if not desc:
                missing.append((name, a.dest))
                desc = "Command-specific value; see the linked contract."
            with contextlib.suppress(TypeError, KeyError, ValueError):
                desc = desc % {
                    "default": a.default,
                    "prog": p.prog,
                    "type": getattr(a.type, "__name__", "text"),
                    "choices": ",".join(map(str, a.choices or [])),
                }
            lines.append(f"| {code(flag)} | {typ} | {req} | {default} | {cell(desc)} |")
            checked += 1
        for mx in p._mutually_exclusive_groups:
            names = [" / ".join(a.option_strings) or a.dest for a in mx._group_actions]
            lines += [
                "",
                ("Exactly one required: " if mx.required else "Mutually exclusive: ")
                + ", ".join(code(n) for n in names)
                + ".",
            ]
        lines += [
            "",
            "**Result:** " + RESULTS[g],
            "",
            "CLI entry point and delegated output renderers: "
            f"[{source_for(g)}]({URL}{source_for(g)}).",
        ]
lines += [
    "",
    "## Practical sequences",
    "",
    "### Discover and annotate a source",
    "",
    "```bash",
    "tarel source check warehouse-prod",
    "tarel source build warehouse-prod warehouse",
    "tarel annotation plan warehouse --format json",
    "tarel graph annotate warehouse --provider openrouter --dry-run",
    "tarel graph annotate warehouse --provider openrouter",
    "tarel annotation list warehouse",
    "tarel ui warehouse --edit",
    "```",
    "",
    (
        "The source profile and provider must already exist. A successful"
        " provider run produces proposals; use the explicit review comman"
        "ds to accept knowledge."
    ),
    "",
    "### Analyze ETL and trace a report",
    "",
    "```bash",
    "tarel lineage build sales-etl --source imports/sales-etl.json",
    (
        "tarel lineage analyze sales-etl --source imports/sales-etl.json "
        "--provider openrouter --review-passes 1"
    ),
    "tarel lineage show sales-etl --view status",
    "tarel lineage review sales-etl",
    ('tarel focus build report-01 --seed "<measure-reference>" --lineage sales-etl --max-hops 40'),
    "tarel annotation plan --focus report-01 --format json",
    "```",
    "",
    (
        "Prepare canonical lineage input first. Scheduler order alone is "
        "insufficient evidence for physical data flow."
    ),
    "",
    "### Retrieve and keep a stable prefix",
    "",
    "```bash",
    'tarel search warehouse "customer revenue" --mode bm25',
    ('tarel context build warehouse "customer revenue" --mode bm25 --validated-only --format json'),
    "tarel context prefix warehouse --validated-only --format json",
    "```",
    "",
    (
        "The harness serializes and reuses the prefix and appends changin"
        "g material separately. Validate budgets, omissions, and revision"
        "s before reuse."
    ),
    "",
    "### Extend TAREL through a contract",
    "",
    "```bash",
    "tarel connector scaffold example-source --output ./example-source",
    "tarel provider scaffold example-provider --output ./example-provider",
    "```",
    "",
    (
        "These commands generate inactive code candidates. Follow the gen"
        "erated task documents, implement the contract, test, review, and"
        " then install the chosen package. Configuration of a new endpoin"
        "t using an existing provider adapter does not need a new scaffol"
        "d."
    ),
    "",
]
lines += appendices()
text = "\n".join(lines)
for block in re.findall(r"```bash\n(.*?)```", text, re.S):
    for cmd in block.splitlines():
        if cmd.startswith("tarel ") and not cmd.endswith("--help"):
            root.parse_args(shlex.split(cmd)[1:])
if missing:
    raise SystemExit(f"Missing parameter documentation: {missing}")
if "--check" in sys.argv:
    if not OUT.exists() or OUT.read_text() != text:
        raise SystemExit("CLI reference is stale. Run python tools/generate_cli_reference.py")
    print(f"CLI reference current: {len(leaves)} commands, {checked} parameter rows.")
else:
    OUT.write_text(text)
    print(f"Generated {OUT.relative_to(ROOT)}: {len(leaves)} commands.")
