# Codex Handoff

Last updated: 2026-06-06

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
- Latest checked commit before Node 4 work: `95e341e feat: add cccl include dependency graph`.

## What Changed This Session

- Completed Node 4 config and macro layer decision:
  - Inspected `repos/accl/libascendcxx/include/ascend/std/__config` and current ACCL generated
    algorithm headers.
  - Confirmed existing generated target headers and examples use `_ASCEND_STD_BEGIN`,
    `_ASCEND_STD_END`, and `_ASCEND_AICORE_FN` as their working config surface.
  - Confirmed `_ACCL_*` currently appears as the migrated form of CCCL support macros, especially
    the historical `__cccl/os.h -> __accl/os.h` example with `_ACCL_OS(...)`.
  - Recorded the decision in `docs/decisions.md`: keep `_ASCEND_*` canonical for target namespace
    and AscendC annotations; provide `_ACCL_*` compatibility aliases; use `_ACCL_*` for migrated
    CCCL support-header macro families where appropriate.
  - Added a narrow alias section to `ascend/std/__config`; existing generated headers were not
    mechanically rewritten.
  - Added `tests/test_config_macro_policy.py` to compile-check `_ACCL_*` aliases and the
    `_ACCL_STD_NO_EXCEPTIONS -> _ASCEND_STD_NO_EXCEPTIONS` bridge.

## Verification

- `git branch --show-current`: `develop_jzy`.
- `git status --short`: clean before Node 4 edits.
- `git log -1 --oneline`: `95e341e feat: add cccl include dependency graph`.
- `conda run -n accl python -m pytest tests/test_config_macro_policy.py`: passed (`1 passed`).
- `conda run -n accl python -m pytest`: passed (`174 passed`).
- `conda run -n accl python main.py selftest`: passed.

## Next Concrete Task

Start Node 5: Minimal Foundational Dependencies:

1. Start with `__utility/move.h`, `__utility/forward.h`, and `__utility/pair.h`.
2. Add only the minimal `__type_traits` pieces required by those utilities and the first
   algorithms.
3. Add `__functional/identity.h`, `__functional/operations.h`, and `__algorithm/comp.h` only as
   needed.
4. Add focused self-include or host semantic tests.
5. Make `minmax` depend on a real migrated `pair` instead of its local inline substitute.

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
- Missing CANN/cannsim is an environment block, not a code failure.
- Avoid making generated examples the source of truth until they pass quality gates.
