"""Web search tool (DuckDuckGo via `ddgs`, no API key required).

Every result URL is filtered through the governance engine before it can
be handed to an agent - the search tool cannot introduce a forbidden host.
"""
import time
from dataclasses import dataclass

from ..config import SETTINGS
from ..governance.engine import GovernanceEngine


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class SearchTool:
    def __init__(self, gov: GovernanceEngine) -> None:
        self.gov = gov
        self.enabled = SETTINGS.search_provider != "none"

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        if not self.enabled:
            return []
        try:
            from ddgs import DDGS
        except ImportError:
            return []
        try:
            raw = DDGS().text(query, max_results=max_results * 2, region="us-en",
                              safesearch="moderate", backend="auto")
        except Exception as exc:  # noqa: BLE001 - search is best-effort
            self.gov.audit.append("search_failed", "search", query=query, error=str(exc)[:200])
            return []
        time.sleep(1.0)  # be polite to the free search backend

        results: list[SearchResult] = []
        for item in raw or []:
            url = item.get("href") or item.get("url") or ""
            if not url:
                continue
            if not self.gov.check_url(url).allowed:
                continue
            results.append(SearchResult(item.get("title", ""), url, item.get("body", "")))
            if len(results) >= max_results:
                break
        return results
