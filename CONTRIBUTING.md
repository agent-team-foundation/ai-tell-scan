# Contributing

[English](CONTRIBUTING.md) | [简体中文](CONTRIBUTING.zh-CN.md)

AI Tell Scan is intentionally precision-first. Before changing a rule, read the
signal and gold-set references in `.claude/skills/ai-tell-scan/references/`.

## Choose the work first

- Search existing issues and pull requests before starting.
- Use an issue for a new signal family, public contract change, or behavior that
  affects hosted trials. Small test, documentation, and unambiguous bug fixes may
  go directly to a pull request.
- Do not paste private repositories, proprietary screenshots, credentials, or
  unredacted hosted reports into an issue.

Use a short branch name such as `fix/bounded-aurora-scan` or
`docs/local-development`. Keep commits focused and write imperative subjects,
for example `fix: bound aurora source windows`.

## Rule and contract changes

Every rule change must:

1. add or update at least one positive and one hard-negative corpus case;
2. keep candidate and context-confirmed precision at or above 0.90;
3. preserve valid file/line evidence and framework/status classification;
4. include a context-review rejection path when the candidate can be intentional;
5. pass the scanner tests, renderer tests, evaluator, and skill validator.

Schema, publishing, checkout, digest, and hosted-handoff changes need focused
negative tests and an independent security/contract review. Keep target
repository data out of commits unless it is fictional, de-identified, licensed
for this use, and explicitly part of the controlled corpus.

## Pull requests

Run the complete commands in [DEVELOPMENT.md](DEVELOPMENT.md#release-checks)
before opening a pull request. In the description:

- state the user-visible outcome and the boundary that remains unchanged;
- name every new or changed fixture;
- report candidate and confirmed precision, including rejection counts;
- include the exact commands run and any limitation that was not exercised;
- request an independent review for security, resource-bound, or public-contract
  changes.

Maintainers may ask for a smaller diff, a hard-negative case, or a fresh
evaluation before reviewing style. Approval is based on evidence and contract
fit, not only green tests. A maintainer will close work that infers authorship,
executes target code, weakens the read-only boundary, or hides evaluation
limitations.

By participating, you agree to [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Report
suspected vulnerabilities through [SECURITY.md](SECURITY.md), never a public
issue.
