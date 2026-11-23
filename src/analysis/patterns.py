"""Pattern analysis: turns 100 rows into the headline findings.

Outputs (data/charts/): 4 PNG charts + findings.json with the numbers the
case-study page leads with. Pure pandas/matplotlib - no LLM involved.
"""
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ACCENT = "#4C6EF5"
GRAY = "#E5E7EB"
BLUE_FAMILY = ["#DBEAFE", "#BFDBFE", "#93C5FD", "#60A5FA", "#3B82F6"]
AMBER = "#F59E0B"
TEXT = "#1E293B"


def analyze(apps_json: Path, charts_dir: Path) -> dict:
    rows = json.loads(Path(apps_json).read_text())
    df = pd.DataFrame(rows)
    charts_dir.mkdir(parents=True, exist_ok=True)
    findings: dict = {"apps": len(df)}

    # ── auth mix ──────────────────────────────────────────────────────
    auth_counts = Counter(
        a.strip() for auths in df["auth"] for a in (auths or []) if a
    )
    if auth_counts:
        fig, ax = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
        labels, values = zip(*auth_counts.most_common())
        colors = [ACCENT if i == 0 else GRAY for i in range(len(labels))]
        ax.barh(labels[::-1], values[::-1], color=colors[::-1])
        for i, v in enumerate(values[::-1]):
            ax.text(v, i, f"  {v}", va="center", fontsize=11, color=TEXT)
        ax.set_title(f"Dominant auth: {labels[0]} ({values[0]}/{len(df)} apps)",
                     fontsize=13, color=TEXT, loc="left")
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=11)
        fig.savefig(charts_dir / "auth-mix.png", dpi=200)
        plt.close(fig)
        findings["dominant_auth"] = {"label": labels[0],
                                     "share": round(values[0] / len(df), 3)}

    # ── self-serve vs gated, by category ─────────────────────────────
    order = ["self-serve", "paid-tier", "admin-approval", "partner-gated", "unknown"]
    ct = pd.crosstab(df["category"], df["self_serve"])
    ct = ct.reindex(columns=[c for c in order if c in ct.columns]).fillna(0)
    if not ct.empty:
        fig, ax = plt.subplots(figsize=(9, 5), constrained_layout=True)
        left = pd.Series(0, index=ct.index, dtype=float)
        for i, col in enumerate(ct.columns):
            vals = ct[col] / ct.sum(axis=1) * 100
            ax.barh(ct.index, vals, left=left, color=BLUE_FAMILY[i % len(BLUE_FAMILY)],
                    label=col, height=0.62)
            left = left + vals
        ax.invert_yaxis()
        ax.set_xlabel("% of apps in category", fontsize=11)
        ax.set_title("Self-serve vs gated access, by category",
                     fontsize=13, color=TEXT, loc="left")
        ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", frameon=False, fontsize=10)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=10)
        fig.savefig(charts_dir / "selfserve-by-category.png", dpi=200)
        plt.close(fig)
        known = df[df["self_serve"] != "unknown"]
        findings["pct_self_serve"] = round(
            (known["self_serve"] == "self-serve").mean() if len(known) else 0, 3)

    # ── verdicts + MCP coverage ──────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    verdicts = df["verdict"].value_counts()
    axes[0].barh(verdicts.index[::-1], verdicts.values[::-1],
                 color=[ACCENT if v == "buildable-today" else GRAY
                        for v in verdicts.index[::-1]])
    axes[0].set_title("Buildability verdicts", fontsize=12, color=TEXT, loc="left")
    axes[0].spines[["top", "right"]].set_visible(False)
    mcp = df["existing_mcp"].value_counts()
    axes[1].barh(mcp.index[::-1], mcp.values[::-1],
                 color=[AMBER if v == "official" else GRAY for v in mcp.index[::-1]])
    axes[1].set_title("Existing MCP servers", fontsize=12, color=TEXT, loc="left")
    axes[1].spines[["top", "right"]].set_visible(False)
    for ax in axes:
        ax.tick_params(labelsize=10)
    fig.savefig(charts_dir / "verdicts-mcp.png", dpi=200)
    plt.close(fig)
    findings["easy_wins"] = int(((df["verdict"] == "buildable-today") &
                                 (df["existing_mcp"].isin(["none", "unknown"]))).sum())
    findings["official_mcp"] = int((df["existing_mcp"] == "official").sum())

    # ── blocker frequency ────────────────────────────────────────────
    blockers = df["blocker"].dropna().astype(str)
    blockers = blockers[~blockers.str.lower().isin(["none", "null", ""])]
    key = blockers.str.lower().str.replace(r"[^a-z ]", "", regex=True).str.strip()
    if not key.empty:
        top = Counter(key).most_common(6)
        fig, ax = plt.subplots(figsize=(8, 3.6), constrained_layout=True)
        labels, values = zip(*top)
        ax.barh([l[:44] for l in labels][::-1], values[::-1], color=GRAY)
        ax.set_title("Most common blockers (normalised)", fontsize=13, color=TEXT, loc="left")
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=10)
        fig.savefig(charts_dir / "blockers.png", dpi=200)
        plt.close(fig)
        findings["top_blocker"] = labels[0] if labels else None

    # ── composio status breakdown ────────────────────────────────────
    if "composio_status" in df.columns:
        cs_counts = df["composio_status"].fillna("unknown").value_counts()
        fig, ax = plt.subplots(figsize=(7, 3), constrained_layout=True)
        STATUS_COLORS = {
            "connected": "#10B981",
            "immediate-candidate": "#4C6EF5",
            "outreach-needed": "#F59E0B",
            "unknown": "#94A3B8",
        }
        bar_colors = [STATUS_COLORS.get(v, GRAY) for v in cs_counts.index[::-1]]
        ax.barh(cs_counts.index[::-1], cs_counts.values[::-1], color=bar_colors)
        for i, v in enumerate(cs_counts.values[::-1]):
            ax.text(v, i, f"  {v}", va="center", fontsize=11, color=TEXT)
        ax.set_title("Composio integration status across 100 apps",
                     fontsize=13, color=TEXT, loc="left")
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=11)
        fig.savefig(charts_dir / "composio-status.png", dpi=200)
        plt.close(fig)
        findings["composio_connected"] = int((df["composio_status"] == "connected").sum())
        findings["immediate_candidates"] = int((df["composio_status"] == "immediate-candidate").sum())
        findings["outreach_needed"] = int((df["composio_status"] == "outreach-needed").sum())

    (charts_dir / "findings.json").write_text(json.dumps(findings, indent=2))
    print(f"findings -> {charts_dir / 'findings.json'}")
    return findings
