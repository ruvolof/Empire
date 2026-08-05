import logging
import os
import platform
import tarfile
from pathlib import Path

import requests

from empire.server.core.config import config_manager
from empire.server.core.config.config_manager import (
    EmpireCompilerConfig,
    PluginRegistryConfig,
    StarkillerConfig,
)
from empire.server.utils.git_util import clone_git_repo

log = logging.getLogger(__name__)


def sync_starkiller(starkiller_config: StarkillerConfig):
    starkiller_dir = config_manager.DATA_DIR / "starkiller" / starkiller_config.ref

    if not Path(starkiller_dir).exists():
        log.info("Starkiller: directory not found. Cloning Starkiller")
        clone_git_repo(starkiller_config.repo, starkiller_config.ref, starkiller_dir)

    return starkiller_dir


def _resolve_compiler_platform():
    """Return (os, arch) strings used in compiler asset names, or (None, None)."""
    os_ = platform.system()
    arch = platform.machine()

    if os_ == "Darwin":
        os_ = "osx"
    elif os_ == "Linux":
        os_ = "linux"
    else:
        log.error(f"Empire Compiler: unsupported OS '{os_}'")
        return None, None

    if arch == "x86_64":
        arch = "x64"
    elif arch in ["aarch64", "arm64"]:
        arch = "arm64"
    else:
        log.error(f"Empire Compiler: unsupported architecture '{arch}'")
        return None, None

    return os_, arch


def _github_api_headers() -> dict[str, str]:
    """Headers for the GitHub REST API.

    Adds bearer auth when ``GITHUB_TOKEN``/``GH_TOKEN`` is present so requests
    aren't subject to GitHub's 60 req/hr unauthenticated limit. That limit is
    keyed on the egress IP, which CI runners share, so unauthenticated calls
    routinely 403 during test runs.
    """
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _resolve_compiler_download_url(
    compiler_config: EmpireCompilerConfig, platform_str: str
) -> str | None:
    """Resolve the download URL for the compiler archive.

    Queries the GitHub Releases API using ``repo`` and ``ref``.
    """
    if not compiler_config.repo or not compiler_config.ref:
        log.error("Empire Compiler: 'repo' and 'ref' must be configured")
        return None

    api_url = f"https://api.github.com/repos/{compiler_config.repo}/releases/tags/{compiler_config.ref}"
    log.info(f"Empire Compiler: querying GitHub release {api_url}")
    resp = requests.get(api_url, timeout=30, headers=_github_api_headers())
    if not resp.ok:
        log.error(
            f"Empire Compiler: failed to fetch release info ({resp.status_code}): {resp.text}"
        )
        return None

    assets = resp.json().get("assets", [])
    for asset in assets:
        name = asset.get("name", "")
        if platform_str in name and name.endswith(".tgz"):
            return asset["browser_download_url"]

    log.error(
        f"Empire Compiler: no matching asset for platform '{platform_str}' in release {compiler_config.ref}"
    )
    return None


def _configure_compiler(
    compiler_config: EmpireCompilerConfig, extracted_folder: Path
) -> Path:
    """Write the ConfuserEx project file if it doesn't already exist."""
    confuser_proj_dir = extracted_folder / "EmpireCompiler"
    confuser_base_dir = confuser_proj_dir / "Data" / "Temp"
    confuser_output_dir = confuser_base_dir / "confused_out"
    confuser_project_file = confuser_base_dir / "empire.crproj"

    if not confuser_project_file.exists():
        confuser_template = Path(compiler_config.confuser_proj).read_text()
        confuser_project_file.parent.mkdir(parents=True, exist_ok=True)
        confuser_project_file.write_text(
            confuser_template.format(
                confuser_base_dir=confuser_base_dir,
                confuser_output_dir=confuser_output_dir,
                confuser_module_path="confused.exe",
                confuser_proj_dir=confuser_proj_dir,
            ),
            encoding="utf-8",
        )

    return extracted_folder


def sync_empire_compiler(compiler_config: EmpireCompilerConfig):
    # Allow a local directory override so developers can test without
    # publishing a GitHub release (mirrors how Starkiller handles this).
    if compiler_config.directory:
        local_dir = Path(compiler_config.directory)
        if local_dir.exists():
            log.info(f"Empire Compiler: using local directory {local_dir}")
            return _configure_compiler(compiler_config, local_dir)
        log.warning(
            f"Empire Compiler: configured directory '{compiler_config.directory}' does not exist, falling back to download"
        )

    os_, arch = _resolve_compiler_platform()
    if os_ is None:
        return None

    platform_str = f"{os_}-{arch}"
    compiler_dir = config_manager.DATA_DIR / "empire-compiler"

    # Check for any existing directory matching this platform before hitting
    # the GitHub API, so cached compilers don't require network access.
    if compiler_dir.exists():
        for d in compiler_dir.iterdir():
            if d.is_dir() and platform_str in d.name:
                log.info(f"Empire Compiler: using cached {d.name}")
                return _configure_compiler(compiler_config, d)

    url = _resolve_compiler_download_url(compiler_config, platform_str)
    if url is None:
        return None

    name = url.split("/")[-1].removesuffix(".tgz")

    if not Path(compiler_dir / name).exists():
        log.info("Empire Compiler: directory not found. Downloading Empire Compiler")
        log.info(f"Empire Compiler: fetching and unarchiving {url}")
        compiler_dir.mkdir(parents=True, exist_ok=True)
        with (
            requests.get(url, stream=True, timeout=30) as resp,
            tarfile.open(fileobj=resp.raw, mode="r|gz") as tar,
        ):
            # filter="data" guards against path traversal in the downloaded archive.
            tar.extractall(compiler_dir, filter="data")

    extracted_folder = compiler_dir / name
    return _configure_compiler(compiler_config, extracted_folder)


def sync_plugin_registry(registry_config: PluginRegistryConfig):
    base_dir = config_manager.DATA_DIR / "plugin-registries" / registry_config.name
    base_dir.mkdir(parents=True, exist_ok=True)

    # If a local location is provided, prefer it as-is (no copy) for speed
    if registry_config.location:
        return registry_config.location

    # Clone a git-based registry into a persistent offline directory
    if registry_config.git_url:
        ref = registry_config.ref or "main"
        target_dir = base_dir / ref

        if not target_dir.exists():
            log.info(
                f"Plugin Registry: directory not found for {registry_config.name}. Cloning {registry_config.git_url} ({ref})"
            )
            clone_git_repo(registry_config.git_url, ref, target_dir)

        return target_dir / (registry_config.file or "registry.yaml")

    # Fallback: download from URL and cache to disk for offline use
    if registry_config.url:
        registry_file = base_dir / "registry.yaml"
        log.info(
            f"Plugin Registry: downloading {registry_config.name} from {registry_config.url}"
        )
        resp = requests.get(registry_config.url, timeout=30)
        if resp.ok:
            registry_file.write_text(resp.text)
            return registry_file
        log.error(
            f"Failed to download plugin registry {registry_config.name} from {registry_config.url}"
        )
        return None

    return None
