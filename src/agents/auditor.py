"""HUMAN-IN-THE-LOOP auditor.

1. export_sample(): draws a random sample of researched rows and writes a
   fill-in labels file (data/audit/human-labels.yml). The human checks each
   sampled app against the REAL vendor docs and records ground truth.
2. score(): compares human labels against BOTH the first-pass draft and the
   verified final row -> the v1 -> v2 accuracy story, per field and overall.

Neither step uses the LLM: the ground truth is human-provided by design.
"""
import json
import random
from pathlib import Path

import yaml

from ..governance.engine import GovernanceEngine
from ..store.canonical import CanonicalStore

SCORED_FIELDS = ["auth", "self_serve", "existing_mcp", "verdict"]


def export_sample(store: CanonicalStore, gov: GovernanceEngine,
                  audit_dir: Path, sample_size: int | None = None,
                  seed: int = 42) -> Path:
    rows = [r for r in store.all_rows() if not r.get("flags") or
            not {"mock-mode"} & set(r.get("flags", []))]
    rows = store.all_rows() if not rows else rows
    n = sample_size or gov.audit_sample_size
    sample = random.Random(seed).sample(rows, min(n, len(rows)))

    labels_path = Path(audit_dir) / "human-labels.yml"
    doc = [
        "# Human audit labels - fill this in against the REAL vendor docs.",
        "# For each app below: put your ground-truth value in each field,",
        "# keep 'field_ok: true' only where the agent's value matched.",
        "labels:",
    ]
    for r in sample:
        doc.append(f"  - id: {r['id']}")
        doc.append(f"    app: {r['app']}")
        doc.append("    fields:")
        for f in SCORED_FIELDS:
            mine = r.get(f)
            if isinstance(mine, list):
                mine = ", ".join(mine)
            doc.append(f"      {f}: {{agent: {json.dumps(mine)}, human: \"\", field_ok: null}}")
        doc.append("    notes: \"\"")
    labels_path.write_text("\n".join(doc) + "\n")
    gov.audit.append("human_sample_exported", "auditor", n=len(sample),
                     ids=[r["id"] for r in sample])
    return labels_path


def score(store: CanonicalStore, gov: GovernanceEngine,
          labels_path: Path, out_dir: Path) -> dict:
    data = yaml.safe_load(Path(labels_path).read_text())
    per_field = {f: {"v1_ok": 0, "v2_ok": 0, "n": 0} for f in SCORED_FIELDS}
    misses: list[dict] = []

    for item in data.get("labels", []):
        row = store.get(int(item["id"]))
        if row is None:
            continue
        for field, spec in (item.get("fields") or {}).items():
            if field not in per_field or spec.get("field_ok") is None:
                continue
            per_field[field]["n"] += 1
            if spec.get("field_ok"):
                per_field[field]["v1_ok"] += 1
                per_field[field]["v2_ok"] += 1
            else:
                fp = (row.get("first_pass") or {}).get(field)
                fin = row.get(field)
                human = spec.get("human")
                v1_hit = _norm(fp) == _norm(human)
                v2_hit = _norm(fin) == _norm(human)
                per_field[field]["v1_ok"] += int(v1_hit)
                per_field[field]["v2_ok"] += int(v2_hit)
                misses.append({
                    "id": row["id"], "app": row["app"], "field": field,
                    "human": human, "first_pass": fp, "final": fin,
                    "v1_hit": v1_hit, "v2_hit": v2_hit,
                })

    totals = {"v1_ok": sum(f["v1_ok"] for f in per_field.values()),
              "v2_ok": sum(f["v2_ok"] for f in per_field.values()),
              "n": sum(f["n"] for f in per_field.values())}
    report = {
        "overall": {
            "accuracy_v1_first_pass": round(totals["v1_ok"] / max(totals["n"], 1), 3),
            "accuracy_v2_verified": round(totals["v2_ok"] / max(totals["n"], 1), 3),
            "sampled_fields": totals["n"],
        },
        "per_field": {
            f: {
                "n": v["n"],
                "accuracy_v1": round(v["v1_ok"] / max(v["n"], 1), 3),
                "accuracy_v2": round(v["v2_ok"] / max(v["n"], 1), 3),
            } for f, v in per_field.items() if v["n"]
        },
        "misses": misses,
    }
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "accuracy-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    gov.audit.append("accuracy_scored", "auditor", overall=report["overall"])
    return report


def _norm(value) -> str:
    if isinstance(value, list):
        return ", ".join(sorted(str(v).lower() for v in value))
    return str(value).strip().lower()
