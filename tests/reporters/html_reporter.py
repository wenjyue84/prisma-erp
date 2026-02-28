"""HTML report generator — renders a self-contained HTML dashboard from a JSON report dict."""

import json
import os
from datetime import datetime


def generate(report: dict, path: str) -> str:
    """Write a standalone HTML file and return its path."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    summary = report["summary"]
    categories = report["categories"]
    generated_at = report.get("generated_at", datetime.now().isoformat())

    # Status badge colour
    def badge(status: str) -> str:
        colour = {"PASS": "#22c55e", "FAIL": "#ef4444", "ERROR": "#f97316", "SKIP": "#94a3b8"}.get(status, "#6b7280")
        return f'<span style="background:{colour};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600">{status}</span>'

    # Build test rows HTML
    all_rows_html = ""
    for cat, cat_data in categories.items():
        all_rows_html += f"""
        <tr style="background:#1e293b;">
          <td colspan="4" style="padding:8px 12px;font-weight:700;color:#94a3b8;font-size:12px;letter-spacing:.5px;text-transform:uppercase">
            {cat.upper()} &nbsp; ({cat_data['passed']}/{cat_data['total']} passed)
          </td>
        </tr>"""
        for t in cat_data["tests"]:
            err_html = ""
            if t["error"]:
                tb = "\n".join(t["error"].get("traceback") or [])
                err_html = f"""
                <details style="margin-top:4px">
                  <summary style="cursor:pointer;color:#f97316;font-size:11px">▶ {t['error']['type']}: {t['error']['message'][:120]}</summary>
                  <pre style="margin:6px 0 0;font-size:10px;color:#cbd5e1;white-space:pre-wrap">{tb}</pre>
                </details>"""
            all_rows_html += f"""
        <tr style="border-bottom:1px solid #334155">
          <td style="padding:6px 12px;font-size:12px;color:#64748b">{t['id'].split('.')[-1]}</td>
          <td style="padding:6px 12px">
            <div style="color:#e2e8f0;font-size:13px">{t['name']}</div>
            <div style="color:#64748b;font-size:11px">{t['description']}</div>
            {err_html}
          </td>
          <td style="padding:6px 12px;text-align:right;color:#94a3b8;font-size:12px">{t['duration_ms']} ms</td>
          <td style="padding:6px 12px">{badge(t['status'])}</td>
        </tr>"""

    pass_rate = summary.get("pass_rate", "N/A")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Prisma ERP Test Report</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #0f172a; color: #e2e8f0; padding: 24px; }}
  h1 {{ font-size: 22px; font-weight: 700; }}
  .card {{ background: #1e293b; border-radius: 8px; padding: 20px; margin-bottom: 16px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  details summary::-webkit-details-marker {{ display: none; }}
</style>
</head>
<body>

<div class="card" style="display:flex;justify-content:space-between;align-items:center">
  <div>
    <h1>🧪 Prisma ERP Test Report</h1>
    <p style="color:#64748b;font-size:13px;margin-top:4px">Generated {generated_at}</p>
  </div>
  <div style="text-align:right">
    <div style="font-size:32px;font-weight:800;color:{'#22c55e' if summary['failed']+summary['errored']==0 else '#ef4444'}">{pass_rate}</div>
    <div style="color:#64748b;font-size:12px">pass rate</div>
  </div>
</div>

<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px">
  <div class="card" style="text-align:center">
    <div style="font-size:28px;font-weight:700;color:#e2e8f0">{summary['total']}</div>
    <div style="color:#64748b;font-size:12px">Total</div>
  </div>
  <div class="card" style="text-align:center">
    <div style="font-size:28px;font-weight:700;color:#22c55e">{summary['passed']}</div>
    <div style="color:#64748b;font-size:12px">Passed</div>
  </div>
  <div class="card" style="text-align:center">
    <div style="font-size:28px;font-weight:700;color:#ef4444">{summary['failed']}</div>
    <div style="color:#64748b;font-size:12px">Failed</div>
  </div>
  <div class="card" style="text-align:center">
    <div style="font-size:28px;font-weight:700;color:#f97316">{summary['errored']}</div>
    <div style="color:#64748b;font-size:12px">Errors</div>
  </div>
</div>

<div class="card">
  <table>
    <thead>
      <tr style="border-bottom:2px solid #334155">
        <th style="padding:8px 12px;text-align:left;color:#64748b;font-size:11px;font-weight:600;text-transform:uppercase;width:200px">Test ID</th>
        <th style="padding:8px 12px;text-align:left;color:#64748b;font-size:11px;font-weight:600;text-transform:uppercase">Description</th>
        <th style="padding:8px 12px;text-align:right;color:#64748b;font-size:11px;font-weight:600;text-transform:uppercase;width:100px">Duration</th>
        <th style="padding:8px 12px;color:#64748b;font-size:11px;font-weight:600;text-transform:uppercase;width:80px">Status</th>
      </tr>
    </thead>
    <tbody>
      {all_rows_html}
    </tbody>
  </table>
</div>

<div style="margin-top:12px;color:#475569;font-size:12px;text-align:center">
  Prisma ERP Test Suite &mdash; {report.get('suite', '')}
</div>

<script>
  // Embed raw JSON for machine reading
  window.testReport = {json.dumps(report, default=str)};
</script>
</body>
</html>"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
