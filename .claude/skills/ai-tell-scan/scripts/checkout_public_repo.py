#!/usr/bin/env python3
"""Materialize bounded public GitHub source without executing target filters."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

sys.dont_write_bytecode = True

from ats_core import (  # noqa: E402
    HOSTED_REPOSITORY_RE,
    MAX_TOTAL_SOURCE_BYTES,
    SKIP_DIRECTORIES,
    SUPPORTED_EXTENSIONS,
    _is_skipped,
)
from publish_report import _verify_public_repository  # noqa: E402


MAX_FILES = 5_000
MAX_FILE_BYTES = 1_000_000
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_CONTENT_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 100_000


@dataclass(frozen=True)
class BlobEntry:
    oid: str
    size: int
    path: str


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as error:
        raise ValueError(f"Required command is unavailable: {command[0]}") from error


def _fetch_tree(source: str) -> tuple[str, list[BlobEntry]]:
    owner, repo = source.removeprefix("https://github.com/").split("/", 1)
    result = _run(
        ["gh", "api", f"repos/{owner}/{repo}/git/trees/HEAD?recursive=1"]
    )
    if result.returncode != 0 or not isinstance(result.stdout, str):
        raise ValueError("Could not inspect the public repository tree.")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("GitHub returned invalid repository tree metadata.") from error
    if not isinstance(payload, dict) or payload.get("truncated") is not False:
        raise ValueError("GitHub repository tree is incomplete; narrow the scan root.")
    head_oid = payload.get("sha")
    tree = payload.get("tree")
    if (
        not isinstance(head_oid, str)
        or re.fullmatch(r"[0-9a-f]{40}", head_oid) is None
        or not isinstance(tree, list)
    ):
        raise ValueError("GitHub returned invalid repository tree metadata.")

    entries: list[BlobEntry] = []
    for item in tree:
        if not isinstance(item, dict) or item.get("type") != "blob":
            continue
        if item.get("mode") not in {"100644", "100755"}:
            continue
        path = item.get("path")
        oid = item.get("sha")
        size = item.get("size")
        if (
            not isinstance(path, str)
            or not isinstance(oid, str)
            or re.fullmatch(r"[0-9a-f]{40}", oid) is None
            or type(size) is not int
            or size < 0
        ):
            raise ValueError("GitHub returned an invalid repository blob entry.")
        entries.append(BlobEntry(oid=oid, size=size, path=path))
    return head_oid, entries


def _eligible_path(value: str) -> bool:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        return False
    if any(part in SKIP_DIRECTORIES for part in path.parts[:-1]) or _is_skipped(value):
        return False
    return path.suffix.lower() in SUPPORTED_EXTENSIONS or path.name == "package.json"


def select_entries(entries: list[BlobEntry]) -> list[BlobEntry]:
    selected: list[BlobEntry] = []
    total_bytes = 0
    for entry in entries:
        if not _eligible_path(entry.path) or entry.size > MAX_FILE_BYTES:
            continue
        if len(selected) + 1 > MAX_FILES:
            raise ValueError(f"Source file limit exceeded ({MAX_FILES}); narrow the scan root.")
        if total_bytes + entry.size > MAX_TOTAL_SOURCE_BYTES:
            raise ValueError(
                "Source byte limit exceeded "
                f"({MAX_TOTAL_SOURCE_BYTES}); narrow the scan root."
            )
        selected.append(entry)
        total_bytes += entry.size
    return selected


def _write_blob(root: Path, entry: BlobEntry, content: bytes) -> None:
    output = root.joinpath(*PurePosixPath(entry.path).parts)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(output, flags, 0o600)
    except OSError as error:
        raise ValueError(f"Could not materialize repository source {entry.path}: {error}") from error
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)


def _github_token() -> str:
    result = _run(["gh", "auth", "token"])
    if result.returncode != 0 or not result.stdout.strip():
        raise ValueError("Could not authenticate the bounded GitHub archive request.")
    return result.stdout.strip()


def _download_archive(source: str, head_oid: str, destination: Path) -> None:
    owner, repo = source.removeprefix("https://github.com/").split("/", 1)
    request = urllib.request.Request(
        f"https://api.github.com/repos/{owner}/{repo}/tarball/{head_oid}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {_github_token()}",
            "User-Agent": "ai-tell-scan",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            content_length = response.headers.get("Content-Length")
            if content_length is not None and int(content_length) > MAX_ARCHIVE_BYTES:
                raise ValueError("Repository archive exceeds the bounded download limit.")
            total = 0
            with destination.open("xb") as handle:
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_ARCHIVE_BYTES:
                        raise ValueError(
                            "Repository archive exceeds the bounded download limit."
                        )
                    handle.write(chunk)
    except (OSError, urllib.error.URLError, ValueError) as error:
        if isinstance(error, ValueError):
            raise
        raise ValueError("Could not download the bounded public repository archive.") from error


def _git_blob_oid(content: bytes) -> str:
    payload = f"blob {len(content)}\0".encode("ascii") + content
    return hashlib.sha1(payload, usedforsecurity=False).hexdigest()


def _materialize_archive(
    archive: Path, output: Path, entries: list[BlobEntry]
) -> None:
    expected = {entry.path: entry for entry in entries}
    materialized: set[str] = set()
    prefix: str | None = None
    member_count = 0
    content_bytes = 0
    try:
        package = tarfile.open(archive, mode="r:gz")
    except (OSError, tarfile.TarError) as error:
        raise ValueError("GitHub returned an invalid repository archive.") from error

    with package:
        try:
            for member in package:
                member_count += 1
                if member_count > MAX_ARCHIVE_MEMBERS:
                    raise ValueError("Repository archive member limit exceeded.")
                if member.size < 0:
                    raise ValueError("Repository archive contains an invalid member size.")
                content_bytes += member.size
                if content_bytes > MAX_ARCHIVE_CONTENT_BYTES:
                    raise ValueError("Repository archive content limit exceeded.")

                path = PurePosixPath(member.name)
                if (
                    path.is_absolute()
                    or not path.parts
                    or any(part in {"", ".", ".."} for part in path.parts)
                ):
                    raise ValueError("Repository archive contains an unsafe path.")
                if prefix is None:
                    prefix = path.parts[0]
                elif path.parts[0] != prefix:
                    raise ValueError("Repository archive contains multiple roots.")
                if len(path.parts) == 1:
                    if not member.isdir():
                        raise ValueError("Repository archive root is not a directory.")
                    continue

                relative = PurePosixPath(*path.parts[1:]).as_posix()
                entry = expected.get(relative)
                if entry is None:
                    continue
                if relative in materialized or not member.isfile():
                    raise ValueError(
                        f"Repository archive has an invalid selected member: {relative}."
                    )
                if member.size != entry.size:
                    raise ValueError(
                        f"Repository archive size does not match GitHub metadata: {relative}."
                    )
                handle = package.extractfile(member)
                if handle is None:
                    raise ValueError(
                        f"Could not read selected repository source: {relative}."
                    )
                content = handle.read(MAX_FILE_BYTES + 1)
                if len(content) != entry.size or _git_blob_oid(content) != entry.oid:
                    raise ValueError(
                        f"Repository archive content does not match GitHub metadata: {relative}."
                    )
                _write_blob(output, entry, content)
                materialized.add(relative)
        except (OSError, tarfile.TarError) as error:
            raise ValueError("Could not read the bounded repository archive.") from error

    missing = sorted(expected.keys() - materialized)
    if missing:
        raise ValueError(
            f"Repository archive omitted selected source: {missing[0]}."
        )


def checkout(source: str, workspace: Path) -> Path:
    if HOSTED_REPOSITORY_RE.fullmatch(source) is None:
        raise ValueError("Repository URL must be exact https://github.com/<owner>/<repo>.")
    _verify_public_repository(source)
    head_oid, tree_entries = _fetch_tree(source)
    entries = select_entries(tree_entries)

    resolved = workspace.expanduser().resolve(strict=False)
    if os.path.lexists(resolved):
        raise ValueError(f"Refusing to reuse checkout workspace: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.mkdir(mode=0o700)
    output = resolved / "repository"
    output.mkdir(mode=0o700)
    archive = resolved / ".source.tar.gz"
    try:
        _download_archive(source, head_oid, archive)
        _materialize_archive(archive, output, entries)
    finally:
        archive.unlink(missing_ok=True)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize bounded source from an exact public GitHub repository."
    )
    parser.add_argument("repository_url")
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = checkout(args.repository_url, args.workspace)
    except ValueError as error:
        print(f"ai-tell-scan: {error}", file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
