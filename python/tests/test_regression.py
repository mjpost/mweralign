#!/usr/bin/env python3
"""
Golden-file regression tests for the ``mweralign`` command-line interface.

Each subdirectory of ``regression/`` is a test case containing:

* ``cmd``          - the command-line arguments to pass to ``mweralign``
                     (relative paths, ``-o`` is added automatically).
* input files      - referenced by the ``cmd`` line (e.g. ``ref.txt``,
                     ``hyp.txt``, ``docids.txt``).
* ``expected.txt`` - the golden output the CLI is expected to produce.

To (re)generate the golden ``expected.txt`` files after an intentional
behavior change, run::

    MWERALIGN_REGEN=1 pytest python/tests/test_regression.py

Copyright (c) 2025 Matt Post

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0
"""

import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REGRESSION_DIR = Path(__file__).parent / "regression"
REGEN = os.environ.get("MWERALIGN_REGEN") == "1"


def _discover_cases():
    if not REGRESSION_DIR.is_dir():
        return []
    return sorted(p for p in REGRESSION_DIR.iterdir() if (p / "cmd").is_file())


def _run_case(case_dir: Path) -> str:
    """Run the CLI for a case and return the contents of its output file."""
    args = shlex.split((case_dir / "cmd").read_text().strip())
    out_path = case_dir / "actual.txt"
    cmd = [sys.executable, "-m", "mweralign.mweralign", *args, "-o", str(out_path)]
    result = subprocess.run(
        cmd,
        cwd=case_dir,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"mweralign failed for case {case_dir.name!r}\n"
        f"stderr:\n{result.stderr}"
    )
    output = out_path.read_text()
    out_path.unlink(missing_ok=True)
    return output


@pytest.mark.parametrize(
    "case_dir", _discover_cases(), ids=lambda p: p.name
)
def test_regression(case_dir: Path):
    output = _run_case(case_dir)
    expected_path = case_dir / "expected.txt"

    if REGEN or not expected_path.exists():
        expected_path.write_text(output)
        if REGEN:
            pytest.skip(f"regenerated golden output for {case_dir.name}")
        pytest.fail(
            f"missing golden output for {case_dir.name}; generated it now, "
            "re-run the tests to verify"
        )

    expected = expected_path.read_text()
    assert output == expected, (
        f"output mismatch for case {case_dir.name!r}\n"
        f"--- expected ---\n{expected}\n--- actual ---\n{output}"
    )


def test_cases_exist():
    """Guard against the regression suite silently becoming empty."""
    assert _discover_cases(), "no regression cases were discovered"
