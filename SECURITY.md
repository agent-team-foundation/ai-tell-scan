# Security policy

[English](SECURITY.md) | [简体中文](SECURITY.zh-CN.md)

## Supported versions

Security fixes target the latest `main` commit and the latest tagged release,
when one exists. Earlier commits and copied skill directories are not supported;
reproduce against the current canonical repository before reporting.

## Report privately

Use GitHub's private vulnerability-reporting flow for this repository. If that
surface is unavailable, email `security@first-tree.ai` with the subject
`[AI Tell Scan security]`. Do not open a public issue, discussion, pull request,
or review for secrets, path traversal, shell injection, unsafe target handling,
resource exhaustion, or hosted-report publishing defects.

Include the affected commit, prerequisites, impact, minimal reproduction, and
whether any real repository or hosted report was exposed. Do not send secrets
or third-party source unless the maintainers explicitly arrange a protected
channel.

Maintainers aim to acknowledge a report within three calendar days. They will
validate impact privately, coordinate a fix or mitigation, and agree on public
disclosure after affected users have a reasonable update path. Acknowledgement
is not a promise that remediation will finish within three days.

## Security boundaries

The scanner treats target content as untrusted data, does not execute target
commands, and writes only to new artifact paths outside the target repository.
Hosted trials pin public GitHub metadata, cap archive and source resources,
materialize only eligible regular files, and verify every selected Git blob
digest without invoking target checkout filters or hooks. Hosted publishing is
limited to repositories whose public visibility and identity are verified
immediately before rendering and upload.
