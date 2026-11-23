#!/usr/bin/env python
"""Standalone audit-log verifier: re-walks the sha256 hash chain and reports
the first tampered/deleted record, if any.

    python scripts/verify_audit.py
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import yaml  # noqa: E402

from src.config import REPO_ROOT  # noqa: E402
from src.governance.audit import AuditLog  # noqa: E402


def main() -> int:
    policy = yaml.safe_load((REPO / "governance.yaml").read_text())
    log_dir = REPO_ROOT / policy["audit"]["log_dir"]
    audit = AuditLog(log_dir)
    ok, first_bad, total = audit.verify()
    print(f"audit log: {audit.path}")
    print(f"records: {total} | chain: {'OK' if ok else 'BROKEN at record #' + str(first_bad)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
