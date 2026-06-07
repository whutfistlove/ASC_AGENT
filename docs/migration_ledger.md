# Migration Ledger

Last updated: 2026-06-07

This ledger tracks migration completion at a human-readable level. Node 9 now
also provides a machine-readable report generated from real CCCL inventory,
test indexing, dependency graph data, the ACCL target tree, and this ledger's
validation status rows.

Status values:

- `pending`: not migrated yet.
- `generated`: ACCL header exists but semantic validation is incomplete.
- `host_passed`: host semantic tests passed.
- `kernel_passed`: host and kernel tests passed where applicable.
- `full_passed`: all applicable tests and repo checks passed.
- `blocked_env`: blocked by environment setup.
- `blocked_design`: blocked by missing design or unsupported mapping.

## Automated Status Report

Generate the deterministic JSON report with:

```bash
conda run -n accl python main.py migration-status --cccl-repo /home/zhenyu/projects/cccl
```

Current report path: `outputs/migration_status.json`.

Current real scan summary:

| Metric | Value |
| --- | ---: |
| Real CCCL headers scanned | 786 |
| Source-mapped migrated headers | 23 |
| ACCL target-only headers | 6 |
| Header/test mappings | 65 |
| Unmapped tests | 68 |
| Missing dependency edges from migrated source headers | 439 |

Current source-mapped status counts:

| Status | Count |
| --- | ---: |
| pending | 763 |
| generated | 5 |
| host_passed | 11 |
| kernel_passed | 7 |
| full_passed | 0 |
| blocked_env | 0 |
| blocked_design | 0 |

Notes:

- `missing_dependencies` is the raw difference between upstream CCCL include
  dependencies and files present in the ACCL target tree for headers that have
  an ACCL counterpart. For intentionally narrowed public aggregation headers
  and hand-authored bootstrap headers, it is a planning signal rather than an
  automatic failure.
- `target_only_headers` records ACCL compatibility wrappers and historical
  synthetic samples that do not map one-to-one to real CCCL headers.
- `outputs/` remains generated output and must not become source input for
  migration logic.

## Current Sample Targets

| Source area | Item | Status | Notes |
| --- | --- | --- | --- |
| `__cccl` | `os.h` | generated | Historical successful sample in v2/ASC_AGENT examples. Needs real upstream revalidation. |
| `__algorithm` | `max.h` | kernel_passed | Node 6 real revalidation mapped upstream header and tests from `/home/zhenyu/projects/cccl/libcudacxx`: applicable tests are `max.pass.cpp` and `max_comp.pass.cpp`; `max_element*` and `max_init_list*` are deferred until those dependencies are migrated. ACCL host test uses independent golden logic and passed with `host.max`. Kernel fast cannsim uses independent golden `(x_ref < y_ref) ? y_ref : x_ref` and passed with `outputs/kernel_test_max.log` (`KERNEL_SIM_RESULT: PASS`). |
| `__algorithm` | `min.h` | kernel_passed | Node 6 real revalidation mapped upstream header and tests: applicable tests are `min.pass.cpp` and `min_comp.pass.cpp`; `min_element*` and `min_init_list*` are deferred. ACCL host test uses independent golden logic and passed with `host.min`. Kernel fast cannsim uses independent golden `(y_ref < x_ref) ? y_ref : x_ref` and passed with `outputs/kernel_test_min.log` (`KERNEL_SIM_RESULT: PASS`). |
| `__algorithm` | `clamp.h` | kernel_passed | Node 6 real revalidation mapped upstream `clamp.pass.cpp` and `clamp.comp.pass.cpp`. ACCL host test uses independent golden logic and passed with `host.clamp`. Kernel fast cannsim uses independent clamp golden logic and passed with `outputs/kernel_test_clamp.log` (`KERNEL_SIM_RESULT: PASS`). |
| `__utility` | `swap.h` | kernel_passed | Node 6 corrected the real upstream source area from historical `__algorithm/swap.h` to `__utility/swap.h`; `__algorithm/swap.h` remains a compatibility wrapper. Real tests mapped to `utility.swap/swap.pass.cpp` and `swap_array.pass.cpp`. ACCL host test includes `__utility/swap.h`, uses independent golden logic, and passed with `host.swap`. Kernel fast cannsim verifies the swapped first value against `y_ref` and passed with `outputs/kernel_test_swap.log` (`KERNEL_SIM_RESULT: PASS`). |
| `__algorithm` | `minmax.h` | kernel_passed | Node 6 real revalidation mapped upstream header and tests: applicable tests are `minmax.pass.cpp` and `minmax_comp.pass.cpp`; `minmax_element*` and `minmax_init_list*` are deferred. Header depends on migrated `__utility/pair.h`. ACCL host test uses independent golden logic and passed with `host.minmax`. Kernel fast cannsim verifies both pair outputs with independent golden logic and passed with `outputs/kernel_test_minmax.log` (`KERNEL_SIM_RESULT: PASS`). |
| `__utility` | `move.h` | host_passed | Bootstrap ACCL implementation passed focused g++ semantic coverage in `tests/test_foundational_dependencies.py`. |
| `__utility` | `forward.h` | host_passed | Bootstrap ACCL implementation passed focused g++ semantic coverage in `tests/test_foundational_dependencies.py`. |
| `__utility` | `pair.h` | host_passed | Bootstrap ACCL implementation passed value, move-only, and reference-pair coverage in `tests/test_foundational_dependencies.py`. |
| `__functional` | `identity.h` | host_passed | Bootstrap ACCL implementation passed focused g++ semantic coverage in `tests/test_foundational_dependencies.py`. |
| `__functional` | `operations.h` | host_passed | Bootstrap ACCL implementation passed focused g++ semantic coverage in `tests/test_foundational_dependencies.py`. |
| `__algorithm` | `comp.h` | host_passed | Bootstrap ACCL comparator helpers passed focused g++ semantic coverage in `tests/test_foundational_dependencies.py`. |
| `__numeric` | `gcd_lcm.h` / `gcd.h` | kernel_passed | Node 7 real inventory maps upstream implementation to `/home/zhenyu/projects/cccl/libcudacxx/include/cuda/std/__numeric/gcd_lcm.h`; `gcd.h` is an ACCL compatibility wrapper for the current per-operator tool/test layout. Relevant upstream tests include `numeric.ops.gcd/gcd.pass.cpp` plus bool/non-integral compile-fail tests. ACCL host test uses independent Euclidean golden logic across signed, unsigned, mixed-width, negative, zero, and `INT32_MIN` cases and passed with `host.gcd`. Fast cannsim kernel uses `int32_t` and independent Euclidean golden logic and passed with `kernel.gcd.sim` (`KERNEL_SIM_RESULT: PASS`). Compile-fail tests are not yet wired into the ACCL scaffold. |
| `__numeric` | `gcd_lcm.h` / `lcm.h` | kernel_passed | Node 7 real inventory maps upstream implementation to shared `__numeric/gcd_lcm.h`; `lcm.h` is an ACCL compatibility wrapper. Relevant upstream tests include `numeric.ops.lcm/lcm.pass.cpp` plus bool/non-integral compile-fail tests. ACCL host test uses independent gcd-based lcm golden logic across zero, signed, unsigned, mixed-width, negative, and LWG#2837-style cases and passed with `host.lcm`. Fast cannsim kernel uses `int32_t` exact comparison and independent golden logic and passed with `kernel.lcm.sim` (`KERNEL_SIM_RESULT: PASS`). Compile-fail tests are not yet wired into the ACCL scaffold. |
| `__numeric` | `midpoint.h` | kernel_passed | Node 7 real inventory maps upstream implementation to `/home/zhenyu/projects/cccl/libcudacxx/include/cuda/std/__numeric/midpoint.h`; relevant upstream tests are `midpoint.integer.pass.cpp`, `midpoint.float.pass.cpp`, `midpoint.pointer.pass.cpp`, and `midpoint.verify.cpp`. ACCL host test uses independent wide-integer golden logic plus float and pointer checks and passed with `host.midpoint`. Fast cannsim kernel covers `int32_t` midpoint, including `INT32_MIN`/`INT32_MAX`, with independent `int64_t` golden logic and passed with `kernel.midpoint.sim` (`KERNEL_SIM_RESULT: PASS`). Float/pointer kernel variants and the upstream verify test are deferred because the current kernel scaffold is scalar dtype-based. |

## Public Aggregation Headers

| Public header | Status | Exposed validated components | Notes |
| --- | --- | --- | --- |
| `ascend/std/algorithm` | host_passed | `clamp`, `max`, `min`, `minmax`, `swap` | Node 8 includes only the real-upstream validated Node 6 algorithm surface plus the `swap` compatibility wrapper backed by validated `__utility/swap.h`. It intentionally excludes historical synthetic samples and broader algorithms. `host.public_algorithm` passed. |
| `ascend/std/numeric` | host_passed | `gcd`, `lcm`, `midpoint` | Node 8 keeps the public numeric header limited to Node 7 validated numeric APIs through the thin `gcd.h`/`lcm.h` wrappers and `midpoint.h`. `host.public_numeric` passed. |
| `ascend/std/type_traits` | host_passed | `conditional`, `integral_constant`, `is_reference`, `is_same`, `remove_reference` | Minimal foundational aggregation for headers already covered by Node 5 bootstrap semantic tests. `host.public_type_traits` passed. |
| `ascend/std/utility` | host_passed | `forward`, `move`, `pair`, `swap` | Minimal foundational aggregation for Node 5/6 validated utility pieces. `host.public_utility` passed. |
| `ascend/std/functional` | host_passed | `identity`, arithmetic/comparison function objects from `operations.h` | Minimal foundational aggregation for Node 5 validated functional pieces. `host.public_functional` passed. |
| `ascend/std/iterator` | pending | none | Not added in Node 8 because no iterator internals have been prepared and validated yet. |

## Ledger Rules

- Do not mark `full_passed` without recording the exact tests/checks that passed.
- If a test is skipped because CANN/cannsim is unavailable, keep the item below `kernel_passed`.
- For type traits or pure compile-time utilities, record the static/host tests used instead of kernel tests.
- Prefer adding entries as batches are planned, then updating status after validation.
