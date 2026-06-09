import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


ACCL_INCLUDE = (
    Path(__file__).resolve().parents[1]
    / "repos/accl/libascendcxx/include"
)


@pytest.mark.skipif(
    not shutil.which("g++"),
    reason="requires g++ for ACCL foundational header semantic check",
)
def test_accl_foundational_dependencies_compile_and_run(tmp_path: Path) -> None:
    source = tmp_path / "foundational_dependencies.cpp"
    exe = tmp_path / "foundational_dependencies"
    source.write_text(
        textwrap.dedent(
            """
            #include "ascend/std/__type_traits/integral_constant.h"
            #include "ascend/std/__type_traits/remove_reference.h"
            #include "ascend/std/__type_traits/is_reference.h"
            #include "ascend/std/__type_traits/is_same.h"
            #include "ascend/std/__type_traits/conditional.h"
            #include "ascend/std/__utility/move.h"
            #include "ascend/std/__utility/forward.h"
            #include "ascend/std/__utility/pair.h"
            #include "ascend/std/__functional/identity.h"
            #include "ascend/std/__functional/operations.h"
            #include "ascend/std/__algorithm/comp.h"
            #include "ascend/std/__algorithm/minmax.h"

            static_assert(ascend::std::true_type::value, "true_type");
            static_assert(!ascend::std::false_type::value, "false_type");
            static_assert(ascend::std::is_same_v<ascend::std::remove_reference_t<int&>, int>, "remove_reference");
            static_assert(ascend::std::is_lvalue_reference_v<int&>, "lvalue reference");
            static_assert(ascend::std::is_rvalue_reference_v<int&&>, "rvalue reference");
            static_assert(ascend::std::is_same_v<ascend::std::conditional_t<true, int, long>, int>, "conditional true");
            static_assert(ascend::std::is_same_v<ascend::std::conditional_t<false, int, long>, long>, "conditional false");
            static_assert(ascend::std::__is_identity_v<ascend::std::identity>, "identity marker");

            struct MoveOnly {
              int value;

              explicit constexpr MoveOnly(int v) : value(v) {}
              MoveOnly(const MoveOnly&) = delete;
              MoveOnly& operator=(const MoveOnly&) = delete;

              constexpr MoveOnly(MoveOnly&& other) : value(other.value) {
                other.value = -1;
              }

              constexpr MoveOnly& operator=(MoveOnly&& other) {
                value = other.value;
                other.value = -1;
                return *this;
              }
            };

            constexpr int category(int&) { return 1; }
            constexpr int category(int&&) { return 2; }

            template <class T>
            constexpr int forward_category(T&& value) {
              return category(ascend::std::forward<T>(value));
            }

            int main() {
              int failures = 0;

              int x = 3;
              if (forward_category(x) != 1) {
                ++failures;
              }
              if (forward_category(3) != 2) {
                ++failures;
              }

              MoveOnly moved_from(7);
              MoveOnly moved_to(ascend::std::move(moved_from));
              if (moved_to.value != 7 || moved_from.value != -1) {
                ++failures;
              }

              ascend::std::pair<int, int> values(4, 9);
              if (values.first != 4 || values.second != 9) {
                ++failures;
              }

              ascend::std::pair<MoveOnly, int> move_pair(MoveOnly(11), 5);
              if (move_pair.first.value != 11 || move_pair.second != 5) {
                ++failures;
              }

              int a = 8;
              int b = 2;
              ascend::std::pair<int&, int&> refs(a, b);
              refs.first = 10;
              refs.second = 20;
              if (a != 10 || b != 20) {
                ++failures;
              }

              auto ordered = ascend::std::minmax(a, b);
              if (&ordered.first != &a || &ordered.second != &b) {
                ++failures;
              }

              auto tied = ascend::std::minmax(a, a);
              if (&tied.first != &a || &tied.second != &a) {
                ++failures;
              }

              auto descending = ascend::std::minmax(a, b, ascend::std::greater<int>());
              if (&descending.first != &b || &descending.second != &a) {
                ++failures;
              }

              int id_value = 13;
              auto&& id_ref = ascend::std::identity()(id_value);
              id_ref = 21;
              if (id_value != 21) {
                ++failures;
              }

              if (ascend::std::plus<int>()(2, 5) != 7) {
                ++failures;
              }
              if (!ascend::std::less<void>()(2, 5)) {
                ++failures;
              }
              if (!ascend::std::__less()(2, 5)) {
                ++failures;
              }
              if (!ascend::std::__equal_to()(5, 5)) {
                ++failures;
              }

              return failures == 0 ? 0 : 1;
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )

    compile_proc = subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-I",
            str(ACCL_INCLUDE),
            str(source),
            "-o",
            str(exe),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert compile_proc.returncode == 0, compile_proc.stderr

    run_proc = subprocess.run(
        [str(exe)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert run_proc.returncode == 0, run_proc.stderr
