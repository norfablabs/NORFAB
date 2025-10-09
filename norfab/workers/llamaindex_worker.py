import json
import logging
import sys
import importlib.metadata
from norfab.core.worker import NFPWorker, Task, Job
from norfab.models import Result
from typing import Union

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.llms import ChatMessage
from llama_index.llms.ollama import Ollama

SERVICE = "llamaindex"

log = logging.getLogger(__name__)


class LlamaindexWorker(NFPWorker):

    def __init__(
        self,
        inventory,
        broker: str,
        worker_name: str,
        exit_event=None,
        init_done_event=None,
        log_level: str = "WARNING",
        log_queue: object = None,
    ):
        super().__init__(
            inventory, broker, SERVICE, worker_name, exit_event, log_level, log_queue
        )
        self.init_done_event = init_done_event

        # get inventory from broker
        self.agent_inventory = self.load_inventory()
        self.llm_model = self.agent_inventory.get("llm_model", "llama3.1:8b")
        self.llm_base_url = self.agent_inventory.get(
            "base_url", "http://127.0.0.1:11434"
        )
        self.llm_flavour = self.agent_inventory.get("llm_flavour", "ollama")

        if self.llm_flavour == "ollama":
            self.llm = Ollama(model=self.llm_model, base_url=self.llm_base_url)

        self.init_done_event.set()
        log.info(f"{self.name} - Started")

    def worker_exit(self):
        pass

    @Task(fastapi={"methods": ["GET"]})
    def get_version(self):
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
            "llama-index-llms-ollama": "",
            "llama-index": "",
            "python": sys.version.split(" ")[0],
            "platform": sys.platform,
            "llm_model": self.llm_model,
        }
        # get version of packages installed
        for pkg in libs.keys():
            try:
                libs[pkg] = importlib.metadata.version(pkg)
            except importlib.metadata.PackageNotFoundError:
                pass

        return Result(result=libs)

    @Task(fastapi={"methods": ["GET"]})
    def get_inventory(self):
        """
        NorFab task to retrieve the agent's inventory.

        Returns:
            Result: An instance of the Result class containing the agent's inventory.
        """
        return Result(result=self.agent_inventory)

    @Task(fastapi={"methods": ["GET"]})
    def get_status(self):
        """
        NorFab Task that retrieves the status of the agent worker.

        Returns:
            Result: An object containing the status result with a value of "OK".
        """
        return Result(result="OK")

    @Task(fastapi={"methods": ["POST"]})
    def chat(self, job: Job, user_input: str) -> str:
        """
        NorFab Task that handles the chat interaction with the user by processing the
        input through a language model.

        Args:
            user_input (str): The input provided by the user.

        Returns:
            str: Language model's response.
        """
        response = self.llm.chat(
            [
                ChatMessage(
                    role="system",
                    content="You are a pirate with a colorful personality",
                ),
                ChatMessage(role="user", content=user_input),
            ]
        )

        return Result(result=response.message.blocks[-1].text)
