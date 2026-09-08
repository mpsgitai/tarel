# TAREL documentation

Start with the [Retail DWH demo](retail-demo.md) for a local, credential-free walkthrough.

| Guide | Use it to |
| --- | --- |
| [CLI reference](cli-reference.md) | Look up every command, argument, default, result, and related contract |
| [Architecture and extensions](architecture.md) | Understand the graph, adapter boundaries, and reviewed self-modification |
| [Demo warehouse](retail-demo.md) | Build and inspect a reproducible source |
| [Three-day workshop](workshop.md) | Apply TAREL to an enterprise landscape with a harness |

The [contract reference](contracts.md) documents formats and shared rules. The
[Python SDK](cli-reference.md#python-sdk) uses the same application paths as the CLI.

The CLI reference is generated from the parser and curated notes. Run
`python tools/generate_cli_reference.py` after changing commands or SDK signatures;
CI checks that the generated page stays current. CLI syntax examples are templates unless a
demo explicitly supplies their resources. Provider calls and database queries require the
corresponding configuration.

[Project README](../README.md)
