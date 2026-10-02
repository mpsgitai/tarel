# Portable `.tarel` packages

TAREL's editable source of truth remains a normal `.tarel/` directory containing readable JSON
documents. A file ending in `.tarel` is a selected metadata snapshot for review and transfer,
not a complete backup of local state. It is an ordinary ZIP container so the contents remain
inspectable with standard operating-system tools. The package layer uses only the Python standard
library.

New exports use `tarel.package.v0.2`; readers also accept `tarel.package.v0.1` snapshots.
Version 0.2 records the narrower auxiliary selection policy without changing graph, knowledge,
lineage, workspace, or focus schemas. Older TAREL readers require an update to open these exports.
`application/vnd.tarel+zip` is currently a
project media type, not an IANA-registered type. The package contract has its own version and does
not inherit the installed TAREL version.

## Commands

```console
tarel package plan --state .tarel --workspace team
tarel package pack --state .tarel --workspace team --output team.tarel
tarel package pack --state .tarel --workspace team --output team.tarel --lineage sales-etl --knowledge shared-terms
tarel package inspect team.tarel
tarel package verify team.tarel
tarel package unpack team.tarel --destination imported-state
```

`unpack` accepts only a destination that does not yet exist. The first contract has no merge,
overwrite, or conflict-resolution mode.

## Container layout

```text
mimetype
manifest.json
graphs/<graph>/graph.json
workspaces/<workspace>/workspace.json
lineage/<lineage>/lineage.json
focus/<focus>/focus.json
knowledge/<document>/document.json
```

`manifest.json` identifies the selected workspace and every document by path, kind, logical name,
contract version, byte size, and SHA-256 digest. It also carries a deterministic package revision.
ZIP member timestamps and permissions are normalized, entries are sorted, and the manifest has no
wall-clock timestamp. Identical state therefore produces identical package bytes with the same
TAREL/Python ZIP implementation.

Packing includes the selected workspace, its graphs, knowledge scoped to its graphs/objects/schemas
or workspace systems, and focus snapshots whose sources are all included. Global knowledge and
lineage documents require explicit selection with repeatable `--knowledge ID` and `--lineage NAME`
flags. Lineage has no persisted workspace ownership, so TAREL does not guess membership from names
or SQL. Explicit knowledge selection can intentionally include a document outside the workspace.
The plan command accepts the same selection flags and lists paths, sizes, and hashes without
creating a package. A later pack captures a fresh snapshot; a plan does not pin future state.
Invalid inspected knowledge/focus documents and missing selected documents fail visibly.

Version 0.1 packages retain their original broad auxiliary policy when read; accepting an old
package does not narrow or otherwise rewrite its contents.

The allowlist excludes selective graph caches, search indexes, lineage analysis caches, connector
and provider configuration, credentials, logs, raw samples, source rows, and analytical results.
Indexes are rebuilt after import when needed.

## Snapshot completeness

Neither v0.1 nor v0.2 transfers logical topology overlays
(`logical-topology/<graph>/topology.json`) or graph change reports
(`graphs/<graph>/changes/<before>--<after>.json`). These are persisted metadata, not rebuildable
search indexes. A verified package therefore does not prove that all local graph-related metadata
was captured. It cannot restore topology-based explanations or historical change evidence that
remains only in the original state directory.

Every package command displays both omissions in text output. JSON plans and reports include an
`omissions` list covering these and the existing exclusions. This is derived reporting information
for both supported versions; their serialized manifests, omission policies, and revisions remain
unchanged. The notice describes the package boundary even when the source had no such documents;
an imported archive cannot reveal whether omitted files existed at its source.

Transferring these documents requires a separately reviewed package contract before stabilization.
That review must settle graph ownership, supported document versions, revision validation for
topology, selection and reference validation for historical reports, and snapshot locking across
their stores. Adding paths to ZIP files alone would not establish safe or complete round trips.

## Concurrent writes and snapshots

Graph transformations reload and update the latest document under a per-graph OS lock. Provider
generation, stdin reads, and source observations run without that lock. Stale annotation tasks
are rejected, including full proposals planned before an intervening annotation or human edit.
Refresh reconciles its observation with the latest annotations; an intervening schema change
requires a retry. Other graph transformations use an expected-revision check when saving.

The five packaged stores serialize atomic file publication with a short state lock. Pack copies
selected documents into a private temporary directory under this lock, then compresses and verifies
them after releasing it. The snapshot copy needs temporary disk space equal to the selected metadata
size and is removed on success or failure; it does not retain the complete snapshot in RAM.
This captures a consistent committed file state; it does not make several independent CLI commands
one transaction. Manual editors and other programs must cooperate with the same locks.

Without `--replace`, publication uses an atomic hard link: competing exports cannot overwrite a
winner. The output filesystem must support hard links; an unsupported operation fails visibly.
`--replace` atomically replaces an existing package only after successful verification.

Locks use the Python standard library (`flock` on POSIX and byte-range locking on Windows), with a
30-second acquisition timeout. OS locks are released on process exit. The small `.write.lock` and
`.state.lock` files remain so waiters always use the same inode; they are excluded from packages.
Use filesystems that support these OS locks; cross-host SMB/NFS behavior is not established by
local tests. Directory ACLs still determine who may read or write.
Snapshot capture requires access to the state lock file; a read-only copy must first be placed
in a writable local directory. Shared access permissions must cover lock files as well.

## Verification and extraction safety

`verify` checks the ZIP structure, manifest membership, sizes, SHA-256 digests, JSON contracts,
document identities, workspace graph references, and focus source references. It rejects duplicate
or case/Unicode-colliding names, absolute paths, parent traversal, backslashes, Windows-reserved names,
symlinks, encrypted ZIP members, excessive entry counts and sizes, and unsafe compression ratios.
Paths must use their canonical POSIX spelling: redundant slashes and `./` components are rejected
before extraction, including when the manifest declares them with valid checksums. Original ZIP
names are checked before Python's null-byte truncation can disguise a member path.
JSON must be UTF-8; duplicate object keys and non-finite numbers are rejected. Invalid syntax,
excessive parser nesting, and document validation failures produce ordinary CLI errors.

Extraction runs only after full verification. Files go into a temporary sibling directory, which
is renamed to the requested destination after every write succeeds. File-system failures during
setup, extraction, and publication report an error category and cause, with staging files removed
on failure. Existing destinations, including dangling symlinks, are rejected without following them.

Verification establishes package integrity and structural validity. It does not refresh or promote
revision-pinned focus snapshots. Their current/stale status remains part of the imported state and
is enforced by the normal focus and UI application paths.

## Permissions and encryption

For a local working directory, access control should initially use operating-system ownership and
ACLs. A package is a transferable artifact, so filesystem permissions alone no longer protect it
after copying. On POSIX systems, unpack creates the state root and its directories with mode `0700`
and documents with mode `0600` (a stricter umask can restrict them further). ZIP member permissions
do not grant access. Native Windows uses the destination's inherited ACLs; POSIX mode bits do not
configure Windows ACLs. Shared team access must be granted deliberately after import.
Encryption belongs around the complete package as a separate envelope, for example
`team.tarel.age`; it should not make individual ZIP members partly readable or add key management
to the metadata kernel. A later signing contract can authenticate the package revision without
changing the internal graph documents.
