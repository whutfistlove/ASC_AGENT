# Migration Ledger

Last updated: 2026-06-07

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

## Ledger Rules

- Do not mark `full_passed` without recording the exact tests/checks that passed.
- If a test is skipped because CANN/cannsim is unavailable, keep the item below `kernel_passed`.
- For type traits or pure compile-time utilities, record the static/host tests used instead of kernel tests.
- Prefer adding entries as batches are planned, then updating status after validation.
