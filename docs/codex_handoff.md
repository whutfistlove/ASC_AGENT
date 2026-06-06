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
- Latest checked commit before Node 3 work: `dd34e7b feat: add real cccl test index`.

## What Changed This Session

- Completed Node 3 include dependency graph:
  - Added `core/dep_graph.py` to turn header inventory include data into a deterministic
    in-tree dependency graph.
  - Keeps only dependencies that exist under `libcudacxx/include/cuda/std`; missing
    `cuda/std/...` includes are reported as `unknown_cuda_std_includes` and are not graph edges.
  - Returns dependency-first/leaf-first ordering for migration planning.
  - Detects include cycles safely and records them in the report.
  - Added `main.py dep-graph`, resolving CCCL from `--cccl-repo`, `CCCL_REPO`, then
    `/home/zhenyu/projects/cccl`, and writing `outputs/cccl_dep_graph.json`.
  - Added fixture tests in `tests/test_dep_graph.py`, including A -> B -> C ordering and
    cycle reporting.
  - Ran a real read-only scan of `/home/zhenyu/projects/cccl`; it found 786 headers,
    6,889 in-tree dependency edges, 31 unknown `cuda/std/...` includes, and 1 cycle:
    `__internal/pstl_config.h -> detail/__config -> __internal/pstl_config.h`.

## Verification

- `git branch --show-current`: `develop_jzy`.
- `git status --short`: clean before Node 3 edits.
- `git log -1 --oneline`: `dd34e7b feat: add real cccl test index`.
- `conda run -n accl python -m pytest tests/test_dep_graph.py`: passed (`4 passed`).
- `conda run -n accl python -m pytest tests/test_inventory.py tests/test_test_index.py`:
  passed (`13 passed`).
- `conda run -n accl python main.py dep-graph --cccl-repo /home/zhenyu/projects/cccl`:
  passed; wrote `outputs/cccl_dep_graph.json`.
- `conda run -n accl python -m pytest`: passed (`173 passed`).
- `conda run -n accl python main.py selftest`: passed.

## Next Concrete Task

Start Node 4: Config and Macro Layer Decision:

1. Evaluate current `_ASCEND_*` macros in `ascend/std/__config`.
2. Compare with a possible `_ACCL_*` compatibility layer.
3. Decide whether to keep `_ASCEND_*`, migrate to `_ACCL_*`, or support aliases.
4. Record the decision in `docs/decisions.md`.
5. Keep existing headers/tests passing.

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
- Missing CANN/cannsim is an environment block, not a code failure.
- Avoid making generated examples the source of truth until they pass quality gates.
