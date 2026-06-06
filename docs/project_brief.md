# CCCL -> ACCL Project Brief

Last updated: 2026-06-06

## Goal

Migrate NVIDIA CCCL to ACCL for AscendC, starting with `libcudacxx -> libascendcxx`.
The long-term goal is complete migration with the applicable tests passing, not only
style-clean generated code.

## Repository Roles

- `/home/zhenyu/projects/cccl`: read-only upstream CCCL source of truth.
- `/home/zhenyu/projects/ASC_AGENT`: main development project and migration assistant.
- `ASC_AGENT/repos/accl`: primary target ACCL repository and experiment target.
- `ASC_AGENT/repos/cccl`: incomplete fixture source repository for offline tests and examples only;
  do not treat it as real upstream coverage.
- `/home/zhenyu/projects/mylearn`: reference for historical ACCL layout, hooks, and CANN workflow.
- `cccl-to-accl-v2`: historical prototype; keep useful lessons but do not extend it as the main tool.

Real inventory and test indexing should default to the complete upstream tree selected by
`CCCL_REPO=/home/zhenyu/projects/cccl`. Do not copy the full CCCL repository into
`ASC_AGENT/repos/cccl`.

## Development Branches

- Long-lived personal branch: `develop_jzy`.
- Short task branches should be created from `develop_jzy`, for example:
  - `feature/dep-graph`
  - `feature/real-test-index`
  - `feature/type-traits-bootstrap`
  - `feature/algorithm-batch-1`

## Work Strategy

Prefer toolchain reliability before broad migration:

1. Stabilize ASC_AGENT baseline.
2. Add real CCCL scanning, real test indexing, and include dependency graph support.
3. Migrate foundational headers first: `__config`, `__utility`, `__type_traits`, `__functional`.
4. Migrate simpler `__algorithm` operators in batches.
5. Run host/kernel/repo checks for each batch.
6. Promote validated outputs into `examples/` so future model prompts improve.

## Completion Standard

A migrated item should be marked complete only when the applicable checks pass:

- Header self-containment and syntax checks pass.
- Host semantic tests pass with independent golden logic.
- AscendC/cannsim kernel tests pass for operators that can be expressed in the kernel scaffold.
- Repository style, hook, and commit checks pass when submitting to the target repository.
- The result is recorded in `docs/migration_ledger.md`.
