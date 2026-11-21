"""`tarel model`: download and inspect local embedding models."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tarel.cli._args import Subcommands, add_format_argument
from tarel.cli._output import print_json
from tarel.retrieval.application import (
    download_embedding_model_use_case,
    embedding_model_status_use_case,
)
from tarel.retrieval.local import DEFAULT_MODEL_NAME


def register(subcommands: Subcommands) -> None:
    """Add the `model` command group to the top-level parser."""
    model = subcommands.add_parser("model", help="Manage optional local embedding models.")
    model_commands = model.add_subparsers(dest="model_command")

    model_download = model_commands.add_parser(
        "download",
        help="Download and verify the recommended local embedding model.",
    )
    model_download.add_argument("--name", default=DEFAULT_MODEL_NAME)
    model_download.add_argument("--target", type=Path)
    model_download.add_argument("--force", action="store_true")
    add_format_argument(model_download)

    model_status = model_commands.add_parser(
        "status",
        help="Check the recommended model path and checksum.",
    )
    model_status.add_argument("--name", default=DEFAULT_MODEL_NAME)
    model_status.add_argument("--model", type=Path, dest="model_path")
    add_format_argument(model_status)



def dispatch(args: argparse.Namespace) -> int | None:
    """Run a parsed `model` command; return ``None`` for other commands."""
    if args.command != "model":
        return None
    command = args.model_command
    handler = _HANDLERS.get(command)
    if handler is not None:
        return handler(args)
    return None


def _model_download_progress(downloaded: int, total: int) -> None:
    interval = 25 * 1024 * 1024
    previous = max(0, downloaded - 1024 * 1024)
    if downloaded == total or downloaded // interval != previous // interval:
        percentage = min(100, round(downloaded * 100 / max(total, 1)))
        print(f"Downloading embedding model: {percentage}%", file=sys.stderr)


def _run_download(args: argparse.Namespace) -> int:
    result = download_embedding_model_use_case(
        name=args.name,
        target=args.target,
        force=args.force,
        progress=_model_download_progress,
    )
    payload = {
        "model": result.spec.name,
        "path": str(result.path),
        "reused": result.reused,
        "sha256": result.spec.sha256,
        "size": result.spec.size,
        "source": result.spec.source,
    }
    if args.format == "json":
        print_json(payload)
    else:
        print(f"Model: {result.spec.name}")
        print(f"Status: {'already present' if result.reused else 'downloaded'}")
        print(f"Path: {result.path}")
        print(f"SHA-256: {result.spec.sha256}")
    return 0


def _run_status(args: argparse.Namespace) -> int:
    payload = embedding_model_status_use_case(
        name=args.name,
        model_path=args.model_path,
    )
    if args.format == "json":
        print_json(payload)
    else:
        print(f"Model: {payload['model']}")
        print(f"Path: {payload['path']}")
        print(f"Status: {'ready' if payload['sha256_valid'] else 'missing or invalid'}")
    return 0 if payload["sha256_valid"] else 1


_HANDLERS = {
    "download": _run_download,
    "status": _run_status,
}
