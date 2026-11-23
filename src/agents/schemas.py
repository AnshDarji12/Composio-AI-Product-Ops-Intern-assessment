"""Structured-output contracts. The LLM must return these exact shapes
(enforced via Gemini response_schema + Pydantic validation) - free-form
text never enters the dataset."""
from typing import List, Literal, Optional

from pydantic import BaseModel

SelfServe = Literal["self-serve", "paid-tier", "admin-approval", "partner-gated", "unknown"]
MCPStatus = Literal["official", "community", "none", "unknown"]
Verdict = Literal["buildable-today", "buildable-with-friction", "blocked"]


class Evidence(BaseModel):
    """One citation: which field, which page, what the page actually says."""
    field: str
    url: str
    quote: str


class ResearchRow(BaseModel):
    id: int = 0
    app: str
    category: str = ""
    what_it_does: str
    auth: List[str] = []
    self_serve: SelfServe = "unknown"
    api_surface: str = "Not documented in fetched pages"
    existing_mcp: MCPStatus = "unknown"
    composio_status: Optional[str] = "immediate-candidate"
    verdict: Verdict = "buildable-with-friction"
    blocker: Optional[str] = None
    evidence: List[Evidence] = []
    confidence: float = 0.5
    flags: List[str] = []


class Dispute(BaseModel):
    field: str
    draft_claim: str
    ruling: Literal["supported", "contradicted", "unsupported"]
    note: str


class VerificationResult(BaseModel):
    corrections: ResearchRow
    disputes: List[Dispute] = []
    confidence: float = 0.5
    verifier_notes: str = ""
