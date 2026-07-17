# Local development

[English](DEVELOPMENT.md) | [简体中文](DEVELOPMENT.zh-CN.md)

This is the reproducible contributor workflow for AI Tell Scan. The repository
has no runtime package dependency: scanner, review, renderer, evaluator, and
validators use Python's standard library.

## Prerequisites

- Python 3.11 or 3.12
- Git
- Optional: `uvx` for Ruff without a persistent install
- Optional: authenticated GitHub CLI (`gh`) for bounded public-repository
  materialization and hosted visibility tests
- Optional: AWS CLI only for maintainers testing the hosted publisher in an
  authorized runtime

## Bootstrap

```bash
git clone https://github.com/agent-team-foundation/ai-tell-scan.git
cd ai-tell-scan
python3 --version
python3 -B scripts/validate_skill.py
```

No `pip install`, package lock, or build step is required. Do not install or run
dependencies from a target repository during a scan.

## Run locally

Scan a React or Next.js checkout and write artifacts outside that checkout:

```bash
OUT="$(mktemp -d)"
python3 -B bin/ats-scan.py /path/to/react-app \
  --target-id owner/repository \
  --output "$OUT/candidates.ats-1.json" \
  --review-template "$OUT/review.ats-review-1.json"
```

Follow the finalize commands in [README.md](README.md#run-it-locally). The
scanner refuses to overwrite output or write inside the target.

## Test and lint

```bash
python3 -B .claude/skills/ai-tell-scan/scripts/test_ats.py -v
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
python3 -B .claude/skills/ai-tell-scan/scripts/evaluate.py \
  --output /tmp/ats-eval-1.json
python3 -B scripts/validate_skill.py
python3 -m compileall -q .claude/skills/ai-tell-scan bin scripts tests
uvx ruff check .
```

There is no separate type-check or automatic-format command. Preserve the
existing Python style; Ruff lint, Python compile validation, executable report
validation, and the public JSON Schema cover the shipped contracts.

## Architecture map

- `.claude/skills/ai-tell-scan/`: canonical skill, deterministic engine,
  agent-review workflow, references, and controlled corpus
- `bin/ats-scan.py`: repository-local scanner entry point
- `schemas/ats-1.schema.json`: public report contract
- `examples/`: checked machine and script-free HTML output
- `tests/`: hosted materialization, renderer, publisher, schema, and repository
  contract tests

The deterministic pass emits candidates. Agent context review confirms or
rejects them against the same source digest. Finalization reports at most three
confirmed findings. Hosted publication is a separate, fail-closed step.

## Environment and credentials

Ordinary development requires no environment variables. `gh auth login` or an
existing `GH_TOKEN` may authenticate GitHub CLI when testing public checkout.
Hosted publication reads AWS credentials from the authorized runtime; never put
credentials in repository files, fixtures, command examples, or test output.

## Troubleshooting

- **Source/index/rule limit exceeded:** reduce the scan root or add a bounded
  prefilter with a regression that still detects split component composition.
  Do not simply raise a limit.
- **No React or Next.js signal:** ensure the selected root contains the owning
  `package.json`, not only a nested UI file.
- **Output already exists or is inside the target:** choose a fresh directory
  outside the scanned checkout.
- **Public checkout or visibility verification fails:** confirm `gh auth status`
  and the exact `https://github.com/<owner>/<repo>` URL. The hosted path fails
  closed when identity cannot be verified.
- **Evaluation changes unexpectedly:** inspect candidate, confirmed, rejected,
  framework, status, and evidence errors in the generated evaluation JSON.

## Release checks

Before asking for approval, run every command in **Test and lint**, verify the
checked example is reproducible, scan a representative public repository
without executing target code, and record the exact commit reviewed. Rule or
security-boundary changes require an independent review. `main` remains
protected by the required Python 3.11 and 3.12 checks plus a non-author approval.
