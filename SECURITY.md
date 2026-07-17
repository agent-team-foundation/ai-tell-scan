# Security policy

Please report a vulnerability through GitHub's private security-advisory flow
for this repository. Do not open a public issue for secrets, path traversal,
shell injection, unsafe target-repository handling, or hosted-report publishing
defects.

The scanner treats target content as untrusted data, does not execute target
commands, and writes only to new artifact paths outside the target repository.
Hosted trials pin public GitHub metadata, cap archive and source resources,
materialize only eligible regular files, and verify every selected Git blob
digest without invoking target checkout filters or hooks. Hosted publishing is
limited to repositories whose public visibility and identity are verified
immediately before rendering and upload.
