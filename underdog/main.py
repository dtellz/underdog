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
from .writer import write_run


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
        "--data-dir",
        type=Path,
        default=Path("docs/data"),
        help="Where to write run JSON + index (consumed by the docs/ site).",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Override the run id (default: today's UTC date, YYYY-MM-DD).",
    )
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Skip writing JSON. Useful for dry runs.",
    )
    parser.add_argument(
        "--save-markdown",
        type=Path,
        default=None,
        help="Optional path to ALSO write the final markdown report to.",
    )
    args = parser.parse_args()

    model = os.getenv("LLAMA_MODEL", "qwen3.6-35b-a3b")
    server = os.getenv("LLAMA_SERVER_URL", "http://localhost:8080/v1")

    console.print(
        Panel.fit(
            f"[bold magenta]The Underdog[/]\n"
            f"[cyan]topic:[/] {args.topic}\n"
            f"[cyan]model:[/] {model}\n"
            f"[cyan]server:[/] {server}",
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

    if not args.no_persist:
        run_path, index_path = write_run(
            state=result,
            model=model,
            data_dir=args.data_dir,
            run_id=args.run_id,
        )
        console.print(
            f"\n[green]Wrote[/] {run_path}\n"
            f"[green]Updated[/] {index_path}"
        )

    if args.save_markdown:
        args.save_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.save_markdown.write_text(report_md, encoding="utf-8")
        console.print(f"[green]Saved markdown to[/] {args.save_markdown}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
