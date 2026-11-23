"""VERIFIER agent: adversarial second pass.

Re-fetches every cited evidence URL (cache makes this free), then asks the
model to rule each draft claim supported / contradicted / unsupported and
return a corrected row. The verifier can only downgrade or keep claims
unless page content clearly contradicts them - it cannot invent new facts.
"""
import json

from ..governance.engine import GovernanceEngine
from ..llm.gemini import BaseLLM
from ..tools.fetcher import Fetcher
from .schemas import ResearchRow, VerificationResult

SYSTEM = """You are the VERIFIER agent - an adversarial fact-checker.
INPUT: a DRAFT research row plus the fetched content of the pages it cites.
TASK:
1. For each factual field (auth, self_serve, api_surface, existing_mcp, verdict, what_it_does):
   rule it "supported" (page content clearly backs it), "contradicted" (page content clearly
   refutes it), or "unsupported" (no real backing in the content).
2. Produce `corrections`: the corrected row (same schema). Keep draft values unless page
   content clearly supports a change; for contradicted fields use the page-backed value or
   "unknown". Unsupported non-critical fields: keep value but lower confidence.
3. Re-score `confidence` honestly: start from the share of supported fields, never above 0.95.
4. verifier_notes: max 40 words, name the weakest field.
5. NEVER invent new facts or new evidence URLs. Keep existing evidence; you may fix a quote
   to match the actual page text verbatim."""


class Verifier:
    def __init__(self, llm: BaseLLM, fetcher: Fetcher, gov: GovernanceEngine) -> None:
        self.llm = llm
        self.fetcher = fetcher
        self.gov = gov

    def verify(self, draft: ResearchRow) -> tuple[VerificationResult, list[str]]:
        user = f"DRAFT_ROW_JSON:\n{draft.model_dump_json(indent=1)}\n"
        seen: set[str] = set()
        for ev in draft.evidence:
            url = ev.url
            if not url or url in seen:
                continue
            seen.add(url)
            doc = self.fetcher.fetch(url)
            if doc.error:
                user += f"\nPAGE URL: {url}\nPAGE STATUS: UNAVAILABLE ({doc.error})\n"
            else:
                user += f"\nPAGE URL: {doc.final_url or doc.url}\nPAGE CONTENT:\n<<<\n{doc.text}\n>>>\n"
        user += "\nVerify the draft row now."

        result = self.llm.generate(SYSTEM, user, VerificationResult)
        if isinstance(result.parsed, VerificationResult):
            vres = result.parsed
        else:
            try:
                vres = VerificationResult.model_validate_json(result.text)
            except Exception:
                vres = VerificationResult(
                    corrections=draft, disputes=[],
                    confidence=min(draft.confidence, 0.6),
                    verifier_notes="verifier output unparseable - draft kept, flagged")
                draft.flags.append("verifier-unparseable")

        clean, flags, quarantined = self.gov.guard_row(
            vres.corrections.model_dump(), source="verifier")
        vres.corrections = ResearchRow.model_validate(clean)
        if quarantined:
            vres.corrections.flags.append("quarantined")
        if flags:
            vres.corrections.flags = list(dict.fromkeys(vres.corrections.flags + flags))
        return vres, flags
