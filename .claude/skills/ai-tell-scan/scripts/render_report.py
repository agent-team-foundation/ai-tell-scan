#!/usr/bin/env python3
"""Render a validated hosted-trial ats-1 report as self-contained HTML."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True

from ats_core import load_json, validate_final_report, write_text  # noqa: E402


REPORT_BASE = "https://report.first-tree.ai"
SOURCE_REPO = "https://github.com/agent-team-foundation/ai-tell-scan"
REPOSITORY_RE = re.compile(
    r"^https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)$"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a completed hosted-trial ats-1 report."
    )
    parser.add_argument("report", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _slug(value: str, limit: int) -> str:
    normalized = re.sub(r"[^a-z0-9._-]+", "-", value.lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-._")
    if not normalized:
        raise ValueError("Repository owner or name cannot form a report key.")
    return normalized[:limit].rstrip("-._")


def report_key(report: dict[str, object]) -> str:
    repository = report.get("repository")
    generated_at = report.get("generatedAt")
    if not isinstance(repository, dict) or not isinstance(
        repository.get("source"), str
    ):
        raise ValueError("Hosted rendering requires repository.source.")
    match = REPOSITORY_RE.fullmatch(repository["source"])
    if not match:
        raise ValueError(
            "Hosted rendering requires an exact https://github.com/<owner>/<repo> source."
        )
    if not isinstance(generated_at, str):
        raise ValueError("Hosted rendering requires generatedAt.")
    try:
        parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("generatedAt is not an ISO-8601 timestamp.") from error
    if parsed.tzinfo is None:
        raise ValueError("generatedAt must include a timezone.")

    stable = json.loads(json.dumps(report))
    stable.pop("generatedAt", None)
    canonical = json.dumps(
        stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()[:8]
    owner = _slug(match.group("owner"), 39)
    repo = _slug(match.group("repo"), 50)
    return f"{owner}-{repo}-{parsed.strftime('%Y%m%d')}-{digest}"


def _evidence_items(tell: dict[str, object]) -> str:
    evidence = tell.get("evidence")
    if not isinstance(evidence, list):
        return ""
    items: list[str] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        location = f"{item.get('file', '')}:{item.get('line', '')}"
        items.append(
            "<li>"
            f"<code>{_escape(location)}</code>"
            f"<span>{_escape(item.get('detail', ''))}</span>"
            f"<pre>{_escape(item.get('excerpt', ''))}</pre>"
            "</li>"
        )
    return "".join(items)


def _finding_cards(report: dict[str, object]) -> str:
    tells = report.get("tells")
    if not isinstance(tells, list) or not tells:
        return (
            '<section class="clean" aria-labelledby="clean-title">'
            '<p class="section-label">Final result</p>'
            '<h2 id="clean-title">No context-confirmed tells.</h2>'
            '<p>No bundled composite rule crossed the final reporting threshold. '
            "This is not an authorship verdict or a general design-quality score.</p>"
            "</section>"
        )
    cards: list[str] = []
    for index, value in enumerate(tells, start=1):
        if not isinstance(value, dict):
            continue
        location = f"{value.get('file', '')}:{value.get('line', '')}"
        cards.append(
            '<article class="finding">'
            '<header class="finding-head">'
            f'<span class="rank">{index:02d}</span>'
            '<div>'
            f'<p class="rule">{_escape(value.get("ruleId", ""))}</p>'
            f'<h2>{_escape(value.get("title", ""))}</h2>'
            f'<code class="location">{_escape(location)}</code>'
            "</div></header>"
            '<div class="finding-grid">'
            '<section><h3>Why it can lower trust</h3>'
            f'<p>{_escape(value.get("whyItHurtsTrust", ""))}</p></section>'
            '<section><h3>Context decision</h3>'
            f'<p>{_escape(value.get("reviewRationale", ""))}</p></section>'
            '<section class="fix"><h3>Smallest credible correction</h3>'
            f'<p>{_escape(value.get("minimalFix", ""))}</p></section>'
            "</div>"
            '<details><summary>Source evidence</summary>'
            f'<ol class="evidence">{_evidence_items(value)}</ol>'
            "</details>"
            "</article>"
        )
    return "".join(cards)


def render(report: dict[str, object], key: str) -> str:
    repository = report["repository"]
    target = report["target"]
    scan_result = report["scan"]
    summary = report["summary"]
    limitations = report["limitations"]
    source_url = str(repository["source"])
    repo_label = source_url.removeprefix("https://github.com/")
    frameworks = " / ".join(str(item) for item in target["frameworks"]) or "n/a"
    limitation_items = "".join(
        f"<li>{_escape(item)}</li>" for item in limitations
    )
    machine_url = f"{REPORT_BASE}/{key}.json"
    tell_count = int(summary["reportedCount"])
    title = f"AI Tell Scan — {repo_label}"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'">
  <title>{_escape(title)}</title>
  <style>
    :root {{ color-scheme: dark; --bg:#0a0a08; --paper:#ece8dc; --muted:#9d9a91; --line:#34332e; --accent:#ff603a; --acid:#d9ff43; }}
    * {{ box-sizing:border-box; }}
    html {{ background:var(--bg); }}
    body {{ margin:0; background:var(--bg); color:var(--paper); font:16px/1.6 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    a {{ color:inherit; }}
    code,pre,.mono,.section-label,.rule,.rank {{ font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }}
    .wrap {{ width:min(1120px,calc(100% - 40px)); margin:0 auto; }}
    .mast {{ padding:72px 0 64px; border-bottom:1px solid var(--line); }}
    .brand {{ display:flex; justify-content:space-between; gap:20px; color:var(--muted); font:12px/1.4 ui-monospace,monospace; letter-spacing:.08em; text-transform:uppercase; }}
    h1 {{ max-width:900px; margin:64px 0 18px; font-size:clamp(48px,8vw,104px); line-height:.92; letter-spacing:-.065em; font-weight:560; }}
    h1 em {{ color:var(--accent); font-style:normal; }}
    .lede {{ max-width:760px; margin:0; color:#bbb7ad; font-size:19px; }}
    .facts {{ display:grid; grid-template-columns:repeat(4,1fr); margin-top:52px; border-top:1px solid var(--line); border-left:1px solid var(--line); }}
    .facts div {{ min-height:118px; padding:18px; border-right:1px solid var(--line); border-bottom:1px solid var(--line); }}
    .facts dt {{ color:var(--muted); font:11px/1.3 ui-monospace,monospace; text-transform:uppercase; }}
    .facts dd {{ margin:22px 0 0; font-size:22px; letter-spacing:-.03em; overflow-wrap:anywhere; }}
    main {{ padding:80px 0 120px; }}
    .finding {{ margin:0 0 38px; border:1px solid var(--line); background:#10100d; }}
    .finding-head {{ display:grid; grid-template-columns:72px 1fr; gap:24px; padding:28px; border-bottom:1px solid var(--line); }}
    .rank {{ color:var(--acid); font-size:14px; }}
    .rule,.section-label {{ margin:0 0 10px; color:var(--accent); font-size:11px; letter-spacing:.09em; text-transform:uppercase; }}
    h2 {{ margin:0; font-size:clamp(30px,5vw,56px); line-height:1.02; letter-spacing:-.045em; }}
    .location {{ display:inline-block; margin-top:18px; color:#c9c5ba; font-size:12px; overflow-wrap:anywhere; }}
    .finding-grid {{ display:grid; grid-template-columns:1fr 1fr; }}
    .finding-grid section {{ min-height:190px; padding:28px; border-right:1px solid var(--line); border-bottom:1px solid var(--line); }}
    .finding-grid section:nth-child(2) {{ border-right:0; }}
    .finding-grid .fix {{ grid-column:1/-1; min-height:0; border-right:0; }}
    h3 {{ margin:0 0 12px; color:var(--muted); font:11px/1.3 ui-monospace,monospace; text-transform:uppercase; letter-spacing:.08em; }}
    p {{ margin:0; }}
    details {{ padding:22px 28px 28px; }}
    summary {{ cursor:pointer; color:#ccc8bd; font-size:14px; }}
    .evidence {{ display:grid; gap:14px; margin:22px 0 0; padding:0; list-style:none; }}
    .evidence li {{ padding:16px; border:1px solid #2a2925; background:#0b0b09; }}
    .evidence code {{ display:block; color:var(--acid); font-size:11px; overflow-wrap:anywhere; }}
    .evidence span {{ display:block; margin-top:7px; color:#c0bcb2; }}
    .evidence pre {{ margin:10px 0 0; padding:10px; overflow:auto; color:#929087; white-space:pre-wrap; background:#070706; }}
    .clean {{ padding:52px; border:1px solid var(--line); background:#10100d; }}
    .clean p:last-child {{ max-width:720px; margin-top:18px; color:#aaa69d; }}
    .limitations {{ margin-top:72px; padding-top:38px; border-top:1px solid var(--line); }}
    .limitations h2 {{ font-size:34px; }}
    .limitations ul {{ max-width:850px; padding-left:20px; color:#aaa69d; }}
    .links {{ display:flex; flex-wrap:wrap; gap:12px; margin-top:30px; }}
    .links a {{ padding:10px 13px; border:1px solid var(--line); text-decoration:none; font-size:13px; }}
    footer {{ padding:28px 0; border-top:1px solid var(--line); color:var(--muted); font-size:12px; }}
    @media (max-width:760px) {{ .facts {{ grid-template-columns:1fr 1fr; }} .finding-head {{ grid-template-columns:42px 1fr; padding:20px; }} .finding-grid {{ grid-template-columns:1fr; }} .finding-grid section,.finding-grid section:nth-child(2) {{ border-right:0; }} .finding-grid .fix {{ grid-column:auto; }} .clean {{ padding:28px; }} }}
    @media print {{ :root {{ color-scheme:light; --bg:#fff; --paper:#111; --muted:#555; --line:#bbb; }} body,.finding,.clean {{ background:#fff; }} .links {{ display:none; }} details {{ display:block; }} }}
  </style>
</head>
<body>
  <header class="mast">
    <div class="wrap">
      <div class="brand"><span>AI Tell Scan / ATS-1</span><span>read-only source review</span></div>
      <h1>{_escape(repo_label)}<br><em>{tell_count} confirmed tell{'' if tell_count == 1 else 's'}.</em></h1>
      <p class="lede">Composite UI defaults, reviewed in source context. This report describes visible implementation evidence; it does not identify who or what authored the code.</p>
      <dl class="facts">
        <div><dt>Status</dt><dd>{_escape(scan_result['status'])}</dd></div>
        <div><dt>Files examined</dt><dd>{_escape(scan_result['filesExamined'])}</dd></div>
        <div><dt>UI files</dt><dd>{_escape(scan_result['uiFilesExamined'])}</dd></div>
        <div><dt>Framework</dt><dd>{_escape(frameworks)}</dd></div>
      </dl>
    </div>
  </header>
  <main class="wrap">
    {_finding_cards(report)}
    <section class="limitations">
      <p class="section-label">Interpretation boundary</p>
      <h2>What this result does not prove</h2>
      <ul>{limitation_items}</ul>
      <div class="links">
        <a href="{_escape(machine_url)}">Machine-readable ats-1 JSON</a>
        <a href="{_escape(source_url)}" rel="noreferrer">Scanned repository</a>
        <a href="{SOURCE_REPO}" rel="noreferrer">Scanner source</a>
      </div>
    </section>
  </main>
  <footer><div class="wrap">Generated {_escape(report['generatedAt'])} · AI Tell Scan by First Tree · report key {_escape(key)}</div></footer>
</body>
</html>
"""


def main() -> int:
    args = parse_args()
    try:
        report = load_json(args.report)
        validate_final_report(report)
        key = report_key(report)
        output = args.out_dir.expanduser().resolve() / f"{key}.html"
        write_text(render(report, key), output)
    except ValueError as error:
        print(f"ai-tell-scan: {error}", file=sys.stderr)
        return 2
    print(key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
