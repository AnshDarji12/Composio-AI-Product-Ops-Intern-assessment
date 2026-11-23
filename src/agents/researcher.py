"""RESEARCHER agent: search -> governed fetch -> one structured extraction.

The LLM sees only page text that passed the governance layer, must cite
verbatim quotes, and may only use vocabulary from the schema enums.
Identifiers (id/category/app) are stamped by code afterwards, never trusted
from the model.
"""
from ..governance.engine import GovernanceEngine
from ..llm.gemini import BaseLLM
from ..tools.composio_tool import ComposioConnector
from ..tools.fetcher import FetchedDoc, Fetcher
from ..tools.mcp_lookup import MCPLookup
from ..tools.search import SearchTool
from .schemas import ResearchRow

SYSTEM = """You are the RESEARCHER agent in a SaaS API research pipeline.
TASK: fill one structured row about the given app using ONLY the page contents provided.

HARD RULES:
1. Use only facts present in the provided PAGE CONTENTS. Never invent; never fill gaps from prior knowledge.
2. Every factual field needs at least one Evidence item: the exact page URL plus a VERBATIM quote (max 30 words) copied from that page's provided content. Quotes must not be paraphrased.
3. If the contents do not answer a field: auth=[], self_serve="unknown", existing_mcp="unknown", api_surface="Not documented in fetched pages", verdict="buildable-with-friction", blocker="insufficient evidence", confidence<=0.4.
4. auth labels must come from: "OAuth2", "API key", "Basic", "Bearer token", "JWT", "HMAC", "mTLS", "Session cookie", "No auth". List every method that applies.
5. self_serve meanings: "self-serve" = any developer can self-register and get credentials free or on a trial; "paid-tier" = self-serve but credentials require a paid plan or card; "admin-approval" = an org admin must approve/create the app; "partner-gated" = requires sales contact / partnership; "unknown" = unclear.
6. verdict meanings: "buildable-today" = public API + self-serve credentials; "buildable-with-friction" = public API but paid/approval gating; "blocked" = no public API, partner-gated, or not an API product at all.
7. confidence in [0,1] is your honest evidence quality, not optimism.
8. what_it_does: max 15 words.
9. existing_mcp: "official" if the pages show a vendor-owned MCP server, "community" for third-party, "none" if pages affirmatively show none, "unknown" if unclear. The KNOWN_MCP_STATUS hint is pre-verified by a tool - if it is official/community, adopt it and cite its URL as evidence for existing_mcp."""


class Researcher:
    def __init__(self, llm: BaseLLM, search: SearchTool, fetcher: Fetcher,
                 mcp: MCPLookup, gov: GovernanceEngine) -> None:
        self.llm = llm
        self.search = search
        self.fetcher = fetcher
        self.mcp = mcp
        self.gov = gov
        self.composio = ComposioConnector()

    def research(self, app: dict, attempt: int = 1) -> tuple[ResearchRow, list[str]]:
        name = app["name"]
        hint = app.get("hint", "")
        pages = self._collect_pages(name, app.get("website", ""), attempt, hint)
        mcp_status, mcp_url = self.mcp.lookup(name)

        extra = ""
        if attempt > 1:
            extra = ("\nNOTE: attempt 2 - the previous draft scored low confidence. "
                     "Be stricter: use 'unknown' over guessing.\n")

        user = (
            f"APP_NAME: {name}\n"
            f"WEBSITE: {app.get('website', '')}\n"
            f"CATEGORY: {app.get('category', '')}\n"
            + (f"HINT: {hint}\n" if hint else "")
            + f"KNOWN_MCP_STATUS: {mcp_status}"
            + (f" ({mcp_url})" if mcp_url else "")
            + extra + "\n"
        )
        for i, doc in enumerate(pages, 1):
            user += f"\nPAGE {i} URL: {doc.final_url or doc.url}\nPAGE {i} CONTENT:\n<<<\n{doc.text[:8000]}\n>>>\n"
        user += "\nResearch the row now. Keep evidence concise: 3-5 key quotes, max 25 words each."

        result = self.llm.generate(SYSTEM, user, ResearchRow)
        if isinstance(result.parsed, ResearchRow):
            row = result.parsed
        else:
            try:
                row = ResearchRow.model_validate_json(result.text)
            except Exception:
                import json
                try:
                    data = json.loads(result.text)
                    row = ResearchRow.model_validate(data)
                except Exception:
                    row = ResearchRow(
                        app=name, category=app.get("category", ""),
                        what_it_does=f"{name} platform",
                        auth=[], self_serve="unknown", api_surface="Not documented",
                        existing_mcp="unknown", verdict="buildable-with-friction",
                        blocker="unparseable response", confidence=0.4,
                    )

        # identifiers come from code, not the model
        row.id = int(app["id"])
        row.app = name
        row.category = app.get("category", "")
        row.flags = list(dict.fromkeys(row.flags + result.flags))
        if result.provider == "mock":
            row.flags.append("mock-mode")

        if mcp_status in {"official", "community"} and row.existing_mcp not in {"official", "community"}:
            row.existing_mcp = mcp_status
            from .schemas import Evidence
            row.evidence.append(Evidence(field="existing_mcp", url=mcp_url,
                                         quote=f"MCP server listed for {name} (tool-verified)"))

        # Composio tool integration check
        comp_status, _ = self.composio.check_app(name, row.verdict, row.self_serve)
        row.composio_status = comp_status

        clean, flags, quarantined = self.gov.guard_row(row.model_dump(), source="researcher")
        row = ResearchRow.model_validate(clean)
        if quarantined:
            row.flags.append("quarantined")
        if flags:
            row.flags = list(dict.fromkeys(row.flags + flags))
        return row, flags

    def _collect_pages(self, name: str, website: str, attempt: int, hint: str = "") -> list[FetchedDoc]:
        queries = [f"{name} API authentication documentation"]
        if hint:
            queries.insert(0, f"{name} {hint} API authentication")
        if attempt > 1:
            queries.extend([f"{name} developer portal API keys", f"{name} REST API docs pricing"])
        queries.append(f"{name} MCP server")

        urls: list[str] = []
        for q in queries[:3]:
            for res in self.search.search(q, max_results=3):
                if res.url not in urls:
                    urls.append(res.url)

        # prioritize URLs that have docs/developer/api
        def _score_url(u: str) -> int:
            score = 0
            low = u.lower()
            if any(k in low for k in ("docs.", "developer.", "api.", "/docs", "/api", "/developer", "reference")):
                score += 10
            if any(k in low for k in ("auth", "quickstart", "guide", "rest")):
                score += 5
            return score

        urls = sorted(urls, key=_score_url, reverse=True)

        # if website is an explicit doc URL, seed first; otherwise put at end
        if website:
            low_web = website.lower()
            if any(k in low_web for k in ("docs", "developer", "api", "stoplight", "github.com")):
                if website not in urls:
                    urls.insert(0, website)
            elif website not in urls:
                urls.append(website)

        pages: list[FetchedDoc] = []
        for url in urls[:5]:
            doc = self.fetcher.fetch(url)
            if not doc.error and doc.text and len(doc.text) > 150:
                pages.append(doc)
            if len(pages) >= 3:
                break
        return pages
