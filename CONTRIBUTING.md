# Contributing to TAREL

TAREL welcomes focused bug fixes, documentation improvements, and small features that strengthen
its analytics context compiler.

## Before changing code

- Open an issue before changing a core contract, graph identity rule, persisted format, connector
  boundary, or context packet.
- Keep generated connectors inactive until a human has reviewed their permissions and queries.
- Never commit credentials, connection URLs, local database targets, samples, `.tarel/` state, or
  model files.
- Keep new runtime dependencies optional unless the core cannot reasonably provide the required
  behavior with the Python standard library.

## Where code lives

TAREL has two entry adapters over one set of use cases. A change usually touches three places.

| Layer | Location | Rule |
| --- | --- | --- |
| CLI | `src/tarel/cli/<group>.py` | `register(subcommands)` adds the argparse tree, `dispatch(args)` calls use cases and renders. No domain logic. |
| SDK | `src/tarel/sdk/<facade>.py` | One facade class per `Tarel` attribute; methods forward to use cases with the client's runtime. |
| Use cases | `src/tarel/<domain>/application.py` | The only functions the CLI, SDK and browser call. They accept `runtime: TarelRuntime \| None`. |
| Domain | `src/tarel/<domain>/contracts.py`, `core.py`, `store.py`, ... | Typed records with `from_dict`/`to_dict`, pure logic, file stores. Never import `cli` or `sdk`. |
| State | `src/tarel/runtime.py` | `TarelRuntime` owns the `.tarel` directory and every store in it; `resolve_runtime(runtime)` supplies the `./.tarel` default. |
| Errors | `src/tarel/errors.py` | Every domain failure subclasses `TarelError(code, message)`. |

To add a command group, write `cli/<group>.py` with `register` and `dispatch` and append the module
to `COMMANDS` in `cli/__init__.py`. To add an SDK facade, subclass `RuntimeAPI` from
`sdk/_base.py` and wire it in `sdk/client.py`. Keep modules focused; when one grows past roughly
500 lines, split it by responsibility rather than by size alone.

## Development setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

Before opening a pull request, run:

```bash
ruff check src tests tools
mypy
python -m unittest discover -s tests -q
python -m compileall -q src tests tools
python -m build
python tools/check_distribution.py dist
python tools/generate_cli_reference.py --check
python tools/check_docs.py
python tools/generate_code_map.py --check
python tools/smoke_demo.py > /dev/null
```

Experiments that need optional runtimes or private state live in `tools/evals/` and are not part of
the unit suite; see its README.

`mypy` checks every module except the type-debt list in `pyproject.toml`; when you fix a listed
module, delete it from that list.

`tools/smoke_demo.py` runs the CLI and SDK end to end against the built-in retail demo. Its
normalized transcript is deterministic, so diffing it before and after a refactor shows any
user-visible change.

Pull requests should explain the concrete use case, the evidence behind semantic or connector
behavior, and any intentionally changed CLI or serialized output. Add focused tests for behavior
that could regress. Live-system tests must use ignored local configuration and must never expose
their targets in logs or fixtures.

By submitting a contribution, you agree that it is licensed under the repository's MIT License.

For command or SDK changes, run `python tools/generate_cli_reference.py` and commit the updated
reference. After adding, moving or renaming modules, regenerate `REFACTOR_DOCUMENTATION.md` with
`python tools/generate_code_map.py`. Update the CLI generator's curated notes when behavior
changes. Shared formats and invariants belong in `docs/contracts.md`; executable examples belong
in the demo or workshop.
