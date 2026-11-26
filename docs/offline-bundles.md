# Offline bundles

An offline bundle carries TAREL and the hub packages you choose to a computer without internet
access, such as a server in a restricted on-premises network. It is a plain ZIP file:

```
tarel-offline-0.0.6-windows-x86_64-py3.12/
  wheels/             unmodified wheels as published upstream, plus locally built hub packages
  requirements.lock   every wheel, pinned by version and SHA-256 hash
  bundle.json         target, components, and packages with their licenses
  licenses/           the license files every wheel carries
  INSTALL.md          the install commands for this target
```

The target needs Python and pip, nothing else. A bundle contains no executable, installer
script, or self-extracting archive, so virus scanners see nothing unusual.

## Build a bundle

On a computer with internet access and TAREL installed, run:

```bash
tarel bundle
```

A short dialog asks three things:

1. **The target computer.** The most accurate way is to run one command there and paste the
   line it prints; `tarel bundle profile` shows that command. It needs only Python. You can
   also choose the system yourself or use this computer.
2. **The TAREL hub.** The folder of a hub checkout, for connectors beyond the core. The
   environment variable `TAREL_HUB` sets the default. Type `none` (or press Enter without a
   default) to use only the core.
3. **What to include.** Data sources and extras, from the core and from the hub catalog.

After a summary, TAREL downloads the wheels, pins them by hash, tests the bundle, and writes
the ZIP file plus a recipe (`.toml`) next to it.

Without the dialog, for scripts:

```bash
tarel bundle components --hub ../tarel-hub
tarel bundle plan --target windows-x86_64-py3.12 --with sqlserver,postgres --hub ../tarel-hub
tarel bundle build --target "tarel-target:1 cpython win-amd64 3.12 AMD64 - -" --with sqlserver
tarel bundle build --recipe tarel-offline-0.0.6-windows-x86_64-py3.12.toml
```

`--tarel-from PATH` bundles an unreleased TAREL wheel or source checkout instead of the PyPI
release. Locally built wheels, from `--tarel-from` and from the hub, always replace a downloaded
wheel of the same project, even when both carry the same version number. A saved recipe keeps the
`--tarel-from` path, so `--recipe` rebuilds from the same source.

`--target` accepts `host`, a pasted profile line, or a short name such as
`windows-x86_64-py3.12`, `linux-arm64-py3.13-glibc2.31`, or `macos-arm64-py3.12-macos14.0`.
A Linux name without glibc assumes glibc 2.28.

## Install on the target

Unzip the file and, inside its folder, run the commands from `INSTALL.md`. On Windows:

```
py -3.12 -I -m venv .venv
.venv\Scripts\python -I -m pip install --no-index --find-links wheels --require-hashes -r requirements.lock
.venv\Scripts\tarel --version
```

`-I` keeps Python from importing anything from the bundle folder, which may be writable by
others. `--no-index` stops pip from contacting any server. `--require-hashes` makes pip refuse any file
whose hash differs from `requirements.lock`, so a damaged or swapped file stops the install.

The hashes detect damage and mix-ups, not a deliberate swap of the whole bundle: whoever can
change the wheels can also change the lock file. Whether a bundle is genuine depends on the
transfer path, as for any other file brought into the network.

## What the build checks

- **Dependencies for the target, not for this computer.** `pip download --platform` picks wheels
  for the target but evaluates environment markers such as `sys_platform == "win32"` for the
  computer it runs on. TAREL therefore downloads each package without its dependencies, walks
  the dependency closure with the target's markers, downloads what is missing, and removes what
  the target would never install. Every version constraint on a package counts, from every
  package that needs it. Unlike pip, the walk does not fall back to older versions of a
  package when constraints conflict; the build stops and names who needs which version.
  Dependencies given by URL are refused, because the offline install takes every file from
  `wheels/`.
- **Wheels only.** Source distributions are refused, so nothing is compiled on the target.
- **Native libraries inside the wheel.** When a hub package offers a `binary` extra (for example
  PostgreSQL's bundled libpq), the bundle always takes it; an offline target cannot install
  system libraries later.
- **Every file against the target.** Each wheel is checked against the target's tags, Python
  version, and hash, even when a real install follows: a newer computer also accepts wheels that
  need a newer glibc or macOS than the target has.
- **A real install where possible.** When this computer matches the target (system, processor,
  Python, and a glibc or macOS version at least as new), the bundle is also installed offline
  into a fresh virtual environment and every included package is imported. Otherwise the report
  says the bundle was only resolved. Install it once on a matching test computer before rollout.
- **Repeatable.** The same recipe and the same upstream wheels give a byte-identical ZIP file:
  sorted entries and fixed timestamps. The bundle records no build time, host name, or path.
