import os
import shutil
import sys
from contextlib import contextmanager, suppress
from pathlib import Path

import pytest
import yaml
from starlette.testclient import TestClient

from empire.client.src.utils.data_util import get_random_string

SERVER_CONFIG_LOC = "empire/test/test_server_config.yaml"
CLIENT_CONFIG_LOC = "empire/test/test_client_config.yaml"
DEFAULT_ARGV = ["", "server", "--config", SERVER_CONFIG_LOC]


os.chdir(Path(os.path.dirname(os.path.abspath(__file__))).parent.parent)
sys.argv = DEFAULT_ARGV


@pytest.fixture(scope="session")
def default_argv():
    return DEFAULT_ARGV


@pytest.fixture(scope="session")
def install_path():
    return Path(os.path.realpath(__file__)).parent.parent / "server"


@pytest.fixture(scope="session", autouse=True)
def client():
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]
    os.chdir(Path(os.path.dirname(os.path.abspath(__file__))).parent.parent)

    import empire.server.core.db.base
    from empire.server.core.db.base import reset_db, startup_db

    startup_db()

    shutil.rmtree("empire/test/downloads", ignore_errors=True)
    shutil.rmtree("empire/test/data/obfuscated_module_source", ignore_errors=True)

    from empire import arguments

    args = arguments.parent_parser.parse_args()

    import empire.server.server
    from empire.server.api.app import initialize
    from empire.server.common.empire import MainMenu

    empire.server.server.main = MainMenu(args)

    app = initialize(ip="localhost", run=False)

    # fix for pycharm debugger
    # https://stackoverflow.com/a/77926544/5849681
    # yield TestClient(app, backend_options={"loop_factory": asyncio.new_event_loop})
    yield TestClient(app)

    from empire.server.server import main

    main.shutdown()
    reset_db()


@pytest.fixture(scope="session", autouse=True)
def empire_config():
    from empire.server.core.config import empire_config

    yield empire_config


@pytest.fixture(scope="session")
def models():
    from empire.server.core.db import models

    yield models


@pytest.fixture(scope="session")
def admin_auth_token(client):
    response = client.post(
        "/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "password",
            "username": "empireadmin",
            "password": "password123",
        },
    )

    yield response.json()["access_token"]


@pytest.fixture(scope="session")
def admin_auth_header(admin_auth_token):
    return {"Authorization": f"Bearer {admin_auth_token}"}


@pytest.fixture(scope="session")
def regular_auth_token(client, admin_auth_token):
    client.post(
        "/api/v2/users/",
        headers={"Authorization": f"Bearer {admin_auth_token}"},
        json={"username": "vinnybod", "password": "hunter2", "is_admin": False},
    )

    response = client.post(
        "/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "password", "username": "vinnybod", "password": "hunter2"},
    )

    yield response.json()["access_token"]


@pytest.fixture(scope="module")
def db():
    from empire.server.core.db.base import SessionLocal

    yield SessionLocal()


@pytest.fixture(scope="session")
def main():
    from empire.server.server import main

    yield main


@pytest.fixture(scope="function")
def base_listener():
    return {
        "name": "new-listener-1",
        "template": "http",
        "options": {
            "Name": "new-listener-1",
            "Host": "http://localhost:1336",
            "BindIP": "0.0.0.0",
            "Port": "1336",
            "Launcher": "powershell -noP -sta -w 1 -enc ",
            "StagingKey": "2c103f2c4ed1e59c0b4e2e01821770fa",
            "DefaultDelay": "5",
            "DefaultJitter": "0.0",
            "DefaultLostLimit": "60",
            "DefaultProfile": "/admin/get.php,/news.php,/login/process.php|Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko",
            "CertPath": "",
            "KillDate": "",
            "WorkingHours": "",
            "Headers": "Server:Microsoft-IIS/7.5",
            "Cookie": "",
            "StagerURI": "",
            "UserAgent": "default",
            "Proxy": "default",
            "ProxyCreds": "default",
            "SlackURL": "",
            "JA3_Evasion": "False",
        },
    }


@pytest.fixture(scope="function")
def malleable_listener():
    return {
        "name": "malleable_listener_1",
        "template": "http_malleable",
        "options": {
            "Name": "http_malleable",
            "Host": "http://localhost",
            "BindIP": "0.0.0.0",
            "Port": "1338",
            "Profile": "amazon.profile",
            "Launcher": "powershell -noP -sta -w 1 -enc ",
            "StagingKey": "2c103f2c4ed1e59c0b4e2e01821770fa",
            "DefaultDelay": "5",
            "DefaultJitter": "0.0",
            "DefaultLostLimit": "60",
            "CertPath": "",
            "KillDate": "",
            "WorkingHours": "",
            "Cookie": "",
            "UserAgent": "default",
            "Proxy": "default",
            "ProxyCreds": "default",
            "SlackURL": "",
            "JA3_Evasion": "False",
        },
    }


def base_listener_non_fixture():
    return {
        "name": "new-listener-1",
        "template": "http",
        "options": {
            "Name": "new-listener-1",
            "Host": "http://localhost:80",
            "BindIP": "0.0.0.0",
            "Port": "1336",
            "Launcher": "powershell -noP -sta -w 1 -enc ",
            "StagingKey": "2c103f2c4ed1e59c0b4e2e01821770fa",
            "DefaultDelay": "5",
            "DefaultJitter": "0.0",
            "DefaultLostLimit": "60",
            "DefaultProfile": "/admin/get.php,/news.php,/login/process.php|Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko",
            "CertPath": "",
            "KillDate": "",
            "WorkingHours": "",
            "Headers": "Server:Microsoft-IIS/7.5",
            "Cookie": "",
            "StagerURI": "",
            "UserAgent": "default",
            "Proxy": "default",
            "ProxyCreds": "default",
            "SlackURL": "",
            "JA3_Evasion": "False",
        },
    }


def malleable_listener_non_fixture():
    return {
        "name": "malleable_listener_1",
        "template": "http_malleable",
        "options": {
            "Name": "http_malleable",
            "Host": "http://localhost",
            "BindIP": "0.0.0.0",
            "Port": "1338",
            "Profile": "amazon.profile",
            "Launcher": "powershell -noP -sta -w 1 -enc ",
            "StagingKey": "2c103f2c4ed1e59c0b4e2e01821770fa",
            "DefaultDelay": "5",
            "DefaultJitter": "0.0",
            "DefaultLostLimit": "60",
            "CertPath": "",
            "KillDate": "",
            "WorkingHours": "",
            "Cookie": "",
            "UserAgent": "default",
            "Proxy": "default",
            "ProxyCreds": "default",
            "SlackURL": "",
            "JA3_Evasion": "False",
        },
    }


@pytest.fixture(scope="module", autouse=True)
def listener(client, admin_auth_header):
    # not using fixture because scope issues
    response = client.post(
        "/api/v2/listeners/",
        headers=admin_auth_header,
        json=base_listener_non_fixture(),
    )

    yield response.json()

    with suppress(Exception):
        client.delete(
            f"/api/v2/listeners/{response.json()['id']}", headers=admin_auth_header
        )


@pytest.fixture(scope="module", autouse=True)
def listener_malleable(client, admin_auth_header):
    # not using fixture because scope issues
    response = client.post(
        "/api/v2/listeners/",
        headers=admin_auth_header,
        json=malleable_listener_non_fixture(),
    )

    yield response.json()

    with suppress(Exception):
        client.delete(
            f"/api/v2/listeners/{response.json()['id']}", headers=admin_auth_header
        )


@pytest.fixture(scope="function")
def base_stager():
    return {
        "name": "MyStager",
        "template": "multi_launcher",
        "options": {
            "Listener": "new-listener-1",
            "Language": "powershell",
            "StagerRetries": "0",
            "OutFile": "",
            "Base64": "True",
            "Obfuscate": "False",
            "ObfuscateCommand": "Token\\All\\1",
            "SafeChecks": "True",
            "UserAgent": "default",
            "Proxy": "default",
            "ProxyCreds": "default",
            "Bypasses": "mattifestation etw",
        },
    }


@pytest.fixture(scope="function")
def base_stager_dll():
    return {
        "name": "MyStager2",
        "template": "windows_dll",
        "options": {
            "Listener": "new-listener-1",
            "Language": "powershell",
            "StagerRetries": "0",
            "Arch": "x86",
            "OutFile": "my-windows-dll.dll",
            "Base64": "True",
            "Obfuscate": "False",
            "ObfuscateCommand": "Token\\All\\1",
            "SafeChecks": "True",
            "UserAgent": "default",
            "Proxy": "default",
            "ProxyCreds": "default",
            "Bypasses": "mattifestation etw",
        },
    }


@pytest.fixture(scope="function")
def base_stager_malleable():
    return {
        "name": "MyStager",
        "template": "multi_launcher",
        "options": {
            "Listener": "malleable_listener_1",
            "Language": "powershell",
            "StagerRetries": "0",
            "OutFile": "",
            "Base64": "True",
            "Obfuscate": "False",
            "ObfuscateCommand": "Token\\All\\1",
            "SafeChecks": "True",
            "UserAgent": "default",
            "Proxy": "default",
            "ProxyCreds": "default",
            "Bypasses": "mattifestation etw",
        },
    }


@pytest.fixture(scope="function")
def bat_stager():
    return {
        "name": "bat_stager",
        "template": "windows_launcher_bat",
        "options": {
            "Listener": "new-listener-1",
            "Language": "powershell",
            "OutFile": "my-bat.bat",
            "Obfuscate": "False",
            "ObfuscateCommand": "Token\\All\\1",
            "Bypasses": "mattifestation etw",
        },
    }


@pytest.fixture(scope="function")
def windows_macro_stager():
    return {
        "name": "macro_stager",
        "template": "windows_macro",
        "options": {
            "Listener": "new-listener-1",
            "Language": "powershell",
            "DocumentType": "word",
            "Trigger": "autoopen",
            "OutFile": "document_macro.txt",
            "Obfuscate": "False",
            "ObfuscateCommand": "Token\\All\\1",
            "Bypasses": "mattifestation etw",
            "SafeChecks": "True",
        },
    }


@pytest.fixture(scope="function")
def pyinstaller_stager():
    return {
        "name": "MyStager3",
        "template": "multi_pyinstaller",
        "options": {
            "Listener": "new-listener-1",
            "Language": "python",
            "OutFile": "empire",
            "SafeChecks": "True",
            "UserAgent": "default",
        },
    }


@pytest.fixture(scope="session")
def session_local(client):
    from empire.server.core.db.base import SessionLocal

    yield SessionLocal


@pytest.fixture(scope="function")
def host(session_local, models):
    with session_local.begin() as db:
        host = models.Host(name="host1", internal_ip="192.168.0.1")
        db.add(host)
        db.flush()
        host_id = host.id

    yield host_id

    with session_local.begin() as db:
        db.query(models.Agent).filter(models.Agent.host_id == host_id).delete()
        db.query(models.Host).filter(models.Host.id == host_id).delete()


@pytest.fixture(scope="function")
def agent(session_local, models, host, main):
    with session_local.begin() as db:
        name = f'agent_{__name__.split(".")[-1]}'
        agent = models.Agent(
            name=name,
            session_id=name,
            delay=1,
            jitter=0.1,
            external_ip="1.1.1.1",
            session_key="qwerty",
            nonce="nonce",
            profile="profile",
            kill_date="killDate",
            working_hours="workingHours",
            lost_limit=60,
            listener="http",
            language="powershell",
            language_version="5",
            high_integrity=True,
            process_name="abc",
            process_id=123,
            host_id=host,
            archived=False,
        )
        db.add(agent)
        db.add(models.AgentCheckIn(agent_id=agent.session_id))
        db.flush()

        main.agents.agents[name] = {
            "sessionKey": agent.session_key,
            "functions": agent.functions,
        }

        agent_id = agent.session_id

    yield agent_id

    with session_local.begin() as db:
        db.query(models.AgentCheckIn).filter(
            models.AgentCheckIn.agent_id == agent_id
        ).delete()
        db.query(models.Agent).filter(models.Agent.session_id == agent_id).delete()


@pytest.fixture(scope="function")
def agent_task(client, admin_auth_header, agent):
    resp = client.post(
        f"/api/v2/agents/{agent}/tasks/shell",
        headers=admin_auth_header,
        json={"command": 'echo "HELLO WORLD"'},
    )

    yield resp.json()

    # No need to delete the task, it will be deleted when the agent is deleted
    # After the test.


@pytest.fixture(scope="module")
def plugin_name():
    return "basic_reporting"


@pytest.fixture(scope="function")
def plugin_task(main, session_local, models, plugin_name):
    with session_local.begin() as db:
        plugin_task = models.PluginTask(
            plugin_id=plugin_name,
            input="This is the trimmed input for the task.",
            input_full="This is the full input for the task.",
            user_id=1,
        )
        db.add(plugin_task)
        db.flush()
        task_id = plugin_task.id

    yield task_id

    with session_local.begin() as db:
        db.query(models.PluginTask).delete()


@pytest.fixture(scope="function")
def credential(client, admin_auth_header):
    resp = client.post(
        "/api/v2/credentials/",
        headers=admin_auth_header,
        json={
            "credtype": "hash",
            "domain": "the-domain",
            "username": get_random_string(8),
            "password": get_random_string(8),
            "host": "host1",
        },
    )

    yield resp.json()["id"]

    with suppress(Exception):
        client.delete(
            f"/api/v2/credentials/{resp.json()['id']}", headers=admin_auth_header
        )


@pytest.fixture(scope="function")
def download(client, admin_auth_header):
    response = client.post(
        "/api/v2/downloads",
        headers=admin_auth_header,
        files={
            "file": (
                "test-upload-2.yaml",
                Path("./empire/test/test-upload-2.yaml").read_bytes(),
            )
        },
    )

    yield response.json()["id"]


@pytest.fixture(scope="session")
def server_config_dict():
    # load the config file
    import yaml

    with open(SERVER_CONFIG_LOC) as f:
        config_dict = yaml.safe_load(f)

    yield config_dict


@pytest.fixture(scope="session")
def client_config_dict():
    import yaml

    with open(CLIENT_CONFIG_LOC) as f:
        config_dict = yaml.safe_load(f)

    yield config_dict


@contextmanager
def patch_config(empire_config):
    """
    Change the module_source directory temporarily.
    """
    orig_src_dir = empire_config.directories.module_source
    try:
        empire_config.directories.module_source = Path(
            "empire/test/data/module_source/"
        ).resolve()
        yield empire_config
    finally:
        empire_config.directories.module_source = orig_src_dir


def load_test_config():
    with open(SERVER_CONFIG_LOC) as f:
        return yaml.safe_load(f)
