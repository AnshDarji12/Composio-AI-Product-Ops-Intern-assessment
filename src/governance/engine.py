"""Governance engine: the policy checkpoint every action must pass.

Three interception points, one place:

  1. check_url()        - every outbound HTTP request (scheme, blocklist,
                          SSRF/DNS, robots.txt) BEFORE any bytes leave.
  2. pre_llm() / record - model allowlist + call/token budgets BEFORE each
                          LLM call; usage recorded after.
  3. guard_row()        - every structured output row (schema keys, secret
                          scan, PII redaction) BEFORE it reaches storage.

Everything is audited. Flagged rows are quarantined, never silently kept.
"""
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml

from .audit import AuditLog
from .guards import RobotsCache, redact_pii, redact_secrets, scan_secrets, ssrf_check


@dataclass
class Decision:
    allowed: bool
    rule: str
    reason: str


class BudgetExceeded(RuntimeError):
    """Raised when an LLM call would exceed the run budget."""


@dataclass
class _Budget:
    calls_used: int = 0
    tokens_used: int = 0
    max_calls: int = field(default=260)
    max_tokens: int = field(default=2_000_000)

    def allows(self) -> tuple[bool, str]:
        if self.calls_used >= self.max_calls:
            return False, f"call budget exhausted ({self.calls_used}/{self.max_calls})"
        if self.tokens_used >= self.max_tokens:
            return False, f"token budget exhausted ({self.tokens_used}/{self.max_tokens})"
        return True, "ok"


class GovernanceEngine:
    def __init__(self, policy_path: Path, audit: AuditLog) -> None:
        self.policy = yaml.safe_load(Path(policy_path).read_text())
        self.audit = audit
        net = self.policy["network"]
        self._require_https = bool(net.get("require_https", True))
        self._blocked_hosts = {h.lower() for h in net.get("blocked_hosts", [])}
        self._block_private_ips = bool(net.get("block_private_ips", True))
        self._respect_robots = bool(net.get("respect_robots", True))
        self.robots = RobotsCache()

        llm = self.policy["llm"]
        self._allowed_models = set(llm.get("allowed_models", []))
        self._rpm = float(llm.get("rpm", 9))
        self._last_call_ts = 0.0
        self.budget = _Budget(
            max_calls=int(llm.get("max_calls_per_run", 260)),
            max_tokens=int(llm.get("max_tokens_per_run", 2_000_000)),
        )

        data = self.policy.get("data", {})
        self._redact_pii = bool(data.get("redact_pii", True))
        self._secret_scan = bool(data.get("secret_scan", True))
        self._quarantine_on_flag = bool(data.get("quarantine_on_flag", True))

        hr = self.policy.get("human_review", {})
        self.confidence_threshold = float(hr.get("confidence_threshold", 0.75))
        self.audit_sample_size = int(hr.get("audit_sample_size", 20))
        self.max_retries = int(hr.get("max_retries", 1))

        self.quarantined: list[dict] = []

    # ── 1. network policy ────────────────────────────────────────────
    def check_url(self, url: str) -> Decision:
        try:
            parts = urlparse(url)
        except ValueError:
            return self._deny_url(url, "url-parse-failed", "unparseable URL")
        host = (parts.hostname or "").lower()

        if self._require_https and parts.scheme != "https":
            return self._deny_url(url, "require_https", f"scheme={parts.scheme or 'none'}")
        if not host:
            return self._deny_url(url, "require_https", "missing host")
        if host in self._blocked_hosts or host.split(".")[0] in {"localhost"}:
            return self._deny_url(url, "blocked_hosts", host)
        if self._block_private_ips:
            ok, reason = ssrf_check(host)
            if not ok:
                return self._deny_url(url, "ssrf_guard", reason)
        if self._respect_robots and not self.robots.can_fetch(url):
            return self._deny_url(url, "robots_txt", "disallowed by robots.txt")
        self.audit.append("url_allowed", "governance", host=host)
        return Decision(True, "network", "ok")

    def _deny_url(self, url: str, rule: str, reason: str) -> Decision:
        self.audit.append("url_denied", "governance", rule=rule, reason=reason, url=url)
        return Decision(False, rule, reason)

    # ── 2. LLM policy ────────────────────────────────────────────────
    def pre_llm(self, model: str) -> Decision:
        if model not in self._allowed_models:
            self.audit.append("llm_denied", "governance", rule="model_allowlist", model=model)
            return Decision(False, "model_allowlist", f"{model} not in policy")
        ok, reason = self.budget.allows()
        if not ok:
            raise BudgetExceeded(reason)
        # client-side rate limiting (free-tier friendly)
        wait = max(0.0, (60.0 / self._rpm) - (time.monotonic() - self._last_call_ts))
        if wait > 0:
            time.sleep(wait)
        self._last_call_ts = time.monotonic()
        self.budget.calls_used += 1
        self.audit.append("llm_call_allowed", "governance", model=model,
                          calls_used=self.budget.calls_used)
        return Decision(True, "llm", "ok")

    def record_llm_usage(self, model: str, tokens: int) -> None:
        self.budget.tokens_used += int(tokens or 0)
        self.audit.append("llm_usage", "governance", model=model, tokens=int(tokens or 0),
                          tokens_used=self.budget.tokens_used)

    def scan_model_output(self, text: str) -> tuple[str, list[str]]:
        """Secret-scan raw model output before it touches disk."""
        if not self._secret_scan:
            return text, []
        clean, labels = redact_secrets(text)
        if labels:
            self.audit.append("secret_redacted_in_llm_output", "governance", labels=labels)
        return clean, labels

    # ── 3. data policy ───────────────────────────────────────────────
    REQUIRED_ROW_KEYS = ("id", "app", "category", "what_it_does", "auth", "self_serve",
                         "api_surface", "existing_mcp", "verdict", "blocker",
                         "evidence", "confidence")

    def guard_row(self, row: dict, source: str) -> tuple[dict, list[str], bool]:
        """Validate + sanitise an output row. Returns (row, flags, quarantined)."""
        flags: list[str] = []
        missing = [k for k in self.REQUIRED_ROW_KEYS if k not in row]
        if missing:
            flags.append(f"missing-keys:{','.join(missing)}")

        clean = dict(row)
        clean["evidence"] = [dict(e) for e in clean.get("evidence", [])]
        for ev in clean["evidence"]:
            if self._redact_pii:
                quote, pii_labels = redact_pii(str(ev.get("quote", "")))
                if pii_labels:
                    ev["quote"] = quote
                    flags.append(f"pii-redacted:{'+'.join(pii_labels)}")
            if self._secret_scan:
                quote, secret_labels = redact_secrets(str(ev.get("quote", "")))
                if secret_labels:
                    ev["quote"] = quote
                    flags.append(f"secret-redacted:{'+'.join(secret_labels)}")

        if flags and self._quarantine_on_flag:
            self.quarantined.append({"row": clean, "flags": flags, "source": source})
            self.audit.append("row_quarantined", "governance", app=clean.get("app"),
                              flags=flags, source=source)
        self.audit.append("row_guarded", "governance", app=clean.get("app"),
                          flags=flags, source=source)
        return clean, flags, bool(flags and self._quarantine_on_flag)

    def export_quarantine(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.quarantined, indent=2, ensure_ascii=False))
        self.audit.append("quarantine_exported", "governance",
                          count=len(self.quarantined), path=str(path))
