"""Governed URL fetcher.

Every hop of every request passes governance.check_url() FIRST
(https-only, blocklist, SSRF/DNS guard, robots.txt). Bodies are size-capped
and reduced to readable document text. Raw snapshots are cached so
verification re-fetches are free and the evidence trail is reproducible.
"""
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from ..governance.engine import GovernanceEngine

USER_AGENT = "ComposioResearchAgent/1.0 (+research take-home; respects robots.txt)"
MAX_TEXT_CHARS = 20_000


@dataclass
class FetchedDoc:
    url: str
    final_url: str = ""
    status: int = 0
    text: str = ""
    sha256: str = ""
    bytes: int = 0
    fetched_at: str = ""
    error: str = ""
    policy_rule: str = ""
    from_cache: bool = False
    links: list[str] = field(default_factory=list)


class Fetcher:
    def __init__(self, gov: GovernanceEngine, cache_dir: Path,
                 max_mb: float = 5.0, timeout_s: float = 20.0, max_hops: int = 3) -> None:
        self.gov = gov
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = int(max_mb * 1024 * 1024)
        self.timeout = timeout_s
        self.max_hops = max_hops

    # ── public ────────────────────────────────────────────────────────
    def fetch(self, url: str) -> FetchedDoc:
        cached = self._cache_get(url)
        if cached:
            return cached
        doc = self._fetch_live(url)
        if not doc.error:
            self._cache_put(doc)
        return doc

    # ── live fetch with per-hop policy checks ─────────────────────────
    def _fetch_live(self, url: str) -> FetchedDoc:
        current = url
        for hop in range(self.max_hops + 1):
            decision = self.gov.check_url(current)
            if not decision.allowed:
                return FetchedDoc(url=url, error=f"policy-denied: {decision.rule}",
                                  policy_rule=decision.rule)
            try:
                resp = httpx.get(
                    current,
                    follow_redirects=False,  # redirects re-checked hop by hop
                    timeout=self.timeout,
                    headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"},
                )
            except httpx.HTTPError as exc:
                return FetchedDoc(url=url, final_url=current, error=f"http-error: {exc}")

            if 300 <= resp.status_code < 400:
                location = resp.headers.get("location", "")
                if not location or hop == self.max_hops:
                    return FetchedDoc(url=url, final_url=current, status=resp.status_code,
                                      error="redirect-loop-or-missing-location")
                current = urljoin(current, location)
                continue

            if resp.status_code != 200:
                return FetchedDoc(url=url, final_url=current, status=resp.status_code,
                                  error=f"http-{resp.status_code}")
            if len(resp.content) > self.max_bytes:
                return FetchedDoc(url=url, final_url=current, status=resp.status_code,
                                  error=f"body-too-large>{self.max_bytes}b")

            text = self._extract_text(resp.text)
            return FetchedDoc(
                url=url,
                final_url=str(resp.url),
                status=resp.status_code,
                text=text,
                sha256=hashlib.sha256(resp.content).hexdigest(),
                bytes=len(resp.content),
                fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
        return FetchedDoc(url=url, error="max-redirect-hops-exceeded")

    # ── HTML -> readable text ─────────────────────────────────────────
    @staticmethod
    def _extract_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "aside", "noscript", "svg", "form"]):
            tag.decompose()
        root = soup.find("main") or soup.find("article") or soup.body or soup
        text = root.get_text(" ", strip=True)
        return re.sub(r"\s{2,}", " ", text)[:MAX_TEXT_CHARS]

    # ── cache ─────────────────────────────────────────────────────────
    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".json")

    def _cache_get(self, url: str) -> FetchedDoc | None:
        path = self._cache_path(url)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        doc = FetchedDoc(**{k: data[k] for k in data if k in FetchedDoc.__dataclass_fields__})
        doc.from_cache = True
        return doc

    def _cache_put(self, doc: FetchedDoc) -> None:
        self._cache_path(doc.url).write_text(json.dumps(doc.__dict__, ensure_ascii=False))
        self.gov.audit.append("fetched", "fetcher", url=doc.url, status=doc.status,
                              bytes=doc.bytes, sha256=doc.sha256[:12])
