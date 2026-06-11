"""Local quality dashboard: live views over the history file, gates, and risks.

Zero dependencies beyond the stdlib — `aqef dashboard` starts a small local
HTTP server. The page fetches /api/data, which re-reads framework.yaml, the
history JSONL, and the risk register on every request, so the dashboard is
always current: store a new run and refresh.

This is a read-only viewer. It renders evidence; it never mutates it.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from aqef.config import ConfigError, load_config
from aqef.coverage import (
    CoverageError,
    analyze_risk_coverage,
    load_coverage,
    risk_coverage_to_dict,
    undercovered,
)
from aqef.history import compute_trend, load_runs
from aqef.risks import RiskRegisterError, load_register


def build_dashboard_data(
    config_path: str | None = None,
    history_path: str | None = None,
    register_path: str | None = None,
    coverage_path: str | None = None,
) -> dict:
    """Assemble everything the dashboard renders. Missing sources degrade
    gracefully; parse errors are reported, never swallowed."""
    data: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": {
            "config": config_path,
            "history": history_path,
            "register": register_path,
            "coverage": coverage_path,
        },
        "config": None,
        "runs": [],
        "trends": {},
        "register": None,
        "risk_coverage": None,
        "errors": [],
    }

    if config_path and Path(config_path).exists():
        try:
            config = load_config(config_path)
            data["config"] = {
                "name": config.name,
                "version": config.version,
                "gates": {
                    name: {
                        "description": gate.description,
                        "rules": [asdict(rule) for rule in gate.rules],
                    }
                    for name, gate in config.gates.items()
                },
                "workflows": {
                    name: {"gate": wf.gate, "checkpoint": wf.human_checkpoint}
                    for name, wf in config.workflows.items()
                },
            }
        except ConfigError as exc:
            data["errors"].append(f"config: {exc}")

    if history_path:
        runs = load_runs(history_path)
        data["runs"] = [asdict(run) for run in runs]
        for gate_name in sorted({run.gate for run in runs}):
            gate_runs = [run for run in runs if run.gate == gate_name]
            data["trends"][gate_name] = compute_trend(gate_runs)

    if register_path and Path(register_path).exists():
        try:
            register = load_register(register_path)
            data["register"] = {
                "product": register.product,
                "risks": [
                    {
                        "id": risk.id,
                        "title": risk.title,
                        "score": risk.score,
                        "tier": risk.tier,
                        "likelihood": risk.likelihood,
                        "impact": risk.impact,
                        "areas": list(risk.areas),
                        "tests": list(risk.tests),
                        "owner": risk.owner,
                    }
                    for risk in sorted(register.risks, key=lambda r: -r.score)
                ],
                "untested_high": [r.id for r in register.untested(min_tier="high")],
            }
        except RiskRegisterError as exc:
            data["errors"].append(f"register: {exc}")

    if coverage_path and Path(coverage_path).exists() and data["register"] is not None:
        try:
            register = load_register(register_path)
            file_coverage = load_coverage(coverage_path)
            results = analyze_risk_coverage(register, file_coverage)
            payload = risk_coverage_to_dict(results)
            payload["undercovered_high_risk"] = [
                rc.risk.id for rc in undercovered(results, threshold=80)
            ]
            data["risk_coverage"] = payload
        except (RiskRegisterError, CoverageError) as exc:
            data["errors"].append(f"coverage: {exc}")

    return data


def create_server(
    config_path: str | None,
    history_path: str | None,
    register_path: str | None,
    port: int = 8765,
    coverage_path: str | None = None,
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the terminal quiet
            pass

        def _send(self, code: int, content_type: str, body: bytes):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/":
                self._send(200, "text/html; charset=utf-8", DASHBOARD_HTML.encode("utf-8"))
            elif self.path == "/api/data":
                payload = build_dashboard_data(
                    config_path, history_path, register_path, coverage_path
                )
                self._send(
                    200,
                    "application/json; charset=utf-8",
                    json.dumps(payload).encode("utf-8"),
                )
            else:
                self._send(404, "text/plain; charset=utf-8", b"not found")

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AQEF dashboard</title>
<style>
:root { color-scheme: light dark;
        --ok:#116329; --warn:#7d4e00; --bad:#a40e26; --muted:#3f4953;
        --border:#b7c0c9; --bg:#eef1f4; --info:#0550ae;
        --fg:#111418; --page:#ffffff; --warnbg:#fff1f0; --pillfg:#ffffff; }
[data-theme="dark"] { --ok:#3fb950; --warn:#d29922; --bad:#ff7b72; --muted:#aab4bf;
        --border:#444c56; --bg:#1c2128; --info:#58a6ff;
        --fg:#f0f3f6; --page:#0d1117; --warnbg:#2d1516; --pillfg:#0d1117; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { --ok:#3fb950; --warn:#d29922; --bad:#ff7b72;
        --muted:#aab4bf; --border:#444c56; --bg:#1c2128; --info:#58a6ff;
        --fg:#f0f3f6; --page:#0d1117; --warnbg:#2d1516; --pillfg:#0d1117; }
}
body { font-family: system-ui, sans-serif; max-width: 1080px; margin: 1.5rem auto;
       padding: 0 1rem 3rem; color: var(--fg); background: var(--page);
       font-size: 16px; line-height: 1.55; }
h1 { font-size: 1.8rem; margin: 0; }
h2 { font-size: 1.3rem; margin: 2.2rem 0 .8rem; border-bottom: 2px solid var(--border);
     padding-bottom: .35rem; }
h3 { font-size: 1.05rem !important; margin: 1.4rem 0 .5rem; }
.topbar { display: flex; align-items: center; justify-content: space-between;
          gap: 12px; flex-wrap: wrap; }
#theme-btn { font-size: .9rem; padding: .4rem .9rem; border-radius: 6px; cursor: pointer;
             border: 1px solid var(--border); background: var(--bg); color: var(--fg); }
table { border-collapse: collapse; width: 100%; font-size: 1rem; }
th, td { border: 1px solid var(--border); padding: .5rem .75rem; text-align: left; }
th { background: var(--bg); font-weight: 600; }
.pill { display: inline-block; padding: 2px 12px; border-radius: 12px;
        color: var(--pillfg); font-size: .85rem; font-weight: 700;
        letter-spacing: .02em; white-space: nowrap; }
.PASS, .PROMOTE, .improving { background: var(--ok); }
.WARN, .HOLD, .flat { background: var(--warn); }
.FAIL, .ROLLBACK, .worsening { background: var(--bad); }
.neutral { background: var(--muted); }
.tier-critical { background: var(--bad); } .tier-high { background: #e8590c; }
.tier-medium { background: var(--warn); } .tier-low { background: var(--muted); }
.muted { color: var(--muted); font-size: .95rem; }
.warnbox { background: var(--warnbg); border: 1.5px solid var(--bad); color: var(--bad);
           padding: .6rem .9rem; border-radius: 6px; margin: .5rem 0; font-size: 1rem;
           font-weight: 500; }
.cards { display: flex; gap: 14px; flex-wrap: wrap; margin: 1rem 0 1.25rem; }
.card { background: var(--bg); border: 1px solid var(--border); border-radius: 10px;
        padding: .8rem 1.2rem; min-width: 140px; }
.card .n { font-size: 1.7rem; font-weight: 700; } .card .l { font-size: .9rem; color: var(--muted); }
code { background: var(--bg); border: 1px solid var(--border); padding: 1px 6px;
       border-radius: 4px; font-size: .9rem; }
</style>
</head>
<body>
<div class="topbar">
  <h1>AQEF quality dashboard</h1>
  <button id="theme-btn" type="button">theme: auto</button>
</div>
<p class="muted" id="meta">loading…</p>
<div id="errors"></div>
<div class="cards" id="summary"></div>
<h2>Run history</h2>
<div id="runs"><p class="muted">no runs recorded yet — store one with:
<code>aqef gate &lt;gate&gt; --config framework.yaml --metrics m.json --store</code></p></div>
<h2>Latest run evidence</h2>
<div id="latest"><p class="muted">—</p></div>
<h2>Trends</h2>
<div id="trends"><p class="muted">—</p></div>
<h2>Risk register</h2>
<div id="register"><p class="muted">no register loaded</p></div>
<h2>Risk-weighted coverage</h2>
<div id="riskcov"><p class="muted">no coverage report loaded — start with
<code>aqef dashboard --coverage coverage.json --register risk-register.yaml</code></p></div>
<script>
const themeBtn = document.getElementById('theme-btn');
function applyTheme(t){
  if(t==='auto') document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme', t);
  themeBtn.textContent = 'theme: '+t;
  try { localStorage.setItem('aqef-theme', t); } catch(e) {}
}
let theme = 'auto';
try { theme = localStorage.getItem('aqef-theme') || 'auto'; } catch(e) {}
applyTheme(theme);
themeBtn.addEventListener('click', ()=>{
  theme = theme==='auto' ? 'light' : (theme==='light' ? 'dark' : 'auto');
  applyTheme(theme);
});

function pill(text, cls){ return '<span class="pill '+cls+'">'+text+'</span>'; }
function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;'); }
function fmt(n){ return (typeof n==='number') ? Math.round(n*100)/100 : n; }

async function refresh(){
  const r = await fetch('/api/data');
  const d = await r.json();
  document.getElementById('meta').textContent =
    (d.config ? d.config.name + ' v' + d.config.version + ' · ' : '') +
    'history: ' + (d.sources.history || '—') + ' · refreshed ' + d.generated_at;

  document.getElementById('errors').innerHTML =
    d.errors.map(e=>'<div class="warnbox">'+esc(e)+'</div>').join('');

  const runs = d.runs.slice().reverse();
  const counts = {PASS:0, WARN:0, FAIL:0};
  d.runs.forEach(x=>{ counts[x.verdict] = (counts[x.verdict]||0)+1; });
  document.getElementById('summary').innerHTML =
    '<div class="card"><div class="n">'+d.runs.length+'</div><div class="l">runs recorded</div></div>'+
    ['PASS','WARN','FAIL'].map(v=>'<div class="card"><div class="n">'+(counts[v]||0)+'</div><div class="l">'+v+'</div></div>').join('')+
    (d.register ? '<div class="card"><div class="n">'+d.register.risks.length+'</div><div class="l">risks tracked</div></div>' : '');

  if(runs.length){
    let h = '<table><tr><th>when</th><th>gate</th><th>verdict</th><th>workflow</th><th>subject</th></tr>';
    runs.slice(0,25).forEach(x=>{
      h += '<tr><td>'+esc(x.timestamp)+'</td><td>'+esc(x.gate)+'</td><td>'+pill(x.verdict, x.verdict)+
           '</td><td>'+esc(x.workflow||'—')+'</td><td>'+esc(x.subject||'—')+'</td></tr>';
    });
    document.getElementById('runs').innerHTML = h + '</table>';

    const latest = runs[0];
    let lh = '<p class="muted">'+esc(latest.timestamp)+' · gate '+esc(latest.gate)+' · '+pill(latest.verdict, latest.verdict)+'</p>';
    lh += '<table><tr><th>metric</th><th>actual</th><th>rule</th><th>severity</th><th>outcome</th></tr>';
    latest.rules.slice().sort((a,b)=>(a.passed?1:0)-(b.passed?1:0)).forEach(ru=>{
      const status = ru.passed ? pill('pass','PASS') : (ru.missing ? pill('missing evidence','WARN') : pill('FAIL','FAIL'));
      lh += '<tr><td>'+esc(ru.metric)+'</td><td>'+(ru.missing?'—':fmt(ru.actual))+'</td><td>'+esc(ru.operator)+' '+fmt(ru.threshold)+
            '</td><td>'+esc(ru.severity)+'</td><td>'+status+'</td></tr>';
    });
    document.getElementById('latest').innerHTML = lh + '</table>';
  }

  const gateNames = Object.keys(d.trends);
  if(gateNames.length){
    let th = '';
    gateNames.forEach(g=>{
      const t = d.trends[g];
      const vd = Object.entries(t.verdicts).map(([v,c])=>c+'× '+v).join(', ');
      th += '<h3>'+esc(g)+' <span class="muted">('+t.runs+' runs: '+vd+')</span></h3>';
      th += '<table><tr><th>metric</th><th>first</th><th>last</th><th>delta</th><th>assessment</th></tr>';
      Object.entries(t.metrics).forEach(([k,m])=>{
        const cls = m.assessment==='improving'?'improving':(m.assessment==='worsening'?'worsening':'neutral');
        th += '<tr><td>'+esc(k)+'</td><td>'+fmt(m.first)+'</td><td>'+fmt(m.last)+'</td><td>'+
              (m.delta>0?'+':'')+fmt(m.delta)+'</td><td>'+pill(m.assessment, cls)+'</td></tr>';
      });
      th += '</table>';
    });
    document.getElementById('trends').innerHTML = th;
  }

  if(d.register){
    let rh = '<p class="muted">product: '+esc(d.register.product)+'</p>';
    d.register.untested_high.forEach(id=>{
      rh += '<div class="warnbox">'+esc(id)+' is high/critical but has NO linked tests — untested risk</div>';
    });
    rh += '<table><tr><th>id</th><th>risk</th><th>score</th><th>tier</th><th>areas</th><th>tests</th><th>owner</th></tr>';
    d.register.risks.forEach(x=>{
      rh += '<tr><td>'+esc(x.id)+'</td><td>'+esc(x.title)+'</td><td>'+x.score+'</td><td>'+
            pill(x.tier,'tier-'+x.tier)+'</td><td><code>'+x.areas.map(esc).join('</code> <code>')+'</code></td><td>'+
            (x.tests.length ? x.tests.map(t=>'<code>'+esc(t)+'</code>').join(' ') : '<span class="pill FAIL">none</span>')+
            '</td><td>'+esc(x.owner||'—')+'</td></tr>';
    });
    document.getElementById('register').innerHTML = rh + '</table>';
  }

  if(d.risk_coverage){
    let ch = '';
    d.risk_coverage.undercovered_high_risk.forEach(id=>{
      ch += '<div class="warnbox">'+esc(id)+' is high/critical with coverage below 80% — low coverage meets high risk</div>';
    });
    ch += '<table><tr><th>risk</th><th>tier</th><th>area coverage</th><th>gap score</th><th>files</th></tr>';
    d.risk_coverage.risk_coverage.forEach(x=>{
      const cov = x.unmatched ? pill('no files matched','neutral')
        : fmt(x.coverage_pct)+'%' + (d.risk_coverage.undercovered_high_risk.includes(x.risk_id) ? ' '+pill('UNDER','FAIL') : '');
      ch += '<tr><td>'+esc(x.risk_id)+'</td><td>'+pill(x.tier,'tier-'+x.tier)+'</td><td>'+cov+
            '</td><td>'+fmt(x.gap_score)+'</td><td>'+x.files.length+'</td></tr>';
    });
    document.getElementById('riskcov').innerHTML = ch + '</table>'+
      '<p class="muted">gap score = risk score × uncovered fraction — the top row is where low coverage meets high risk</p>';
  }
}
refresh();
setInterval(refresh, 10000);
</script>
</body>
</html>
"""
