"""Describe a target machine and translate it into the wheel platform tags pip understands."""

from __future__ import annotations

import platform
import re
import sys
import sysconfig

from tarel.bundle.contracts import Architecture, BundleFailure, OperatingSystem, Target

PROFILE_PREFIX = "tarel-target:1"

# Run on the target. Standard library only, and free of `%`, `$` and nested double quotes so it
# can be pasted unchanged into cmd.exe, PowerShell, and POSIX shells.
PROFILE_COMMAND = (
    'python -c "import platform as p,sys,sysconfig as s;'
    "print('tarel-target:1',sys.implementation.name,s.get_platform(),"
    "'.'.join(map(str,sys.version_info[:2]))+('t' if s.get_config_var('Py_GIL_DISABLED') else ''),"
    "p.machine(),"
    "'-'.join(p.libc_ver()),p.mac_ver()[0] or '-')\""
)

# Oldest glibc baseline that manylinux wheels are still built for (manylinux2014).
_OLDEST_GLIBC_MINOR = 17
_32_BIT = {"win32", "i686", "i386", "x86", "armv7l", "armv6l"}
_MACHINES: dict[str, Architecture] = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "arm64": "arm64",
    "aarch64": "arm64",
}


def host_profile() -> str:
    """The profile line this machine would print; lets "same as this machine" share one parser."""
    libc = "-".join(platform.libc_ver())
    python = ".".join(map(str, sys.version_info[:2]))
    if sysconfig.get_config_var("Py_GIL_DISABLED"):
        python += "t"
    return " ".join(
        (
            PROFILE_PREFIX,
            sys.implementation.name,
            sysconfig.get_platform(),
            python,
            platform.machine(),
            libc,
            platform.mac_ver()[0] or "-",
        )
    )


def host_target() -> Target:
    return parse_profile(host_profile())


def parse_profile(line: str) -> Target:
    """Read the line printed by :data:`PROFILE_COMMAND`."""
    fields = line.strip().split()
    if len(fields) != 7 or fields[0] != PROFILE_PREFIX:
        raise BundleFailure(
            "bundle_profile_invalid",
            "That is not a target profile. Run `tarel bundle profile` to see the command to use.",
        )
    _, implementation, build_platform, python, machine, libc, mac_version = fields
    if implementation != "cpython":
        raise BundleFailure(
            "bundle_profile_python", f"Only CPython targets are supported, not {implementation}."
        )
    if python.endswith("t"):
        # Free-threaded CPython needs cp3XXt wheels, which few native packages publish yet.
        raise BundleFailure(
            "bundle_profile_python",
            f"The target runs free-threaded Python {python}; use the regular build there.",
        )
    arch = _arch_from_platform(build_platform, machine)
    os_name = _os_from_platform(build_platform)
    glibc = None
    macos = None
    if os_name == "linux":
        name, _, version = libc.partition("-")
        if name != "glibc" or not version:
            raise BundleFailure(
                "bundle_profile_libc",
                "Only glibc-based Linux is supported (musl, e.g. Alpine, has too few wheels).",
            )
        glibc = ".".join(version.split(".")[:2])
    if os_name == "macos" and mac_version != "-":
        macos = macos_baseline(mac_version)
    return Target(os=os_name, arch=arch, python=python, glibc=glibc, macos=macos)


def macos_baseline(version: str) -> str:
    """The wheel-tag version of a macOS release: 10.x keeps its minor, 11 and later do not."""
    major, _, rest = version.partition(".")
    minor = rest.split(".")[0] if major == "10" and rest else "0"
    return f"{major}.{minor}"


def _arch_from_platform(build_platform: str, machine: str) -> Architecture:
    """The architecture of the Python that loads the wheels, which can differ from the machine.

    Windows on ARM runs x64 Python under emulation, and 64-bit Windows runs 32-bit Python; the
    build platform says which one the target uses. Only a macOS universal2 build runs natively
    either way, so there the machine decides.
    """
    suffix = build_platform.rsplit("-", 1)[-1].lower()
    if suffix == "universal2":
        suffix = machine.lower()
    arch = _MACHINES.get(suffix)
    if arch is not None:
        return arch
    if suffix in _32_BIT:
        raise BundleFailure(
            "bundle_profile_arch",
            f"The target runs 32-bit Python ({build_platform}); install 64-bit Python there.",
        )
    raise BundleFailure(
        "bundle_profile_arch", f"Unsupported processor: {build_platform} on {machine}."
    )


def _os_from_platform(build_platform: str) -> OperatingSystem:
    if build_platform.startswith("win"):
        return "windows"
    if build_platform.startswith("linux"):
        return "linux"
    if build_platform.startswith("macosx"):
        return "macos"
    raise BundleFailure("bundle_profile_os", f"Unsupported operating system: {build_platform}.")


_SLUG_OS: dict[str, OperatingSystem] = {"windows": "windows", "linux": "linux", "macos": "macos"}
_SLUG = re.compile(
    r"(?P<os>windows|linux|macos)-(?P<arch>x86_64|arm64)-py(?P<python>3\.\d+)"
    r"(?:-glibc(?P<glibc>\d+\.\d+))?(?:-macos(?P<macos>\d+\.\d+))?"
)


def parse_target(text: str) -> Target:
    """Read ``host``, a profile line, or a slug such as ``linux-x86_64-py3.12-glibc2.28``."""
    text = text.strip()
    if text == "host":
        return host_target()
    if text.startswith(PROFILE_PREFIX):
        return parse_profile(text)
    match = _SLUG.fullmatch(text)
    if match is None:
        raise BundleFailure(
            "bundle_target_invalid",
            f"Unknown target {text!r}. Use e.g. windows-x86_64-py3.12, "
            "linux-x86_64-py3.12-glibc2.28, or host.",
        )
    os_name = _SLUG_OS[match.group("os")]
    glibc = match.group("glibc")
    if os_name == "linux" and glibc is None:
        glibc = "2.28"
    return Target(
        os=os_name,
        arch=_MACHINES[match.group("arch")],
        python=match.group("python"),
        glibc=glibc,
        macos=match.group("macos") or ("11.0" if os_name == "macos" else None),
    )


def pip_platforms(target: Target) -> tuple[str, ...]:
    """Every platform tag a wheel may carry and still install on ``target``, best first."""
    if target.os == "windows":
        return ("win_amd64",) if target.arch == "x86_64" else ("win_arm64",)
    if target.os == "linux":
        machine = "x86_64" if target.arch == "x86_64" else "aarch64"
        major, minor = (int(part) for part in (target.glibc or "2.28").split("."))
        if major != 2 or minor < _OLDEST_GLIBC_MINOR:
            raise BundleFailure(
                "bundle_target_glibc", f"glibc {target.glibc} is older than manylinux2014 (2.17)."
            )
        tags = [f"manylinux_2_{m}_{machine}" for m in range(minor, _OLDEST_GLIBC_MINOR - 1, -1)]
        return (*tags, f"manylinux2014_{machine}")
    # pip expands one macOS tag to every older macOS release and to universal2 itself.
    version = (target.macos or "11.0").replace(".", "_")
    machine = "x86_64" if target.arch == "x86_64" else "arm64"
    return (f"macosx_{version}_{machine}",)


def can_test_install(target: Target, host: Target) -> bool:
    """True when a bundle for ``target`` can really be installed on ``host`` as a test."""
    if (target.os, target.arch, target.python) != (host.os, host.arch, host.python):
        return False
    if target.os == "linux":
        return _version_tuple(host.glibc) >= _version_tuple(target.glibc)
    if target.os == "macos":
        return _version_tuple(host.macos) >= _version_tuple(target.macos)
    return True


def _version_tuple(value: str | None) -> tuple[int, ...]:
    return tuple(int(part) for part in (value or "0.0").split("."))
