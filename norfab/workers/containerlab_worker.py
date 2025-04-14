import logging
import sys
import threading
import time
import os
import signal
import importlib.metadata

from norfab.core.worker import NFPWorker
from norfab.models import Result
from typing import Union, List, Dict, Any, Annotated, Optional

SERVICE = "containerlab"

log = logging.getLogger(__name__)


class ContainerlabWorker(NFPWorker):
    """
    FastAPContainerlabWorker IWorker is a worker class that integrates with containerlab to run network topologies.

    Args:
        inventory (str): Inventory configuration for the worker.
        broker (str): Broker URL to connect to.
        worker_name (str): Name of this worker.
        exit_event (threading.Event, optional): Event to signal worker to stop/exit.
        init_done_event (threading.Event, optional): Event to signal when worker is done initializing.
        log_level (str, optional): Logging level for this worker.
        log_queue (object, optional): Queue for logging.
    """

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

        # get inventory from broker
        self.containerlab_inventory = self.load_inventory()
        
        self.init_done_event.set()

    def worker_exit(self):
        """
        Terminates the current process by sending a SIGTERM signal to itself.

        This method retrieves the current process ID using `os.getpid()` and then
        sends a SIGTERM signal to terminate the process using `os.kill()`.
        """
        os.kill(os.getpid(), signal.SIGTERM)

    def get_version(self):
        """
        Produce a report of the versions of various Python packages.

        This method collects the versions of several specified Python packages
        and returns them in a dictionary.

        Returns:
            Result: An object containing the task name and a dictionary with
                    the package names as keys and their respective versions as values.
        """
        libs = {
            "norfab": "",
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

    def get_inventory(self) -> Dict:
        """
        Retrieve the inventory of the Containerlab worker.

        Returns:
            Dict: A dictionary containing the combined inventory of Containerlab.
        """
        return Result(
            result=self.containerlab_inventory,
            task=f"{self.name}:get_inventory",
        )
    
    def get_containerlab_status(self) -> Result:
        """
        Retrieve the status of the Containerlab worker.

        Returns:
            Result: A result object containing the status of the Containerlab worker.
        """
        status = "OS NOT SUPPORTED" if sys.platform.startswith("win") else "READY"
        return Result(
            task=f"{self.name}:get_containerlab_status",
            result={"status": status},
        )