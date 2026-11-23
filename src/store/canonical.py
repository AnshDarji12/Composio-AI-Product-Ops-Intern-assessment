"""Canonical dataset store: data/apps.json - the single source of truth.

Upserts are keyed by app id and idempotent. The FIRST draft of each row is
preserved in `first_pass` (before verification) so accuracy can be reported
as "v1 draft" vs "v2 verified" later.
"""
import json
from pathlib import Path


class CanonicalStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.rows: dict[int, dict] = {}
        if self.path.exists():
            for row in json.loads(self.path.read_text()):
                self.rows[int(row["id"])] = row

    def upsert(self, row: dict, first_pass: dict | None = None,
               verified_by: str = "") -> None:
        rid = int(row["id"])
        existing = self.rows.get(rid, {})
        record = dict(row)
        record["first_pass"] = existing.get("first_pass") or first_pass or row
        record["verified_by"] = verified_by or existing.get("verified_by", "")
        if existing:
            # accumulate flags across passes, keep history of disputes
            record["flags"] = sorted(set(existing.get("flags", [])) | set(record.get("flags", [])))
            if existing.get("disputes"):
                record["disputes"] = existing["disputes"]
        self.rows[rid] = record
        self.save()

    def add_disputes(self, app_id: int, disputes: list[dict]) -> None:
        if app_id in self.rows and disputes:
            self.rows[app_id]["disputes"] = disputes
            self.save()

    def save(self) -> None:
        ordered = [self.rows[k] for k in sorted(self.rows)]
        self.path.write_text(json.dumps(ordered, indent=2, ensure_ascii=False))

    def all_rows(self) -> list[dict]:
        return [self.rows[k] for k in sorted(self.rows)]

    def get(self, app_id: int) -> dict | None:
        return self.rows.get(app_id)
