"""Bridge between the shared render layer and rich.

The MCP server flattens styled spans to plain text; the CLI paints them. Same
lines, same wording, same shape — one product, two surfaces.
"""

from __future__ import annotations

from rich.console import Console
from rich.text import Text

from .render import Line

console = Console()
err_console = Console(stderr=True)


def to_rich(lines: list[Line]) -> Text:
    out = Text()
    for index, line in enumerate(lines):
        if index:
            out.append("\n")
        for text, style in line:
            out.append(text, style=style or None)
    return out


def emit(lines: list[Line], *, stderr: bool = False) -> None:
    # soft_wrap keeps the box drawing intact on narrow terminals; rich would
    # otherwise reflow the borders into nonsense.
    target = err_console if stderr else console
    target.print(to_rich(lines), soft_wrap=True)
