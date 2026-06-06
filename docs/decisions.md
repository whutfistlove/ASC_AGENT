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

## Open Decisions

- Exact status format for a future machine-generated migration ledger.
- Whether final submissions should sync from `ASC_AGENT/repos/accl` into `mylearn` manually or through automation.
- How to classify components that are semantically valid on host but not expressible in the current kernel scaffold.
