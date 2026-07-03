"""Manifest-driven loader for the auditable migration knowledge base.

The repository separates concrete mapping facts from reusable rules:

* ``mappings/`` records concrete CCCL -> ASC names, include forms, path segments,
  and API tables.
* ``rules/`` records reusable matching/decision logic such as syntax rewrites,
  constraints, implicit-dependency discovery, and migration policy.

``reference/manifest.yaml`` is the only file that knows where those datasets
live.  A legacy three-file layout is still accepted for small external fixtures
and older tests, but the project itself uses the manifest layout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ReferenceBundle:
    reference_dir: Path
    mappings: list[dict] = field(default_factory=list)
    rules: dict[str, list[dict]] = field(default_factory=dict)
    segment_substitutions: list[dict] = field(default_factory=list)
    migration_policy: dict = field(default_factory=dict)
    catalogs: dict[str, dict] = field(default_factory=dict)
    layout: str = "empty"

    def rules_of(self, kind: str) -> list[dict]:
        return list(self.rules.get(kind, []))


def _read_yaml(path: Path, *, strict: bool) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        if strict:
            raise ValueError(f"无法读取 reference 文件: {path}") from exc
        return None
    except yaml.YAMLError as exc:
        if strict:
            raise ValueError(f"reference 文件不是合法 YAML: {path}") from exc
        return None


def _records(doc: Any) -> list[dict]:
    return [dict(item) for item in doc if isinstance(item, dict)] if isinstance(doc, list) else []


def _manifest_path(root: Path, value: object, *, strict: bool) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        if strict:
            raise ValueError("reference/manifest.yaml 中的 file 必须是非空字符串")
        return None
    root_resolved = root.resolve()
    path = (root / value).resolve()
    try:
        path.relative_to(root_resolved)
    except ValueError as exc:
        if strict:
            raise ValueError(f"reference manifest 路径越界: {value}") from exc
        return None
    return path


def _load_manifest_layout(root: Path, manifest: dict, *, strict: bool) -> ReferenceBundle:
    mappings: list[dict] = []
    rules: dict[str, list[dict]] = {}
    catalogs: dict[str, dict] = {}

    for spec in manifest.get("mapping_sets", []) or []:
        if not isinstance(spec, dict):
            continue
        path = _manifest_path(root, spec.get("file"), strict=strict)
        if path is None:
            continue
        rows = _records(_read_yaml(path, strict=strict))
        mapping_kind = str(spec.get("kind") or spec.get("id") or "mapping")
        for row in rows:
            row.setdefault("mapping_kind", mapping_kind)
        if spec.get("inject", True):
            mappings.extend(rows)
        else:
            catalogs[str(spec.get("id") or mapping_kind)] = {
                "kind": mapping_kind,
                "path": str(path),
                "records": rows,
            }

    # Catalogs are registered but intentionally lazy: loading 1000+ API rows on
    # every header migration would add latency and prompt noise. A future API
    # query layer can load the declared path on demand.
    for spec in manifest.get("catalog_sets", []) or []:
        if not isinstance(spec, dict):
            continue
        path = _manifest_path(root, spec.get("file"), strict=strict)
        if path is None:
            continue
        catalog_id = str(spec.get("id") or spec.get("kind") or path.stem)
        catalogs[catalog_id] = {
            "kind": str(spec.get("kind") or "catalog"),
            "path": str(path),
        }

    for spec in manifest.get("rule_sets", []) or []:
        if not isinstance(spec, dict):
            continue
        path = _manifest_path(root, spec.get("file"), strict=strict)
        if path is None:
            continue
        kind = str(spec.get("kind") or spec.get("id") or "generic")
        rows = _records(_read_yaml(path, strict=strict))
        for row in rows:
            row.setdefault("rule_kind", kind)
        rules.setdefault(kind, []).extend(rows)

    strategy = manifest.get("strategy") or {}
    if not isinstance(strategy, dict):
        if strict:
            raise ValueError("reference/manifest.yaml 的 strategy 必须是 mapping")
        strategy = {}

    segment_path = _manifest_path(root, strategy.get("segment_substitutions"), strict=strict)
    policy_path = _manifest_path(root, strategy.get("migration_policy"), strict=strict)
    segments = _records(_read_yaml(segment_path, strict=strict)) if segment_path else []
    policy_doc = _read_yaml(policy_path, strict=strict) if policy_path else {}
    policy = dict(policy_doc) if isinstance(policy_doc, dict) else {}

    if strict and not segments:
        raise ValueError("reference manifest 必须提供非空 segment_substitutions")
    if strict and not isinstance(policy_doc, dict):
        raise ValueError("reference manifest 的 migration_policy 文件顶层必须是 mapping")

    return ReferenceBundle(
        reference_dir=root,
        mappings=mappings,
        rules=rules,
        segment_substitutions=segments,
        migration_policy=policy,
        catalogs=catalogs,
        layout="manifest-v2",
    )


def _load_legacy_layout(root: Path, *, strict: bool) -> ReferenceBundle:
    """Compatibility loader for the historical three-file layout."""
    symbol_path = root / "symbol_mapping.yaml"
    if not symbol_path.is_file():
        return ReferenceBundle(reference_dir=root)
    symbol_doc = _read_yaml(symbol_path, strict=strict)
    symbol_doc = symbol_doc if isinstance(symbol_doc, dict) else {}
    grammar = _records(_read_yaml(root / "grammar_rules.yaml", strict=False))
    constraints = _records(_read_yaml(root / "constraint_rules.yaml", strict=False))
    implicit = _records(symbol_doc.get("symbol_dependencies"))
    rules = {
        "grammar": grammar,
        "constraint": constraints,
        "implicit_dependency": implicit,
    }
    return ReferenceBundle(
        reference_dir=root,
        mappings=_records(symbol_doc.get("symbols")),
        rules=rules,
        segment_substitutions=_records(symbol_doc.get("segment_substitutions")),
        migration_policy=dict(symbol_doc.get("migration_policy") or {}),
        layout="legacy-v1",
    )


def load_reference_bundle(reference_dir: str | Path, *, strict: bool = False) -> ReferenceBundle:
    root = Path(reference_dir)
    manifest_path = root / "manifest.yaml"
    if manifest_path.is_file():
        doc = _read_yaml(manifest_path, strict=strict)
        if not isinstance(doc, dict):
            if strict:
                raise ValueError("reference/manifest.yaml 顶层必须是 mapping")
            return ReferenceBundle(reference_dir=root)
        return _load_manifest_layout(root, doc, strict=strict)
    return _load_legacy_layout(root, strict=strict)
