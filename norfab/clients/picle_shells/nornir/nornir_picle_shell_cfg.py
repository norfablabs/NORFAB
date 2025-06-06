import json

from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
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
from typing import Union, Optional, List, Any, Dict, Callable, Tuple
from nornir_salt.plugins.functions import TabulateFormatter
from picle.models import PipeFunctionsModel


class NrCfgPluginNetmiko(BaseModel):
    enable: Optional[StrictBool] = Field(
        None,
        description="Attempt to enter enable-mode",
        json_schema_extra={"presence": True},
    )
    exit_config_mode: Optional[StrictBool] = Field(
        None,
        description="Determines whether or not to exit config mode after complete",
        json_schema_extra={"presence": True},
        alias="exit-config-mode",
    )
    strip_prompt: Optional[StrictBool] = Field(
        None,
        description="Determines whether or not to strip the prompt",
        json_schema_extra={"presence": True},
        alias="strip-prompt",
    )
    strip_command: Optional[StrictBool] = Field(
        None,
        description="Determines whether or not to strip the command",
        json_schema_extra={"presence": True},
        alias="strip-command",
    )
    read_timeout: Optional[StrictInt] = Field(
        None,
        description="Absolute timer to send to read_channel_timing",
        alias="read-timeout",
    )
    config_mode_command: Optional[StrictStr] = Field(
        None,
        description="The command to enter into config mode",
        alias="config-mode-command",
    )
    cmd_verify: Optional[StrictBool] = Field(
        None,
        description="Whether or not to verify command echo for each command in config_set",
        json_schema_extra={"presence": True},
        alias="cmd-verify",
    )
    enter_config_mode: Optional[StrictBool] = Field(
        None,
        description="Do you enter config mode before sending config commands",
        json_schema_extra={"presence": True},
        alias="enter-config-mode",
    )
    error_pattern: Optional[StrictStr] = Field(
        None,
        description="Regular expression pattern to detect config errors in the output",
        alias="error-pattern",
    )
    terminator: Optional[StrictStr] = Field(
        None, description="Regular expression pattern to use as an alternate terminator"
    )
    bypass_commands: Optional[StrictStr] = Field(
        None,
        description="Regular expression pattern indicating configuration commands, cmd_verify is automatically disabled",
        alias="bypass-commands",
    )
    commit: Optional[Union[StrictBool, StrictStr]] = Field(
        True,
        description="Commit configuration",
        json_schema_extra={"presence": True},
    )
    commit_confirm: Optional[StrictBool] = Field(
        None,
        description="Perform commit confirm on supported platforms",
        alias="commit-confirm",
        json_schema_extra={"presence": True},
    )
    commit_confirm_delay: Optional[StrictInt] = Field(
        None,
        description="Confirmed commit rollback timeout in minutes, used with commit-confirm",
        alias="commit-confirm-delay",
    )
    commit_final_delay: Optional[StrictInt] = Field(
        None,
        description="Time to wait in seconds before doing final commit, used with commit-confirm",
        alias="commit-final-delay",
    )
    commit_comment: Optional[StrictStr] = Field(
        None, description="Commit operation comment", alias="commit-comment"
    )
    batch: Optional[StrictInt] = Field(
        None, description="Commands count to send in batches"
    )

    @staticmethod
    def run(*args, **kwargs):
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
        outputter = print_nornir_results


class NrCfgPluginScrapli(BaseModel):
    dry_run: Optional[StrictBool] = Field(
        None,
        description="Apply changes or not, also tests if possible to enter config mode",
        json_schema_extra={"presence": True},
        alias="dry-run",
    )
    strip_prompt: Optional[StrictBool] = Field(
        None,
        description="Strip prompt from returned output",
        json_schema_extra={"presence": True},
        alias="strip-prompt",
    )
    failed_when_contains: Optional[StrictStr] = Field(
        None,
        description="String or list of strings indicating failure if found in response",
        alias="failed-when-contains",
    )
    stop_on_failed: Optional[StrictBool] = Field(
        None,
        description="Stop executing commands if command fails",
        json_schema_extra={"presence": True},
        alias="stop-on-failed",
    )
    privilege_level: Optional[StrictStr] = Field(
        None,
        description="Name of configuration privilege level to acquire",
        alias="privilege-level",
    )
    eager: Optional[StrictBool] = Field(
        None,
        description="Do not read until prompt is seen at each command sent to the channel",
        json_schema_extra={"presence": True},
    )
    timeout_ops: Optional[StrictInt] = Field(
        None,
        description="Timeout ops value for this operation",
        alias="timeout-ops",
    )

    @staticmethod
    def run(*args, **kwargs):
        kwargs["plugin"] = "scrapli"
        return NornirCfgShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = print_nornir_results


class NrCfgPluginNapalm(BaseModel):
    replace: Optional[StrictBool] = Field(
        None,
        description="Whether to replace or merge the configuration",
        json_schema_extra={"presence": True},
    )
    dry_run: Optional[StrictBool] = Field(
        None,
        description="Apply changes or not, also tests if possible to enter config mode",
        json_schema_extra={"presence": True},
        alias="dry-run",
    )
    revert_in: Optional[StrictInt] = Field(
        None,
        description="Amount of time in seconds after which to revert the commit",
        alias="revert-in",
    )

    @staticmethod
    def run(*args, **kwargs):
        kwargs["plugin"] = "napalm"
        return NornirCfgShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = print_nornir_results


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
    NorniHostsFilters, TabulateTableModel, NornirCommonArgs, ClientRunJobArgs
):
    dry_run: Optional[StrictBool] = Field(
        None,
        description="Dry run cfg function",
        json_schema_extra={"presence": True},
        alias="dry-run",
    )
    config: Union[StrictStr, List[StrictStr]] = Field(
        ...,
        description="List of configuration commands to send to devices",
        json_schema_extra={"multiline": True},
        required=True,
    )
    plugin: NrCfgPlugins = Field(None, description="Configuration plugin parameters")
    job_data: Optional[StrictStr] = Field(
        None,
        description="Path to YAML file with job data",
        alias="job-data",
    )

    @staticmethod
    def source_config():
        broker_files = NFCLIENT.get(
            "fss.service.broker", "walk", kwargs={"url": "nf://"}
        )
        return broker_files["results"]

    @staticmethod
    def source_job_data():
        broker_files = NFCLIENT.get(
            "fss.service.broker", "walk", kwargs={"url": "nf://"}
        )
        return broker_files["results"]

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)

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

        result = NFCLIENT.run_job(
            "nornir",
            "cfg",
            workers=workers,
            args=args,
            kwargs=kwargs,
            uuid=uuid,
            timeout=timeout,
        )

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
        prompt = "nf[nornir-cfg]#"
        outputter = print_nornir_results
        pipe = PipeFunctionsModel
