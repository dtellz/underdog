from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """Shared state across the underdog graph.

    `messages` uses the add_messages reducer so each node can append
    incrementally. `findings` is the deduped raw set gathered from tool
    results; `evaluated` is what survived LLM scoring; `report` is the
    final markdown render.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    topic: str
    findings: list[dict[str, Any]]
    evaluated: list[dict[str, Any]]
    report: str
