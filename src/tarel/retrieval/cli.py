"""Thin CLI over shared retrieval configuration and model discovery."""

from __future__ import annotations

import argparse
import json

from tarel.retrieval.catalog import list_models
from tarel.retrieval.contracts import RetrievalFailure
from tarel.retrieval.local import DEFAULT_MODEL_NAME
from tarel.retrieval.settings import ModelChoice, RetrievalSettings, load_settings, save_settings


def add_retrieval_commands(commands: argparse._SubParsersAction) -> None:
    parser = commands.add_parser(
        "retrieval", help="Select independent embedding and reranker models."
    )
    subcommands = parser.add_subparsers(dest="retrieval_command", required=True)
    status = subcommands.add_parser("settings", help="Show credential-free retrieval settings.")
    configure = subcommands.add_parser(
        "configure", help="Save model selection; does not download or index."
    )
    for task in ("embedding", "reranker"):
        configure.add_argument(
            f"--{task}-provider",
            help="local or a configured HTTP profile; none disables reranking.",
        )
        configure.add_argument(f"--{task}-model", help=f"Model ID for {task}.")
        configure.add_argument(f"--{task}-model-path", help="Explicit local GGUF path.")
    configure.add_argument("--rerank-depth", type=int, help="Maximum candidates to rerank (1–100).")
    models = subcommands.add_parser(
        "models", help="List supported local models or fetch a provider catalog."
    )
    models.add_argument("--provider", default="local")
    models.add_argument("--task", choices=("embedding", "reranker"), default="embedding",
                        help="Requested retrieval model capability.")
    for subcommand in (status, configure, models):
        subcommand.add_argument("--format", choices=("text", "json"), default="text")


def dispatch_retrieval(args: argparse.Namespace) -> int | None:
    if args.command != "retrieval":
        return None
    if args.retrieval_command == "models":
        result = list_models(provider=args.provider, task=args.task)
    elif args.retrieval_command == "settings":
        result = load_settings(None).to_dict()
    else:
        current = load_settings(None)
        choices = {}
        for task in ("embedding", "reranker"):
            previous = getattr(current, task)
            provider = getattr(args, f"{task}_provider") or (
                previous.provider if previous else "none"
            )
            model = getattr(args, f"{task}_model")
            path = getattr(args, f"{task}_model_path")
            if provider == "none":
                if task == "embedding" or model is not None or path is not None:
                    raise RetrievalFailure(
                        "invalid_retrieval_settings", "Only a reranker can be disabled."
                    )
                choices[task] = None
                continue
            same_provider = previous is not None and previous.provider == provider
            if model is None:
                if same_provider:
                    model = previous.model
                elif provider == "local":
                    model = (
                        DEFAULT_MODEL_NAME if task == "embedding" else "qwen3-reranker-0.6b-q4-k-m"
                    )
                else:
                    raise RetrievalFailure(
                        "invalid_retrieval_settings", "Select a model when changing HTTP providers."
                    )
            if path is None and same_provider and previous.model == model:
                path = previous.model_path
            choices[task] = ModelChoice(provider, model, path)
        settings = RetrievalSettings(
            choices["embedding"],
            choices["reranker"],
            args.rerank_depth if args.rerank_depth is not None else current.rerank_depth,
        )
        result = save_settings(None, settings)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
