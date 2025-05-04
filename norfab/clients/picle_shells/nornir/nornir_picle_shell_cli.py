import json

from enum import Enum
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


class NrCliPluginNetmiko(BaseModel):
    # nornir_netmiko.tasks.netmiko_send_command arguments
    enable: Optional[StrictBool] = Field(
        None,
        description="Attempt to enter enable-mode",
        json_schema_extra={"presence": True},
    )
    use_timing: Optional[StrictBool] = Field(
        None,
        description="switch to send command timing method",
        json_schema_extra={"presence": True},
        alias="use-timing",
    )
    # netmiko send_command methods arguments
    expect_string: Optional[StrictStr] = Field(
        None,
        description="Regular expression pattern to use for determining end of output",
        alias="expect-string",
    )
    read_timeout: Optional[StrictInt] = Field(
        None,
        description="Maximum time to wait looking for pattern",
        alias="read-timeout",
    )
    auto_find_prompt: Optional[StrictBool] = Field(
        None,
        description="Use find_prompt() to override base prompt",
        alias="auto-find-prompt",
    )
    strip_prompt: Optional[StrictBool] = Field(
        None,
        description="Remove the trailing router prompt from the output",
        json_schema_extra={"presence": True},
        alias="strip-prompt",
    )
    strip_command: Optional[StrictBool] = Field(
        None,
        description="Remove the echo of the command from the output",
        json_schema_extra={"presence": True},
        alias="strip-command",
    )
    normalize: Optional[StrictBool] = Field(
        None,
        description="Ensure the proper enter is sent at end of command",
        json_schema_extra={"presence": True},
    )
    use_textfsm: Optional[StrictBool] = Field(
        None,
        description="Process command output through TextFSM template",
        json_schema_extra={"presence": True},
        alias="use-textfsm",
    )
    textfsm_template: Optional[StrictStr] = Field(
        None,
        description="Name of template to parse output with",
        alias="textfsm-template",
    )
    use_ttp: Optional[StrictBool] = Field(
        None,
        description="Process command output through TTP template",
        json_schema_extra={"presence": True},
        alias="use-ttp",
    )
    ttp_template: Optional[StrictBool] = Field(
        None, description="Name of template to parse output with", alias="ttp-template"
    )
    use_genie: Optional[StrictBool] = Field(
        None,
        description="Process command output through PyATS/Genie parser",
        json_schema_extra={"presence": True},
        alias="use-genie",
    )
    cmd_verify: Optional[StrictBool] = Field(
        None,
        description="Verify command echo before proceeding",
        json_schema_extra={"presence": True},
        alias="cmd-verify",
    )
    # nornir_salt.plugins.tasks.netmiko_send_commands arguments
    interval: Optional[StrictInt] = Field(
        None,
        description="Interval between sending commands",
    )
    use_ps: Optional[StrictBool] = Field(
        None,
        description="Use send command promptless method",
        json_schema_extra={"presence": True},
        alias="use-ps",
    )
    use_ps_timeout: Optional[StrictInt] = Field(
        None,
        description="Promptless mode absolute timeout",
        json_schema_extra={"presence": True},
        alias="use-ps-timeout",
    )
    split_lines: Optional[StrictBool] = Field(
        None,
        description="Split multiline string to individual commands",
        json_schema_extra={"presence": True},
        alias="split-lines",
    )
    new_line_char: Optional[StrictStr] = Field(
        None,
        description="Character to replace with new line before sending to device, default is _br_",
        alias="new-line-char",
    )
    repeat: Optional[StrictInt] = Field(
        None,
        description="Number of times to repeat the commands",
    )
    stop_pattern: Optional[StrictStr] = Field(
        None,
        description="Stop commands repeat if output matches provided glob pattern",
        alias="stop-pattern",
    )
    repeat_interval: Optional[StrictInt] = Field(
        None,
        description="Time in seconds to wait between repeating commands",
        alias="repeat-interval",
    )
    return_last: Optional[StrictInt] = Field(
        None,
        description="Returns requested last number of commands outputs",
        alias="return-last",
    )

    @staticmethod
    def run(*args, **kwargs):
        kwargs["plugin"] = "netmiko"
        return NornirCliShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = print_nornir_results


class NrCliPluginScrapli(BaseModel):
    # nornir_scrapli.tasks.send_command arguments
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
    timeout_ops: Optional[StrictInt] = Field(
        None, description="Timeout ops value for this operation", alias="timeout-ops"
    )
    # nornir_salt.plugins.tasks.scrapli_send_commands arguments
    interval: Optional[StrictInt] = Field(
        None,
        description="Interval between sending commands",
    )
    split_lines: Optional[StrictBool] = Field(
        None,
        description="Split multiline string to individual commands",
        json_schema_extra={"presence": True},
        alias="split-lines",
    )
    new_line_char: Optional[StrictStr] = Field(
        None,
        description="Character to replace with new line before sending to device, default is _br_",
        alias="new-line-char",
    )
    repeat: Optional[StrictInt] = Field(
        None,
        description="Number of times to repeat the commands",
    )
    stop_pattern: Optional[StrictStr] = Field(
        None,
        description="Stop commands repeat if output matches provided glob pattern",
        alias="stop-pattern",
    )
    repeat_interval: Optional[StrictInt] = Field(
        None,
        description="Time in seconds to wait between repeating commands",
        alias="repeat-interval",
    )
    return_last: Optional[StrictInt] = Field(
        None,
        description="Returns requested last number of commands outputs",
        alias="return-last",
    )

    @staticmethod
    def run(*args, **kwargs):
        kwargs["plugin"] = "scrapli"
        return NornirCliShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = print_nornir_results


class NrCliPluginNapalm(BaseModel):
    # nornir_salt.plugins.tasks.napalm_send_commands arguments
    interval: Optional[StrictInt] = Field(
        None,
        description="Interval between sending commands",
    )
    split_lines: Optional[StrictBool] = Field(
        None,
        description="Split multiline string to individual commands",
        json_schema_extra={"presence": True},
        alias="split-lines",
    )
    new_line_char: Optional[StrictStr] = Field(
        None,
        description="Character to replace with new line before sending to device, default is _br_",
        alias="new-line-char",
    )

    @staticmethod
    def run(*args, **kwargs):
        kwargs["plugin"] = "napalm"
        return NornirCliShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = print_nornir_results


class NrCliPlugins(BaseModel):
    netmiko: NrCliPluginNetmiko = Field(
        None, description="Use Netmiko plugin to configure devices"
    )
    scrapli: NrCliPluginScrapli = Field(
        None, description="Use Scrapli plugin to configure devices"
    )
    napalm: NrCliPluginNapalm = Field(
        None, description="Use NAPALM plugin to configure devices"
    )


class NornirCliShell(
    NorniHostsFilters, TabulateTableModel, NornirCommonArgs, ClientRunJobArgs
):
    commands: Union[StrictStr, List[StrictStr]] = Field(
        None,
        description="List of commands to collect form devices",
        json_schema_extra={"multiline": True},
        required=True,
    )
    plugin: NrCliPlugins = Field(None, description="Connection plugin parameters")
    dry_run: Optional[StrictBool] = Field(
        None,
        description="Dry run the commands",
        json_schema_extra={"presence": True},
        alias="dry-run",
    )
    enable: Optional[StrictBool] = Field(
        None, description="Enter exec mode", json_schema_extra={"presence": True}
    )
    run_ttp: Optional[StrictStr] = Field(
        None, description="TTP Template to run", alias="run-ttp"
    )
    job_data: Optional[StrictStr] = Field(
        None, description="Path to YAML file with job data", alias="job-data"
    )

    @staticmethod
    def source_commands():
        broker_files = NFCLIENT.get(
            "fss.service.broker", "walk", kwargs={"url": "nf://"}
        )
        return broker_files["results"]

    @staticmethod
    def source_run_ttp():
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
        verbose_result = kwargs.pop("verbose_result")

        # covert use_ps_timeout to timeout as use_ps expects "timeout" argument
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
        prompt = "nf[nornir-cli]#"
        outputter = print_nornir_results
        pipe = PipeFunctionsModel
