import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock

from empire.server.core.bypass_service import BypassService
from empire.server.core.listener_template_service import ListenerTemplateService
from empire.server.core.profile_service import ProfileService
from empire.server.core.stager_template_service import StagerTemplateService
from empire.test.conftest import SERVER_CONFIG_LOC


def test_bypass_loader(monkeypatch):
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]
    session_mock = MagicMock()
    monkeypatch.setattr("empire.server.core.bypass_service.SessionLocal", session_mock)

    session_mock.begin.return_value.__enter__.return_value.scalars.return_value.first.return_value = None

    main_menu = Mock()
    main_menu.installPath = "empire/server"
    main_menu.install_path = Path("empire/server")

    BypassService(main_menu)

    min_call_count = 4
    assert (
        session_mock.begin.return_value.__enter__.return_value.add.call_count
        > min_call_count
    )


def test_listener_template_loader(monkeypatch):
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]
    session_mock = MagicMock()
    monkeypatch.setattr(
        "empire.server.core.listener_template_service.SessionLocal", session_mock
    )

    session_mock.begin.return_value.__enter__.return_value.query.return_value.first.return_value.install_path = "empire/server"

    main_menu = Mock()
    main_menu.installPath = "empire/server"
    main_menu.install_path = Path("empire/server")

    listener_template_service = ListenerTemplateService(main_menu)

    min_template_count = 5
    assert len(listener_template_service.get_listener_templates()) > min_template_count


def test_stager_template_loader(monkeypatch):
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]
    session_mock = MagicMock()
    monkeypatch.setattr(
        "empire.server.core.stager_template_service.SessionLocal", session_mock
    )

    session_mock.begin.return_value.__enter__.return_value.query.return_value.first.return_value.install_path = "empire/server"

    main_menu = Mock()
    main_menu.installPath = "empire/server"
    main_menu.install_path = Path("empire/server")

    stager_template_service = StagerTemplateService(main_menu)

    min_template_count = 10
    assert len(stager_template_service.get_stager_templates()) > min_template_count


def test_profile_loader(monkeypatch):
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]
    session_mock = MagicMock()
    monkeypatch.setattr("empire.server.core.profile_service.SessionLocal", session_mock)

    # Empty existing-names set — every on-disk profile is a fresh insert.
    session_mock.begin.return_value.__enter__.return_value.scalars.return_value.all.return_value = []

    main_menu = Mock()
    main_menu.installPath = "empire/server"
    main_menu.install_path = Path("empire/server")

    ProfileService(main_menu)

    min_call_count = 20
    assert (
        session_mock.begin.return_value.__enter__.return_value.add.call_count
        > min_call_count
    )


def test_profile_loader_warns_on_duplicate(monkeypatch, tmp_path, caplog):
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]
    session_mock = MagicMock()
    monkeypatch.setattr("empire.server.core.profile_service.SessionLocal", session_mock)
    session_mock.begin.return_value.__enter__.return_value.query.return_value.all.return_value = []

    profiles_root = tmp_path / "data" / "profiles"
    (profiles_root / "cat_a").mkdir(parents=True)
    (profiles_root / "cat_b").mkdir(parents=True)
    first = profiles_root / "cat_a" / "duplicate.profile"
    second = profiles_root / "cat_b" / "duplicate.profile"
    first.write_text("first body")
    second.write_text("second body")

    main_menu = Mock()
    main_menu.installPath = str(tmp_path)
    main_menu.install_path = tmp_path

    with caplog.at_level("WARNING", logger="empire.server.core.profile_service"):
        ProfileService(main_menu)

    dup_warnings = [
        r.getMessage()
        for r in caplog.records
        if "Duplicate malleable profile name" in r.getMessage()
    ]
    assert len(dup_warnings) == 1
    assert "duplicate.profile" in dup_warnings[0]
    # Only the first occurrence should be inserted.
    assert session_mock.begin.return_value.__enter__.return_value.add.call_count == 1
