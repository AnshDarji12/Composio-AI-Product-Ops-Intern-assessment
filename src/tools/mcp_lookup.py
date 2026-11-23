"""MCP-server lookup: does this app already have an MCP server?

Two sources, merged:
  1. A curated map of known OFFICIAL MCP servers (vendor-owned repos).
  2. GitHub repository search for community servers (needs >=50 stars to
     count, to avoid every 3-commit hobby repo flagging as an ecosystem).

GitHub API is unauthenticated unless GITHUB_TOKEN is set (60 vs 5000 req/h),
politeness-capped and cached to disk.
"""
import json
import time
from pathlib import Path

import httpx

from ..config import SETTINGS
from ..governance.engine import GovernanceEngine

OFFICIAL_MCP: dict[str, str] = {
    "github": "https://github.com/github/github-mcp-server",
    "sentry": "https://github.com/getsentry/sentry-mcp",
    "stripe": "https://github.com/stripe/stripe-mcp",
    "notion": "https://github.com/makenotion/notion-mcp-server",
    "cloudflare": "https://github.com/cloudflare/mcp-server-cloudflare",
    "supabase": "https://github.com/supabase-community/supabase-mcp",
    "mongodb atlas": "https://github.com/mongodb-js/mongodb-mcp-server",
    "datadog": "https://github.com/DataDog/datadog-mcp-server",
    "slack": "https://api.slack.com/mcp",
    "telegram": "https://github.com/nash-su/telegram-mcp",
    "gitlab": "https://github.com/zereight/gitlab-mcp",
    "linear": "https://mcp.linear.app/sse",
    "wordpress": "https://github.com/FlorianRappl/wordpress-mcp",
    "twilio": "https://github.com/twilio-labs/mcp",
    "shopify": "https://shopify.dev/docs/apps/build/mcp",
    "jira": "https://github.com/sooperset/mcp-atlassian",
    "neon": "https://github.com/neondatabase/mcp-server-neon",
    "vercel": "https://github.com/vercel/mcp-adapter",
    "salesforce": "https://developer.salesforce.com/docs/platform/mcp",
    "devin": "https://docs.devin.ai/mcp",
    "otter ai": "https://help.otter.ai",
    "firecrawl": "https://github.com/mendableai/firecrawl-mcp-server",
    "apify": "https://github.com/apify/mcp-server-apify",
    "bright data": "https://github.com/bright-data/brightdata-mcp",
    "snowflake": "https://github.com/Snowflake-Labs/mcp-snowflake",
    "neo4j": "https://github.com/neo4j-contrib/neo4j-mcp",
    "airtable": "https://github.com/domdomegg/airtable-mcp-server",
    "asana": "https://github.com/rohitg00/asana-mcp-server",
    "clickup": "https://github.com/taishi-k/clickup-mcp-server",
    "quickbooks": "https://github.com/intuit/quickbooks-mcp",
}

GH_SEARCH_URL = "https://api.github.com/search/repositories"
MIN_COMMUNITY_STARS = 50


class MCPLookup:
    def __init__(self, gov: GovernanceEngine, cache_dir: Path) -> None:
        self.gov = gov
        self.cache_path = Path(cache_dir) / "mcp-lookup.json"
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache: dict[str, dict] = (
            json.loads(self.cache_path.read_text()) if self.cache_path.exists() else {}
        )

    def lookup(self, app_name: str) -> tuple[str, str]:
        """Returns (status, url). status in {official, community, none, unknown}."""
        key = app_name.lower().strip()
        if key in self.cache:
            rec = self.cache[key]
            return rec["status"], rec["url"]

        status, url = self._lookup_live(app_name)
        self.cache[key] = {"status": status, "url": url}
        self.cache_path.write_text(json.dumps(self.cache, indent=2))
        return status, url

    def _lookup_live(self, app_name: str) -> tuple[str, str]:
        # 1) curated official map (word-prefix match on the app name)
        low = app_name.lower()
        for official_name, url in OFFICIAL_MCP.items():
            if low == official_name or low.startswith(official_name):
                self.gov.audit.append("mcp_lookup", "mcp", app=app_name,
                                      status="official", source="curated")
                return "official", url

        # 2) GitHub community search
        decision = self.gov.check_url(GH_SEARCH_URL)
        if not decision.allowed:
            return "unknown", ""
        query = f'"{app_name}" mcp in:name,description,readme'
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "composio-research-agent"}
        if SETTINGS.github_token:
            headers["Authorization"] = f"Bearer {SETTINGS.github_token}"
        try:
            resp = httpx.get(GH_SEARCH_URL, params={"q": query, "sort": "stars", "per_page": 3},
                             headers=headers, timeout=20)
        except httpx.HTTPError:
            return "unknown", ""
        time.sleep(6)  # stay inside unauthenticated search limits (10/min)
        if resp.status_code != 200:
            self.gov.audit.append("mcp_lookup", "mcp", app=app_name,
                                  status="gh-api-error", code=resp.status_code)
            return "unknown", ""
        items = resp.json().get("items", [])
        for item in items:
            if (item.get("stargazers_count") or 0) >= MIN_COMMUNITY_STARS:
                self.gov.audit.append("mcp_lookup", "mcp", app=app_name,
                                      status="community", stars=item["stargazers_count"])
                return "community", item["html_url"]
        return "none", ""
