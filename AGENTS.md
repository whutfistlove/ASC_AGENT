# AI Agent Instructions

This file is the project-level entry point for AI-assisted development in
`ASC_AGENT`. Read it before changing code.

## First Read

Read these files in order when taking over the project:

1. `docs/codex_handoff.md`
2. `docs/current_status.md`
3. `docs/decisions.md`
4. `docs/project_brief.md`
5. `docs/migration_ledger.md`
6. `README.md`
7. `docs/roadmap.md`

## Hard Rules

- Main development branch: `develop_jzy`.
- Main project root: `/home/zhenyu/projects/ASC_AGENT`.
- Real upstream CCCL repository: `/home/zhenyu/projects/cccl`.
- `/home/zhenyu/projects/cccl` is read-only. Do not modify it.
- `ASC_AGENT/repos/cccl` is an incomplete fixture repository for offline tests only.
- Do not treat `ASC_AGENT/repos/cccl` as real CCCL coverage.
- Do not copy the full CCCL repository into `ASC_AGENT/repos/cccl`.
- `ASC_AGENT/repos/accl` is the main ACCL target repository and experiment target.
- `/home/zhenyu/projects/mylearn` is only a historical/reference repository.
- `cccl-to-accl-v2` is only a historical prototype. Do not continue development there.
- Never read, print, or commit secrets from `.env` files.

## Repository Roles

- `core/`: migration, testing, model, repair, and verification logic.
- `config/`: settings and batch manifests.
- `skills/`: model prompts and shared prompt contracts.
- `examples/`: curated few-shot examples promoted from validated results.
- `tests/`: offline unit tests for the toolchain.
- `outputs/`: generated logs and model IO; do not treat as source input.
- `repos/accl`: generated ACCL target repository and current migration target.
- `repos/cccl`: small fixture source tree for offline tests and examples only.

## Current Technical Direction

The immediate priority is to make the toolchain work against the real CCCL tree
without importing that tree into this repository.

Next recommended work:

1. Implement real CCCL header inventory under `libcudacxx/include/cuda/std`.
2. Implement real CCCL test indexing under `libcudacxx/test/libcudacxx/std`.
3. Default real inventory/test indexing to `CCCL_REPO=/home/zhenyu/projects/cccl`.
4. Generate deterministic reports for headers, tests, includes, and unmapped tests.
5. Add fixture-based unit tests before scanning the full upstream tree.
6. Add include dependency closure migration before large real batches.

## Quality Bar

- A style-clean commit is not enough to mark migration complete.
- Host tests must use independent golden logic and return nonzero on failure.
- Kernel tests must inspect real cannsim verification output, not only process exit status.
- Environment failures must not be sent into model repair loops as code failures.
- Promote results into `examples/` only after quality gates pass.
- Update `docs/codex_handoff.md` after meaningful work sessions.

## Safe Working Pattern

Before making changes:

1. Check branch and working tree with `git branch --show-current` and `git status --short`.
2. Preserve user changes. Do not revert unrelated edits.
3. Prefer small, tested changes.
4. Use fixture tests first, then real read-only CCCL scans.

Useful commands:

```bash
python3 main.py selftest
python3 -m pytest
CCCL_REPO=/home/zhenyu/projects/cccl python3 main.py <future-inventory-command>
```

