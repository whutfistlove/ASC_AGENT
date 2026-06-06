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
    reason="requires g++ for header syntax check",
)
def test_accl_config_exposes_accl_alias_macros(tmp_path: Path) -> None:
    source = tmp_path / "config_alias_check.cpp"
    source.write_text(
        textwrap.dedent(
            """
            #define _ACCL_STD_NO_EXCEPTIONS 0
            #include "ascend/std/__config"

            #ifndef _ACCL_AICORE_FN
            #error "_ACCL_AICORE_FN should alias the canonical function annotation"
            #endif

            #ifndef _ACCL_STD_BEGIN
            #error "_ACCL_STD_BEGIN should alias the canonical namespace macro"
            #endif

            #if _ASCEND_STD_NO_EXCEPTIONS != 0
            #error "_ACCL_STD_NO_EXCEPTIONS should feed the canonical exception flag"
            #endif

            _ACCL_STD_BEGIN

            template <class T>
            _ACCL_AICORE_FN constexpr T config_alias_identity(T value) {
                return value;
            }

            _ACCL_STD_END

            static_assert(
                _ACCL_STD::config_alias_identity(7) == 7,
                "alias namespace failed"
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
            str(ACCL_INCLUDE),
            str(source),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert proc.returncode == 0, proc.stderr
