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

## Task Node Workflow

Use one conversation for one task node whenever possible. At the start of a new
conversation, read the files in "First Read", check the current branch and
working tree, then pick up the next unfinished node from this section.

At the end of a completed node:

1. Run the relevant tests.
2. Commit the completed change if requested by the user.
3. Update `docs/codex_handoff.md` with what changed, verification, and the next
   concrete task.
4. Leave the next conversation a clear starting point.

Do not start broad migrations until real inventory, test indexing, and dependency
closure support are in place.

## Task Nodes

### Node 0: Environment and Rules Baseline

Goal: keep the development environment and AI handoff rules stable.

- Verify `conda run -n accl python main.py selftest`.
- Verify `conda run -n accl python -m pytest`.
- Project defaults should use conda env `accl`.
- Keep `.env` ignored and out of commits.

Status: Python development environment has passed selftest and pytest in env
`accl`; project defaults now use `accl`; CANN/cannsim and real model calls are
not yet verified.

### Node 1: Real CCCL Header Inventory

Goal: scan real upstream headers without copying CCCL into this repository.

- Resolve the real source root from `CCCL_REPO`, defaulting to
  `/home/zhenyu/projects/cccl`.
- Scan `libcudacxx/include/cuda/std`.
- Record header relative path, module, public/private shape, and includes.
- Produce a deterministic JSON report under `outputs/`.
- Add fixture-based unit tests first.

### Node 2: Real CCCL Test Indexing

Goal: understand the real upstream test layout and map tests to components.

- Scan `libcudacxx/test/libcudacxx/std`.
- Index `.pass.cpp`, `.verify.cpp`, `.fail.cpp`, and helper headers.
- Extract `cuda/std/...` includes from tests.
- Build candidate header/test mappings without assuming fixture-style parallel
  paths.
- Report unmapped headers and unmapped tests.

### Node 3: Include Dependency Graph

Goal: move from single-file migration toward dependency-closure migration.

- Parse `#include <cuda/std/...>` and `#include "cuda/std/..."`.
- Keep dependencies within `libcudacxx/include/cuda/std`.
- Build a graph and return a leaf-first topological order.
- Detect cycles safely.
- Add fixture tests for A -> B -> C ordering.

### Node 4: Config and Macro Layer Decision

Goal: make the ACCL configuration layer explicit before broad migration.

- Evaluate current `_ASCEND_*` macros in `ascend/std/__config`.
- Compare with a possible `_ACCL_*` compatibility layer.
- Decide whether to keep `_ASCEND_*`, migrate to `_ACCL_*`, or support aliases.
- Record the decision in `docs/decisions.md`.
- Keep existing headers/tests passing.

### Node 5: Minimal Foundational Dependencies

Goal: migrate the smallest shared building blocks needed by algorithms.

- Start with `__utility/move.h`, `__utility/forward.h`, `__utility/pair.h`.
- Add minimal required `__type_traits` pieces.
- Add `__functional/identity.h`, `__functional/operations.h`, and
  `__algorithm/comp.h` as needed.
- Add self-include or host semantic tests.
- Make `minmax` depend on a real migrated `pair` instead of inlining a local
  substitute.

### Node 6: Revalidate Existing Samples Against Real CCCL

Goal: stop treating fixture-generated examples as final completion evidence.

- Revalidate `max`, `min`, `clamp`, `swap`, and `minmax` against real upstream
  headers/tests.
- Migrate or correct host tests with independent golden logic.
- Generate or correct kernel specs where the operation is kernel-expressible.
- Update `docs/migration_ledger.md`.
- Promote only validated results into `examples/`.

### Node 7: First Real Algorithm Batch

Goal: migrate a small real batch using the inventory and dependency graph.

Suggested order:

1. `max.h`
2. `min.h`
3. `clamp.h`
4. `swap.h`
5. `minmax.h`
6. `gcd.h`
7. `lcm.h`
8. `midpoint.h`

After that, consider `find`, `find_if`, `count`, `count_if`, `all_of`,
`any_of`, and `none_of`.

### Node 8: Public Aggregation Headers

Goal: make user-facing includes work.

- Complete `ascend/std/algorithm` only with validated components.
- Add `ascend/std/type_traits`, `ascend/std/utility`,
  `ascend/std/functional`, and `ascend/std/iterator` when their internals are
  ready.
- Add minimal include tests for each public header.

### Node 9: Automated Status and Ledger

Goal: make progress visible and machine-checkable.

- Generate machine-readable migration status from inventory and target repo.
- Track `pending`, `generated`, `host_passed`, `kernel_passed`,
  `full_passed`, `blocked_env`, and `blocked_design`.
- Summarize migrated headers, missing dependencies, mapped tests, and unmapped
  tests.
- Use the report to keep `docs/migration_ledger.md` accurate.

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
