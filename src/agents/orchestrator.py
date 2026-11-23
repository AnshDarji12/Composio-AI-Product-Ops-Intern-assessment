"""ORCHESTRATOR: batching, retries, state, resume, and the golden path

  research(app, attempt=1) -> confidence gate -> verify -> canonical store

Low-confidence rows are re-researched once (governance.max_retries), then
quarantined with the failures if still weak. State is written per run so an
interrupted 100-app run resumes without re-spending quota.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from ..governance.engine import GovernanceEngine
from ..llm.gemini import BaseLLM
from ..store.canonical import CanonicalStore
from ..tools.fetcher import Fetcher
from ..tools.mcp_lookup import MCPLookup
from ..tools.search import SearchTool
from .researcher import Researcher
from .schemas import ResearchRow
from .verifier import Verifier


class Orchestrator:
    def __init__(self, apps: list[dict], gov: GovernanceEngine, llm: BaseLLM,
                 store: CanonicalStore, cache_dir: Path, runs_dir: Path,
                 run_id: str, mock: bool = False) -> None:
        self.apps = apps
        self.gov = gov
        self.store = store
        self.run_dir = Path(runs_dir) / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.run_dir / "state.json"

        self.search = SearchTool(gov)
        self.fetcher = Fetcher(gov, cache_dir,
                               max_mb=gov.policy["network"].get("max_response_mb", 5),
                               timeout_s=gov.policy["network"].get("timeout_s", 20),
                               max_hops=gov.policy["network"].get("max_redirect_hops", 3))
        self.mcp = MCPLookup(gov, cache_dir)
        self.researcher = Researcher(llm, self.search, self.fetcher, self.mcp, gov)
        self.verifier = Verifier(llm, self.fetcher, gov)
        self.mock = mock
        self.stats = {"researched": 0, "verified": 0, "retried": 0,
                      "quarantined": 0, "stored": 0, "llm_calls": 0}

    # ── state (resume support) ───────────────────────────────────────
    def _load_state(self) -> dict:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        return {"done": {}, "skipped": {}}

    def _save_state(self, state: dict) -> None:
        self.state_path.write_text(json.dumps(state, indent=2))

    # ── main loop ────────────────────────────────────────────────────
    def run(self, limit: int = 0, only_ids: list[int] | None = None,
            skip_verify: bool = False) -> dict:
        self.gov.audit.append("run_started", "orchestrator",
                              apps=len(self.apps), limit=limit, mock=self.mock)
        state = self._load_state()
        todo = [a for a in self.apps
                if str(a["id"]) not in state["done"]
                and (not only_ids or int(a["id"]) in only_ids)]
        if limit:
            todo = todo[:limit]

        threshold = self.gov.confidence_threshold
        retries = self.gov.max_retries

        for i, app in enumerate(todo, 1):
            print(f"[{i}/{len(todo)}] {app['name']} ... ", flush=True)
            t0 = time.time()
            try:
                row, flags = self.researcher.research(app, attempt=1)
            except Exception as exc:  # noqa: BLE001 - keep the run going
                print(f"    research-failed: {type(exc).__name__}: {str(exc)[:120]}")
                self.gov.audit.append("research_failed", "orchestrator",
                                      app=app["name"], error=str(exc)[:300])
                state["skipped"][str(app["id"])] = str(exc)[:300]
                self._save_state(state)
                continue
            self.stats["researched"] += 1

            # confidence gate -> bounded retry
            attempt, best = 1, row
            while row.confidence < threshold and attempt <= retries:
                print(f"    low confidence {row.confidence:.2f} < {threshold} -> retrying")
                attempt += 1
                self.stats["retried"] += 1
                row, flags = self.researcher.research(app, attempt=attempt)
                if row.confidence >= best.confidence:
                    best = row
            row = best

            if "quarantined" in row.flags:
                self.stats["quarantined"] += 1
                state["skipped"][str(app["id"])] = "quarantined by governance"
                self._save_state(state)
                print("    quarantined by governance (see quarantine.json)")
                continue

            first_pass = row.model_dump()
            if skip_verify:
                self.store.upsert(row.model_dump(), first_pass=first_pass,
                                  verified_by="skipped")
                self.stats["stored"] += 1
            else:
                try:
                    vres, _ = self.verifier.verify(row)
                    final = vres.corrections.model_dump()
                    final["id"] = row.id
                    final["app"] = row.app
                    final["category"] = row.category
                    final["flags"] = sorted(set(final.get("flags", []) + row.flags))
                    self.store.upsert(final, first_pass=first_pass,
                                      verified_by=f"verifier:{'mock' if self.mock else 'gemini'}")
                    self.store.add_disputes(row.id,
                                            [d.model_dump() for d in vres.disputes])
                    self.stats["verified"] += 1
                    print(f"    verified: {len(vres.disputes)} disputes, "
                          f"confidence {vres.confidence:.2f}")
                except Exception as exc:  # noqa: BLE001 - verify is best-effort
                    print(f"    verify-failed ({str(exc)[:80]}) -> storing draft, flagged")
                    draft = row.model_dump()
                    draft["flags"].append("verify-failed")
                    self.store.upsert(draft, first_pass=first_pass, verified_by="failed")
                self.stats["stored"] += 1

            self.stats["llm_calls"] = self.gov.budget.calls_used
            state["done"][str(app["id"])] = {
                "confidence": row.confidence, "attempts": attempt,
                "seconds": round(time.time() - t0, 1),
            }
            self._save_state(state)

        self.gov.audit.append("run_finished", "orchestrator", stats=self.stats)
        self._write_summary()
        return self.stats

    def _write_summary(self) -> None:
        summary = {
            "run_id": self.run_dir.name,
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "stats": self.stats,
            "llm_budget": {
                "calls_used": self.gov.budget.calls_used,
                "tokens_used": self.gov.budget.tokens_used,
            },
        }
        (self.run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        print(f"\nrun summary -> {self.run_dir / 'summary.json'}")
