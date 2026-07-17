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

`scripts/render_report.py` is the only implementation of report rendering and
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

Verify visibility before rendering, then capture the key from the renderer:

```bash
OUT=<fresh-scan-output-directory>
REPORT="$OUT/report.ats-1.json"

python3 -B scripts/validate_report.py "$REPORT"
REPO_URL="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["repository"]["source"])' "$REPORT")"

python3 -c 'import re,sys; raise SystemExit(0 if re.fullmatch(r"https://github[.]com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", sys.argv[1]) else 1)' "$REPO_URL" || {
  echo "Repository is not an exact eligible GitHub URL; not publishing." >&2
  exit 1
}

VISIBILITY="$(gh repo view "$REPO_URL" --json visibility --jq '.visibility' 2>/dev/null)" || {
  echo "Could not verify public repository visibility; not publishing." >&2
  exit 1
}
test "$VISIBILITY" = "PUBLIC" || {
  echo "Repository is not public; not publishing." >&2
  exit 1
}

KEY="$(python3 -B scripts/render_report.py "$REPORT" --out-dir "$OUT")"
test -n "$KEY"
test -f "$OUT/$KEY.html"
```

The exact URL shape check is only an initial guard. The GitHub visibility result is
the authoritative gate because ambient credentials can make a private
repository readable.

The HTML is self-contained, script-free, escaped at every report-controlled
sink, printable, and linked only to the matching machine JSON plus explicit
repository/product sources.

## JSON-first gated upload

Credentials come from the hosted runtime. Never hardcode a key, secret,
region, or profile. When the runtime credential files exist outside its
workspace-local home, point the AWS CLI at them explicitly:

```bash
if [ -f /home/ubuntu/.aws/credentials ]; then
  export AWS_SHARED_CREDENTIALS_FILE=/home/ubuntu/.aws/credentials
  export AWS_CONFIG_FILE=/home/ubuntu/.aws/config
fi

PUBLISHED=false
if aws s3 cp "$REPORT" "s3://first-tree-report/$KEY.json" \
  --content-type application/json --only-show-errors; then
  if aws s3 cp "$OUT/$KEY.html" "s3://first-tree-report/$KEY.html" \
    --content-type text/html --only-show-errors; then
    PUBLISHED=true
  fi
fi
```

Upload JSON first and HTML second. Do not reorder uploads or retry with a
different key. Only when both commands exit zero, form the public URL as:

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

If publishing failed, do not attach a report parameter. Explain that the hosted
handoff is unavailable and offer a re-run. If the final report contains zero
reported tells, close with the limitation-qualified result and do not create an
empty fix workflow.

Do not put the Cloud conversion URL in the HTML report. Do not file issues,
edit source, apply fixes, or create a team without the separate explicit choice
and the normal First Tree workflow gates.
