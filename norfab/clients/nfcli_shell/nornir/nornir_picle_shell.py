import builtins
import logging
from typing import Any, List, Union

from picle.models import Outputters, PipeFunctionsModel
from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictStr,
)

from norfab.workers.nornir_worker.nornir_models import (
    GetInventoryInput,
    RefreshNornirInput,
)

from ..common import ClientRunJobArgs, log_error_or_result, run_future_job
from .nornir_picle_shell_cfg import NornirCfgShell
from .nornir_picle_shell_cli import NornirCliShell
from .nornir_picle_shell_common import NorniHostsFilters
from .nornir_picle_shell_diagram import NornirDiagramShell
from .nornir_picle_shell_file_copy import NornirFileCopyShell
from .nornir_picle_shell_gnmi import NornirGnmiShell
from .nornir_picle_shell_inventory import NornirInventoryShell
from .nornir_picle_shell_netconf import NornirNetconfShell
from .nornir_picle_shell_network import NornirNetworkShell
from .nornir_picle_shell_parse import NornirParseShell
from .nornir_picle_shell_restconf import NornirRestconfShell
from .nornir_picle_shell_snmp import NornirSnmpShell
from .nornir_picle_shell_task import NornirTaskShell
from .nornir_picle_shell_test import NornirTestShell

SERVICE = "nornir"
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# NORNIR SERVICE SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class NornirShowHostsModel(
    NorniHostsFilters,
    ClientRunJobArgs,
    extra="forbid",
    use_enum_values=True,
    populate_by_name=True,
):
    brief: StrictBool = Field(
        False,
        description="Show host lists grouped by worker",
        json_schema_extra={"presence": True},
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args: object, **kwargs: object) -> Any:
        brief = kwargs.pop("brief", False)
        verbose_result = kwargs.setdefault("verbose_result", False)
        nowait = kwargs.pop("nowait", False)
        kwargs["details"] = not brief

        result = NorniHostsFilters.get_nornir_hosts(**kwargs)
        if nowait:
            return result, Outputters.outputter_nested

        if brief or verbose_result or not isinstance(result, dict):
            return result

        rows = []
        for worker, hosts in result.items():
            if not isinstance(hosts, dict) or any(
                not isinstance(data, dict) for data in hosts.values()
            ):
                return result
            rows.extend(
                {"host": host, **data, "worker": worker} for host, data in hosts.items()
            )
        rows.sort(key=lambda row: row["host"])
        rows = [{"index": index, **row} for index, row in enumerate(rows, start=1)]
        return (
            rows,
            Outputters.outputter_rich_table,
            {
                "headers": [
                    "index",
                    "worker",
                    "host",
                    "platform",
                    "hostname",
                    "port",
                    "groups",
                    "username",
                ],
            },
        )


class ShowWatchDogModel(NorniHostsFilters):
    statistics: Any = Field(
        None,
        description="show Nornir watchdog statistics",
        json_schema_extra={"function": "get_stats"},
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
    def get_stats(**kwargs: object):
        workers = kwargs.pop("workers", "all")
        nowait = kwargs.pop("nowait", False)
        result = run_future_job("nornir", "get_stats", workers=workers)
        if nowait:
            return result
        return log_error_or_result(result)

    @staticmethod
    def get_watchdog_configuration(**kwargs: object):
        workers = kwargs.pop("workers", "all")
        nowait = kwargs.pop("nowait", False)
        result = run_future_job("nornir", "get_watchdog_configuration", workers=workers)
        if nowait:
            return result
        return log_error_or_result(result)

    @staticmethod
    def get_watchdog_connections(**kwargs: object):
        workers = kwargs.pop("workers", "all")
        nowait = kwargs.pop("nowait", False)
        result = run_future_job("nornir", "get_watchdog_connections", workers=workers)
        if nowait:
            return result
        return log_error_or_result(result)


class NornirShowInventoryModel(
    GetInventoryInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    class PicleConfig:
        outputter = Outputters.outputter_yaml
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "nornir",
            "get_inventory",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            nowait=nowait,
        )
        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)


class NornirErrdisabledHostsListModel(ClientRunJobArgs):
    @staticmethod
    def run(*args: object, **kwargs: object) -> Any:
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600) or 600
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)
        result = run_future_job(
            "nornir",
            "errdisabled_hosts_list",
            workers=workers,
            timeout=timeout,
            nowait=nowait,
        )
        if nowait:
            return result, Outputters.outputter_nested
        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested


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
    errdisabled_hosts: NornirErrdisabledHostsListModel = Field(
        None,
        description="show Nornir errdisabled hosts",
        alias="errdisabled-hosts",
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def get_version(**kwargs: object):
        workers = kwargs.pop("workers", "all")
        nowait = kwargs.pop("nowait", False)
        result = run_future_job("nornir", "get_version", workers=workers, nowait=nowait)
        if nowait:
            return result
        return log_error_or_result(result)


# ---------------------------------------------------------------------------------------------
# NORNIR SERVICE UTILITIES SHELL MODELS
# ---------------------------------------------------------------------------------------------


class RefreshNornirModel(
    RefreshNornirInput,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    workers: Union[StrictStr, List[StrictStr]] = Field(
        ..., description="Workers to refresh"
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested

    @staticmethod
    def source_workers() -> list:
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.mmi(
            "mmi.service.broker", "show_workers", kwargs={"service": "nornir"}
        )
        workers = [i["name"] for i in reply["results"]]

        return ["all", "any"] + workers

    @staticmethod
    def run(**kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result")
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "nornir",
            "refresh_nornir",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            nowait=nowait,
        )
        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)


class NornirErrdisabledHostsClearModel(ClientRunJobArgs):
    @staticmethod
    def run(*args: object, **kwargs: object) -> Any:
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600) or 600
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)
        result = run_future_job(
            "nornir",
            "errdisabled_hosts_clear",
            workers=workers,
            timeout=timeout,
            nowait=nowait,
        )
        if nowait:
            return result, Outputters.outputter_nested
        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class NornirClearCommandsModel(BaseModel):
    errdisabled_hosts: NornirErrdisabledHostsClearModel = Field(
        None,
        description="recover all Nornir errdisabled hosts",
        alias="errdisabled-hosts",
    )


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
    restconf: NornirRestconfShell = Field(
        None, description="Manage devices using RESTCONF"
    )
    netconf: NornirNetconfShell = Field(
        None, description="Manage devices using NETCONF"
    )
    gnmi: NornirGnmiShell = Field(None, description="Retrieve device data using gNMI")
    snmp: NornirSnmpShell = Field(None, description="Interact with devices using SNMP")
    clear: NornirClearCommandsModel = Field(
        None, description="Clear Nornir service state"
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir]#"
