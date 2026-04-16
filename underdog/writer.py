"""JSON persistence for a scout run.

Layout (relative to `data_dir`, default `docs/data`):

    data/
      index.json            # list of all runs, newest first
      runs/
        YYYY-MM-DD.json     # one document per run

The run document is self-contained (no DB, no server). The frontend in
`docs/` loads `index.json`, picks a run, then fetches the corresponding
run file.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .state import AgentState


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_run_id() -> str:
    # Minute precision so multiple runs in the same day (different topics)
    # don't overwrite each other, while still sorting chronologically.
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M")


def _source_breakdown(findings: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for f in findings:
        src = f.get("source", "unknown")
        out[src] = out.get(src, 0) + 1
    return out


def _enriched_findings(
    raw: list[dict[str, Any]],
    evaluated: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge evaluator scores with the raw tool payloads by URL."""
    raw_by_url = {f.get("url"): f for f in raw if f.get("url")}
    merged = []
    for rank, e in enumerate(evaluated, 1):
        url = e.get("url")
        src = raw_by_url.get(url, {})
        merged.append(
            {
                "rank": rank,
                "title": e.get("title") or src.get("title"),
                "url": url,
                "source": src.get("source", "unknown"),
                "score": e.get("score"),
                "verdict": e.get("verdict"),
                "reasoning": (e.get("reasoning") or "").strip(),
                "description": (src.get("description") or "").strip(),
                "signal": {
                    k: src[k]
                    for k in (
                        "stars",
                        "score",
                        "points",
                        "comments",
                        "updated",
                        "created",
                        "topics",
                    )
                    if k in src
                },
            }
        )
    return merged


def build_run_document(state: AgentState, model: str, run_id: str) -> dict[str, Any]:
    findings = state.get("findings", []) or []
    evaluated = state.get("evaluated", []) or []
    return {
        "id": run_id,
        "topic": state.get("topic", ""),
        "model": model,
        "generated_at": _now_iso(),
        "stats": {
            "scouted": len(findings),
            "kept": len(evaluated),
            "sources": _source_breakdown(findings),
        },
        "findings": _enriched_findings(findings, evaluated),
    }


def _update_index(data_dir: Path, doc: dict[str, Any]) -> None:
    index_path = data_dir / "index.json"
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            index = {"runs": []}
    else:
        index = {"runs": []}

    run_id = doc["id"]
    index["runs"] = [r for r in index.get("runs", []) if r.get("id") != run_id]
    index["runs"].insert(
        0,
        {
            "id": run_id,
            "topic": doc.get("topic", ""),
            "generated_at": doc.get("generated_at"),
            "kept": doc.get("stats", {}).get("kept", 0),
            "scouted": doc.get("stats", {}).get("scouted", 0),
            "top_score": max(
                (f.get("score", 0) for f in doc.get("findings", [])),
                default=0,
            ),
            "file": f"runs/{run_id}.json",
        },
    )
    # Newest first by generated_at (string-sortable ISO timestamps).
    index["runs"].sort(key=lambda r: r.get("generated_at") or "", reverse=True)
    index["updated_at"] = _now_iso()
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")


def write_run(
    state: AgentState,
    model: str,
    data_dir: Path,
    run_id: str | None = None,
) -> tuple[Path, Path]:
    """Persist a run and refresh the index. Returns (run_path, index_path)."""
    run_id = run_id or _default_run_id()
    doc = build_run_document(state, model, run_id)

    runs_dir = data_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_path = runs_dir / f"{run_id}.json"
    run_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    _update_index(data_dir, doc)
    return run_path, data_dir / "index.json"
