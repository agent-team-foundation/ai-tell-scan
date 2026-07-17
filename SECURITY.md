# Security policy

Please report a vulnerability through GitHub's private security-advisory flow
for this repository. Do not open a public issue for secrets, path traversal,
shell injection, unsafe target-repository handling, or hosted-report publishing
defects.

The scanner treats target content as untrusted data, does not execute target
commands, and writes only to new artifact paths outside the target repository.
Hosted publishing is limited to repositories whose public visibility is
verified immediately before rendering and upload.
