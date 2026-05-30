import builtins
import json
from enum import Enum
from typing import List, Optional, Union

from nornir_salt.plugins.functions import TabulateFormatter
from picle.models import Outputters, PipeFunctionsModel
from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictStr,
)

from norfab.workers.nornir_worker.cli_task import (
    CliInput,
    NrCliPluginNapalm as TaskNrCliPluginNapalm,
    NrCliPluginNetmiko as TaskNrCliPluginNetmiko,
    NrCliPluginScrapli as TaskNrCliPluginScrapli,
)

from ..common import ClientRunJobArgs, listen_events, log_error_or_result
from .nornir_picle_shell_common import (
    NorniHostsFilters,
    TabulateTableModel,
)


class NrCliPluginNetmiko(TaskNrCliPluginNetmiko):
    @staticmethod
    def run(*args: object, **kwargs: object):
        kwargs["plugin"] = "netmiko"
        return NornirCliShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class NrCliPluginScrapli(TaskNrCliPluginScrapli):
    @staticmethod
    def run(*args: object, **kwargs: object):
        kwargs["plugin"] = "scrapli"
        return NornirCliShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class NrCliPluginNapalm(TaskNrCliPluginNapalm):
    @staticmethod
    def run(*args: object, **kwargs: object):
        kwargs["plugin"] = "napalm"
        return NornirCliShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class NrCliPlugins(BaseModel):
    netmiko: NrCliPluginNetmiko = Field(
        None, description="Use Netmiko plugin to collect output from devices"
    )
    scrapli: NrCliPluginScrapli = Field(
        None, description="Use Scrapli plugin to collect output from devices"
    )
    napalm: NrCliPluginNapalm = Field(
        None, description="Use NAPALM plugin to collect output from devices"
    )


class NornirCliShell(
    CliInput,
    NorniHostsFilters,
    TabulateTableModel,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    commands: Union[StrictStr, List[StrictStr]] = Field(
        None,
        description="List of commands to collect form devices",
        json_schema_extra={"multiline": True},
    )
    plugin: NrCliPlugins = Field(None, description="Connection plugin parameters")
    enable: Optional[StrictBool] = Field(
        None, description="Enter exec mode", json_schema_extra={"presence": True}
    )
    job_data: Optional[StrictStr] = Field(
        None, description="Path to YAML file with job data", alias="job-data"
    )

    @staticmethod
    def source_commands() -> list:
        completions = ClientRunJobArgs.walk_norfab_files()
        completions.append("load-terminal")
        return completions

    @staticmethod
    def source_run_ttp() -> list:
        return ClientRunJobArgs.walk_norfab_files()

    @staticmethod
    def source_job_data() -> list:
        return ClientRunJobArgs.walk_norfab_files()

    @staticmethod
    @listen_events
    def run(uuid: str, *args: object, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result")
        nowait = kwargs.pop("nowait", False)

        # convert use_ps_timeout to timeout as use_ps expects "timeout" argument
        if kwargs.get("use_ps") and "use_ps_timeout" in kwargs:
            kwargs["timeout"] = kwargs.pop("use_ps_timeout")

        # extract job_data
        if kwargs.get("job_data") and not kwargs["job_data"].startswith("nf://"):
            kwargs["job_data"] = json.loads(kwargs["job_data"])

        # extract Tabulate arguments
        table = kwargs.pop("table", {})  # tabulate
        headers = kwargs.pop("headers", "keys")  # tabulate
        headers_exclude = kwargs.pop("headers_exclude", [])  # tabulate
        sortby = kwargs.pop("sortby", "host")  # tabulate
        reverse = kwargs.pop("reverse", False)  # tabulate

        if table:
            kwargs["add_details"] = True
            kwargs["to_dict"] = False

        # run the job
        result = NFCLIENT.run_job(
            "nornir",
            "cli",
            workers=workers,
            args=args,
            kwargs=kwargs,
            uuid=uuid,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        result = log_error_or_result(result, verbose_result=verbose_result)

        # form table results
        if table:
            table_data = []
            for w_name, w_res in result.items():
                for item in w_res:
                    item["worker"] = w_name
                    table_data.append(item)
            ret = TabulateFormatter(
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

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir-cli]#"
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel


class CliPlugins(str, Enum):
    netmiko = "netmiko"
    scrapli = "scrapli"
    napalm = "napalm"


class NorniCliInput(
    CliInput,
    NorniHostsFilters,
    TabulateTableModel,
    ClientRunJobArgs,
    use_enum_values=True,
):
    plugin: CliPlugins = Field(None, description="Connection plugin parameters")
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Filter workers to target"
    )
