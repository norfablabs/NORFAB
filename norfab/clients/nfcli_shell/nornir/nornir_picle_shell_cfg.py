import json
from typing import List, Optional, Union

from picle.models import Outputters, PipeFunctionsModel
from pydantic import (
    BaseModel,
    Field,
    StrictStr,
)

from norfab.workers.nornir_worker.nornir_models import (
    CfgInput,
)
from norfab.workers.nornir_worker.nornir_models import (
    NrCfgPluginNapalm as TaskNrCfgPluginNapalm,
)
from norfab.workers.nornir_worker.nornir_models import (
    NrCfgPluginNetmiko as TaskNrCfgPluginNetmiko,
)
from norfab.workers.nornir_worker.nornir_models import (
    NrCfgPluginScrapli as TaskNrCfgPluginScrapli,
)

from ..common import ClientRunJobArgs, log_error_or_result, run_future_job
from .nornir_picle_shell_common import (
    NorniHostsFilters,
    TabulateTableModel,
    tabulate_worker_results,
)


class NrCfgPluginNetmiko(TaskNrCfgPluginNetmiko):
    @staticmethod
    def run(*args: object, **kwargs: object):
        kwargs["plugin"] = "netmiko"

        # handle commit command for netmiko
        if kwargs.pop("commit_confirm", None) is True:
            kwargs["commit"] = {
                "confirm": True,
                "confirm_delay": kwargs.pop("commit_confirm_delay", None),
            }
        if kwargs.get("commit_comment"):
            if isinstance(kwargs["commit"], dict):
                kwargs["commit"]["comment"] = kwargs.pop("commit_comment")
            else:
                kwargs["commit"] = {"comment": kwargs.pop("commit_comment")}

        return NornirCfgShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class NrCfgPluginScrapli(TaskNrCfgPluginScrapli):
    @staticmethod
    def run(*args: object, **kwargs: object):
        kwargs["plugin"] = "scrapli"
        return NornirCfgShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class NrCfgPluginNapalm(TaskNrCfgPluginNapalm):
    @staticmethod
    def run(*args: object, **kwargs: object):
        kwargs["plugin"] = "napalm"
        return NornirCfgShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class NrCfgPlugins(BaseModel):
    netmiko: NrCfgPluginNetmiko = Field(
        None, description="Use Netmiko plugin to configure devices"
    )
    scrapli: NrCfgPluginScrapli = Field(
        None, description="Use Scrapli plugin to configure devices"
    )
    napalm: NrCfgPluginNapalm = Field(
        None, description="Use NAPALM plugin to configure devices"
    )


class NornirCfgShell(
    CfgInput,
    NorniHostsFilters,
    TabulateTableModel,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    config: Union[StrictStr, List[StrictStr]] = Field(
        ...,
        description="List of configuration commands to send to devices",
        json_schema_extra={"multiline": True},
    )
    plugin: NrCfgPlugins = Field(None, description="Configuration plugin parameters")
    job_data: Optional[StrictStr] = Field(
        None,
        description="Path to YAML file with job data",
        alias="job-data",
    )

    @staticmethod
    def source_config() -> list:
        completions = ClientRunJobArgs.walk_norfab_files()
        completions.append("load-terminal")
        return completions

    @staticmethod
    def source_job_data() -> list:
        return ClientRunJobArgs.walk_norfab_files()

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

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

        result = run_future_job(
            "nornir",
            "cfg",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        result = log_error_or_result(result, verbose_result=verbose_result)

        # form table results
        if table:
            ret = tabulate_worker_results(
                result=result,
                table=table,
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
        prompt = "nf[nornir-cfg]#"
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
