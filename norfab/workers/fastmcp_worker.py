import logging
import sys
import threading
import time
import os
import signal
import importlib.metadata

from fnmatch import fnmatch
from norfab.core.worker import NFPWorker, Task
from norfab.models import Result
from diskcache import FanoutCache
from mcp.server.fastmcp import FastMCP
from mcp import types
from typing import Any

SERVICE = "fastmcp"

log = logging.getLogger(__name__)


def service_tasks_discovery(
    worker: Any, cycles: int = 5, discover_service: str = "all"
) -> None:
    """
    Discovers available tasks from NorFab services and registers them
    as tools for the worker. This function periodically queries the
    broker for available services and their tasks, and registers each
    discovered task as a tool in the worker's `norfab_services_tasks`
    dictionary. It continues this process for a specified number of
    cycles or until the worker's exit event is set.

    Args:
        worker: The worker instance responsible for managing service
            tasks and tools.
        cycles (int, optional): The number of discovery cycles to perform.
        discover_service (str, optional): The name of a specific service
            to discover tasks from. If set to "all", tasks from all services
            are discovered. Defaults to "all".
    """
    result = {}
    while not worker.exit_event.is_set() and cycles > 0:
        tasks = []
        services = []
        try:
            # get a list of workers and construct a list of services
            services = worker.client.mmi("mmi.service.broker", "show_workers")
            services = [
                s["service"]
                for s in services["results"]
                if discover_service == "all" or s["service"] == discover_service
            ]

            # retrieve NorFab services and their tasks
            for service in services:
                # skip already discovered services
                if service in result:
                    continue
                service_tasks = worker.client.run_job(
                    service=service,
                    task="list_tasks",
                    workers="any",
                    timeout=3,
                )
                # skip if client request timed out
                if service_tasks is None:
                    continue
                for wres in service_tasks.values():
                    for t in wres["result"]:
                        t["service"] = service
                    tasks.extend(wres["result"])

            # create tools for discovered tasks
            for task in tasks:
                # skip task tool creation if set to false
                if task["mcp"] is False:
                    continue
                # save service to results
                result.setdefault(task["service"], {})
                # continue with creating tool for task
                task_tool = {
                    "name": task["name"],
                    "description": task["description"],
                    "inputSchema": task["inputSchema"],
                    "outputSchema": task["outputSchema"],
                    **task["mcp"],
                }
                task_tool["name"] = (
                    f"service_{task['service']}__task_{task_tool['name']}"
                )
                # skip already discovered tasks
                if task_tool["name"] in result[task["service"]]:
                    continue
                # save discovered task to return results
                result[task["service"]][task_tool["name"]] = {
                    "tool": types.Tool(**task_tool),
                    "task": task,
                }
            # save tools to worker tasks dictionary
            worker.norfab_services_tasks.update(result)
        except Exception as e:
            log.exception(f"Failed to discover services tasks, error: {e}")

        cycles -= 1
        time.sleep(5)

    return result


class FastMCPWorker(NFPWorker):

    def __init__(
        self,
        inventory: str,
        broker: str,
        worker_name: str,
        exit_event=None,
        init_done_event=None,
        log_level: str = None,
        log_queue: object = None,
    ):
        super().__init__(
            inventory, broker, SERVICE, worker_name, exit_event, log_level, log_queue
        )
        self.init_done_event = init_done_event
        self.exit_event = exit_event
        self.norfab_services_tasks = {}
        self.mcp_server_name = "NorFab MCP Server"

        # get inventory from broker
        self.fastmcp_inventory = self.load_inventory()
        self.fastmcp_inventory.setdefault("host", "0.0.0.0")
        self.fastmcp_inventory.setdefault("port", 8001)

        # instantiate cache
        self.cache_dir = os.path.join(self.base_dir, "cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache = self.get_diskcache()
        self.cache.expire()

        # start FastMCP server
        self.fastmcp_start()

        self.service_tasks_discovery_thread = threading.Thread(
            target=service_tasks_discovery, args=(self,)
        )
        self.service_tasks_discovery_thread.start()

        self.init_done_event.set()

    def get_diskcache(self) -> FanoutCache:
        """
        Initializes and returns a FanoutCache object.

        The FanoutCache is configured with the following parameters:

        - directory: The directory where the cache will be stored.
        - shards: Number of shards to use for the cache.
        - timeout: Timeout for cache operations in seconds.
        - size_limit: Maximum size of the cache in bytes.

        Returns:
            FanoutCache: An instance of FanoutCache configured with the specified parameters.
        """
        return FanoutCache(
            directory=self.cache_dir,
            shards=4,
            timeout=1,  # 1 second
            size_limit=1073741824,  #  1 GigaByte
        )

    def worker_exit(self):
        os.kill(os.getpid(), signal.SIGTERM)

    @Task(fastapi={"methods": ["GET"]})
    def get_version(self) -> Result:
        """
        Retrieves version information for key libraries and the current Python environment.

        Returns:
            Result: An object containing a dictionary with the version numbers of
                'norfab', 'mcp', 'uvicorn', 'pydantic', the Python version, and the platform.
                If a package is not found, its version will be an empty string.
        """

        libs = {
            "norfab": "",
            "uvicorn": "",
            "pydantic": "",
            "mcp": "",
            "python": sys.version.split(" ")[0],
            "platform": sys.platform,
        }
        # get version of packages installed
        for pkg in libs.keys():
            try:
                libs[pkg] = importlib.metadata.version(pkg)
            except importlib.metadata.PackageNotFoundError:
                pass

        return Result(task=f"{self.name}:get_version", result=libs)

    @Task(fastapi={"methods": ["GET"]})
    def get_inventory(self) -> Result:
        """
        Retrieves the current inventory from the FastMCP worker.

        Returns:
            Result: An object containing a copy of the worker's inventory and the task name.
        """
        return Result(
            result={**self.fastmcp_inventory},
            task=f"{self.name}:get_inventory",
        )

    @Task(fastapi={"methods": ["GET"]})
    def get_tools(
        self, brief: bool = False, service: str = "all", name: str = "*"
    ) -> Result:
        """
        Retrieve tools from the available norfab services, optionally filtered by service
        name and tool name pattern.

        Args:
            brief (bool, optional): If True, returns a list of tool names. If False,
                returns a dictionary with tool details.
            service (str, optional): The name of the service to filter tools by.
                Use "all" to include all services.
            name (str, optional): A glob pattern to match tool names.

        Returns:
            Result: An object containing the filtered tools. If brief is True, result
                is a list of tool names. Otherwise, result is a dictionary mapping tool
                names to their details.
        """
        ret = Result(
            result={},
            task=f"{self.name}:get_tools",
        )
        if brief:
            ret.result = []
            for service_name, tasks in self.norfab_services_tasks.items():
                if service == "all" or service_name == service:
                    for tool_name, tool_data in tasks.items():
                        if fnmatch(tool_name, name):
                            ret.result.append(tool_name)
        else:
            for service_name, tasks in self.norfab_services_tasks.items():
                if service == "all" or service_name == service:
                    for tool_name, tool_data in tasks.items():
                        if fnmatch(tool_name, name):
                            ret.result[tool_name] = tool_data["tool"].model_dump()

        return ret

    @Task(fastapi={"methods": ["POST"]})
    def discover(self, job, service: str = "all", progress: bool = True) -> Result:
        """
        Discovers available services tasks and auto-generate tools for them.

        Args:
            service (str, optional): The name of the service to discover. Defaults to "all".

        Returns:
            Result: An object containing the discovery results for the specified service.
        """
        job.event("Discovering NorFab services tasks")
        ret = Result(task=f"{self.name}:discover")
        ret.result = service_tasks_discovery(self, cycles=1, discover_service=service)

        return ret

    @Task(fastapi={"methods": ["GET"]})
    def get_status(self) -> Result:
        """
        Retrieves the current status of the application, including its name,
        URL, and the count of available tools.

        Returns:
            Result: An object containing a dictionary with the application's name,
                URL, and the number of tools, as well as the task identifier.
        """
        tools = self.get_tools(brief=True).result

        return Result(
            result={
                "name": self.app.name,
                "url": f"http://{self.fastmcp_inventory['host']}:{self.fastmcp_inventory['port']}/mcp/",
                "tools_count": len(tools),
            },
            task=f"{self.name}:get_status",
        )

    def fastmcp_start(self):
        """
        Starts the FastMCP server for the NorFab MCP application.

        This method initializes a FastMCP application instance with
        the specified host and port from `self.fastmcp_inventory`.

        It registers two MCP server endpoints:

          - `list_tools`: Asynchronously returns a list of available
            tools by aggregating all tools from `self.norfab_services_tasks`.
          - `call_tool`: Asynchronously handles tool invocation requests by
            parsing the tool name, extracting the corresponding service and
            task, and running the job using `self.client.run_job`.

        The FastMCP server is started in a separate thread using the
        "streamable-http" transport.
        """
        self.app = FastMCP(
            self.mcp_server_name,
            port=self.fastmcp_inventory["port"],
            host=self.fastmcp_inventory["host"],
        )

        @self.app._mcp_server.list_tools()
        async def list_tools() -> list[types.Tool]:
            ret = []
            for service, tasks in self.norfab_services_tasks.items():
                for tool_name, tool_data in tasks.items():
                    ret.append(tool_data["tool"])  # types.Tool object
            return ret

        @self.app._mcp_server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            log.error(f"Calling tool '{name}' with arguments: '{arguments}'")

            # form NorFab service and task names
            service, tool_name = name.split("__")
            service = service[8:]
            tool_name = tool_name[5:]
            task_name = self.norfab_services_tasks[service][name]["task"]["name"]

            log.error(
                f"Calling NorFab service '{service}' task '{task_name}' with arguments: '{arguments}'"
            )

            res = self.client.run_job(
                service=service,
                task=task_name,
                kwargs=arguments,
                workers="all",
            )

            return {"result": res}

        self.app_server_thread = threading.Thread(
            target=self.app.run, kwargs={"transport": "streamable-http"}
        )
        self.app_server_thread.start()

        log.info(
            f"{self.name} - MCP server started, serving FastMCP app at "
            f"http://{self.fastmcp_inventory['host']}:{self.fastmcp_inventory['port']}/mcp/"
        )
