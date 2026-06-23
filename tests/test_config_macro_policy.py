import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ASC_INCLUDE = (
    Path(__file__).resolve().parents[1]
    / "repos/accl/asc-stl/include"
)


@pytest.mark.skipif(
    not shutil.which("g++"),
    reason="requires g++ for header syntax check",
)
def test_asc_config_exposes_canonical_macros(tmp_path: Path) -> None:
    source = tmp_path / "config_macro_check.cpp"
    source.write_text(
        textwrap.dedent(
            """
            #include "asc/std/__config"

            #ifndef _ASC_AICORE_FN
            #error "_ASC_AICORE_FN should define the canonical function annotation"
            #endif

            #ifndef _ASC_STD_BEGIN
            #error "_ASC_STD_BEGIN should define the canonical namespace macro"
            #endif

            #if _ASC_STD_NO_EXCEPTIONS != 1
            #error "_ASC_STD_NO_EXCEPTIONS should default to 1 on host"
            #endif

            _ASC_STD_BEGIN

            template <class T>
            _ASC_AICORE_FN constexpr T config_identity(T value) {
                return value;
            }

            _ASC_STD_END

            static_assert(
                _ASC_STD::config_identity(7) == 7,
                "canonical namespace failed"
            );
            """
        ).lstrip(),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            "g++",
            "-fsyntax-only",
            "-std=c++17",
            "-I",
            str(ASC_INCLUDE),
            str(source),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert proc.returncode == 0, proc.stderr
