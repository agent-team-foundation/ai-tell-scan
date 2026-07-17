#!/usr/bin/env python3
"""Deterministic, read-only candidate engine for AI Tell Scan.

The engine deliberately detects visible combinations rather than authorship.
It uses only the Python standard library so the shipped skill stays portable.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

SCHEMA_VERSION = "ats-1"
TOOL_VERSION = "0.2.0"
SUPPORTED_EXTENSIONS = {
    ".css",
    ".html",
    ".js",
    ".jsx",
    ".less",
    ".sass",
    ".scss",
    ".ts",
    ".tsx",
}
UI_EXTENSIONS = {".html", ".js", ".jsx", ".ts", ".tsx"}
MAX_TOTAL_SOURCE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_SOURCE_LINES = 1_000_000
MAX_INDEXED_CSS_BLOCKS = 100_000
MAX_INDEXED_ELEMENTS = 100_000
MAX_CANDIDATES = 10_000
HOSTED_REPOSITORY_RE = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
)
SKIP_DIRECTORIES = {
    "__tests__",
    "__mocks__",
    "__snapshots__",
    ".cache",
    ".git",
    ".next",
    ".nuxt",
    ".output",
    ".turbo",
    ".vercel",
    "build",
    "coverage",
    "cypress",
    "dist",
    "e2e",
    "fixture",
    "fixtures",
    "generated",
    "mock",
    "mocks",
    "node_modules",
    "out",
    "playwright",
    "spec",
    "specs",
    "storybook-static",
    "test",
    "tests",
    "test-data",
    "vendor",
}
SKIP_FILE_RE = re.compile(
    r"(?:^|/)(?:__snapshots__|fixtures?|mocks?|test-data)(?:/|$)|"
    r"(?:\.d\.ts|\.generated\.[^.]+|\.min\.[^.]+|\.snap|\.stories\.[^.]+|\.test\.[^.]+|\.spec\.[^.]+)$",
    re.IGNORECASE,
)
STATIC_CLASS_RE = re.compile(
    r"className\s*=\s*(?:\"(?P<double>[^\"]*)\"|'(?P<single>[^']*)'|\{\s*`(?P<template>[^`]*)`\s*\}|"
    r"\{\s*\"(?P<braced_double>[^\"]*)\"\s*\}|\{\s*'(?P<braced_single>[^']*)'\s*\})",
    re.DOTALL,
)
ELEMENT_RE = re.compile(
    r"<(?P<tag>[A-Za-z][\w.-]*)\b(?P<attrs>[^<>]{0,2400})>", re.DOTALL
)
CSS_BLOCK_RE = re.compile(r"(?P<selectors>[^{}]+)\{(?P<body>[^{}]*)\}", re.DOTALL)
CSS_CLASS_RE = re.compile(r"\.([A-Za-z_][\w-]*)")


@dataclass(frozen=True)
class SourceFile:
    relative_path: str
    absolute_path: Path
    text: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class CssBlock:
    source: SourceFile
    body_line: int
    body: str


@dataclass(frozen=True)
class Element:
    file: SourceFile
    tag: str
    line: int
    attrs: str
    classes: str
    style_blocks: tuple[CssBlock, ...]

    @property
    def surface(self) -> str:
        styles = " ".join(block.body for block in self.style_blocks)
        return f"{self.attrs} {self.classes} {styles}".lower()


@dataclass(frozen=True)
class Evidence:
    kind: str
    file: str
    line: int
    detail: str
    excerpt: str


@dataclass(frozen=True)
class Candidate:
    candidateId: str
    ruleId: str
    title: str
    severity: str
    confidence: float
    file: str
    line: int
    whyItHurtsTrust: str
    minimalFix: str
    evidence: tuple[Evidence, ...]

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["evidence"] = [asdict(item) for item in self.evidence]
        result["disposition"] = "pending"
        return result


@dataclass(frozen=True)
class RuleDefinition:
    rule_id: str
    title: str
    severity: str
    confidence: float
    why: str
    fix: str


@dataclass
class ScanIndex:
    root: Path
    files: list[SourceFile]
    ui_files: list[SourceFile]
    elements: list[Element]
    frameworks: list[str]
    css_classes: dict[str, list[CssBlock]]

    def elements_for_file(self, source: SourceFile) -> list[Element]:
        return [element for element in self.elements if element.file == source]


RULES: dict[str, RuleDefinition] = {
    "ats.gradient-display-heading": RuleDefinition(
        "ats.gradient-display-heading",
        "Gradient-clipped display heading",
        "high",
        0.97,
        "A large multicolor clipped headline is an overlearned launch-page default; when it carries the first message, the brand can feel selected from a generator preset.",
        "Keep the wording and hierarchy, remove text clipping, and use one brand-owned solid color or a restrained accent on a smaller element.",
    ),
    "ats.aurora-centered-hero": RuleDefinition(
        "ats.aurora-centered-hero",
        "Centered hero with decorative aurora blobs",
        "high",
        0.96,
        "The full-screen centered hero plus blurred gradient blobs is a recognizable template composition that can make an otherwise credible product look interchangeable.",
        "Preserve the content, remove the decorative blob layer, and give the hero a product-specific layout or concrete product evidence.",
    ),
    "ats.glass-floating-nav": RuleDefinition(
        "ats.glass-floating-nav",
        "Floating glass navigation capsule",
        "medium",
        0.94,
        "A fixed translucent capsule with blur, border, shadow, and a CTA stacks several fashionable defaults into the first interaction users see.",
        "Keep the navigation behavior, flatten the container to one surface treatment, and reserve the strongest emphasis for the primary action.",
    ),
    "ats.icon-card-triptych": RuleDefinition(
        "ats.icon-card-triptych",
        "Three-column icon-card feature block",
        "high",
        0.95,
        "Three identical rounded cards with tinted icon tiles turn product differentiation into a stock layout and often hide which capability actually matters.",
        "Promote the most important capability, vary the information shape by content, and remove decorative icon containers that add no meaning.",
    ),
    "ats.repeated-section-kickers": RuleDefinition(
        "ats.repeated-section-kickers",
        "Uppercase kicker repeated above every section",
        "medium",
        0.93,
        "Repeated tiny uppercase labels create a generator-like rhythm and add hierarchy chrome without adding information.",
        "Keep at most the one kicker that supplies real context; let the remaining section titles stand on their own.",
    ),
    "ats.round-metric-proof-row": RuleDefinition(
        "ats.round-metric-proof-row",
        "Suspicious round-number proof row",
        "high",
        0.99,
        "A three-up row of generic round metrics looks like invented social proof; one ungrounded number can damage trust in every adjacent claim.",
        "Remove unverifiable metrics or replace them with a specific measured value and a visible source or date.",
    ),
    "ats.glass-card-field": RuleDefinition(
        "ats.glass-card-field",
        "Repeated glass cards over an atmospheric background",
        "medium",
        0.92,
        "When every surface uses translucency, blur, border, and rounding, the page reads as a mood-board preset instead of an intentional hierarchy.",
        "Choose one flat base surface, keep glass treatment only where depth communicates state, and reduce repeated border/shadow layers.",
    ),
    "ats.pill-role-overload": RuleDefinition(
        "ats.pill-role-overload",
        "Pill shape used for unrelated roles",
        "medium",
        0.92,
        "Using the same capsule silhouette for badges, actions, fields, and status controls flattens affordances and gives the interface a template-stamped texture.",
        "Reserve pills for one semantic family, then restore role-specific shapes for actions, fields, and status indicators.",
    ),
    "ats.spring-hover-everywhere": RuleDefinition(
        "ats.spring-hover-everywhere",
        "Identical springy hover treatment everywhere",
        "medium",
        0.94,
        "Repeated scale or lift animation on every action makes the interface feel generated and can obscure which interactions are important.",
        "Remove universal transition-all/scale behavior and animate only the property and interactions that communicate a state change.",
    ),
    "ats.multicolor-card-wash": RuleDefinition(
        "ats.multicolor-card-wash",
        "Each feature card tinted with its own accent color",
        "medium",
        0.93,
        "A row of otherwise identical cards differentiated only by green, purple, and orange washes is a common shortcut for visual variety rather than real hierarchy.",
        "Use one surface system and differentiate cards through content, data, or structure; keep color semantic and limited.",
    ),
}


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def candidate_set_digest(candidates: Iterable[dict[str, object]]) -> str:
    normalized = [
        {
            key: value
            for key, value in candidate.items()
            if key not in {"disposition", "reviewRationale"}
        }
        for candidate in candidates
    ]
    return canonical_digest(normalized)


def _read_package(root: Path) -> dict[str, object]:
    package_path = root / "package.json"
    if not package_path.is_file():
        return {}
    try:
        value = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _dependency_names(package: dict[str, object]) -> set[str]:
    result: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        section = package.get(key)
        if isinstance(section, dict):
            result.update(str(name) for name in section)
    return result


def _declared_frameworks(dependencies: set[str]) -> set[str]:
    frameworks: set[str] = set()
    if "next" in dependencies:
        frameworks.add("nextjs")
    if "react" in dependencies or "next" in dependencies:
        frameworks.add("react")
    return frameworks


def _source_references_react(source: SourceFile) -> bool:
    return bool(
        re.search(
            r"(?:from\s+['\"]react(?:/[^'\"]*)?['\"]|"
            r"require\(['\"]react(?:/[^'\"]*)?['\"]\)|React\.)",
            source.text[:20_000],
        )
    )


def _package_dependencies(
    files: Iterable[SourceFile],
) -> dict[Path, set[str]]:
    packages: dict[Path, set[str]] = {}
    for source in files:
        if source.absolute_path.name != "package.json":
            continue
        try:
            value = json.loads(source.text)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            packages[source.absolute_path.parent] = _dependency_names(value)
    return packages


def _nearest_package_dependencies(
    root: Path, source: SourceFile, packages: dict[Path, set[str]]
) -> tuple[Path | None, set[str]]:
    current = source.absolute_path.parent
    while True:
        dependencies = packages.get(current)
        if dependencies is not None:
            return current, dependencies
        if current == root:
            return None, set()
        parent = current.parent
        if parent == current or root not in parent.parents and parent != root:
            return None, set()
        current = parent


def _scope_react_ui_files(
    root: Path, files: Iterable[SourceFile], ui_files: Iterable[SourceFile]
) -> tuple[list[SourceFile], list[str]]:
    """Keep UI files inside their nearest React/Next package boundary.

    A repository-level dependency union is unsafe in monorepos: one React package
    must not make a sibling Preact or plain package eligible for UI rules.
    """
    packages = _package_dependencies(files)
    declared: set[str] = set()
    for dependencies in packages.values():
        declared.update(_declared_frameworks(dependencies))

    scoped: list[SourceFile] = []
    inferred: set[str] = set()
    for source in ui_files:
        package_root, dependencies = _nearest_package_dependencies(
            root, source, packages
        )
        file_frameworks = _declared_frameworks(dependencies)
        if "react" in file_frameworks:
            scoped.append(source)
            continue

        # Support a manifest-less repository (or a root manifest missing a
        # declaration) only when the source itself imports React. Never apply
        # this fallback inside a nested non-React package or a Preact package.
        is_root_scope = package_root in {None, root}
        if (
            is_root_scope
            and "preact" not in dependencies
            and _source_references_react(source)
        ):
            scoped.append(source)
            inferred.add("react")

    frameworks = declared | inferred
    return scoped, [name for name in ("nextjs", "react") if name in frameworks]


def _default_target_id(root: Path) -> str:
    package_name = _read_package(root).get("name")
    if isinstance(package_name, str) and package_name.strip():
        return package_name.strip()
    return root.name


def _is_skipped(relative_path: str) -> bool:
    normalized = relative_path.replace(os.sep, "/")
    return bool(SKIP_FILE_RE.search(normalized))


def read_sources(
    root: Path,
    max_files: int = 5000,
    max_file_bytes: int = 1_000_000,
    max_total_bytes: int = MAX_TOTAL_SOURCE_BYTES,
    max_total_lines: int = MAX_TOTAL_SOURCE_LINES,
) -> list[SourceFile]:
    files: list[SourceFile] = []
    total_bytes = 0
    total_lines = 0
    for current, directories, names in os.walk(root, followlinks=False):
        directories[:] = sorted(
            directory
            for directory in directories
            if directory not in SKIP_DIRECTORIES
            and not (Path(current) / directory).is_symlink()
        )
        for name in sorted(names):
            path = Path(current) / name
            if (
                path.suffix.lower() not in SUPPORTED_EXTENSIONS
                and name != "package.json"
            ) or path.is_symlink():
                continue
            relative = path.relative_to(root).as_posix()
            if _is_skipped(relative):
                continue
            try:
                with path.open("rb") as handle:
                    raw = handle.read(max_file_bytes + 1)
                if len(raw) > max_file_bytes:
                    continue
                text = raw.decode("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if total_bytes + len(raw) > max_total_bytes:
                raise ValueError(
                    "Source byte limit exceeded "
                    f"({max_total_bytes}); narrow the scan root."
                )
            file_lines = raw.count(b"\n") + (1 if raw else 0)
            if total_lines + file_lines > max_total_lines:
                raise ValueError(
                    "Source line limit exceeded "
                    f"({max_total_lines}); narrow the scan root."
                )
            total_bytes += len(raw)
            total_lines += file_lines
            files.append(SourceFile(relative, path, text, tuple(text.splitlines())))
            if len(files) > max_files:
                raise ValueError(
                    f"Source file limit exceeded ({max_files}); narrow the scan root."
                )
    return files


def _css_index(
    files: Iterable[SourceFile],
) -> dict[str, list[CssBlock]]:
    result: dict[str, list[CssBlock]] = {}
    block_count = 0
    for source in files:
        if source.absolute_path.suffix.lower() not in {
            ".css",
            ".less",
            ".sass",
            ".scss",
        }:
            continue
        for block in CSS_BLOCK_RE.finditer(source.text):
            block_count += 1
            if block_count > MAX_INDEXED_CSS_BLOCKS:
                raise ValueError(
                    "CSS block limit exceeded "
                    f"({MAX_INDEXED_CSS_BLOCKS}); narrow the scan root."
                )
            body = block.group("body")
            body_line = source.text.count("\n", 0, block.start("body")) + 1
            css_block = CssBlock(source=source, body_line=body_line, body=body)
            for class_name in CSS_CLASS_RE.findall(block.group("selectors")):
                result.setdefault(class_name, []).append(css_block)
    return result


def _static_classes(attrs: str) -> str:
    match = STATIC_CLASS_RE.search(attrs)
    if match is None:
        return ""
    for name in ("double", "single", "template", "braced_double", "braced_single"):
        value = match.group(name)
        if value is not None:
            return value
    return ""


def _elements(
    files: Iterable[SourceFile],
    css_classes: dict[str, list[CssBlock]],
) -> list[Element]:
    result: list[Element] = []
    for source in files:
        if source.absolute_path.suffix.lower() not in UI_EXTENSIONS:
            continue
        for match in ELEMENT_RE.finditer(source.text):
            attrs = match.group("attrs")
            classes = _static_classes(attrs)
            style_blocks: list[CssBlock] = []
            seen_blocks: set[tuple[str, int, str]] = set()
            for token in re.findall(r"[A-Za-z_][\w-]*", classes):
                for css_block in css_classes.get(token, []):
                    css_source = css_block.source
                    same_directory = (
                        css_source.absolute_path.parent == source.absolute_path.parent
                    )
                    css_name = re.escape(css_source.absolute_path.name)
                    explicit_import = bool(
                        re.search(
                            rf"(?:\bimport\s+(?:[^'\"]+\s+from\s+)?|\brequire\(\s*|\bimport\(\s*)['\"][^'\"]*{css_name}['\"]",
                            source.text,
                        )
                    )
                    if same_directory and explicit_import:
                        block_key = (
                            css_source.relative_path,
                            css_block.body_line,
                            css_block.body,
                        )
                        if block_key not in seen_blocks:
                            seen_blocks.add(block_key)
                            style_blocks.append(css_block)
            result.append(
                Element(
                    file=source,
                    tag=match.group("tag").lower(),
                    line=source.text.count("\n", 0, match.start()) + 1,
                    attrs=attrs,
                    classes=classes,
                    style_blocks=tuple(style_blocks),
                )
            )
            if len(result) > MAX_INDEXED_ELEMENTS:
                raise ValueError(
                    "UI element limit exceeded "
                    f"({MAX_INDEXED_ELEMENTS}); narrow the scan root."
                )
    return result


def _is_ui_source(source: SourceFile) -> bool:
    suffix = source.absolute_path.suffix.lower()
    if suffix in {".html", ".jsx", ".tsx"}:
        return True
    if suffix not in {".js", ".ts"}:
        return False
    return bool(
        re.search(
            r"(?:from\s+['\"]react['\"]|require\(['\"]react['\"]\)|React\.(?:createElement|Fragment))",
            source.text,
        )
        or re.search(r"return\s*\(\s*<[A-Za-z]", source.text)
    )


def build_index(root: Path, max_files: int = 5000) -> ScanIndex:
    resolved = root.expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError(f"Scan root is not a directory: {resolved}")
    files = read_sources(resolved, max_files=max_files)
    ui_candidates = [source for source in files if _is_ui_source(source)]
    ui_files, frameworks = _scope_react_ui_files(resolved, files, ui_candidates)
    css_classes = _css_index(files)
    return ScanIndex(
        root=resolved,
        files=files,
        ui_files=ui_files,
        elements=_elements(ui_files, css_classes),
        frameworks=frameworks,
        css_classes=css_classes,
    )


def _excerpt(source: SourceFile, line: int, width: int = 180) -> str:
    if line < 1 or line > len(source.lines):
        return ""
    return re.sub(r"\s+", " ", source.lines[line - 1].strip())[:width]


def _window(source: SourceFile, line: int, before: int, after: int) -> str:
    start = max(0, line - 1 - before)
    end = min(len(source.lines), line + after)
    return "\n".join(source.lines[start:end])


def _line_for_pattern(
    source: SourceFile, pattern: str, start_line: int = 1, flags: int = re.IGNORECASE
) -> int:
    start_offset = sum(len(item) + 1 for item in source.lines[: max(0, start_line - 1)])
    match = re.search(pattern, source.text[start_offset:], flags)
    if match is None:
        raise ValueError(
            f"Could not resolve evidence pattern to a source line in {source.relative_path}."
        )
    return source.text.count("\n", 0, start_offset + match.start()) + 1


def _evidence(kind: str, source: SourceFile, line: int, detail: str) -> Evidence:
    return Evidence(kind, source.relative_path, line, detail, _excerpt(source, line))


def _element_evidence(
    kind: str,
    element: Element,
    detail: str,
    patterns: Iterable[str] = (),
    *,
    search_source: bool = False,
) -> Evidence:
    """Attribute evidence to the file and line that actually carries a primitive."""
    pattern_list = tuple(patterns)
    inline_surface = f"{element.attrs} {element.classes}"
    if not pattern_list or _has_any(inline_surface, pattern_list):
        return _evidence(kind, element.file, element.line, detail)
    for block in element.style_blocks:
        for pattern in pattern_list:
            match = re.search(pattern, block.body, re.IGNORECASE)
            if match is not None:
                line = block.body_line + block.body.count("\n", 0, match.start())
                return _evidence(kind, block.source, line, detail)
    if search_source and pattern_list:
        combined_pattern = "|".join(f"(?:{pattern})" for pattern in pattern_list)
        return _evidence(
            kind,
            element.file,
            _line_for_pattern(element.file, combined_pattern, element.line),
            detail,
        )
    return _evidence(kind, element.file, element.line, detail)


def _candidate(
    rule_id: str, source: SourceFile, line: int, evidence: list[Evidence]
) -> Candidate:
    rule = RULES[rule_id]
    identity = canonical_digest(
        {
            "ruleId": rule_id,
            "file": source.relative_path,
            "line": line,
            "evidence": [(item.kind, item.file, item.line) for item in evidence],
        }
    )[:16]
    return Candidate(
        candidateId=f"ats-{identity}",
        ruleId=rule.rule_id,
        title=rule.title,
        severity=rule.severity,
        confidence=rule.confidence,
        file=source.relative_path,
        line=line,
        whyItHurtsTrust=rule.why,
        minimalFix=rule.fix,
        evidence=tuple(evidence),
    )


def _has_any(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _accent_tokens(text: str) -> set[str]:
    accents = set(
        re.findall(
            r"(?:indigo|violet|purple|pink|fuchsia|blue|cyan)", text, re.IGNORECASE
        )
    )
    for raw_hex in re.findall(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b", text):
        expanded = (
            "".join(character * 2 for character in raw_hex)
            if len(raw_hex) == 3
            else raw_hex
        )
        red, green, blue = (int(expanded[index : index + 2], 16) for index in (0, 2, 4))
        if max(red, green, blue) - min(red, green, blue) >= 32:
            accents.add(f"#{expanded.lower()}")
    for hue in re.findall(r"hsla?\(\s*(\d{1,3})(?:deg)?[\s,]", text, re.IGNORECASE):
        accents.add(f"hsl:{int(hue) % 360}")
    return accents


def _gradient_display_heading(index: ScanIndex) -> list[Candidate]:
    candidates: list[Candidate] = []
    for element in index.elements:
        if element.tag not in {"h1", "h2"}:
            continue
        surface = element.surface
        gates = [
            _has_any(surface, (r"bg-gradient", r"linear-gradient")),
            _has_any(surface, (r"bg-clip-text", r"background-clip\s*:\s*text")),
            _has_any(
                surface, (r"text-transparent", r"(?:^|[;\s])color\s*:\s*transparent")
            ),
            _has_any(
                surface,
                (
                    r"text-(?:4|5|6|7|8|9)xl",
                    r"font-size\s*:\s*(?:clamp\(|[3-9](?:\.\d+)?(?:rem|em))",
                ),
            ),
        ]
        accents = _accent_tokens(surface)
        if all(gates) and len(accents) >= 2:
            candidates.append(
                _candidate(
                    "ats.gradient-display-heading",
                    element.file,
                    element.line,
                    [
                        _evidence(
                            "display-heading",
                            element.file,
                            element.line,
                            "A large h1/h2 owns the primary message.",
                        ),
                        _element_evidence(
                            "multicolor-gradient",
                            element,
                            f"Accent families: {', '.join(sorted(accents))}.",
                            (r"bg-gradient", r"linear-gradient"),
                        ),
                        _element_evidence(
                            "text-clip",
                            element,
                            "The background is clipped to the text.",
                            (r"bg-clip-text", r"background-clip\s*:\s*text"),
                        ),
                        _element_evidence(
                            "transparent-text",
                            element,
                            "The text foreground is transparent.",
                            (
                                r"text-transparent",
                                r"(?:^|[;\s])color\s*:\s*transparent",
                            ),
                        ),
                    ],
                )
            )
    return candidates


def _aurora_centered_hero(index: ScanIndex) -> list[Candidate]:
    candidates: list[Candidate] = []
    for source in index.ui_files:
        for element in index.elements_for_file(source):
            if element.tag not in {"div", "header", "main", "section"}:
                continue
            nearby = _window(source, element.line, 3, 120).lower()
            surface = f"{element.surface} {nearby}"
            centered = "text-center" in surface and _has_any(
                surface, (r"items-center", r"justify-center")
            )
            tall = _has_any(
                surface,
                (r"min-h-(?:screen|\[\d+vh\])", r"h-screen", r"py-(?:2[048]|3[02])"),
            )
            atmospheric = _has_any(
                surface,
                (r"blur-(?:2xl|3xl|\[)", r"filter\s*:\s*blur", r"radial-gradient"),
            )
            positioned = "absolute" in surface or "position: absolute" in surface
            gradient = _has_any(
                surface, (r"bg-gradient", r"linear-gradient", r"radial-gradient")
            )
            message = "<h1" in nearby and _has_any(
                nearby, (r"<button", r"<a\b[^>]*href")
            )
            accents = _accent_tokens(surface)
            if (
                centered
                and tall
                and atmospheric
                and positioned
                and gradient
                and message
                and len(accents) >= 2
            ):
                candidates.append(
                    _candidate(
                        "ats.aurora-centered-hero",
                        source,
                        element.line,
                        [
                            _element_evidence(
                                "centered-full-hero",
                                element,
                                "Tall hero centers its message and controls.",
                                (
                                    r"text-center",
                                    r"items-center",
                                    r"justify-center",
                                    r"min-h-(?:screen|\[\d+vh\])",
                                    r"h-screen",
                                ),
                                search_source=True,
                            ),
                            _element_evidence(
                                "decorative-aurora",
                                element,
                                "Absolutely positioned blur and gradient create a decorative glow.",
                                (
                                    r"blur-(?:2xl|3xl|\[)",
                                    r"filter\s*:\s*blur",
                                    r"radial-gradient",
                                ),
                                search_source=True,
                            ),
                            _evidence(
                                "hero-conversion",
                                source,
                                _line_for_pattern(source, r"<h1", element.line),
                                "The composition contains the primary heading and CTA.",
                            ),
                        ],
                    )
                )
                break
    return candidates


def _glass_floating_nav(index: ScanIndex) -> list[Candidate]:
    candidates: list[Candidate] = []
    for element in index.elements:
        if element.tag != "nav":
            continue
        nearby = _window(element.file, element.line, 2, 45).lower()
        surface = f"{element.surface} {nearby}"
        anchored = _has_any(
            surface,
            (r"(?:fixed|sticky)[^\n]{0,80}top", r"position\s*:\s*(?:fixed|sticky)"),
        )
        blurred = _has_any(surface, (r"backdrop-blur", r"backdrop-filter\s*:\s*blur"))
        translucent = _has_any(
            surface,
            (r"bg-[^\s\"']+/[1-9]\d?", r"rgba\(", r"hsla\(", r"opacity\s*:\s*0\."),
        )
        capsule = _has_any(
            surface,
            (r"rounded-(?:full|2xl|3xl)", r"border-radius\s*:\s*(?:999|[2-9]\d)"),
        )
        framed = _has_any(surface, (r"\bborder\b", r"box-shadow", r"\bshadow(?:-|\b)"))
        action = _has_any(nearby, (r"<button", r"<a\b[^>]*href"))
        if anchored and blurred and translucent and capsule and framed and action:
            candidates.append(
                _candidate(
                    "ats.glass-floating-nav",
                    element.file,
                    element.line,
                    [
                        _element_evidence(
                            "anchored-nav",
                            element,
                            "Navigation is fixed or sticky near the viewport edge.",
                            (
                                r"(?:fixed|sticky)",
                                r"position\s*:\s*(?:fixed|sticky)",
                            ),
                            search_source=True,
                        ),
                        _element_evidence(
                            "capsule-surface",
                            element,
                            "A large radius turns the navigation surface into a capsule.",
                            (
                                r"rounded-(?:full|2xl|3xl)",
                                r"border-radius\s*:",
                            ),
                            search_source=True,
                        ),
                        _element_evidence(
                            "backdrop-blur",
                            element,
                            "The navigation surface applies backdrop blur.",
                            (r"backdrop-blur", r"backdrop-filter\s*:\s*blur"),
                            search_source=True,
                        ),
                        _element_evidence(
                            "translucent-surface",
                            element,
                            "The navigation surface is translucent.",
                            (
                                r"bg-[^\s\"']+/[1-9]\d?",
                                r"rgba\(",
                                r"hsla\(",
                                r"opacity\s*:\s*0\.",
                            ),
                            search_source=True,
                        ),
                        _element_evidence(
                            "framed-surface",
                            element,
                            "A border or shadow frames the navigation capsule.",
                            (r"\bborder\b", r"box-shadow", r"\bshadow(?:-|\b)"),
                            search_source=True,
                        ),
                        _evidence(
                            "conversion-action",
                            element.file,
                            _line_for_pattern(
                                element.file, r"<(?:a|button)\b", element.line
                            ),
                            "The same capsule contains an action control.",
                        ),
                    ],
                )
            )
    return candidates


def _card_elements_in_range(
    index: ScanIndex, source: SourceFile, start: int, end: int
) -> list[Element]:
    return [
        element
        for element in index.elements_for_file(source)
        if start <= element.line <= end
        and _has_any(
            element.surface, (r"rounded-(?:xl|2xl|3xl)", r"border-radius\s*:\s*[1-9]\d")
        )
        and _has_any(
            element.surface, (r"\bborder\b", r"box-shadow", r"\bshadow(?:-|\b)")
        )
    ]


def _icon_card_triptych(index: ScanIndex) -> list[Candidate]:
    candidates: list[Candidate] = []
    for source in index.ui_files:
        for grid in index.elements_for_file(source):
            if not _has_any(
                grid.surface, (r"grid-cols-3", r"grid-template-columns\s*:\s*repeat\(3")
            ):
                continue
            end = grid.line + 190
            nearby = _window(source, grid.line, 2, 190)
            cards = _card_elements_in_range(index, source, grid.line, end)
            headings = len(re.findall(r"<h[234]\b", nearby, re.IGNORECASE))
            descriptions = len(re.findall(r"<p\b", nearby, re.IGNORECASE))
            icon_tiles: list[Element] = []
            for element in index.elements_for_file(source):
                if not grid.line <= element.line <= end:
                    continue
                square = _has_any(
                    element.surface,
                    (r"(?:w|size)-(?:8|9|10|11|12)", r"width\s*:\s*(?:3[2-9]|4\d)px"),
                ) and _has_any(
                    element.surface,
                    (r"h-(?:8|9|10|11|12)", r"height\s*:\s*(?:3[2-9]|4\d)px"),
                )
                tinted = _has_any(
                    element.surface,
                    (
                        r"bg-(?:blue|cyan|emerald|green|indigo|orange|pink|purple|rose|violet)-",
                        r"background(?:-color)?\s*:",
                    ),
                )
                rounded = _has_any(
                    element.surface, (r"rounded-(?:lg|xl)", r"border-radius")
                )
                local = _window(source, element.line, 0, 8)
                icon = bool(re.search(r"<[A-Z][A-Za-z0-9]*(?:Icon)?\b", local))
                if square and tinted and rounded and icon:
                    icon_tiles.append(element)
            if (
                len(cards) >= 3
                and headings >= 3
                and descriptions >= 3
                and len(icon_tiles) >= 3
            ):
                candidates.append(
                    _candidate(
                        "ats.icon-card-triptych",
                        source,
                        grid.line,
                        [
                            _element_evidence(
                                "three-column-grid",
                                grid,
                                "A three-column feature grid establishes the repeated structure.",
                                (
                                    r"grid-cols-3",
                                    r"grid-template-columns\s*:\s*repeat\(3",
                                ),
                            ),
                            _element_evidence(
                                "uniform-cards",
                                cards[0],
                                f"At least {len(cards)} rounded bordered/shadowed card surfaces repeat.",
                                (
                                    r"rounded-(?:xl|2xl|3xl)",
                                    r"border-radius\s*:",
                                    r"\bborder\b",
                                    r"box-shadow",
                                    r"\bshadow(?:-|\b)",
                                ),
                            ),
                            _element_evidence(
                                "tinted-icon-tiles",
                                icon_tiles[0],
                                f"At least {len(icon_tiles)} rounded colored icon tiles lead the cards.",
                                (
                                    r"bg-(?:blue|cyan|emerald|green|indigo|orange|pink|purple|rose|violet)-",
                                    r"background(?:-color)?\s*:",
                                ),
                            ),
                        ],
                    )
                )
                break
    return candidates


def _repeated_section_kickers(index: ScanIndex) -> list[Candidate]:
    candidates: list[Candidate] = []
    for source in index.ui_files:
        hits: list[Element] = []
        for element in index.elements_for_file(source):
            if element.tag not in {"div", "p", "span"}:
                continue
            surface = element.surface
            if not (
                "uppercase" in surface
                and "tracking-" in surface
                and _has_any(
                    surface, (r"text-(?:xs|sm)", r"font-size\s*:\s*(?:0\.[5-9]|1)")
                )
            ):
                continue
            if re.search(r"<h2\b", _window(source, element.line, 0, 7), re.IGNORECASE):
                hits.append(element)
        if len(hits) >= 3:
            candidates.append(
                _candidate(
                    "ats.repeated-section-kickers",
                    source,
                    hits[0].line,
                    [
                        _element_evidence(
                            "section-kicker",
                            hit,
                            "Uppercase, tracked small text immediately precedes an h2.",
                            (r"uppercase", r"text-transform\s*:\s*uppercase"),
                        )
                        for hit in hits[:3]
                    ],
                )
            )
    return candidates


SUSPICIOUS_METRICS = (
    r"\b(?:[2-9]\d|[1-9]\d{2})\s*k\+",
    r"\b(?:9[5-9](?:\.\d)?|100)\s*%",
    r"\b(?:[2-9]|1\d)\s*x\b",
    r"\b(?:[2-9]\d{2,}|1\d{3,})\+\s*(?:customers|teams|users|developers|companies)\b",
    r"\b(?:[1-9]\d{0,2})\s*m\+",
)


def _round_metric_proof_row(index: ScanIndex) -> list[Candidate]:
    candidates: list[Candidate] = []
    metric_re = re.compile(
        "|".join(f"(?:{item})" for item in SUSPICIOUS_METRICS), re.IGNORECASE
    )
    for source in index.ui_files:
        for element in index.elements_for_file(source):
            if not _has_any(
                element.surface,
                (
                    r"grid-cols-3",
                    r"grid-template-columns\s*:\s*repeat\(3",
                    r"justify-(?:around|between|evenly)",
                ),
            ):
                continue
            nearby = _window(source, element.line, 1, 100)
            matches = list(metric_re.finditer(nearby))
            values = {
                re.sub(r"\s+", "", match.group(0).lower()): match.group(0)
                for match in matches
            }
            if len(values) < 3:
                continue
            evidence: list[Evidence] = [
                _element_evidence(
                    "proof-row",
                    element,
                    "A three-up/fanned layout presents the values as social proof.",
                    (
                        r"grid-cols-3",
                        r"grid-template-columns\s*:\s*repeat\(3",
                        r"justify-(?:around|between|evenly)",
                    ),
                )
            ]
            for value, raw_value in sorted(values.items())[:3]:
                literal_parts = re.split(r"\s+", raw_value.strip())
                evidence_pattern = r"\s*".join(
                    re.escape(part) for part in literal_parts
                )
                line = _line_for_pattern(source, evidence_pattern, element.line)
                evidence.append(
                    _evidence(
                        "round-metric", source, line, f"Generic proof value: {value}."
                    )
                )
            candidates.append(
                _candidate("ats.round-metric-proof-row", source, element.line, evidence)
            )
            break
    return candidates


def _glass_card_field(index: ScanIndex) -> list[Candidate]:
    candidates: list[Candidate] = []
    for source in index.ui_files:
        lowered = source.text.lower()
        if re.search(r"\b(?:admin|analytics|dashboard|data table)\b", lowered[:8000]):
            continue
        glass: list[Element] = []
        for element in index.elements_for_file(source):
            surface = element.surface
            if (
                _has_any(surface, (r"backdrop-blur", r"backdrop-filter\s*:\s*blur"))
                and _has_any(surface, (r"bg-[^\s\"']+/[1-9]\d?", r"rgba\(", r"hsla\("))
                and _has_any(surface, (r"rounded-(?:xl|2xl|3xl)", r"border-radius"))
                and _has_any(
                    surface, (r"\bborder\b", r"box-shadow", r"\bshadow(?:-|\b)")
                )
            ):
                glass.append(element)
        page_context = "<h1" in lowered and _has_any(
            lowered, (r"<button", r"<a\b[^>]*href")
        )
        atmosphere = _has_any(
            lowered,
            (r"bg-gradient", r"linear-gradient", r"radial-gradient", r"blur-3xl"),
        )
        if len(glass) >= 4 and page_context and atmosphere:
            candidates.append(
                _candidate(
                    "ats.glass-card-field",
                    source,
                    glass[0].line,
                    [
                        _element_evidence(
                            "repeated-glass-panel",
                            item,
                            "Blurred translucent rounded panel repeats on the page.",
                            (r"backdrop-blur", r"backdrop-filter\s*:\s*blur"),
                        )
                        for item in glass[:3]
                    ]
                    + [
                        _evidence(
                            "atmospheric-layer",
                            source,
                            _line_for_pattern(source, r"(?:gradient|blur-3xl)"),
                            "A gradient or blur layer sits behind the panels.",
                        )
                    ],
                )
            )
    return candidates


def _pill_role(element: Element) -> str | None:
    if not _has_any(element.surface, (r"rounded-full", r"border-radius\s*:\s*999")):
        return None
    if element.tag in {"a", "button"}:
        return "action"
    if element.tag in {"input", "select", "textarea"}:
        return "field"
    if _has_any(
        element.surface, (r"text-(?:xs|sm)", r"font-size\s*:\s*0\.")
    ) and _has_any(element.surface, (r"p[xy]-", r"padding")):
        return "badge"
    if _has_any(
        element.surface, (r"(?:h|w)-(?:2|3|4|5|6|8|10|12)", r"(?:height|width)\s*:")
    ):
        return "status-or-avatar"
    return None


def _pill_role_overload(index: ScanIndex) -> list[Candidate]:
    candidates: list[Candidate] = []
    for source in index.ui_files:
        role_hits: dict[str, list[Element]] = {}
        for element in index.elements_for_file(source):
            role = _pill_role(element)
            if role is not None:
                role_hits.setdefault(role, []).append(element)
        all_hits = [item for hits in role_hits.values() for item in hits]
        if (
            len(all_hits) >= 7
            and len(role_hits) >= 3
            and len(role_hits.get("action", [])) >= 2
        ):
            chosen = [hits[0] for _, hits in sorted(role_hits.items())]
            candidates.append(
                _candidate(
                    "ats.pill-role-overload",
                    source,
                    min(item.line for item in all_hits),
                    [
                        _element_evidence(
                            "pill-role",
                            item,
                            f"Pill treatment used for {role}.",
                            (r"rounded-full", r"border-radius\s*:\s*999"),
                        )
                        for role, item in zip(sorted(role_hits), chosen)
                    ],
                )
            )
    return candidates


def _spring_hover_everywhere(index: ScanIndex) -> list[Candidate]:
    candidates: list[Candidate] = []
    for source in index.ui_files:
        hits: list[Element] = []
        for element in index.elements_for_file(source):
            surface = element.surface
            interactive = (
                element.tag in {"a", "button"}
                or "cursor-pointer" in surface
                or 'role="button"' in surface
            )
            transition = _has_any(surface, (r"transition-all", r"transition\s*:\s*all"))
            movement = _has_any(
                surface,
                (
                    r"hover:(?:scale-(?:10[3-9]|110)|-translate-y-)",
                    r":hover[^{}]*(?:transform|scale|translate)",
                ),
            )
            if interactive and transition and movement:
                hits.append(element)
        if len({item.line for item in hits}) >= 4:
            candidates.append(
                _candidate(
                    "ats.spring-hover-everywhere",
                    source,
                    hits[0].line,
                    [
                        _element_evidence(
                            "repeated-hover-motion",
                            item,
                            "Interactive surface combines transition-all with scale/lift hover motion.",
                            (r"transition-all", r"transition\s*:\s*all"),
                        )
                        for item in hits[:4]
                    ],
                )
            )
    return candidates


ACCENT_COLORS = (
    "amber",
    "blue",
    "cyan",
    "emerald",
    "fuchsia",
    "green",
    "indigo",
    "lime",
    "orange",
    "pink",
    "purple",
    "rose",
    "teal",
    "violet",
)


def _multicolor_card_wash(index: ScanIndex) -> list[Candidate]:
    candidates: list[Candidate] = []
    for source in index.ui_files:
        for grid in index.elements_for_file(source):
            if not _has_any(
                grid.surface,
                (r"grid-cols-(?:3|4)", r"grid-template-columns\s*:\s*repeat\((?:3|4)"),
            ):
                continue
            end = grid.line + 190
            cards = _card_elements_in_range(index, source, grid.line, end)
            colors: dict[str, Element] = {}
            for element in cards:
                for color in ACCENT_COLORS:
                    background = re.search(
                        rf"bg-{color}-(?:50|100|400|500)(?:/\d+)?", element.surface
                    )
                    companion = re.search(rf"(?:text|border)-{color}-", element.surface)
                    if background and companion:
                        colors.setdefault(color, element)
            if len(cards) >= 3 and len(colors) >= 3:
                selected = sorted(colors.items())[:3]
                candidates.append(
                    _candidate(
                        "ats.multicolor-card-wash",
                        source,
                        grid.line,
                        [
                            _element_evidence(
                                "feature-grid",
                                grid,
                                "Three/four-column card grid establishes a uniform family.",
                                (
                                    r"grid-cols-(?:3|4)",
                                    r"grid-template-columns\s*:\s*repeat\((?:3|4)",
                                ),
                            )
                        ]
                        + [
                            _element_evidence(
                                "card-accent-wash",
                                element,
                                f"Card surface pairs a {color} tint with same-family foreground/border.",
                                (
                                    rf"bg-{color}-(?:50|100|400|500)(?:/\d+)?",
                                    r"background(?:-color)?\s*:",
                                ),
                            )
                            for color, element in selected
                        ],
                    )
                )
                break
    return candidates


RULE_SCANNERS: tuple[Callable[[ScanIndex], list[Candidate]], ...] = (
    _gradient_display_heading,
    _aurora_centered_hero,
    _glass_floating_nav,
    _icon_card_triptych,
    _repeated_section_kickers,
    _round_metric_proof_row,
    _glass_card_field,
    _pill_role_overload,
    _spring_hover_everywhere,
    _multicolor_card_wash,
)


def source_digest(files: Iterable[SourceFile]) -> str:
    digest = hashlib.sha256()
    for source in sorted(files, key=lambda item: item.relative_path):
        digest.update(source.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(source.text.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def scan(
    root: Path, max_files: int = 5000, target_id: str | None = None
) -> dict[str, object]:
    index = build_index(root, max_files=max_files)
    resolved_target_id = target_id or _default_target_id(index.root)
    if not resolved_target_id.strip():
        raise ValueError("Target id must be a non-empty stable project identifier.")
    candidates: list[Candidate] = []
    if index.frameworks:
        for scanner in RULE_SCANNERS:
            candidates.extend(scanner(index))
            if len(candidates) > MAX_CANDIDATES:
                raise ValueError(
                    "Candidate limit exceeded "
                    f"({MAX_CANDIDATES}); narrow the scan root."
                )

    deduplicated: dict[tuple[str, str], Candidate] = {}
    for candidate in candidates:
        key = (candidate.ruleId, candidate.file)
        previous = deduplicated.get(key)
        if previous is None or (candidate.confidence, -candidate.line) > (
            previous.confidence,
            -previous.line,
        ):
            deduplicated[key] = candidate
    ordered = sorted(
        deduplicated.values(),
        key=lambda item: (-item.confidence, item.ruleId, item.file, item.line),
    )
    candidate_dicts = [candidate.to_dict() for candidate in ordered]
    candidate_digest = candidate_set_digest(candidate_dicts)

    if not index.frameworks:
        status = "unsupported"
        reason = "No React or Next.js project signal was found. AI Tell Scan does not assign a score to this repository."
    elif not index.ui_files:
        status = "not-applicable"
        reason = (
            "React/Next.js is declared, but no scannable UI source files were found."
        )
    elif candidate_dicts:
        status = "needs-review"
        reason = "Deterministic candidates require component/page context review before any tell is confirmed."
    else:
        status = "completed"
        reason = "No composite rule crossed the candidate threshold; this is not proof of authorship or overall design quality."

    return {
        "schemaVersion": SCHEMA_VERSION,
        "tool": {"name": "ai-tell-scan", "version": TOOL_VERSION},
        "target": {
            "label": index.root.name,
            "targetId": resolved_target_id,
            "frameworks": index.frameworks,
            "sourceDigest": source_digest(index.files),
        },
        "scan": {
            "status": status,
            "reason": reason,
            "filesExamined": len(index.files),
            "uiFilesExamined": len(index.ui_files),
            "rulesEvaluated": len(RULES),
            "readOnly": True,
        },
        "summary": {
            "candidateCount": len(candidate_dicts),
            "confirmedCount": 0,
            "rejectedCount": 0,
            "reportedCount": 0,
            "suppressedConfirmedCount": 0,
        },
        "candidateSetDigest": candidate_digest,
        "review": {
            "state": "pending" if candidate_dicts else "not-required",
            "policy": "Review visible page/component context; never infer AI authorship from a candidate.",
        },
        "candidates": candidate_dicts,
        "tells": [],
        "limitations": [
            "Static analysis sees only literal JSX/HTML classes and resolvable local CSS class blocks.",
            "Runtime composition, screenshots, visual prominence, and product intent require agent review.",
            "A clean result is not a design-system audit and does not establish who or what authored the code.",
        ],
    }


def review_template(
    report: dict[str, object], reviewer: str = "agent"
) -> dict[str, object]:
    candidates = report.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("Candidate report has no candidates array.")
    digest = report.get("candidateSetDigest")
    if not isinstance(digest, str):
        raise ValueError("Candidate report has no candidateSetDigest.")
    target = report.get("target")
    tool = report.get("tool")
    if not isinstance(target, dict) or not isinstance(tool, dict):
        raise ValueError("Candidate report has no target/tool binding.")
    source_digest_value = target.get("sourceDigest")
    target_id = target.get("targetId")
    tool_version = tool.get("version")
    tool_name = tool.get("name")
    if not all(
        isinstance(value, str) and value
        for value in (source_digest_value, target_id, tool_name, tool_version)
    ):
        raise ValueError("Candidate report target/tool binding is malformed.")
    decisions: list[dict[str, object]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or not isinstance(
            candidate.get("candidateId"), str
        ):
            raise ValueError("Candidate report contains an invalid candidate.")
        decisions.append(
            {
                "candidateId": candidate["candidateId"],
                "disposition": "pending",
                "rationale": "Replace with context-specific confirmation or rejection rationale.",
            }
        )
    return {
        "schemaVersion": "ats-review-1",
        "candidateSetDigest": digest,
        "sourceDigest": source_digest_value,
        "targetId": target_id,
        "toolName": tool_name,
        "toolVersion": tool_version,
        "reviewer": reviewer,
        "decisions": decisions,
    }


def _tell_key(tell: dict[str, object]) -> str:
    return f"{tell.get('ruleId', '')}|{tell.get('file', '')}"


def _tell_sort_key(item: dict[str, object]) -> tuple[float, str, str, int]:
    return (
        -float(item.get("confidence", 0)),
        str(item.get("ruleId", "")),
        str(item.get("file", "")),
        int(item.get("line", 0)),
    )


def _is_safe_relative_file(value: object) -> bool:
    if not isinstance(value, str) or not value or "\0" in value or "\\" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and path.parts not in {(), (".",)} and ".." not in path.parts


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _is_nonnegative_int(value: object) -> bool:
    return type(value) is int and value >= 0


def _validate_candidate_core(candidate: dict[str, object]) -> None:
    candidate_id = candidate.get("candidateId")
    rule_id = candidate.get("ruleId")
    confidence = candidate.get("confidence")
    line = candidate.get("line")
    if not isinstance(candidate_id, str) or re.fullmatch(r"ats-[0-9a-f]{16}", candidate_id) is None:
        raise ValueError("Report contains an invalid candidateId.")
    if not isinstance(rule_id, str) or re.fullmatch(r"ats\.[a-z0-9-]+", rule_id) is None:
        raise ValueError("Report contains an invalid candidate ruleId.")
    for field in ("title", "whyItHurtsTrust", "minimalFix"):
        value = candidate.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Report candidate {field} is missing or invalid.")
    if candidate.get("severity") not in {"medium", "high"}:
        raise ValueError("Report contains an invalid candidate severity.")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0 <= confidence <= 1
    ):
        raise ValueError("Report contains an invalid candidate confidence.")
    if not _is_safe_relative_file(candidate.get("file")) or type(line) is not int or line < 1:
        raise ValueError("Report contains invalid candidate file/line metadata.")

    evidence = candidate.get("evidence")
    if not isinstance(evidence, list) or len(evidence) < 3:
        raise ValueError("Report candidate requires at least three evidence records.")
    for item in evidence:
        if not isinstance(item, dict):
            raise ValueError("Report contains a malformed evidence record.")
        evidence_line = item.get("line")
        if not _is_safe_relative_file(item.get("file")) or type(evidence_line) is not int or evidence_line < 1:
            raise ValueError("Report contains invalid evidence file/line metadata.")
        for field in ("kind", "detail"):
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Report evidence {field} is missing or invalid.")
        if not isinstance(item.get("excerpt"), str):
            raise ValueError("Report evidence excerpt is missing or invalid.")


def _validated_hosted_repository_source(report: dict[str, object]) -> str | None:
    repository = report.get("repository")
    generated_at = report.get("generatedAt")
    if repository is None and generated_at is None:
        return None
    if not isinstance(repository, dict) or set(repository) != {"source"}:
        raise ValueError("Hosted report repository metadata is missing or invalid.")
    source = repository.get("source")
    if not isinstance(source, str) or HOSTED_REPOSITORY_RE.fullmatch(source) is None:
        raise ValueError("Hosted report repository.source is not a canonical GitHub URL.")
    if not isinstance(generated_at, str):
        raise ValueError("Hosted report generatedAt is missing or invalid.")
    try:
        parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Hosted report generatedAt is not an ISO-8601 timestamp.") from error
    if parsed.tzinfo is None:
        raise ValueError("Hosted report generatedAt must include a timezone.")
    return source


def _validated_finalized_tells(report: dict[str, object]) -> list[dict[str, object]]:
    scan_result = report.get("scan")
    review_result = report.get("review")
    candidates = report.get("candidates")
    tells = report.get("tells")
    summary = report.get("summary")
    if (
        report.get("schemaVersion") != SCHEMA_VERSION
        or not isinstance(scan_result, dict)
        or scan_result.get("status") != "completed"
        or not isinstance(review_result, dict)
        or not isinstance(candidates, list)
        or not all(isinstance(item, dict) for item in candidates)
        or not isinstance(tells, list)
        or not all(isinstance(item, dict) for item in tells)
        or not isinstance(summary, dict)
    ):
        raise ValueError("Report is not a completed, finalized ats-1 report.")
    candidate_objects = [item for item in candidates if isinstance(item, dict)]
    for candidate in candidate_objects:
        _validate_candidate_core(candidate)
    if candidate_set_digest(candidate_objects) != report.get("candidateSetDigest"):
        raise ValueError("Finalized report candidate digest is inconsistent.")
    candidate_ids = [item.get("candidateId") for item in candidate_objects]
    if not all(isinstance(item, str) and item for item in candidate_ids) or len(
        set(candidate_ids)
    ) != len(candidate_ids):
        raise ValueError("Finalized report candidate identities are inconsistent.")

    confirmed: list[dict[str, object]] = []
    for candidate in candidate_objects:
        disposition = candidate.get("disposition")
        rationale = candidate.get("reviewRationale")
        if disposition not in {"confirmed", "rejected"}:
            raise ValueError("Finalized report contains an unreviewed candidate.")
        if not isinstance(rationale, str) or len(rationale.strip()) < 12:
            raise ValueError("Finalized report contains an invalid review rationale.")
        if disposition == "confirmed":
            confirmed.append(
                {key: value for key, value in candidate.items() if key != "disposition"}
            )

    if candidate_objects and review_result.get("state") != "complete":
        raise ValueError("Reviewed candidates require review.state=complete.")
    if not candidate_objects and review_result.get("state") != "not-required":
        raise ValueError(
            "An empty finalized report requires review.state=not-required."
        )
    confirmed.sort(key=_tell_sort_key)
    expected_tells = confirmed[:3]
    expected_summary = {
        "candidateCount": len(candidate_objects),
        "confirmedCount": len(confirmed),
        "rejectedCount": len(candidate_objects) - len(confirmed),
        "reportedCount": len(expected_tells),
        "suppressedConfirmedCount": max(0, len(confirmed) - len(expected_tells)),
    }
    if any(
        not _is_nonnegative_int(summary.get(key)) for key in expected_summary
    ):
        raise ValueError("Finalized report summary fields are missing or invalid.")
    if tells != expected_tells or any(
        summary.get(key) != value for key, value in expected_summary.items()
    ):
        raise ValueError(
            "Finalized report tells or summary are internally inconsistent."
        )
    return confirmed


def _validate_rescan_shape(report: dict[str, object]) -> None:
    rescan = report.get("rescan")
    if rescan is None:
        return
    if not isinstance(rescan, dict):
        raise ValueError("Report rescan metadata is invalid.")
    if "baselineSourceDigest" not in rescan:
        raise ValueError("Report rescan baselineSourceDigest is missing.")
    baseline_digest = rescan.get("baselineSourceDigest")
    if baseline_digest is not None and not _is_sha256(baseline_digest):
        raise ValueError("Report rescan baselineSourceDigest is invalid.")
    for field in ("resolved", "persisted", "introduced"):
        tells = rescan.get(field)
        if not isinstance(tells, list) or not all(
            isinstance(item, dict) for item in tells
        ):
            raise ValueError(f"Report rescan {field} list is invalid.")
        for tell in tells:
            if not isinstance(tell, dict):
                raise ValueError(f"Report rescan {field} list is invalid.")
            _validate_candidate_core(tell)
            rationale = tell.get("reviewRationale")
            if not isinstance(rationale, str) or len(rationale.strip()) < 12:
                raise ValueError(f"Report rescan {field} rationale is invalid.")


def validate_final_report(report: dict[str, object]) -> None:
    """Validate the executable semantics of a completed ats-1 report."""

    tool = report.get("tool")
    target = report.get("target")
    scan_result = report.get("scan")
    limitations = report.get("limitations")
    if not isinstance(tool, dict) or tool.get("name") != "ai-tell-scan":
        raise ValueError("Report tool identity is not ai-tell-scan.")
    if not isinstance(tool.get("version"), str) or not tool["version"]:
        raise ValueError("Report tool version is missing.")
    if not isinstance(target, dict):
        raise ValueError("Report target is missing.")
    if not isinstance(target.get("label"), str) or not target["label"].strip():
        raise ValueError("Report target label is missing.")
    if not isinstance(target.get("targetId"), str) or not target["targetId"]:
        raise ValueError("Report targetId is missing.")
    frameworks = target.get("frameworks")
    if not isinstance(frameworks, list) or any(
        not isinstance(item, str) or item not in {"react", "nextjs"}
        for item in frameworks
    ) or len(frameworks) != len(set(frameworks)):
        raise ValueError("Report framework labels are invalid.")
    if not _is_sha256(target.get("sourceDigest")):
        raise ValueError("Report target sourceDigest is missing or invalid.")
    if not isinstance(scan_result, dict) or scan_result.get("readOnly") is not True:
        raise ValueError("Report does not preserve the read-only scan assertion.")
    if not isinstance(scan_result.get("reason"), str) or not scan_result["reason"].strip():
        raise ValueError("Report scan reason is missing or invalid.")
    for field in ("filesExamined", "uiFilesExamined", "rulesEvaluated"):
        if not _is_nonnegative_int(scan_result.get(field)):
            raise ValueError(f"Report scan {field} is missing or invalid.")
    review = report.get("review")
    if not isinstance(review, dict):
        raise ValueError("Report review metadata is missing or invalid.")
    if not isinstance(review.get("policy"), str) or not review["policy"].strip():
        raise ValueError("Report review policy is missing or invalid.")
    if "reviewer" in review and (
        not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip()
    ):
        raise ValueError("Report reviewer is invalid.")
    if not isinstance(limitations, list) or not limitations or any(
        not isinstance(item, str) or not item.strip() for item in limitations
    ):
        raise ValueError("Report limitations are missing or invalid.")
    _validated_hosted_repository_source(report)

    confirmed = _validated_finalized_tells(report)
    _validate_rescan_shape(report)
    if len(confirmed) != report["summary"]["confirmedCount"]:
        raise ValueError("Report confirmed count is inconsistent.")


def _rescan_summary(
    baseline: dict[str, object],
    current: dict[str, object],
) -> dict[str, object]:
    validate_final_report(baseline)
    validate_final_report(current)
    baseline_tells = _validated_finalized_tells(baseline)
    current_tells = _validated_finalized_tells(current)
    baseline_target = baseline.get("target")
    current_target = current.get("target")
    baseline_tool = baseline.get("tool")
    current_tool = current.get("tool")
    if (
        not isinstance(baseline_target, dict)
        or not isinstance(current_target, dict)
        or not isinstance(baseline_tool, dict)
        or not isinstance(current_tool, dict)
    ):
        raise ValueError("Baseline is not a finalized ats-1 report.")
    if baseline_target.get("targetId") != current_target.get("targetId"):
        raise ValueError("Baseline and current report targetId values do not match.")
    if baseline_tool.get("name") != current_tool.get("name") or baseline_tool.get(
        "version"
    ) != current_tool.get("version"):
        raise ValueError("Baseline and current report tool versions do not match.")
    baseline_repository = _validated_hosted_repository_source(baseline)
    current_repository = _validated_hosted_repository_source(current)
    if baseline_repository != current_repository:
        raise ValueError(
            "Baseline and current hosted repository.source values do not match."
        )
    old = {_tell_key(item): item for item in baseline_tells if isinstance(item, dict)}
    new = {_tell_key(item): item for item in current_tells}
    return {
        "baselineSourceDigest": baseline_target.get("sourceDigest"),
        "resolved": [old[key] for key in sorted(set(old) - set(new))],
        "persisted": [new[key] for key in sorted(set(old) & set(new))],
        "introduced": [new[key] for key in sorted(set(new) - set(old))],
    }


def finalize(
    candidate_report: dict[str, object],
    review: dict[str, object],
    baseline: dict[str, object] | None = None,
) -> dict[str, object]:
    if candidate_report.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("Candidate report is not ats-1.")
    if review.get("schemaVersion") != "ats-review-1":
        raise ValueError("Review file is not ats-review-1.")
    if review.get("candidateSetDigest") != candidate_report.get("candidateSetDigest"):
        raise ValueError("Review does not match this candidate set digest.")
    target = candidate_report.get("target")
    tool = candidate_report.get("tool")
    if not isinstance(target, dict) or not isinstance(tool, dict):
        raise ValueError("Candidate report target/tool binding is malformed.")
    if tool.get("name") != "ai-tell-scan":
        raise ValueError("Candidate report tool name is not ai-tell-scan.")
    if review.get("sourceDigest") != target.get("sourceDigest"):
        raise ValueError("Review does not match this source digest.")
    if review.get("targetId") != target.get("targetId"):
        raise ValueError("Review does not match this target id.")
    if review.get("toolName") != tool.get("name"):
        raise ValueError("Review does not match this tool name.")
    if review.get("toolVersion") != tool.get("version"):
        raise ValueError("Review does not match this tool version.")
    candidates = candidate_report.get("candidates")
    decisions = review.get("decisions")
    if not isinstance(candidates, list) or not isinstance(decisions, list):
        raise ValueError("Candidate report or review decisions are malformed.")
    if candidate_set_digest(candidates) != candidate_report.get("candidateSetDigest"):
        raise ValueError(
            "Candidate report contents do not match its candidate set digest."
        )

    if not candidates:
        if decisions:
            raise ValueError(
                "Review contains decisions, but the candidate report is empty."
            )
        result = json.loads(json.dumps(candidate_report))
        if baseline is not None:
            result["rescan"] = _rescan_summary(baseline, result)
        validate_final_report(result)
        return result

    candidate_by_id: dict[str, dict[str, object]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict) or not isinstance(
            candidate.get("candidateId"), str
        ):
            raise ValueError("Candidate report contains an invalid candidate.")
        _validate_candidate_core(candidate)
        if candidate["candidateId"] in candidate_by_id:
            raise ValueError(
                f"Candidate report contains duplicate identity {candidate['candidateId']}."
            )
        candidate_by_id[candidate["candidateId"]] = candidate
    decision_by_id: dict[str, dict[str, object]] = {}
    for decision in decisions:
        if not isinstance(decision, dict) or not isinstance(
            decision.get("candidateId"), str
        ):
            raise ValueError("Review contains an invalid decision.")
        candidate_id = decision["candidateId"]
        if candidate_id in decision_by_id:
            raise ValueError(f"Duplicate review decision for {candidate_id}.")
        if candidate_id not in candidate_by_id:
            raise ValueError(f"Review references unknown candidate {candidate_id}.")
        disposition = decision.get("disposition")
        rationale = decision.get("rationale")
        if disposition not in {"confirmed", "rejected"}:
            raise ValueError(
                f"Decision for {candidate_id} must be confirmed or rejected."
            )
        if not isinstance(rationale, str) or len(rationale.strip()) < 12:
            raise ValueError(
                f"Decision for {candidate_id} needs a context-specific rationale."
            )
        decision_by_id[candidate_id] = decision
    missing = sorted(set(candidate_by_id) - set(decision_by_id))
    if missing:
        raise ValueError(f"Review is missing decisions for: {', '.join(missing)}")

    reviewed_candidates: list[dict[str, object]] = []
    confirmed: list[dict[str, object]] = []
    for candidate in candidates:
        candidate_id = str(candidate["candidateId"])
        decision = decision_by_id[candidate_id]
        reviewed = dict(candidate)
        reviewed["disposition"] = decision["disposition"]
        reviewed["reviewRationale"] = decision["rationale"]
        reviewed_candidates.append(reviewed)
        if decision["disposition"] == "confirmed":
            tell = {
                key: value for key, value in reviewed.items() if key != "disposition"
            }
            confirmed.append(tell)

    confirmed.sort(key=_tell_sort_key)
    tells = confirmed[:3]
    result = json.loads(json.dumps(candidate_report))
    result["scan"]["status"] = "completed"
    result["scan"]["reason"] = (
        "Context review completed. Only the highest-confidence three confirmed tells are reported."
    )
    result["summary"] = {
        "candidateCount": len(candidates),
        "confirmedCount": len(confirmed),
        "rejectedCount": len(candidates) - len(confirmed),
        "reportedCount": len(tells),
        "suppressedConfirmedCount": max(0, len(confirmed) - len(tells)),
    }
    result["review"] = {
        "state": "complete",
        "reviewer": review.get("reviewer", "agent"),
        "policy": "Confirmed only after visible page/component context review; no authorship inference.",
    }
    result["candidates"] = reviewed_candidates
    result["tells"] = tells

    if baseline is not None:
        result["rescan"] = _rescan_summary(baseline, result)
    validate_final_report(result)
    return result


def validate_source_root(
    candidate_report: dict[str, object], root: Path, max_files: int = 5000
) -> Path:
    resolved = root.expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError(f"Target source root is not a directory: {resolved}")
    target = candidate_report.get("target")
    if not isinstance(target, dict) or not isinstance(target.get("sourceDigest"), str):
        raise ValueError("Candidate report has no source digest to bind the target.")
    files = read_sources(resolved, max_files=max_files)
    if source_digest(files) != target["sourceDigest"]:
        raise ValueError(
            "Target source no longer matches the candidate report; scan and review it again."
        )
    return resolved


def path_is_within(path: Path, parent: Path) -> bool:
    resolved_path = path.expanduser().resolve()
    resolved_parent = parent.expanduser().resolve()
    current = resolved_path
    while True:
        try:
            if os.path.samefile(current, resolved_parent):
                return True
        except OSError:
            pass
        if current.parent == current:
            return False
        current = current.parent


def validate_new_output_path(
    output: Path, forbidden_root: Path | None = None
) -> Path:
    expanded = output.expanduser()
    if os.path.lexists(expanded):
        raise ValueError(f"Refusing to overwrite existing artifact path: {expanded}")
    resolved = expanded.resolve(strict=False)
    if forbidden_root is not None and path_is_within(resolved, forbidden_root):
        raise ValueError(
            "Refusing to write scan artifacts inside the repository being scanned."
        )
    return resolved


def write_text(
    payload: str, output: Path, forbidden_root: Path | None = None
) -> None:
    resolved = validate_new_output_path(output, forbidden_root)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(resolved, flags, 0o600)
    except FileExistsError as error:
        raise ValueError(
            f"Refusing to overwrite existing artifact path: {resolved}"
        ) from error
    except OSError as error:
        raise ValueError(f"Could not create artifact {resolved}: {error}") from error
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(payload)


def write_json(
    value: object, output: Path | None, forbidden_root: Path | None = None
) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    if output is None:
        print(payload, end="")
        return
    write_text(payload, output, forbidden_root)


def load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read JSON from {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return value
