#!/usr/bin/env python
"""Research-agent CLI.

Typical runs:
  python scripts/run_pipeline.py                       # full 100-app run (needs GEMINI_API_KEY)
  python scripts/run_pipeline.py --limit 5             # first 5 apps only
  python scripts/run_pipeline.py --only 1,22,81        # specific apps
  python scripts/run_pipeline.py --mock --limit 3      # offline dry-run (no quota spent)
  python scripts/run_pipeline.py --skip-research       # re-analyze + re-render only
  python scripts/run_pipeline.py --export-sample       # draw the human-audit sample
  python scripts/run_pipeline.py --score data/audit/human-labels.yml
  python scripts/run_pipeline.py --verify-audit        # check the audit hash chain
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import yaml  # noqa: E402

from src.agents import auditor  # noqa: E402
from src.agents.orchestrator import Orchestrator  # noqa: E402
from src.analysis.patterns import analyze  # noqa: E402
from src.config import SETTINGS, REPO_ROOT  # noqa: E402
from src.governance.audit import AuditLog  # noqa: E402
from src.governance.engine import BudgetExceeded, GovernanceEngine  # noqa: E402
from src.llm.gemini import build_llm  # noqa: E402
from src.render.page import render  # noqa: E402
from src.store.canonical import CanonicalStore  # noqa: E402


def load_apps(path: Path) -> list[dict]:
    data = yaml.safe_load(Path(path).read_text())
    return data["apps"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apps", default=str(REPO / "apps.yml"))
    ap.add_argument("--limit", type=int, default=0, help="research only the first N")
    ap.add_argument("--only", default="", help="comma-separated app ids, e.g. 1,22,81")
    ap.add_argument("--mock", action="store_true", help="offline dry-run (MockLLM, no quota)")
    ap.add_argument("--skip-research", action="store_true")
    ap.add_argument("--skip-verify", action="store_true", help="store drafts without verification")
    ap.add_argument("--no-analyze", action="store_true")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--export-sample", action="store_true")
    ap.add_argument("--score", default="", help="path to filled human-labels.yml")
    ap.add_argument("--verify-audit", action="store_true")
    ap.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("run-%Y%m%d-%H%M%S"))
    args = ap.parse_args()

    policy_path = REPO / "governance.yaml"
    policy = yaml.safe_load(policy_path.read_text())
    audit_dir = REPO_ROOT / policy["audit"]["log_dir"]
    audit = AuditLog(audit_dir, enabled=policy["audit"].get("hash_chain", True))
    gov = GovernanceEngine(policy_path, audit)
    store = CanonicalStore(SETTINGS.canonical_db)

    if args.verify_audit:
        ok, first_bad, total = audit.verify()
        print(f"audit chain: {'OK' if ok else 'BROKEN'} "
              f"({total} records{'' if ok else f', first bad at #{first_bad}'})")
        return 0 if ok else 1

    apps = load_apps(Path(args.apps))
    print(f"governance: rpm={gov.policy['llm']['rpm']} "
          f"budget={gov.budget.max_calls} calls / {gov.budget.max_tokens} tokens | "
          f"https-only={gov.policy['network']['require_https']} "
          f"ssrf-guard={gov.policy['network']['block_private_ips']} "
          f"robots={gov.policy['network']['respect_robots']}")

    if not args.skip_research:
        llm = build_llm(gov, mock=args.mock)
        orch = Orchestrator(apps, gov, llm, store, SETTINGS.cache_dir,
                            SETTINGS.runs_dir, args.run_id, mock=args.mock)
        only_ids = [int(x) for x in args.only.split(",") if x.strip()]
        try:
            stats = orch.run(limit=args.limit, only_ids=only_ids, skip_verify=args.skip_verify)
            print("stats:", stats)
        except BudgetExceeded as exc:
            print(f"\n!! governance stopped the run: {exc}")
            print("   partial results are stored; raise budgets in governance.yaml to continue.")
        gov.export_quarantine(audit_dir / "quarantine.json")

    if args.export_sample:
        path = auditor.export_sample(store, gov, audit_dir)
        print(f"human-audit sample -> {path}\n"
              f"Fill the 'human' values in against the real vendor docs, then:\n"
              f"  python scripts/run_pipeline.py --score {path}")

    if args.score:
        report = auditor.score(store, gov, Path(args.score), audit_dir)
        o = report["overall"]
        print(f"accuracy v1 (first pass): {o['accuracy_v1_first_pass']:.1%}")
        print(f"accuracy v2 (verified):   {o['accuracy_v2_verified']:.1%}")
        print(f"report -> {audit_dir / 'accuracy-report.json'}")

    if not args.no_analyze:
        analyze(SETTINGS.canonical_db, SETTINGS.charts_dir)
    if not args.no_render:
        page = render(SETTINGS.site_dir, SETTINGS.charts_dir,
                      audit_dir / "accuracy-report.json")
        print(f"case-study page -> {page}")

    ok, first_bad, total = audit.verify()
    print(f"audit chain: {'OK' if ok else 'BROKEN'} ({total} records)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
