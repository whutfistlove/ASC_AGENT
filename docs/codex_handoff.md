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
- Latest checked commit before Node 7 work: `6a2aad3 feat: revalidate node6 samples against real cccl`.

## What Changed This Session

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
- `git status --short`: clean before Node 7 edits.
- `git log -1 --oneline`: `6a2aad3 feat: revalidate node6 samples against real cccl`.
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

Node 7 has migrated and validated the first new numeric algorithms after the Node 6 samples. Next:

1. Decide whether to extend Node 7 to the next small algorithm set (`find`, `find_if`, `count`,
   `count_if`, `all_of`, `any_of`, `none_of`) or stop here and move to Node 8 public aggregation.
2. For `midpoint`, keep float/pointer kernel variants deferred until the scaffold can express
   multiple dtype/pointer-shaped contracts cleanly.
3. Keep cannsim on the configured `Ascend910_9599` / `Ascend950` pairing unless the local CANN
   installation changes.

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
