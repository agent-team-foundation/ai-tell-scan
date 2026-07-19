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


def _priority_rows(report: dict[str, object], empty_message: str) -> str:
    tells = report.get("tells")
    if not isinstance(tells, list) or not tells:
        return (
            '<div class="priority-empty" role="row"><span role="cell" '
            f'aria-colspan="5">{_escape(empty_message)}</span></div>'
        )
    rows: list[str] = []
    for index, value in enumerate(tells, start=1):
        if not isinstance(value, dict):
            continue
        location = f"{value.get('file', '')}:{value.get('line', '')}"
        rows.append(
            '<div class="priority-row" role="row">'
            f'<span class="priority-index" role="cell">{index:02d}</span>'
            f'<strong role="cell">{_escape(value.get("title", ""))}</strong>'
            f'<code role="cell">{_escape(value.get("ruleId", ""))}</code>'
            '<span role="cell"><b class="confirmed-chip">Confirmed</b></span>'
            f'<span role="cell">{_escape(location)}</span>'
            "</div>"
        )
    return "".join(rows)


def _finding_chapters(
    report: dict[str, object], empty_title: str, empty_message: str
) -> str:
    tells = report.get("tells")
    if not isinstance(tells, list) or not tells:
        return (
            '<section class="clean" aria-labelledby="clean-title">'
            '<p class="section-label">Final result</p>'
            f'<h2 id="clean-title">{_escape(empty_title)}</h2>'
            f'<p>{_escape(empty_message)} This is not an authorship verdict or '
            "a general design-quality score.</p>"
            "</section>"
        )
    chapters: list[str] = []
    for index, value in enumerate(tells, start=1):
        if not isinstance(value, dict):
            continue
        location = f"{value.get('file', '')}:{value.get('line', '')}"
        chapters.append(
            '<article class="finding">'
            '<header class="finding-head">'
            f'<span class="rank">{index:02d}</span>'
            '<div>'
            f'<p class="rule">{_escape(value.get("ruleId", ""))}</p>'
            f'<h3>{_escape(value.get("title", ""))}</h3>'
            f'<code class="location">{_escape(location)}</code>'
            "</div><span class=\"confirmed-chip\">Confirmed</span></header>"
            '<div class="finding-grid">'
            '<section><h4>Evidence</h4>'
            f'<ol class="evidence">{_evidence_items(value)}</ol></section>'
            '<section><h4>Why it can lower trust</h4>'
            f'<p>{_escape(value.get("whyItHurtsTrust", ""))}</p></section>'
            '<section><h4>Context decision</h4>'
            f'<p>{_escape(value.get("reviewRationale", ""))}</p></section>'
            '<section class="fix"><h4>Smallest credible correction</h4>'
            f'<p>{_escape(value.get("minimalFix", ""))}</p></section>'
            "</div></article>"
        )
    return "".join(chapters)


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
    confirmed_count = int(summary["confirmedCount"])
    reported_count = int(summary["reportedCount"])
    suppressed_count = int(summary["suppressedConfirmedCount"])
    candidate_count = int(summary["candidateCount"])
    review_state = str(report["review"]["state"])
    context_reviewed = candidate_count > 0 and review_state == "complete"
    verdict = (
        "No context-confirmed tells"
        if confirmed_count == 0
        else "Visible defaults confirmed"
    )
    result_class = "clean-result" if confirmed_count == 0 else "has-findings"
    count_label = (
        f"{confirmed_count} confirmed tell{'' if confirmed_count == 1 else 's'}"
    )
    if confirmed_count == 0:
        reporting_note = (
            "All candidates were rejected during source-context review."
            if context_reviewed
            else "No source-context review was required."
        )
    elif suppressed_count > 0:
        reporting_note = (
            f"Showing {reported_count} reported finding{'' if reported_count == 1 else 's'}"
            f" from {confirmed_count} confirmed."
        )
    else:
        reporting_note = (
            f"All {reported_count} confirmed finding{'' if reported_count == 1 else 's'} shown."
        )
    review_label = (
        "after source-context review"
        if context_reviewed
        else "after deterministic source scan"
    )
    lede = (
        "Composite UI defaults, reviewed in source context."
        if context_reviewed
        else "Composite UI defaults, checked by deterministic source rules."
    )
    if candidate_count == 0:
        empty_title = "No composite candidate reached review."
        empty_message = "No deterministic composite rule crossed the candidate threshold."
    else:
        empty_title = "No context-confirmed tells."
        empty_message = "Source-context review rejected every candidate."
    next_step = (
        '<aside class="cta"><div><strong>Review with First Tree</strong><p>Share '
        "the evidence with your team and turn confirmed tells into scoped fixes."
        '</p></div><a href="https://first-tree.ai" rel="noreferrer">Review with First Tree</a></aside>'
        if confirmed_count > 0
        else '<aside class="cta"><div><strong>Keep visible defaults intentional</strong><p>'
        "Re-run the evidence-first scan when the interface changes."
        f'</p></div><a href="{SOURCE_REPO}" rel="noreferrer">Open scanner source</a></aside>'
    )
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
    :root {{ color-scheme:dark; --bg:#080907; --surface:#0d0f0c; --paper:#f2f1eb; --muted:#989b92; --soft:#c9cbc3; --line:#292b27; --accent:#ff7138; --acid:#d9ff43; --focus:#f2f1eb; }}
    * {{ box-sizing:border-box; }}
    html {{ background:var(--bg); }}
    body {{ margin:0; background:var(--bg); color:var(--paper); font:16px/1.55 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; -webkit-font-smoothing:antialiased; }}
    a {{ color:inherit; text-underline-offset:.18em; }}
    a:focus-visible,summary:focus-visible {{ outline:2px solid var(--focus); outline-offset:4px; }}
    code,pre,.mono,.section-label,.rule,.rank,.priority-index {{ font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }}
    .skip-link {{ position:fixed; left:16px; top:-80px; z-index:10; padding:12px 16px; background:var(--paper); color:var(--bg); }}
    .skip-link:focus {{ top:16px; }}
    .wrap {{ width:min(1240px,calc(100% - 48px)); margin:0 auto; }}
    .mast {{ padding-top:18px; }}
    .brand {{ min-height:54px; display:flex; align-items:center; justify-content:space-between; gap:20px; padding:0 18px; border:1px solid var(--line); color:var(--muted); font:11px/1.4 ui-monospace,monospace; letter-spacing:.08em; text-transform:uppercase; }}
    .brand strong {{ color:var(--paper); font-size:13px; letter-spacing:-.02em; text-transform:none; }}
    .hero {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(360px,.82fr); gap:72px; align-items:start; padding:58px 0 48px; }}
    .section-label {{ margin:0 0 12px; color:var(--accent); font-size:11px; letter-spacing:.1em; text-transform:uppercase; }}
    h1 {{ max-width:720px; margin:0 0 28px; font:650 clamp(28px,4vw,54px)/1.02 ui-monospace,SFMono-Regular,Menlo,monospace; letter-spacing:-.055em; overflow-wrap:anywhere; }}
    .count-lockup {{ display:flex; align-items:baseline; gap:12px; margin-bottom:10px; }}
    .count-lockup strong {{ color:var(--accent); font-size:clamp(72px,10vw,120px); line-height:.82; letter-spacing:-.08em; }}
    .clean-result .count-lockup strong {{ color:var(--acid); }}
    .count-lockup span {{ font-size:clamp(22px,3.4vw,40px); font-weight:700; letter-spacing:-.045em; }}
    h2 {{ margin:0; font-size:clamp(26px,3vw,38px); line-height:1.05; letter-spacing:-.04em; }}
    h3 {{ margin:0; font-size:clamp(22px,3vw,34px); line-height:1.05; letter-spacing:-.035em; }}
    h4 {{ margin:0 0 12px; color:var(--muted); font:750 10px/1.4 ui-monospace,monospace; text-transform:uppercase; letter-spacing:.09em; }}
    .lede {{ max-width:720px; margin:18px 0 0; color:var(--soft); font-size:17px; }}
    .repo-panel {{ border:1px solid var(--line); }}
    .repo-card {{ padding:22px; border-bottom:1px solid var(--line); }}
    .repo-card span,.facts dt {{ color:var(--muted); font:10px/1.3 ui-monospace,monospace; letter-spacing:.09em; text-transform:uppercase; }}
    .repo-card strong {{ display:block; margin:12px 0 5px; font:650 18px/1.3 ui-monospace,monospace; overflow-wrap:anywhere; }}
    .repo-card small {{ color:var(--muted); }}
    .facts {{ display:grid; grid-template-columns:1fr 1fr; margin:0; }}
    .facts div {{ min-height:98px; padding:18px 22px; border-bottom:1px solid var(--line); }}
    .facts div:nth-child(odd) {{ border-right:1px solid var(--line); }}
    .facts div:nth-last-child(-n+2) {{ border-bottom:0; }}
    .facts dd {{ margin:14px 0 0; font-size:18px; letter-spacing:-.03em; overflow-wrap:anywhere; }}
    .action-rail {{ display:grid; grid-template-columns:repeat(3,1fr); margin-bottom:62px; border-top:1px solid var(--line); border-bottom:1px solid var(--line); }}
    .action-rail a {{ padding:16px; text-align:center; text-decoration:none; font-size:14px; }}
    .action-rail a + a {{ border-left:1px solid var(--line); }}
    .action-rail a.primary {{ color:var(--acid); }}
    main {{ padding:0 0 110px; }}
    .narrative {{ max-width:780px; margin-bottom:68px; }}
    .narrative p {{ margin-top:16px; color:var(--soft); }}
    .boundary-note {{ padding:18px 0 0; border-top:1px solid var(--line); color:var(--muted)!important; font-size:13px; }}
    .section {{ margin-bottom:76px; }}
    .section-head {{ display:flex; justify-content:space-between; align-items:end; gap:28px; margin-bottom:24px; padding-bottom:18px; border-bottom:1px solid var(--line); }}
    .section-head p {{ max-width:560px; color:var(--muted); }}
    .priority-table {{ border-bottom:1px solid var(--line); }}
    .priority-head,.priority-row {{ display:grid; grid-template-columns:56px 1.3fr 1fr 120px .9fr; gap:18px; align-items:center; padding:15px 0; border-top:1px solid var(--line); }}
    .priority-head {{ color:var(--muted); font:10px/1.3 ui-monospace,monospace; letter-spacing:.08em; text-transform:uppercase; }}
    .priority-row {{ color:var(--soft); font-size:13px; }}
    .priority-row strong {{ color:var(--paper); font-size:15px; }}
    .priority-row>*,.finding-head>*,.finding-grid>*,.repo-card,.facts>* {{ min-width:0; overflow-wrap:anywhere; }}
    .priority-index {{ color:var(--accent); font-size:24px; font-weight:800; }}
    .confirmed-chip {{ display:inline-flex; border:1px solid var(--accent); border-radius:999px; padding:5px 9px; color:var(--accent); font:800 10px/1 ui-monospace,monospace; letter-spacing:.08em; text-transform:uppercase; }}
    .priority-empty {{ padding:28px 0; border-top:1px solid var(--line); color:var(--soft); }}
    .finding {{ border-bottom:1px solid var(--line); }}
    .finding-head {{ display:grid; grid-template-columns:52px 1fr auto; gap:18px; align-items:start; padding:24px 0; }}
    .rank {{ color:var(--accent); font-size:24px; font-weight:800; }}
    .rule {{ margin:0 0 8px; color:var(--accent); font-size:10px; letter-spacing:.09em; text-transform:uppercase; }}
    .location {{ display:inline-block; margin-top:12px; color:var(--muted); font-size:12px; overflow-wrap:anywhere; }}
    .finding-grid {{ display:grid; grid-template-columns:1.2fr .9fr .9fr 1fr; border-top:1px solid var(--line); }}
    .finding-grid section {{ min-width:0; padding:22px 20px 24px 0; }}
    .finding-grid section + section {{ padding-left:20px; border-left:1px solid var(--line); }}
    .finding-grid p {{ color:var(--soft); font-size:13px; }}
    .finding-grid .fix p {{ color:var(--acid); }}
    p {{ margin:0; }}
    .evidence {{ display:grid; gap:12px; margin:0; padding:0; list-style:none; }}
    .evidence li {{ min-width:0; }}
    .evidence code {{ display:block; color:var(--acid); font-size:11px; overflow-wrap:anywhere; }}
    .evidence span {{ display:block; margin-top:6px; color:var(--soft); font-size:12px; }}
    .evidence pre {{ margin:9px 0 0; padding:10px; overflow:auto; border:1px solid var(--line); color:var(--muted); font-size:11px; white-space:pre-wrap; background:#060705; }}
    .clean {{ padding:42px; border:1px solid var(--line); }}
    .clean p:last-child {{ max-width:720px; margin-top:18px; color:#aaa69d; }}
    .limitations {{ margin-top:72px; padding:28px; border:1px solid var(--line); }}
    .limitations h2 {{ font-size:28px; }}
    .limitations ul {{ max-width:850px; padding-left:20px; color:var(--soft); }}
    .cta {{ display:flex; justify-content:space-between; align-items:center; gap:24px; margin-top:64px; padding:24px 28px; border:1px solid #6f8522; }}
    .cta strong {{ display:block; color:var(--acid); font-size:18px; }}
    .cta p {{ margin-top:5px; color:var(--muted); font-size:13px; }}
    .cta a {{ flex:0 0 auto; padding:12px 18px; background:var(--acid); color:#111408; font-weight:800; text-decoration:none; }}
    footer {{ padding:28px 0; border-top:1px solid var(--line); color:var(--muted); font-size:12px; }}
    @media (max-width:900px) {{ .hero {{ grid-template-columns:1fr; gap:36px; }} .priority-head {{ position:absolute; width:1px; height:1px; margin:-1px; padding:0; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; border:0; }} .priority-row {{ grid-template-columns:48px 1fr auto; }} .priority-row>:nth-child(3),.priority-row>:nth-child(5) {{ grid-column:2/-1; }} .finding-grid {{ grid-template-columns:1fr 1fr; }} .finding-grid section:nth-child(3) {{ border-left:0; border-top:1px solid var(--line); }} .finding-grid section:nth-child(4) {{ border-top:1px solid var(--line); }} }}
    @media (max-width:680px) {{ .wrap {{ width:min(100% - 24px,1240px); }} .brand span {{ display:none; }} .action-rail {{ grid-template-columns:1fr; }} .action-rail a+a {{ border-left:0; border-top:1px solid var(--line); }} .section-head {{ display:block; }} .section-head>p {{ margin-top:12px; }} .priority-row {{ grid-template-columns:42px 1fr; }} .priority-row>:nth-child(4) {{ grid-column:2; }} .finding-head {{ grid-template-columns:42px 1fr; }} .finding-head>.confirmed-chip {{ grid-column:2; }} .finding-grid {{ grid-template-columns:1fr; }} .finding-grid section,.finding-grid section+section {{ padding:18px 0; border-left:0; border-top:1px solid var(--line); }} .clean {{ padding:26px; }} .cta {{ align-items:stretch; flex-direction:column; }} .cta a {{ text-align:center; }} }}
    @media (max-width:420px) {{ h1,h2,h3,a,code,strong,pre {{ overflow-wrap:anywhere; }} .facts {{ grid-template-columns:1fr; }} .facts div,.facts div:nth-child(odd) {{ border-right:0; border-bottom:1px solid var(--line); }} .facts div:last-child {{ border-bottom:0; }} }}
    @media print {{ :root {{ color-scheme:light; --bg:#fff; --surface:#fff; --paper:#111; --muted:#555; --soft:#333; --line:#bbb; --accent:#8f2f08; --acid:#3f5200; --focus:#111; }} body,.finding,.clean {{ background:#fff; }} .action-rail,.cta,.skip-link,footer {{ display:none; }} .narrative,.priority-row,.section-head,.finding-head,.evidence li,.limitations {{ break-inside:avoid; }} .section-head,.finding-head {{ break-after:avoid-page; }} }}
  </style>
</head>
<body>
  <a class="skip-link" href="#report">Skip to report</a>
  <header class="mast">
    <div class="wrap">
      <div class="brand"><strong>first-tree</strong><span>AI Tell Scan / evidence-first source review</span></div>
      <section class="hero {result_class}">
        <div>
          <p class="section-label">AI Tell Scan</p>
          <h1>{_escape(repo_label)}</h1>
          <div class="count-lockup"><strong>{confirmed_count}</strong><span>confirmed tell{'' if confirmed_count == 1 else 's'}</span></div>
          <h2>{_escape(verdict)}</h2>
          <p class="lede">{_escape(lede)} This report describes visible implementation evidence; it does not identify who or what authored the code.</p>
        </div>
        <div class="repo-panel">
          <div class="repo-card"><span>Repository</span><strong><a href="{_escape(source_url)}" rel="noreferrer">{_escape(repo_label)}</a></strong><small>{_escape(target['label'])} · {_escape(report['generatedAt'])}</small></div>
          <dl class="facts">
            <div><dt>Status</dt><dd>{_escape(scan_result['status'])}</dd></div>
            <div><dt>Framework</dt><dd>{_escape(frameworks)}</dd></div>
            <div><dt>Files examined</dt><dd>{_escape(scan_result['filesExamined'])}</dd></div>
            <div><dt>UI files</dt><dd>{_escape(scan_result['uiFilesExamined'])}</dd></div>
          </dl>
        </div>
      </section>
    </div>
  </header>
  <main id="report" class="wrap">
    <nav class="action-rail" aria-label="Report actions"><a href="{_escape(source_url)}" rel="noreferrer">Open scanned repository</a><a class="primary" href="#findings">Review evidence</a><a href="{_escape(machine_url)}" rel="noreferrer">Open machine JSON</a></nav>

    <section class="narrative" aria-labelledby="meaning-title">
      <p class="section-label">What this result means</p>
      <h2 id="meaning-title">{_escape(count_label)} {_escape(review_label)}.</h2>
      <p>{_escape(scan_result['reason'])}</p>
      <p>{_escape(reporting_note)}</p>
      <p class="boundary-note">This scan evaluates visible implementation combinations. It does not prove authorship, provenance, intent, or overall product quality.</p>
    </section>

    <section class="section" aria-labelledby="priority-title">
      <div class="section-head"><div><p class="section-label">Where the interface defaults show</p><h2 id="priority-title">Priority findings</h2></div><p>Only context-confirmed composite tells appear here; ambiguous hints stay excluded.</p></div>
      <div class="priority-table" role="table" aria-label="Priority findings"><div class="priority-head" role="row"><span role="columnheader">Priority</span><span role="columnheader">Finding</span><span role="columnheader">Rule</span><span role="columnheader">Status</span><span role="columnheader">Location</span></div>{_priority_rows(report, empty_message)}</div>
    </section>

    <section id="findings" class="section" aria-labelledby="findings-title">
      <div class="section-head"><div><p class="section-label">Confirmed tells · Evidence first</p><h2 id="findings-title">Read the evidence before the label</h2></div><p>Each chapter keeps the source evidence, trust impact, context decision, and smallest credible correction together.</p></div>
      {_finding_chapters(report, empty_title, empty_message)}
    </section>

    <section class="limitations">
      <p class="section-label">Interpretation boundary</p>
      <h2>What this result does not prove</h2>
      <ul>{limitation_items}</ul>
    </section>
    {next_step}
  </main>
  <footer><div class="wrap">first-tree · AI Tell Scan · report key {_escape(key)} · <a href="{SOURCE_REPO}" rel="noreferrer">scanner source</a></div></footer>
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
