from pathlib import Path, PurePosixPath
from unittest.mock import MagicMock, patch

import pytest
import yaml

from empire.server.core.config.config_manager import EmpireCompilerConfig
from empire.server.core.config.data_manager import (
    _resolve_compiler_download_url,
    _resolve_compiler_platform,
)

STAGERS_DIR = Path(__file__).resolve().parent.parent / "server" / "stagers"
LAUNCHER_RESOURCE_RELATIVE_PATH = "common/launcher.txt"


@patch("empire.server.core.config.data_manager.platform")
def test_resolve_platform_linux_x86_64(mock_platform):
    mock_platform.system.return_value = "Linux"
    mock_platform.machine.return_value = "x86_64"
    assert _resolve_compiler_platform() == ("linux", "x64")


@patch("empire.server.core.config.data_manager.platform")
def test_resolve_platform_darwin_arm64(mock_platform):
    mock_platform.system.return_value = "Darwin"
    mock_platform.machine.return_value = "arm64"
    assert _resolve_compiler_platform() == ("osx", "arm64")


@patch("empire.server.core.config.data_manager.platform")
def test_resolve_platform_darwin_aarch64(mock_platform):
    mock_platform.system.return_value = "Darwin"
    mock_platform.machine.return_value = "aarch64"
    assert _resolve_compiler_platform() == ("osx", "arm64")


@patch("empire.server.core.config.data_manager.platform")
def test_resolve_platform_linux_arm64(mock_platform):
    mock_platform.system.return_value = "Linux"
    mock_platform.machine.return_value = "arm64"
    assert _resolve_compiler_platform() == ("linux", "arm64")


def test_download_url_missing_repo_and_ref():
    config = EmpireCompilerConfig()
    assert _resolve_compiler_download_url(config, "linux-x64") is None


def test_download_url_missing_ref():
    config = EmpireCompilerConfig(repo="BC-SECURITY/Empire-Compiler")
    assert _resolve_compiler_download_url(config, "linux-x64") is None


@patch("empire.server.core.config.data_manager.requests")
def test_download_url_repo_ref_finds_asset(mock_requests, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "assets": [
            {
                "name": "EmpireCompiler-linux-x64-v1.0.0-a.1.tgz",
                "browser_download_url": "https://github.com/downloads/EmpireCompiler-linux-x64-v1.0.0-a.1.tgz",
            },
            {
                "name": "EmpireCompiler-osx-arm64-v1.0.0-a.1.tgz",
                "browser_download_url": "https://github.com/downloads/EmpireCompiler-osx-arm64-v1.0.0-a.1.tgz",
            },
        ]
    }
    mock_requests.get.return_value = mock_resp

    config = EmpireCompilerConfig(repo="BC-SECURITY/Empire-Compiler", ref="v1.0.0-a.1")
    url = _resolve_compiler_download_url(config, "linux-x64")
    assert url == "https://github.com/downloads/EmpireCompiler-linux-x64-v1.0.0-a.1.tgz"

    mock_requests.get.assert_called_once_with(
        "https://api.github.com/repos/BC-SECURITY/Empire-Compiler/releases/tags/v1.0.0-a.1",
        timeout=30,
        headers={"Accept": "application/vnd.github+json"},
    )


@patch("empire.server.core.config.data_manager.requests")
def test_download_url_authenticates_when_token_present(mock_requests, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "tok_abc123")
    monkeypatch.delenv("GH_TOKEN", raising=False)
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"assets": []}
    mock_requests.get.return_value = mock_resp

    config = EmpireCompilerConfig(repo="BC-SECURITY/Empire-Compiler", ref="v1.0.0")
    _resolve_compiler_download_url(config, "linux-x64")

    headers = mock_requests.get.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer tok_abc123"


@patch("empire.server.core.config.data_manager.requests")
def test_download_url_falls_back_to_gh_token(mock_requests, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GH_TOKEN", "tok_gh")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"assets": []}
    mock_requests.get.return_value = mock_resp

    config = EmpireCompilerConfig(repo="BC-SECURITY/Empire-Compiler", ref="v1.0.0")
    _resolve_compiler_download_url(config, "linux-x64")

    headers = mock_requests.get.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer tok_gh"


@patch("empire.server.core.config.data_manager.requests")
def test_download_url_unauthenticated_when_no_token(mock_requests, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"assets": []}
    mock_requests.get.return_value = mock_resp

    config = EmpireCompilerConfig(repo="BC-SECURITY/Empire-Compiler", ref="v1.0.0")
    _resolve_compiler_download_url(config, "linux-x64")

    headers = mock_requests.get.call_args.kwargs["headers"]
    assert "Authorization" not in headers


@patch("empire.server.core.config.data_manager.requests")
def test_download_url_repo_ref_no_matching_asset(mock_requests):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "assets": [
            {
                "name": "EmpireCompiler-osx-arm64-v1.0.0-a.1.tgz",
                "browser_download_url": "https://example.com/osx.tgz",
            },
        ]
    }
    mock_requests.get.return_value = mock_resp

    config = EmpireCompilerConfig(repo="BC-SECURITY/Empire-Compiler", ref="v1.0.0-a.1")
    assert _resolve_compiler_download_url(config, "linux-x64") is None


@patch("empire.server.core.config.data_manager.requests")
def test_download_url_repo_ref_api_failure(mock_requests):
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 404
    mock_resp.text = "Not Found"
    mock_requests.get.return_value = mock_resp

    config = EmpireCompilerConfig(repo="BC-SECURITY/Empire-Compiler", ref="v99.0.0")
    assert _resolve_compiler_download_url(config, "linux-x64") is None


def _find_launcher_locations(entries):
    """Recursively find launcher.txt Location values in YAML task entries."""
    locations = []
    if not entries:
        return locations
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for res in entry.get("EmbeddedResources", []) or []:
            if isinstance(res, dict) and res.get("Name") == "launcher.txt":
                locations.append(res["Location"])
        for lib in entry.get("ReferenceSourceLibraries", []) or []:
            if isinstance(lib, dict):
                for res in lib.get("EmbeddedResources", []) or []:
                    if isinstance(res, dict) and res.get("Name") == "launcher.txt":
                        locations.append(res["Location"])
    return locations


@pytest.mark.parametrize("stager_file", ["CSharpPS.yaml", "CSharpPy.yaml"])
def test_stager_yaml_launcher_path_matches_service(stager_file):
    """Verify that stager YAML EmbeddedResources Location for launcher.txt
    is consistent with the path used in StagerGenerationService._write_launcher_resource.
    """
    stager_data = yaml.safe_load(
        (STAGERS_DIR / stager_file).read_text(encoding="utf-8")
    )
    entries = stager_data if isinstance(stager_data, list) else [stager_data]

    launcher_locations = _find_launcher_locations(entries)

    assert launcher_locations, (
        f"No launcher.txt EmbeddedResource found in {stager_file}"
    )
    for loc in launcher_locations:
        normalised = str(PurePosixPath(loc.replace("\\", "/")))
        assert normalised == LAUNCHER_RESOURCE_RELATIVE_PATH, (
            f"{stager_file}: EmbeddedResources Location '{loc}' does not match "
            f"expected '{LAUNCHER_RESOURCE_RELATIVE_PATH}'"
        )
