from __future__ import annotations

import json
import re

import pytest

from core.api_mapping.pipeline import (
    ApiMappingOptions,
    ApiMappingPipeline,
    _SourceShard,
    _candidate_anchors,
    _deduplicate_apis,
    _locally_declared_names,
    _skill_hash_is_compatible,
    _split_source,
    _validate_extraction,
)


def _marker(text: str, name: str):
    match = re.search(rf"^{re.escape(name)}\s*(.+)$", text, re.MULTILINE)
    assert match
    return json.loads(match.group(1))


class MappingModel:
    def __init__(self):
        self.calls = []

    def generate(self, *, system_prompt, user_content, on_delta=None):
        self.calls.append(user_content)
        if "STAGE: source_api_extraction" in user_content:
            candidates = _marker(user_content, "CANDIDATES_JSON:")
            foo = next(row for row in candidates if row["name_hint"] == "::foo")
            coverage = []
            for row in candidates:
                is_foo = row["candidate_id"] == foo["candidate_id"]
                coverage.append({
                    "candidate_id": row["candidate_id"],
                    "disposition": "api" if is_foo else "non_api",
                    "api_ids": ["local-foo"] if is_foo else [],
                    "reason": "declaration" if is_foo else "scanner false positive",
                })
            return json.dumps({
                "apis": [{
                    "api_id": "local-foo",
                    "name": "::foo",
                    "unqualified_name": "foo",
                    "kind": "function",
                    "origin": "referenced",
                    "signature": "::foo(value)",
                    "source_line_start": foo["line"],
                    "source_line_end": foo["line"],
                    "device_support": "host_device",
                    "visibility": "public",
                    "summary": "返回输入值。",
                    "evidence": "return ::foo(value);",
                    "candidate_ids": [foo["candidate_id"]],
                }],
                "coverage": coverage,
                "chunk_notes": "",
            })
        apis = _marker(user_content, "SOURCE_APIS_JSON:")
        return json.dumps({"mappings": [{
            "source_api_id": api["source_api_id"],
            "accl_apis": ["foo"],
            "match_status": "exact",
            "doc_paths": ["数学函数/foo.md"],
            "doc_evidence": ["foo 返回输入参数。"],
            "mapping_notes": "语义一致。",
            "function_summary": "返回输入值。",
        } for api in apis]})


def _fixture(tmp_path):
    source = tmp_path / "include" / "cuda"
    (source / "std" / "__demo").mkdir(parents=True)
    (source / "std" / "__demo" / "foo.h").write_text(
        "#define API_MARKER 1\nnamespace cuda {\n_CCCL_API int wrapper(int value) { return ::foo(value); }\n}\n",
        encoding="utf-8",
    )
    docs = tmp_path / "docs"
    (docs / "数学函数").mkdir(parents=True)
    (docs / "数学函数" / "foo.md").write_text(
        "# foo\n\n`foo(int value)` 返回输入参数。\n",
        encoding="utf-8",
    )
    skill = tmp_path / "SKILL.md"
    skill.write_text("Map APIs and return JSON.", encoding="utf-8")
    return source, docs, skill


def test_source_split_covers_all_lines_with_overlap():
    text = "".join(f"line-{i:03d}\n" for i in range(50))
    shards = _split_source(text, max_chars=80, overlap_lines=2)

    assert len(shards) > 1
    assert shards[0].start_line == 1
    assert shards[-1].end_line == 50
    assert all(right.start_line <= left.end_line for left, right in zip(shards, shards[1:]))


def test_scope_only_skill_revision_keeps_legacy_checkpoints_compatible():
    legacy = "11cf069e2857ebfdb742edf3292e31ce0d9bebc803f15b0c39564055328440bb"
    assert _skill_hash_is_compatible(legacy, "new-skill-hash")
    assert _skill_hash_is_compatible("same", "same")
    assert not _skill_hash_is_compatible("unrelated", "new-skill-hash")


def test_candidate_anchors_include_api_shapes_but_exclude_macros_and_control_flow():
    candidates = _candidate_anchors(
        "#define FLAG 1\nstruct item {};\nusing alias = int;\nint foo(int x);\nif (x) {}\n",
        1,
        1,
    )
    pairs = {(row["kind_hint"], row["name_hint"]) for row in candidates}

    assert ("macro", "FLAG") not in pairs
    assert ("type", "item") in pairs
    assert ("alias", "alias") in pairs
    assert ("function", "foo") in pairs
    ref_candidates = _candidate_anchors("return ::__brevll(value);\n", 1, 1)
    brevll = next(row for row in ref_candidates if row["name_hint"] == "::__brevll")
    assert brevll["kind_hint"] == "api_reference"
    assert brevll["must_be_api"] is True
    assert not any(name == "if" for _, name in pairs)
    package_refs = {
        row["name_hint"]: row
        for row in _candidate_anchors(
            "auto a = ::cuda::std::forward<T>(x); auto b = ::cuda::neg(i); auto c = ::__half{};\n",
            1,
            1,
        )
        if row["kind_hint"] == "api_reference"
    }
    assert package_refs["::cuda::std::forward"]["must_be_api"] is False
    assert package_refs["::cuda::std::forward"]["scope_hint"] == "package_internal_dependency"
    assert package_refs["::cuda::neg"]["must_be_api"] is False
    assert package_refs["::__half"]["must_be_api"] is True
    inherited = _candidate_anchors("using base<T>::__base;\n", 1, 1)
    assert not any(row["kind_hint"] == "api_reference" for row in inherited)


def test_pipeline_maps_api_and_resumes_without_model_calls(tmp_path):
    source, docs, skill = _fixture(tmp_path)
    options = ApiMappingOptions(
        source_root=source,
        docs_root=docs,
        output_dir=tmp_path / "out",
        skill_path=skill,
        save_model_io=True,
    )
    model = MappingModel()
    pipeline = ApiMappingPipeline(options, model, model_name="test-model")

    first = pipeline.run()
    assert first["completed_files"] == 1
    assert first["api_count"] == 1
    assert first["match_counts"] == {"exact": 1}
    assert len(model.calls) == 2
    report = json.loads((tmp_path / "out" / "api_mapping.json").read_text(encoding="utf-8"))
    api = report["results"][0]["apis"][0]
    assert api["name"] == "foo"
    assert api["accl_apis"] == ["foo"]
    assert api["doc_paths"] == ["数学函数/foo.md"]
    markdown = (tmp_path / "out" / "api_mapping.md").read_text(encoding="utf-8")
    assert markdown.startswith("| CCCL 侧 API | 来源头文件 |")
    assert "<sub>" not in markdown
    assert "文件覆盖与异常" not in markdown

    # Scope filters must clean aggregate reports without mutating or
    # invalidating the resumable per-file checkpoint.
    result_path = next((tmp_path / "out" / "files").glob("*.json"))
    checkpoint = json.loads(result_path.read_text(encoding="utf-8"))
    checkpoint["apis"].extend([
        {**api, "name": "cudaSuccess", "unqualified_name": "cudaSuccess", "kind": "variable", "signature": "::cudaSuccess"},
        {**api, "name": "max", "unqualified_name": "max", "signature": "::cuda::std::numeric_limits<T>::max()"},
        {**api, "name": "cudaStream_t", "unqualified_name": "cudaStream_t", "kind": "type", "signature": "::cudaStream_t", "device_support": "host_only"},
        {**api, "name": "cudaAccessProperty", "unqualified_name": "cudaAccessProperty", "kind": "type", "signature": "::cudaAccessProperty", "device_support": "host_device"},
    ])
    checkpoint["api_count"] = len(checkpoint["apis"])
    result_path.write_text(json.dumps(checkpoint), encoding="utf-8")

    second = pipeline.run()
    assert second["resumed"] == 1
    assert second["api_count"] == 1
    assert len(model.calls) == 2
    report = json.loads((tmp_path / "out" / "api_mapping.json").read_text(encoding="utf-8"))
    assert [row["name"] for row in report["results"][0]["apis"]] == ["foo"]
    raw_checkpoint = json.loads(result_path.read_text(encoding="utf-8"))
    assert {row["name"] for row in raw_checkpoint["apis"]} == {
        "foo", "cudaSuccess", "max", "cudaStream_t", "cudaAccessProperty"
    }


def test_pipeline_rejects_unread_document_citation(tmp_path):
    source, docs, skill = _fixture(tmp_path)

    class BadModel(MappingModel):
        def generate(self, **kwargs):
            raw = super().generate(**kwargs)
            if "STAGE: documentation_mapping" in kwargs["user_content"]:
                obj = json.loads(raw)
                obj["mappings"][0]["doc_paths"] = ["不存在.md"]
                return json.dumps(obj)
            return raw

    options = ApiMappingOptions(
        source_root=source,
        docs_root=docs,
        output_dir=tmp_path / "out",
        skill_path=skill,
        model_retries=0,
    )
    summary = ApiMappingPipeline(options, BadModel(), model_name="test-model").run()

    assert summary["failed_files"] == 1
    result = json.loads(next((tmp_path / "out" / "files").glob("*.json")).read_text(encoding="utf-8"))
    assert "未作为该 API 候选提供给模型" in result["error"]


def test_options_reject_missing_document_root(tmp_path):
    source, _, skill = _fixture(tmp_path)
    with pytest.raises(FileNotFoundError, match="文档目录不存在"):
        ApiMappingPipeline(
            ApiMappingOptions(source, tmp_path / "missing", tmp_path / "out", skill),
            MappingModel(),
        )


def test_zero_match_filter_fails_with_path_suggestion_without_writing_reports(tmp_path):
    source, docs, skill = _fixture(tmp_path)
    options = ApiMappingOptions(
        source_root=source,
        docs_root=docs,
        output_dir=tmp_path / "out",
        skill_path=skill,
        include=("std/wrong/foo.h",),
    )

    with pytest.raises(ValueError, match=r"筛选结果为 0.*std/__demo/foo\.h"):
        ApiMappingPipeline(options, MappingModel()).run()

    assert not (tmp_path / "out" / "api_mapping.md").exists()


def test_extraction_rejects_macro_internal_and_contradictory_non_api_records():
    shard = _SourceShard(1, 1, 1, "int helper();\n")
    base_api = {
        "api_id": "a1",
        "name": "helper",
        "unqualified_name": "helper",
        "kind": "function",
        "origin": "referenced",
        "signature": "int helper()",
        "source_line_start": 1,
        "source_line_end": 1,
        "device_support": "host_device",
        "visibility": "internal",
        "summary": "helper",
        "evidence": "int helper();",
        "candidate_ids": ["S0001-C0001"],
    }
    coverage = [{
        "candidate_id": "S0001-C0001",
        "disposition": "api",
        "api_ids": ["a1"],
        "reason": "declaration",
    }]
    with pytest.raises(ValueError, match="不是公开 API"):
        _validate_extraction({"apis": [base_api], "coverage": coverage}, {"S0001-C0001"}, shard)

    public_api = {**base_api, "visibility": "public"}
    contradictory = [{**coverage[0], "disposition": "non_api"}]
    with pytest.raises(ValueError, match="non_api"):
        _validate_extraction({"apis": [public_api], "coverage": contradictory}, {"S0001-C0001"}, shard)

    declared_api = {**public_api, "origin": "declared"}
    with pytest.raises(ValueError, match="origin 非法"):
        _validate_extraction({"apis": [declared_api], "coverage": coverage}, {"S0001-C0001"}, shard)

    package_internal = {**public_api, "name": "::cuda::std::forward", "unqualified_name": "forward"}
    with pytest.raises(ValueError, match="包内依赖"):
        _validate_extraction({"apis": [package_internal], "coverage": coverage}, {"S0001-C0001"}, shard)

    shortened_internal = {
        **public_api,
        "name": "max",
        "unqualified_name": "max",
        "signature": "::cuda::std::numeric_limits<T>::max()",
    }
    with pytest.raises(ValueError, match="签名属于 libcudacxx 包内依赖"):
        _validate_extraction({"apis": [shortened_internal], "coverage": coverage}, {"S0001-C0001"}, shard)

    enum_value = {
        **public_api,
        "name": "CU_MEMORYTYPE_HOST",
        "unqualified_name": "CU_MEMORYTYPE_HOST",
        "kind": "variable",
        "signature": "::CU_MEMORYTYPE_HOST",
    }
    with pytest.raises(ValueError, match="枚举值或状态常量"):
        _validate_extraction({"apis": [enum_value], "coverage": coverage}, {"S0001-C0001"}, shard)

    access_value = {
        **public_api,
        "name": "__host_device",
        "unqualified_name": "__host_device",
        "kind": "other",
        "signature": "::__host_device",
    }
    with pytest.raises(ValueError, match="内存可访问性枚举值"):
        _validate_extraction({"apis": [access_value], "coverage": coverage}, {"S0001-C0001"}, shard)

    ordinary_enum_value = {
        **public_api,
        "name": "cudaMemcpySrcAccessOrderStream",
        "unqualified_name": "cudaMemcpySrcAccessOrderStream",
        "kind": "variable",
        "signature": "::cudaMemcpySrcAccessOrderStream",
    }
    with pytest.raises(ValueError, match="普通常量或枚举值"):
        _validate_extraction({"apis": [ordinary_enum_value], "coverage": coverage}, {"S0001-C0001"}, shard)

    builtin_variable = {
        **public_api,
        "name": "threadIdx",
        "unqualified_name": "threadIdx",
        "kind": "variable",
        "signature": "::threadIdx",
    }
    validated = _validate_extraction({"apis": [builtin_variable], "coverage": coverage}, {"S0001-C0001"}, shard)
    assert validated["apis"][0]["name"] == "threadIdx"

    local_type = {
        **public_api,
        "name": "__deferred_base",
        "unqualified_name": "__deferred_base",
        "kind": "constructor",
        "signature": "__deferred_base<T>::__deferred_base",
    }
    with pytest.raises(ValueError, match="当前头文件自身声明/定义"):
        _validate_extraction(
            {"apis": [local_type], "coverage": coverage},
            {"S0001-C0001"},
            shard,
            {"__deferred_base"},
        )

    host_runtime_type = {
        **public_api,
        "name": "cudaStream_t",
        "unqualified_name": "cudaStream_t",
        "kind": "type",
        "signature": "::cudaStream_t",
        "device_support": "host_only",
    }
    with pytest.raises(ValueError, match="runtime/driver 句柄、配置或枚举类型"):
        _validate_extraction({"apis": [host_runtime_type], "coverage": coverage}, {"S0001-C0001"}, shard)

    runtime_enum_type = {
        **public_api,
        "name": "cudaAccessProperty",
        "unqualified_name": "cudaAccessProperty",
        "kind": "type",
        "signature": "::cudaAccessProperty",
        "device_support": "host_device",
    }
    with pytest.raises(ValueError, match="runtime/driver 句柄、配置或枚举类型"):
        _validate_extraction({"apis": [runtime_enum_type], "coverage": coverage}, {"S0001-C0001"}, shard)


def test_external_host_only_function_remains_an_api():
    shard = _SourceShard(1, 1, 1, "::__host_runtime_call();\n")
    candidates = [{
        "candidate_id": "S0001-C0001",
        "name_hint": "::__host_runtime_call",
        "must_be_api": True,
    }]
    api = {
        "api_id": "host-call",
        "name": "::__host_runtime_call",
        "unqualified_name": "__host_runtime_call",
        "kind": "function",
        "origin": "referenced",
        "signature": "::__host_runtime_call()",
        "source_line_start": 1,
        "source_line_end": 1,
        "device_support": "host_only",
        "visibility": "public",
        "summary": "host runtime call",
        "evidence": "::__host_runtime_call();",
        "candidate_ids": ["S0001-C0001"],
    }
    coverage = [{
        "candidate_id": "S0001-C0001",
        "disposition": "api",
        "api_ids": ["host-call"],
        "reason": "external host-only CUDA runtime function",
    }]

    validated = _validate_extraction({"apis": [api], "coverage": coverage}, candidates, shard)
    assert validated["apis"][0]["device_support"] == "host_only"

    coverage[0] = {**coverage[0], "disposition": "non_api", "api_ids": [], "reason": "host_only"}
    with pytest.raises(ValueError, match="必须进入 API 结果"):
        _validate_extraction({"apis": [], "coverage": coverage}, candidates, shard)


def test_report_accumulates_compatible_results_across_include_batches(tmp_path):
    source, docs, skill = _fixture(tmp_path)
    second = source / "__demo" / "foo.h"
    second.parent.mkdir(parents=True)
    second.write_text("_CCCL_API int wrapper(int value) { return ::foo(value); }\n", encoding="utf-8")
    output = tmp_path / "out"

    first_options = ApiMappingOptions(
        source_root=source,
        docs_root=docs,
        output_dir=output,
        skill_path=skill,
        include=("std/__demo/foo.h",),
    )
    first = ApiMappingPipeline(first_options, MappingModel(), model_name="test-model").run()
    assert first["selected_files"] == 1
    assert first["inventory_files"] == 2
    assert first["completed_files"] == 1

    second_options = ApiMappingOptions(
        source_root=source,
        docs_root=docs,
        output_dir=output,
        skill_path=skill,
        include=("__demo/foo.h",),
    )
    second_summary = ApiMappingPipeline(second_options, MappingModel(), model_name="test-model").run()
    assert second_summary["selected_files"] == 1
    assert second_summary["completed_files"] == 2
    report = json.loads((output / "api_mapping.json").read_text(encoding="utf-8"))
    assert {row["source_file"] for row in report["results"]} == {
        "std/__demo/foo.h",
        "__demo/foo.h",
    }
    inventory = json.loads((output / "source_inventory.json").read_text(encoding="utf-8"))
    assert inventory["file_count"] == 2
    assert inventory["selected_relative_paths"] == ["__demo/foo.h"]


def test_referenced_api_calls_are_deduplicated_with_all_occurrence_lines():
    common = {
        "api_id": "local",
        "name": "__brevll",
        "unqualified_name": "__brevll",
        "kind": "function",
        "origin": "referenced",
        "signature": "__brevll(value)",
        "source_line_end": 10,
        "device_support": "device",
        "visibility": "public",
        "summary": "反转64位整数位序",
        "evidence": "::__brevll(value)",
        "candidate_ids": ["S0001-C0001"],
        "source_shard": 1,
    }
    first = {**common, "source_line_start": 10}
    second = {
        **common,
        "api_id": "local-2",
        "source_line_start": 20,
        "source_line_end": 20,
        "candidate_ids": ["S0001-C0002"],
    }

    result = _deduplicate_apis([first, second])

    assert len(result) == 1
    assert result[0]["name"] == "__brevll"
    assert result[0]["source_line_occurrences"] == [10, 20]
    assert result[0]["candidate_ids"] == ["S0001-C0001", "S0001-C0002"]


def test_required_external_cuda_reference_cannot_be_classified_non_api():
    shard = _SourceShard(1, 1, 1, "return ::__brevll(value);\n")
    candidates = _candidate_anchors(shard.text, 1, 1)
    coverage = [{
        "candidate_id": row["candidate_id"],
        "disposition": "non_api",
        "api_ids": [],
        "reason": "call expression",
    } for row in candidates]

    with pytest.raises(ValueError, match="外部公开 CUDA API 引用.*__brevll"):
        _validate_extraction({"apis": [], "coverage": coverage}, candidates, shard)


def test_global_call_is_not_confused_with_same_named_cuda_declaration():
    text = (
        "[[nodiscard]] _CCCL_API auto sincos(double value);\n"
        "auto own = ::cuda::sincos(value);\n"
        "::sincos(value, &s, &c);\n"
    )
    candidates = _candidate_anchors(text, 1, 1)
    refs = {
        row["name_hint"]: row["must_be_api"]
        for row in candidates
        if row["kind_hint"] == "api_reference"
    }

    assert refs["::cuda::sincos"] is False
    assert refs["::sincos"] is True
    assert "sincos" not in _locally_declared_names(candidates)
