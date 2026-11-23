"""Tamper-evident audit log: append-only JSONL with a sha256 hash chain.

Each record carries `prev` (hash of the previous record) and `hash`
(sha256 over the canonical serialisation of the record). Any later edit
or deletion of a record breaks the chain and `verify()` reports the first
bad index - this is what makes the research run auditable after the fact.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


class AuditLog:
    def __init__(self, log_dir: Path, enabled: bool = True) -> None:
        self.enabled = enabled
        self.path = Path(log_dir) / "audit.jsonl"
        if self.enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._last_hash = self._load_last_hash()

    # ── write path ────────────────────────────────────────────────
    def append(self, event: str, actor: str, **data) -> None:
        if not self.enabled:
            return
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event": event,
            "actor": actor,
            "data": data,
            "prev": self._last_hash,
        }
        payload = json.dumps(record, sort_keys=True, ensure_ascii=False)
        record["hash"] = hashlib.sha256(payload.encode()).hexdigest()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._last_hash = record["hash"]

    def _load_last_hash(self) -> str:
        if not self.path.exists():
            return ""
        last = ""
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    last = json.loads(line).get("hash", last)
        return last

    # ── verification path ─────────────────────────────────────────
    def verify(self) -> tuple[bool, int, int]:
        """Re-walk the chain. Returns (ok, first_bad_index, total_records)."""
        if not self.path.exists():
            return True, -1, 0
        prev = ""
        ok, first_bad, total = True, -1, 0
        with self.path.open(encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                line = line.strip()
                if not line:
                    continue
                total += 1
                rec = json.loads(line)
                expected = {k: rec[k] for k in ("ts", "event", "actor", "data", "prev")}
                digest = hashlib.sha256(
                    json.dumps(expected, sort_keys=True, ensure_ascii=False).encode()
                ).hexdigest()
                if rec.get("prev") != prev or rec.get("hash") != digest:
                    ok, first_bad = False, i
                    break
                prev = rec["hash"]
        return ok, first_bad, total
