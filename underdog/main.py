from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.markdown import Markdown
from rich.panel import Panel

from .agent import build_graph, initial_state
from .log import console


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="underdog",
        description="The Underdog — scout for AI-powered game dev tools.",
    )
    parser.add_argument(
        "topic",
        nargs="?",
        default="newly released AI-powered game development tools",
        help="Topic / angle to scout for.",
    )
    parser.add_argument(
        "--recursion-limit",
        type=int,
        default=80,
        help="Hard cap on LangGraph node transitions. Scout is capped at "
        "5 tool-call rounds regardless; this is just a safety net.",
    )
    parser.add_argument(
        "--save",
        type=Path,
        default=None,
        help="Optional path to write the final markdown report to.",
    )
    args = parser.parse_args()

    console.print(
        Panel.fit(
            f"[bold magenta]The Underdog[/]\n"
            f"[cyan]topic:[/] {args.topic}\n"
            f"[cyan]model:[/] {os.getenv('LLAMA_MODEL', 'qwen3.6-35b-a3b')}\n"
            f"[cyan]server:[/] {os.getenv('LLAMA_SERVER_URL', 'http://localhost:8080/v1')}",
            border_style="magenta",
        )
    )

    graph = build_graph()
    try:
        result = graph.invoke(
            initial_state(args.topic),
            config={"recursion_limit": args.recursion_limit},
        )
    except Exception as e:
        console.print(f"[bold red]Graph failed:[/] {e}")
        return 1

    report_md = result.get("report", "(no report produced)")
    console.rule("[bold green]Report[/]")
    console.print(Markdown(report_md))

    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(report_md, encoding="utf-8")
        console.print(f"\n[green]Saved report to[/] {args.save}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
