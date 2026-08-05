import base64
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from empire.server.core.exceptions import ModuleValidationException
from empire.server.core.module_models import EmpireModule, LanguageEnum
from empire.server.core.module_service import ModuleService
from empire.server.core.obfuscation_service import ObfuscationService


@pytest.fixture(scope="module")
def main_menu_mock(models, install_path):
    main_menu = Mock()
    main_menu.installPath = install_path
    main_menu.install_path = Path(install_path)
    main_menu.listeners.activeListeners = {}
    main_menu.listeners.listeners = {}
    main_menu.obfuscationv2 = Mock()
    main_menu.obfuscationv2.get_obfuscation_config = Mock(
        return_value=models.ObfuscationConfig(
            language="python", command="", enabled=False
        )
    )
    main_menu.obfuscationv2.obfuscate_keywords = Mock(side_effect=lambda x: x)

    return main_menu


@pytest.fixture(scope="module")
def module_service(main_menu_mock):
    module_service = ModuleService(main_menu=main_menu_mock)

    module_service.dotnet_compiler.compile_task = Mock(
        return_value=Path("/tmp/compiled_task.exe")
    )

    # Wire up so custom_generate modules can access modulesv2 via main_menu
    main_menu_mock.modulesv2 = module_service

    return module_service


@pytest.fixture
def agent_mock():
    agent_mock = Mock()
    agent_mock.session_id = "ABC123"
    return agent_mock


def test_execute_module_with_script_in_yaml_modified_python_agent(
    module_service, agent_mock
):
    agent_mock.language = "python"
    params = {
        "Agent": agent_mock.session_id,
        "Text": "Hello World",
    }
    module_id = "python_trollsploit_osx_say"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, "Modified Script: {{ Text }}"
    )

    assert err is None
    script = res.data

    assert script == "Modified Script: Hello World"


def test_execute_module_with_script_in_path_powershell_agent(
    module_service, agent_mock
):
    agent_mock.language = "powershell"
    params = {
        "Agent": agent_mock.session_id,
        "BooSource": "Hello World",
    }
    module_id = "powershell_code_execution_invoke_boolang"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    script = res.data

    assert script.startswith("function Invoke-Boolang")


def test_execute_module_with_script_in_path_modified_powershell(
    module_service, agent_mock
):
    agent_mock.language = "powershell"
    params = {
        "Agent": agent_mock.session_id,
        "BooSource": "Hello World",
    }
    module_id = "powershell_code_execution_invoke_boolang"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, "Modified Script: "
    )

    assert err is None
    script = res.data

    assert script.startswith(
        'Modified Script:  Invoke-Boolang -BooSource "Hello World"'
    )


def test_execute_module_custom_generate_no_obfuscation_config_powershell_agent(
    main_menu_mock, module_service, agent_mock
):
    agent_mock.language = "python"
    params = {"Agent": agent_mock.session_id}
    module_id = "python_collection_osx_search_email"

    main_menu_mock.obfuscationv2.get_obfuscation_config = Mock(
        side_effect=lambda x, y: None
    )
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    script = res.data

    assert script == 'cmd = "find /Users/ -name *.emlx 2>/dev/null"\nrun_command(cmd)'


def test_execute_module_task_command_python_agent(module_service, agent_mock):
    agent_mock.language = "python"
    params = {
        "Agent": agent_mock.session_id,
        "Text": "Hello World",
    }
    module_id = "python_trollsploit_osx_say"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None

    script = res.data
    assert script == "run_command('say -v alex Hello World')"

    task_command = res.command
    assert task_command == "TASK_PYTHON_CMD_WAIT"


def test_execute_module_task_command_ironpython_agent(module_service, agent_mock):
    agent_mock.language = "ironpython"
    params = {
        "Agent": agent_mock.session_id,
        "Text": "Hello World",
    }
    module_id = "python_trollsploit_osx_say"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    task_command = res.command
    assert task_command == "TASK_PYTHON_CMD_WAIT"


def test_execute_module_task_command_csharp_agent_with_missing_csharp_module(
    module_service, agent_mock
):
    agent_mock.language = "csharp"
    params = {
        "Agent": agent_mock.session_id,
        "Text": "Hello World",
    }
    module_id = "csharp_execution_some_module"
    _res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err == "Module not found for id csharp_execution_some_module"


def test_execute_module_task_command_csharp_agent_with_csharp_module(
    module_service, agent_mock
):
    agent_mock.language = "csharp"
    params = {
        "Agent": agent_mock.session_id,
        "Command": "triage",
    }
    module_id = "csharp_credentials_rubeus"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    task_command = res.command
    assert task_command == "TASK_CSHARP_CMD_JOB"


@pytest.mark.parametrize(
    ("background_override", "expected_command"),
    [
        (False, "TASK_CSHARP_CMD_WAIT"),
        (True, "TASK_CSHARP_CMD_JOB"),
        (None, "TASK_CSHARP_CMD_JOB"),
    ],
)
def test_execute_module_background_override(
    module_service, agent_mock, background_override, expected_command
):
    """Test that background_override overrides the module's YAML background setting."""
    agent_mock.language = "csharp"
    module_id = "csharp_credentials_rubeus"

    module = module_service.get_by_id(module_id)
    assert module.background is True, "Rubeus should have background=true in YAML"

    params = {
        "Agent": agent_mock.session_id,
        "Command": "triage",
    }
    res, err = module_service.execute_module(
        None,
        agent_mock,
        module_id,
        params,
        True,
        True,
        None,
        background_override=background_override,
    )

    assert err is None
    assert res.command == expected_command


@pytest.mark.parametrize(
    ("background_override", "expected_command"),
    [
        (True, "TASK_CSHARP_CMD_JOB"),
        (False, "TASK_CSHARP_CMD_WAIT"),
        (None, "TASK_CSHARP_CMD_WAIT"),
    ],
)
def test_execute_module_background_override_default_false(
    module_service, agent_mock, background_override, expected_command
):
    """Test background_override on a module whose YAML background defaults to false."""
    agent_mock.language = "csharp"
    module_id = "csharp_credentials_certify"

    module = module_service.get_by_id(module_id)
    assert module.background is False, "Certify should have background=false in YAML"

    params = {
        "Agent": agent_mock.session_id,
        "Command": "find",
    }
    res, err = module_service.execute_module(
        None,
        agent_mock,
        module_id,
        params,
        True,
        True,
        None,
        background_override=background_override,
    )

    assert err is None
    assert res.command == expected_command


def test_execute_module_bof_custom_generate(module_service, agent_mock):
    agent_mock.language = "csharp"
    params = {
        "Agent": agent_mock.session_id,
        "Architecture": "x64",
        "Domain": ".",
    }
    module_id = "bof_situational_awareness_adcs_enum"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    task_command = res.command
    assert task_command == "TASK_CSHARP_CMD_WAIT"


def test_execute_module_bof(module_service, agent_mock):
    agent_mock.language = "csharp"
    params = {
        "Agent": agent_mock.session_id,
        "Architecture": "x64",
        "Server": ".",
    }
    module_id = "bof_situational_awareness_tasklist"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    task_command = res.command
    assert task_command == "TASK_CSHARP_CMD_WAIT"


def test_execute_bof_module_missing_architecture(module_service, agent_mock):
    agent_mock.language = "csharp"
    params = {
        "Agent": agent_mock.session_id,
        "Architecture": "",
        "Server": ".",
    }
    module_id = "bof_situational_awareness_tasklist"

    with pytest.raises(ModuleValidationException) as excinfo:
        module_service.execute_module(
            None, agent_mock, module_id, params, True, True, None
        )

    assert "required option missing: Architecture" in str(excinfo.value)


def test_execute_csharp_module(module_service, agent_mock):
    agent_mock.language = "csharp"
    params = {
        "Agent": agent_mock.session_id,
        "Password": "password",
        "Port": "5900",
        "Username": "Empire",
    }
    module_id = "csharp_management_vnc"

    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    task_command = res.command
    assert task_command == "TASK_CSHARP_CMD_WAIT"


def test_execute_bof_module_missing_option(module_service, agent_mock):
    agent_mock.language = "csharp"
    params = {
        "Agent": agent_mock.session_id,
        "Password": "password",
        "Port": "",
        "Username": "Empire",
    }
    module_id = "csharp_management_vnc"

    with pytest.raises(ModuleValidationException) as excinfo:
        module_service.execute_module(
            None, agent_mock, module_id, params, True, True, None
        )

    assert "required option missing: Port" in str(excinfo.value)


def test_execute_module_task_command_powershell_agent(module_service, agent_mock):
    agent_mock.language = "powershell"
    params = {
        "Agent": agent_mock.session_id,
        "BooSource": "Hello World",
    }
    module_id = "powershell_code_execution_invoke_boolang"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    task_command = res.command
    assert task_command == "TASK_POWERSHELL_CMD_JOB"


def test_execute_module_task_command_unsupported_agent_language(
    module_service, agent_mock
):
    agent_mock.language = "unsupported_language"
    params = {
        "Agent": agent_mock.session_id,
        "BooSource": "Hello World",
    }
    module_id = "powershell_code_execution_invoke_boolang"

    with pytest.raises(ModuleValidationException) as excinfo:
        module_service.execute_module(
            None, agent_mock, module_id, params, True, True, None
        )

    assert "Unsupported agent language 'unsupported_language'" in str(excinfo.value)


def test_execute_module_with_non_ascii_characters(module_service, agent_mock):
    agent_mock.language = "python"
    params = {
        "Agent": agent_mock.session_id,
        "Text": "こんにちは世界",
    }
    module_id = "python_trollsploit_osx_say"

    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    assert res.data


def test_execute_disabled_module(module_service, agent_mock):
    agent_mock.language = "python"
    params = {
        "Agent": agent_mock.session_id,
        "Text": "Hello World",
    }
    module_id = "python_trollsploit_osx_say"

    module = module_service.get_by_id(module_id)
    module.enabled = False

    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    module.enabled = True

    assert res is None
    assert err == "Cannot execute disabled module"


def test_execute_module_validation_error(module_service, agent_mock):
    agent_mock.language = "python"
    params = {
        "InvalidParam": "invalid_value",
    }
    module_id = "python_trollsploit_osx_say"

    with pytest.raises(ModuleValidationException) as excinfo:
        module_service.execute_module(
            None, agent_mock, module_id, params, True, True, None
        )

    assert "required option missing: Agent" in str(excinfo.value)


def test_execute_module_with_empty_params(module_service, agent_mock):
    agent_mock.language = "python"
    params = {}
    module_id = "python_trollsploit_osx_say"

    with pytest.raises(ModuleValidationException) as excinfo:
        module_service.execute_module(
            None, agent_mock, module_id, params, True, True, None
        )

    assert "required option missing: Agent" in str(excinfo.value)


def test_handle_save_file_command_with_extension(module_service):
    """Test _handle_save_file_command extracts basename from path-like module name."""
    command, data = module_service._handle_save_file_command(
        "TASK_PYTHON", "python/trollsploit/osx/say", ".txt ", "data_here"
    )
    assert command == "TASK_PYTHON_CMD_WAIT_SAVE"
    # The prefix should be the basename "say" right-justified to 15 chars
    assert data.startswith("say".rjust(15))
    assert ".txt " in data
    assert data.endswith("data_here")


def test_handle_save_file_command_without_extension(module_service):
    """Test _handle_save_file_command with empty extension returns CMD_WAIT."""
    command, data = module_service._handle_save_file_command(
        "TASK_POWERSHELL", "powershell/collection/screenshot", "", "script_data"
    )
    assert command == "TASK_POWERSHELL_CMD_WAIT"
    assert data == "script_data"


@pytest.mark.parametrize(
    ("agent_language", "module_language", "should_raise"),
    [
        # Valid combinations
        ("go", "bof", False),
        ("go", "powershell", False),
        ("go", "csharp", False),
        ("ironpython", "bof", False),
        ("ironpython", "powershell", False),
        ("ironpython", "csharp", False),
        ("ironpython", "python", False),
        ("powershell", "bof", False),
        ("powershell", "powershell", False),
        ("powershell", "csharp", False),
        ("csharp", "bof", False),
        ("csharp", "powershell", False),
        ("csharp", "csharp", False),
        ("python", "python", False),
        # Invalid combinations
        ("go", "python", True),
        ("go", "ironpython", True),
        ("powershell", "python", True),
        ("powershell", "ironpython", True),
        ("csharp", "python", True),
        ("csharp", "ironpython", True),
        ("python", "powershell", True),
        ("python", "csharp", True),
        ("python", "bof", True),
    ],
)
def test_validate_agent_module_language_compatibility(
    module_service, agent_mock, agent_language, module_language, should_raise
):
    agent_mock.language = agent_language
    agent_mock.language_version = "5.1"

    module_mock = Mock()
    module_mock.language = module_language
    module_mock.min_language_version = "5.0"
    module_mock.needs_admin = False
    module_mock.options = {}

    params = {"Agent": agent_mock.session_id}

    if should_raise:
        with pytest.raises(ModuleValidationException) as excinfo:
            module_service._validate_module_params(
                None, module_mock, agent_mock, params
            )
        assert (
            f"agent language '{agent_language}' cannot run module language '{module_language}'"
            in str(excinfo.value)
        )
    else:
        options, err = module_service._validate_module_params(
            None, module_mock, agent_mock, params
        )
        assert err is None
        assert options is not None


@pytest.mark.parametrize(
    ("needs_admin", "high_integrity", "ignore_admin_check", "should_raise"),
    [
        (
            True,
            False,
            False,
            True,
        ),  # Needs admin, no high integrity, no ignore -> should raise
        (
            True,
            False,
            True,
            False,
        ),  # Needs admin, no high integrity, but ignored -> should not raise
        (
            True,
            True,
            False,
            False,
        ),  # Needs admin, has high integrity -> should not raise
        (False, False, False, False),  # Does not need admin -> should not raise
    ],
)
def test_validate_module_admin_check(
    module_service,
    agent_mock,
    needs_admin,
    high_integrity,
    ignore_admin_check,
    should_raise,
):
    agent_mock.language = "powershell"
    agent_mock.language_version = "5.1"
    agent_mock.high_integrity = high_integrity

    module_mock = Mock()
    module_mock.language = "powershell"
    module_mock.min_language_version = "5.0"
    module_mock.needs_admin = needs_admin
    module_mock.options = {}

    params = {"Agent": agent_mock.session_id}

    if needs_admin and not high_integrity and not ignore_admin_check:
        with pytest.raises(ModuleValidationException) as excinfo:
            module_service._validate_module_params(
                None,
                module_mock,
                agent_mock,
                params,
                ignore_admin_check=ignore_admin_check,
            )
        assert "module needs to run in an elevated context" in str(excinfo.value)
    else:
        options, err = module_service._validate_module_params(
            None, module_mock, agent_mock, params, ignore_admin_check=ignore_admin_check
        )
        assert err is None
        assert options is not None


@pytest.mark.parametrize(
    (
        "agent_language",
        "module_language",
        "agent_version",
        "module_version",
        "ignore_version_check",
        "should_raise",
    ),
    [
        ("powershell", "powershell", "4.0", "5.0", False, True),  # Version too low
        ("powershell", "powershell", "5.0", "5.0", False, False),  # Matching versions
        (
            "powershell",
            "powershell",
            "6.0",
            "5.0",
            False,
            False,
        ),  # Agent version higher than required
        (
            "powershell",
            "powershell",
            "4.0",
            "5.0",
            True,
            False,
        ),  # Ignoring version check
        ("csharp", "csharp", "3.0", "3.5", False, True),  # C# version too low
        ("csharp", "csharp", "3.5", "3.5", False, False),  # C# version matches
        ("csharp", "csharp", "4.0", "3.5", False, False),  # C# agent version higher
    ],
)
def test_validate_module_version_check(
    module_service,
    agent_mock,
    agent_language,
    module_language,
    agent_version,
    module_version,
    ignore_version_check,
    should_raise,
):
    agent_mock.language = agent_language
    agent_mock.language_version = agent_version

    module_mock = Mock()
    module_mock.language = module_language
    module_mock.min_language_version = module_version
    module_mock.needs_admin = False
    module_mock.options = {}

    params = {"Agent": agent_mock.session_id}

    if should_raise:
        with pytest.raises(ModuleValidationException) as excinfo:
            module_service._validate_module_params(
                None,
                module_mock,
                agent_mock,
                params,
                ignore_language_version_check=ignore_version_check,
            )
        assert (
            f"module requires language version {module_version} but agent running language version {agent_version}"
            in str(excinfo.value)
        )
    else:
        options, err = module_service._validate_module_params(
            None,
            module_mock,
            agent_mock,
            params,
            ignore_language_version_check=ignore_version_check,
        )
        assert err is None
        assert options is not None


def test_format_bof_output_go_agent(module_service):
    """Test format_bof_output returns base64 JSON with File and HexData for Go agents."""
    result = module_service.format_bof_output(
        bof_data_b64="dGVzdA==",
        hex_data="AAAA",
        agent_language="go",
    )

    decoded = json.loads(base64.b64decode(result))
    assert decoded == {"File": "dGVzdA==", "HexData": "AAAA"}
    assert "Entrypoint" not in decoded


def test_format_bof_output_dotnet_agent(module_service):
    """Test format_bof_output returns file|,json format with Entrypoint for .NET agents."""
    result = module_service.format_bof_output(
        bof_data_b64="dGVzdA==",
        hex_data="AAAA",
        agent_language="csharp",
        obfuscate=False,
    )

    assert "|," in result.data
    script_file, b64_json = result.data.split("|,", 1)
    assert script_file  # non-empty file path
    assert len(result.files) == 1

    decoded = json.loads(base64.b64decode(b64_json))
    assert decoded["Entrypoint"] == "go"
    assert decoded["File"] == "dGVzdA=="
    assert decoded["HexData"] == "AAAA"


def test_format_bof_output_custom_entry_point(module_service):
    """Test format_bof_output respects custom entry_point parameter."""
    result = module_service.format_bof_output(
        bof_data_b64="dGVzdA==",
        hex_data="AAAA",
        agent_language="csharp",
        entry_point="main",
    )

    _, b64_json = result.data.split("|,", 1)
    decoded = json.loads(base64.b64decode(b64_json))
    assert decoded["Entrypoint"] == "main"


def test_execute_module_bof_go_agent(module_service, agent_mock):
    """Test standard BOF module execution with Go agent produces correct format."""
    agent_mock.language = "go"
    params = {
        "Agent": agent_mock.session_id,
        "Architecture": "x64",
        "Server": ".",
    }
    module_id = "bof_situational_awareness_tasklist"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    assert res.command == "TASK_BOF_CMD_WAIT"

    # Go format: base64 JSON with File + HexData, no Entrypoint
    decoded = json.loads(base64.b64decode(res.data))
    assert "File" in decoded
    assert "HexData" in decoded
    assert "Entrypoint" not in decoded


def test_execute_module_bof_custom_generate_go_agent(module_service, agent_mock):
    """Test custom-generate BOF module with Go agent returns Go format, not .NET format."""
    agent_mock.language = "go"
    params = {
        "Agent": agent_mock.session_id,
    }
    module_id = "bof_situational_awareness_clipboard_window_inject_list"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    assert res.command == "TASK_BOF_CMD_WAIT"

    # Must be valid base64 JSON, not the .NET file|,json format
    assert "|," not in res.data
    decoded = json.loads(base64.b64decode(res.data))
    assert "File" in decoded
    assert "HexData" in decoded
    assert "Entrypoint" not in decoded


def test_generate_script_powershell_obfuscates_source_and_script_end_separately(
    module_service, models
):
    """Verify that _generate_script_powershell does NOT double-obfuscate.

    When obfuscation is enabled, the module source is already obfuscated by
    get_module_source(obfuscate=True).  finalize_module() only obfuscates
    script_end (the invoke command), not the already-obfuscated source.
    """
    module = module_service.get_by_id("powershell_code_execution_invoke_boolang")

    obfuscation_config = Mock()
    obfuscation_config.enabled = True
    obfuscation_config.command = "Token\\All\\1"

    fake_source = "function Invoke-Boolang { <# original source #> }"
    obfuscated_source = f"OBFUSCATED({fake_source})"

    obfuscate_calls = []

    def mock_obfuscate(script, command, timeout=300):
        obfuscate_calls.append(script)
        return f"OBFUSCATED({script})"

    with (
        patch.object(
            module_service,
            "get_module_source",
            return_value=(obfuscated_source, None),
        ) as mock_get_source,
        patch.object(
            module_service.obfuscation_service,
            "obfuscate",
            side_effect=mock_obfuscate,
        ),
        patch.object(
            module_service.obfuscation_service,
            "obfuscate_keywords",
            side_effect=lambda x: x,
        ),
    ):
        params = {"Agent": "ABC123", "BooSource": "test"}
        result = module_service._generate_script_powershell(
            module, params, obfuscation_config
        )

        # get_module_source should have been called with obfuscate=True
        mock_get_source.assert_called_once_with(
            module_name=module.script_path,
            obfuscate=True,
            obfuscate_command="Token\\All\\1",
        )

        # obfuscate() should have been called exactly ONCE inside
        # _generate_script_powershell — for script_end only.
        # (get_module_source handles its own obfuscation internally.)
        assert len(obfuscate_calls) == 1, (
            f"Expected obfuscate() to be called once (for script_end), "
            f"but it was called {len(obfuscate_calls)} time(s). "
            f"Calls: {obfuscate_calls}"
        )

        # The single obfuscate call should be for the script_end, not for
        # the combined script+script_end (which would indicate double-obfuscation).
        assert not obfuscate_calls[0].startswith("OBFUSCATED("), (
            "obfuscate() was called on already-obfuscated content, "
            "indicating double-obfuscation"
        )

        # The result should contain the obfuscated source (from get_module_source)
        # and the separately obfuscated script_end.
        assert "OBFUSCATED(" in result
        assert obfuscated_source in result


def test_generate_script_powershell_no_obfuscation_skips_obfuscate(
    module_service, models
):
    """When obfuscation is disabled, obfuscate() should not be called at all."""
    module = module_service.get_by_id("powershell_code_execution_invoke_boolang")

    obfuscation_config = Mock()
    obfuscation_config.enabled = False
    obfuscation_config.command = ""

    fake_source = "function Invoke-Boolang { <# original source #> }"

    with (
        patch.object(
            module_service,
            "get_module_source",
            return_value=(fake_source, None),
        ),
        patch.object(
            module_service.obfuscation_service,
            "obfuscate",
        ) as mock_obfuscate,
        patch.object(
            module_service.obfuscation_service,
            "obfuscate_keywords",
            side_effect=lambda x: x,
        ),
    ):
        params = {"Agent": "ABC123", "BooSource": "test"}
        result = module_service._generate_script_powershell(
            module, params, obfuscation_config
        )

        mock_obfuscate.assert_not_called()
        assert fake_source in result


# ---------------------------------------------------------------------------
# finalize_module — direct tests for both script_already_obfuscated paths
# ---------------------------------------------------------------------------


def test_finalize_module_obfuscates_full_script_when_not_preobfuscated(module_service):
    """When script_already_obfuscated=False (default), finalize_module should
    obfuscate the combined script+script_end as a single unit.  This is the
    path used by custom_generate modules (ask.py, logoff.py, etc.)."""
    raw_script = "function Invoke-Something { Write-Output 'hello' }"
    script_end = " Invoke-Something -Param 'value'"

    obfuscate_calls = []

    def mock_obfuscate(script, command, timeout=300):
        obfuscate_calls.append(script)
        return f"OBFUSCATED({script})"

    with (
        patch.object(
            module_service.obfuscation_service, "obfuscate", side_effect=mock_obfuscate
        ),
        patch.object(
            module_service.obfuscation_service,
            "obfuscate_keywords",
            side_effect=lambda x: x,
        ),
    ):
        result = module_service.finalize_module(
            script=raw_script,
            script_end=script_end,
            obfuscate=True,
            obfuscation_command="Token\\All\\1",
            script_already_obfuscated=False,
        )

    # Should obfuscate the COMBINED script, not just script_end
    assert len(obfuscate_calls) == 1
    assert obfuscate_calls[0] == raw_script + script_end
    assert result == f"OBFUSCATED({raw_script}{script_end})"


def test_finalize_module_obfuscates_only_script_end_when_preobfuscated(module_service):
    """When script_already_obfuscated=True, finalize_module should only
    obfuscate script_end, leaving the pre-obfuscated source intact."""
    pre_obfuscated = "ALREADY_OBFUSCATED_SOURCE"
    script_end = " Invoke-Something -Param 'value'"

    obfuscate_calls = []

    def mock_obfuscate(script, command, timeout=300):
        obfuscate_calls.append(script)
        return f"OBFUSCATED({script})"

    with (
        patch.object(
            module_service.obfuscation_service, "obfuscate", side_effect=mock_obfuscate
        ),
        patch.object(
            module_service.obfuscation_service,
            "obfuscate_keywords",
            side_effect=lambda x: x,
        ),
    ):
        result = module_service.finalize_module(
            script=pre_obfuscated,
            script_end=script_end,
            obfuscate=True,
            obfuscation_command="Token\\All\\1",
            script_already_obfuscated=True,
        )

    # Should only obfuscate script_end, not the pre-obfuscated source
    assert len(obfuscate_calls) == 1
    assert obfuscate_calls[0] == script_end
    assert pre_obfuscated in result


# ---------------------------------------------------------------------------
# obfuscate() fallback paths — non-zero returncode and empty output
# ---------------------------------------------------------------------------


def test_obfuscate_nonzero_returncode_returns_keyword_obfuscated_script(main_menu_mock):
    """When subprocess exits with non-zero code, obfuscate() should return
    the keyword-obfuscated script (graceful degradation)."""
    obfuscation_service = ObfuscationService(main_menu=main_menu_mock)

    raw_script = "Write-Host 'hello'"
    keyword_result = "Write-Host 'KEYWORD_REPLACED'"

    mock_completed = Mock()
    mock_completed.returncode = 1
    mock_completed.stderr = b"some error"

    with (
        patch(
            "empire.server.core.obfuscation_service.data_util.is_powershell_installed",
            return_value=True,
        ),
        patch.object(
            obfuscation_service, "obfuscate_keywords", return_value=keyword_result
        ),
        patch(
            "empire.server.core.obfuscation_service.subprocess.run",
            return_value=mock_completed,
        ),
    ):
        result = obfuscation_service.obfuscate(raw_script, "Token\\All\\1")

    assert result == keyword_result


def test_obfuscate_empty_output_returns_keyword_obfuscated_script(main_menu_mock):
    """When subprocess succeeds but produces empty output, obfuscate() should
    return the keyword-obfuscated script."""
    obfuscation_service = ObfuscationService(main_menu=main_menu_mock)

    raw_script = "Write-Host 'hello'"
    keyword_result = "Write-Host 'KEYWORD_REPLACED'"

    mock_completed = Mock()
    mock_completed.returncode = 0

    with (
        patch(
            "empire.server.core.obfuscation_service.data_util.is_powershell_installed",
            return_value=True,
        ),
        patch.object(
            obfuscation_service, "obfuscate_keywords", return_value=keyword_result
        ),
        patch(
            "empire.server.core.obfuscation_service.subprocess.run",
            return_value=mock_completed,
        ),
    ):
        result = obfuscation_service.obfuscate(raw_script, "Token\\All\\1")

    # The obfuscated file will be empty (NamedTemporaryFile with no writes from subprocess)
    # so obfuscate() should detect empty output and return the keyword-obfuscated script
    assert result == keyword_result


# ---------------------------------------------------------------------------
# preobfuscate_module_by_id
# ---------------------------------------------------------------------------


def test_preobfuscate_module_by_id_not_found(module_service):
    with patch.object(module_service, "get_by_id", return_value=None):
        result = module_service.preobfuscate_module_by_id("nonexistent")
    assert "not found" in result


def test_preobfuscate_module_by_id_no_script_path(module_service):
    mock_module = Mock(script_path=None)
    with patch.object(module_service, "get_by_id", return_value=mock_module):
        result = module_service.preobfuscate_module_by_id("inline_only")
    assert "no script_path" in result


def test_preobfuscate_module_by_id_happy_path(module_service):
    mock_module = Mock(script_path="test/test.ps1", language="powershell")
    mock_config = Mock(command="Token\\All\\1")

    with (
        patch.object(module_service, "get_by_id", return_value=mock_module),
        patch("empire.server.core.module_service.SessionLocal") as mock_sl,
        patch.object(
            module_service.obfuscation_service,
            "get_obfuscation_config",
            return_value=mock_config,
        ),
        patch.object(module_service, "obfuscate_module") as mock_obfuscate,
    ):
        mock_db = Mock()
        mock_sl.begin.return_value.__enter__ = Mock(return_value=mock_db)
        mock_sl.begin.return_value.__exit__ = Mock(return_value=False)

        result = module_service.preobfuscate_module_by_id("test_module")

    assert result is None
    mock_obfuscate.assert_called_once()


def test_preobfuscate_module_by_id_config_survives_session_close(module_service):
    """config.command must be readable after the SessionLocal context exits.

    The real get_obfuscation_config returns a session-bound ORM object.
    With expire_on_commit=True (the default), accessing attributes after
    the session closes raises DetachedInstanceError — crashing the ASGI
    background task and preventing all pre-obfuscation.
    """
    mock_module = Mock(script_path="test/test.ps1", language="powershell")

    # Replace the mock get_obfuscation_config with the real static method
    # so it returns a session-bound ORM object (not a transient Mock).
    original_get_config = module_service.obfuscation_service.get_obfuscation_config
    module_service.obfuscation_service.get_obfuscation_config = (
        ObfuscationService.get_obfuscation_config
    )

    try:
        with (
            patch.object(module_service, "get_by_id", return_value=mock_module),
            patch.object(module_service, "obfuscate_module") as mock_obfuscate,
        ):
            # Should NOT raise DetachedInstanceError
            result = module_service.preobfuscate_module_by_id("test_module")

        assert result is None
        mock_obfuscate.assert_called_once()
    finally:
        module_service.obfuscation_service.get_obfuscation_config = original_get_config


# ---------------------------------------------------------------------------
# obfuscate() timeout fallback
# ---------------------------------------------------------------------------


def test_obfuscate_timeout_returns_keyword_obfuscated_script(main_menu_mock):
    """When subprocess.run raises TimeoutExpired, obfuscate() should return
    the keyword-obfuscated (but not Invoke-Obfuscation-processed) script."""
    obfuscation_service = ObfuscationService(main_menu=main_menu_mock)

    raw_script = "Write-Host 'hello world'"
    keyword_obfuscated = "Write-Host 'KEYWORD_OBFUSCATED'"

    with (
        patch(
            "empire.server.core.obfuscation_service.data_util.is_powershell_installed",
            return_value=True,
        ),
        patch.object(
            obfuscation_service,
            "obfuscate_keywords",
            return_value=keyword_obfuscated,
        ),
        patch(
            "empire.server.core.obfuscation_service.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="pwsh", timeout=300),
        ),
    ):
        result = obfuscation_service.obfuscate(raw_script, "Token\\All\\1", timeout=300)

    # Should get back the keyword-obfuscated version, not empty string
    assert result == keyword_obfuscated


# ---------------------------------------------------------------------------
# _generate_script_powershell — inline script (no script_path) with obfuscation
# ---------------------------------------------------------------------------


def test_generate_script_powershell_inline_script_obfuscation(module_service, models):
    """Verify _generate_script_powershell obfuscates inline module.script and
    script_end separately when there is no script_path.  finalize_module
    only obfuscates script_end, not the already-obfuscated inline source."""
    module = module_service.get_by_id("powershell_code_execution_invoke_boolang")

    # Create a copy-like mock that has no script_path but has an inline script
    inline_module = Mock()
    inline_module.script_path = None
    inline_module.script = "function Invoke-Inline { <# inline source #> }"
    inline_module.script_end = module.script_end
    inline_module.advanced = module.advanced

    obfuscation_config = Mock()
    obfuscation_config.enabled = True
    obfuscation_config.command = "Token\\All\\1"

    obfuscate_calls = []

    def mock_obfuscate(script, command, timeout=300):
        obfuscate_calls.append(script)
        return f"OBFUSCATED({script})"

    with (
        patch.object(
            module_service.obfuscation_service,
            "obfuscate",
            side_effect=mock_obfuscate,
        ),
        patch.object(
            module_service.obfuscation_service,
            "obfuscate_keywords",
            side_effect=lambda x: x,
        ),
        patch.object(
            module_service,
            "finalize_module",
            wraps=module_service.finalize_module,
        ) as mock_finalize,
    ):
        params = {"Agent": "ABC123", "BooSource": "test"}
        result = module_service._generate_script_powershell(
            inline_module, params, obfuscation_config
        )

        # obfuscate() should be called twice: once for the inline script,
        # once for script_end
        expected_obfuscate_call_count = 2
        assert len(obfuscate_calls) == expected_obfuscate_call_count, (
            f"Expected obfuscate() called {expected_obfuscate_call_count} times "
            f"(inline script + script_end), "
            f"got {len(obfuscate_calls)}: {obfuscate_calls}"
        )

        # First call should be for the inline script
        assert obfuscate_calls[0] == inline_module.script

        # Second call should be for script_end (not the already-obfuscated inline script)
        assert not obfuscate_calls[1].startswith("OBFUSCATED("), (
            "script_end obfuscation was called on already-obfuscated content"
        )

        # finalize_module is called with obfuscate=True and
        # script_already_obfuscated=True, so it only obfuscates script_end.
        mock_finalize.assert_called_once()
        _, kwargs = mock_finalize.call_args
        assert kwargs.get("obfuscate") is True
        assert kwargs.get("script_already_obfuscated") is True

        # The result should contain both obfuscated parts
        assert "OBFUSCATED(" in result


# ---------------------------------------------------------------------------
# Integration tests — real Invoke-Obfuscation output verification
# ---------------------------------------------------------------------------

requires_powershell = pytest.mark.skipif(
    not shutil.which("powershell") and not shutil.which("pwsh"),
    reason="PowerShell (powershell or pwsh) is not available on this system",
)


@pytest.mark.slow
@requires_powershell
def test_obfuscate_produces_transformed_output(install_path):
    """Verify Invoke-Obfuscation actually transforms the script content.

    Calls the real obfuscation subprocess and checks that:
    - The output is non-empty
    - The output differs from the input
    - Original identifiers are no longer present in plaintext
    """
    main_menu = Mock()
    main_menu.install_path = Path(install_path)
    obfuscation_service = ObfuscationService(main_menu=main_menu)

    original_script = (
        "function Invoke-PerfTestMarker {\n"
        "    $PerfTestVariable = 'HelloFromPerfTest'\n"
        "    Write-Output $PerfTestVariable\n"
        "}\n"
    )

    result = obfuscation_service.obfuscate(
        original_script, "Token\\All\\1", timeout=120
    )

    assert result, "Obfuscation returned empty output"
    assert result != original_script, (
        "Obfuscation returned the script unchanged — Invoke-Obfuscation may not be running"
    )
    # The original function name and variable should be obfuscated away
    assert "Invoke-PerfTestMarker" not in result, (
        f"Original function name 'Invoke-PerfTestMarker' still present in obfuscated output:\n{result[:500]}"
    )
    assert "PerfTestVariable" not in result, (
        f"Original variable name 'PerfTestVariable' still present in obfuscated output:\n{result[:500]}"
    )
    assert "HelloFromPerfTest" not in result, (
        f"Original string literal 'HelloFromPerfTest' still present in obfuscated output:\n{result[:500]}"
    )


@pytest.mark.slow
@requires_powershell
def test_finalize_module_obfuscates_script_end_not_source(install_path):
    """End-to-end verification that finalize_module obfuscates script_end
    while leaving the already-obfuscated source intact.

    Uses real Invoke-Obfuscation to verify the output contains both
    the pre-obfuscated source and a transformed script_end.
    """
    main_menu = Mock()
    main_menu.install_path = Path(install_path)
    obfuscation_service = ObfuscationService(main_menu=main_menu)

    # Simulate a pre-obfuscated module source (already processed)
    pre_obfuscated_source = (
        "# This simulates pre-obfuscated source\n"
        "Set-Variable -Name xQ3k -Value 'already_obfuscated_content'\n"
    )
    # A recognizable script_end that should get obfuscated
    script_end = " Invoke-OriginalCommand -TargetParam 'SensitiveValue' | Out-String"

    module_service_mock = Mock()
    module_service_mock.obfuscation_service = obfuscation_service

    # Call finalize_module directly via the real class method
    result = ModuleService.finalize_module(
        module_service_mock,
        script=pre_obfuscated_source,
        script_end=script_end,
        obfuscate=True,
        obfuscation_command="Token\\All\\1",
        script_already_obfuscated=True,
    )

    assert result, "finalize_module returned empty output"

    # The pre-obfuscated source should still be present (not re-obfuscated)
    assert "already_obfuscated_content" in result, (
        "Pre-obfuscated source was modified — finalize_module should not re-obfuscate it"
    )

    # The original script_end identifiers should be obfuscated away.
    # Note: Token\All\1 obfuscates command names and string literals
    # but not parameter names (e.g., -TargetParam survives).
    assert "Invoke-OriginalCommand" not in result, (
        f"script_end function name 'Invoke-OriginalCommand' was not obfuscated:\n{result[:500]}"
    )
    assert "SensitiveValue" not in result, (
        f"script_end string 'SensitiveValue' was not obfuscated:\n{result[:500]}"
    )


def _make_custom_generate_module(path: Path) -> EmpireModule:
    mod = EmpireModule(
        id="custom_gen_test", name="custom_gen_test", language=LanguageEnum.python
    )
    mod.advanced.custom_generate = True
    mod.advanced.custom_generate_path = str(path)
    return mod


def test_load_custom_generate_class_returns_cached(module_service, tmp_path):
    mod = _make_custom_generate_module(tmp_path / "noop.py")
    sentinel = object()
    mod.advanced.generate_class = sentinel

    assert module_service._load_custom_generate_class(mod) is sentinel


def test_load_custom_generate_class_caches_after_first_call(module_service, tmp_path):
    py = tmp_path / "lazy_load_once.py"
    py.write_text("class Module:\n    pass\n")
    mod = _make_custom_generate_module(py)

    with patch(
        "empire.server.core.module_service.importlib.util.module_from_spec",
        wraps=importlib.util.module_from_spec,
    ) as wrapped:
        first = module_service._load_custom_generate_class(mod)
        second = module_service._load_custom_generate_class(mod)

    assert first is second
    assert wrapped.call_count == 1


def test_load_custom_generate_class_wraps_none_spec(module_service, tmp_path):
    mod = _make_custom_generate_module(tmp_path / "doesnotmatter.py")
    with (
        patch(
            "empire.server.core.module_service.importlib.util.spec_from_file_location",
            return_value=None,
        ),
        pytest.raises(ModuleValidationException, match="cannot build import spec"),
    ):
        module_service._load_custom_generate_class(mod)


def test_load_custom_generate_class_wraps_import_error(module_service, tmp_path):
    py = tmp_path / "broken.py"
    py.write_text("raise RuntimeError('boom')\n")
    mod = _make_custom_generate_module(py)

    with pytest.raises(ModuleValidationException, match="failed to load") as excinfo:
        module_service._load_custom_generate_class(mod)
    assert isinstance(excinfo.value.__cause__, RuntimeError)
