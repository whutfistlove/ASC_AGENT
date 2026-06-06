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
- This handoff was created while implementing the long-cycle development workflow.

## What Changed This Session

- Completed Node 1 real CCCL header inventory:
  - Added `core/inventory.py` for read-only scans of the real upstream CCCL tree.
  - Added `main.py inventory`, resolving CCCL from `--cccl-repo`, `CCCL_REPO`, then
    `/home/zhenyu/projects/cccl`.
  - Scans `libcudacxx/include/cuda/std` and records header relative path, module,
    filename, public/private shape, and `cuda/std/...` include list.
  - Writes deterministic JSON to `outputs/cccl_header_inventory.json`.
  - Added fixture-based tests in `tests/test_inventory.py`.
  - Ran a real read-only scan of `/home/zhenyu/projects/cccl`; it found 786 headers.

## Verification

- `git branch --show-current`: `develop_jzy`.
- `git status --short`: clean before Node 1 edits.
- `git log -1 --oneline`: `837fc45 chore: baseline accl development environment`.
- `conda run -n accl python -m pytest tests/test_inventory.py`: passed (`8 passed`).
- `conda run -n accl python main.py inventory`: passed; wrote
  `outputs/cccl_header_inventory.json` with 786 headers.
- `conda run -n accl python -m pytest`: passed (`164 passed`).
- `conda run -n accl python main.py selftest`: passed.

## Next Concrete Task

Start Node 2: implement real CCCL test indexing:

1. Scan `libcudacxx/test/libcudacxx/std` in the real upstream CCCL repository.
2. Index `.pass.cpp`, `.verify.cpp`, `.fail.cpp`, and helper headers.
3. Extract `cuda/std/...` includes from tests.
4. Build candidate header/test mappings without assuming fixture-style parallel paths.
5. Report unmapped headers and unmapped tests.
6. Add fixture-based unit tests before scanning the full upstream test tree.

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
