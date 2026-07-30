#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# ruff: noqa: S607
"""Validate documentation structure for the Beads documentation-first workflow.

Default mode enforces the current workflow. ``--migration-mode`` keeps broken
links and unsafe navigation as errors but reports legacy ``tasks.md`` files,
include-based feature pages, and pre-template design headings as warnings while
an existing project is being migrated.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path


DESIGN_HEADINGS = (
    "Feature Summary",
    "User Intent",
    "Goals",
    "Non-Goals",
    "User-Facing Behavior",
    "Requirements",
    "Existing Context",
    "Proposed Design",
    "Architecture Consistency",
    "Operational Considerations",
    "Documentation Impact",
    "Validation Strategy",
    "Implementation Decomposition",
    "Dependencies and Parallelism",
    "Risks and Tradeoffs",
    "Open Questions",
)

IMPLEMENTED_HEADINGS = (
    "Delivery Summary",
    "Delivered Capability",
    "User-Facing Behavior",
    "Design Integration",
    "Operational Impact",
    "Reference and Contracts",
    "Validation Evidence",
    "Design Reconciliation",
    "Documentation Updated",
    "Audit Trail",
)

FEATURE_DIR_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LEGACY_FEATURE_DIR_RE = re.compile(r"^[0-9]{3,}-[a-z0-9]+(?:-[a-z0-9]+)*$")
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
LINK_DEFINITION_RE = re.compile(r"^\s{0,3}\[([^\]]+)\]:\s*(.+?)\s*$", re.MULTILINE)
REFERENCE_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\[([^\]]*)\]")
IMAGE_REFERENCE_RE = re.compile(r"!\[[^\]]+\]\[[^\]]*\]")
SHORTCUT_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\](?![\[(])")
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
SUMMARY_START = "<!-- BEGIN IMPLEMENTED FEATURES -->"
SUMMARY_END = "<!-- END IMPLEMENTED FEATURES -->"
MIGRATION_MARKER = "<!-- workflow-migration:legacy-markdown-to-beads -->"


@dataclass(frozen=True, slots=True)
class Finding:
    severity: str
    code: str
    path: str
    message: str


def repository_root(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return Path(__file__).resolve().parents[1]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def link_target(raw: str) -> str:
    target = raw.strip()
    target = target[1 : target.index(">")] if target.startswith("<") and ">" in target else target.split(maxsplit=1)[0]
    return target.split("#", 1)[0]


def local_links(markdown: str) -> list[str]:
    definitions: dict[str, str] = {}
    for label, raw in LINK_DEFINITION_RE.findall(markdown):
        definitions.setdefault(re.sub(r"\s+", " ", label.strip()).casefold(), link_target(raw))
    body = LINK_DEFINITION_RE.sub("", markdown)
    raw_targets = list(LINK_RE.findall(body))
    raw_targets.extend(
        definitions.get(re.sub(r"\s+", " ", (label or text).strip()).casefold(), "")
        for text, label in REFERENCE_LINK_RE.findall(body)
    )
    shortcut_body = REFERENCE_LINK_RE.sub("", IMAGE_REFERENCE_RE.sub("", body))
    raw_targets.extend(
        definitions.get(re.sub(r"\s+", " ", label.strip()).casefold(), "")
        for label in SHORTCUT_LINK_RE.findall(shortcut_body)
    )
    targets = (
        target
        for raw in raw_targets
        if raw and (target := link_target(raw)) and not target.startswith(("http://", "https://", "mailto:", "tel:"))
    )
    return list(dict.fromkeys(targets))


def normalize_heading(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().rstrip("#").strip()).casefold()


def headings(markdown: str) -> set[str]:
    return {normalize_heading(match) for match in HEADING_RE.findall(markdown)}


def add(
    findings: list[Finding],
    *,
    severity: str,
    code: str,
    path: Path | str,
    message: str,
    root: Path,
) -> None:
    display = str(path.relative_to(root)) if isinstance(path, Path) and path.is_absolute() else str(path)
    findings.append(Finding(severity, code, display, message))


def marked_region(
    markdown: str,
    *,
    path: Path,
    root: Path,
    findings: list[Finding],
    migration_mode: bool,
) -> str:
    start_count = markdown.count(SUMMARY_START)
    end_count = markdown.count(SUMMARY_END)
    if start_count != 1 or end_count != 1:
        add(
            findings,
            severity="warning" if migration_mode else "error",
            code="invalid-implemented-feature-markers",
            path=path,
            message="Expected exactly one BEGIN and one END IMPLEMENTED FEATURES marker",
            root=root,
        )
        return ""
    start = markdown.index(SUMMARY_START) + len(SUMMARY_START)
    end = markdown.index(SUMMARY_END)
    if start > end:
        add(
            findings,
            severity="error",
            code="reversed-implemented-feature-markers",
            path=path,
            message="BEGIN IMPLEMENTED FEATURES must appear before END IMPLEMENTED FEATURES",
            root=root,
        )
        return ""
    return markdown[start:end]


def validate_links(root: Path, markdown_files: Iterable[Path], published_files: set[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for source in markdown_files:
        text = read_text(source)
        for target in local_links(text):
            resolved = (source.parent / target).resolve()
            if not resolved.exists():
                add(
                    findings,
                    severity="error",
                    code="broken-link",
                    path=source,
                    message=f"Link target does not exist: {target}",
                    root=root,
                )
            elif source.resolve() in published_files and resolved.suffix == ".md" and resolved not in published_files:
                add(
                    findings,
                    severity="error",
                    code="unpublished-page-link",
                    path=source,
                    message=f"Published reader page links to an unpublished Markdown page: {target}",
                    root=root,
                )
    return findings


def validate_summary(root: Path, *, migration_mode: bool) -> tuple[list[Finding], set[Path]]:
    findings: list[Finding] = []
    summary_path = root / "docs/src/SUMMARY.md"
    if not summary_path.exists():
        add(
            findings,
            severity="error",
            code="missing-summary",
            path=summary_path,
            message="docs/src/SUMMARY.md is required",
            root=root,
        )
        return findings, set()

    summary = read_text(summary_path)
    target_paths: set[Path] = set()
    for target in local_links(summary):
        target_paths.add((summary_path.parent / target).resolve())
        if target.endswith("tasks.md"):
            add(
                findings,
                severity="warning" if migration_mode else "error",
                code="task-file-in-summary",
                path=summary_path,
                message=f"Legacy task tracker must not be a reader-facing chapter: {target}",
                root=root,
            )

    marked_region(
        summary,
        path=summary_path,
        root=root,
        findings=findings,
        migration_mode=migration_mode,
    )
    return findings, target_paths


def validate_feature_files(root: Path, *, migration_mode: bool) -> list[Finding]:
    findings: list[Finding] = []
    features_dir = root / "docs/src/features"
    if not features_dir.exists():
        add(
            findings,
            severity="error",
            code="missing-features-directory",
            path=features_dir,
            message="docs/src/features is required",
            root=root,
        )
        return findings

    summary_path = root / "docs/src/SUMMARY.md"
    feature_index_path = features_dir / "index.md"
    summary = read_text(summary_path) if summary_path.exists() else ""
    feature_index = read_text(feature_index_path) if feature_index_path.exists() else ""
    summary_region = (
        marked_region(
            summary,
            path=summary_path,
            root=root,
            findings=findings,
            migration_mode=migration_mode,
        )
        if summary
        else ""
    )
    index_region = (
        marked_region(
            feature_index,
            path=feature_index_path,
            root=root,
            findings=findings,
            migration_mode=migration_mode,
        )
        if feature_index
        else ""
    )

    summary_targets = {(summary_path.parent / target).resolve() for target in local_links(summary_region)}
    index_targets = {(feature_index_path.parent / target).resolve() for target in local_links(index_region)}

    for directory in sorted(path for path in features_dir.iterdir() if path.is_dir() and not path.name.startswith("_")):
        if FEATURE_DIR_RE.fullmatch(directory.name) is None:
            severity = "warning" if migration_mode and LEGACY_FEATURE_DIR_RE.fullmatch(directory.name) else "error"
            add(
                findings,
                severity=severity,
                code="invalid-feature-directory",
                path=directory,
                message="Feature directory must use <slug>",
                root=root,
            )

        design = directory / "design.md"
        tasks = directory / "tasks.md"
        implemented = directory / "index.md"

        if not design.exists():
            add(
                findings,
                severity="error",
                code="missing-feature-design",
                path=directory,
                message="Feature directory must contain design.md",
                root=root,
            )
        else:
            design_text = read_text(design)
            present = headings(design_text)
            missing = [heading for heading in DESIGN_HEADINGS if normalize_heading(heading) not in present]
            if missing:
                add(
                    findings,
                    severity=("warning" if migration_mode or MIGRATION_MARKER in design_text else "error"),
                    code="legacy-or-incomplete-design",
                    path=design,
                    message="Missing current design sections: " + ", ".join(missing),
                    root=root,
                )

        if tasks.exists():
            add(
                findings,
                severity="warning" if migration_mode else "error",
                code="legacy-task-file",
                path=tasks,
                message="tasks.md is migration input only; Beads owns active task state",
                root=root,
            )

        if not implemented.exists():
            continue

        implemented_text = read_text(implemented)
        if "{{#include tasks.md}}" in implemented_text:
            add(
                findings,
                severity="warning" if migration_mode else "error",
                code="implemented-record-includes-tasks",
                path=implemented,
                message="Implemented-feature record must not embed legacy tasks.md",
                root=root,
            )
        if "{{#include design.md}}" in implemented_text:
            add(
                findings,
                severity="warning" if migration_mode else "error",
                code="implemented-record-includes-design",
                path=implemented,
                message="Implemented-feature record must stand alone instead of embedding design.md",
                root=root,
            )
        present = headings(implemented_text)
        missing = [heading for heading in IMPLEMENTED_HEADINGS if normalize_heading(heading) not in present]
        if missing:
            add(
                findings,
                severity=("warning" if migration_mode or MIGRATION_MARKER in implemented_text else "error"),
                code="legacy-or-incomplete-implemented-record",
                path=implemented,
                message="Missing current implemented-feature sections: " + ", ".join(missing),
                root=root,
            )

        resolved = implemented.resolve()
        if resolved not in summary_targets:
            add(
                findings,
                severity="warning" if migration_mode else "error",
                code="implemented-feature-not-in-summary",
                path=implemented,
                message="Delivered feature page is not in the implemented-feature region of SUMMARY.md",
                root=root,
            )
        if feature_index_path.exists() and resolved not in index_targets:
            add(
                findings,
                severity="warning" if migration_mode else "error",
                code="implemented-feature-not-in-index",
                path=implemented,
                message="Delivered feature page is not in the marked region of docs/src/features/index.md",
                root=root,
            )

    return findings


def validate(root: Path, *, migration_mode: bool) -> list[Finding]:
    findings, published_files = validate_summary(root, migration_mode=migration_mode)
    findings.extend(validate_feature_files(root, migration_mode=migration_mode))
    docs_src = root / "docs/src"
    markdown_files = sorted(docs_src.rglob("*.md")) if docs_src.exists() else []
    findings.extend(validate_links(root, markdown_files, published_files))
    return findings


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="Repository root; defaults to git root")
    parser.add_argument("--migration-mode", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = repository_root(args.root)
    findings = validate(root, migration_mode=args.migration_mode)
    errors = [finding for finding in findings if finding.severity == "error"]
    warnings = [finding for finding in findings if finding.severity == "warning"]

    if args.json:
        print(json.dumps([asdict(finding) for finding in findings], indent=2, sort_keys=True))
    else:
        for finding in findings:
            print(f"{finding.severity.upper()} [{finding.code}] {finding.path}: {finding.message}")
        if not findings:
            print("Documentation checks passed.")
        else:
            print(f"Documentation checks: {len(errors)} errors, {len(warnings)} warnings.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
