"""Layout primitives for ``--format pretty``: the human reading mode of the CLI.

``text`` stays the stable, line-oriented output scripts already parse; ``json`` is for agents.
``pretty`` is only for people at a terminal: titled sections, aligned tables, lineage as a tree,
bars for coverage. It is built from the same payloads as the other formats, so it shows the same
facts and never more.

Everything is plain standard library. Colour follows :class:`~tarel.cli._terminal.Style`
(terminal only, never with ``NO_COLOR``), symbols fall back to ASCII on consoles that cannot
encode them, and the width follows the terminal (``COLUMNS`` overrides it, which also makes the
output deterministic in tests). Long cells are cut with an ellipsis, never wrapped mid-table.
"""

from __future__ import annotations

import re
import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TextIO

from tarel.cli._terminal import Style
from tarel.errors import TarelError

_MIN_WIDTH, _MAX_WIDTH = 60, 160

Styler = Callable[[str], str]


@dataclass
class Pretty:
    """A page of pretty output, collected as lines and printed once."""

    style: Style
    width: int
    lines: list[str] = field(default_factory=list)

    @classmethod
    def for_stdout(cls) -> Pretty:
        return cls.for_stream(sys.stdout)

    @classmethod
    def for_stream(cls, stream: TextIO) -> Pretty:
        columns = shutil.get_terminal_size((100, 24)).columns
        return cls(Style.for_stream(stream), max(_MIN_WIDTH, min(columns, _MAX_WIDTH)))

    # -- output -------------------------------------------------------------------------------

    def emit(self, stream: TextIO | None = None) -> None:
        target = stream if stream is not None else sys.stdout
        text = "\n".join(self.lines)
        if not self.style.unicode:
            encoding = getattr(target, "encoding", None) or "ascii"
            text = text.encode(encoding, errors="replace").decode(encoding)
        print(text, file=target)

    def add(self, value: str = "") -> None:
        self.lines.append(value)

    # -- building blocks ----------------------------------------------------------------------

    def header(self, kind: str, subject: str, tags: Sequence[str] = ()) -> None:
        """``KIND  subject  [tag · tag]`` and a rule under it."""
        dot = f" {self.style.symbol('dot')} "
        suffix = f"  {self.style.dim('[' + dot.join(tags) + ']')}" if tags else ""
        self.add(f"{self.style.bold(kind.upper())}  {self.style.accent(subject)}{suffix}")
        self.rule()

    def rule(self, indent: int = 0) -> None:
        self.add(" " * indent + self.style.dim(self.style.symbol("rule") * (self.width - indent)))

    def summary(self, parts: Sequence[str]) -> None:
        """One line of facts joined by a middle dot, e.g. ``40 systems · 103 graphs``."""
        values = [item for item in parts if item]
        if values:
            self.text(f" {self.style.symbol('dot')} ".join(values), indent=2)

    def section(self, title: str, count: int | None = None) -> None:
        self.add()
        suffix = f" ({count:,})" if count is not None else ""
        self.add(f"  {self.style.bold(title.upper())}{suffix}")

    def text(
        self, value: str, indent: int = 4, styler: Styler | None = None, *, hang: int = 0,
    ) -> None:
        """Wrapped text; continuation lines are indented ``hang`` columns further."""
        width = self.width - indent
        for number, line in enumerate(_wrap(value, width, hang)):
            prefix = " " * (indent + (hang if number else 0))
            self.add(prefix + (styler(line) if styler else line))

    def bullets(
        self, values: Sequence[str], *, indent: int = 4, limit: int | None = None,
        more_hint: str = "",
    ) -> None:
        shown = values if limit is None else values[:limit]
        for value in shown:
            line = f"{self.style.symbol('bullet')} {value}"
            self.add(" " * indent + self.fit(line, self.width - indent))
        hidden = len(values) - len(shown)
        if hidden > 0:
            note = f"{self.style.symbol('ellipsis')} +{hidden:,} more{more_hint}"
            self.add(" " * indent + self.style.dim(note))

    def table(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        *,
        right: Sequence[int] = (),
        stylers: Mapping[int, Styler] | None = None,
        indent: int = 2,
        flex: int | None = None,
        cut_left: Sequence[int] = (),
    ) -> None:
        """Aligned columns that fit the width: ``flex`` shrinks first, then the widest column.

        Columns in ``cut_left`` lose their beginning instead of their end, for paths whose
        file name matters more than the directories leading to it.
        """
        if not rows:
            return
        # A column that is empty in every row says nothing; leave it out.
        keep = [0, *(index for index in range(1, len(headers)) if any(row[index] for row in rows))]
        if len(keep) < len(headers):
            remap = {old: new for new, old in enumerate(keep)}
            right = [remap[index] for index in right if index in remap]
            stylers = {remap[i]: s for i, s in (stylers or {}).items() if i in remap}
            cut_left = [remap[index] for index in cut_left if index in remap]
            flex = remap.get(flex) if flex is not None else None
            headers = [headers[index] for index in keep]
            rows = [[row[index] for index in keep] for row in rows]
        count = len(headers)
        widths = [
            max(len(headers[index]), *(len(row[index]) for row in rows)) for index in range(count)
        ]
        available = self.width - indent - 2 * (count - 1)
        # Shrink the flex column first, then always the currently widest one, so one long
        # column cannot push the others off the screen.
        # The first column names the row, so it keeps its width while any other column can give.
        floor = [widths[0], *(max(len(item), 6) for item in headers[1:])]
        if flex is not None and sum(widths) > available:
            widths[flex] = max(floor[flex], widths[flex] - (sum(widths) - available))
        for floors in (floor, [max(len(headers[0]), 6), *floor[1:]]):
            while sum(widths) > available:
                index = max(range(count), key=lambda item: (widths[item] - floors[item], -item))
                if widths[index] <= floors[index]:
                    break
                widths[index] -= 1
        aligned, left_cut = set(right), set(cut_left)
        styles = stylers or {}

        def cells(values: Sequence[str], styled: bool) -> str:
            parts = []
            for index, value in enumerate(values):
                fitted = self.fit(value, widths[index], left=index in left_cut)
                padded = fitted.rjust(widths[index]) if index in aligned else fitted.ljust(
                    widths[index]
                )
                if styled and index in styles and value:
                    padded = padded.replace(fitted, styles[index](fitted), 1)
                parts.append(padded)
            return (" " * indent + "  ".join(parts)).rstrip()

        self.add(self.style.dim(cells(headers, False)))
        self.rule(indent)
        for row in rows:
            self.add(cells(row, True))

    def bar(self, ratio: float, width: int = 16) -> str:
        ratio = min(max(ratio, 0.0), 1.0)
        filled = round(ratio * width)
        full, empty = self.style.symbol("full"), self.style.symbol("empty")
        return self.style.good(full * filled) + self.style.dim(empty * (width - filled))

    def tree(
        self,
        root: str,
        children: Mapping[str, Sequence[tuple[str, str, str]]],
        label: Callable[[str], str],
        *,
        indent: int = 2,
    ) -> None:
        """Draw ``root`` and its descendants; ``children[node]`` is ``[(edge, child, note)]``.

        A node reached a second time is printed once more, marked "see above", but not expanded
        again, so diamonds and cycles stay finite and readable.
        """
        self.add(" " * indent + label(root))
        expanded = {root}

        def walk(node: str, prefix: str) -> None:
            kids = children.get(node, ())
            for position, (edge, child, extra) in enumerate(kids):
                last = position == len(kids) - 1
                branch = self.style.symbol("elbow" if last else "tee")
                repeat = child in expanded
                note = self.style.dim("  (see above)") if repeat and children.get(child) else ""
                tail = f"  {self.style.dim(extra)}" if extra else ""
                line = f"{prefix}{self.style.dim(branch)} {edge} {label(child)}{tail}{note}"
                self.add(" " * indent + line)
                if not repeat:
                    expanded.add(child)
                    walk(child, prefix + ("   " if last else pipe))

        pipe = self.style.dim(self.style.symbol("pipe")) + " "

        walk(root, "")

    def footer(
        self,
        facts: Sequence[tuple[str, str]] = (),
        *,
        limits: Sequence[str] = (),
        warnings: Sequence[str] = (),
        hints: Sequence[str] = (),
    ) -> None:
        if not (facts or limits or warnings or hints):
            return
        self.add()
        self.rule(2)
        label_width = max([len(name) for name, _ in facts] + [len("Warning"), len("Limit")])
        for name, value in facts:
            self.add(f"  {self.style.dim((name + ':').ljust(label_width + 1))} {value}")
        for value in limits:
            self.add(f"  {self.style.dim('Limit:'.ljust(label_width + 1))} {value}")
        mark = self.style.warn(self.style.symbol("warn"))
        for value in warnings:
            for number, line in enumerate(_wrap(value, self.width - 4)):
                self.add(f"  {mark if number == 0 else ' '} {self.style.warn(line)}")
        for value in hints:
            self.add(f"  {self.style.dim('Next:'.ljust(label_width + 1))} {value}")

    def fit(self, value: str, width: int, *, left: bool = False) -> str:
        if visible_len(value) <= width:
            return value
        # Cutting through a colour code would leave the terminal coloured; cut plain text.
        value = _ANSI.sub("", value)
        ellipsis = self.style.symbol("ellipsis")
        keep = max(width - len(ellipsis), 0)
        return ellipsis + value[len(value) - keep:] if left else value[:keep] + ellipsis

    def state(self, value: str | None) -> str:
        """An annotation or review state with its conventional colour."""
        if not value:
            return self.style.dim("unannotated")
        if value == "validated":
            return self.style.good(value)
        if value in {"rejected"}:
            return self.style.bad(value)
        return self.style.warn(value)


def render_error(exc: TarelError, stream: TextIO) -> None:
    """A failure as a short block on stderr: what failed, why, and how to retry."""
    page = Pretty.for_stream(stream)
    style = page.style
    page.add(f"{style.bad(style.symbol('fail') + ' Error')} {style.dim('[' + exc.code + ']')}")
    page.text(str(exc), indent=2)
    details = exc.details
    rows: list[tuple[str, str]] = []
    if exc.hint:
        rows.append(("Hint", exc.hint))
    suggestion = details.get("suggestion")
    if isinstance(suggestion, dict):
        flags = [f"--lineage {item}" for item in suggestion.get("lineages", ())]
        flags += [f"--graph {item}" for item in suggestion.get("graphs", ())]
        if flags:
            rows.append(("Suggestion", " ".join(flags)))
    elif isinstance(suggestion, list) and suggestion:
        rows.append(("Suggestion", " or ".join(str(item) for item in suggestion)))
    preview = details.get("accepted_preview")
    if isinstance(preview, list) and preview:
        total = details.get("accepted_count")
        more = (
            f" {style.symbol('ellipsis')} ({total:,} total)"
            if isinstance(total, int) and total > len(preview)
            else ""
        )
        rows.append(("Accepted", ", ".join(str(item) for item in preview) + more))
    candidates = details.get("candidates")
    if isinstance(candidates, list) and candidates:
        ids = [str(item.get("id")) for item in candidates[:5] if isinstance(item, dict)]
        rows.append(("Candidates", ", ".join(ids)))
    rows.append(("Retry", "yes, with the changes above" if exc.retryable else "no"))
    if rows:
        page.add()
        width = max(len(name) for name, _ in rows) + 1
        for name, value in rows:
            page.add(f"  {style.dim((name + ':').ljust(width))} {value}")
    page.emit(stream)


_ANSI = re.compile(r"\033\[[0-9;]*m")


def visible_len(value: str) -> int:
    """Length as the terminal shows it, without colour codes."""
    return len(_ANSI.sub("", value))


def _wrap(value: str, width: int, hang: int = 0) -> list[str]:
    lines: list[str] = []
    for paragraph in value.splitlines() or [""]:
        words = paragraph.split(" ")
        current = ""
        for word in words:
            candidate = f"{current} {word}" if current else word
            limit = width - (hang if lines else 0)
            if visible_len(candidate) > limit and current:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
    return lines
