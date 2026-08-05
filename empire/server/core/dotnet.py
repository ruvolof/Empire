import base64
import logging
import subprocess
import tempfile
import zlib
from pathlib import Path

from empire.server.common.helpers import random_string
from empire.server.core.config.config_manager import empire_config
from empire.server.core.config.data_manager import sync_empire_compiler
from empire.server.core.exceptions import ModuleExecutionException

log = logging.getLogger(__name__)

_COMPILER_UNAVAILABLE_MSG = (
    "Empire Compiler is not available. It could not be downloaded at startup "
    "(see logs — most often a GitHub API rate-limit). Set GITHUB_TOKEN in the "
    "environment or configure empire_compiler.directory to a local build."
)


class DotnetCompiler:
    def __init__(self, install_path):
        self.install_path = install_path
        compiler_root = sync_empire_compiler(empire_config.empire_compiler)
        if compiler_root is None:
            # Don't hard-crash startup (a bare ``None / "EmpireCompiler"`` used
            # to raise TypeError and take down the whole server / test suite).
            # C# compilation is opt-in, so degrade gracefully and only fail when
            # a caller actually asks to compile.
            log.error(_COMPILER_UNAVAILABLE_MSG)
            self.compiler_dir = None
        else:
            self.compiler_dir = compiler_root / "EmpireCompiler"

    def compile_task(
        self, compiler_yaml, task_name, dot_net_version="net40", confuse=False
    ) -> Path:
        if self.compiler_dir is None:
            raise ModuleExecutionException(_COMPILER_UNAVAILABLE_MSG)

        random_task_name = f"{task_name}_{random_string(6)}.exe"

        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            output_path = temp_file.name
            args = [
                "./EmpireCompiler",
                "--output",
                output_path,
                "--dotnet-version",
                dot_net_version,
                "--yaml",
                base64.b64encode(compiler_yaml.encode("UTF-8")).decode("UTF-8"),
            ]

            if confuse:
                args.extend(["--confuse"])

            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                check=False,
                cwd=self.compiler_dir,
            )

            if result.returncode != 0:
                log.error(
                    "EmpireCompiler failed (rc=%d)\nstdout: %s\nstderr: %s",
                    result.returncode,
                    result.stdout,
                    result.stderr,
                )
                detail = (
                    result.stderr.strip()
                    or result.stdout.strip()
                    or "<no output — likely killed by signal, check OOM/AV/cgroup limits>"
                )
                raise ModuleExecutionException(
                    f"EmpireCompiler execution failed (rc={result.returncode}): {detail}"
                )

            if "Final Task Path:" not in result.stdout.strip():
                log.error(result.stdout)
                raise ModuleExecutionException("Module compile failed")

            exe_location = Path(output_path)
            exe_location = exe_location.rename(exe_location.with_name(random_task_name))
            compiled_location = exe_location.with_suffix(".compiled")

            data_bytes = exe_location.read_bytes()
            encoded_data = zlib.compress(data_bytes, level=-1)[2:-4]
            compiled_location.write_bytes(encoded_data)

            return compiled_location

    def compile_stager(
        self, compiler_yaml, task_name, dot_net_version="net40", confuse=False
    ) -> Path:
        if self.compiler_dir is None:
            raise ModuleExecutionException(_COMPILER_UNAVAILABLE_MSG)

        random_task_name = f"{task_name}_{random_string(4)}.exe"

        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            output_path = temp_file.name
            args = [
                "./EmpireCompiler",
                "--output",
                output_path,
                "--dotnet-version",
                dot_net_version,
                "--yaml",
                base64.b64encode(compiler_yaml.encode("UTF-8")).decode("UTF-8"),
            ]

            if confuse:
                args.extend(["--confuse"])

            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                check=False,
                cwd=self.compiler_dir,
            )

            if result.returncode != 0:
                log.error(
                    "EmpireCompiler failed (rc=%d)\nstdout: %s\nstderr: %s",
                    result.returncode,
                    result.stdout,
                    result.stderr,
                )
                detail = (
                    result.stderr.strip()
                    or result.stdout.strip()
                    or "<no output — likely killed by signal, check OOM/AV/cgroup limits>"
                )
                raise ModuleExecutionException(
                    f"EmpireCompiler execution failed (rc={result.returncode}): {detail}"
                )

            if "Final Task Path:" not in result.stdout.strip():
                log.error(result.stdout)
                raise ModuleExecutionException("Stager compile failed")

        exe_location = Path(output_path)
        return exe_location.rename(exe_location.with_name(random_task_name))
