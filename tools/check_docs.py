"""Check documentation links and concrete CLI example syntax without execution."""

from __future__ import annotations

import ast
import re
import shlex
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tarel.cli import build_parser  # noqa: E402


def prose(text: str) -> str:
    return re.sub(r"^```[^\n]*\n.*?^```[^\n]*$", "", text, flags=re.M | re.S)


def anchors(text: str) -> set[str]:
    found: set[str] = set()
    counts: dict[str, int] = {}
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", prose(text), re.M):
        base = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        number = counts.get(base, 0)
        found.add(base if not number else f"{base}-{number}")
        counts[base] = number + 1
    return found


def main() -> int:
    files = sorted(ROOT.glob("*.md")) + sorted((ROOT / "docs").glob("*.md"))
    files += sorted((ROOT / "src").rglob("*.md"))
    files += sorted((ROOT / "tools").rglob("*.md"))
    errors = []
    checked = 0
    for path in files:
        text = path.read_text()
        for target in re.findall(r'\]\(([^\s)]+)(?:\s+"[^"]*")?\)', prose(text)):
            if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                continue
            relative, _, fragment = unquote(target).partition("#")
            resolved = (path.parent / relative).resolve() if relative else path
            if not resolved.exists():
                errors.append(f"{path.relative_to(ROOT)}: missing {target}")
            elif (
                fragment
                and resolved.suffix == ".md"
                and fragment not in anchors(resolved.read_text())
            ):
                errors.append(f"{path.relative_to(ROOT)}: missing anchor {target}")
            checked += 1
    parser = build_parser()
    examples = 0
    # Contract documents can include shell loops; their payloads are covered by domain tests.
    for name in ("cli-reference.md", "architecture.md", "workshop.md", "retail-demo.md"):
        text = (ROOT / "docs" / name).read_text()
        for block in re.findall(r"```bash\n(.*?)```", text, re.S):
            for line in block.replace("\\\n", " ").splitlines():
                if not line.startswith("tarel "):
                    continue
                args = shlex.split(line, comments=True)[1:]
                for symbol in (">", ">>", "|", "2>"):
                    if symbol in args:
                        args = args[: args.index(symbol)]
                if "--help" in args:
                    continue
                if args[0] == "context" and args[1] not in {
                    "build",
                    "prefix",
                    "diff",
                    "impact",
                    "expand",
                }:
                    args.insert(1, "build")
                try:
                    parser.parse_args(args)
                except SystemExit:
                    errors.append(f"{name}: invalid example {line}")
                examples += 1
        if name == "cli-reference.md":
            examples_text = text.split("### SDK method reference")[0]
            for block in re.findall(r"```python\n(.*?)```", examples_text, re.S):
                ast.parse(block)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Documentation: {checked} internal links and {examples} CLI examples checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
