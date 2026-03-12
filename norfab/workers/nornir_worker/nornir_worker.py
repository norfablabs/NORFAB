import importlib.metadata
import ipaddress
import logging
import os
import sys
import time
from threading import Lock
from typing import Any, Dict, Tuple, Union

import yaml
from nornir import InitNornir
from nornir_salt.plugins.functions import (
    FFun,
    FFun_functions,
    HostsKeepalive,
)
from nornir_salt.plugins.processors import (
    DataProcessor,
    DiffProcessor,
    NorFabEventProcessor,
    TestsProcessor,
    ToFileProcessor,
)
from nornir_salt.plugins.tasks import (
    connections as nr_connections,
)

from norfab.core.inventory import merge_recursively
from norfab.core.worker import Job, NFPWorker, Task, WorkerWatchDog
from norfab.models import Result

from .cfg_task import CfgTask
from .cli_task import CliTask
from .file_copy_task import FileCopyTask
from .netconf_task import NetconfTask
from .network_task import NetworkTask
from .nornir_models import GetNornirHosts, GetNornirHostsResponse
from .parse_task import ParseTask
from .runtime_inventory_task import RuntimeInventoryTask
from .task_task import TaskTask
from .test_task import TestTask

SERVICE = "nornir"

log = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Nornir Service watchdog class
# -----------------------------------------------------------------------


class WatchDog(WorkerWatchDog):
    """
    Class to monitor Nornir worker performance.

    Args:
        worker (Worker): The worker instance that this NornirWorker will manage.

    Attributes:
        worker (Worker): The worker instance being monitored.
        connections_idle_timeout (int): Timeout value for idle connections.
        connections_data (dict): Dictionary to store connection use timestamps.
        started_at (float): Timestamp when the watchdog was started.
        idle_connections_cleaned (int): Counter for idle connections cleaned.
        dead_connections_cleaned (int): Counter for dead connections cleaned.
        watchdog_tasks (list): List of tasks for the watchdog to run in a given order.
    """

    def __init__(self, worker):
        super().__init__(worker)
        self.worker = worker
        self.connections_idle_timeout = worker.nornir_worker_inventory.get(
            "connections_idle_timeout", None
        )
        self.connections_data = {}  # store connections use timestamps
        self.started_at = time.time()

        # stats attributes
        self.idle_connections_cleaned = 0
        self.dead_connections_cleaned = 0

        # list of tasks for watchdog to run in given order
        self.watchdog_tasks = [
            self.connections_clean,
            self.connections_keepalive,
        ]

    def stats(self) -> Dict:
        """
        Collects and returns statistics about the worker.

        Returns:
            dict: A dictionary containing the following keys:

                - runs (int): The number of runs executed by the worker.
                - timestamp (str): The current time in a human-readable format.
                - alive (int): The time in seconds since the worker started.
                - dead_connections_cleaned (int): The number of dead connections cleaned.
                - idle_connections_cleaned (int): The number of idle connections cleaned.
                - worker_ram_usage_mbyte (float): The current RAM usage of the worker in megabytes.
        """
        return {
            "runs": self.runs,
            "timestamp": time.ctime(),
            "alive": int(time.time() - self.started_at),
            "dead_connections_cleaned": self.dead_connections_cleaned,
            "idle_connections_cleaned": self.idle_connections_cleaned,
            "worker_ram_usage_mbyte": self.get_ram_usage(),
        }

    def configuration(self) -> Dict:
        """
        Returns the configuration settings for the worker.

        Returns:
            Dict: A dictionary containing the configuration settings:

                - "watchdog_interval" (int): The interval for the watchdog timer.
                - "connections_idle_timeout" (int): The timeout for idle connections.
        """
        return {
            "watchdog_interval": self.watchdog_interval,
            "connections_idle_timeout": self.connections_idle_timeout,
        }

    def connections_get(self) -> Dict:
        """
        Retrieve the current connections data.

        Returns:
            Dict: A dictionary containing the current connections data.
        """
        return {
            "connections": self.connections_data,
        }

    def connections_update(self, nr: Any, plugin: str) -> None:
        """
        Function to update connection use timestamps for each host

        Args:
            nr: Nornir object
            plugin: connection plugin name
        """
        conn_stats = {
            "last_use": None,
            "last_keepalive": None,
            "keepalive_count": 0,
        }
        for host_name in nr.inventory.hosts:
            self.connections_data.setdefault(host_name, {})
            self.connections_data[host_name].setdefault(plugin, conn_stats.copy())
            self.connections_data[host_name][plugin]["last_use"] = time.ctime()
        log.info(
            f"{self.worker.name} - updated connections use timestamps for '{plugin}'"
        )

    def connections_clean(self):
        """
        Cleans up idle connections based on the configured idle timeout.

        This method checks for connections that have been idle for longer than the
        specified `connections_idle_timeout` and disconnects them. The behavior
        varies depending on the value of `connections_idle_timeout`:

        - If `connections_idle_timeout` is None, no connections are disconnected.
        - If `connections_idle_timeout` is 0, all connections are disconnected.
        - If `connections_idle_timeout` is greater than 0, only connections that
          have been idle for longer than the specified timeout are disconnected.

        The method acquires a lock to ensure thread safety while modifying the
        connections data. It logs the disconnection actions and updates the
        `idle_connections_cleaned` counter.

        Raises:
            Exception: If an error occurs while attempting to disconnect idle connections, an error message is logged.
        """
        # dictionary keyed by plugin name and value as a list of hosts
        disconnect = {}
        if not self.worker.connections_lock.acquire(blocking=False):
            return
        try:
            # if idle timeout not set, connections don't age out
            if self.connections_idle_timeout is None:
                disconnect = {}
            # disconnect all connections for all hosts
            elif self.connections_idle_timeout == 0:
                disconnect = {"all": list(self.connections_data.keys())}
            # only disconnect aged/idle connections
            elif self.connections_idle_timeout > 0:
                for host_name, plugins in self.connections_data.items():
                    for plugin, conn_data in plugins.items():
                        last_use = time.mktime(time.strptime(conn_data["last_use"]))
                        age = time.time() - last_use
                        if age > self.connections_idle_timeout:
                            disconnect.setdefault(plugin, [])
                            disconnect[plugin].append(host_name)
            # run task to disconnect connections for aged hosts
            for plugin, hosts in disconnect.items():
                if not hosts:
                    continue
                aged_hosts = FFun(self.worker.nr, FL=hosts)
                aged_hosts.run(task=nr_connections, call="close", conn_name=plugin)
                log.debug(
                    f"{self.worker.name} watchdog, disconnected '{plugin}' "
                    f"connections for '{', '.join(hosts)}'"
                )
                self.idle_connections_cleaned += len(hosts)
                # wipe out connections data if all connection closed
                if plugin == "all":
                    self.connections_data = {}
                    break
                # remove disconnected plugin from host's connections_data
                for host in hosts:
                    self.connections_data[host].pop(plugin)
                    if not self.connections_data[host]:
                        self.connections_data.pop(host)
        except Exception as e:
            msg = f"{self.worker.name} - watchdog failed to close idle connections, error: {e}"
            log.error(msg)
        finally:
            self.worker.connections_lock.release()

    def connections_keepalive(self):
        """
        Keepalive connections and clean up dead connections if any.

        This method performs the following tasks:

        - If `connections_idle_timeout` is 0, it returns immediately without performing any actions.
        - Attempts to acquire a lock on `worker.connections_lock` to ensure thread safety.
        - Logs a debug message indicating that the keepalive process is running.
        - Uses `HostsKeepalive` to check and clean up dead connections, updating the `dead_connections_cleaned` counter.
        - Removes connections that are no longer present in the Nornir inventory.
        - Removes hosts from `connections_data` if they have no remaining connections.
        - Updates the keepalive statistics for each connection plugin, including the last keepalive time and keepalive count.
        - Logs an error message if an exception occurs during the keepalive process.
        - Releases the lock on `worker.connections_lock` in the `finally` block to ensure it is always released.

        Raises:
            Exception: If an error occurs during the keepalive process, it is logged as an error.
        """
        if self.connections_idle_timeout == 0:  # do not keepalive if idle is 0
            return
        if not self.worker.connections_lock.acquire(blocking=False):
            return
        try:
            log.debug(f"{self.worker.name} - watchdog running connections keepalive")
            stats = HostsKeepalive(self.worker.nr)
            self.dead_connections_cleaned += stats["dead_connections_cleaned"]
            # remove connections that are no longer present in Nornir inventory
            for host_name, host_connections in self.connections_data.items():
                # check if host is still in Nornir inventory
                if host_name not in self.worker.nr.inventory.hosts:
                    self.connections_data.pop(host_name, None)
                    continue
                # clean up specific connections for host
                for connection_name in list(host_connections.keys()):
                    if not self.worker.nr.inventory.hosts[host_name].connections.get(
                        connection_name
                    ):
                        self.connections_data[host_name].pop(connection_name)
            # remove host if no connections left
            for host_name in list(self.connections_data.keys()):
                if self.connections_data[host_name] == {}:
                    self.connections_data.pop(host_name)
            # update connections statistics
            for plugins in self.connections_data.values():
                for plugin in plugins.values():
                    plugin["last_keepalive"] = time.ctime()
                    plugin["keepalive_count"] += 1
        except Exception as e:
            msg = f"{self.worker.name} - watchdog HostsKeepalive check error: {e}"
            log.error(msg)
        finally:
            self.worker.connections_lock.release()


class NornirWorker(
    NFPWorker,
    TaskTask,
    CliTask,
    CfgTask,
    TestTask,
    NetworkTask,
    RuntimeInventoryTask,
    ParseTask,
    FileCopyTask,
    NetconfTask,
):
    """
    NornirWorker class for managing Nornir Service tasks.

    Args:
        inventory (str): Path to the inventory file.
        broker (str): Broker address.
        worker_name (str): Name of the worker.
        exit_event (threading.Event, optional): Event to signal worker exit. Defaults to None.
        init_done_event (threading.Event, optional): Event to signal initialization completion. Defaults to None.
        log_level (str, optional): Logging level. Defaults to None.
        log_queue (object, optional): Queue for logging. Defaults to None.

    Attributes:
        init_done_event (threading.Event): Event to signal initialization completion.
        tf_base_path (str): Base path for files folder saved using `tf` processor.
        connections_lock (threading.Lock): Lock for managing connections.
        nornir_inventory (dict): Inventory data for Nornir.
        watchdog (WatchDog): Watchdog instance for monitoring.
    """

    nr = None
    nornir_inventory = {}

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
        self.tf_base_path = os.path.join(self.base_dir, "tf")

        # misc attributes
        self.connections_lock = Lock()

        # initiate Nornir
        self.refresh_nornir(job=Job())

        # initiate watchdog
        self.watchdog = WatchDog(self)
        self.watchdog.start()

        # run startup hooks
        for f in self.inventory.hooks.get("nornir-startup", []):
            f["function"](self, *f.get("args", []), **f.get("kwargs", {}))

        if self.init_done_event is not None:
            self.init_done_event.set()

        log.info(f"{self.name} - Started")

    def worker_exit(self):
        """
        Executes all functions registered under the "nornir-exit" hook in the inventory.

        This method iterates through the list of hooks associated with the "nornir-exit"
        key in the inventory's hooks.

        For each hook, it calls the function specified in the hook, passing the current
        instance (`self`) as the first argument, followed by any additional positional
        and keyword arguments specified in the hook.
        """
        # run exit hooks
        for f in self.inventory.hooks.get("nornir-exit", []):
            f["function"](self, *f.get("args", []), **f.get("kwargs", {}))

    def init_nornir(self, inventory: dict) -> None:
        """
        Initializes the Nornir automation framework with the provided inventory.

        This method first closes any existing Nornir connections if present, optionally emitting a progress event.
        It then creates a new Nornir instance using the supplied inventory dictionary, which should contain
        configuration for logging, runner, hosts, groups, defaults, and user-defined settings.

        Args:
            inventory (dict): A dictionary containing Nornir inventory and configuration options.
        """
        # clean up existing Nornir instance
        with self.connections_lock:
            if self.nr is not None and self.nr.inventory.hosts:
                self.nr.close_connections()

            # initiate Nornir
            self.nr = InitNornir(
                logging=inventory.get("logging", {"enabled": False}),
                runner=inventory.get("runner", {}),
                inventory={
                    "plugin": "DictInventory",
                    "options": {
                        "hosts": inventory.get("hosts", {}),
                        "groups": inventory.get("groups", {}),
                        "defaults": inventory.get("defaults", {}),
                    },
                },
                user_defined=inventory.get("user_defined", {}),
            )

    def filter_hosts_and_validate(
        self, kwargs: Dict[str, Any], ret: Result
    ) -> Tuple[Any, Result]:
        """
        Helper method to filter hosts and validate results.

        Returns:
            tuple: (filtered_nornir, Result) where Result status set to
                `no_match` if no hosts matched.
        """
        self.nr.data.reset_failed_hosts()  # reset failed hosts before filtering
        filters = {k: kwargs.pop(k) for k in list(kwargs.keys()) if k in FFun_functions}
        filtered_nornir = FFun(self.nr, **filters)

        if not filtered_nornir.inventory.hosts:
            msg = (
                f"{self.name} - nothing to do, no hosts matched by filters '{filters}'"
            )
            log.debug(msg)
            ret.messages.append(msg)
            ret.status = "no_match"

        return filtered_nornir, ret

    @Task(fastapi={"methods": ["POST"]})
    def refresh_nornir(
        self,
        job: Job,
        progress: bool = False,
    ) -> Result:
        """
        Refreshes the Nornir instance by reloading the inventory from configured sources.

        This method performs the following steps:

            1. Loads the inventory configuration from the broker.
            2. If Netbox is specified in the inventory, pulls inventory data from Netbox.
            3. If Containerlab is specified in the inventory, pulls inventory data from Containerlab.
            4. Initializes the Nornir instance with the refreshed inventory.
            5. Optionally emits progress events at each stage if `progress` is True.

        Args:
            job: NorFab Job object containing relevant metadata
            progress (bool, optional): If True, emits progress events during the refresh process. Defaults to False.

        The inventory configuration is expected to be a dictionary with the following keys:

        - "logging": A dictionary specifying logging configuration (default: {"enabled": False}).
        - "runner": A dictionary specifying runner options (default: {}).
        - "hosts": A dictionary specifying host details (default: {}).
        - "groups": A dictionary specifying group details (default: {}).
        - "defaults": A dictionary specifying default values (default: {}).
        - "user_defined": A dictionary specifying user-defined options (default: {}).

        Returns:
            Result: A Result object indicating the outcome of the refresh operation.
        """
        ret = Result(task=f"{self.name}:refresh_nornir", result=True)

        # get inventory from broker
        self.nornir_worker_inventory = self.load_inventory()

        # pull Nornir inventory from Netbox
        if "netbox" in self.nornir_worker_inventory:
            self.nornir_inventory_load_netbox(job=job)
            job.event("Pulled Nornir inventory data from Netbox")

        # pull Nornir inventory from Containerlab
        if "containerlab" in self.nornir_worker_inventory:
            self.nornir_inventory_load_containerlab(
                job=job,
                **self.nornir_worker_inventory["containerlab"],
                re_init_nornir=False,
            )
            job.event("Pulled Nornir inventory data from Containerlab")

        job.event("Pulled inventories, refreshing Nornir instance")

        self.init_nornir(self.nornir_worker_inventory)

        job.event("Nornir instance refreshed")

        return ret

    @Task(fastapi={"methods": ["POST"]})
    def nornir_inventory_load_netbox(
        self,
        job: Job,
        progress: bool = False,
    ) -> Result:
        """
        Queries inventory data from Netbox Service and merges it into the Nornir inventory.

        This function checks if there is Netbox data in the inventory and retrieves
        it if available. It handles retries and timeout configurations, and ensures
        that necessary filters or devices are specified. The retrieved inventory
        data is then merged into the existing Nornir inventory.

        Args:
            job: NorFab Job object containing relevant metadata

        Logs:
            - Critical: If the inventory has no hosts, filters, or devices defined.
            - Error: If no inventory data is returned from Netbox.
            - Warning: If the Netbox instance returns no hosts data.
        """
        ret = Result(task=f"{self.name}:nornir_inventory_load_netbox", result=True)

        # form Netbox inventory load arguments
        if isinstance(self.nornir_worker_inventory.get("netbox"), dict):
            kwargs = self.nornir_worker_inventory["netbox"]
        elif self.nornir_worker_inventory.get("netbox") is True:
            kwargs = {}
        timeout = max(10, kwargs.pop("timeout", 100))

        # check if need to add devices list
        if "filters" not in kwargs and "devices" not in kwargs:
            if self.nornir_worker_inventory.get("hosts"):
                kwargs["devices"] = list(self.nornir_worker_inventory["hosts"])
            else:
                msg = f"{self.name} - inventory has no hosts, Netbox filters or devices defined"
                log.warning(msg)
                ret.result = False
                ret.messages = [msg]
                return ret

        nb_inventory_data = self.client.run_job(
            service="netbox",
            task="get_nornir_inventory",
            workers="any",
            kwargs=kwargs,
            timeout=timeout,
        )

        if nb_inventory_data is None:
            msg = f"{self.name} - Netbox get_nornir_inventory no inventory returned"
            log.error(msg)
            raise RuntimeError(msg)

        # merge Netbox inventory into Nornir inventory
        for wname, wdata in nb_inventory_data.items():
            if wdata["failed"] is False and wdata["result"].get("hosts"):
                merge_recursively(self.nornir_worker_inventory, wdata["result"])
                break
        else:
            msg = (
                f"{self.name} - Netbox worker(s) "
                f"'{', '.join(list(nb_inventory_data.keys()))}' returned no hosts data."
            )
            log.error(msg)
            job.event(msg, severity="ERROR")

        job.event("Completed processing Nornir inventory from Netbox")

        return ret

    @Task(fastapi={"methods": ["POST"]})
    def nornir_inventory_load_containerlab(
        self,
        job: Job,
        lab_name: str = None,
        groups: Union[None, list] = None,
        clab_workers: str = "all",
        use_default_credentials: bool = True,
        progress: bool = False,
        dry_run: bool = False,
        re_init_nornir: bool = True,
    ) -> Result:
        """
        Pulls the Nornir inventory from a Containerlab lab instance and merges it with the
        existing Nornir inventory.

        Args:
            job: NorFab Job object containing relevant metadata
            lab_name (str): The name of the Containerlab lab to retrieve the inventory from.
            groups (list, optional): A list of group names to include into the hosts' inventory.
            use_default_credentials (bool): Whether to use default credentials for the hosts.

        Returns:
            Result: A Result object indicating the success or failure of the operation.
                    If successful, the Nornir inventory is updated with the retrieved data.

        Notes:
            - The method retrieves inventory data from a Containerlab lab using a client job.
            - If the retrieved inventory contains host data, it is merged into the existing
              Nornir inventory using the `merge_recursively` function.
            - If no inventory or host data is returned, the method logs an error and marks
              the operation as failed.
            - After successful merging of inventory, Nornir instance is re-initialized with the
              updated inventory.
        """
        groups = groups or []
        ret = Result(
            task=f"{self.name}:nornir_inventory_load_containerlab", result=True
        )
        job.event(
            f"Pulling Containerlab '{lab_name or 'all'}' inventory from '{clab_workers}' workers"
        )

        clab_inventory_data = self.client.run_job(
            service="containerlab",
            task="get_nornir_inventory",
            workers=clab_workers,
            kwargs={
                "lab_name": lab_name,
                "groups": groups,
                "use_default_credentials": use_default_credentials,
            },
        )

        if clab_inventory_data is None:
            msg = f"{self.name} - Containerlab get_nornir_inventory no data returned"
            log.error(msg)
            raise RuntimeError(msg)

        job.event(f"Pulled Containerlab '{lab_name or 'all'}' lab inventory")

        if dry_run is True:
            ret.result = {w: r["result"] for w, r in clab_inventory_data.items()}
            return ret

        for wname, wdata in clab_inventory_data.items():
            # use inventory from first worker that returned hosts data
            if wdata["failed"] is False and wdata["result"].get("hosts"):
                merge_recursively(self.nornir_worker_inventory, wdata["result"])
                break
        else:
            msg = (
                f"{self.name} - Containerlab worker(s) '{', '.join(list(clab_inventory_data.keys()))}' "
                f"returned no hosts data for '{lab_name}' lab."
            )
            log.error(msg)
            raise RuntimeError(msg)

        job.event(
            f"Merged Containerlab '{lab_name or 'all'}' lab inventory with Nornir runtime inventory"
        )

        if re_init_nornir is True:
            self.init_nornir(self.nornir_worker_inventory)
            job.event("Nornir instance re-initialized")

        return ret

    def _add_processors(self, nr: Any, kwargs: Dict[str, Any], job: Job) -> Any:
        """
        Add various processors to the Nornir object based on the provided keyword arguments.

        Args:
            nr (Nornir): The Nornir object to which processors will be added.
            kwargs (dict): A dictionary of keyword arguments specifying which
                processors to add and their configurations.

        Keyword Args:
            tf (str, optional): Path to the file for ToFileProcessor.
            tf_skip_failed (bool, optional): Whether to skip failed tasks in ToFileProcessor.
            diff (str, optional): Configuration for DiffProcessor.
            diff_last (int, optional): Number of last diffs to keep for DiffProcessor.
            dp (list, optional): Configuration for DataProcessor.
            xml_flake (str, optional): Pattern for xml_flake function in DataProcessor.
            match (str, optional): Pattern for match function in DataProcessor.
            before (int, optional): Number of lines before match in DataProcessor.
            run_ttp (str, optional): Template for run_ttp function in DataProcessor.
            ttp_structure (str, optional): Structure for run_ttp results in DataProcessor.
            remove_tasks (bool, optional): Whether to remove tasks in DataProcessor and TestsProcessor.
            tests (list, optional): Configuration for TestsProcessor.
            subset (list, optional): Subset of tests for TestsProcessor.
            failed_only (bool, optional): Whether to include only failed tests in TestsProcessor.
            xpath (str, optional): XPath expression for DataProcessor.
            jmespath (str, optional): JMESPath expression for DataProcessor.
            iplkp (str, optional): IP lookup configuration for DataProcessor.
            ntfsm (bool, optional): Whether to use ntc-templates TextFSM parsing in DataProcessor.
            progress (bool, optional): Whether to emit progress events using NorFabEventProcessor.

        Returns:
            Nornir: The Nornir object with the added processors.
        """
        processors = []

        # extract parameters
        tf = kwargs.pop("tf", None)  # to file
        tf_skip_failed = kwargs.pop("tf_skip_failed", False)  # to file
        diff = kwargs.pop("diff", "")  # diff processor
        diff_last = kwargs.pop("diff_last", 1) if diff else None  # diff processor
        dp = kwargs.pop("dp", [])  # data processor
        xml_flake = kwargs.pop("xml_flake", "")  # data processor xml_flake function
        match = kwargs.pop("match", "")  # data processor match function
        before = kwargs.pop("before", 0)  # data processor match function
        run_ttp = kwargs.pop("run_ttp", None)  # data processor run_ttp function
        ttp_structure = kwargs.pop(
            "ttp_structure", "flat_list"
        )  # data processor run_ttp function
        remove_tasks = kwargs.pop("remove_tasks", True)  # tests and/or run_ttp
        tests = kwargs.pop("tests", None)  # tests
        subset = kwargs.pop("subset", [])  # tests
        failed_only = kwargs.pop("failed_only", False)  # tests
        groups = kwargs.pop("groups", [])  # tests
        xpath = kwargs.pop("xpath", "")  # xpath DataProcessor
        jmespath = kwargs.pop("jmespath", "")  # jmespath DataProcessor
        iplkp = kwargs.pop("iplkp", "")  # iplkp - ip lookup - DataProcessor
        ntfsm = kwargs.pop("ntfsm", False)  # ntfsm - ntc-templates TextFSM parsing
        progress = kwargs.pop(
            "progress", True
        )  # Emit progress events using NorFabEventProcessor

        # add processors if any
        if dp:
            processors.append(DataProcessor(dp))
        if iplkp:
            processors.append(
                DataProcessor(
                    [
                        {
                            "fun": "iplkp",
                            "use_dns": True if iplkp == "dns" else False,
                            "use_csv": iplkp if iplkp else False,
                        }
                    ]
                )
            )
        if xml_flake:
            processors.append(
                DataProcessor([{"fun": "xml_flake", "pattern": xml_flake}])
            )
        if xpath:
            processors.append(
                DataProcessor(
                    [{"fun": "xpath", "expr": xpath, "recover": True, "rm_ns": True}]
                )
            )
        if jmespath:
            processors.append(DataProcessor([{"fun": "jmespath", "expr": jmespath}]))
        if match:
            processors.append(
                DataProcessor([{"fun": "match", "pattern": match, "before": before}])
            )
        if run_ttp:
            processors.append(
                DataProcessor(
                    [
                        {
                            "fun": "run_ttp",
                            "template": run_ttp,
                            "res_kwargs": {"structure": ttp_structure},
                            "remove_tasks": remove_tasks,
                        }
                    ]
                )
            )
        if ntfsm:
            processors.append(DataProcessor([{"fun": "ntfsm"}]))
        if tests:
            processors.append(
                TestsProcessor(
                    tests=tests,
                    remove_tasks=remove_tasks,
                    failed_only=failed_only,
                    build_per_host_tests=True,
                    subset=subset,
                    render_tests=False,
                    groups=groups,
                )
            )
        if diff:
            processors.append(
                DiffProcessor(
                    diff=diff,
                    last=int(diff_last),
                    base_url=self.tf_base_path,
                    index=self.name,
                )
            )
        if progress:
            processors.append(NorFabEventProcessor(job=job))
        # append ToFileProcessor as the last one in the sequence
        if tf and isinstance(tf, str):
            processors.append(
                ToFileProcessor(
                    tf=tf,
                    base_url=self.tf_base_path,
                    index=self.name,
                    max_files=1000,
                    skip_failed=tf_skip_failed,
                    tf_index_lock=None,
                )
            )

        return nr.with_processors(processors)

    def load_job_data(self, job_data: Any) -> Dict:
        """
        Helper function to download job data YAML files and load it.

        Args:
            job_data (str): job data NorFab file path to download and load using YAML.

        Returns:dict
            data: The job data loaded from the YAML string.

        Raises:
            FileNotFoundError: If the job data is a URL and the file download fails.
        """
        if self.is_url(job_data):
            job_data = self.fetch_file(job_data)
            if job_data is None:
                msg = f"{self.name} - '{job_data}' job data file download failed"
                raise FileNotFoundError(msg)
            job_data = yaml.safe_load(job_data)

        return job_data

    # ----------------------------------------------------------------------
    # Nornir Service Jinja2 Filters
    # ----------------------------------------------------------------------

    def jinja2_network_hosts(self, network: str, pfxlen: bool = False) -> list:
        """
        Custom Jinja2 filter that return a list of hosts for a given IP network.

        Args:
            network (str): The network address in CIDR notation.
            pfxlen (bool, optional): If True, include the prefix length
                in the returned host addresses. Defaults to False.

        Returns:
            list: A list of host addresses as strings. If pfxlen is True,
                each address will include the prefix length.
        """
        ret = []
        ip_interface = ipaddress.ip_interface(network)
        prefixlen = ip_interface.network.prefixlen
        for ip in ip_interface.network.hosts():
            ret.append(f"{ip}/{prefixlen}" if pfxlen else str(ip))
        return ret

    def jinja2_nb_create_ip(
        self, prefix: str, device: str = None, interface: str = None, **kwargs
    ) -> str:
        """
        Jinja2 filter to get or create next available IP address from
        prefix using Netbox service.
        """
        kwargs["prefix"] = prefix
        kwargs["device"] = device
        kwargs["interface"] = interface
        reply = self.client.run_job(
            "netbox",
            "create_ip",
            kwargs=kwargs,
            workers="any",
            timeout=30,
        )
        # reply is a dict of {worker_name: results_dict}
        res = list(reply.values())[0]
        if res["failed"]:
            raise RuntimeError(res["messages"])
        return res["result"]["address"]

    def jinja2_nb_create_prefix(
        self, parent: str, description: str, prefixlen: int = 30, **kwargs
    ) -> str:
        """
        Jinja2 filter to get or create next available prefix from
        parent prefix using Netbox service.
        """
        kwargs["parent"] = parent
        kwargs["description"] = description
        kwargs["prefixlen"] = prefixlen
        reply = self.client.run_job(
            "netbox",
            "create_prefix",
            kwargs=kwargs,
            workers="any",
            timeout=30,
        )
        # reply is a dict of {worker_name: results_dict}
        res = list(reply.values())[0]
        if res["failed"]:
            raise RuntimeError(res["messages"])

        return res["result"]["prefix"]

    def jinja2_call_netbox(self, netbox_task: str) -> callable:
        """
        Returns a callable function to execute arbitrary NetBox service task.
        """

        def call_netbox(*args, **kwargs) -> dict:
            reply = self.client.run_job(
                "netbox",
                netbox_task,
                args=args,
                kwargs=kwargs,
                workers="any",
                timeout=300,
            )
            res = list(reply.values())[0]

            # check if has an error
            if res["failed"]:
                raise RuntimeError(res["messages"])

            # return result for single host only
            if len(kwargs.get("devices", [])) == 1:
                return res["result"][kwargs["devices"][0]]
            # return full results
            else:
                return res["result"]

        return call_netbox

    def add_jinja2_netbox(self) -> Dict:
        """
        Aggregates Jinja2 NetBox-related methods and functions into a dictionary
        for the ease of use within Jinja2 templates.
        """
        return {
            "get_connections": self.jinja2_call_netbox("get_connections"),
            "get_interfaces": self.jinja2_call_netbox("get_interfaces"),
            "get_circuits": self.jinja2_call_netbox("get_circuits"),
            "get_devices": self.jinja2_call_netbox("get_devices"),
            "rest": self.jinja2_call_netbox("rest"),
            "graphql": self.jinja2_call_netbox("graphql"),
            "create_ip": self.jinja2_nb_create_ip,
            "create_prefix": self.jinja2_nb_create_prefix,
        }

    def add_jinja2_filters(self) -> Dict:
        """
        Adds custom filters for use in Jinja2 templates using `|` syntaxis.

        Returns:
            dict (Dict): A dictionary where the keys are the names of the filters
                and the values are the corresponding filter functions.

                - "nb_create_ip": Method to get the next IP address.
                - "nb_create_prefix": Method to get next available prefix.
                - "network_hosts": Method to get IP network hosts.
        """
        return {
            "netbox.create_ip": self.jinja2_nb_create_ip,
            "netbox.create_prefix": self.jinja2_nb_create_prefix,
            "network_hosts": self.jinja2_network_hosts,
        }

    # ----------------------------------------------------------------------
    # Nornir Service Functions that exposed for calling
    # ----------------------------------------------------------------------

    @Task(
        fastapi={"methods": ["GET"]},
        input=GetNornirHosts,
        output=GetNornirHostsResponse,
    )
    def get_nornir_hosts(self, details: bool = False, **kwargs: dict) -> Result:
        """
        Retrieve a list of Nornir hosts managed by this worker.

        Args:
            details (bool): If True, returns detailed information about each host.
            **kwargs (dict): Hosts filters to apply when retrieving hosts.

        Returns:
            List[Dict]: A list of hosts with optional detailed information.
        """
        ret = Result(task=f"{self.name}:get_nornir_hosts", result={} if details else [])
        filtered_nornir, ret = self.filter_hosts_and_validate(kwargs, ret)
        if ret.status == "no_match":
            ret.result = None
        elif details:
            ret.result = {
                host_name: {
                    "platform": str(host.platform),
                    "hostname": str(host.hostname),
                    "port": str(host.port),
                    "groups": [str(g) for g in host.groups],
                    "username": str(host.username),
                }
                for host_name, host in filtered_nornir.inventory.hosts.items()
            }
        else:
            ret.result = list(filtered_nornir.inventory.hosts)
        return ret

    @Task(fastapi={"methods": ["GET"]})
    def get_inventory(self, **kwargs: dict) -> Result:
        """
        Retrieve running Nornir inventory for requested hosts

        Args:
            **kwargs (dict): Fx filters used to filter the inventory.

        Returns:
            Dict: A dictionary representation of the filtered inventory.
        """
        ret = Result(task=f"{self.name}:get_inventory", result={})
        filtered_nornir, ret = self.filter_hosts_and_validate(kwargs, ret)
        if ret.status != "no_match":
            ret.result = filtered_nornir.inventory.dict()
        return ret

    @Task(fastapi={"methods": ["GET"]})
    def get_version(self) -> Result:
        """
        Retrieve the versions of various libraries and system information.

        This method collects the version information of a predefined set of libraries
        and system details such as the Python version and platform. It attempts to
        import each library and fetch its version. If a library is not found, it is
        skipped.

        Returns:
            dict: a dictionary with the library names as keys and their respective
                version numbers as values. If a library is not found, its value will be
                an empty string.
        """
        libs = {
            "norfab": "",
            "scrapli": "",
            "scrapli-netconf": "",
            "scrapli-community": "",
            "paramiko": "",
            "netmiko": "",
            "napalm": "",
            "nornir": "",
            "ncclient": "",
            "nornir-netmiko": "",
            "nornir-napalm": "",
            "nornir-scrapli": "",
            "nornir-utils": "",
            "tabulate": "",
            "xmltodict": "",
            "puresnmp": "",
            "pygnmi": "",
            "pyyaml": "",
            "jmespath": "",
            "jinja2": "",
            "ttp": "",
            "nornir-salt": "",
            "lxml": "",
            "ttp-templates": "",
            "ntc-templates": "",
            "cerberus": "",
            "pydantic": "",
            "requests": "",
            "textfsm": "",
            "N2G": "",
            "dnspython": "",
            "pythonping": "",
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
    def get_watchdog_stats(self) -> Result:
        """
        Retrieve the statistics from the watchdog.

        Returns:
            Result: An object containing the statistics from the watchdog.
        """
        return Result(result=self.watchdog.stats())

    @Task(fastapi={"methods": ["GET"]})
    def get_watchdog_configuration(self) -> Result:
        """
        Retrieves the current configuration of the watchdog.

        Returns:
            Result: An object containing the watchdog configuration.
        """
        return Result(result=self.watchdog.configuration())

    @Task(fastapi={"methods": ["GET"]})
    def get_watchdog_connections(self) -> Result:
        """
        Retrieve the list of connections currently managed by watchdog.

        Returns:
            Result: An instance of the Result class containing the current
                watchdog connections.
        """
        return Result(result=self.watchdog.connections_get())
