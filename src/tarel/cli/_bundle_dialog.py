"""The interactive ``tarel bundle`` dialog: three short steps, sensible defaults, one summary.

Only asks questions and renders answers; every decision is made by ``tarel.bundle.application``.
Input is numbered choices plus Enter, which works the same in every console, over SSH, and in
Windows ``cmd.exe``, without any terminal library.
"""

from __future__ import annotations

import os
import textwrap
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from tarel import __version__
from tarel.bundle.application import (
    build_bundle_use_case,
    default_output,
    list_components_use_case,
    save_recipe_use_case,
)
from tarel.bundle.contracts import (
    ARCHITECTURES,
    BundleFailure,
    BundleReport,
    Component,
    OperatingSystem,
    Recipe,
    Target,
)
from tarel.bundle.targets import PROFILE_COMMAND, host_target, parse_profile
from tarel.cli._terminal import Style

_WIDTH = 56
_PYTHON_CHOICES = ("3.12", "3.11", "3.13")
_SUMMARY = 40


def _short(summary: str) -> str:
    """Hub descriptions end in "for TAREL, ..."; inside TAREL that part says nothing."""
    text = summary.split(" for TAREL", 1)[0]
    return text if len(text) <= _SUMMARY else text[: _SUMMARY - 3] + "..."


class Cancelled(Exception):
    """The person left the dialog (Ctrl+C, Ctrl+D, or declined the summary)."""


@dataclass
class Dialog:
    style: Style
    ask: Callable[[str], str] = input
    say: Callable[[str], None] = print
    folder: Path = Path()

    # -- building blocks -------------------------------------------------------------------

    def rule(self) -> None:
        self.say("")
        self.say("  " + self.style.dim(self.style.symbol("rule") * _WIDTH))
        self.say("")

    def heading(self, number: int, title: str) -> None:
        self.say(f"  {self.style.accent(str(number))}  {self.style.bold(title)}")
        self.say("")

    def prompt(self, label: str, default: str = "") -> str:
        hint = f" [{default}]" if default else ""
        try:
            answer = self.ask(f"  {label}{self.style.dim(hint)}: ").strip()
        except (EOFError, KeyboardInterrupt) as exc:
            raise Cancelled from exc
        return answer or default

    def choose(self, question: str, options: Sequence[tuple[str, str]], default: int = 1) -> int:
        """One numbered choice. Returns the zero-based index."""
        self.say(f"     {question}")
        for index, (label, note) in enumerate(options, start=1):
            pointer = self.style.accent(self.style.symbol("pointer")) if index == default else " "
            extra = f"   {self.style.dim(note)}" if note else ""
            self.say(f"     {pointer} {index}  {label}{extra}")
        self.say("")
        while True:
            answer = self.prompt("Choice", str(default))
            if answer.isdigit() and 1 <= int(answer) <= len(options):
                self.say("")
                return int(answer) - 1
            self.say(f"  {self.style.dim(f'Please type a number from 1 to {len(options)}.')}")

    def choose_many(self, question: str, items: Sequence[Component], preset: set[str]) -> set[str]:
        self.say(f"     {question}   {self.style.dim('(numbers separated by spaces)')}")
        width = max(len(item.id) for item in items)
        for index, item in enumerate(items, start=1):
            status = (
                "" if item.status == "builtin" else f" {self.style.symbol('dot')} {item.status}"
            )
            note = self.style.dim(f"{item.origin}{status}")
            summary = _short(item.summary)
            self.say(f"       {index:>2}  {item.id:<{width}}  {summary:<{_SUMMARY}}  {note}")
        self.say("")
        default = " ".join(str(i) for i, c in enumerate(items, start=1) if c.id in preset)
        while True:
            answer = self.prompt("Choice", default or "none")
            if answer in ("none", "-", "0"):
                self.say("")
                return set()
            numbers = answer.replace(",", " ").split()
            if numbers and all(n.isdigit() and 1 <= int(n) <= len(items) for n in numbers):
                self.say("")
                return {items[int(n) - 1].id for n in numbers}
            self.say(f"  {self.style.dim('Type numbers from the list, or none.')}")

    def done(self, text: str) -> None:
        self.say(f"  {self.style.good(self.style.symbol('ok'))} {self.style.text(text)}")

    # -- the three steps -------------------------------------------------------------------

    def run(self) -> BundleReport:
        self.say("")
        self.say(f"  {self.style.bold('TAREL offline bundle')}")
        self.say("  Build a package for a computer without internet access.")
        self.rule()
        target = self.ask_target()
        self.rule()
        hub = self.ask_hub()
        self.rule()
        chosen = self.ask_components(hub)
        recipe = Recipe(target=target, components=chosen, tarel_version=__version__, hub=hub)
        self.rule()
        output = default_output(recipe, self.folder)
        self.summary(recipe, output)
        if self.prompt("Build the bundle?", "Y/n").lower() not in ("y", "yes", "y/n"):
            raise Cancelled
        self.say("")
        report = self.build(recipe, output)
        recipe_path = output.with_suffix(".toml")
        save_recipe_use_case(recipe, recipe_path)
        self.finish(report, recipe_path)
        return report

    def ask_target(self) -> Target:
        self.heading(1, "Target computer")
        choice = self.choose(
            "How do you want to describe it?",
            [
                ("Paste a profile from the target", "most accurate"),
                ("Choose it myself", ""),
                ("Same as this computer", self.style.text(host_target().label)),
            ],
        )
        target = (self.paste_profile, self.pick_target, host_target)[choice]()
        self.done(target.label)
        return target

    def paste_profile(self) -> Target:
        self.say("     Run this on the target computer and paste the line it prints:")
        self.say("")
        self.say(f"       {self.style.accent(PROFILE_COMMAND)}")
        self.say("")
        windows_hint = "On Windows, type py instead of python if python is not found."
        self.say(f"     {self.style.dim(windows_hint)}")
        self.say("")
        while True:
            line = self.prompt("Profile")
            try:
                target = parse_profile(line)
            except BundleFailure as exc:
                self.say(f"  {self.style.bad(self.style.symbol('fail'))} {exc}")
                continue
            self.say("")
            return target

    def pick_target(self) -> Target:
        systems: tuple[OperatingSystem, ...] = ("windows", "linux", "macos")
        os_name = systems[
            self.choose("Operating system", [("Windows", ""), ("Linux", ""), ("macOS", "")])
        ]
        processors = [("Intel / AMD", "x86-64"), ("ARM", "e.g. Snapdragon, Graviton, Apple")]
        arch = ARCHITECTURES[self.choose("Processor", processors)]
        python = _PYTHON_CHOICES[
            self.choose("Python on the target", [(v, "") for v in _PYTHON_CHOICES])
        ]
        glibc = macos = None
        if os_name == "linux":
            hint = "On the target, `ldd --version` shows the glibc version."
            self.say(f"     {self.style.dim(hint)}")
            glibc = self.ask_version("glibc version", "2.28")
        if os_name == "macos":
            macos = self.ask_version("Oldest macOS version", "11.0")
        return Target(os=os_name, arch=arch, python=python, glibc=glibc, macos=macos)

    def ask_version(self, label: str, default: str) -> str:
        while True:
            value = self.prompt(label, default)
            parts = value.split(".")
            if len(parts) == 2 and all(p.isdigit() for p in parts):
                self.say("")
                return value
            self.say(f"  {self.style.dim('Type a version like ' + default + '.')}")

    def ask_hub(self) -> Path | None:
        self.heading(2, "TAREL hub")
        self.say("     Folder of your TAREL hub checkout, for connectors beyond the core.")
        default = os.environ.get("TAREL_HUB", "")
        hint = "Type none to use only the core." if default else "Press Enter to use only the core."
        self.say(f"     {self.style.dim(hint)}")
        self.say("")
        while True:
            answer = self.prompt("Hub folder", default)
            if not answer or answer.lower() == "none":
                self.done("Core only")
                return None
            hub = Path(answer).expanduser().resolve()
            try:
                count = sum(c.origin == "hub" for c in list_components_use_case(hub))
            except BundleFailure as exc:
                self.say(f"  {self.style.bad(self.style.symbol('fail'))} {exc}")
                continue
            self.say("")
            self.done(f"{count} hub packages found")
            return hub

    def ask_components(self, hub: Path | None) -> tuple[str, ...]:
        self.heading(3, "What should be included?")
        available = list_components_use_case(hub)
        always = [c for c in available if c.always]
        sources = [c for c in available if c.kind == "source" and not c.always]
        extras = [c for c in available if c.kind == "extra"]
        for component in always:
            self.say(f"     {self.style.good(self.style.symbol('ok'))} {component.summary}")
        self.say("")
        chosen = self.choose_many("Data sources", sources, preset={"sqlserver"})
        if extras:
            chosen |= self.choose_many("Extras", extras, preset=set())
        return tuple(c.id for c in available if c.id in chosen)

    # -- summary and build -----------------------------------------------------------------

    def summary(self, recipe: Recipe, output: Path) -> None:
        available = {c.id: c for c in list_components_use_case(recipe.hub)}
        parts = [available[i] for i in recipe.components]
        sources = [c.id for c in parts if c.kind == "source"] or ["none"]
        extras = [c.id for c in parts if c.kind == "extra"] or ["none"]
        self.say(f"  {self.style.bold('Summary')}")
        self.say("")
        rows = [
            ("Target", self.style.text(recipe.target.label)),
            ("TAREL", recipe.tarel_version),
            ("Sources", ", ".join(["sqlite", *sources])),
            ("Extras", ", ".join(extras)),
            ("Saved to", str(output)),
        ]
        for label, value in rows:
            self.say(f"     {self.style.dim(f'{label:<10}')}  {value}")
        self.say("")

    def build(self, recipe: Recipe, output: Path) -> BundleReport:
        progress = _Progress(self)
        try:
            report = build_bundle_use_case(recipe, output, on_step=progress.step)
        except BaseException:
            progress.fail()
            raise
        progress.finish()
        return report

    def finish(self, report: BundleReport, recipe_path: Path) -> None:
        size = f"{report.size_bytes / 1_000_000:.1f} MB"
        count = f"{len(report.packages)} packages"
        dot = self.style.symbol("dot")
        self.say("")
        details = self.style.dim(f"{size} {dot} {count}")
        self.say(f"  {self.style.bold('Done.')}  {report.path.name}  {details}")
        for note in report.notes:
            self.say("")
            lines = textwrap.wrap(note, width=_WIDTH + 14)
            self.say(f"  {self.style.dim('Note:')} {lines[0]}")
            for line in lines[1:]:
                self.say(f"        {line}")
        self.say("")
        self.say("  On the target computer:")
        self.say("     1. Unzip the file")
        self.say("     2. Follow INSTALL.md: two commands, no internet needed")
        self.say("")
        self.say("  Build the same bundle again:")
        self.say(f"     {self.style.accent(f'tarel bundle build --recipe {recipe_path}')}")
        self.say("")


class _Progress:
    """One line per step; on a terminal the running step turns into a check mark in place."""

    def __init__(self, dialog: Dialog) -> None:
        self.dialog = dialog
        self.current: str | None = None

    def step(self, text: str) -> None:
        self.finish()
        self.current = self.dialog.style.text(text)
        style = self.dialog.style
        if style.live:
            print(self._busy_line(), end="", flush=True)

    def finish(self) -> None:
        self._close(ok=True)

    def fail(self) -> None:
        self._close(ok=False)

    def _busy_line(self) -> str:
        style = self.dialog.style
        return f"  {style.dim(style.symbol('busy'))} {self.current} ..."

    def _close(self, *, ok: bool) -> None:
        if self.current is None:
            return
        style = self.dialog.style
        mark = style.good(style.symbol("ok")) if ok else style.bad(style.symbol("fail"))
        line = f"  {mark} {self.current}"
        if style.live:
            # Carriage return plus padding works in every console, with or without ANSI support.
            width = len(self._busy_line())
            print("\r" + line + " " * max(0, width - len(line)), flush=True)
        else:
            self.dialog.say(line)
        self.current = None
