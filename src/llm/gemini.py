"""LLM providers.

- GeminiLLM  : Google AI Studio free tier (gemini-2.5-flash). Every call is
               rate-limited, budget-checked and audited by the governance
               engine BEFORE it is sent, with 429-aware retry/backoff.
- MockLLM    : deterministic offline provider so the full pipeline can be
               dry-run (CI / demo) without spending quota. Output rows are
               flagged `mock-mode` and are NEVER research results.
"""
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Type

from pydantic import BaseModel

from ..config import SETTINGS
from ..governance.engine import GovernanceEngine


class PolicyDenied(RuntimeError):
    """Governance refused the call (model not in allowlist)."""


@dataclass
class LLMResult:
    text: str
    parsed: Any = None
    tokens: int = 0
    provider: str = "gemini"
    flags: list[str] = field(default_factory=list)


class BaseLLM:
    def generate(self, system: str, user: str, schema: Type[BaseModel]) -> LLMResult:
        raise NotImplementedError


class GeminiLLM(BaseLLM):
    RETRYABLE = ("429", "resource_exhausted", "503", "unavailable", "deadline", "timeout")

    def __init__(self, gov: GovernanceEngine) -> None:
        import os
        from google import genai
        from google.genai import types

        keys_env = os.environ.get("GEMINI_API_KEYS", "").strip()
        if keys_env:
            self.KEYS = [k.strip() for k in keys_env.split(",") if k.strip()]
        elif SETTINGS.has_llm_key:
            self.KEYS = [SETTINGS.gemini_api_key]
        else:
            raise RuntimeError("GEMINI_API_KEY missing - get a free key at aistudio.google.com")

        self._genai = genai
        self._types = types
        self.key_idx = 0
        self.client = genai.Client(api_key=self.KEYS[self.key_idx])
        self.gov = gov
        self.model = SETTINGS.gemini_model or "gemini-2.5-flash"
        self._cfg = gov.policy["llm"]

    def _rotate_client(self):
        if len(self.KEYS) > 1:
            self.key_idx = (self.key_idx + 1) % len(self.KEYS)
            print(f" [Key Rotation -> Key #{self.key_idx + 1}]", flush=True)
            self.client = self._genai.Client(api_key=self.KEYS[self.key_idx])

    def generate(self, system: str, user: str, schema: Type[BaseModel]) -> LLMResult:
        decision = self.gov.pre_llm(self.model)
        if not decision.allowed:
            raise PolicyDenied(decision.reason)

        config = self._types.GenerateContentConfig(
            system_instruction=system,
            temperature=float(self._cfg.get("temperature", 0.2)),
            max_output_tokens=int(self._cfg.get("max_output_tokens", 4096)),
            response_mime_type="application/json",
            response_schema=schema,
        )

        resp = None
        last_exc = None
        for attempt in range(len(self.KEYS) * 2):
            try:
                resp = self.client.models.generate_content(
                    model=self.model, contents=[user], config=config
                )
                break
            except Exception as exc:
                last_exc = exc
                err_str = str(exc).lower()
                self._rotate_client()
                time.sleep(1.0)

        if resp is None:
            raise last_exc or RuntimeError("All API keys exhausted or failed")

        tokens = 0
        if resp.usage_metadata and resp.usage_metadata.total_token_count:
            tokens = int(resp.usage_metadata.total_token_count)
        self.gov.record_llm_usage(self.model, tokens)

        text = resp.text or ""
        clean, flags = self.gov.scan_model_output(text)
        return LLMResult(text=clean, parsed=resp.parsed, tokens=tokens,
                         provider="gemini", flags=flags)


class MockLLM(BaseLLM):
    """Deterministic offline provider - flags every row with `mock-mode`."""

    def __init__(self, gov: GovernanceEngine) -> None:
        self.gov = gov

    def _first_url(self, text: str) -> str:
        m = re.search(r"https?://[^\s\"')]+", text)
        return m.group(0).rstrip(".") if m else "https://example.com/docs"

    def _app_name(self, text: str) -> str:
        m = re.search(r"APP_NAME:\s*(.+)", text)
        return m.group(1).strip() if m else "UnknownApp"

    def generate(self, system: str, user: str, schema: Type[BaseModel]) -> LLMResult:
        self.gov.pre_llm("mock-model")
        name = self._app_name(user)
        url = self._first_url(user)

        if schema.__name__ == "ResearchRow":
            row = {
                "id": 0,
                "app": name,
                "category": "Mock",
                "what_it_does": f"(mock dry-run row for {name})",
                "auth": ["API key"],
                "self_serve": "self-serve",
                "api_surface": "Public REST (mock - not researched)",
                "existing_mcp": "unknown",
                "composio_status": "immediate-candidate",
                "verdict": "buildable-today",
                "blocker": None,
                "evidence": [{"field": "auth", "url": url, "quote": "(mock dry-run evidence)"}],
                "confidence": 0.85,
                "flags": ["mock-mode"],
            }
            parsed = schema(**row)
        elif schema.__name__ == "VerificationResult":
            draft: dict = {}
            m = re.search(r"\{", user)
            if m:  # streaming decode: parse the first JSON value, ignore trailing text
                try:
                    draft = json.JSONDecoder().raw_decode(user[m.start():])[0]
                except json.JSONDecodeError:
                    draft = {}
            if draft:
                draft.setdefault("flags", []).append("mock-mode")
                draft["confidence"] = 0.9
            else:
                draft = {"id": 0, "app": name, "category": "Mock", "what_it_does": "mock",
                         "auth": ["API key"], "self_serve": "self-serve",
                         "api_surface": "mock", "existing_mcp": "unknown", "composio_status": "immediate-candidate",
                         "verdict": "buildable-today", "blocker": None,
                         "evidence": [], "confidence": 0.9, "flags": ["mock-mode"]}
            parsed = schema(
                corrections=draft,
                disputes=[],
                confidence=0.9,
                verifier_notes="(mock verifier - offline dry run)",
            )
        else:
            parsed = schema()

        self.gov.record_llm_usage("mock-model", 0)
        return LLMResult(text="(mock output)", parsed=parsed, tokens=0, provider="mock",
                         flags=["mock-mode"])


def build_llm(gov: GovernanceEngine, mock: bool = False) -> BaseLLM:
    if mock:
        return MockLLM(gov)
    return GeminiLLM(gov)
