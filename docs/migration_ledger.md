# Migration Ledger

Last updated: 2026-06-06

This ledger tracks migration completion at a human-readable level until an automated
inventory/status generator is implemented.

Status values:

- `pending`: not migrated yet.
- `generated`: ACCL header exists but semantic validation is incomplete.
- `host_passed`: host semantic tests passed.
- `kernel_passed`: host and kernel tests passed where applicable.
- `full_passed`: all applicable tests and repo checks passed.
- `blocked_env`: blocked by environment setup.
- `blocked_design`: blocked by missing design or unsupported mapping.

## Current Sample Targets

| Source area | Item | Status | Notes |
| --- | --- | --- | --- |
| `__cccl` | `os.h` | generated | Historical successful sample in v2/ASC_AGENT examples. Needs real upstream revalidation. |
| `__algorithm` | `max.h` | generated | Existing ACCL header and tests in `repos/accl`; treat as sample, not final upstream completion. |
| `__algorithm` | `min.h` | generated | Existing ACCL header and tests in `repos/accl`; needs real upstream test mapping. |
| `__algorithm` | `swap.h` | generated | Existing sample covers original void/in-place shape. |
| `__algorithm` | `clamp.h` | generated | Existing sample and kernel spec present. |
| `__algorithm` | `minmax.h` | host_passed | Now depends on migrated `__utility/pair.h` instead of an inline pair substitute. Local foundational pytest and `host.minmax` passed; real upstream revalidation remains Node 6. |
| `__utility` | `move.h` | host_passed | Bootstrap ACCL implementation passed focused g++ semantic coverage in `tests/test_foundational_dependencies.py`. |
| `__utility` | `forward.h` | host_passed | Bootstrap ACCL implementation passed focused g++ semantic coverage in `tests/test_foundational_dependencies.py`. |
| `__utility` | `pair.h` | host_passed | Bootstrap ACCL implementation passed value, move-only, and reference-pair coverage in `tests/test_foundational_dependencies.py`. |
| `__functional` | `identity.h` | host_passed | Bootstrap ACCL implementation passed focused g++ semantic coverage in `tests/test_foundational_dependencies.py`. |
| `__functional` | `operations.h` | host_passed | Bootstrap ACCL implementation passed focused g++ semantic coverage in `tests/test_foundational_dependencies.py`. |
| `__algorithm` | `comp.h` | host_passed | Bootstrap ACCL comparator helpers passed focused g++ semantic coverage in `tests/test_foundational_dependencies.py`. |
| `__numeric` | `gcd.h` | pending | Listed in batch manifest; integer dtype tests should be used. |
| `__numeric` | `lcm.h` | pending | Listed in batch manifest; integer dtype tests should be used. |
| `__numeric` | `midpoint.h` | pending | Listed in batch manifest; needs overflow-sensitive host tests. |

## Ledger Rules

- Do not mark `full_passed` without recording the exact tests/checks that passed.
- If a test is skipped because CANN/cannsim is unavailable, keep the item below `kernel_passed`.
- For type traits or pure compile-time utilities, record the static/host tests used instead of kernel tests.
- Prefer adding entries as batches are planned, then updating status after validation.
