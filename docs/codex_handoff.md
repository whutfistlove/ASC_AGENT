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

- Created the long-lived personal branch `develop_jzy`.
- Added the long-term documentation handoff package:
  - `docs/project_brief.md`
  - `docs/current_status.md`
  - `docs/decisions.md`
  - `docs/migration_ledger.md`
  - `docs/codex_handoff.md`

## Verification

- `python3 main.py selftest`: passed.
- `git status --short`: clean before documentation was added to the repository.

## Next Concrete Task

Implement real CCCL inventory and test indexing:

1. Add a small module that scans real `libcudacxx/include/cuda/std` headers from
   `CCCL_REPO=/home/zhenyu/projects/cccl` by default.
2. Add a small module or command that scans real `libcudacxx/test/libcudacxx/std` tests from
   `CCCL_REPO=/home/zhenyu/projects/cccl` by default.
3. Connect the scanner to a report in `outputs/` or a CLI subcommand.
4. Add fixture-based unit tests before scanning the full upstream tree.

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
