import os
import shutil
from pathlib import Path

import pytest

# Paths must stay in sync with config_manager.py's TEST_MODE branch.
_REPO_ROOT = Path(__file__).resolve().parent
_TEST_CONFIG_DIR = Path.home() / ".config" / "empire-test"
_TEST_DATA_DIR = Path.home() / ".local" / "share" / "empire-test"


def pytest_addoption(parser):
    parser.addoption(
        "--runslow", action="store_true", default=False, help="run slow tests"
    )
    parser.addoption(
        "--nodocker",
        action="store_true",
        default=False,
        help="skip tests that fail in docker",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: mark test as slow to run")
    config.addinivalue_line("markers", "no_docker: mark test as failing in docker")
    config.addinivalue_line(
        "markers", "compiler: requires C# compiler (EmpireCompiler)"
    )
    config.addinivalue_line(
        "markers", "mysql: mark test as requiring MySQL (and Docker)"
    )
    _reset_test_dirs()


def _reset_test_dirs():
    """Wipe and reseed test-mode CONFIG_DIR and DATA_DIR once per pytest session.

    The wipe used to live as a module-import side-effect in config_manager.py.
    That meant every subprocess (e.g. the perf-test Empire server) re-wiped the
    directory, defeating the in-process compiler cache. Owning it here in
    pytest_configure lets the wipe fire exactly once.

    The invariant we rely on: nothing imported during pytest startup or
    initial-conftest loading transitively imports config_manager. The first
    config_manager import happens later (during collection of test modules
    or fixture execution), by which point _reset_test_dirs has already run
    and empire/test/conftest.py has set sys.argv to point at
    test_server_config.yaml. So config_manager's module body — and the
    empire_config singleton it builds — uses the test config and sees a
    clean DATA_DIR.
    """
    if not os.environ.get("TEST_MODE"):
        return

    shutil.rmtree(_TEST_CONFIG_DIR, ignore_errors=True)
    shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True)
    _TEST_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        _REPO_ROOT / "empire/test/test_registry_1.yaml",
        _TEST_DATA_DIR / "test_registry_1.yaml",
    )
    shutil.copy(
        _REPO_ROOT / "empire/test/test_registry_2.yaml",
        _TEST_DATA_DIR / "test_registry_2.yaml",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--runslow"):
        pass
    else:
        skip_slow = pytest.mark.skip(reason="need --runslow option to run")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)

    if config.getoption("--nodocker"):
        skip_docker = pytest.mark.skip(reason="skipping tests that fail in docker")
        for item in items:
            if "no_docker" in item.keywords:
                item.add_marker(skip_docker)
