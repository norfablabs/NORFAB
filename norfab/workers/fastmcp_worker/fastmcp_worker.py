import importlib.metadata
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime
from fnmatch import fnmatch
from typing import Any, Optional

from diskcache import FanoutCache
from mcp import types
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from pydantic import AnyHttpUrl

from norfab.core.worker import Job, NFPWorker, Task
from norfab.models import Result

from .fastmcp_models import (
    BearerTokenCheckInput,
    BearerTokenDeleteInput,
    BearerTokenListInput,
    BearerTokenListResult,
    BearerTokenStoreInput,
    BoolResult,
    DiscoverInput,
    DiscoverResult,
    GetInventoryInput,
    GetInventoryResult,
    GetStatusInput,
    GetStatusResult,
    GetToolsInput,
    GetToolsResult,
    GetVersionInput,
    GetVersionResult,
)

SERVICE = "fastmcp"

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# FASTMCP TASKS MODELS
# --------------------------------------------------------------------------


class DiskcacheBearerTokenVerifier:
    """
    MCP bearer token verifier backed by the worker diskcache token database.
    """

    def __init__(self, cache: FanoutCache, scopes: list[str] | None = None) -> None:
        self.cache = cache
        self.scopes = scopes or []

    async def verify_token(self, token: str) -> AccessToken | None:
        self.cache.expire()
        cache_key = f"bearer_token::{token}"
        token_data, expires, tag = self.cache.get(
            cache_key, default=None, expire_time=True, tag=True
        )
        if token_data is None:
            return None

        return AccessToken(
            token=token,
            client_id=token_data.get("username") or tag or "unknown",
            scopes=self.scopes,
            expires_at=int(expires) if expires is not None else None,
        )


def is_task_allowed_by_policy(
    policy: list[dict[str, Any]], service: str, task_name: str
) -> bool:
    """
    Return True when a NorFab service task is allowed by FastMCP tools policy.

    Policy entries are evaluated in order; the first matching rule wins and the
    default action is allow.
    """
    action = "allow"
    for rule in policy:
        if fnmatch(service, rule.get("service", "*")):
            if any(fnmatch(task_name, p) for p in rule.get("tasks", ["*"])):
                action = rule.get("action", "allow").lower()
                break

    return action != "reject"


def service_tasks_discovery(
    worker: Any, cycles: int = 5, discover_service: str = "all"
) -> dict:
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
            policy = worker.fastmcp_inventory.get("tools", {}).get("policy", [])
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
                # evaluate policy entries; first match wins, default is allow
                if policy and not is_task_allowed_by_policy(
                    policy, task["service"], task["name"]
                ):
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
        exit_event: Optional[threading.Event] = None,
        init_done_event: Optional[threading.Event] = None,
        log_level: Optional[str] = None,
        log_queue: Optional[object] = None,
    ) -> None:
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
        self.fastmcp_inventory.setdefault("authentication_enabled", False)
        self.fastmcp_inventory.setdefault("auth_bearer", {})
        self.authentication_enabled = self.is_authentication_enabled()

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

    def worker_exit(self) -> None:
        os.kill(os.getpid(), signal.SIGTERM)

    def is_authentication_enabled(self) -> bool:
        """
        Return True when MCP bearer token authentication is enabled in inventory.
        """
        value = self.fastmcp_inventory.get("authentication_enabled", False)
        if isinstance(value, str):
            return value.lower() in ("1", "true", "yes", "on")
        return value is True

    def get_auth_server_url(self) -> str:
        """
        Return the default public MCP auth/resource URL.
        """
        host = self.fastmcp_inventory["host"]
        if host in ("0.0.0.0", "::", ""):
            host = "127.0.0.1"
        elif ":" in host and not host.startswith("["):
            host = f"[{host}]"

        return f"http://{host}:{self.fastmcp_inventory['port']}"

    def get_auth_settings(self) -> AuthSettings:
        """
        Build MCP authentication settings from FastMCP inventory.
        """
        auth_bearer = self.fastmcp_inventory.get("auth_bearer", {})
        auth_server_url = self.get_auth_server_url()

        return AuthSettings(
            issuer_url=AnyHttpUrl(auth_bearer.get("issuer_url", auth_server_url)),
            resource_server_url=AnyHttpUrl(
                auth_bearer.get("resource_server_url", auth_server_url)
            ),
            required_scopes=auth_bearer.get("required_scopes"),
        )

    def get_token_scopes(self) -> list[str]:
        """
        Return scopes assigned to locally verified bearer tokens.
        """
        auth_bearer = self.fastmcp_inventory.get("auth_bearer", {})
        return auth_bearer.get("token_scopes", auth_bearer.get("required_scopes", []))

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
        Retrieves the current inventory from the FastMCP worker.

        Returns:
            Result: An object containing a copy of the worker's inventory and the task name.
        """
        return Result(
            result={**self.fastmcp_inventory},
            task=f"{self.name}:get_inventory",
        )

    @Task(
        input=GetToolsInput,
        output=GetToolsResult,
        fastapi={"methods": ["GET"]},
        mcp={
            "annotations": {
                "title": "Get MCP Tools",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            }
        },
    )
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

    @Task(input=BearerTokenStoreInput, output=BoolResult, fastapi=False, mcp=False)
    def bearer_token_store(
        self, job: Job, username: str, token: str, expire: int = None
    ) -> Result:
        """
        Store a bearer token in the FastMCP worker token database.
        """
        expire = expire or self.fastmcp_inventory.get("auth_bearer", {}).get(
            "token_ttl", expire
        )
        self.cache.expire()
        cache_key = f"bearer_token::{token}"
        if cache_key in self.cache:
            user_token = self.cache.get(cache_key)
        else:
            user_token = {
                "token": token,
                "username": username,
                "created": str(datetime.now()),
            }
        self.cache.set(cache_key, user_token, expire=expire, tag=username)

        return Result(task=f"{self.name}:bearer_token_store", result=True)

    @Task(input=BearerTokenDeleteInput, output=BoolResult, fastapi=False, mcp=False)
    def bearer_token_delete(
        self, job: Job, username: str = None, token: str = None
    ) -> Result:
        """
        Delete bearer tokens by username or token value.
        """
        self.cache.expire()
        token_removed_count = 0
        if token:
            cache_key = f"bearer_token::{token}"
            if cache_key in self.cache:
                if self.cache.delete(cache_key, retry=True):
                    token_removed_count = 1
                else:
                    raise RuntimeError(f"Failed to remove {username} token from cache")
        elif username:
            token_removed_count = self.cache.evict(tag=username, retry=True)
        else:
            raise Exception("Cannot delete, either username or token must be provided")

        log.info(
            f"{self.name} removed {token_removed_count} token(s) for user {username}"
        )

        return Result(task=f"{self.name}:bearer_token_delete", result=True)

    @Task(
        input=BearerTokenListInput,
        output=BearerTokenListResult,
        fastapi=False,
        mcp=False,
    )
    def bearer_token_list(self, job: Job, username: str = None) -> Result:
        """
        List bearer tokens stored in the FastMCP worker token database.
        """
        self.cache.expire()
        ret = Result(task=f"{self.name}:bearer_token_list", result=[])

        for cache_key in self.cache:
            if not str(cache_key).startswith("bearer_token::"):
                continue
            token_data, expires, tag = self.cache.get(
                cache_key, expire_time=True, tag=True
            )
            if username and tag != username:
                continue
            if expires is not None:
                expires = datetime.fromtimestamp(expires)
            creation = datetime.fromisoformat(token_data["created"])
            age = datetime.now() - creation
            ret.result.append(
                {
                    "username": token_data["username"],
                    "token": token_data["token"],
                    "age": str(age),
                    "creation": str(creation),
                    "expires": str(expires),
                }
            )

        if not ret.result:
            ret.result = [
                {
                    "username": "",
                    "token": "",
                    "age": "",
                    "creation": "",
                    "expires": "",
                }
            ]

        return ret

    @Task(input=BearerTokenCheckInput, output=BoolResult, fastapi=False, mcp=False)
    def bearer_token_check(self, token: str, job: Job) -> Result:
        """
        Check if a bearer token is present and active in the FastMCP token database.
        """
        self.cache.expire()
        cache_key = f"bearer_token::{token}"
        return Result(
            task=f"{self.name}:bearer_token_check", result=cache_key in self.cache
        )

    @Task(
        input=DiscoverInput,
        output=DiscoverResult,
        fastapi={"methods": ["POST"]},
        mcp={
            "annotations": {
                "title": "Discover MCP Tools",
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            }
        },
    )
    def discover(self, job, service: str = "all", progress: bool = True) -> Result:
        """
        Discovers available services tasks and auto-generate tools for them.

        Args:
            service (str, optional): The name of the service to discover. Defaults to "all".

        Returns:
            Result: An object containing the discovery results for the specified service.
        """
        job.event("discovering NorFab services tasks")
        ret = Result(task=f"{self.name}:discover")
        ret.result = service_tasks_discovery(self, cycles=1, discover_service=service)

        return ret

    @Task(
        input=GetStatusInput,
        output=GetStatusResult,
        fastapi={"methods": ["GET"]},
        mcp={
            "annotations": {
                "title": "Get MCP Status",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            }
        },
    )
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

    def get_allowed_task_call(self, name: str) -> tuple[str, str]:
        """
        Resolve an MCP tool name to a NorFab service/task pair and enforce policy.
        """
        try:
            service_part, tool_part = name.split("__", 1)
        except ValueError as exc:
            raise ValueError(f"Invalid NorFab MCP tool name '{name}'") from exc

        if not service_part.startswith("service_") or not tool_part.startswith("task_"):
            raise ValueError(f"Invalid NorFab MCP tool name '{name}'")

        service = service_part[8:]
        tool_name = tool_part[5:]
        if not service or not tool_name:
            raise ValueError(f"Invalid NorFab MCP tool name '{name}'")

        if service not in self.norfab_services_tasks:
            raise ValueError(f"NorFab service '{service}' not found for tool '{name}'")

        if name not in self.norfab_services_tasks[service]:
            raise ValueError(f"NorFab MCP tool '{name}' is not registered")

        task_name = self.norfab_services_tasks[service][name]["task"]["name"]
        policy = self.fastmcp_inventory.get("tools", {}).get("policy", [])
        if policy and not is_task_allowed_by_policy(policy, service, task_name):
            log.warning(
                f"Rejected MCP tool call '{name}' by policy: "
                f"service='{service}', task='{task_name}'"
            )
            raise PermissionError(
                f"MCP tool call '{name}' is rejected by FastMCP tools policy"
            )

        return service, task_name

    def fastmcp_start(self) -> None:
        """
        Starts the FastMCP server for the NorFab MCP application.

        This method initializes a FastMCP application instance with
        the specified host and port from `self.fastmcp_inventory`.

        It registers two MCP server endpoints:

          - `list_tools`: Asynchronously returns a list of available
            tools by aggregating all tools from `self.norfab_services_tasks`,
            filtered by the inventory ``tools.allow`` glob patterns.
          - `call_tool`: Asynchronously handles tool invocation requests by
            parsing the tool name, checking it against the ``tools.allow``
            inventory patterns, extracting the corresponding service and
            task, and running the job using `self.client.run_job`.

        The FastMCP server is started in a separate thread using the
        "streamable-http" transport.
        """
        fastmcp_kwargs = {
            "port": self.fastmcp_inventory["port"],
            "host": self.fastmcp_inventory["host"],
        }
        if self.authentication_enabled:
            fastmcp_kwargs.update(
                {
                    "auth": self.get_auth_settings(),
                    "token_verifier": DiskcacheBearerTokenVerifier(
                        self.cache, scopes=self.get_token_scopes()
                    ),
                }
            )

        self.app = FastMCP(self.mcp_server_name, **fastmcp_kwargs)

        @self.app._mcp_server.list_tools()
        async def list_tools() -> list[types.Tool]:
            ret = []
            for service, tasks in self.norfab_services_tasks.items():
                for tool_name, tool_data in tasks.items():
                    ret.append(tool_data["tool"])  # types.Tool object
            return ret

        @self.app._mcp_server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            log.info(f"Calling tool '{name}' with arguments: '{arguments}'")

            service, task_name = self.get_allowed_task_call(name)

            log.info(
                f"Calling NorFab service '{service}' task '{task_name}' with arguments: '{arguments}'"
            )

            return self.client.run_job(
                service=service,
                task=task_name,
                kwargs=arguments,
                workers="all",
            )

        self.app_server_thread = threading.Thread(
            target=self.app.run, kwargs={"transport": "streamable-http"}
        )
        self.app_server_thread.start()

        log.info(
            f"{self.name} - MCP server started, serving FastMCP app at "
            f"http://{self.fastmcp_inventory['host']}:{self.fastmcp_inventory['port']}/mcp/"
        )
