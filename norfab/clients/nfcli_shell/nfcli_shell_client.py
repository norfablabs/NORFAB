"""
PICLE Shell CLient
==================

Client that implements interactive shell to work with NorFab.
"""

import builtins
import importlib.metadata
import logging
import sys
from enum import Enum
from typing import Any, List, Optional, Union

from picle import App
from picle.models import Outputters, PipeFunctionsModel
from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
)
from rich.console import Console

from norfab.core.nfapi import NorFab
from norfab.models.norfab_configuration import NorFabInventory
from norfab.workers.filesharing_worker.filesharing_models import (
    FileDetailsInput,
    ListFilesInput,
)

from .agent import agent_picle_shell
from .client_agent import client_agent_picle_shell
from .common import ClientRunJobArgs, log_error_or_result, run_future_job
from .containerlab import containerlab_picle_shell
from .fakenos import fakenos_picle_shell
from .fastapi import fastapi_picle_shell
from .fastmcp import fastmcp_picle_shell
from .netbox import netbox_picle_shell
from .norfab_jobs_shell import NorFabJobsShellCommands
from .nornir import nornir_picle_shell
from .workers.workers_picle_shell import (
    NorfabWorkersCommands,
    ShowWorkersJobsModel,
    ShowWorkersStatistics,
    ShowWorkersStatusBrief,
    ShowWorkersVersion,
)
from .workflow import workflow_picle_shell

NFCLIENT = None
RICHCONSOLE = Console()
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class LogLevel(str, Enum):
    NOTSET = "NOTSET"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ShowBrokerModel(BaseModel):
    version: Any = Field(
        None,
        description="Show broker version report",
        json_schema_extra={
            "outputter": Outputters.outputter_yaml,
            "absolute_indent": 2,
            "function": "show_broker_version",
        },
    )
    inventory: Any = Field(
        None,
        description="Show broker inventory",
        json_schema_extra={
            "outputter": Outputters.outputter_yaml,
            "function": "show_broker_inventory",
        },
    )
    workers: ShowWorkersStatusBrief = Field(
        None, description="Show workers known to broker"
    )

    class PicleConfig:
        outputter = Outputters.outputter_yaml
        outputter_kwargs = {"absolute_indent": 2}
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args: object, **kwargs: object):
        return ShowBrokerModel._run_broker_mmi("show_broker")

    @staticmethod
    def show_broker_version(**kwargs: object):
        return ShowBrokerModel._run_broker_mmi("show_broker_version")

    @staticmethod
    def show_broker_inventory(**kwargs: object):
        return ShowBrokerModel._run_broker_mmi("show_broker_inventory")

    @staticmethod
    def _run_broker_mmi(task: str):
        nfclient = getattr(builtins, "NFCLIENT", NFCLIENT)
        reply = nfclient.mmi("mmi.service.broker", task)
        if reply["errors"]:
            return "\n".join(reply["errors"])
        else:
            return reply["results"]


class ShowNorfabWorkersModel(BaseModel):
    jobs: ShowWorkersJobsModel = Field(None, description="Show workers jobs")
    statistics: ShowWorkersStatistics = Field(
        None, description="Show workers statistics"
    )
    version: ShowWorkersVersion = Field(None, description="Show workers version info")

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_nested


class ShowNorfabClientModel(BaseModel):
    version: Any = Field(
        None,
        description="show nfcli client version report",
        json_schema_extra={"function": "show_version"},
    )
    jobs: NorFabJobsShellCommands = Field(
        None, description="Show NorFab Jobs for all services"
    )

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_yaml
        outputter_kwargs = {"absolute_indent": 2}

    @staticmethod
    def run(*args: object, **kwargs: object):
        nfclient = getattr(builtins, "NFCLIENT", NFCLIENT)
        return {
            "client-type": "PICLE Shell",
            "status": "connected",
            "name": nfclient.name,
            "zmq-name": nfclient.zmq_name,
            "broker": {
                "endpoint": nfclient.broker,
                "reconnects": nfclient.stats_reconnect_to_broker,
                "messages-rx": nfclient.stats_recv_from_broker,
                "messages-tx": nfclient.stats_send_to_broker,
            },
            "directories": {
                "base-dir": nfclient.base_dir,
                "public-keys-dir": nfclient.public_keys_dir,
                "private-keys-dir": nfclient.private_keys_dir,
            },
            "security": {
                "client-private-key-file": nfclient.client_private_key_file,
                "broker-public-key-file": nfclient.broker_public_key_file,
                "zmq_auth": nfclient.zmq_auth,
            },
        }

    @staticmethod
    def show_version(**kwargs: object):
        libs = {
            "norfab": "",
            "pyyaml": "",
            "pyzmq": "",
            "psutil": "",
            "tornado": "",
            "jinja2": "",
            "picle": "",
            "rich": "",
            "tabulate": "",
            "pydantic": "",
            "pyreadline3": "",
            "python": sys.version.split(" ")[0],
            "platform": sys.platform,
        }
        # get version of packages installed
        for pkg in libs.keys():
            try:
                libs[pkg] = importlib.metadata.version(pkg)
            except importlib.metadata.PackageNotFoundError:
                pass

        return libs


class ShowNorfabLoggingModel(BaseModel):
    broker: StrictBool = Field(
        True,
        description="Retrieve broker logs",
        json_schema_extra={"presence": True},
    )
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Workers to retrieve logs from"
    )
    service: StrictStr = Field(
        "all", description="Service to retrieve worker logs from"
    )
    details: StrictBool = Field(
        False,
        description="Return complete log records",
        json_schema_extra={"presence": True},
    )
    last: Optional[StrictInt] = Field(
        100,
        description="Return the last N log records after filtering",
    )
    level: Optional[LogLevel] = Field(None, description="Filter by log level")
    logger: Optional[StrictStr] = Field(None, description="Filter by logger name")
    since: Optional[StrictStr] = Field(
        None, description="Filter records at or after timestamp"
    )
    until: Optional[StrictStr] = Field(
        None, description="Filter records at or before timestamp"
    )

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_pprint

    @staticmethod
    def source_workers() -> list:
        nfclient = getattr(builtins, "NFCLIENT", NFCLIENT)
        reply = nfclient.mmi("mmi.service.broker", "show_workers")
        return ["all"] + [worker["name"] for worker in reply["results"]]

    @staticmethod
    def source_service() -> list:
        nfclient = getattr(builtins, "NFCLIENT", NFCLIENT)
        reply = nfclient.mmi("mmi.service.broker", "show_workers")
        services = sorted({worker["service"] for worker in reply["results"]})
        return ["all"] + services

    @staticmethod
    def run(*args: object, **kwargs: object):
        details = kwargs.pop("details", False)
        records = ShowNorfabLoggingModel._collect_records(kwargs)
        records.sort(key=lambda item: item.get("ts") or "9999")

        last = kwargs.get("last", 100)
        records = records[-last:] if last else records
        if details:
            return records, Outputters.outputter_nested

        return ShowNorfabLoggingModel._format_records(records)

    @staticmethod
    def _collect_records(kwargs: dict) -> list:
        nfclient = getattr(builtins, "NFCLIENT", NFCLIENT)
        broker = kwargs.pop("broker", True)
        workers = kwargs.pop("workers", "all")
        service = kwargs.pop("service", "all")
        filters = {"last": kwargs.get("last", 100)}
        filters.update(
            {
                k: v.value if isinstance(v, Enum) else v
                for k, v in kwargs.items()
                if v is not None
            }
        )
        records = []

        if broker:
            reply = nfclient.mmi(
                "mmi.service.broker", "get_logs", kwargs=filters, timeout=600
            )
            if reply.get("errors"):
                records.append(
                    {
                        "ts": "",
                        "level": "ERROR",
                        "role": "broker",
                        "name": "NFPBroker",
                        "message": "; ".join(reply["errors"]),
                    }
                )
            else:
                records.extend(reply.get("results", []))

        if workers:
            reply = nfclient.run_job(
                service, "get_logs", workers=workers, kwargs=filters, timeout=600
            )
            for worker_name, result in reply.items():
                if result.get("failed"):
                    records.append(
                        {
                            "ts": "",
                            "level": "ERROR",
                            "role": "worker",
                            "name": worker_name,
                            "message": "; ".join(result.get("errors", [])),
                        }
                    )
                else:
                    records.extend(result.get("result") or [])

        return records

    @staticmethod
    def _format_records(records: list[dict]) -> str:
        return "\n".join(
            ShowNorfabLoggingModel._format_record(record) for record in records
        )

    @staticmethod
    def _format_record(record: dict) -> str:
        location = ":".join(
            str(item)
            for item in (
                record.get("module") or record.get("filename"),
                record.get("function"),
                record.get("line"),
            )
            if item
        )
        source = f"{record.get('role', '')}:{record.get('name', '')}".strip(":")
        parts = [
            record.get("ts", ""),
            record.get("level", ""),
            source,
            record.get("logger", ""),
        ]
        if location:
            parts.append(location)
        parts.append(record.get("message", ""))
        return " ".join(str(part) for part in parts if part)


class ShowNorfabModel(BaseModel):
    broker: ShowBrokerModel = Field(None, description="show broker details")
    workers: ShowNorfabWorkersModel = Field(
        None, description="show workers information"
    )
    client: ShowNorfabClientModel = Field(None, description="Show client details")
    logging: ShowNorfabLoggingModel = Field(None, description="Show NorFab logs")
    inventory: Any = Field(
        None,
        description="Show NorFab inventory",
        json_schema_extra={
            "outputter": Outputters.outputter_yaml,
            "function": "show_inventory",
        },
    )

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_yaml
        outputter_kwargs = {"absolute_indent": 2}

    @staticmethod
    def show_inventory(**kwargs: object):
        nfclient = getattr(builtins, "NFCLIENT", NFCLIENT)
        return nfclient.inventory.dict()


class ShowCommandsModel(BaseModel):
    norfab: ShowNorfabModel = Field(None, description="Show NorFab platform")
    nornir: nornir_picle_shell.NornirShowCommandsModel = Field(
        None, description="Show Nornir service"
    )
    netbox: netbox_picle_shell.NetboxShowCommandsModel = Field(
        None, description="Show Netbox service"
    )
    fastapi: fastapi_picle_shell.FastAPIShowCommandsModel = Field(
        None, description="Show FastAPI service"
    )
    fastmcp: fastmcp_picle_shell.FastMCPShowCommandsModel = Field(
        None, description="Show FastMCP service"
    )
    fakenos: fakenos_picle_shell.FakeNOSShowCommands = Field(
        None, description="Show FakeNOS service"
    )
    agent: agent_picle_shell.AgentShowCommandsModel = Field(
        None, description="Show AI Agent service"
    )
    workflow: workflow_picle_shell.WorkflowShowCommandsModel = Field(
        None, description="Show Workflow service"
    )
    containerlab: containerlab_picle_shell.ContainerlabShowCommandsModel = Field(
        None, description="Show Containerlab service"
    )

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_yaml
        outputter_kwargs = {"absolute_indent": 2}


# ---------------------------------------------------------------------------------------------
# FILE SHELL SERVICE MODELS
# ---------------------------------------------------------------------------------------------


class ListFilesModel(ListFilesInput, use_enum_values=True, populate_by_name=True):
    url: StrictStr = Field("nf://", description="Directory to list content for")

    @staticmethod
    def source_url() -> list:
        broker_files = run_future_job(
            "filesharing",
            "walk",
            workers="any",
            kwargs={"url": "nf://"},
        )
        for w_name, wres in broker_files.items():
            return wres["result"]

    @staticmethod
    def run(*args: object, **kwargs: object):
        reply = run_future_job(
            "filesharing",
            "list_files",
            args=args,
            kwargs=kwargs,
            workers="any",
        )
        for w_name, wres in reply.items():
            return wres["result"]

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_nested


class CopyFileModel(BaseModel):
    url: StrictStr = Field("nf://", description="File location")
    destination: Optional[StrictStr] = Field(
        None, description="File location to save downloaded content"
    )
    read: Optional[StrictBool] = Field(False, description="Print file content")

    @staticmethod
    def source_url() -> list:
        broker_files = run_future_job(
            "filesharing",
            "walk",
            kwargs={"url": "nf://"},
            workers="any",
        )
        for w_name, wres in broker_files.items():
            return wres["result"]

    @staticmethod
    def run(*args: object, **kwargs: object):
        return NFCLIENT.fetch_file(**kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class ListFileDetails(FileDetailsInput, use_enum_values=True, populate_by_name=True):
    url: StrictStr = Field("nf://", description="File location")

    @staticmethod
    def source_url() -> list:
        broker_files = run_future_job(
            "filesharing",
            "walk",
            kwargs={"url": "nf://"},
            workers="any",
        )
        for w_name, wres in broker_files.items():
            return wres["result"]

    @staticmethod
    def run(*args: object, **kwargs: object):
        reply = run_future_job(
            "filesharing",
            "file_details",
            args=args,
            kwargs=kwargs,
            workers="any",
        )
        for w_name, wres in reply.items():
            return wres["result"]

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_nested


class DeleteFetchedFiles(ClientRunJobArgs):
    filepath: StrictStr = Field("*", description="Files location glob pattern")

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "all",
            "delete_fetched_files",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)

    @staticmethod
    def source_filepath() -> list:
        broker_files = run_future_job(
            "filesharing", "any", "walk", kwargs={"url": "nf://"}
        )
        for w_name, wres in broker_files.items():
            return wres["result"]

    @staticmethod
    def source_workers() -> list:
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.mmi("mmi.service.broker", "show_workers")
        workers = [i["name"] for i in reply["results"]]

        return ["all", "any"] + workers

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_nested


class FileServiceCommands(BaseModel):
    """
    # Sample Usage

    ## copy

    Copy to client's fetched files directory:

    ``file copy_ url nf://cli/commands.txt``

    Copy file to destination relative to current directory

    ``file copy_ url nf://cli/commands.txt destination commands.txt``

    ## list

    List files at broker root directory:

    ``
    file list
    file list url nf://
    ``

    List files details:

    ```
    file details
    file details url nf://
    ```
    """

    list_: ListFilesModel = Field(None, description="List files", alias="list")
    copy_: CopyFileModel = Field(None, description="Copy files", alias="copy")
    details: ListFileDetails = Field(None, description="Show file details")
    delete_fetched_files: DeleteFetchedFiles = Field(
        None, description="Delete local client files", alias="delete-fetched-files"
    )


# ---------------------------------------------------------------------------------------------
# MAIN SHELL MODEL
# ---------------------------------------------------------------------------------------------


class NorfabCommands(BaseModel):
    configure: NorFabInventory = Field(None, description="Configure NorFab inventory")
    workers: NorfabWorkersCommands = Field(None, description="NorFab workers commands")


class NorFabShell(BaseModel):
    norfab: NorfabCommands = Field(None, description="NorFab platform commands")
    show: ShowCommandsModel = Field(None, description="NorFab show commands")
    file: FileServiceCommands = Field(None, description="File sharing service")
    nornir: nornir_picle_shell.NornirServiceCommands = Field(
        None, description="Nornir service"
    )
    netbox: netbox_picle_shell.NetboxServiceCommands = Field(
        None, description="Netbox service"
    )
    agent: agent_picle_shell.AgentServiceCommands = Field(
        None, description="AI Agent service"
    )
    client_agent: client_agent_picle_shell.ClientAgentCommands = Field(
        None, description="Invoke client agent", alias="client-agent"
    )
    fastapi: fastapi_picle_shell.FastAPIServiceCommands = Field(
        None, description="FastAPI service"
    )
    fastmcp: fastmcp_picle_shell.FastMCPServiceCommands = Field(
        None, description="FastMCP service"
    )
    fakenos: fakenos_picle_shell.FakeNOSServiceCommands = Field(
        None, description="FakeNOS service"
    )
    workflow: workflow_picle_shell.WorkflowServiceCommands = Field(
        None, description="Workflow service"
    )
    containerlab: containerlab_picle_shell.ContainerlabServiceCommands = Field(
        None, description="Containerlab service"
    )

    class PicleConfig:
        subshell = True
        prompt = "nf#"
        intro = "Welcome to NorFab Interactive Shell."
        methods_override = {"preloop": "cmd_preloop_override"}
        history_file = "./__norfab__/nfcli_history.txt"

    @classmethod
    def cmd_preloop_override(self) -> None:
        """This method called before CMD loop starts"""
        pass


# ---------------------------------------------------------------------------------------------
# MAN SHELL COMMANDS
# ---------------------------------------------------------------------------------------------


class ManTasks(BaseModel):
    service: StrictStr = Field(None, description="Service name to show tasks for")
    name: StrictStr = Field(None, description="Name of the service task to show")
    brief: StrictBool = Field(
        None, description="Only show tasks names", json_schema_extra={"presence": True}
    )

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_nested

    @staticmethod
    def run(**kwargs: object):
        service = kwargs.pop("service", "all")

        result = run_future_job(
            service,
            "list_tasks",
            workers="any",
            timeout=60,
            kwargs=kwargs,
        )
        ret = {}
        for worker, wresult in result.items():
            if wresult["failed"]:
                continue
            key = f"{wresult['service']}-service:{kwargs.get('name', 'all-tasks')}"
            ret[key] = wresult["result"]
        return ret


# ---------------------------------------------------------------------------------------------
# SHELL ENTRY POINT
# ---------------------------------------------------------------------------------------------


def mount_shell_plugins(shell: App, inventory: object) -> None:
    """
    Mounts shell plugins to the given shell application.

    This function iterates over the plugins in the inventory and mounts
    those that have an "nfcli" configuration to the shell application.

    Args:
        shell (App): The shell application to which the plugins will be mounted.
        inventory (object): An object containing the plugins to be mounted.
                            It should have an attribute `plugins` which is a dictionary
                            where keys are service names and values are service data dictionaries.

    Returns:
        None
    """
    for service_name, service_data in inventory.plugins.items():
        if service_data.get("nfcli"):
            plugin = inventory.load_plugin(service_name)
            shell.model_mount(
                path=plugin[service_name]["nfcli"]["mount_path"],
                model=plugin[service_name]["nfcli"]["shell_model"],
            )

    # mount MAN commands
    shell.model_mount(
        path=["man", "tasks"],
        model=ManTasks,
        description="SHow NorFab services tasks documentation",
    )


def start_picle_shell(
    inventory="./inventory.yaml",
    run_workers=None,
    run_broker=None,
    log_level: str = "WARNING",
) -> None:
    global NFCLIENT
    # initiate NorFab
    with NorFab(
        inventory=inventory,
        log_level=log_level,
        configure_logging=True,
        logging_name="nfcli",
        run_broker=run_broker,
        run_workers=run_workers,
    ) as nf:
        NFCLIENT = nf.client
        if NFCLIENT is not None:
            # inject NFCLIENT to all imported models' global space
            builtins.NFCLIENT = NFCLIENT

            # start PICLE interactive shell
            shell = App(NorFabShell)
            mount_shell_plugins(shell, nf.inventory)
            shell.start()

            print("Exiting...")
