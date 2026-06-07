import builtins
import importlib.metadata
import logging
import sys
from typing import Any, Dict

from picle.models import Outputters
from pydantic import (
    BaseModel,
    Field,
)

from norfab.core.worker import NFPWorker, Task
from norfab.models import Result

SERVICE = "DummyService"

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# DUMMY SERVICE WORKER CLASS
# ---------------------------------------------------------------------------------------------


class DummyServiceWorker(NFPWorker):
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
        """
        Initialize the DummyService.

        Args:
            inventory: The inventory object.
            broker (str): The broker address.
            worker_name (str): The name of the worker.
            exit_event (threading.Event, optional): Event to signal service exit.
            init_done_event (threading.Event, optional): Event to signal initialization completion.
            log_level (str, optional): The logging level.
            log_queue (object, optional): The logging queue.
        """
        super().__init__(
            inventory, broker, SERVICE, worker_name, exit_event, log_level, log_queue
        )
        self.init_done_event = init_done_event

        # get inventory from broker
        self.dummy_inventory = self.load_inventory()

        # signal to NFAPI that finished initializing
        self.init_done_event.set()
        log.info(f"{self.name} - Started")

    @Task(fastapi={"methods": ["GET"]})
    def get_version(self) -> Dict:
        """
        Retrieves the version information for specified libraries and the current Python environment.

        Returns:
            Dict: A dictionary containing the version information for the following keys:
                - "norfab": The version of the 'norfab' package, if installed.
                - "python": The version of the Python interpreter.
                - "platform": The platform on which the Python interpreter is running.

        Note:
            If the 'norfab' package is not installed, its version will be an empty string.
        """

        libs = {
            "norfab": "",
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
    def get_inventory(self) -> Dict:
        """
        Retrieves the dummy service inventory.

        Returns:
            Dict: A dictionary containing the dummy inventory data.
        """
        return Result(result=self.dummy_inventory)

    @Task(fastapi={"methods": ["POST"]})
    def dummy_task(self) -> Dict:
        """
        Dummy task
        """
        return Result(result="dummy")

    @Task(fastapi={"methods": ["POST"]})
    def input_request_task(self, job=None) -> Dict:
        """
        Dummy task that waits for client input before completing.
        """
        response = job.request_input(
            question="approve dummy task?",
            default="no",
            timeout=10,
            metadata={"task": "input_request_task"},
        )
        return Result(result={"response": response})

    @Task(fastapi={"methods": ["POST"]})
    def input_request_timeout_task(self, job=None) -> Dict:
        """
        Dummy task with a short client input timeout.
        """
        response = job.request_input(
            question="timeout dummy task?",
            default="no",
            timeout=1,
            metadata={"task": "input_request_timeout_task"},
        )
        return Result(result={"response": response})

    @Task(fastapi={"methods": ["POST"]})
    def event_task(self, job=None) -> Dict:
        """
        Dummy task that emits a custom progress event.
        """
        job.event(
            "dummy progress event",
            status="running",
            resource=["dummy-resource"],
        )
        return Result(result="event done")


# ---------------------------------------------------------------------------------------------
# DUMMY SERVICE SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class DummyServiceShowCommandsModel(BaseModel):
    inventory: Any = Field(
        None,
        description="show Dummy service inventory data",
        json_schema_extra={"function": "get_inventory"},
    )
    version: Any = Field(
        None,
        description="show Dummy service version report",
        json_schema_extra={"function": "get_version"},
    )

    class PicleConfig:
        outputter = Outputters.outputter_json

    @staticmethod
    def get_inventory(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = builtins.NFCLIENT.run_job(
            "DummyService", "get_inventory", workers=workers
        )
        return result

    @staticmethod
    def get_version(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = builtins.NFCLIENT.run_job(
            "DummyService", "get_version", workers=workers
        )
        return result


class DummyServiceNfcliShell(BaseModel):
    show: DummyServiceShowCommandsModel = Field(
        None, description="Show Dummy service parameters"
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[dummy]#"
