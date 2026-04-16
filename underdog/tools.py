"""Search tools the scout can call during the ReAct loop.

Each tool returns a list of plain dicts with a consistent shape so the
`collect` node can dedupe them by URL without special-casing the source.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup
from langchain_core.tools import tool

USER_AGENT = "the-underdog/0.1 (AI gamedev news scout; contact: local)"
HTTP_TIMEOUT = 20


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    h = {"User-Agent": USER_AGENT}
    if extra:
        h.update(extra)
    return h


@tool
def search_github(query: str, days: int = 45, limit: int = 15) -> list[dict[str, Any]]:
    """Search GitHub for recently-pushed repositories matching a query.

    Use this to find newly released or actively developed AI-powered
    game-dev tools. `query` should be a focused phrase such as
    "generative AI level design" or "LLM npc dialogue". `days` bounds
    recency by the last-pushed date.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    q = f"{query} pushed:>{since}"
    r = requests.get(
        "https://api.github.com/search/repositories",
        params={"q": q, "sort": "stars", "order": "desc", "per_page": limit},
        headers=_headers({"Accept": "application/vnd.github+json"}),
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    items = r.json().get("items", [])
    return [
        {
            "source": "github",
            "title": it["full_name"],
            "url": it["html_url"],
            "description": (it.get("description") or "")[:500],
            "stars": it.get("stargazers_count", 0),
            "updated": it.get("pushed_at"),
            "topics": it.get("topics", []),
        }
        for it in items
    ]


@tool
def search_reddit(query: str, subreddit: str = "gamedev", limit: int = 20) -> list[dict[str, Any]]:
    """Search a subreddit for posts matching a query (sorted by new, last month).

    Good subreddits: gamedev, IndieDev, GameDevelopment, proceduralgeneration,
    Unity3D, unrealengine, godot. Use to surface community chatter about
    tools, demos, and controversies.
    """
    r = requests.get(
        f"https://www.reddit.com/r/{subreddit}/search.json",
        params={
            "q": query,
            "restrict_sr": "on",
            "sort": "new",
            "t": "month",
            "limit": limit,
        },
        headers=_headers(),
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    children = r.json().get("data", {}).get("children", [])
    out = []
    for c in children:
        d = c.get("data", {})
        out.append(
            {
                "source": f"reddit/{subreddit}",
                "title": d.get("title"),
                "url": "https://www.reddit.com" + d.get("permalink", ""),
                "description": (d.get("selftext") or "")[:500],
                "score": d.get("score", 0),
                "comments": d.get("num_comments", 0),
                "created": d.get("created_utc"),
                "external_url": d.get("url_overridden_by_dest"),
            }
        )
    return out


@tool
def search_hackernews(query: str, limit: int = 15) -> list[dict[str, Any]]:
    """Search Hacker News (via Algolia) for recent stories matching a query.

    Great for discovering tech-forward tool launches and long-form
    commentary. Stories are sorted by date (newest first).
    """
    r = requests.get(
        "https://hn.algolia.com/api/v1/search_by_date",
        params={"query": query, "tags": "story", "hitsPerPage": limit},
        headers=_headers(),
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    hits = r.json().get("hits", [])
    return [
        {
            "source": "hackernews",
            "title": h.get("title"),
            "url": h.get("url")
            or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
            "description": (h.get("story_text") or "")[:500],
            "points": h.get("points", 0),
            "comments": h.get("num_comments", 0),
            "created": h.get("created_at"),
        }
        for h in hits
    ]


@tool
def fetch_url(url: str) -> str:
    """Fetch a URL and return cleaned text content (first 4000 chars).

    Use sparingly to dig deeper into a promising finding — e.g. reading a
    repo README, a blog post, or a Reddit thread before scoring it.
    """
    r = requests.get(url, headers=_headers(), timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "noscript"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())
    return text[:4000]


ALL_TOOLS = [search_github, search_reddit, search_hackernews, fetch_url]
