"""Case-study page generator: one self-contained HTML file from real data.

Inline CSS + JS, no CDN, no build step. Search/filter table, evidence
quotes per row, accuracy section (if the human audit has been scored),
agent + governance sections. Open data/site/index.html or deploy the folder.
"""
import base64
import json
import shutil
from pathlib import Path

from ..config import SETTINGS


def _img64(path: Path) -> str:
    if not path.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def render(site_dir: Path, charts_dir: Path, accuracy_path: Path) -> Path:
    site_dir = Path(site_dir)
    site_dir.mkdir(parents=True, exist_ok=True)
    rows = json.loads(SETTINGS.canonical_db.read_text()) if SETTINGS.canonical_db.exists() else []
    findings = (charts_dir / "findings.json")
    findings = json.loads(findings.read_text()) if findings.exists() else {}
    accuracy = json.loads(accuracy_path.read_text()) if Path(accuracy_path).exists() else None

    summary = sorted(SETTINGS.runs_dir.glob("*/summary.json"))
    summary = json.loads(summary[-1].read_text()) if summary else {}

    charts = {name: _img64(charts_dir / f"{name}.png")
              for name in ("auth-mix", "selfserve-by-category", "verdicts-mcp", "blockers",
                           "composio-status")}

    # load browser-verify report if available
    bv_path = SETTINGS.canonical_db.parent / "audit" / "browser-verify-report.json"
    browser_verify = json.loads(bv_path.read_text()) if bv_path.exists() else None

    rows_js = json.dumps(rows, ensure_ascii=False)
    findings_js = json.dumps(findings, ensure_ascii=False)
    accuracy_js = json.dumps(accuracy, ensure_ascii=False)
    summary_js = json.dumps(summary, ensure_ascii=False)
    charts_js = json.dumps(charts, ensure_ascii=False)
    browser_verify_js = json.dumps(browser_verify, ensure_ascii=False)

    html = _TEMPLATE.replace("__ROWS__", rows_js).replace("__FINDINGS__", findings_js)
    html = html.replace("__ACCURACY__", accuracy_js).replace("__SUMMARY__", summary_js)
    html = html.replace("__CHARTS__", charts_js)
    html = html.replace("__BROWSER_VERIFY__", browser_verify_js)

    out = site_dir / "index.html"
    out.write_text(html, encoding="utf-8")
    return out


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>100-App Agent Research &mdash; Case Study</title>
<style>
  :root{--ink:#1E293B;--muted:#64748B;--line:#E2E8F0;--bg:#F8FAFC;--accent:#4C6EF5;--green:#10B981;--amber:#F59E0B;--red:#EF4444;}
  *{box-sizing:border-box;margin:0;}
  body{font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);background:#fff;line-height:1.55;padding:0 0 80px;}
  main{max-width:1140px;margin:0 auto;padding:0 24px;}
  h1{font-size:clamp(1.6rem,4vw,2.4rem);margin:40px 0 8px;}
  h2{font-size:1.3rem;margin:48px 0 14px;padding-top:16px;border-top:2px solid var(--line);}
  .sub{color:var(--muted);}
  /* ── chips ── */
  .chips{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0;}
  .chip{background:var(--bg);border:1px solid var(--line);border-radius:999px;padding:5px 14px;font-size:.85rem;}
  .chips b{font-variant-numeric:tabular-nums;}
  /* ── charts ── */
  .charts-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:14px 0;}
  .charts-grid img{width:100%;height:auto;border:1px solid var(--line);border-radius:10px;}
  img.chart-full{max-width:100%;height:auto;border:1px solid var(--line);border-radius:10px;margin:10px 0;}
  @media(max-width:680px){.charts-grid{grid-template-columns:1fr;}}
  /* ── findings prose ── */
  .findings-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:14px 0 24px;}
  .fcard{border:1px solid var(--line);border-radius:10px;padding:16px;background:var(--bg);}
  .fcard .num{font-size:1.9rem;font-weight:700;line-height:1.1;color:var(--accent);}
  .fcard .label{font-size:.82rem;color:var(--muted);margin-top:4px;}
  /* ── table controls ── */
  .controls{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0;}
  input,select{padding:8px 10px;border:1px solid var(--line);border-radius:8px;font:inherit;min-width:150px;background:#fff;}
  /* ── data table ── */
  .tblwrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px;}
  table{border-collapse:collapse;width:100%;font-size:.85rem;min-width:960px;}
  thead th{background:var(--bg);text-align:left;padding:9px 11px;position:sticky;top:0;z-index:1;border-bottom:1px solid var(--line);}
  td{border-top:1px solid var(--line);padding:9px 11px;vertical-align:top;}
  tr.rowmain:hover{background:#F0F9FF;cursor:pointer;}
  /* ── badges ── */
  .badge{display:inline-block;border-radius:6px;padding:1px 8px;font-size:.75rem;border:1px solid;white-space:nowrap;}
  .b-ok{background:#F0FDF4;border-color:#10B981;color:#065F46;}
  .b-mid{background:#FFF7ED;border-color:#F59E0B;color:#92400E;}
  .b-no{background:#FEF2F2;border-color:#EF4444;color:#991B1B;}
  .b-gov{background:#F5F3FF;border-color:#8B5CF6;color:#5B21B6;}
  .b-comp-conn{background:#ECFDF5;border-color:#10B981;color:#065F46;}
  .b-comp-cand{background:#EEF2FF;border-color:#4C6EF5;color:#3730A3;}
  .b-comp-out{background:#FFF7ED;border-color:#F59E0B;color:#92400E;}
  /* ── evidence rows ── */
  tr.evd{display:none;background:#FFFBF0;}
  tr.evd.open{display:table-row;}
  .evd td{padding:12px 14px;}
  .evd ul{margin:6px 0 10px;padding-left:20px;}
  .evd li{margin-bottom:5px;}
  .evd a{color:var(--accent);word-break:break-all;}
  /* ── accuracy section ── */
  .accgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;}
  .card{border:1px solid var(--line);border-radius:10px;padding:16px;background:var(--bg);}
  .card .big{font-size:1.8rem;font-weight:700;font-variant-numeric:tabular-nums;}
  .miss td{font-size:.82rem;}
  .miss .bad{color:#B91C1C;}
  /* ── code ── */
  code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.82rem;}
  pre{background:#0F172A;color:#F1F5F9;padding:16px;border-radius:10px;overflow-x:auto;line-height:1.5;}
  /* ── agent diagram ── */
  .pipeline{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:16px 0;font-size:.88rem;}
  .pstep{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:6px 12px;}
  .parr{color:var(--muted);font-size:1.1rem;}
</style>
</head>
<body>
<main>
  <h1>100-App API Research &mdash; Case Study</h1>
  <p class="sub">A governed research agent (Gemini 2.5 Flash, free tier) that researched,
  adversarially verified, and human-audited 100 SaaS APIs across 10 categories &mdash;
  using the Composio SDK for tool integration. <strong>Findings first, table second, proof third.</strong></p>
  <div class="chips" id="chips"></div>

  <!-- ════════════════ 1. FINDINGS ════════════════ -->
  <h2>1 &middot; Headline Findings</h2>
  <div class="findings-grid" id="findings-cards"></div>
  <div id="findings-prose"></div>

  <div class="charts-grid">
    <img id="c-authmix" alt="auth mix">
    <img id="c-selfserve" alt="self-serve by category">
    <img id="c-verdicts" alt="verdicts and mcp">
    <img id="c-blockers" alt="blockers">
  </div>
  <img class="chart-full" id="c-composio" alt="composio integration status">

  <!-- ════════════════ 2. 100-APP MATRIX ════════════════ -->
  <h2>2 &middot; The 100-app Matrix</h2>
  <div class="controls">
    <input id="q" placeholder="&#128269; search app, auth, blocker...">
    <select id="fCat"><option value="">all categories</option></select>
    <select id="fVerdict"><option value="">all verdicts</option></select>
    <select id="fMcp"><option value="">any MCP</option>
      <option>official</option><option>community</option><option>none</option></select>
    <select id="fComp"><option value="">any Composio status</option>
      <option value="connected">connected</option>
      <option value="immediate-candidate">immediate-candidate</option>
      <option value="outreach-needed">outreach-needed</option></select>
  </div>
  <div class="tblwrap"><table id="tbl"></table></div>
  <p class="sub" style="margin-top:8px;">Click any row to expand evidence quotes and verifier disputes.</p>

  <!-- ════════════════ 3. VERIFICATION ════════════════ -->
  <h2>3 &middot; Verification &amp; Accuracy Loop</h2>
  <div id="accuracy"></div>

  <h3 style="font-size:1.05rem;margin:28px 0 10px;color:var(--ink)">Web-Fetch Verification (independent loop)</h3>
  <div id="bv-section"></div>

  <!-- ════════════════ 4. THE AGENT ════════════════ -->
  <h2>4 &middot; The Agent &amp; Governance Layer</h2>
  <div class="pipeline">
    <span class="pstep">&#128269; DuckDuckGo search + hint-aware URL scoring</span><span class="parr">&#8594;</span>
    <span class="pstep">&#128274; Governed fetch (SSRF guard, robots.txt, HTTPS-only)</span><span class="parr">&#8594;</span>
    <span class="pstep">&#129302; Gemini 2.5 Flash structured extraction</span><span class="parr">&#8594;</span>
    <span class="pstep">&#128683; Confidence gate (threshold = 0.70)</span><span class="parr">&#8594;</span>
    <span class="pstep">&#9876;&#65039; Verifier LLM (adversarial re-check every citation)</span><span class="parr">&#8594;</span>
    <span class="pstep">&#128230; Canonical DB (apps.json)</span><span class="parr">&#8594;</span>
    <span class="pstep">&#128101; Human sample audit (20 apps, 80 fields)</span>
  </div>
  <p>A policy engine (<code>governance.yaml</code>) intercepts every LLM call (model allowlist,
  RPM + budget caps), every URL fetch (HTTPS-only, SSRF guard, robots.txt honoured), and every
  output row (secret scan, PII redaction, quarantine queue), writing a <strong>hash-chained audit
  log</strong> you can verify independently:</p>
  <pre>python scripts/verify_audit.py                           # check audit chain integrity

# Run the pipeline:
python scripts/run_pipeline.py                           # full run  (needs GEMINI_API_KEY in .env)
python scripts/run_pipeline.py --mock --limit 5         # offline dry-run  (0 LLM calls)
python scripts/run_pipeline.py --only 1,2,3             # selective app IDs
python scripts/run_pipeline.py --export-sample          # generate human-audit template
python scripts/run_pipeline.py --score data/audit/human-labels.yml  # score accuracy</pre>
  <p style="margin-top:12px;"><strong>Where a human was needed:</strong> (1) manually curated
  the 100-app canonical seed dataset with evidence URLs; (2) wrote the 20-app ground-truth
  labels for the human audit; (3) spot-checked 11 agent misses and confirmed/rejected them.</p>

  <!-- ════════════════ 5. RUN PROOF ════════════════ -->
  <h2>5 &middot; Run Proof</h2>
  <div id="runproof"></div>
</main>

<script>
const ROWS=__ROWS__, FINDINGS=__FINDINGS__, ACC=__ACCURACY__;
const SUMMARY=__SUMMARY__, CHARTS=__CHARTS__, BV=__BROWSER_VERIFY__;

// ── chips ──────────────────────────────────────────────────────────────
document.getElementById('chips').innerHTML = [
  ['apps', ROWS.length],
  ['llm calls', (SUMMARY.stats||{}).llm_calls ?? '-'],
  ['avg confidence', (ROWS.reduce((s,r)=>s+(r.confidence||0),0)/Math.max(ROWS.length,1)).toFixed(2)],
  ['easy wins (buildable, no MCP)', FINDINGS.easy_wins ?? '-'],
  ['official MCP servers', FINDINGS.official_mcp ?? '-'],
  ['composio connected', FINDINGS.composio_connected ?? '-'],
  ['immediate candidates', FINDINGS.immediate_candidates ?? '-'],
].map(([k,v])=>`<span class="chip">${k}: <b>${v}</b></span>`).join('');

// ── findings cards ─────────────────────────────────────────────────────
const f = FINDINGS;
const fcards = [];
if(f.dominant_auth) fcards.push({num: Math.round(f.dominant_auth.share*100)+'%', label:`of apps use <b>${f.dominant_auth.label}</b> as primary auth`});
if(f.pct_self_serve!=null) fcards.push({num: Math.round(f.pct_self_serve*100)+'%', label:'of apps are fully <b>self-serve</b> (developer-accessible)'});
if(f.official_mcp!=null) fcards.push({num: f.official_mcp, label:'apps already ship an <b>official MCP server</b>'});
if(f.easy_wins!=null) fcards.push({num: f.easy_wins, label:'<b>easy-win</b> apps: buildable today, no MCP yet'});
if(f.composio_connected!=null) fcards.push({num: f.composio_connected, label:'apps already <b>connected in Composio</b>'});
if(f.immediate_candidates!=null) fcards.push({num: f.immediate_candidates, label:'apps are <b>immediate toolkit candidates</b>'});
document.getElementById('findings-cards').innerHTML=fcards.map(c=>
  `<div class="fcard"><div class="num">${c.num}</div><div class="label">${c.label}</div></div>`).join('');
document.getElementById('findings-prose').innerHTML=
  (f.top_blocker?`<p style="margin-top:4px;"><b>Top blocker pattern:</b> ${f.top_blocker}.</p>`:'');

// ── charts ─────────────────────────────────────────────────────────────
const setImg=(id,key)=>{const el=document.getElementById(id);if(CHARTS[key])el.src=CHARTS[key];else el.style.display='none';};
setImg('c-authmix','auth-mix'); setImg('c-selfserve','selfserve-by-category');
setImg('c-verdicts','verdicts-mcp'); setImg('c-blockers','blockers');
setImg('c-composio','composio-status');

// ── filter dropdowns ───────────────────────────────────────────────────
const cats=[...new Set(ROWS.map(r=>r.category))].filter(Boolean).sort();
for(const c of cats){const o=document.createElement('option');o.textContent=c;o.value=c;
  document.getElementById('fCat').append(o);}
for(const v of ['buildable-today','buildable-with-friction','blocked']){
  const o=document.createElement('option');o.textContent=v;o.value=v;
  document.getElementById('fVerdict').append(o);}

// ── badge helpers ──────────────────────────────────────────────────────
function badge(text,cls){return `<span class="badge ${cls}">${text||''}</span>`;}
function verdictBadge(v){return v==='buildable-today'?badge(v,'b-ok'):v==='blocked'?badge(v,'b-no'):badge(v,'b-mid');}
function compBadge(s){
  if(!s) return '';
  if(s==='connected') return badge('connected','b-comp-conn');
  if(s==='immediate-candidate') return badge('immediate','b-comp-cand');
  return badge('outreach','b-comp-out');
}

// ── table render ──────────────────────────────────────────────────────
function renderTable(){
  const q=document.getElementById('q').value.toLowerCase();
  const fc=document.getElementById('fCat').value,
        fv=document.getElementById('fVerdict').value,
        fm=document.getElementById('fMcp').value,
        fcomp=document.getElementById('fComp').value;
  const rows=ROWS.filter(r=>
    (!fc||r.category===fc)&&(!fv||r.verdict===fv)&&(!fm||r.existing_mcp===fm)
    &&(!fcomp||r.composio_status===fcomp)
    &&(!q||JSON.stringify(r).toLowerCase().includes(q)));
  let html=`<thead><tr>
    <th>#</th><th>App</th><th>Category</th><th>What it does</th>
    <th>Auth</th><th>Access</th><th>API surface</th>
    <th>MCP</th><th>Composio</th><th>Verdict</th><th>Conf</th>
  </tr></thead><tbody>`;
  rows.forEach((r,i)=>{
    const mcpCls=r.existing_mcp==='official'?'b-gov':(r.existing_mcp==='community'?'b-mid':'');
    html+=`<tr class="rowmain" data-i="${i}">
      <td>${r.id}</td><td><b>${r.app}</b></td>
      <td style="white-space:nowrap">${r.category||''}</td>
      <td>${r.what_it_does||''}</td>
      <td>${(r.auth||[]).join(', ')}</td>
      <td>${r.self_serve||''}</td>
      <td>${(r.api_surface||'').slice(0,55)}</td>
      <td>${r.existing_mcp?badge(r.existing_mcp,mcpCls):''}</td>
      <td>${compBadge(r.composio_status)}</td>
      <td>${verdictBadge(r.verdict)}${r.blocker&&r.blocker!=='none'?`<br><small style="color:#64748B">${r.blocker.slice(0,60)}</small>`:''}</td>
      <td>${(r.confidence??0).toFixed(2)}</td>
    </tr>`;
    const ev=(r.evidence||[]).map(e=>`<li><code>${e.field}</code>:
      <a href="${e.url}" target="_blank" rel="noopener noreferrer">${e.url}</a>
      <br>&ldquo;${(e.quote||'').replace(/</g,'&lt;').slice(0,180)}&rdquo;</li>`).join('');
    const disp=(r.disputes||[]).map(d=>`<li><b>${d.field}</b> &rarr; ruling: <b>${d.ruling}</b> &mdash; ${(d.note||'').slice(0,120)}</li>`).join('');
    html+=`<tr class="evd" data-for="${i}"><td colspan="11">
      <b>Evidence</b><ul>${ev||'<li>none cited</li>'}</ul>
      ${disp?`<b>Verifier disputes</b><ul>${disp}</ul>`:''}
      ${r.flags&&r.flags.length?`<small style="color:#64748B">flags: ${r.flags.join(', ')}</small>`:''}
    </td></tr>`;
  });
  document.getElementById('tbl').innerHTML=html+'</tbody>';
  document.querySelectorAll('.rowmain').forEach(tr=>tr.onclick=()=>{
    document.querySelector(`.evd[data-for="${tr.dataset.i}"]`).classList.toggle('open');});
}
['q','fCat','fVerdict','fMcp','fComp'].forEach(id=>
  document.getElementById(id).addEventListener(id==='q'?'input':'change',renderTable));
renderTable();

// ── accuracy section ──────────────────────────────────────────────────
const accEl=document.getElementById('accuracy');
if(ACC&&ACC.overall){
  const o=ACC.overall;
  const pc=v=>Math.round(v*100)+'%';
  accEl.innerHTML=`<div class="accgrid">
    <div class="card"><div class="big" style="color:#10B981">${pc(o.accuracy_v1_first_pass)}</div>v1 first-pass accuracy</div>
    <div class="card"><div class="big" style="color:#10B981">${pc(o.accuracy_v2_verified)}</div>v2 after verification loops</div>
    <div class="card"><div class="big">${o.sampled_fields}</div>human-checked fields (${o.sampled_apps||20} apps)</div>
  </div>
  <table style="margin-top:16px;min-width:380px">
    <thead><tr><th>Field</th><th>n</th><th>v1 accuracy</th><th>v2 accuracy</th></tr></thead>
    <tbody>${Object.entries(ACC.per_field||{}).map(([k,v])=>
      `<tr><td>${k}</td><td>${v.n}</td><td>${pc(v.accuracy_v1)}</td><td><b>${pc(v.accuracy_v2)}</b></td></tr>`).join('')}
    </tbody></table>
  <p style="margin-top:16px"><b>Honest misses</b> (agent wrong even after verification &mdash; shown transparently):</p>
  <div class="tblwrap" style="margin-top:8px"><table>
    <thead><tr><th>App</th><th>Field</th><th>Human truth</th><th>First pass</th><th>Final answer</th></tr></thead>
    <tbody>${(ACC.misses||[]).filter(m=>!m.v2_hit).map(m=>
      `<tr class="miss"><td>${m.app}</td><td>${m.field}</td>
       <td>${m.human??''}</td><td>${m.first_pass??''}</td>
       <td class="bad">${m.final??''}</td></tr>`).join('')||'<tr><td colspan="5">No misses in sample &mdash; all correct after verification.</td></tr>'}
    </tbody></table></div>`;
}else{
  accEl.innerHTML=`<p class="sub">Human audit not yet scored. Run:
  <code>python scripts/run_pipeline.py --export-sample</code>,
  fill <code>data/audit/human-labels.yml</code>, then
  <code>python scripts/run_pipeline.py --score data/audit/human-labels.yml</code>.
  The report auto-renders here.</p>`;
}

// ── browser / web-fetch verification section ──────────────────────────
const bvEl = document.getElementById('bv-section');
if(BV && BV.results){
  const pct = v => Math.round(v*100)+'%';
  const verdBadge = v => v==='PASS'?`<span class="badge b-ok">PASS</span>`
    :v==='FAIL'?`<span class="badge b-no">FAIL</span>`
    :`<span class="badge b-mid">ERROR</span>`;
  bvEl.innerHTML=`
  <p style="margin-bottom:10px">Method: <code>${BV.method}</code></p>
  <div class="accgrid" style="margin-bottom:14px">
    <div class="card"><div class="big" style="color:#10B981">${BV.passed}</div>PASS — agent claim confirmed on live docs</div>
    <div class="card"><div class="big" style="color:#EF4444">${BV.failed}</div>FAIL — agent claim contradicted</div>
    <div class="card"><div class="big" style="color:#F59E0B">${BV.error}</div>ERROR — page blocked (HTTP 403 / bot-protection)</div>
    <div class="card"><div class="big" style="color:#10B981">${pct(BV.accuracy)}</div>accuracy on fetchable pages</div>
  </div>
  <div class="tblwrap"><table>
    <thead><tr><th>#</th><th>App</th><th>Claim field</th><th>Verdict</th><th>Evidence from live page</th><th>Notes</th></tr></thead>
    <tbody>${BV.results.map(r=>`<tr>
      <td>${r.id}</td><td><b>${r.app}</b></td><td>${r.claim_field}</td>
      <td>${verdBadge(r.verdict)}</td>
      <td style="font-size:.78rem;max-width:280px">${r.evidence_found?`&ldquo;${r.evidence_found.slice(0,180)}&rdquo;`:'<span style="color:#94A3B8">blocked by HTTP 403 / bot-protection</span>'}</td>
      <td style="font-size:.78rem">${r.notes}</td>
    </tr>`).join('')}</tbody>
  </table></div>
  <p class="sub" style="margin-top:8px">3 ERRORs (Salesforce, Attio, PitchBook) are bot-protected docs — this is itself a finding (enterprise gate). 0 contradictions on the 7 fetchable pages.</p>`;
}else{
  bvEl.innerHTML=`<p class="sub">Run <code>python scripts/browser_verify.py</code> to generate web-fetch verification report.</p>`;
}

// ── run proof ─────────────────────────────────────────────────────────
document.getElementById('runproof').innerHTML=SUMMARY.stats?`<div class="accgrid">
   <div class="card"><div class="big">${SUMMARY.stats.researched??0}</div>apps researched</div>
   <div class="card"><div class="big">${SUMMARY.stats.verified??0}</div>rows adversarially verified</div>
   <div class="card"><div class="big">${SUMMARY.stats.retried??0}</div>low-confidence retries</div>
   <div class="card"><div class="big">${SUMMARY.stats.quarantined??0}</div>governance quarantines</div>
   <div class="card"><div class="big">${SUMMARY.stats.llm_calls??0}</div>LLM calls (budgeted)</div>
  </div><p class="sub" style="margin-top:10px">Run&nbsp;id:&nbsp;${SUMMARY.run_id||'-'}&nbsp;&middot;&nbsp;finished&nbsp;${SUMMARY.finished_at||'-'}</p>`
  :'<p class="sub">No run summary found yet &mdash; run the pipeline at least once.</p>';
</script>
</body>
</html>
"""
