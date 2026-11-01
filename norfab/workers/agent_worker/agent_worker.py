import importlib.metadata
import logging
import sys

import yaml

from norfab.core.agent import AgentProgress, NFAgent
from norfab.core.worker import Job, NFPWorker, Task
from norfab.models import Result

from .agent_models import (
    GetInventoryInput,
    GetInventoryResult,
    GetStatusInput,
    GetStatusResult,
    GetVersionInput,
    GetVersionResult,
    InvokeInput,
    InvokeResult,
)

SERVICE = "agent"

log = logging.getLogger(__name__)


class AgentWorker(NFPWorker):
    """
    This class represents a worker that interacts with a language model to
    handle various tasks such as chatting with users, retrieving inventory,
    and producing version reports of Python packages.

    Args:
        inventory: The inventory object to be used by the worker.
        broker (str): The broker URL to connect to.
        worker_name (str): The name of this worker.
        exit_event: An event that, if set, indicates the worker needs to stop/exit.
        init_done_event: An event to set when the worker has finished initializing.
        log_level (str): The logging level of this worker. Defaults to "WARNING".

    """

    def __init__(
        self,
        inventory: object,
        broker: str,
        worker_name: str,
        exit_event: object = None,
        init_done_event: object = None,
        log_level: str = "WARNING",
    ) -> None:
        super().__init__(inventory, broker, SERVICE, worker_name, exit_event, log_level)
        self.init_done_event = init_done_event

        # get inventory from broker
        self.agent_inventory = self.load_inventory()

        self.init_done_event.set()
        log.info(f"worker {self.name} started")

    def worker_exit(self) -> None:
        pass

    @Task(
        input=GetVersionInput,
        output=GetVersionResult,
        fastapi={"methods": ["GET"]},
        mcp={
            "annotations": {
                "title": "Get Version",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            }
        },
    )
    def get_version(self) -> Result:
        """
        Generate a report of the versions of specific Python packages and system information.
        This method collects the version information of several Python packages and system details,
        including the Python version, platform, and a specified language model.

        Returns:
            Result: An object containing a dictionary with the package names as keys and their
                    respective version numbers as values. If a package is not found, its version
                    will be an empty string.
        """
        libs = {
            "norfab": "",
            "langchain": "",
            "langchain-community": "",
            "langchain-core": "",
            "langchain-ollama": "",
            "ollama": "",
            "python": sys.version.split(" ")[0],
            "platform": sys.platform,
        }
        # get version of packages installed
        for pkg in libs.keys():
            try:
                libs[pkg] = importlib.metadata.version(pkg)
            except importlib.metadata.PackageNotFoundError:
                pass

        return Result(result=libs)

    @Task(
        input=GetInventoryInput,
        output=GetInventoryResult,
        fastapi={"methods": ["GET"]},
        mcp={
            "annotations": {
                "title": "Get Inventory",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            }
        },
    )
    def get_inventory(self) -> Result:
        """
        NorFab task to retrieve the agent's inventory.

        Returns:
            Result: An instance of the Result class containing the agent's inventory.
        """
        return Result(result=self.agent_inventory)

    @Task(
        input=GetStatusInput,
        output=GetStatusResult,
        fastapi={"methods": ["GET"]},
        mcp={
            "annotations": {
                "title": "Get Status",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            }
        },
    )
    def get_status(self) -> Result:
        """
        NorFab Task that retrieves the status of the agent worker.

        Returns:
            Result: An object containing the status result with a value of "OK".
        """
        return Result(result="OK")

    @Task(
        input=InvokeInput,
        output=InvokeResult,
        fastapi={"methods": ["POST"]},
        mcp={
            "annotations": {
                "title": "Invoke Agent",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": False,
                "openWorldHint": True,
            }
        },
    )
    def invoke(
        self,
        job: Job,
        instructions: str,
        name: str = "NorFab",
        verbose_result: bool = False,
    ) -> Result:
        """Run instructions with the built-in agent or a custom YAML definition.

        Args:
            job (Job): Job context used to report execution progress.
            instructions (str): Request sent to the agent.
            name (str): ``NorFab`` for native access to discovered NorFab tasks, or an
                ``nf://`` or ``git://`` URL to a YAML agent definition. Custom
                definitions may supply ``name``, ``system_prompt``, ``tools``
                and ``llm`` using the shared core agent format. Defaults to ``NorFab``.
            verbose_result (bool): Return the full agent invocation payload when
                true; otherwise return the final response content. Defaults to false.

        Returns:
            Result: Final response content or the full invocation payload.
                Each invocation starts a fresh conversation without stored history.

        Raises:
            FileNotFoundError: The custom definition cannot be fetched.
            KeyError: Neither the definition nor inventory supplies an LLM.
            ValueError: The definition has duplicate tools or an unsupported provider.
            ImportError: A configured provider or optional feature is not installed.
        """
        job.event(f"getting {name} agent ready")
        if name == "NorFab":
            config = {"llm": self.agent_inventory["default_llm"]}
        else:
            config = yaml.safe_load(
                self.fetch_file(name, raise_on_fail=True, read=True)
            )
            if not config.get("llm"):
                config["llm"] = self.agent_inventory["default_llm"]

        agent = NFAgent(self.client, config)
        try:
            return Result(
                result=agent.invoke(
                    instructions,
                    verbose_result=verbose_result,
                    callbacks=[AgentProgress(job.event)],
                )
            )
        finally:
            agent.close()
