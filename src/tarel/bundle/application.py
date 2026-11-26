"""Use cases for offline bundles. The CLI dialog and the plain commands both call only these."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from tarel import __version__
from tarel.bundle.builder import StepCallback, build_bundle
from tarel.bundle.catalog import available_components, select_components
from tarel.bundle.contracts import BundleFailure, BundlePlan, BundleReport, Component, Recipe
from tarel.bundle.targets import pip_platforms


def list_components_use_case(hub: Path | None) -> tuple[Component, ...]:
    return available_components(hub)


def plan_bundle_use_case(recipe: Recipe) -> BundlePlan:
    """Resolve the recipe into exact requirements without downloading anything."""
    if recipe.tarel_version != __version__:
        raise BundleFailure(
            "bundle_version_mismatch",
            f"The recipe asks for TAREL {recipe.tarel_version}, but this is TAREL {__version__}. "
            f"Run the bundle command with TAREL {recipe.tarel_version}.",
        )
    components = select_components(available_components(recipe.hub), recipe.components)
    extras = sorted(c.requirement for c in components if c.origin == "core" and c.requirement)
    tarel = "tarel" + (f"[{','.join(extras)}]" if extras else "") + f"=={__version__}"
    hub = [c.requirement for c in components if c.origin == "hub" and c.requirement]
    return BundlePlan(
        target=recipe.target,
        components=components,
        requirements=(tarel, *hub),
        pip_platforms=pip_platforms(recipe.target),
        tarel_version=__version__,
    )


def build_bundle_use_case(
    recipe: Recipe,
    output: Path,
    *,
    replace: bool = False,
    on_step: StepCallback = lambda _: None,
) -> BundleReport:
    """Build the bundle for ``recipe`` into the ZIP file ``output``."""
    if output.suffix != ".zip":
        raise BundleFailure("bundle_output_suffix", f"The bundle file must end in .zip: {output}.")
    if output.exists() and not replace:
        raise BundleFailure(
            "bundle_output_exists", f"{output} already exists. Pass --replace to overwrite it."
        )
    if not output.parent.is_dir():
        raise BundleFailure("bundle_output_folder", f"Folder does not exist: {output.parent}.")
    plan = plan_bundle_use_case(recipe)
    return build_bundle(plan, output, tarel_from=recipe.tarel_from, on_step=on_step)


def default_output(recipe: Recipe, folder: Path) -> Path:
    return folder / f"tarel-offline-{recipe.tarel_version}-{recipe.target.slug}.zip"


def load_recipe_use_case(path: Path) -> Recipe:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise BundleFailure("bundle_recipe_missing", f"No recipe at {path}.") from exc
    return Recipe.from_toml(text)


def save_recipe_use_case(recipe: Recipe, path: Path) -> None:
    """Write the recipe next to the bundle; like the bundle, never through a planted link."""
    handle, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".partial", dir=path.parent)
    partial = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(recipe.to_toml())
        partial.chmod(0o644)
        partial.replace(path)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
