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
- Latest checked commit before Node 5 work: `9f8ae71 docs: decide accl config macro layer`.

## What Changed This Session

- Advanced Node 5 minimal foundational dependencies:
  - Added ACCL bootstrap headers for `__utility/move.h`, `__utility/forward.h`, and
    `__utility/pair.h`.
  - Added minimal `__type_traits` pieces used by those utilities:
    `integral_constant.h`, `remove_reference.h`, `is_reference.h`, `is_same.h`, and
    `conditional.h`.
  - Added focused bootstrap versions of `__functional/identity.h`,
    `__functional/operations.h`, and `__algorithm/comp.h`.
  - Updated `repos/accl/libascendcxx/include/ascend/std/__algorithm/minmax.h` to include and return
    the migrated `ascend::std::pair` instead of defining a local inline pair substitute.
  - Added `tests/test_foundational_dependencies.py`, a g++ host semantic test covering self-includes,
    value-category forwarding, move-only construction, pair reference semantics, `minmax` reference
    ordering, identity, operations, and algorithm comparator helpers.
  - Updated `docs/migration_ledger.md` so `minmax.h` is no longer marked blocked by the missing
    pair design; real upstream revalidation remains a Node 6 task.

## Verification

- `git branch --show-current`: `develop_jzy`.
- `git status --short`: clean before Node 5 edits.
- `git log -1 --oneline`: `9f8ae71 docs: decide accl config macro layer`.
- `conda run -n accl python -m pytest tests/test_foundational_dependencies.py`: passed (`1 passed`).
- `bash repos/accl/libascendcxx/run_host_test.sh`: passed `host.minmax`.
- `conda run -n accl python -m pytest`: passed (`175 passed`).
- `conda run -n accl python main.py selftest`: passed.

## Next Concrete Task

Continue Node 5 or start Node 6, depending on desired scope:

1. If continuing Node 5, add only immediately needed missing foundational pieces such as public
   aggregation headers (`ascend/std/utility`, `ascend/std/functional`, `ascend/std/type_traits`) or
   additional traits when a concrete algorithm requires them.
2. If moving to Node 6, revalidate `max`, `min`, `clamp`, `swap`, and `minmax` against the real
   read-only CCCL headers/tests and update `docs/migration_ledger.md` from that evidence.
3. Keep examples unchanged until the quality gates for the corresponding real upstream items pass.

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
