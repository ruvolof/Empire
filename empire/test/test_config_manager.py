"""Regression tests for empire.server.core.config.config_manager."""

from __future__ import annotations

import os
import subprocess
import sys

from empire.server.core.config.config_manager import DATA_DIR


def test_config_manager_import_does_not_wipe_data_dir():
    """Importing config_manager in a TEST_MODE subprocess must NOT delete
    pre-existing DATA_DIR contents.

    Regression for the bug fixed by the
    2026-05-26-test-mode-data-dir-wipe spec: the rmtree at config_manager
    module-import time used to nuke the EmpireCompiler cache the parent
    pytest process had just downloaded, defeating the
    `empire_base_url` perf-test fixture's reuse of that cache.
    """
    assert os.environ.get("TEST_MODE"), (
        "TEST_MODE must be set for this test to exercise the wipe path. "
        "Run via pytest (which reads pytest.ini's `env = TEST_MODE=true`), "
        "not bare python."
    )

    sentinel = DATA_DIR / "test_config_manager_sentinel.txt"
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    try:
        sentinel.write_text("must_survive")
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import empire.server.core.config.config_manager",
            ],
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"subprocess crashed during config_manager import:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert sentinel.exists(), (
            "config_manager module import wiped DATA_DIR (regression "
            "of the 2026-05-26 spec). The wipe must live only in "
            "root conftest.py::_reset_test_dirs."
        )
    finally:
        sentinel.unlink(missing_ok=True)
