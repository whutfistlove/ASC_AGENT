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

When replying to the user about a task node, always state whether the current
node is complete, what still needs work if anything, whether it is recommended
to move to the next node, and what the next node should do.

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

### Node 10: Status-Driven Batch Planning

Goal: turn the machine-readable status report into actionable next-batch
planning.

- Refine `core/migration_status.py` so missing dependency data is classified,
  not only reported as raw edges.
- Separate true dependency-closure gaps from hand-authored bootstrap headers,
  target-only compatibility wrappers, intentionally narrowed public aggregation
  headers, and deferred upstream-only/support-only surfaces.
- Rank candidate migration headers using real inventory, test mappings,
  dependency closure size, missing dependency count, ACCL artifact presence, and
  host/kernel test suitability.
- Add fixture-based unit tests for the new planning/classification behavior.
- Update `docs/codex_handoff.md` with the recommended next migration batch.

### Node 11: AI Migration Context Pack

Goal: provide the AI/API migration step with structured, dependency-aware
context instead of only a single source header.

- Build a deterministic context pack for an entry CCCL header.
- Include source header metadata, dependency closure summary, existing ACCL
  counterpart if present, nearby ACCL sibling headers, mapped upstream tests,
  relevant validated examples, and ledger/status evidence.
- Keep context bounded; do not dump unrelated real CCCL content into prompts.
- Add fixture tests for context pack generation.
- Ensure the context pack reads `/home/zhenyu/projects/cccl` only as a
  read-only source and never reads `.env` files.

### Node 12: Dependency-Aware AI Header Migration

Goal: upgrade header migration from single-file AI rewriting to dependency-aware
AI rewriting.

- For an entry header, compute the dependency closure with `core/dep_graph.py`.
- Skip already migrated and validated dependencies when safe.
- Migrate missing dependencies in leaf-first order before the entry header.
- Feed each AI/API rewrite call with the Node 11 context pack.
- Preserve environment-vs-code failure triage; environment failures must not be
  sent into model repair loops.
- Validate the orchestration with fixture tests such as A -> B -> C ordering
  before attempting real CCCL targets.

### Node 13: AI Test Migration Upgrade

Goal: make AI-generated ACCL tests use real upstream test context and independent
validation logic.

- Connect real test-index mappings to `core/test_migrator.py`.
- Select applicable upstream `.pass.cpp` tests and explicitly mark deferred
  `.verify.cpp`, `.fail.cpp`, compile-fail, dependency-blocked, or
  scaffold-inexpressible tests.
- Require host tests to use independent golden logic and return nonzero on
  failure.
- Require kernel specs to state dtype, inputs, outputs, and independent golden
  logic; kernel success must inspect cannsim verification output.
- Add unit tests for mapped/deferred test classification and guards against
  using the tested `ascend::std::*` API as the expected value.

### Node 14: First AI-Driven Real Algorithm Batch

Goal: run the first dependency-aware AI migration batch on real CCCL algorithms.

- Choose the batch from Node 10 planning rather than from a hand-picked broad
  pending list.
- Candidate family: `find`, `find_if`, `count`, `count_if`, `all_of`,
  `any_of`, and `none_of`, subject to dependency and test suitability.
- Use Nodes 11-13 to generate headers, host tests, and kernel specs.
- Run relevant host/kernel tests, pytest, and selftest.
- Update `docs/migration_ledger.md`, `outputs/migration_status.json`, and
  `docs/codex_handoff.md`.
- Promote only validated results into `examples/`.

### Node 15: Minimal Iterator and Range Support

Goal: migrate only the iterator/range support required by the first real
algorithm batch.

- Use Node 14 failures and dependency reports to identify the smallest required
  iterator/type-trait support set.
- Prefer focused internal headers over broad public aggregation.
- Add host include/semantic tests for each migrated foundational piece.
- Add `ascend/std/iterator` only after the underlying internals are prepared and
  validated.

### Node 16: AI Repair Loop Hardening

Goal: improve model repair success while avoiding useless retries.

- Refine failure classification for missing includes, namespace/macro issues,
  missing type traits, semantic mismatches, kernel scaffold limits, and CANN/env
  failures.
- Feed AI repair with concise, high-value logs and current artifact context.
- Track per-attempt root cause, changed artifacts, and result so repeated
  ineffective fixes can be avoided.
- Add unit tests for representative failure classifications.

### Node 17: Promotion and Example Curation v2

Goal: make validated real migrations improve future AI few-shot behavior.

- Extend example promotion to record source header, upstream test evidence,
  ACCL header, host test, kernel spec, and validation notes.
- Promote only real-upstream mapped and validated results.
- Exclude fixture-only and incomplete generated artifacts from gold examples.
- Ensure retrieval prefers relevant validated examples for nearby algorithms.

### Node 18: Broader Batch Migration Gate

Goal: define the gate for safely moving from small AI-driven batches to larger
batch migration.

- Define batch eligibility criteria: dependency closure known, missing
  dependencies classified, mapped tests or substitutes available, AI context
  pack available, and host/kernel validation path clear.
- Add batch manifest v2 planning that supports dry-run planning, mock AI runs,
  and explicit real AI runs.
- Produce batch-level reports and update ledger/status after each batch.
- Do not default to broad writes or real API calls without an explicit task
  request.

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
