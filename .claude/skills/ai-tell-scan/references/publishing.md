# Hosted report publishing

Use this flow only for a public GitHub repository in the hosted
`ai-tell-scan` landing campaign. Ordinary local and private scans keep their
artifacts local.

## Fixed contracts

- Report base: `https://report.first-tree.ai`
- Bucket: `s3://first-tree-report`
- HTML object: `<report_key>.html`, retained for 7 days by bucket lifecycle
- Machine handoff: `<report_key>.json`, retained for 30 days by bucket lifecycle
- Cloud fix handoff:
  `https://cloud.first-tree.ai/quickstart?campaign=ai-tell-scan&repo=<encoded-public-repo-url>&action=fix&report=<report_key>`

`scripts/publish_report.py` is the only hosted publication entry point. It uses
`scripts/render_report.py` as the only implementation of report rendering and
report-key derivation. The key is
`<owner>-<repo>-<YYYYMMDD>-<8-char-hash>`. The date comes from `generatedAt`;
the hash is SHA-256 over recursively key-sorted `ats-1` JSON excluding
`generatedAt`, so sub-day clock differences do not change content identity.

Never derive the key in shell or use an upload command's printed URL as the
public report base.

## Eligibility and render gate

All of these must hold before rendering:

1. `repository.source` exactly matches the normalized public repository URL
   requested by the trial and has the
   `https://github.com/<owner>/<repo>` shape.
2. `gh repo view` reports that exact repository as `PUBLIC`. A missing CLI,
   authentication error, access error, lookup failure, or any other visibility
   stops hosted rendering and publishing. Fail closed.
3. `ats-1.json` passes `scripts/validate_report.py` and is completed.
4. `generatedAt` is timezone-aware and the scan artifacts are outside the
   target repository.
5. The output directory is fresh; the renderer refuses to overwrite any path.

Resolve `<skill-dir>` from this skill's `SKILL.md`, then publish through the
checked orchestrator. Never resolve an executable relative to the untrusted
target repository:

```bash
OUT=<fresh-scan-output-directory>
REPORT="$OUT/report.ats-1.json"

python3 -B <skill-dir>/scripts/publish_report.py "$REPORT" --out-dir "$OUT"
```

The command validates the executable report contract, checks the exact GitHub
repository identity and `PUBLIC` visibility, renders create-only HTML, uploads
machine JSON first, uploads HTML second, and prints the hosted URL only after
both uploads succeed. A missing CLI, malformed response, identity mismatch,
private repository, validation failure, existing output path, or failed upload
exits nonzero without printing a URL.

The HTML is self-contained, script-free, escaped at every report-controlled
sink, printable, and linked only to the matching machine JSON plus explicit
repository/product sources.

## JSON-first gated upload

Credentials come from the hosted runtime. The publisher never hardcodes a key,
secret, region, or profile. When `/home/ubuntu/.aws/credentials` exists, it
passes that file and the matching config path to the AWS CLI explicitly.

The publisher uploads JSON first and HTML second. Do not bypass it, reorder
uploads, or retry with a different key. Only when both commands exit zero does
it form and print the public URL as:

`https://report.first-tree.ai/<report_key>.html`

If either upload fails, state that hosted publishing failed and present the
local artifacts. Never print a speculative hosted URL or promise a report key
whose JSON object is missing.

## Hosted-trial closing choice

The trial agent remains read-only: it reports and hands off; it never applies a
finding to the scanned repository.

After a successful publish with at least one reported tell, raise one tracked
First Tree `chat ask`: ask whether the user wants to build their own team to fix
the context-confirmed Top 3, or stop after the report. The fix choice uses the
fixed Cloud handoff above with the URL-encoded repository and exact report key.
The receiving team must verify both identities before editing: normalize the
report's `repository.source` against the handoff repository, then run the
read-only scanner on the current checkout and require its
`target.sourceDigest` to equal the report's digest. A mismatch means the report
is stale; make no changes and request a fresh scan.

If publishing failed, do not attach a report parameter. Explain that the hosted
handoff is unavailable and offer a re-run. If the final report contains zero
reported tells, close with the limitation-qualified result and do not create an
empty fix workflow.

Do not put the Cloud conversion URL in the HTML report. Do not file issues,
edit source, apply fixes, or create a team without the separate explicit choice
and the normal First Tree workflow gates.
