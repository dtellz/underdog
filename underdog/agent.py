"""LangGraph workflow for The Underdog.

Graph:

    scout ──tool_calls?──▶ tools ──▶ scout
      │                                │
      └──no tool_calls──▶ collect ─▶ evaluate ─▶ report ─▶ END

The scout is an LLM bound to the search tools. It loops until it stops
emitting tool calls. `collect` pulls structured results out of the
ToolMessages (the LLM never has to hand-summarise them), `evaluate` asks
the LLM to score each finding, and `report` renders markdown.
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from .llm import get_llm
from .log import detail, event, format_args, warn
from .state import AgentState
from .tools import ALL_TOOLS

MAX_TOOL_ROUNDS = 5  # hard cap to prevent infinite scout loops

SCOUT_SYSTEM = f"""You are **The Underdog**, a sharp scout for AI-powered game development tools.

Mission: given a topic, hunt across GitHub, Reddit, and Hacker News for newly
released or newsworthy AI tools relevant to game development (engines,
procedural content, NPC dialogue, asset generation, animation, playtesting,
dev workflow, etc.).

HARD LIMITS (do not exceed):
- Make AT MOST {MAX_TOOL_ROUNDS} tool-call turns total.
- Each turn, issue 1–3 tool calls in parallel — do not call the same tool
  with the same arguments twice.
- Use `fetch_url` at most once, and only for a clearly promising candidate.

Rules of engagement:
- Cover DIFFERENT sources and angles (github + reddit + hackernews).
- Vary the subreddit (gamedev, IndieDev, proceduralgeneration, Unity3D,
  unrealengine, godot) and query wording.
- Prefer recency (< 60 days) and a clear AI/ML angle.

Stopping: once you have covered 2–3 sources OR gathered enough signal,
reply with a short plain-text note like "scouting complete — N candidates"
and DO NOT call any more tools. Never try to list findings in prose; the
system collects them from your tool calls automatically.
"""

EVALUATOR_SYSTEM = """You are a discerning reviewer of AI-powered game-dev tools.

For each candidate below, score it on a 0–10 scale based on:
- novelty (genuinely new or hype recycling?)
- relevance to game development (actually useful for building games?)
- credibility (repo has traction / source is reputable / not vaporware?)

Return STRICT JSON of the form:
{"items": [
  {"title": "...", "url": "...", "score": 0-10,
   "verdict": "keep" | "drop",
   "reasoning": "one or two sentences"}
]}

Mark verdict "keep" only if score >= 6. Output nothing except the JSON object.
"""


def _extract_json(text: str) -> dict[str, Any] | None:
    """Extract the first top-level JSON object from a string, if any."""
    if not text:
        return None
    # Fast path: the whole thing is JSON.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fenced code block.
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    # Fallback: first {...} by brace matching.
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _parse_tool_content(content: Any) -> Any:
    if isinstance(content, (list, dict)):
        return content
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None
    return None


def build_graph():
    llm = get_llm()
    llm_with_tools = llm.bind_tools(ALL_TOOLS)
    _tool_node = ToolNode(ALL_TOOLS)

    def tool_node(state: AgentState) -> dict[str, Any]:
        event("tools", "dispatching…")
        result = _tool_node.invoke(state)
        for msg in result.get("messages", []):
            if not isinstance(msg, ToolMessage):
                continue
            data = _parse_tool_content(msg.content)
            if isinstance(data, list):
                detail(f"[magenta]{msg.name}[/] → {len(data)} results")
            elif isinstance(data, str):
                detail(f"[magenta]{msg.name}[/] → {len(data)} chars")
            else:
                preview = str(msg.content)[:60].replace("\n", " ")
                detail(f"[magenta]{msg.name}[/] → {preview}")
        return result

    def scout(state: AgentState) -> dict[str, Any]:
        event("scout", "thinking…")
        response = llm_with_tools.invoke(state["messages"])
        tool_calls = getattr(response, "tool_calls", None) or []
        if tool_calls:
            for tc in tool_calls:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "?")
                args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                detail(f"[magenta]{name}[/]({format_args(args)})")
        else:
            text = (response.content or "").strip() if isinstance(response.content, str) else ""
            detail(f"done — {text[:80] or 'no tool calls'}")
        return {"messages": [response]}

    def route_after_scout(state: AgentState) -> str:
        last = state["messages"][-1]
        has_tool_calls = isinstance(last, AIMessage) and bool(getattr(last, "tool_calls", None))
        if not has_tool_calls:
            return "collect"
        rounds = sum(
            1
            for m in state["messages"]
            if isinstance(m, AIMessage) and getattr(m, "tool_calls", None)
        )
        if rounds > MAX_TOOL_ROUNDS:
            warn(f"tool-call cap reached ({MAX_TOOL_ROUNDS}); forcing stop")
            # Drop pending tool_calls so downstream nodes don't try to dispatch them.
            last.tool_calls = []
            return "collect"
        return "tools"

    def collect(state: AgentState) -> dict[str, Any]:
        event("collect", "deduping tool results…")
        findings: list[dict[str, Any]] = []
        seen: set[str] = set()
        raw = 0
        for msg in state["messages"]:
            if not isinstance(msg, ToolMessage):
                continue
            data = _parse_tool_content(msg.content)
            if not isinstance(data, list):
                continue
            for item in data:
                if not isinstance(item, dict):
                    continue
                raw += 1
                url = item.get("url")
                if not url or url in seen:
                    continue
                seen.add(url)
                findings.append(item)
        detail(f"{raw} raw → {len(findings)} unique candidates")
        return {"findings": findings}

    def evaluate(state: AgentState) -> dict[str, Any]:
        findings = state.get("findings", [])
        event("evaluate", f"scoring {len(findings)} candidates…")
        if not findings:
            warn("nothing to score")
            return {"evaluated": []}
        # Trim each finding so the evaluator prompt stays compact.
        compact = [
            {
                "title": f.get("title"),
                "url": f.get("url"),
                "source": f.get("source"),
                "description": (f.get("description") or "")[:300],
                "signal": {
                    k: f[k]
                    for k in ("stars", "score", "points", "comments", "updated", "created")
                    if k in f
                },
            }
            for f in findings
        ]
        resp = llm.invoke(
            [
                SystemMessage(content=EVALUATOR_SYSTEM),
                HumanMessage(
                    content=(
                        f"Topic: {state.get('topic','')}\n\n"
                        f"Candidates (JSON):\n{json.dumps(compact, indent=2)}"
                    )
                ),
            ]
        )
        parsed = _extract_json(resp.content if isinstance(resp.content, str) else str(resp.content))
        if not parsed:
            warn("evaluator output was not valid JSON")
            return {"evaluated": []}
        items = [i for i in parsed.get("items", []) if i.get("verdict") == "keep"]
        items.sort(key=lambda x: x.get("score", 0), reverse=True)
        detail(f"kept {len(items)} / {len(findings)}")
        return {"evaluated": items}

    def report(state: AgentState) -> dict[str, Any]:
        event("report", "rendering markdown…")
        topic = state.get("topic", "")
        items = state.get("evaluated", [])
        raw_count = len(state.get("findings", []))
        lines = [f"# The Underdog Report — {topic}\n"]
        lines.append(f"_Scouted **{raw_count}** candidates, kept **{len(items)}**._\n")
        if not items:
            lines.append("No worthwhile findings this run. Try a more specific topic.")
        else:
            for i, item in enumerate(items, 1):
                lines.append(f"## {i}. {item.get('title','(untitled)')}  ·  score {item.get('score','?')}/10")
                lines.append(f"- URL: {item.get('url','?')}")
                reason = item.get("reasoning", "").strip()
                if reason:
                    lines.append(f"- Why: {reason}")
                lines.append("")
        return {"report": "\n".join(lines)}

    g = StateGraph(AgentState)
    g.add_node("scout", scout)
    g.add_node("tools", tool_node)
    g.add_node("collect", collect)
    g.add_node("evaluate", evaluate)
    g.add_node("report", report)

    g.set_entry_point("scout")
    g.add_conditional_edges("scout", route_after_scout, {"tools": "tools", "collect": "collect"})
    g.add_edge("tools", "scout")
    g.add_edge("collect", "evaluate")
    g.add_edge("evaluate", "report")
    g.add_edge("report", END)
    return g.compile()


def initial_state(topic: str) -> AgentState:
    return {
        "messages": [
            SystemMessage(content=SCOUT_SYSTEM),
            HumanMessage(content=f"Topic: {topic}\nBegin scouting."),
        ],
        "topic": topic,
        "findings": [],
        "evaluated": [],
        "report": "",
    }
