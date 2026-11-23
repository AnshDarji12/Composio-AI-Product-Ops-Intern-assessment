"""Composio Tool & Connector Integration.

Turns apps into tools that AI agents can call. This module:
1. Provides a connector status lookup for the 100-app research set:
   - "connected" : Already has an active toolkit/connector in Composio's catalog
                   (e.g., GitHub, Slack, Notion, Jira, Salesforce, HubSpot, Stripe, etc.)
   - "immediate-candidate" : Public REST/GraphQL API + self-serve developer access,
                             no vendor MCP or third-party gate -> highest ROI for Composio to build!
   - "outreach-needed" : Enterprise sales gate, partner-gated, or manual developer audit
                         (needs Composio BD/partnerships outreach).
2. Integrates Composio SDK local tools (such as ScrapeWebsiteContent from
   `composio.tools.local.webtool`) into the researcher's extraction toolbelt.
"""
import re
from typing import Literal, Tuple

ComposioStatus = Literal["connected", "immediate-candidate", "outreach-needed"]

# Apps currently supported in Composio's official tool/action ecosystem
COMPOSIO_CONNECTED_APPS: dict[str, str] = {
    "salesforce": "https://composio.dev/tools/salesforce",
    "hubspot": "https://composio.dev/tools/hubspot",
    "pipedrive": "https://composio.dev/tools/pipedrive",
    "attio": "https://composio.dev/tools/attio",
    "zoho crm": "https://composio.dev/tools/zoho",
    "close": "https://composio.dev/tools/close",
    "zendesk": "https://composio.dev/tools/zendesk",
    "intercom": "https://composio.dev/tools/intercom",
    "freshdesk": "https://composio.dev/tools/freshdesk",
    "front": "https://composio.dev/tools/front",
    "slack": "https://composio.dev/tools/slack",
    "twilio": "https://composio.dev/tools/twilio",
    "discord": "https://composio.dev/tools/discord",
    "telegram": "https://composio.dev/tools/telegram",
    "whatsapp business": "https://composio.dev/tools/whatsapp",
    "aircall": "https://composio.dev/tools/aircall",
    "google ads": "https://composio.dev/tools/google_ads",
    "mailchimp": "https://composio.dev/tools/mailchimp",
    "klaviyo": "https://composio.dev/tools/klaviyo",
    "sendgrid": "https://composio.dev/tools/sendgrid",
    "shopify": "https://composio.dev/tools/shopify",
    "woocommerce": "https://composio.dev/tools/woocommerce",
    "apify": "https://composio.dev/tools/apify",
    "firecrawl": "https://composio.dev/tools/firecrawl",
    "github": "https://composio.dev/tools/github",
    "vercel": "https://composio.dev/tools/vercel",
    "netlify": "https://composio.dev/tools/netlify",
    "cloudflare": "https://composio.dev/tools/cloudflare",
    "supabase": "https://composio.dev/tools/supabase",
    "snowflake": "https://composio.dev/tools/snowflake",
    "datadog": "https://composio.dev/tools/datadog",
    "sentry": "https://composio.dev/tools/sentry",
    "notion": "https://composio.dev/tools/notion",
    "airtable": "https://composio.dev/tools/airtable",
    "linear": "https://composio.dev/tools/linear",
    "jira": "https://composio.dev/tools/jira",
    "asana": "https://composio.dev/tools/asana",
    "monday.com": "https://composio.dev/tools/monday",
    "clickup": "https://composio.dev/tools/clickup",
    "coda": "https://composio.dev/tools/coda",
    "stripe": "https://composio.dev/tools/stripe",
    "quickbooks": "https://composio.dev/tools/quickbooks",
    "xero": "https://composio.dev/tools/xero",
}


class ComposioConnector:
    """Queries Composio toolkit status and uses Composio SDK scraping utilities."""

    def __init__(self) -> None:
        self._connected = COMPOSIO_CONNECTED_APPS

    def check_app(self, app_name: str, verdict: str, self_serve: str) -> Tuple[ComposioStatus, str]:
        """Returns (composio_status, composio_url_or_recommendation)."""
        clean = re.sub(r"[^a-z0-9 ]", "", app_name.lower()).strip()
        for key, url in self._connected.items():
            if clean == key or clean.startswith(key) or key in clean:
                return "connected", url

        # If not connected yet, classify by buildability
        if verdict == "blocked" or self_serve in {"partner-gated", "admin-approval"}:
            return "outreach-needed", "Requires partner outreach / BD contract for API access"
        return "immediate-candidate", "Prime candidate for new Composio toolkit (self-serve REST/GraphQL API)"

    def scrape_with_composio(self, url: str) -> str:
        """Invokes Composio's ScrapeWebsiteContent local tool action if available."""
        try:
            from composio.tools.local.webtool.actions.scrape_website_content import (
                ScrapeWebsiteContent,
                ScrapeWebsiteToolRequest,
            )
            tool = ScrapeWebsiteContent()
            res = tool.execute(ScrapeWebsiteToolRequest(website_url=url), {})
            return res.website_content
        except Exception:
            return ""

