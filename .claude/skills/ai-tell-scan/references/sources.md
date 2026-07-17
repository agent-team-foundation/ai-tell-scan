# Reference and license boundary

AI Tell Scan is implemented from the authorized task's product definition:
detect visible React/Next UI combinations, produce deterministic candidates,
require context review, prioritize precision, and never infer provenance.

## Hallmark

- Repository: https://github.com/Nutlope/hallmark
- Consulted commit: `aeb42fb354ff4efa36ab475773a082315a3af2ce`
- License observed: MIT (`LICENSE` present; GitHub license metadata `mit`)
- Consulted material: public skill/audit taxonomy at a category level, including
  visual, structural, motion, honest-copy, typography, and layout-safety review.

No Hallmark scanner code was used. AI Tell Scan's ten rule definitions,
thresholds, parser, report schema, review binding, corpus, and fixes were
written for this project.

## Kill AI Slop

- Repository: https://github.com/yetone/kill-ai-slop
- Consulted commit: `e2456514416e40f133432baf364a2353900267a7`
- License observed: none (`licenseInfo: null`; no root `LICENSE` at inspection)
- Consulted material: repository/license metadata and public high-level problem
  framing only, to establish the comparison and reuse boundary.

Because no license grants reuse, no source code, regex, rule prose, examples,
fix text, taxonomy text, or generated asset is used. The signal set and corpus
derive from the authorized task scope plus independently written source cases.
An exact example sequence noticed during review was removed rather than relying
on an unsupported provenance claim.

## Ongoing rule

Re-check upstream license state before any future reuse, but never retroactively
assume that a later license authorized material observed while unlicensed.
Record the exact commit and copied/adapted scope for every licensed source.
