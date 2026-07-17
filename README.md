# AI Tell Scan

Evidence-first source review for the compound UI defaults that can make a
React or Next.js product feel generic. AI Tell Scan returns at most three
context-confirmed findings with `file:line` evidence. It does not infer AI
authorship, generate an AI percentage, or rank repositories.

**Hosted scan:** [scan a public GitHub repository with First Tree](https://first-tree.ai/ai-tell-scan?utm_source=github&utm_medium=readme&utm_campaign=ai-tell-scan)

## What it detects

The deterministic pass looks for ten composite signal families, including
floating glass navigation, aurora-centered heroes, interchangeable icon-card
triptychs, decorative proof metrics, pill-role overload, and repeated generic
motion. A single color, radius, library, class, or keyword is never enough.

Every candidate then receives a source-bound context review. The reviewer must
confirm that the full composition is shipped and prominent, or reject it when
the match is dead code, a fixture, intentional brand language, or appropriate
for the product genre. Only the strongest three confirmations reach the final
report.

## Run it locally

Python 3.11+ is the only runtime dependency.

```bash
git clone https://github.com/agent-team-foundation/ai-tell-scan.git
cd ai-tell-scan

OUT="$(mktemp -d)"
python3 -B ./bin/ats-scan.py /path/to/react-app \
  --target-id your-org/your-app \
  --output "$OUT/candidates.ats-1.json" \
  --review-template "$OUT/review.ats-review-1.json"
```

Read every reported location and replace each pending decision in the review
file with `confirmed` or `rejected` plus a context-specific rationale. Then:

```bash
python3 -B ./.claude/skills/ai-tell-scan/scripts/finalize.py \
  "$OUT/candidates.ats-1.json" "$OUT/review.ats-review-1.json" \
  --target /path/to/react-app --output "$OUT/report.ats-1.json"

python3 -B ./.claude/skills/ai-tell-scan/scripts/validate_report.py \
  "$OUT/report.ats-1.json"
```

The scanner never writes into the target repository and refuses to overwrite
an existing artifact path. For a clean scan there is no review step; the
candidate report is already the completed, limitation-qualified result.

## Result contract

The published [`ats-1` JSON Schema](schemas/ats-1.schema.json) covers the scan
status, source digest, candidate set, review state, Top 3 findings, and rescan
comparison. A finalized finding contains:

- the composite rule and calibrated ordering confidence;
- a real repository-relative file and one-based line;
- at least three evidence records;
- the context-review rationale;
- the product trust impact and smallest credible correction.

Hosted public-repository trials additionally carry the canonical repository
URL and generation time. They render a self-contained, script-free HTML report
and publish the machine JSON before the HTML. A report URL is shown only when
both uploads succeed. The exact gates live in
[`references/publishing.md`](.claude/skills/ai-tell-scan/references/publishing.md).

## Precision gate

The checked `ats-gold-1` corpus contains 30 compact React/Next.js projects: 15
positive, 13 hard-negative, and 2 not-applicable. Current regression results:

| Layer | TP / FP / FN | Precision | Recall |
| --- | ---: | ---: | ---: |
| Deterministic candidates | 23 / 0 / 0 | 1.0000 | 1.0000 |
| Blinded context-confirmed | 20 / 0 / 0 | 1.0000 | 1.0000 |

The blinded review includes three real rejections; an always-confirm policy
scores 0.8696 and fails the 0.90 precision gate. This is a controlled regression
corpus, not evidence of population-wide accuracy. The full report is in
[`eval-report.md`](.claude/skills/ai-tell-scan/references/eval-report.md).

## Repository layout

```text
.claude/skills/ai-tell-scan/  canonical skill, scanner, evaluator, references
bin/                           local command entry point
schemas/                       public ats-1 contract
examples/                      checked real-repository output
tests/                         renderer and repository-contract tests
```

## Development

```bash
python3 -B .claude/skills/ai-tell-scan/scripts/test_ats.py -v
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
python3 -B .claude/skills/ai-tell-scan/scripts/evaluate.py \
  --output /tmp/ats-eval-1.json
python3 -B scripts/validate_skill.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for rule-change requirements. Licensed
under Apache-2.0.
