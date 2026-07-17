# Gold-set methodology

## Corpus

`../evals/gold-set.json` declares exactly 30 compact React/Next projects:

- 15 confirmed-positive projects, including five overlap projects;
- 13 hard-negative projects containing tempting primitives without the full
  composite or without sufficient context for confirmation;
- 2 React/Next packages with no shipped UI, which must return
  `not-applicable`.

Every project is fictional, de-identified, independently authored for this
Apache-2.0 repository, and contains no copied third-party code, product names,
or user data. The corpus is compact enough to audit in review and deterministic
enough to run without network access.

Three hard-negative projects deliberately cross a deterministic rule threshold
but must be rejected during context review: registered brand treatment,
dated/methodology-backed metrics, and motion in an interaction playground.
This prevents an always-confirm reviewer from passing the precision gate.

## Labels

`expectedCandidates` labels the deterministic `(project, ruleId, file)` output;
`confirmedCandidates` labels the result after page/component context review. A
confirmed label requires every documented primitive in one visible composition
and the rule's stated trust impact. A hard negative intentionally contains one
or more tempting primitives while withholding prominence, repetition, semantic
spread, grounding, or another required gate. Annotation notes are committed
beside every project entry.

Changes to a rule require both a positive and hard-negative review. Do not tune
only the positive fixture. Do not relabel a false positive merely to make the
metric pass; narrow the rule or document a genuine annotation error.

## Metrics

`scripts/evaluate.py` scores every emitted `(project, ruleId, file)` candidate;
an extra same-rule candidate in another file remains a false positive. It then
applies the source-, target-, tool-, and candidate-digest-bound
`evals/independent-review.json`, produced by an agent that was not shown the
gold manifest, and separately reports context-confirmed TP/FP/FN. Every primary
and supporting evidence path, line, and excerpt is revalidated against source.
The release gate requires both candidate and confirmed precision >= 0.90,
complete blinded decisions, at least three valid context rejections, no false
negatives, and no evidence/status/framework errors. It also verifies that an
always-confirm policy scores below 0.90. Recall is reported but cannot
compensate for a precision miss.

## Claim boundary

A perfect controlled-corpus result is a regression result, not proof of 100%
real-world accuracy. Report the corpus composition and limitations with the
metric. Use a separately identified real repository for a sample report; do
not add third-party repositories to a public shame list.
