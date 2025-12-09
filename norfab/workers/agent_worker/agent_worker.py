import json
import yaml
import logging
import sys
import importlib.metadata
from norfab.core.worker import NFPWorker, Task, Job
from norfab.models import Result
from typing import Union, List, Dict, Callable
from pydantic import BaseModel, Field
from pydantic import create_model as create_pydantic_model

from langchain.agents import create_agent
from langchain.agents.middleware import wrap_tool_call
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_ollama import ChatOllama
from langchain.tools import tool as langchain_tool
from . import norfab_agent

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
        log_queue (object): The logging queue object.

    Attributes:
        agent_inventory: The inventory loaded from the broker.
        llm_model (str): The language model to be used. Defaults to "llama3.1:8b".
        llm_temperature (float): The temperature setting for the language model. Defaults to 0.5.
        llm_base_url (str): The base URL for the language model. Defaults to "http://127.0.0.1:11434".
        llm_flavour (str): The flavour of the language model. Defaults to "ollama".
        llm: The language model instance.

    Methods:
        worker_exit(): Placeholder method for worker exit logic.
        get_version(): Produces a report of the versions of Python packages.
        get_inventory(): Returns the agent's inventory.
        get_status(): Returns the status of the worker.
        _chat_ollama(user_input, template=None) -> str: Handles the chat interaction with the Ollama LLM.
        chat(user_input, template=None) -> str: Handles the chat interaction with the user by processing the input through a language model.
    """

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
        self.llms = {}

        self.init_done_event.set()
        log.info(f"{self.name} - Started")

    def worker_exit(self):
        pass

    def get_llm(self, model: str = None, provider: str = None, **kwargs) -> object:
        """
        Retrieve or create an LLM instance.

        If no model_name is provided, this method consults agent service inventory for the
        ``default_model`` definition.

        Args:
            model (str | None): Name of the model to obtain.
            provider (str): Model provider name, e.g. "ollama".
            kwargs (dict): Any additional model parameters supported by LangChain.

        Returns:
            object | None: The LLM instance (e.g. ChatOllama)
        """
        # use inventory defined model or defaults
        if model is None:
            model_data = self.agent_inventory.get("default_model")
        else:
            model_data = {"model": model, **kwargs}

        # instantiate llm object
        if model in self.llms:
            llm = self.llms[model]
        elif provider == "ollama":
            llm = ChatOllama(**model_data)
        else:
            log.error(f"Unsupported LLM provider '{provider}'")
            return None

        # store LLM for future references
        self.llms.setdefault(model, llm)

        return llm

    def make_runnable(self, job, tool: dict, tool_name: str) -> Callable:
        def run_norfab_task(kwargs) -> dict:
            job.event(f"'{tool_name}' agent calling tool, arguments {kwargs}")

            # get service name
            tool_defined_service = tool["norfab"].get("service")
            llm_requested_service = kwargs.pop("service", None)
            service = tool_defined_service or llm_requested_service
            if not service:
                raise RuntimeError(
                    f"No service name provided for '{tool_name}' tool call"
                )

            # run norfab task
            ret = self.client.run_job(
                service=service,
                task=tool["norfab"]["task"],
                kwargs={**tool["norfab"].get("kwargs", {}), **kwargs},
            )

            job.event(f"'{tool_name}' tool call completed")
            job.event(f"Agent processing tool cal result...")

            return ret

        return RunnableLambda(run_norfab_task).with_types(
            input_type=tool.get("model_args_schema", {})
        )

    def make_pydantic_model(self, properties, model_name):
        fields = {}
        for field, definition in properties.items():
            field_type = definition.pop("type", "string")
            if field_type == "string":
                fields[field] = (
                    str,
                    Field(
                        definition.pop("default", None),
                        json_scham_extra={
                            "job_data": definition.pop("job_data", False),
                        },
                        **definition,
                    ),
                )
            else:
                raise TypeError(
                    f"Failed creating Pydantic model, unsupported field "
                    f"type '{field_type}' for '{model_name}' definition"
                )

        if fields:
            return create_pydantic_model(f"DynamicModel_{model_name}", **fields)
        else:
            return {}

    def make_tools(self, job, tools: dict) -> List[langchain_tool]:
        ret = []

        for tool_name, tool in tools.items():
            if isinstance(tool.get("model_args_schema"), dict):
                tool["model_args_schema"] = self.make_pydantic_model(
                    tool["model_args_schema"], tool_name
                )
            ret.append(
                langchain_tool(
                    tool_name,
                    self.make_runnable(job, tool, tool_name),
                    infer_schema=False,
                    parse_docstring=False,
                    description=tool["description"],
                    args_schema=tool.get("model_args_schema", {}),
                )
            )

        return ret

    def get_agent(self, job, agent: str = "NorFab"):
        if agent == "NorFab":
            return {
                "name": norfab_agent.name,
                "system_prompt": norfab_agent.system_prompt,
                "tools": self.make_tools(job, norfab_agent.tools),
                "llm": norfab_agent.llm,
            }
        elif self.is_url(agent):
            agent_definition = self.fetch_file(agent, raise_on_fail=True, read=True)
            agent_data = yaml.safe_load(agent_definition)
            return {
                "name": agent_data["name"],
                "system_prompt": agent_data["system_prompt"],
                "tools": self.make_tools(job, agent_data.get("tools", {})),
                "llm": agent_data.get("llm", {}),
            }
        else:
            log.error(f"Unsupported agent type '{agent}'")
            return None

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
    def invoke(
        self,
        job,
        instructions: str,
        name: str = "NorFab",
        verbose_result: bool = False,
    ) -> Result:
        ret = Result()
        job.event(f"Getting {name} agent ready")

        agent_data = self.get_agent(job, name)

        agent_instance = create_agent(
            name=agent_data["name"],
            model=self.get_llm(**agent_data["llm"]),
            system_prompt=agent_data["system_prompt"],
            tools=agent_data["tools"],
        )

        job.event(f"{name} agent thinking..")

        ret.result = agent_instance.invoke(
            {"messages": [{"role": "user", "content": instructions}]}
        )

        if verbose_result is False:
            ret.result = ret.result["messages"][-1].content

        return ret
