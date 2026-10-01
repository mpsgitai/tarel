# Portable `.tarel` packages

TAREL's editable source of truth remains a normal `.tarel/` directory containing readable JSON
documents. A file ending in `.tarel` is the portable snapshot form for review, transfer, and
backup. It is an ordinary ZIP container so that the contents remain inspectable with standard
operating-system tools. The package layer uses only the Python standard library.

The first package contract is `tarel.package.v0.1`. `application/vnd.tarel+zip` is currently a
project media type, not an IANA-registered type. The package contract has its own version and does
not inherit the installed TAREL version.

## Commands

```console
tarel package pack --state .tarel --workspace team --output team.tarel
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

Packing one workspace includes its graphs, all lineage and knowledge documents in the state
root, and focus snapshots whose graph and lineage sources are present. This broad auxiliary scope
is explicit in the manifest because the current workspace contract does not yet assign lineage or
knowledge documents to a workspace. An invalid selected document fails the package operation.

The allowlist excludes selective graph caches, search indexes, lineage analysis caches, connector
and provider configuration, credentials, logs, raw samples, source rows, and analytical results.
Indexes are rebuilt after import when needed.

## Verification and extraction safety

`verify` checks the ZIP structure, manifest membership, sizes, SHA-256 digests, JSON contracts,
document identities, workspace graph references, and focus source references. It rejects duplicate
or case-colliding names, absolute paths, parent traversal, backslashes, Windows-reserved names,
symlinks, encrypted ZIP members, excessive entry counts and sizes, and unsafe compression ratios.
JSON must be UTF-8 and duplicate object keys are rejected.

Extraction runs only after full verification. Files go into a temporary sibling directory, which
is renamed to the requested destination after every write succeeds.

Verification establishes package integrity and structural validity. It does not refresh or promote
revision-pinned focus snapshots. Their current/stale status remains part of the imported state and
is enforced by the normal focus and UI application paths.

## Permissions and encryption

For a local working directory, access control should initially use operating-system ownership and
ACLs. A package is a transferable artifact, so filesystem permissions alone no longer protect it
after copying. Encryption belongs around the complete package as a separate envelope, for example
`team.tarel.age`; it should not make individual ZIP members partly readable or add key management
to the metadata kernel. A later signing contract can authenticate the package revision without
changing the internal graph documents.
