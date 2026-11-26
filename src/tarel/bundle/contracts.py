"""Records for offline bundles: the target machine, the recipe, the plan, and the build report."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from tarel.errors import TarelError

BUNDLE_FORMAT = 1
RECIPE_FORMAT = 1

OperatingSystem = Literal["windows", "linux", "macos"]
Architecture = Literal["x86_64", "arm64"]
OPERATING_SYSTEMS: tuple[OperatingSystem, ...] = ("windows", "linux", "macos")
ARCHITECTURES: tuple[Architecture, ...] = ("x86_64", "arm64")

_OS_LABELS = {"windows": "Windows", "linux": "Linux", "macos": "macOS"}
_ARCH_LABELS = {"x86_64": "x86-64", "arm64": "ARM64"}
_PYTHON = re.compile(r"3\.(\d{2})")
_VERSION = re.compile(r"\d+\.\d+")
_MACHINE = re.compile(r"[A-Za-z0-9_.-]{1,32}")
# TAREL itself requires Python 3.11 or newer.
MIN_PYTHON_MINOR = 11


class BundleFailure(TarelError):
    """A bundle could not be planned, built, or read."""


@dataclass(frozen=True)
class Target:
    """The machine that will install the bundle. Only what wheel selection depends on."""

    os: OperatingSystem
    arch: Architecture
    python: str
    glibc: str | None = None
    macos: str | None = None
    # What platform.machine() reports, kept only when it differs from the wheel architecture
    # (x64 Python under Windows ARM emulation): markers see the machine, wheels the Python.
    machine: str | None = None

    def __post_init__(self) -> None:
        if self.os not in OPERATING_SYSTEMS:
            raise BundleFailure("bundle_target_os", f"Unknown operating system: {self.os!r}.")
        if self.arch not in ARCHITECTURES:
            raise BundleFailure("bundle_target_arch", f"Unknown processor: {self.arch!r}.")
        match = _PYTHON.fullmatch(self.python)
        if match is None or int(match.group(1)) < MIN_PYTHON_MINOR:
            raise BundleFailure(
                "bundle_target_python",
                f"Python {self.python!r} is not supported; TAREL needs Python 3.11 or newer.",
            )
        for name, value in (("glibc", self.glibc), ("macOS", self.macos)):
            if value is not None and not _VERSION.fullmatch(value):
                raise BundleFailure("bundle_target_version", f"Invalid {name} version: {value!r}.")
        if self.glibc is not None and self.os != "linux":
            raise BundleFailure("bundle_target_version", "A glibc version only applies to Linux.")
        if self.macos is not None and self.os != "macos":
            raise BundleFailure("bundle_target_version", "A macOS version only applies to macOS.")
        if self.machine is not None and not _MACHINE.fullmatch(self.machine):
            raise BundleFailure("bundle_target_machine", f"Invalid machine: {self.machine!r}.")

    @property
    def slug(self) -> str:
        """Short, file-name-safe identifier, e.g. ``windows-x86_64-py3.12``."""
        parts = [self.os, self.arch, f"py{self.python}"]
        if self.glibc:
            parts.append(f"glibc{self.glibc}")
        if self.macos:
            parts.append(f"macos{self.macos}")
        return "-".join(parts)

    @property
    def label(self) -> str:
        """Human description, e.g. ``Windows · x86-64 · Python 3.12``."""
        system = _OS_LABELS[self.os]
        if self.glibc:
            system += f" (glibc {self.glibc})"
        if self.macos:
            system += f" {self.macos}"
        arch = _ARCH_LABELS[self.arch]
        if self.machine:
            arch += f" (on {self.machine})"
        return f"{system} · {arch} · Python {self.python}"

    def to_dict(self) -> dict[str, str]:
        data = {"os": self.os, "arch": self.arch, "python": self.python}
        if self.glibc:
            data["glibc"] = self.glibc
        if self.macos:
            data["macos"] = self.macos
        if self.machine:
            data["machine"] = self.machine
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Target:
        try:
            return cls(
                os=data["os"],
                arch=data["arch"],
                python=str(data["python"]),
                glibc=str(data["glibc"]) if data.get("glibc") else None,
                macos=str(data["macos"]) if data.get("macos") else None,
                machine=str(data["machine"]) if data.get("machine") else None,
            )
        except KeyError as exc:
            raise BundleFailure("bundle_target_missing", f"Target is missing {exc}.") from exc


ComponentKind = Literal["source", "extra"]
ComponentOrigin = Literal["core", "hub"]


@dataclass(frozen=True)
class Component:
    """One selectable part of a bundle: a core extra or a hub package."""

    id: str
    kind: ComponentKind
    origin: ComponentOrigin
    summary: str
    status: str
    # Core: the tarel extra name, or None when the part needs nothing extra (sqlite).
    # Hub: the requirement to download, e.g. "tarel-connector-postgres[binary]".
    requirement: str | None
    hub_path: Path | None = None
    import_name: str | None = None
    always: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "origin": self.origin,
            "summary": self.summary,
            "status": self.status,
            "requirement": self.requirement,
            "always": self.always,
        }


@dataclass(frozen=True)
class Recipe:
    """Everything needed to build the same bundle again."""

    target: Target
    components: tuple[str, ...]
    tarel_version: str
    hub: Path | None = None
    # A local TAREL wheel or checkout that replaces the PyPI release; a rebuild must use it too.
    tarel_from: Path | None = None

    def to_toml(self) -> str:
        lines = [
            "# TAREL offline bundle recipe.",
            "# Rebuild the same bundle with: tarel bundle build --recipe <this file>",
            f"format = {RECIPE_FORMAT}",
            f"tarel = {_toml_string(self.tarel_version)}",
            "components = [" + ", ".join(_toml_string(c) for c in self.components) + "]",
        ]
        if self.hub is not None:
            lines.append(f"hub = {_toml_string(str(self.hub))}")
        if self.tarel_from is not None:
            lines.append(f"tarel_from = {_toml_string(str(self.tarel_from))}")
        lines += ["", "[target]"]
        lines += [f"{key} = {_toml_string(value)}" for key, value in self.target.to_dict().items()]
        return "\n".join(lines) + "\n"

    @classmethod
    def from_toml(cls, text: str) -> Recipe:
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise BundleFailure(
                "bundle_recipe_invalid", f"Recipe is not valid TOML: {exc}"
            ) from exc
        if data.get("format") != RECIPE_FORMAT:
            raise BundleFailure(
                "bundle_recipe_format", f"Unsupported recipe format: {data.get('format')!r}."
            )
        components = data.get("components")
        if not isinstance(components, list) or not all(isinstance(c, str) for c in components):
            raise BundleFailure("bundle_recipe_invalid", "Recipe components must be a list.")
        target = data.get("target")
        if not isinstance(target, dict):
            raise BundleFailure("bundle_recipe_invalid", "Recipe needs a [target] table.")
        hub = data.get("hub")
        tarel_from = data.get("tarel_from")
        return cls(
            target=Target.from_dict(target),
            components=tuple(components),
            tarel_version=str(data.get("tarel", "")),
            hub=Path(hub) if isinstance(hub, str) and hub else None,
            tarel_from=Path(tarel_from) if isinstance(tarel_from, str) and tarel_from else None,
        )


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


@dataclass(frozen=True)
class BundlePlan:
    """What a build will download, before anything is downloaded."""

    target: Target
    components: tuple[Component, ...]
    requirements: tuple[str, ...]
    pip_platforms: tuple[str, ...]
    tarel_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target.to_dict(),
            "target_label": self.target.label,
            "tarel_version": self.tarel_version,
            "components": [component.to_dict() for component in self.components],
            "requirements": list(self.requirements),
            "pip_platforms": list(self.pip_platforms),
        }


InstallCheck = Literal["installed", "resolved"]


@dataclass(frozen=True)
class BundledPackage:
    name: str
    version: str
    license: str


@dataclass(frozen=True)
class BundleReport:
    """The finished bundle and how far it was proven to install."""

    path: Path
    size_bytes: int
    target: Target
    packages: tuple[BundledPackage, ...]
    install_check: InstallCheck
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "size_bytes": self.size_bytes,
            "target": self.target.to_dict(),
            "packages": [
                {"name": p.name, "version": p.version, "license": p.license} for p in self.packages
            ],
            "install_check": self.install_check,
            "notes": list(self.notes),
        }
