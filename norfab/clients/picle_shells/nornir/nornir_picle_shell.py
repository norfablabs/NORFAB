import logging

from picle.models import PipeFunctionsModel, Outputters
from enum import Enum
from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    StrictFloat,
    StrictStr,
    Field,
)
from ..common import ClientRunJobArgs, log_error_or_result, listen_events
from .nornir_picle_shell_common import (
    NorniHostsFilters,
    TabulateTableModel,
    NornirCommonArgs,
    print_nornir_results,
)
from .nornir_picle_shell_cli import NornirCliShell
from .nornir_picle_shell_cfg import NornirCfgShell
from .nornir_picle_shell_task import NornirTaskShell
from .nornir_picle_shell_parse import NornirParseShell
from .nornir_picle_shell_test import NornirTestShell
from .nornir_picle_shell_network import NornirNetworkShell
from .nornir_picle_shell_diagram import NornirDiagramShell
from .nornir_picle_shell_file_copy import NornirFileCopyShell
from .nornir_picle_shell_jobs import NornirJobsShell
from .nornir_picle_shell_inventory import NornirInventoryShell
from typing import Union, Optional, List, Any, Dict, Tuple
from nornir_salt.plugins.functions import TabulateFormatter

SERVICE = "nornir"
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# NORNIR SERVICE SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class NornirShowHostsModel(NorniHostsFilters, TabulateTableModel, ClientRunJobArgs):
    details: Optional[StrictBool] = Field(
        None, description="show hosts details", presence=True
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args, **kwargs):
        # extract Tabulate arguments
        table = kwargs.pop("table", {})  # tabulate
        headers = kwargs.pop("headers", "keys")  # tabulate
        headers_exclude = kwargs.pop("headers_exclude", [])  # tabulate
        sortby = kwargs.pop("sortby", "host")  # tabulate
        reverse = kwargs.pop("reverse", False)  # tabulate

        # run task
        result = NorniHostsFilters.get_nornir_hosts(**kwargs)

        # form table results
        if table:
            if table is True or table == "brief":
                table = {"tablefmt": "grid"}
            table_data = []
            for w_name, w_res in result.items():
                if isinstance(w_res, list):
                    for item in w_res:
                        table_data.append({"worker": w_name, "host": item})
                elif isinstance(w_res, dict):
                    for host, host_data in w_res.items():
                        table_data.append({"worker": w_name, "host": host, **host_data})
                else:
                    return result
            ret = TabulateFormatter(  # tuple to return outputter reference
                table_data,
                tabulate=table,
                headers=headers,
                headers_exclude=headers_exclude,
                sortby=sortby,
                reverse=reverse,
            )
        else:
            ret = result

        return ret


class ShowWatchDogModel(NorniHostsFilters):
    statistics: Any = Field(
        None,
        description="show Nornir watchdog statistics",
        json_schema_extra={"function": "get_watchdog_stats"},
    )
    configuration: Any = Field(
        None,
        description="show Nornir watchdog configuration",
        json_schema_extra={"function": "get_watchdog_configuration"},
    )
    connections: Any = Field(
        None,
        description="show Nornir watchdog connections monitoring data",
        json_schema_extra={"function": "get_watchdog_connections"},
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested

    @staticmethod
    def get_watchdog_stats(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job("nornir", "get_watchdog_stats", workers=workers)
        return log_error_or_result(result)

    @staticmethod
    def get_watchdog_configuration(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job(
            "nornir", "get_watchdog_configuration", workers=workers
        )
        return log_error_or_result(result)

    @staticmethod
    def get_watchdog_connections(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job("nornir", "get_watchdog_connections", workers=workers)
        return log_error_or_result(result)


class NornirShowInventoryModel(NorniHostsFilters, ClientRunJobArgs):
    class PicleConfig:
        outputter = Outputters.outputter_yaml
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)

        result = NFCLIENT.run_job(
            "nornir",
            "get_inventory",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
        )
        return log_error_or_result(result, verbose_result=verbose_result)


class NornirShowCommandsModel(BaseModel):
    inventory: NornirShowInventoryModel = Field(
        None,
        description="show Nornir inventory data",
    )
    hosts: NornirShowHostsModel = Field(
        None,
        description="show Nornir hosts",
    )
    version: Any = Field(
        None,
        description="show Nornir service version report",
        json_schema_extra={
            "outputter": Outputters.outputter_yaml,
            "absolute_indent": 2,
            "function": "get_version",
        },
    )
    watchdog: ShowWatchDogModel = Field(
        None,
        description="show Nornir service version report",
    )
    jobs: NornirJobsShell = Field(None, description="Show Nornir Jobs")

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def get_version(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job("nornir", "get_version", workers=workers)
        return log_error_or_result(result)


# ---------------------------------------------------------------------------------------------
# NORNIR SERVICE UTILITIES SHELL MODELS
# ---------------------------------------------------------------------------------------------


class NornirExternalInentories(str, Enum):
    netbox = "netbox"
    containerlab = "containerlab"


class RefreshNornirModel(ClientRunJobArgs):
    workers: Union[StrictStr, List[StrictStr]] = Field(
        ..., description="Workers to refresh"
    )
    external_inventories: NornirExternalInentories = Field(
        None,
        description="External sources to fetch inventories from",
        alias="external-inventories",
    )
    progress: Optional[StrictBool] = Field(
        True,
        description="Display progress events",
        json_schema_extra={"presence": True},
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested

    @staticmethod
    def source_workers():
        reply = NFCLIENT.get(
            "mmi.service.broker", "show_workers", kwargs={"service": "nornir"}
        )
        workers = [i["name"] for i in reply["results"]]

        return ["all", "any"] + workers

    @staticmethod
    @listen_events
    def run(uuid, **kwargs):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result")

        if isinstance(kwargs.get("external_inventories"), str):
            kwargs["external_inventories"] = [kwargs["external_inventories"]]

        result = NFCLIENT.run_job(
            "nornir",
            "refresh_nornir",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            uuid=uuid,
        )

        return log_error_or_result(result, verbose_result=verbose_result)


# ---------------------------------------------------------------------------------------------
# NORNIR SERVICE MAIN SHELL MODEL
# ---------------------------------------------------------------------------------------------


class NornirServiceCommands(BaseModel):
    cli: NornirCliShell = Field(None, description="Send CLI commands to devices")
    cfg: NornirCfgShell = Field(
        None, description="Configure devices over CLI interface"
    )
    task: NornirTaskShell = Field(None, description="Run Nornir task")
    test: NornirTestShell = Field(None, description="Run network tests")
    network: NornirNetworkShell = Field(
        None, description="Network utility functions - ping, dns etc."
    )
    parse: NornirParseShell = Field(None, description="Parse network devices output")
    diagram: NornirDiagramShell = Field(None, description="Produce network diagrams")
    file_copy: NornirFileCopyShell = Field(
        None, description="Copy files to/from devices", alias="file-copy"
    )
    inventory: NornirInventoryShell = Field(
        None, description="Work with Nornir inventory"
    )
    refresh: RefreshNornirModel = Field(None, description="Refresh inventory")

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir]#"
