# Metadata sync

Several independent TAREL installations can publish approved metadata to one central state. A site
owns what it observes and publishes; the central state owns what it adds. This is one-way: there is
no multi-writer merge, and TAREL copies metadata only, never data.

**Status: experimental, first version.** It has been tested locally with four separate state roots
and real processes. No real cloud, gateway, or network share was involved, and it carries no
certification for high-security environments.

## Quick start

A site names what it approves and publishes a signed file:

```console
tarel graph build erp --connector sqlite --config source.toml
tarel sync init --state .tarel
tarel sync stream-create --state .tarel --name main --graph erp --namespace main
tarel sync publish --state .tarel --stream main --output main-1.tarelpub --signing-key ~/.ssh/tarel
```

The central state grants that stream one local graph, then checks and takes over the file. `init`
and `stream-create` print the three IDs, which reach the central side through your own channel, as
does the public key. A file can never grant them itself.

```console
tarel sync trust-key --state .tarel --publisher-id PUB --public-key-file site.pub
tarel sync trust-add --state .tarel --publisher-id PUB --stream-id STR --graph-id GPH --local-graph site-a.erp --workspace group --system site-a --namespace main
tarel sync inspect main-1.tarelpub
tarel sync plan main-1.tarelpub --state .tarel
tarel sync apply main-1.tarelpub --state .tarel
tarel sync status --state .tarel --max-age-hours 24
tarel search "orders" --workspace group
```

The SDK runs the same use cases and raises the same failure codes:

```python
from tarel.sdk import Tarel

site = Tarel("site/.tarel")
publisher_id = site.sync.init_publisher()
stream = site.sync.create_stream("main", graph="erp", namespaces=("main",))
site.sync.publish("main", output="main-1.tarelpub", signing_key="keys/tarel")

central = Tarel("central/.tarel")
central.sync.trust_key(publisher_id, public_key=open("keys/tarel.pub").read())
central.sync.trust(
    publisher_id=publisher_id,
    stream_id=stream.stream_id,
    graph_id=stream.graph_id,
    local_graph="site-a.erp",
    workspace="group",
    system="site-a",
    namespaces=("main",),
)
plan = central.sync.plan("main-1.tarelpub")
result = central.sync.apply("main-1.tarelpub", plan_id=plan.plan_id)
```

`python tools/sync_four_instances.py` runs this across four instances and prints each check.

## Who owns what

| Statement | Owner | Where it lives centrally |
| --- | --- | --- |
| Observed technical metadata | The site | The local graph, replaced by each update |
| Annotations a site publishes | The site | Word for word in `metadata.published_annotation`, with origin |
| Central annotations and decisions | Central | The node's annotation; a site's update never replaces them |
| Relationships between origins | Central | The workspace document, reviewed by people |

The visible annotation of a node is the central one if there is any. Otherwise it is the site's,
at most as `draft` and with provenance `sync:<publisher>`, so a site's `validated` is not a central
one. Conflicting statements both stay readable. Equal names create no join between origins.

An object's full identity is publisher, source graph and its existing node ID. All IDs are random,
assigned once, and independent of host, path, cloud, and display names. One stream carries one graph
and one approved set of namespaces; two streams of a graph may not overlap.

## What travels

| Document | First version | Reason |
| --- | --- | --- |
| Graph, technical metadata | Transferred under an allowlist | Owned by the site |
| Annotations | Only if the stream approves and trust allows them; evidence values stay home | Free text can hold samples |
| Technical descriptions | Only if the stream approves and trust allows them | Free text from the source |
| Graph change reports | Rebuilt centrally by each update | Bound to central revisions |
| Knowledge documents | Not transferred | Not implemented yet; a file holding one is refused |
| Lineage | Not transferred | Equal qualified names would join origins by name alone |
| Focus, logical topology | Not transferred | Bound to a graph revision; build them centrally |
| Alias and mapping data, credentials, connector or provider configuration, samples, query results, logs, indexes, models | Never transferred | Allowlist; the receiver checks the same list |

So a complete snapshot means complete for the approved technical scope, not for all local TAREL
documents. An export profile limits fields; it cannot promise that approved free text is harmless.

## The publication file

A `.tarelpub` file is an uncompressed ZIP holding exactly `package.tarel`, an ordinary verifiable
[package](package-format.md), `publication.json`, and normally `publication.sig`.

```text
package bytes -> package_sha256 in publication.json -> signature over those exact bytes
```

`publication_id` is the SHA-256 of `publication.json`, which is parsed but never written again.
`content_revision` is the SHA-256 of the sorted `<path> <sha256>` manifest lines, so a TAREL upgrade
or another ZIP implementation does not look like new content. `observed_at` only reports the age of
the source: order comes from `sequence` and `recent_publications`, never from a clock.

| Incoming publication | Result |
| --- | --- |
| The active `publication_id` | No change |
| Higher sequence, same `content_revision` | Freshness moves, the graph is not written |
| Higher sequence, active publication in its history | Content is updated, skipped numbers are reported |
| Higher sequence, active publication missing from a history that is not full | `publication_conflict` |
| Active publication older than a full history | `history_gap` unless explicitly accepted |
| Lower sequence | `stale_publication` |
| Same sequence, other `publication_id` | `publication_conflict` |
| Completeness other than `complete` | `incomplete_snapshot`; the active state stays |

A writer restored from a backup or copied from another installation shows up as a conflict. If it is
the right one, `--accept-history-gap` accepts its next higher sequence; a lower or equal one stays
refused. `sync/streams/<stream>/head.json` is the only authority on what is active. An annotation
that differs from what the last activation wrote counts as central and survives updates.

A publication says where its facts come from. By default `observed_at` and `completeness` come from
`graphs/<graph>/observation.json`, which graph build, import and refresh record beside the graph and
outside its revision: `observation_source` is then `recorded`. A failed refresh keeps the last good
read and blocks publishing with `observation_failed`, because old metadata must not look like a new
observation. A read limited to another namespace makes the file `partial`. Passing `--observed-at`
states the facts on the caller's word instead, and the file says `stated`.

## Removing, withdrawing, not observing

| Event | Evidence | Central effect |
| --- | --- | --- |
| Deleted in the source | Object missing from a complete snapshot of a namespace still approved | Leaves the active graph, reason `source_deleted` |
| No longer approved | `tarel sync stream-update` dropped its namespace, under a new profile version | Leaves the active graph, reason `withdrawn`; claims nothing about the source |
| Not observed | Partial file, failed read, or no delivery at all | Nothing changes; the status shows the failure and the age |

A scope may only change under a new profile version; otherwise the file is a `publication_conflict`.
A site's withdrawal takes effect without central approval, since the site owns what it releases. A
namespace still approved but gone from the graph stops publishing with `scope_namespace_missing`:
that would read as mass deletion, so the stream must be updated on purpose.

Central statements outlive the objects they describe. An annotation on a removed object stays in the
active revision's `impacts.json` with its reason, and returns with the object: a `validated` one as
`review_required`, because the source may have changed, a rejection as a rejection. Zones, areas and
relationships in a workspace are not edited, so a human `validated` stays. While their target is
missing they offer no join, and `plan` and `status` list them as `dangling_references`. This applies
only to graphs carrying `sync_origin`; a dangling reference into an ordinary local graph remains an
error.

Withdrawing removes metadata from the active view, not from disk. Older revisions keep it until
`tarel sync prune`, which keeps what the active state needs. Change reports keep the names of what
changed. No command can recall a file already delivered elsewhere.

## Delivering files and surviving interruptions

A transport only places files. `tarel sync inbox --directory DIR` runs one pass through the same use
case as `tarel sync apply`, so it cannot skip a check or settle a conflict, and the exit status is 1
when a file was rejected. Uploaders write under another name and rename last: only names ending in
`.tarelpub` and not starting with a dot are taken. A truncated file under its final name fails its
checks like any other damaged file. Taken files move to `done/`, refused ones to `rejected/` with a
reason beside them. TAREL runs no scheduler and manages no cloud access; external tools call this.

The switch has one commit point. `apply` first keeps the file and the exact target graph as an
immutable revision, then writes `head.json` naming a pending activation, then writes the graph, and
finally clears the mark, flushing each to disk. A process stopped before the commit leaves the old
state active. One stopped after it is finished by `tarel sync recover`, the next `apply` of that
stream, or the next inbox pass, while readers keep seeing the whole old graph until the switch.
If someone edited the graph meanwhile, recovery stops with `activation_blocked` instead of
overwriting it. `plan` refuses with `activation_pending` until this is resolved.

One lock per stream serializes takeovers of that stream, and streams proceed independently. Lock
order is stream, then graph, then state. A central edit that arrives after planning makes the graph
write fail with `stale_plan`. Workspace edits from other commands take no sync lock, so run them
outside a first takeover into the same workspace.

## Trust and signatures

Five questions stay apart. A checksum shows **integrity**. A signature shows **who sent** a file. The
central trust entry alone decides **what that sender may write**. Encryption would protect
**confidentiality** and is not part of this contract; it belongs around the whole file, for example
`team.tarelpub.age`. Nothing here shows that a statement is **true**: a valid signature never raises
a review state.

Signatures use `ssh-keygen -Y` with Ed25519 keys and the namespace `tarel-publication`, and work
offline. TAREL implements no cryptography and never copies a private key: `publish --signing-key`
takes a key path, or the `.pub` path when the key sits in an agent. A missing `ssh-keygen` is
`signature_tool_missing`, never a fallback.

```console
tarel sync trust-key --state central --publisher-id PUB --public-key-file site.pub
tarel sync trust-add --state central --publisher-id PUB --stream-id STR --graph-id GPH \
  --local-graph site-a.erp --workspace group --system site-a --namespace dbo
tarel sync publish --state site --stream main --output main-8.tarelpub --signing-key ~/.ssh/tarel
tarel sync apply main-8.tarelpub --state central
```

| Refusal | Meaning |
| --- | --- |
| `untrusted_publisher` | No trust entry names this publisher |
| `unauthorized_scope` | Valid sender, but the stream, namespace, annotations or descriptions are not allowed |
| `unknown_signing_key` | The key named is not trusted for this publisher |
| `revoked_signing_key`, `expired_signing_key` | The local trust file stopped accepting this key |
| `invalid_signature` | The bytes do not verify, or statement and signature do not belong together |
| `unsigned_publication` | No signature and no development flag |

The check runs before the package is expanded, and a failed one is recorded as a failure, not as a
received publication. After it, the receiver checks the content against what the file itself
declares, by the same rule the sender selects with: a validly signed package holding a key its scope
does not release, such as `technical_description` when descriptions are off, or a namespace or field
outside its scope, is refused whole with `export_not_allowed`. So is an allowed key holding the wrong
kind of value: a `primary_key` or foreign-key field list must name real fields, and `position`,
`nullable` and `is_primary_key` must have their exact types. Nothing is stripped on arrival, the active
state stays, and a more generous central grant does not widen what the file declared.

Each declared namespace must hold at least one table or view, on both sides, with
`scope_namespace_missing`. A signed snapshot therefore cannot empty a namespace it still declares and
turn its objects into deletions. Removing the last object of a namespace still needs a
`stream-update` that takes the namespace out.

Refusals name only what TAREL knows itself. Names and values a sender chose stay out of error
messages, `sync status` and `.reason.json`. A file kept under `rejected/` keeps its original bytes, so
treat that directory as holding whatever was delivered. A file that cannot be read fails on its own,
without needing a trusted key, and the rest of an inbox pass continues.

The receiver also refuses a node whose ID contradicts its name, such as an `hr` object labelled `dbo`.
This shows that a package is consistent with itself, not that it tells the truth. A trusted sender
that changes every place at once could still publish `hr.salaries` as `dbo.salaries`, and a central
state that cannot see the source cannot notice. So trust belongs to a site's key, which can be
revoked, and what protects that key matters:

- Keep it in an agent or a hardware token; `--signing-key` takes the `.pub` path for that.
- Let a separate account or release process publish, not the account people work with day to day.
- Give each site its own key, so one can be revoked without touching the others.

The statement is signed and retained centrally until `tarel sync prune`, so a publication can be
traced to the key that made it. An unmodified exporter never renames an object: this limit concerns
modified software or a compromised site. To rotate a key, add the new one, switch the site, then revoke the old one.
Publications signed with a revoked key are refused from then on, even old ones not yet delivered.
An offline state knows a revocation only once someone enters it there, so TAREL promises no global
effect. `--allow-unsigned-dev` is for local development: it never excuses a removed signature.

Input from another installation has tighter limits than ordinary packages: 512 MiB per file, 1 GiB
expanded, a compression ratio of 200 for members above 1 MiB, 3 members outside and 16 inside. The
member count is read from the ZIP trailer before a parser walks the directory. Package content is
data: nothing in it is executed, fetched or taken as local policy.

## Known limits

- Tested on one machine: no real cloud, gateway or network share. SMB and NFS locking is unproven.
- Killed processes were tested; power loss was not, although writes are flushed.
- A read record only says the connector returned without error, not that it saw everything.
- A table-level claim is flagged only for changes to the object itself, as in `graph refresh`.
- Other `workspace` commands take no sync lock.
- Anyone who can write the state directory as the same user can change it directly.
- `tarel sync status` reads a graph only if a workspace refers to it, and each at most once. Nothing
  is cached between calls.
- The content check protects future takeovers. A state that accepted such content earlier keeps it
  until new content from that stream replaces the graph, and old revisions keep it until
  `tarel sync prune`. To look without changing anything, compare each
  `sync/streams/<id>/head.json` with its `graphs/<local_graph>/graph.json`: no
  `technical_description` key unless `scope.technical_descriptions` is true, no namespace outside
  `scope.namespaces`, and no field whose `object_id` names a missing object.
- Knowledge transfer and delta updates are not implemented; there is no receipt back to a site.
