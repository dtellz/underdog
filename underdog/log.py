"""Terse progress logging for the graph.

One shared Rich console so CLI output and node-level events don't fight
each other. Every event is a single line, emoji-free by default.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console

console = Console()


def event(node: str, message: str) -> None:
    """Top-level graph transition, e.g. a node starting work."""
    console.print(f"[bold cyan]▸ {node}[/]  {message}")


def detail(message: str) -> None:
    """Sub-event under the most recent node (tool calls, counts, etc.)."""
    console.print(f"  [dim]·[/] {message}")


def warn(message: str) -> None:
    console.print(f"  [yellow]! {message}[/]")


def format_args(args: dict[str, Any] | None, max_len: int = 80) -> str:
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        s = repr(v) if not isinstance(v, str) else f'"{v}"'
        parts.append(f"{k}={s}")
    out = ", ".join(parts)
    return out if len(out) <= max_len else out[: max_len - 1] + "…"
