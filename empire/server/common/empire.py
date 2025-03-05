"""

The main controller class for Empire.

This is what's launched from ./empire.
Contains the Main, Listener, Agents, Agent, and Module
menu loops.

"""

import logging
import os
import time
from pathlib import Path
from socket import SocketIO

# Empire imports
from empire.server.core import hooks_internal
from empire.server.core.agent_file_service import AgentFileService
from empire.server.core.agent_service import AgentService
from empire.server.core.agent_task_service import AgentTaskService
from empire.server.core.bypass_service import BypassService
from empire.server.core.credential_service import CredentialService
from empire.server.core.download_service import DownloadService
from empire.server.core.host_process_service import HostProcessService
from empire.server.core.host_service import HostService
from empire.server.core.listener_service import ListenerService
from empire.server.core.listener_template_service import ListenerTemplateService
from empire.server.core.module_service import ModuleService
from empire.server.core.obfuscation_service import ObfuscationService
from empire.server.core.plugin_service import PluginService
from empire.server.core.profile_service import ProfileService
from empire.server.core.stager_service import StagerService
from empire.server.core.stager_template_service import StagerTemplateService
from empire.server.core.tag_service import TagService
from empire.server.core.user_service import UserService
from empire.server.utils import data_util

from . import agents, credentials, listeners, stagers

VERSION = "5.12.2 BC Security Fork"

log = logging.getLogger(__name__)


class MainMenu:
    """
    The main class used by Empire to drive the 'main' menu
    displayed when Empire starts.
    """

    def __init__(self, args=None):
        time.sleep(1)

        # pull out some common configuration information
        (
            self.isroot,
            self.ipWhiteList,
            self.ipBlackList,
        ) = data_util.get_config("rootuser,ip_whitelist,ip_blacklist")

        self.installPath = str(Path(os.path.realpath(__file__)).parent.parent)

        # parse/handle any passed command line arguments
        self.args = args

        self.socketio: SocketIO | None = None

        self.agents = agents.Agents(self, args=args)
        self.credentials = credentials.Credentials(self, args=args)
        self.stagers = stagers.Stagers(self, args=args)
        self.listeners = listeners.Listeners(self, args=args)

        self.listenertemplatesv2 = ListenerTemplateService(self)
        self.stagertemplatesv2 = StagerTemplateService(self)
        self.bypassesv2 = BypassService(self)
        self.obfuscationv2 = ObfuscationService(self)
        self.profilesv2 = ProfileService(self)
        self.credentialsv2 = CredentialService(self)
        self.hostsv2 = HostService(self)
        self.processesv2 = HostProcessService(self)
        self.downloadsv2 = DownloadService(self)
        self.usersv2 = UserService(self)
        self.listenersv2 = ListenerService(self)
        self.stagersv2 = StagerService(self)
        self.modulesv2 = ModuleService(self)
        self.agenttasksv2 = AgentTaskService(self)
        self.agentfilesv2 = AgentFileService(self)
        self.agentsv2 = AgentService(self)
        self.pluginsv2 = PluginService(self)
        self.tagsv2 = TagService(self)

        self.pluginsv2.startup()
        hooks_internal.initialize()

        self.resourceQueue = []
        # A hashtable of autruns based on agent language
        self.autoRuns = {}
        self.directory = {}

        self.listenersv2.start_existing_listeners()
        log.info("Empire starting up...")

    def shutdown(self):
        """
        Perform any shutdown actions.
        """
        log.info("Empire shutting down...")

        log.info("Shutting down listeners...")
        self.listenersv2.shutdown_listeners()

        log.info("Shutting down plugins...")
        self.pluginsv2.shutdown()
