# Codex Handoff

Last updated: 2026-06-07

## Quick Start for a New Codex Session

Use this prompt in a fresh conversation:

```text
请先只读接手项目。当前主项目是 /home/zhenyu/projects/ASC_AGENT，
真实 CCCL 是 /home/zhenyu/projects/cccl，只读；ASC_AGENT/repos/cccl 只是离线 fixture。
请阅读 docs/codex_handoff.md、docs/current_status.md、docs/decisions.md、
README.md、docs/roadmap.md，然后用 git status 确认工作区状态。
先总结你理解的当前进展和下一步，不要改文件。
```

## Current Branch and Commit

- Branch: `develop_jzy`
- Base commit when branch was created: `894e63a`
- Latest checked commit before Node 10 work: `e0b8329 docs: add node10 migration roadmap`.

## What Changed This Session

- Advanced Node 10 status-driven batch planning:
  - Extended `core/migration_status.py` so raw missing dependency edges remain available while each
    edge is also classified as `true_dependency_gap`, `bootstrap_manual`,
    `target_only_compatibility_wrapper`, `public_aggregation_narrowed`, or
    `deferred_upstream_support_only`.
  - Added target-only artifact classification so ACCL-only wrappers such as
    `ascend/std/__algorithm/swap.h` and generated synthetic samples are distinguishable from
    hand-authored bootstrap surfaces such as `ascend/std/__config`.
  - Added deterministic `batch_candidates` planning output. Candidates are ranked from real CCCL
    inventory, direct test-index mappings, dependency closure size, missing dependency
    classifications, ACCL artifact presence, and host/kernel suitability signals. Upstream support
    and config surfaces are deferred out of the main candidate list, and public facade headers are
    ranked behind implementation headers until internals are ready.
  - Added fixture coverage in `tests/test_migration_status.py` for missing dependency
    classification, target-only classification, and candidate ordering.
  - Updated the `main.py migration-status` CLI summary to print dependency classification counts
    and the candidate count.
  - Regenerated the real read-only status report from `/home/zhenyu/projects/cccl`. Current raw
    missing dependency edges remain 439, now classified as 70 `true_dependency_gap`, 18
    `bootstrap_manual`, 0 `target_only_compatibility_wrapper`, 315
    `public_aggregation_narrowed`, and 36 `deferred_upstream_support_only`. The report contains
    724 ranked batch candidates.
  - Recommended next real migration batch from the current ranking: start with the small
    dependency-light algorithm family `all_of`, `any_of`, `find_if`, and `none_of`; optionally add
    nearby similarly ranked algorithms such as `find_if_not`, `for_each`, or simple copy/replace
    variants only after Node 11/12 context and dependency orchestration are in place. Defer
    `find`, `count`, and `count_if` for now because the current dependency report shows much larger
    closures and many true gaps.

- Advanced Node 9 automated status and ledger:
  - Added `core/migration_status.py` and the `main.py migration-status` CLI.
  - The report is deterministic JSON written to `outputs/migration_status.json`; it combines
    real CCCL header inventory, real test indexing, the dependency graph, the ACCL target tree,
    and compact validation evidence parsed from `docs/migration_ledger.md`.
  - It tracks the required status values: `pending`, `generated`, `host_passed`,
    `kernel_passed`, `full_passed`, `blocked_env`, and `blocked_design`.
  - It summarizes source-mapped migrated headers, ACCL target-only headers, missing dependency
    edges, mapped tests, unmapped tests, unmapped headers, ledger entries, and dependency cycles.
  - Added fixture-based unit tests in `tests/test_migration_status.py`.
  - Updated `docs/migration_ledger.md` with an automated report section and current real-scan
    summary without rewriting the human-maintained migration tables.

- Advanced Node 8 public aggregation headers:
  - Completed `ascend/std/algorithm` with only validated public components from Nodes 6/7:
    `clamp`, `max`, `min`, `minmax`, and the `swap` compatibility wrapper backed by
    validated `ascend/std/__utility/swap.h`. Historical synthetic samples such as `sort3`
    and `quad_fanout`, plus broader unvalidated algorithms, remain excluded.
  - Refined `ascend/std/numeric` to expose the validated numeric API through `gcd.h`, `lcm.h`,
    and `midpoint.h`.
  - Added minimal public aggregation headers for validated foundational pieces:
    `ascend/std/type_traits`, `ascend/std/utility`, and `ascend/std/functional`.
  - Did not add `ascend/std/iterator`; no iterator internals have been prepared and validated yet.
  - Added public include/semantic host tests:
    `public_algorithm_tests.cpp`, `public_numeric_tests.cpp`, `public_type_traits_tests.cpp`,
    `public_utility_tests.cpp`, and `public_functional_tests.cpp`.
  - Updated `docs/migration_ledger.md` with a public aggregation header status table.

- Advanced Node 7 first real algorithm batch for the new numeric algorithms after the Node 6 samples:
  - Re-ran the real read-only CCCL scans from `/home/zhenyu/projects/cccl`:
    `inventory` found 786 headers, `test-index` found 2581 std tests, and `dep-graph` found 6889 edges.
  - Confirmed upstream `gcd` and `lcm` share the real implementation header
    `libcudacxx/include/cuda/std/__numeric/gcd_lcm.h`; ACCL now has
    `ascend/std/__numeric/gcd_lcm.h` plus thin `gcd.h` and `lcm.h` wrappers for the current
    per-operator scaffold layout.
  - Added `ascend/std/__numeric/midpoint.h` and a minimal `ascend/std/numeric` aggregation header
    for the validated numeric surfaces.
  - Added ACCL host semantic tests for `gcd`, `lcm`, and `midpoint`. These tests use independent
    golden logic rather than calling the tested `ascend::std` APIs as expected values.
  - Generated fast cannsim kernel scaffolds and `kernel_spec.json` files for `gcd`, `lcm`, and
    integer `midpoint`. `gcd`/`lcm` use `int32_t` exact comparison; `midpoint` uses `int32_t` inputs
    with `INT32_MIN`/`INT32_MAX` cases and independent `int64_t` golden logic.
  - Updated `docs/migration_ledger.md` to mark `gcd_lcm.h`/`gcd.h`, `gcd_lcm.h`/`lcm.h`, and
    `midpoint.h` as `kernel_passed`, while explicitly deferring compile-fail tests, upstream
    `midpoint.verify.cpp`, and float/pointer kernel variants.

- Advanced Node 6 real-upstream sample revalidation for `max`, `min`, `clamp`, `swap`, and `minmax`:
  - Added `core/sample_revalidation.py` and the `main.py revalidate-samples` CLI. The report uses the
    real read-only CCCL tree and records upstream headers, candidate tests, scaffold-applicable tests,
    deferred tests, dependencies, and ACCL artifact presence.
  - Generated `outputs/sample_revalidation.json` from `/home/zhenyu/projects/cccl`; all five samples
    map to real upstream headers/tests.
  - Corrected the real upstream `swap` location to `__utility/swap.h`, added
    `repos/accl/libascendcxx/include/ascend/std/__utility/swap.h`, and kept
    `__algorithm/swap.h` as a compatibility wrapper.
  - Strengthened `max_tests.cpp` so it uses independent golden logic, checks equal-value reference
    identity, and returns nonzero on failure.
  - Switched ACCL swap host/kernel includes to `ascend/std/__utility/swap.h`.
  - Added a `max` kernel spec with independent golden logic and removed the old kernel verifier's
    call to the tested `ascend::std::max` as its expected value.
  - Added failure triage coverage for unsupported CANN `SOC_VERSION` messages.
  - Made kernel scaffold SOC settings configurable via `tests.kernel_soc_version` and
    `tests.kernel_cannsim_soc_version`; current config follows the validated mylearn/CANN setup:
    CMake `SOC_VERSION=Ascend910_9599`, cannsim `-s Ascend950`.
  - Regenerated the five Node 6 kernel scaffolds from their checked-in `kernel_spec.json` files in
    `--kernel-fast` mode. This keeps real cannsim execution and independent golden checks while
    reducing workload to one core / 64 elements.
  - Marked the five Node 6 samples as `kernel_passed` in `docs/migration_ledger.md`.
  - Refreshed `examples/` for the five validated samples from real CCCL headers/main `.pass.cpp`
    tests plus the current validated ACCL host tests and kernel specs. `minmax` now has a test
    example triplet too.

## Verification

- `git branch --show-current`: `develop_jzy`.
- `git status --short`: clean before Node 10 edits.
- `git log -1 --oneline`: `e0b8329 docs: add node10 migration roadmap`.
- Node 10 focused validation:
  - `conda run -n accl python -m pytest tests/test_migration_status.py`: passed (`4 passed`).
  - `conda run -n accl python main.py migration-status --cccl-repo /home/zhenyu/projects/cccl`:
    passed and wrote `outputs/migration_status.json`.
  - `conda run -n accl python -m pytest tests/test_migration_status.py tests/test_inventory.py tests/test_test_index.py tests/test_dep_graph.py`:
    passed (`21 passed`).
  - `conda run -n accl python -m pytest`: passed (`185 passed`).
  - `conda run -n accl python main.py selftest`: passed.
  - Current Node 10 report summary: 786 real CCCL headers, 23 source-mapped migrated headers,
    6 ACCL target-only headers, 439 raw missing dependency edges, 724 ranked batch candidates,
    65 mapped headers, and 68 unmapped tests. Missing dependency classifications are 70
    `true_dependency_gap`, 18 `bootstrap_manual`, 0 `target_only_compatibility_wrapper`, 315
    `public_aggregation_narrowed`, and 36 `deferred_upstream_support_only`.

- `git branch --show-current`: `develop_jzy`.
- `git status --short`: clean before Node 9 edits.
- `git log -1 --oneline`: `de0988b feat: complete node8 public aggregation headers`.
- Node 9 focused validation:
  - `conda run -n accl python -m pytest tests/test_migration_status.py tests/test_inventory.py tests/test_test_index.py tests/test_dep_graph.py`:
    passed (`21 passed`).
  - `conda run -n accl python main.py migration-status --cccl-repo /home/zhenyu/projects/cccl`:
    passed and wrote `outputs/migration_status.json`.
  - `conda run -n accl python -m pytest`: passed (`185 passed`).
  - `conda run -n accl python main.py selftest`: passed.
  - Current report summary: 786 real CCCL headers, 23 source-mapped migrated headers,
    6 ACCL target-only headers, 439 raw missing dependency edges, 65 mapped headers,
    and 68 unmapped tests. Status counts are 763 `pending`, 5 `generated`,
    11 `host_passed`, 7 `kernel_passed`, and 0 for `full_passed`, `blocked_env`,
    and `blocked_design`.

- `git branch --show-current`: `develop_jzy`.
- `git status --short`: clean before Node 8 edits.
- `git log -1 --oneline`: `8c50f58 feat: complete node7 first algorithm batch`.
- ACCL Node 8 public aggregation validation:
  - `conda run -n accl cmake -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON` from
    `repos/accl/libascendcxx`: passed.
  - `conda run -n accl cmake --build build --target public_algorithm_host_test public_functional_host_test public_numeric_host_test public_type_traits_host_test public_utility_host_test`:
    passed.
  - `conda run -n accl ctest --test-dir build -R "host\\.public_(algorithm|functional|numeric|type_traits|utility)$" -V`:
    passed (`5/5`).
  - `conda run -n accl ctest --test-dir build -R "host\\.(max|min|clamp|swap|minmax|gcd|lcm|midpoint|public_algorithm|public_functional|public_numeric|public_type_traits|public_utility)$" -V`:
    passed (`13/13`).
  - `conda run -n accl python -m pytest`: passed (`181 passed`).
  - `conda run -n accl python main.py selftest`: passed.
- `conda run -n accl python main.py inventory --cccl-repo /home/zhenyu/projects/cccl`: passed and
  wrote `outputs/cccl_header_inventory.json` (786 headers).
- `conda run -n accl python main.py test-index --cccl-repo /home/zhenyu/projects/cccl`: passed and
  wrote `outputs/cccl_test_index.json` (2581 tests, 65 mapped headers).
- `conda run -n accl python main.py dep-graph --cccl-repo /home/zhenyu/projects/cccl`: passed and
  wrote `outputs/cccl_dep_graph.json` (6889 edges).
- ACCL Node 7 host validation:
  - `conda run -n accl cmake -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON` from
    `repos/accl/libascendcxx`: passed.
  - `conda run -n accl cmake --build build --target gcd_host_test lcm_host_test midpoint_host_test`:
    passed.
  - `conda run -n accl ctest --test-dir build -R "host\\.(gcd|lcm|midpoint)$" -V`: passed (`3/3`).
  - `conda run -n accl ctest --test-dir build -R "host\\.(max|min|clamp|swap|minmax|gcd|lcm|midpoint)$" -V`:
    passed (`8/8`).
- ACCL Node 7 kernel validation:
  - `conda run -n accl ctest --test-dir build -R "kernel\\.(gcd|lcm|midpoint)\\.sim$" -V`:
    passed (`3/3`) with `KERNEL_SIM_RESULT: PASS` for all three new kernels.
- `conda run -n accl python -m pytest`: passed (`181 passed`).
- `conda run -n accl python main.py selftest`: passed.
- `conda run -n accl python -m pytest tests/test_sample_revalidation.py`: passed (`3 passed`).
- `conda run -n accl python main.py revalidate-samples --cccl-repo /home/zhenyu/projects/cccl`:
  passed and wrote `outputs/sample_revalidation.json`.
- Examples refreshed from these real upstream main tests:
  `max.pass.cpp`, `min.pass.cpp`, `clamp.pass.cpp`, `swap.pass.cpp`, and `minmax.pass.cpp`.
- ACCL host validation:
  - `conda run -n accl cmake .. -DCMAKE_EXPORT_COMPILE_COMMANDS=ON` from
    `repos/accl/libascendcxx/build`: passed.
  - `conda run -n accl cmake --build . --target max_host_test min_host_test clamp_host_test swap_host_test minmax_host_test`: passed.
  - `conda run -n accl ctest -R "host\\.(max|min|clamp|swap|minmax)$" -V`: passed (`5/5`).
- Kernel validation attempt:
  - First attempt exposed non-executable kernel `run_test.sh` scripts; executable bits were restored
    for the five sample scripts.
  - After that, `conda run -n accl ctest -R "kernel\\.(max|min|clamp|swap|minmax)\\.sim$" -V`
    reached CANN CMake and failed for all five with `SOC_VERSION Ascend950PR_9599 does not support`.
    This was correctly treated as an environment/config issue, not a code failure.
  - After aligning kernel SOC config with `/home/zhenyu/projects/mylearn`, the following fast cannsim
    semantic runs passed with `KERNEL_SIM_RESULT: PASS`:
    `outputs/kernel_test_max.log`, `outputs/kernel_test_min.log`,
    `outputs/kernel_test_clamp.log`, `outputs/kernel_test_swap.log`, and
    `outputs/kernel_test_minmax.log`.
- `conda run -n accl python -m pytest`: passed (`181 passed`).
- `conda run -n accl python main.py selftest`: passed.

## Next Concrete Task

Node 10 has been implemented and verified in the working tree. The next task should start at
Node 11 in `AGENTS.md`.

Planned next-node sequence:

1. Node 11: build an AI migration context pack so model/API calls receive source, dependency,
   test, sibling, example, and ledger context in a bounded structure.
2. Node 12: connect dependency closure to AI header rewriting so missing dependencies are migrated
   leaf-first before an entry header.
3. Node 13: upgrade AI test migration to use real upstream test mappings and explicit
   applicable/deferred test classification.
4. Node 14: run the first dependency-aware AI-driven real algorithm batch. Current Node 10 planning
   recommends beginning with `all_of`, `any_of`, `find_if`, and `none_of`, then reassessing nearby
   candidates. Defer `find`, `count`, and `count_if` until their larger dependency gaps are reduced.

Important constraints for the next session:

- Do not broad-migrate from the full pending set.
- Use `/home/zhenyu/projects/cccl` only as the read-only real CCCL source.
- Treat `ASC_AGENT/repos/cccl` only as an incomplete offline fixture.
- Keep cannsim on the configured `Ascend910_9599` / `Ascend950` pairing unless the local CANN
  installation changes.
- For `midpoint`, keep float/pointer kernel variants deferred until the scaffold can express
  multiple dtype/pointer-shaped contracts cleanly.

## Files and Directories to Treat Carefully

- `/home/zhenyu/projects/cccl`: read-only source reference.
- `ASC_AGENT/repos/cccl`: incomplete fixture repository for offline tests only; do not copy the full
  CCCL repository into it.
- `cccl-to-accl-v2`: historical prototype; avoid modifying unless explicitly asked.
- `ASC_AGENT/repos/accl`: generated target repository, but it is also the current migration target.
- `.env` files: never print secrets or include them in commits.

## Known Pitfalls

- Upstream libcudacxx tests are not under `libcudacxx/test/std`; they are under
  `libcudacxx/test/libcudacxx/std`.
- A single header can have multiple relevant `.pass.cpp` tests.
- Passing commit/style checks does not prove semantic correctness.
- For config macros, `_ASCEND_*` is canonical for namespace/device annotations; `_ACCL_*` is a
  compatibility alias or support-header macro family, not a reason to rewrite existing headers.
- Missing CANN/cannsim, or an unsupported SOC pairing, is an environment/config block, not a code
  failure.
- Avoid making generated examples the source of truth until they pass quality gates.
