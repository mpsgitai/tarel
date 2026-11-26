"""CLI surface for offline install bundles.

``tarel bundle`` alone opens the interactive dialog. ``profile``, ``components``, ``plan`` and
``build`` do the same work without questions, for scripts and for rebuilding from a recipe.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

from tarel import __version__
from tarel.bundle.application import (
    build_bundle_use_case,
    default_output,
    list_components_use_case,
    load_recipe_use_case,
    plan_bundle_use_case,
    save_recipe_use_case,
)
from tarel.bundle.contracts import BundleFailure, BundleReport, Recipe
from tarel.bundle.targets import PROFILE_COMMAND, host_profile, parse_target
from tarel.cli._args import Subcommands, add_format_argument
from tarel.cli._output import print_json
from tarel.cli._terminal import Style, is_interactive


def register(subcommands: Subcommands) -> None:
    bundle = subcommands.add_parser(
        "bundle",
        help="Build an offline install bundle for a computer without internet access.",
        description="Without a subcommand, a short dialog asks about the target computer. "
        "It offers the hub checkout named in TAREL_HUB as its default.",
    )
    commands = bundle.add_subparsers(dest="bundle_command")

    profile = commands.add_parser(
        "profile", help="Show the command that describes a target computer."
    )
    components = commands.add_parser("components", help="List what a bundle can contain.")
    plan = commands.add_parser("plan", help="Show what a build would download; downloads nothing.")
    build = commands.add_parser("build", help="Build a bundle without questions.")
    for parser in (components, plan, build):
        parser.add_argument("--hub", type=Path, help="Folder of a TAREL hub checkout.")
    for parser in (plan, build):
        parser.add_argument("--recipe", type=Path, help="Recipe file from an earlier build.")
        parser.add_argument(
            "--target",
            help="host, a pasted profile line, or e.g. windows-x86_64-py3.12, "
            "linux-x86_64-py3.12-glibc2.28.",
        )
        parser.add_argument(
            "--with",
            dest="components",
            action="append",
            default=[],
            help="Component ids, comma-separated or repeated (see `tarel bundle components`).",
        )
    build.add_argument("--output", type=Path, help="Bundle .zip path (default: current folder).")
    build.add_argument("--replace", action="store_true", help="Overwrite an existing bundle.")
    build.add_argument("--save-recipe", type=Path, help="Also write the recipe to this file.")
    build.add_argument(
        "--test-install",
        action="store_true",
        help="When this computer matches the target, also install and import the bundle in a "
        "throwaway environment. This runs the downloaded packages' code here.",
    )
    build.add_argument(
        "--tarel-from",
        type=Path,
        help="Use this TAREL wheel or source checkout instead of the release from PyPI.",
    )
    for parser in (profile, components, plan, build):
        add_format_argument(parser)


def dispatch(args: argparse.Namespace) -> int | None:
    if args.command != "bundle":
        return None
    command = args.bundle_command
    if command is None:
        return _dialog()
    if command == "profile":
        return _profile(args)
    if command == "components":
        return _components(args)
    recipe = _recipe(args)
    if command == "plan":
        return _plan(args, recipe)
    return _build(args, recipe)


def _dialog() -> int:
    from tarel.cli._bundle_dialog import Cancelled, Dialog

    if not is_interactive():
        raise BundleFailure(
            "bundle_not_interactive",
            "The dialog needs a terminal. Use `tarel bundle build --target ... --with ...`.",
        )
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    try:
        Dialog(style=Style.for_stream(sys.stdout)).run()
    except Cancelled:
        print("\n  Cancelled. Nothing was written.")
        return 130
    return 0


def _profile(args: argparse.Namespace) -> int:
    if args.format == "json":
        print_json({"command": PROFILE_COMMAND, "this_computer": host_profile()})
        return 0
    print("Run this on the target computer. It needs only Python and prints one line:")
    print()
    print(f"  {PROFILE_COMMAND}")
    print()
    print('Pass that line to `tarel bundle build --target "<line>"`, or paste it in the dialog.')
    return 0


def _components(args: argparse.Namespace) -> int:
    available = list_components_use_case(args.hub)
    if args.format == "json":
        print_json([component.to_dict() for component in available])
        return 0
    for kind, title in (("source", "Data sources"), ("extra", "Extras")):
        print(title)
        for component in (c for c in available if c.kind == kind):
            tag: str = "always" if component.always else component.origin
            if component.status != "builtin":
                tag += f", {component.status}"
            print(f"  {component.id:<14} {component.summary}  ({tag})")
        print()
    if args.hub is None:
        print("Pass --hub FOLDER to include packages from a TAREL hub checkout.")
    return 0


def _recipe(args: argparse.Namespace) -> Recipe:
    # Only `build` takes --tarel-from; `plan` has nothing to build locally.
    local = getattr(args, "tarel_from", None)
    tarel_from = local.resolve() if local is not None else None
    chosen = tuple(
        part.strip() for value in args.components for part in value.split(",") if part.strip()
    )
    if args.recipe is not None:
        if args.target or chosen:
            raise BundleFailure(
                "bundle_recipe_conflict", "Pass either --recipe or --target/--with, not both."
            )
        recipe = load_recipe_use_case(args.recipe)
        if args.hub is not None:
            recipe = dataclasses.replace(recipe, hub=args.hub.resolve())
        if tarel_from is not None:
            recipe = dataclasses.replace(recipe, tarel_from=tarel_from)
        return recipe
    if not args.target:
        raise BundleFailure(
            "bundle_target_required", "Pass --target (see `tarel bundle profile`) or --recipe."
        )
    return Recipe(
        target=parse_target(args.target),
        components=chosen,
        tarel_version=__version__,
        # Absolute, so a saved recipe finds the same checkout from any folder.
        hub=args.hub.resolve() if args.hub is not None else None,
        tarel_from=tarel_from,
    )


def _plan(args: argparse.Namespace, recipe: Recipe) -> int:
    plan = plan_bundle_use_case(recipe)
    if args.format == "json":
        print_json(plan.to_dict(), ensure_ascii=False)
        return 0
    print(f"Target:       {plan.target.label}")
    print(f"Components:   {', '.join(c.id for c in plan.components)}")
    print(f"Wheel tags:   {', '.join(plan.pip_platforms)}")
    print("Requirements:")
    for requirement in plan.requirements:
        print(f"  {requirement}")
    return 0


def _build(args: argparse.Namespace, recipe: Recipe) -> int:
    output = args.output or default_output(recipe, Path.cwd())
    text = args.format == "text"
    report = build_bundle_use_case(
        recipe,
        # Resolve the folder only: a link planted as the output file must be replaced, not
        # followed to whatever file it points at.
        output.parent.resolve() / output.name,
        replace=args.replace,
        test_install=args.test_install,
        on_step=(lambda step: print(f"  {step} ...", flush=True)) if text else (lambda _: None),
    )
    if args.save_recipe is not None:
        save_recipe_use_case(recipe, args.save_recipe)
    if not text:
        print_json(report.to_dict(), ensure_ascii=False)
        return 0
    _print_report(report)
    return 0


def _print_report(report: BundleReport) -> None:
    print()
    print(f"Bundle:   {report.path}")
    print(f"Size:     {report.size_bytes / 1_000_000:.1f} MB, {len(report.packages)} packages")
    print(f"Checked:  {report.install_check}")
    for note in report.notes:
        print(f"Note:     {note}")
