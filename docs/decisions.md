# Project Decisions

Last updated: 2026-06-06

## Fixed Decisions

- Use `ASC_AGENT` as the main project for future development.
- Use `develop_jzy` as the long-lived personal branch.
- Keep `/home/zhenyu/projects/cccl` read-only.
- Treat `ASC_AGENT/repos/cccl` as an incomplete fixture repository for offline tests only, not as
  the real CCCL source.
- Use `ASC_AGENT/repos/accl` as the main target repository during toolchain development.
- Treat `/home/zhenyu/projects/mylearn` as a reference repository, not the primary development target.
- Do not continue expanding `cccl-to-accl-v2`; preserve it only as historical context.
- Start with `libcudacxx -> libascendcxx`; defer CUB/Thrust/cudax planning until the libcudacxx path is stable.

## Quality Decisions

- A style-clean commit is not enough to mark migration complete.
- Host tests must use independent golden logic and return nonzero on failure.
- Kernel tests must inspect actual cannsim verification output, not only process exit status.
- Environment failures should not be sent into model repair loops as code failures.
- Validated migration results should be promoted to `examples/` only after quality gates pass.

## Tooling Decisions

- Prefer deterministic local scanning and structured indexes over ad hoc prompt-only context.
- Real CCCL inventory/test indexing should support `CCCL_REPO=/home/zhenyu/projects/cccl` by
  default and must not populate `ASC_AGENT/repos/cccl` by copying the full upstream repository.
- Add dependency closure migration before attempting large batches from real CCCL.
- Keep new Codex sessions productive by reading handoff docs first, not by relying on old chat history.
- Update `docs/codex_handoff.md` at the end of each meaningful work session.

## Config and Macro Layer Decision

- Keep `_ASCEND_*` as the canonical ACCL target spelling for namespace control and AscendC
  execution annotations in `ascend/std/__config`, including `_ASCEND_STD_BEGIN`,
  `_ASCEND_STD_END`, `_ASCEND_AICORE_FN`, `_ASCEND_AIV_FN`, and compiler/platform flags.
- Provide `_ACCL_*` aliases in `ascend/std/__config` as a compatibility layer, not as a
  replacement naming scheme. Existing generated headers and examples should not be mechanically
  rewritten from `_ASCEND_*` to `_ACCL_*`.
- Use `_ACCL_*` for migrated CCCL support-header surfaces where the upstream macro family is
  naturally `_CCCL_*`, for example `__cccl/os.h` mapping to `__accl/os.h` with `_ACCL_OS(...)`.
- Let `_ACCL_STD_NO_EXCEPTIONS` feed `_ASCEND_STD_NO_EXCEPTIONS` when predefined, so callers and
  future migrated support headers can use either spelling consistently.
- Defer any broad macro cleanup until foundational dependency headers are migrated and validated;
  Node 5 should use the existing `_ASCEND_*` canonical macros unless a support header specifically
  needs an `_ACCL_*` public compatibility macro.

## Open Decisions

- Exact status format for a future machine-generated migration ledger.
- Whether final submissions should sync from `ASC_AGENT/repos/accl` into `mylearn` manually or through automation.
- How to classify components that are semantically valid on host but not expressible in the current kernel scaffold.
