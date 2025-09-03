import logging
import sys
import threading
import time
import os
import signal
import importlib.metadata
import uvicorn
import contextlib

from norfab.core.worker import NFPWorker, Task, Job
from norfab.models import Result
from diskcache import FanoutCache
from mcp.server.fastmcp import FastMCP

SERVICE = "fastmcp"

log = logging.getLogger(__name__)


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
        self.api_prefix = "/"

        # get inventory from broker
        self.fastmcp_inventory = self.load_inventory()
        self.uvicorn_inventory = {
            "host": "0.0.0.0",
            "port": 8001,
            **self.fastmcp_inventory.pop("uvicorn", {}),
        }

        # instantiate cache
        self.cache_dir = os.path.join(self.base_dir, "cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache = self.get_diskcache()
        self.cache.expire()

        # start FastMCP server
        self.fastmcp_start()

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

    @Task(fastapi=False)
    def get_version(self) -> Result:

        libs = {
            "norfab": "",
            "mcp": "",
            "uvicorn": "",
            "pydantic": "",
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

    @Task(fastapi=False)
    def get_inventory(self) -> Result:
        return Result(
            result={**self.fastmcp_inventory, "uvicorn": self.uvicorn_inventory},
            task=f"{self.name}:get_inventory",
        )

    def fastmcp_start(self):
        self.app = FastMCP("NorFab MCP Server", stateless_http=True)

        @self.app.tool()
        def add(a: int, b: int) -> int:
            """Add two numbers"""
            print("!! Calling add tool")
            return a + b

        # start uvicorn server in a thread
        config = uvicorn.Config(
            app=self.app.streamable_http_app(), **self.uvicorn_inventory
        )
        self.uvicorn_server = uvicorn.Server(config=config)
        #
        self.uvicorn_server_thread = threading.Thread(target=self.uvicorn_server.run)
        self.uvicorn_server_thread.start()

        # wait for server to start
        while not self.uvicorn_server.started:
            time.sleep(0.001)

        log.info(
            f"{self.name} - MCP server started, serving FastMCP app at "
            f"http://{self.uvicorn_inventory['host']}:{self.uvicorn_inventory['port']}"
        )
