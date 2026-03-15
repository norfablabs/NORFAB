import importlib
import logging
import multiprocessing
import queue
import sys
import time
from typing import Any, List, Union

import psutil
import yaml
from fakenos import FakeNOS
from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictStr,
)

from norfab.core.worker import Job, NFPWorker, Task
from norfab.models import Result

from .nornir_inventory_tasks import FakeNOSNornirInventoryTasks

log = logging.getLogger(__name__)

SERVICE = "fakenos"

# -----------------------------------------------------------------------------------------
# FAKENOS NETWORK PROCESS FUNCTIONS
# -----------------------------------------------------------------------------------------


def fakenos_network_process(
    inventory: dict,
    stop_event: multiprocessing.Event,
    cmd_queue: multiprocessing.Queue,
    result_queue: multiprocessing.Queue,
    nos_plugins: list = None,
) -> None:
    """
    Target function executed in a dedicated process for each FakeNOS network.

    Runs a :class:`FakeNOS` instance and services method-call requests from the
    parent process via *cmd_queue*. Each request must be a
    ``(method_name, args, kwargs)`` 3-tuple. The return value (or a string
    representation of any exception) is placed on *result_queue* so the parent
    can retrieve it synchronously.

    Supported *method_name* values:

    * ``"_get_hosts_as_list"`` – returns a list of host-info dicts with the
      keys ``name``, ``platform``, ``port``, ``username``, ``password``.

    The loop exits when *stop_event* is set, after which the FakeNOS network
    is gracefully stopped.

    Args:
        inventory: FakeNOS inventory dictionary passed directly to
            :class:`FakeNOS`.
        stop_event: Shared :class:`multiprocessing.Event` used by the parent
            to signal the loop to exit.
        cmd_queue: Incoming method-call requests from the parent process.
        result_queue: Outgoing results delivered back to the parent process.
        nos_plugins: Optional list of NOS plugin definitions to register with
            FakeNOS.
    """
    nos_plugins = nos_plugins or []
    net = FakeNOS(inventory=inventory, plugins=nos_plugins)
    net.start()
    while not stop_event.is_set():
        try:
            method, args, kwargs = cmd_queue.get(timeout=0.1)
            try:
                if method == "_get_hosts_as_list":
                    result = [
                        {
                            "name": h.name,
                            "platform": h.platform,
                            "port": h.port,
                            "username": h.username,
                            "password": h.password,
                        }
                        for h in net._get_hosts_as_list()
                    ]
                else:
                    raise ValueError("Method not supported")
            except Exception as e:
                msg = f"Method {method} failed, error: {e}"
                log.error(msg)
                result = msg
            result_queue.put(result)
        except queue.Empty:
            pass
    net.stop()


# -----------------------------------------------------------------------------------------
# FAKENOS TASKS PYDANTIC MODELS
# -----------------------------------------------------------------------------------------


class FakeNOSStartInput(BaseModel):
    """Input model for the ``FakeNOSWorker.start`` task."""

    network: StrictStr = Field(..., description="FakeNOS network name to start")
    inventory: Union[dict, StrictStr, None] = Field(
        None, description="Inventory content (dict) or path/URL to an inventory file"
    )


class FakeNOSStopInput(BaseModel):
    """Input model for the ``FakeNOSWorker.stop`` task."""

    network: Union[StrictStr, None] = Field(
        None, description="FakeNOS network name to stop; stops all networks if omitted"
    )


class FakeNOSRestartInput(BaseModel):
    """Input model for the ``FakeNOSWorker.restart`` task."""

    network: StrictStr = Field(..., description="FakeNOS network name to restart")


class FakeNOSListNetworksInput(BaseModel):
    """Input model for the ``FakeNOSWorker.inspect_networks`` task."""

    network: Union[StrictStr, None] = Field(
        None, description="FakeNOS network name to show; shows all networks if omitted"
    )
    details: StrictBool = Field(
        False, description="Return detailed host information per network"
    )


# -----------------------------------------------------------------------------------------
# FAKENOS WORKER
# -----------------------------------------------------------------------------------------


class FakeNOSWorker(NFPWorker, FakeNOSNornirInventoryTasks):
    """
    NorFab worker that manages one or more FakeNOS virtual networks.

    Each FakeNOS network runs in its own child process so that slow or
    blocking SSH sessions do not affect the main worker event loop.  The
    worker exposes task methods for starting, stopping, restarting, and
    inspecting networks, as well as helpers for querying version and
    inventory information.
    """

    def __init__(
        self,
        inventory: Any,
        broker: str,
        worker_name: str,
        exit_event: Any = None,
        init_done_event: Any = None,
        log_level: str = "WARNING",
        log_queue: object = None,
    ) -> None:
        """
        Initialise the FakeNOS worker.

        Args:
            inventory: NorFab inventory object or dictionary used to
                configure the worker.
            broker: ZeroMQ address of the NorFab broker.
            worker_name: Unique name identifying this worker instance.
            exit_event: Optional :class:`threading.Event` (or compatible)
                that signals the worker to shut down.
            init_done_event: Event set when initialisation is complete,
                signalling the parent that the worker is ready.
            log_level: Logging level string (e.g. ``"DEBUG"``,
                ``"WARNING"``).
            log_queue: Optional queue used for multi-process log
                forwarding.
        """
        super().__init__(
            inventory, broker, SERVICE, worker_name, exit_event, log_level, log_queue
        )
        self.networks = {}
        self.init_done_event = init_done_event
        self.fakenos_inventory = self.load_inventory()
        self.nos_plugins = self.load_nos_plugins()

        log.info(f"{self.name} - Initialization completed")
        self.init_done_event.set()

    def worker_exit(self) -> None:
        """
        Gracefully stop all running FakeNOS networks on worker shutdown.
        """
        self.stop(job=None, network=None)
        self.networks.clear()

    def call_network(
        self, network: str, method: str, *args: Any, timeout: float = 10, **kwargs: Any
    ) -> Any:
        """
        Send a method call to a running FakeNOS process and return the result.

        Places a ``(method, args, kwargs)`` request on the network's command
        queue and blocks until the child process posts a response on the
        result queue.

        Args:
            network: Name of the target FakeNOS network.
            method: Name of the method to invoke inside the child process.
            *args: Positional arguments forwarded to the method.
            timeout: Maximum time in seconds to wait for a response.
            **kwargs: Keyword arguments forwarded to the method.

        Returns:
            The value returned by the child process.
        """
        entry = self.networks[network]
        entry["cmd_queue"].put((method, args, kwargs))
        result = entry["result_queue"].get(timeout=timeout)
        if isinstance(result, Exception):
            raise result
        return result

    def load_nos_plugins(self) -> List[dict]:
        """
        Load NOS plugin definitions declared in the worker inventory.

        Fetches each plugin file listed under the ``nos_plugins`` key of the
        FakeNOS inventory, parses the YAML content, and returns the list of
        plugin dictionaries ready to be passed to :class:`FakeNOS`.

        Returns:
            List of parsed NOS plugin dictionaries.  Empty if no plugins are
            configured or all plugins fail to load.
        """
        ret = []
        for name, plugin in self.fakenos_inventory.get("nos_plugins", {}).items():
            try:
                ret.append(yaml.safe_load(self.fetch_file(plugin, raise_on_fail=True)))
            except Exception as e:
                log.error(f"{name} - Plugin load failed, error: {e}", exc_info=True)
        return ret

    @Task(fastapi={"methods": ["GET"]})
    def get_version(self) -> Result:
        """
        Return version information for key packages and the Python runtime.

        Returns:
            :class:`Result` whose ``result`` field is a dict mapping package
            names (``norfab``, ``fakenos``, ``paramiko``, ``python``,
            ``platform``) to their installed version strings.
        """
        libs = {
            "norfab": "",
            "fakenos": "",
            "paramiko": "",
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
    def get_inventory(self) -> Result:
        """
        Return the raw FakeNOS inventory loaded by this worker.

        Returns:
            :class:`Result` whose ``result`` field is the full inventory dict.
        """
        return Result(result=self.fakenos_inventory)

    @Task(input=FakeNOSStopInput, fastapi={"methods": ["POST"]})
    def stop(self, job: Job, network: Union[str, None] = None) -> Result:
        """
        Stop one or all running FakeNOS networks.

        Signals the target child process(es) to exit via their stop event,
        waits up to one second for a clean shutdown, and kills any process
        that does not exit in time.

        Args:
            job: NorFab job context injected by the ``@Task`` decorator.
            network: Name of the network to stop.  If ``None`` (default),
                all currently running networks are stopped.
        """
        ret = Result(result={})
        names = [network] if network else list(self.networks)

        for name in names:
            log.info(f"Stopping '{name}' FakeNOS network")
            entry = self.networks.get(name)
            if entry:
                entry["stop_event"].set()
                entry["process"].join(timeout=1)
                if entry["process"].is_alive():
                    log.warning(f"{name} Did not stop in 1 second - killing process")
                    entry["process"].kill()
                    entry["process"].join()
                self.networks.pop(name, None)
                ret.result[name] = "stopped"
                log.info(f"Stopped '{name}' FakeNOS network")

        return ret

    @Task(input=FakeNOSStartInput, fastapi={"methods": ["POST"]})
    def start(
        self, job: Job, network: str, inventory: Union[str, dict, None] = None
    ) -> Result:
        """
        Start a new FakeNOS network in a dedicated child process.

        If *inventory* is a URL or file path, it is fetched and parsed before
        the network is started.  The network entry stored in
        ``self.networks`` preserves the resolved inventory dict so that
        ``restart`` can reuse it without re-fetching.

        Args:
            job: NorFab job context injected by the ``@Task`` decorator.
                Used to emit progress events visible to callers.
            network: Unique name to assign to this FakeNOS network.
            inventory: Inventory definition for the network.  Can be:

                * A ``dict`` with the FakeNOS inventory structure.
                * A ``str`` URL or file path that will be fetched and parsed
                  as YAML.
                * ``None`` to use the default inventory from the worker
                  configuration.
        """
        ret = Result()

        # fetch inventory
        if self.is_url(inventory):
            job.event(f"{network} fetching inventory")
            inventory = self.fetch_file(inventory, raise_on_fail=True)
            inventory = yaml.safe_load(inventory)

        log.info(f"{self.name} - Start: Starting '{network}' FakeNOS network")
        job.event(f"{network} starting network")

        stop_event = multiprocessing.Event()
        cmd_queue = multiprocessing.Queue()
        result_queue = multiprocessing.Queue()
        process = multiprocessing.Process(
            target=fakenos_network_process,
            args=(inventory, stop_event, cmd_queue, result_queue, self.nos_plugins),
            daemon=True,
            name=f"fakenos-{network}",
        )
        process.start()

        self.networks[network] = {
            "process": process,
            "stop_event": stop_event,
            "cmd_queue": cmd_queue,
            "result_queue": result_queue,
            "inventory": inventory,
            "start_time": time.time(),
        }

        ret.result = self.inspect_networks(
            job=job, network=network, details=True
        ).result

        return ret

    @Task(input=FakeNOSRestartInput, fastapi={"methods": ["POST"]})
    def restart(self, job: Job, network: str) -> Result:
        """
        Stop and restart an existing FakeNOS network.

        Retrieves the previously resolved inventory from ``self.networks``,
        stops the running process, then starts a fresh child process using the
        same inventory.  Progress events are forwarded to the caller via *job*.

        Args:
            job: NorFab job context injected by the ``@Task`` decorator.
            network: Name of the FakeNOS network to restart.  Must already
                exist in ``self.networks``.
        """
        ret = Result()
        log.info(f"{self.name} - Restart: Restarting '{network}' FakeNOS network")
        inventory = self.networks[network]["inventory"]
        self.stop(job, network)
        self.start(job, network, inventory)
        ret.result = self.inspect_networks(
            job=job, network=network, details=True
        ).result
        return ret

    @Task(input=FakeNOSListNetworksInput, fastapi={"methods": ["GET"]})
    def inspect_networks(
        self, job: Job, network: Union[str, None] = None, details: bool = True
    ) -> Result:
        """
        Return status information for one or all FakeNOS networks.

        When *details* is ``True`` each network entry includes the child
        process PID, liveness flag, and a list of host dicts retrieved from
        the child process.  When *details* is ``False`` only the list of
        network names is returned.

        Args:
            job: NorFab job context injected by the ``@Task`` decorator.
            network: Name of the network to inspect.  If ``None`` (default),
                all networks tracked by this worker are inspected.
            details: When ``True`` (default) query each network process for
                its host list and return extended per-network dicts.  When
                ``False`` return only the list of network names.
        """
        ret = Result()

        names = [network] if network else list(self.networks)

        if details:
            ret.result = {}
            for net_name in names:
                entry = self.networks[net_name]
                process = entry["process"]
                hosts = self.call_network(net_name, "_get_hosts_as_list")
                proc_info = {
                    "pid": process.pid,
                    "alive": process.is_alive(),
                    "hosts": hosts,
                    "hosts_count": len(hosts),
                }
                try:
                    ps = psutil.Process(process.pid)
                    mem = ps.memory_info()
                    uptime = round(
                        time.time() - entry.get("start_time", ps.create_time())
                    )
                    proc_info.update(
                        {
                            "status": ps.status(),
                            "uptime_seconds": uptime,
                            "cpu_percent": ps.cpu_percent(interval=0.1),
                            "memory_rss_mb": round(mem.rss / 1024 / 1024, 2),
                            "memory_vms_mb": round(mem.vms / 1024 / 1024, 2),
                            "num_threads": ps.num_threads(),
                        }
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    log.warning(f"{net_name} - Psutil metrics unavailable: {e}")
                ret.result[net_name] = proc_info
        else:
            ret.result = names

        return ret
