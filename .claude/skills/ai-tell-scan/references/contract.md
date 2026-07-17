# `ats-1` result contract

The machine-readable companion is
[`schemas/ats-1.schema.json`](../../../../schemas/ats-1.schema.json).
The prose below defines behavioral semantics that JSON Schema cannot express.

## Status model

- `unsupported`: no React/Next signal; never attach a grade.
- `not-applicable`: React/Next is present, but no scannable UI source exists.
- `needs-review`: deterministic candidates exist and no tell is confirmed yet.
- `completed`: no candidates exist, or a digest-bound context review finished.

## Stable top-level fields

| Field | Meaning |
| --- | --- |
| `schemaVersion` | Always `ats-1`. |
| `tool` | Scanner name and semantic payload version. |
| `target` | Non-sensitive label, stable rescan `targetId`, detected frameworks, and source digest. |
| `repository` | Optional canonical public GitHub source for an eligible hosted trial. |
| `generatedAt` | Optional timezone-aware generation time paired with hosted metadata. |
| `scan` | Status, reason, coverage counts, and read-only assertion. |
| `summary` | Candidate, confirmed, rejected, reported, and suppressed counts. |
| `candidateSetDigest` | SHA-256 binding review decisions to exact candidates. |
| `review` | `pending`, `not-required`, or `complete` plus policy/reviewer. |
| `candidates` | Every deterministic candidate and final disposition. |
| `tells` | At most three strongest context-confirmed candidates. |
| `limitations` | Static-analysis boundaries that must accompany the result. |
| `rescan` | Optional resolved, persisted, and introduced tell groups. |

## Candidate fields

Every candidate contains a deterministic `candidateId`, rule id, title,
severity, confidence used only for ordering, primary `file` and `line`, trust
impact, minimal fix, and at least three evidence records. Confidence is rule
calibration; it is not an AI likelihood or product score.

Each evidence record contains `kind`, repository-relative `file`, one-based
`line`, a short detail, and a bounded source excerpt. The evaluator verifies
that primary locations resolve to real lines.

## Review contract

An `ats-review-1` object binds the candidate-set digest, full source digest,
stable target id, tool name and version, reviewer label, and exactly one
decision per candidate. The source digest includes package manifests used to
determine React/Next eligibility. `disposition` is `confirmed` or `rejected`;
the rationale must be context-specific. The finalizer rejects stale source or
candidate digests, missing/duplicate/unknown decisions, pending dispositions,
short rationales, candidate content altered after scanning, and a `--target`
whose current source no longer matches the candidate report.

## Ordering and truncation

Confirmed tells sort by calibrated rule confidence, rule id, file, then line.
Only the first three enter `tells`; additional confirmations remain visible in
`candidates` and increment `suppressedConfirmedCount`.

## Compatibility

Consumers must branch on `schemaVersion` and `scan.status`, ignore unknown
fields, preserve one-based lines, and avoid treating a clean result as a score.
Breaking field or semantic changes require a new schema version.

`repository` and `generatedAt` are both required for hosted rendering and must
be absent from ordinary private/local artifacts unless the caller supplied an
authoritative public URL. They do not participate in review binding; source and
candidate digests continue to bind the reviewed code and evidence.

Rescan comparison additionally requires a completed, internally consistent
baseline, the same `targetId`, and the same tool version. It compares every
confirmed baseline candidate, including confirmations suppressed from the
display-only Top 3. This prevents unrelated, tampered, or truncated reports
from manufacturing `resolved`, `persisted`, or `introduced` results.
