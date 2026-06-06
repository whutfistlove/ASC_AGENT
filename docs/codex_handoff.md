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
- Latest checked commit before Node 2 work: `6ec4c8d feat: add real cccl header inventory`.

## What Changed This Session

- Completed Node 2 real CCCL test indexing:
  - Added `core/test_index.py` for read-only scans of the real upstream
    `libcudacxx/test/libcudacxx/std` tree.
  - Added `main.py test-index`, resolving CCCL from `--cccl-repo`, `CCCL_REPO`, then
    `/home/zhenyu/projects/cccl`.
  - Indexes `.pass.cpp`, `.verify.cpp`, `.fail.cpp`, and helper headers
    (`.h`, `.hpp`, `.cuh`).
  - Extracts direct `cuda/std/...` includes from indexed files and builds candidate
    header/test mappings from actual include information, not fixture-style parallel paths.
  - Reports unmapped headers and unmapped tests in deterministic JSON at
    `outputs/cccl_test_index.json`.
  - Added fixture-based tests in `tests/test_test_index.py`.
  - Ran a real read-only scan of `/home/zhenyu/projects/cccl`; it found 2,581 tests,
    38 helper headers, 65 directly mapped headers, 721 unmapped headers, and 68
    unmapped tests.

## Verification

- `git branch --show-current`: `develop_jzy`.
- `git status --short`: clean before Node 2 edits.
- `git log -1 --oneline`: `6ec4c8d feat: add real cccl header inventory`.
- `conda run -n accl python -m pytest tests/test_test_index.py`: passed (`5 passed`).
- `conda run -n accl python main.py test-index --cccl-repo /home/zhenyu/projects/cccl`:
  passed; wrote `outputs/cccl_test_index.json`.
- `conda run -n accl python -m pytest`: passed (`169 passed`).
- `conda run -n accl python main.py selftest`: passed.

## Next Concrete Task

Start Node 3: implement include dependency graph support:

1. Parse `#include <cuda/std/...>` and `#include "cuda/std/..."` from headers.
2. Keep dependencies within `libcudacxx/include/cuda/std`.
3. Build a graph and return a leaf-first topological order.
4. Detect cycles safely.
5. Add fixture tests for A -> B -> C ordering.

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
