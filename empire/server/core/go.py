import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import jinja2

from empire.server.common.helpers import random_string
from empire.server.core.config.config_manager import empire_config
from empire.server.core.exceptions import ModuleExecutionException

log = logging.getLogger(__name__)


def _resolve_go_binary() -> str:
    """Return the path to the real Go binary, bypassing version-manager shims.

    goenv (and similar tools) install bash shim scripts named ``go`` that exec
    into ``goenv-exec``.  When the parent process carries a very large
    environment (e.g. sudo -E preserving the user's shell state into a uvicorn
    worker), those exec calls fail with E2BIG / rc=126 before the build starts.

    Running ``go env GOROOT`` with a minimal two-variable environment avoids
    E2BIG for this probe only; the actual ``go build`` subprocess still receives
    the full environment because it needs GOPATH and other variables.  The fix
    is shim-specific: we obtain the absolute binary path here, then call it
    directly so the shim is never invoked again for builds.
    """
    minimal_env = {k: os.environ[k] for k in ("PATH", "HOME") if k in os.environ}
    try:
        result = subprocess.run(
            ["go", "env", "GOROOT"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            env=minimal_env,
        )
        if result.returncode == 0 and result.stdout.strip():
            candidate = Path(result.stdout.strip()) / "bin" / "go"
            if candidate.exists():
                return str(candidate)
            log.warning(
                "_resolve_go_binary: expected binary not found at %s; "
                "falling back to 'go' — if goenv is in use, builds may hit E2BIG",
                candidate,
            )
        else:
            log.warning(
                "_resolve_go_binary: 'go env GOROOT' returned rc=%d; "
                "falling back to 'go' — if goenv is in use, builds may hit E2BIG",
                result.returncode,
            )
    except FileNotFoundError:
        log.warning(
            "_resolve_go_binary: 'go' not found on PATH with minimal env; "
            "falling back to bare 'go' name"
        )
    except subprocess.TimeoutExpired:
        log.warning(
            "_resolve_go_binary: 'go env GOROOT' timed out after 10s; "
            "falling back to 'go' — goenv shim may be hanging, builds may hit E2BIG"
        )
    except OSError as exc:
        log.warning(
            "_resolve_go_binary: unexpected OS error resolving go binary: %s; "
            "falling back to bare 'go' name",
            exc,
            exc_info=True,
        )
    return "go"


class GoCompiler:
    def __init__(self, install_path: Path):
        self.install_path = install_path
        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(
                str(self.install_path / "data/agent/gopire")
            ),
            autoescape=False,  # noqa: S701 - renders attack payloads/scripts, not HTML; autoescaping would corrupt output
        )
        self._go_binary = _resolve_go_binary()
        log.info("GoCompiler: using go binary at %s", self._go_binary)

    def generate_main_go(self, template_path, output_path, template_vars):
        """
        Generate the main.go file using the Jinja2 template engine.

        :param template_path: Path to the template file (e.g., main.template.go).
        :param output_path: Path to the output main.go file.
        :param template_vars: Dictionary of variables to replace in the template.
        :return: The rendered string (also written to ``output_path``).
        """
        template = self.jinja_env.get_template(template_path)
        rendered_content = template.render(template_vars)

        with Path(output_path).open("w") as output_file:
            output_file.write(rendered_content)

        return rendered_content

    def compile_stager(self, template_vars, task_name, goos="windows", goarch="amd64"):
        # Persistent Go build cache lives under DATA_DIR/.cache/go-build by
        # default (see DirectoriesConfig.cache). Anchored to a configured user-data
        # path rather than the repo or Path.home() so it survives across server
        # restarts and is the same path regardless of which user runs the server.
        go_cache = str(empire_config.directories.cache / "go-build")
        Path(go_cache).mkdir(parents=True, exist_ok=True)
        env = {
            "GOOS": goos,
            "GOARCH": goarch,
            "GOTOOLCHAIN": "local",  # prevent phantom toolchain downloads on Go 1.21+
            "GOCACHE": go_cache,
            "GONOSUMDB": "*",  # gopire is vendored; no sum-database lookups needed
        }
        random_task_name = f"{task_name}_{random_string(6)}.exe"
        template_path = "main.template"
        gopire_src = self.install_path / "data/agent/gopire"
        final_path = Path(tempfile.gettempdir()) / random_task_name

        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir) / "gopire"
            shutil.copytree(gopire_src, build_dir)

            self.generate_main_go(
                template_path, str(build_dir / "main.go"), template_vars
            )

            build_output = build_dir / random_task_name
            # Merge operator env first so explicit function args (GOOS/GOARCH) win.
            # Reversed order would let `GOOS=linux` in the operator's shell
            # silently override a function-arg `goos="windows"` cross-compile.
            try:
                result = subprocess.run(
                    [self._go_binary, "build", "-o", str(build_output), "."],
                    env={**os.environ, **env},
                    capture_output=True,
                    text=True,
                    cwd=build_dir,
                    check=False,
                )
            except FileNotFoundError:
                raise ModuleExecutionException(
                    f"Go build failed: binary not found at {self._go_binary!r} — "
                    "the Go installation may have been moved or removed since server start"
                ) from None
            except OSError as exc:
                raise ModuleExecutionException(
                    f"Go build failed: OS error launching {self._go_binary!r}: {exc}"
                ) from exc

            if result.returncode != 0:
                preservation_note = ""
                try:
                    preserved_fd, preserved_name = tempfile.mkstemp(
                        prefix="gopire-failed-main-", suffix=".go"
                    )
                    os.close(preserved_fd)
                    shutil.copy2(build_dir / "main.go", preserved_name)
                    preservation_note = (
                        f" (rendered main.go preserved at {preserved_name})"
                    )
                except OSError as preserve_err:
                    log.warning(
                        "Could not preserve failed main.go for debugging "
                        "(task=%s, build_dir=%s): %s",
                        task_name,
                        build_dir,
                        preserve_err,
                        exc_info=True,
                    )
                    preservation_note = (
                        " (failed to preserve rendered main.go; see logs)"
                    )
                log.error(
                    "go build failed (rc=%d)\nstdout: %s\nstderr: %s",
                    result.returncode,
                    result.stdout,
                    result.stderr,
                )
                # Empty stderr with rc != 0 is consistent with a signal kill
                # (OOM-killer, cgroup limits, AV). Surface stdout as a fallback
                # and call out the signal-kill case explicitly so operators
                # don't waste time chasing a non-existent build error.
                detail = (
                    result.stderr.strip()
                    or result.stdout.strip()
                    or "<no output — likely killed by signal, check OOM/AV/cgroup limits>"
                )
                raise ModuleExecutionException(
                    f"Go build failed (rc={result.returncode}): {detail}{preservation_note}"
                )

            shutil.move(str(build_output), str(final_path))

        return str(final_path)
