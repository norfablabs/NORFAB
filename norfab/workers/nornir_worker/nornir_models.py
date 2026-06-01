from enum import Enum
from typing import Any, Dict, Union

from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)

from norfab.models import Result

# --------------------------------------------------------------------------
# COMMON NORNIR TASK MODELS
# --------------------------------------------------------------------------


class NornirHostsFilters(BaseModel, extra="forbid", use_enum_values=True):
    """Common host filter arguments supported by Nornir-Salt FFun."""

    FO: Union[None, dict[StrictStr, Any], list[dict[StrictStr, Any]]] = Field(
        None,
        title="Filter Object",
        description="Filter hosts using a Nornir-Salt Filter Object",
    )
    FB: Union[None, list[StrictStr], StrictStr] = Field(
        None,
        title="Filter gloB",
        description="Filter hosts by name using glob patterns",
    )
    FH: Union[None, list[StrictStr], StrictStr] = Field(
        None,
        title="Filter Hostname",
        description="Filter hosts by hostname",
    )
    FC: Union[None, list[StrictStr], StrictStr] = Field(
        None,
        title="Filter Contains",
        description="Filter hosts by name containment pattern",
    )
    FR: Union[None, list[StrictStr], StrictStr] = Field(
        None,
        title="Filter Regex",
        description="Filter hosts by name using regular expressions",
    )
    FG: Union[None, StrictStr] = Field(
        None,
        title="Filter Group",
        description="Filter hosts by group",
    )
    FP: Union[None, list[StrictStr], StrictStr] = Field(
        None,
        title="Filter Prefix",
        description="Filter hosts by hostname using IP prefix",
    )
    FL: Union[None, list[StrictStr], StrictStr] = Field(
        None,
        title="Filter List",
        description="Filter hosts by names list",
    )
    FM: Union[None, list[StrictStr], StrictStr] = Field(
        None,
        title="Filter platforM",
        description="Filter hosts by platform",
    )
    FX: Union[None, list[StrictStr], StrictStr] = Field(
        None,
        title="Filter eXclude",
        description="Exclude hosts by name",
    )
    FN: Union[None, StrictBool] = Field(
        None,
        title="Filter Negate",
        description="Negate the host filter match",
        json_schema_extra={"presence": True},
    )

    @model_validator(mode="before")
    @classmethod
    def validate_mapping(cls, data: Any) -> Any:
        if data is None or isinstance(data, dict):
            if not isinstance(data, dict):
                return data
            normalized = data.copy()
            for key, value in data.items():
                if key == "FO" or key == "FN" or not key.startswith("F"):
                    continue
                if isinstance(value, list):
                    normalized[key] = [str(item) for item in value]
                elif value is not None:
                    normalized[key] = str(value)
            return normalized
        raise TypeError("Nornir host filters must be provided as a mapping")


class NornirCommonArgs(
    NornirHostsFilters, extra="allow", use_enum_values=True, populate_by_name=True
):
    """Common Nornir task arguments accepted by task serializers and processors."""

    to_dict: StrictBool = Field(
        True,
        description="Return task results as a dictionary keyed by host",
        alias="to-dict",
    )
    add_details: StrictBool = Field(
        False,
        description="Add Nornir task execution details to results",
        alias="add-details",
        json_schema_extra={"presence": True},
    )
    progress: StrictBool = Field(
        True,
        description="Emit progress events during task execution",
        json_schema_extra={"presence": True},
    )
    run_num_workers: Union[None, StrictInt] = Field(
        None,
        description="RetryRunner number of threads for task execution",
        alias="num-workers",
    )
    run_num_connectors: Union[None, StrictInt] = Field(
        None,
        description="RetryRunner number of threads for device connections",
        alias="num-connectors",
    )
    run_connect_retry: Union[None, StrictInt] = Field(
        None,
        description="RetryRunner number of connection attempts",
        alias="connect-retry",
    )
    run_task_retry: Union[None, StrictInt] = Field(
        None,
        description="RetryRunner number of attempts to run each task",
        alias="task-retry",
    )
    run_reconnect_on_fail: Union[None, StrictBool] = Field(
        None,
        description="RetryRunner reconnects to a host after task failure",
        alias="reconnect-on-fail",
        json_schema_extra={"presence": True},
    )
    run_connect_check: Union[None, StrictBool] = Field(
        None,
        description="RetryRunner tests TCP connectivity before opening connection",
        alias="connect-check",
        json_schema_extra={"presence": True},
    )
    run_connect_timeout: Union[None, StrictInt] = Field(
        None,
        description="RetryRunner TCP connection check timeout in seconds",
        alias="connect-timeout",
    )
    run_creds_retry: Any = Field(
        None,
        description="RetryRunner connection credentials and parameters to retry",
        alias="creds-retry",
    )
    tf: Union[None, StrictStr] = Field(
        None,
        description="File group name to save task results on the worker",
    )
    tf_skip_failed: Union[None, StrictBool] = Field(
        None,
        description="Skip failed task results when saving to file",
        alias="tf-skip-failed",
        json_schema_extra={"presence": True},
    )
    diff: Union[None, StrictStr] = Field(
        None,
        description="File group name to diff task results against",
    )
    diff_last: Union[None, StrictInt, StrictStr] = Field(
        None,
        description="Previous saved file version to diff against",
        alias="diff-last",
    )
    dp: Any = Field(
        None,
        description="Nornir-Salt DataProcessor pipeline definition",
    )
    xml_flake: Union[None, StrictStr] = Field(
        None,
        description="XML flake pattern for DataProcessor",
        alias="xml-flake",
    )
    match: Union[None, StrictStr] = Field(
        None,
        description="Pattern to match in task output",
    )
    before: StrictInt = Field(
        0,
        description="Number of lines before a match to include",
    )
    run_ttp: Union[None, StrictStr] = Field(
        None,
        description="TTP template to run with DataProcessor",
        alias="run-ttp",
    )
    ttp_structure: StrictStr = Field(
        "flat_list",
        description="TTP result structure for DataProcessor",
        alias="ttp-structure",
    )
    remove_tasks: StrictBool = Field(
        True,
        description="Remove task output when processors produce final results",
        alias="remove-tasks",
        json_schema_extra={"presence": True},
    )
    tests: Any = Field(
        None,
        description="Nornir-Salt TestsProcessor tests definition",
    )
    subset: Union[None, StrictStr, list[StrictStr]] = Field(
        None,
        description="Test subset name or glob pattern to execute",
    )
    failed_only: StrictBool = Field(
        False,
        description="Return failed test results only",
        alias="failed-only",
        json_schema_extra={"presence": True},
    )
    groups: Union[None, StrictStr, list[StrictStr]] = Field(
        None,
        description="Test group names to execute",
    )
    xpath: Union[None, StrictStr] = Field(
        None,
        description="XPath expression to run with DataProcessor",
    )
    jmespath: Union[None, StrictStr] = Field(
        None,
        description="JMESPath expression to run with DataProcessor",
    )
    iplkp: Union[None, StrictStr] = Field(
        None,
        description="IP lookup mode for DataProcessor",
    )
    ntfsm: Union[None, StrictBool] = Field(
        None,
        description="Parse output with NTC TextFSM templates",
        json_schema_extra={"presence": True},
    )


class NornirSerializedResult(Result):
    result: Union[dict[StrictStr, Any], list[Any], None] = Field(
        {},
        description="Serialized Nornir task result keyed by host or returned as a list",
    )


class NornirCliPlugin(str, Enum):
    netmiko = "netmiko"
    scrapli = "scrapli"
    napalm = "napalm"


# --------------------------------------------------------------------------
# CFG TASK MODELS
# --------------------------------------------------------------------------


class NrCfgPluginNetmiko(
    BaseModel, extra="allow", use_enum_values=True, populate_by_name=True
):
    enable: Union[None, StrictBool] = Field(
        None,
        description="Attempt to enter enable-mode",
        json_schema_extra={"presence": True},
    )
    exit_config_mode: Union[None, StrictBool] = Field(
        None,
        description="Exit configuration mode after sending commands",
        alias="exit-config-mode",
        json_schema_extra={"presence": True},
    )
    strip_prompt: Union[None, StrictBool] = Field(
        None,
        description="Strip prompt from returned output",
        alias="strip-prompt",
        json_schema_extra={"presence": True},
    )
    strip_command: Union[None, StrictBool] = Field(
        None,
        description="Strip command echo from returned output",
        alias="strip-command",
        json_schema_extra={"presence": True},
    )
    read_timeout: Union[None, StrictInt] = Field(
        None,
        description="Absolute read timeout in seconds",
        alias="read-timeout",
    )
    config_mode_command: Union[None, StrictStr] = Field(
        None,
        description="Command to enter configuration mode",
        alias="config-mode-command",
    )
    cmd_verify: Union[None, StrictBool] = Field(
        None,
        description="Verify command echo for each configuration command",
        alias="cmd-verify",
        json_schema_extra={"presence": True},
    )
    enter_config_mode: Union[None, StrictBool] = Field(
        None,
        description="Enter configuration mode before sending commands",
        alias="enter-config-mode",
        json_schema_extra={"presence": True},
    )
    error_pattern: Union[None, StrictStr] = Field(
        None,
        description="Regular expression pattern to detect configuration errors",
        alias="error-pattern",
    )
    terminator: Union[None, StrictStr] = Field(
        None,
        description="Regular expression pattern to use as an alternate terminator",
    )
    bypass_commands: Union[None, StrictStr] = Field(
        None,
        description="Regular expression pattern for commands that bypass command verification",
        alias="bypass-commands",
    )
    commit: Union[StrictBool, StrictStr, dict[StrictStr, Any]] = Field(
        True,
        description="Commit configuration or commit options",
        json_schema_extra={"presence": True},
    )
    commit_confirm: Union[None, StrictBool] = Field(
        None,
        description="Perform commit confirm on supported platforms",
        alias="commit-confirm",
        json_schema_extra={"presence": True},
    )
    commit_confirm_delay: Union[None, StrictInt] = Field(
        None,
        description="Confirmed commit rollback timeout in minutes",
        alias="commit-confirm-delay",
    )
    commit_final_delay: Union[None, StrictInt] = Field(
        None,
        description="Time in seconds before final commit",
        alias="commit-final-delay",
    )
    commit_comment: Union[None, StrictStr] = Field(
        None,
        description="Commit operation comment",
        alias="commit-comment",
    )
    batch: Union[None, StrictInt] = Field(
        None,
        description="Number of commands to send in each batch",
    )


class NrCfgPluginScrapli(
    BaseModel, extra="allow", use_enum_values=True, populate_by_name=True
):
    dry_run: Union[None, StrictBool] = Field(
        None,
        description="Validate configuration mode entry without applying changes",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    strip_prompt: Union[None, StrictBool] = Field(
        None,
        description="Strip prompt from returned output",
        alias="strip-prompt",
        json_schema_extra={"presence": True},
    )
    failed_when_contains: Union[None, StrictStr, list[StrictStr]] = Field(
        None,
        description="String or strings indicating failure if found in response",
        alias="failed-when-contains",
    )
    stop_on_failed: Union[None, StrictBool] = Field(
        None,
        description="Stop executing commands after a command fails",
        alias="stop-on-failed",
        json_schema_extra={"presence": True},
    )
    privilege_level: Union[None, StrictStr] = Field(
        None,
        description="Configuration privilege level to acquire",
        alias="privilege-level",
    )
    eager: Union[None, StrictBool] = Field(
        None,
        description="Do not wait for prompt after each command",
        json_schema_extra={"presence": True},
    )
    timeout_ops: Union[None, StrictInt] = Field(
        None,
        description="Operation timeout in seconds",
        alias="timeout-ops",
    )


class NrCfgPluginNapalm(
    BaseModel, extra="allow", use_enum_values=True, populate_by_name=True
):
    replace: Union[None, StrictBool] = Field(
        None,
        description="Replace configuration instead of merging it",
        json_schema_extra={"presence": True},
    )
    dry_run: Union[None, StrictBool] = Field(
        None,
        description="Validate configuration without applying changes",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    revert_in: Union[None, StrictInt] = Field(
        None,
        description="Time in seconds after which to revert the commit",
        alias="revert-in",
    )


class CfgInput(
    NornirCommonArgs,
    NrCfgPluginNetmiko,
    NrCfgPluginScrapli,
    NrCfgPluginNapalm,
    extra="allow",
    use_enum_values=True,
    populate_by_name=True,
):
    config: Union[StrictStr, list[StrictStr]] = Field(
        ...,
        description="Configuration commands, template path, or template text to send to devices",
    )
    plugin: NornirCliPlugin = Field(
        NornirCliPlugin.netmiko,
        description="Nornir configuration connection plugin to use",
    )
    dry_run: StrictBool = Field(
        False,
        description="Render configuration without sending it to devices",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    job_data: Union[None, StrictStr, dict[StrictStr, Any], list[Any]] = Field(
        None,
        description="Job data as a NorFab URL, dictionary, or list for Jinja2 rendering",
        alias="job-data",
    )


class CfgResult(NornirSerializedResult):
    result: Union[dict[StrictStr, Any], list[Any]] = Field(
        {},
        description="Configuration results keyed by host or returned as serialized task records",
    )


# --------------------------------------------------------------------------
# CLI TASK MODELS
# --------------------------------------------------------------------------


class NrCliPluginNetmiko(
    BaseModel, extra="allow", use_enum_values=True, populate_by_name=True
):
    enable: Union[None, StrictBool] = Field(
        None,
        description="Attempt to enter enable-mode",
        json_schema_extra={"presence": True},
    )
    use_timing: Union[None, StrictBool] = Field(
        None,
        description="Switch to send command timing method",
        alias="use-timing",
        json_schema_extra={"presence": True},
    )
    expect_string: Union[None, StrictStr] = Field(
        None,
        description="Regular expression pattern to determine end of output",
        alias="expect-string",
    )
    read_timeout: Union[None, StrictInt] = Field(
        None,
        description="Maximum time in seconds to wait for output pattern",
        alias="read-timeout",
    )
    auto_find_prompt: Union[None, StrictBool] = Field(
        None,
        description="Use find_prompt() to override base prompt",
        alias="auto-find-prompt",
    )
    strip_prompt: Union[None, StrictBool] = Field(
        None,
        description="Remove the trailing router prompt from output",
        alias="strip-prompt",
        json_schema_extra={"presence": True},
    )
    strip_command: Union[None, StrictBool] = Field(
        None,
        description="Remove command echo from output",
        alias="strip-command",
        json_schema_extra={"presence": True},
    )
    normalize: Union[None, StrictBool] = Field(
        None,
        description="Ensure proper line ending is sent after command",
        json_schema_extra={"presence": True},
    )
    use_textfsm: Union[None, StrictBool] = Field(
        None,
        description="Process command output through TextFSM template",
        alias="use-textfsm",
        json_schema_extra={"presence": True},
    )
    textfsm_template: Union[None, StrictStr] = Field(
        None,
        description="TextFSM template name or path to parse output with",
        alias="textfsm-template",
    )
    use_ttp: Union[None, StrictBool] = Field(
        None,
        description="Process command output through TTP template",
        alias="use-ttp",
        json_schema_extra={"presence": True},
    )
    ttp_template: Union[None, StrictStr] = Field(
        None,
        description="TTP template name or path to parse output with",
        alias="ttp-template",
    )
    use_genie: Union[None, StrictBool] = Field(
        None,
        description="Process command output through PyATS/Genie parser",
        alias="use-genie",
        json_schema_extra={"presence": True},
    )
    cmd_verify: Union[None, StrictBool] = Field(
        None,
        description="Verify command echo before proceeding",
        alias="cmd-verify",
        json_schema_extra={"presence": True},
    )
    interval: Union[None, StrictInt] = Field(
        None,
        description="Interval in seconds between sending commands",
    )
    use_ps: Union[None, StrictBool] = Field(
        None,
        description="Use send command promptless method",
        alias="use-ps",
        json_schema_extra={"presence": True},
    )
    use_ps_timeout: Union[None, StrictInt] = Field(
        None,
        description="Promptless mode absolute timeout in seconds",
        alias="use-ps-timeout",
    )
    split_lines: Union[None, StrictBool] = Field(
        None,
        description="Split multiline string to individual commands",
        alias="split-lines",
        json_schema_extra={"presence": True},
    )
    new_line_char: Union[None, StrictStr] = Field(
        None,
        description="Character to replace with newline before sending to device",
        alias="new-line-char",
    )
    repeat: Union[None, StrictInt] = Field(
        None,
        description="Number of times to repeat commands",
    )
    stop_pattern: Union[None, StrictStr] = Field(
        None,
        description="Stop command repeat if output matches glob pattern",
        alias="stop-pattern",
    )
    repeat_interval: Union[None, StrictInt] = Field(
        None,
        description="Time in seconds to wait between command repeats",
        alias="repeat-interval",
    )
    return_last: Union[None, StrictInt] = Field(
        None,
        description="Number of last command outputs to return",
        alias="return-last",
    )


class NrCliPluginScrapli(
    BaseModel, extra="allow", use_enum_values=True, populate_by_name=True
):
    strip_prompt: Union[None, StrictBool] = Field(
        None,
        description="Strip prompt from returned output",
        alias="strip-prompt",
        json_schema_extra={"presence": True},
    )
    failed_when_contains: Union[None, StrictStr, list[StrictStr]] = Field(
        None,
        description="String or strings indicating failure if found in response",
        alias="failed-when-contains",
    )
    timeout_ops: Union[None, StrictInt] = Field(
        None,
        description="Operation timeout in seconds",
        alias="timeout-ops",
    )
    interval: Union[None, StrictInt] = Field(
        None,
        description="Interval in seconds between sending commands",
    )
    split_lines: Union[None, StrictBool] = Field(
        None,
        description="Split multiline string to individual commands",
        alias="split-lines",
        json_schema_extra={"presence": True},
    )
    new_line_char: Union[None, StrictStr] = Field(
        None,
        description="Character to replace with newline before sending to device",
        alias="new-line-char",
    )
    repeat: Union[None, StrictInt] = Field(
        None,
        description="Number of times to repeat commands",
    )
    stop_pattern: Union[None, StrictStr] = Field(
        None,
        description="Stop command repeat if output matches glob pattern",
        alias="stop-pattern",
    )
    repeat_interval: Union[None, StrictInt] = Field(
        None,
        description="Time in seconds to wait between command repeats",
        alias="repeat-interval",
    )
    return_last: Union[None, StrictInt] = Field(
        None,
        description="Number of last command outputs to return",
        alias="return-last",
    )


class NrCliPluginNapalm(
    BaseModel, extra="allow", use_enum_values=True, populate_by_name=True
):
    interval: Union[None, StrictInt] = Field(
        None,
        description="Interval in seconds between sending commands",
    )
    split_lines: Union[None, StrictBool] = Field(
        None,
        description="Split multiline string to individual commands",
        alias="split-lines",
        json_schema_extra={"presence": True},
    )
    new_line_char: Union[None, StrictStr] = Field(
        None,
        description="Character to replace with newline before sending to device",
        alias="new-line-char",
    )


class CliInput(
    NornirCommonArgs,
    NrCliPluginNetmiko,
    NrCliPluginScrapli,
    NrCliPluginNapalm,
    extra="allow",
    use_enum_values=True,
    populate_by_name=True,
):
    commands: Union[None, StrictStr, list[StrictStr]] = Field(
        None,
        description="Commands, template path, or template text to send to devices",
    )
    plugin: NornirCliPlugin = Field(
        NornirCliPlugin.netmiko,
        description="Nornir CLI connection plugin to use",
    )
    dry_run: StrictBool = Field(
        False,
        description="Render commands without sending them to devices",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    run_ttp: Union[None, StrictStr] = Field(
        None,
        description="TTP template string or path to parse collected output",
        alias="run-ttp",
    )
    job_data: Union[None, StrictStr, dict[StrictStr, Any], list[Any]] = Field(
        None,
        description="Job data as a NorFab URL, dictionary, or list for Jinja2 rendering",
        alias="job-data",
    )

    @model_validator(mode="before")
    @classmethod
    def validate_commands_or_ttp_or_tests(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        run_ttp = values.get("run_ttp", values.get("run-ttp"))
        if not values.get("commands") and not run_ttp and not values.get("tests"):
            raise ValueError(
                "Either 'commands' or 'run_ttp' or 'tests' must be provided"
            )
        return values


class CliResult(NornirSerializedResult):
    result: Union[dict[StrictStr, Any], list[Any]] = Field(
        {},
        description="CLI command results keyed by host or returned as serialized task records",
    )


# --------------------------------------------------------------------------
# FILE COPY TASK MODELS
# --------------------------------------------------------------------------


class FileCopyPlugin(str, Enum):
    netmiko = "netmiko"


class SCPDirection(str, Enum):
    put = "put"
    get = "get"


class NrFileCopyPluginNetmiko(
    BaseModel, extra="allow", use_enum_values=True, populate_by_name=True
):
    dest_file: Union[None, StrictStr] = Field(
        None,
        description="Destination file to copy",
        alias="destination-file",
    )
    file_system: Union[None, StrictStr] = Field(
        None,
        description="Destination file system",
        alias="file-system",
    )
    direction: SCPDirection = Field(
        SCPDirection.put,
        description="Direction of file copy",
    )
    inline_transfer: StrictBool = Field(
        False,
        description="Use inline transfer, supported by Cisco IOS",
        alias="inline-transfer",
        json_schema_extra={"presence": True},
    )
    overwrite_file: StrictBool = Field(
        False,
        description="Overwrite destination file if it exists",
        alias="overwrite-file",
        json_schema_extra={"presence": True},
    )
    socket_timeout: Union[StrictFloat, StrictInt] = Field(
        10.0,
        description="Socket timeout in seconds",
        alias="socket-timeout",
    )
    verify_file: StrictBool = Field(
        True,
        description="Verify destination file hash after copy",
        alias="verify-file",
        json_schema_extra={"presence": True},
    )


class FileCopyInput(
    NrFileCopyPluginNetmiko,
    NornirCommonArgs,
    extra="allow",
    use_enum_values=True,
    populate_by_name=True,
):
    source_file: StrictStr = Field(
        ...,
        description="Source file path or NorFab URL to copy",
        alias="source-file",
    )
    plugin: FileCopyPlugin = Field(
        FileCopyPlugin.netmiko,
        description="Nornir file transfer plugin to use",
    )
    dry_run: StrictBool = Field(
        False,
        description="Show file transfer task data without copying files",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )


class FileCopyResult(NornirSerializedResult):
    result: Union[dict[StrictStr, Any], list[Any]] = Field(
        {},
        description="File copy results keyed by host or returned as serialized task records",
    )


# --------------------------------------------------------------------------
# INVENTORY TASKS MODELS
# --------------------------------------------------------------------------


class NornirInventoryLoadNetboxInput(
    BaseModel, use_enum_values=True, populate_by_name=True
):
    progress: StrictBool = Field(
        False,
        description="Emit progress events during NetBox inventory load",
        json_schema_extra={"presence": True},
    )


class NornirInventoryLoadNetboxResult(Result):
    result: StrictBool = Field(
        True,
        description="True if NetBox inventory data was merged successfully",
    )


class NornirInventoryLoadContainerlabInput(
    BaseModel, use_enum_values=True, populate_by_name=True
):
    lab_name: Union[None, StrictStr] = Field(
        None,
        description="Containerlab lab name to load inventory from",
        alias="lab-name",
    )
    groups: Union[None, list[StrictStr]] = Field(
        None,
        description="Nornir group names to attach to imported hosts",
    )
    clab_workers: Union[StrictStr, list[StrictStr]] = Field(
        "all",
        description="Containerlab workers to query for inventory",
        alias="clab-workers",
    )
    use_default_credentials: StrictBool = Field(
        True,
        description="Use Containerlab default credentials for hosts",
        alias="use-default-credentials",
        json_schema_extra={"presence": True},
    )
    progress: StrictBool = Field(
        False,
        description="Emit progress events during Containerlab inventory load",
        json_schema_extra={"presence": True},
    )
    dry_run: StrictBool = Field(
        False,
        description="Return pulled inventory without merging it",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    re_init_nornir: StrictBool = Field(
        True,
        description="Re-initialize Nornir after merging inventory",
        alias="re-init-nornir",
        json_schema_extra={"presence": True},
    )


class NornirInventoryLoadContainerlabResult(Result):
    result: Union[StrictBool, dict[StrictStr, Any]] = Field(
        True,
        description="True when merged, or pulled inventory data keyed by worker for dry runs",
    )


class GetInventoryInput(
    NornirHostsFilters, use_enum_values=True, populate_by_name=True
):
    pass


class GetInventoryResult(Result):
    result: Union[dict[StrictStr, Any], None] = Field(
        {},
        description="Running Nornir inventory dictionary for matched hosts",
    )


class GetNornirHostsInput(
    NornirHostsFilters, extra="forbid", use_enum_values=True, populate_by_name=True
):
    details: StrictBool = Field(
        False,
        description="Return host details instead of host names",
        json_schema_extra={"presence": True},
    )


class HostDetails(BaseModel, extra="forbid", use_enum_values=True):
    platform: StrictStr = Field(None, description="Host platform name")
    hostname: StrictStr = Field(None, description="Host connection hostname")
    port: StrictStr = Field(None, description="Host connection TCP port")
    groups: list[StrictStr] = Field([], description="Host group names")
    username: StrictStr = Field(None, description="Host connection username")


class GetNornirHostsResult(Result):
    result: Union[list[StrictStr], dict[StrictStr, HostDetails], None] = Field(
        None,
        description="Host names list, host details keyed by name, or None when no hosts match",
    )


class RuntimeInventoryAction(str, Enum):
    create_host = "create_host"
    create = "create"
    read_host = "read_host"
    read = "read"
    update_host = "update_host"
    update = "update"
    delete_host = "delete_host"
    delete = "delete"
    load = "load"
    read_inventory = "read_inventory"
    read_host_data = "read_host_data"
    list_hosts = "list_hosts"
    list_hosts_platforms = "list_hosts_platforms"
    update_defaults = "update_defaults"


class RuntimeInventoryInput(
    BaseModel, extra="allow", use_enum_values=True, populate_by_name=True
):
    action: Union[RuntimeInventoryAction, StrictStr] = Field(
        ...,
        description="Runtime inventory action to perform",
    )
    progress: StrictBool = Field(
        True,
        description="Emit progress events during inventory action",
        json_schema_extra={"presence": True},
    )


class GroupsUpdateAction(str, Enum):
    append = "append"
    insert = "insert"
    remove = "remove"


class RuntimeCreateHostInput(
    RuntimeInventoryInput, extra="allow", use_enum_values=True, populate_by_name=True
):
    action: RuntimeInventoryAction = Field(
        RuntimeInventoryAction.create_host,
        description="Runtime inventory action to perform",
    )
    name: StrictStr = Field(..., description="Name of the host")
    username: StrictStr = Field(None, description="Host connections username")
    password: StrictStr = Field(None, description="Host connections password")
    platform: StrictStr = Field(
        None, description="Host platform recognized by connection plugin"
    )
    hostname: StrictStr = Field(
        None,
        description="Hostname of the host to initiate connection with, IP address or FQDN",
    )
    port: StrictInt = Field(22, description="TCP port to initiate connection with")
    connection_options: dict = Field(
        None,
        description="JSON string with connection options",
        alias="connection-options",
    )
    groups: list[StrictStr] = Field(
        None, description="List of groups to associate with this host"
    )
    data: dict = Field(None, description="JSON string with arbitrary host data")


class RuntimeUpdateHostInput(
    RuntimeCreateHostInput, extra="allow", use_enum_values=True, populate_by_name=True
):
    action: RuntimeInventoryAction = Field(
        RuntimeInventoryAction.update_host,
        description="Runtime inventory action to perform",
    )
    groups_action: GroupsUpdateAction = Field(
        GroupsUpdateAction.append,
        description="Action to perform with groups",
        alias="groups-action",
    )


class RuntimeDeleteHostInput(
    RuntimeInventoryInput, extra="allow", use_enum_values=True, populate_by_name=True
):
    action: RuntimeInventoryAction = Field(
        RuntimeInventoryAction.delete_host,
        description="Runtime inventory action to perform",
    )
    name: StrictStr = Field(..., description="Name of the host")


class RuntimeReadHostDataInput(
    RuntimeInventoryInput,
    NornirHostsFilters,
    extra="allow",
    use_enum_values=True,
    populate_by_name=True,
):
    action: RuntimeInventoryAction = Field(
        RuntimeInventoryAction.read_host_data,
        description="Runtime inventory action to perform",
    )
    keys: Union[StrictStr, list[StrictStr]] = Field(
        ...,
        description="Dot separated path within host data",
        examples="config.interfaces.Lo0",
    )


class RuntimeInventoryResult(Result):
    result: Any = Field(
        None,
        description="Runtime inventory action result",
    )


# --------------------------------------------------------------------------
# NETCONF TASK MODELS
# --------------------------------------------------------------------------


class NetconfPlugin(str, Enum):
    ncclient = "ncclient"
    scrapli = "scrapli"


class NetconfConfigSource(str, Enum):
    running = "running"
    candidate = "candidate"


class NetconfInput(
    NornirCommonArgs, extra="allow", use_enum_values=True, populate_by_name=True
):
    call: StrictStr = Field(
        ...,
        description="NETCONF method or special call to execute",
    )
    plugin: NetconfPlugin = Field(
        NetconfPlugin.ncclient,
        description="NETCONF connection plugin to use",
    )
    data: Union[None, StrictStr] = Field(
        None,
        description="RPC content or path to RPC data",
    )


class NetconfGetConfigInput(
    NetconfInput, extra="allow", use_enum_values=True, populate_by_name=True
):
    call: StrictStr = Field("get_config", description="NETCONF method to execute")
    plugin: NetconfPlugin = Field(
        NetconfPlugin.ncclient,
        description="NETCONF plugin to use",
    )
    source: NetconfConfigSource = Field(
        NetconfConfigSource.running,
        description="Configuration source to retrieve",
    )
    filter_subtree: Union[None, StrictStr] = Field(
        None,
        description="XML subtree to retrieve portion of configuration",
        alias="filter-subtree",
    )


class NetconfCapabilitiesInput(
    NetconfInput, extra="allow", use_enum_values=True, populate_by_name=True
):
    call: StrictStr = Field(
        "server_capabilities", description="NETCONF method to execute"
    )
    plugin: NetconfPlugin = Field(
        NetconfPlugin.ncclient,
        description="NETCONF plugin to use",
    )
    capab_filter: Union[None, StrictStr] = Field(
        None, description="Glob pattern to filter capabilities", alias="capab-filter"
    )


class NetconfResult(NornirSerializedResult):
    result: Union[dict[StrictStr, Any], list[Any]] = Field(
        {},
        description="NETCONF operation results keyed by host or returned as serialized task records",
    )


# --------------------------------------------------------------------------
# NETWORK TASK MODELS
# --------------------------------------------------------------------------


class NetworkFunction(str, Enum):
    ping = "ping"
    resolve_dns = "resolve_dns"


class NetworkInput(
    NornirCommonArgs, extra="allow", use_enum_values=True, populate_by_name=True
):
    fun: Union[NetworkFunction, StrictStr] = Field(
        ...,
        description="Nornir-Salt network utility function to call",
    )


class NetworkPingInput(
    NetworkInput, extra="allow", use_enum_values=True, populate_by_name=True
):
    fun: NetworkFunction = Field(
        NetworkFunction.ping,
        description="Nornir-Salt network utility function to call",
    )
    use_host_name: StrictBool = Field(
        None,
        description="Ping host's name instead of host's hostname",
        json_schema_extra={"presence": True},
        alias="use-host-name",
    )
    count: StrictInt = Field(None, description="Number of pings to run")
    ping_timeout: StrictInt = Field(
        None,
        description="Time in seconds before considering each non-arrived reply permanently lost",
        alias="ping-timeout",
    )
    size: StrictInt = Field(None, description="Size of the entire packet to send")
    interval: Union[int, float] = Field(
        None, description="Interval to wait between pings"
    )
    payload: str = Field(None, description="Payload content if size is not set")
    sweep_start: StrictInt = Field(
        None,
        description="If size is not set, initial size in a sweep of sizes",
        alias="sweep-start",
    )
    sweep_end: StrictInt = Field(
        None,
        description="If size is not set, final size in a sweep of sizes",
        alias="sweep-end",
    )
    df: StrictBool = Field(
        None,
        description="Don't Fragment flag value for IP Header",
        json_schema_extra={"presence": True},
    )
    match: StrictBool = Field(
        None,
        description="Do payload matching between request and reply",
        json_schema_extra={"presence": True},
    )
    source: StrictStr = Field(None, description="Source IP address")


class NetworkDnsInput(
    NetworkInput, extra="allow", use_enum_values=True, populate_by_name=True
):
    fun: NetworkFunction = Field(
        NetworkFunction.resolve_dns,
        description="Nornir-Salt network utility function to call",
    )
    use_host_name: StrictBool = Field(
        None,
        description="Ping host's name instead of host's hostname",
        json_schema_extra={"presence": True},
        alias="use-host-name",
    )
    servers: Union[StrictStr, list[StrictStr]] = Field(
        None, description="List of DNS servers to use"
    )
    dns_timeout: StrictInt = Field(
        None,
        description="Time in seconds before considering request lost",
        alias="dns-timeout",
    )
    ipv4: StrictBool = Field(
        None, description="Resolve 'A' record", json_schema_extra={"presence": True}
    )
    ipv6: StrictBool = Field(
        None, description="Resolve 'AAAA' record", json_schema_extra={"presence": True}
    )


class NetworkResult(NornirSerializedResult):
    result: Union[dict[StrictStr, Any], list[Any]] = Field(
        {},
        description="Network utility results keyed by host or returned as serialized task records",
    )


# --------------------------------------------------------------------------
# NORNIR WORKER MODELS
# --------------------------------------------------------------------------


class GetVersionInput(BaseModel, use_enum_values=True, populate_by_name=True):
    pass


class GetVersionResult(Result):
    result: Dict[StrictStr, StrictStr] = Field(
        {},
        description="Installed package versions keyed by package name",
    )


class GetWatchdogConnectionsInput(
    BaseModel, use_enum_values=True, populate_by_name=True
):
    pass


class GetWatchdogConnectionsResult(Result):
    result: Dict[StrictStr, Any] = Field(
        {},
        description="Watchdog connection state keyed by host and plugin",
    )


class RefreshNornirInput(BaseModel, use_enum_values=True, populate_by_name=True):
    progress: StrictBool = Field(
        False,
        description="Emit progress events while refreshing Nornir",
        json_schema_extra={"presence": True},
    )


class RefreshNornirResult(Result):
    result: StrictBool = Field(
        True,
        description="True if Nornir refreshed successfully",
    )


# --------------------------------------------------------------------------
# PARSE TASK MODELS
# --------------------------------------------------------------------------


class NapalmGettersEnum(str, Enum):
    get_arp_table = "get_arp_table"
    get_bgp_config = "get_bgp_config"
    get_bgp_neighbors = "get_bgp_neighbors"
    get_bgp_neighbors_detail = "get_bgp_neighbors_detail"
    get_config = "get_config"
    get_environment = "get_environment"
    get_facts = "get_facts"
    get_firewall_policies = "get_firewall_policies"
    get_interfaces = "get_interfaces"
    get_interfaces_counters = "get_interfaces_counters"
    get_interfaces_ip = "get_interfaces_ip"
    get_ipv6_neighbors_table = "get_ipv6_neighbors_table"
    get_lldp_neighbors = "get_lldp_neighbors"
    get_lldp_neighbors_detail = "get_lldp_neighbors_detail"
    get_mac_address_table = "get_mac_address_table"
    get_network_instances = "get_network_instances"
    get_ntp_peers = "get_ntp_peers"
    get_ntp_servers = "get_ntp_servers"
    get_ntp_stats = "get_ntp_stats"
    get_optics = "get_optics"
    get_probes_config = "get_probes_config"
    get_probes_results = "get_probes_results"
    get_route_to = "get_route_to"
    get_snmp_information = "get_snmp_information"
    get_users = "get_users"
    get_vlans = "get_vlans"
    is_alive = "is_alive"
    ping = "ping"
    traceroute = "traceroute"


class TTPStructureEnum(str, Enum):
    flat_list = "flat_list"
    list_ = "list"
    dictionary = "dictionary"


class ParseNapalmInput(
    NornirCommonArgs, extra="allow", use_enum_values=True, populate_by_name=True
):
    getters: Union[
        NapalmGettersEnum, StrictStr, list[Union[NapalmGettersEnum, StrictStr]]
    ] = Field(
        "get_facts",
        description="NAPALM getter name or list of getter names to call",
    )


class ParseNapalmResult(NornirSerializedResult):
    result: Union[dict[StrictStr, Any], list[Any]] = Field(
        {},
        description="NAPALM getter results keyed by host or returned as serialized task records",
    )


class ParseTextfsmInput(
    NornirCommonArgs, extra="allow", use_enum_values=True, populate_by_name=True
):
    commands: Union[None, StrictStr, list[StrictStr]] = Field(
        None,
        description="Commands to collect and parse with TextFSM",
    )
    template: Union[None, StrictStr] = Field(
        None,
        description="TextFSM template path, NorFab URL, or template text",
    )


class ParseTextfsmResult(NornirSerializedResult):
    result: Union[dict[StrictStr, Any], list[Any]] = Field(
        {},
        description="TextFSM parsed results keyed by host or returned as serialized task records",
    )


class ParseTTPInput(
    NornirCommonArgs, extra="allow", use_enum_values=True, populate_by_name=True
):
    template: Union[None, StrictStr] = Field(
        None,
        description="TTP template string, nf:// path, or ttp:// path",
    )
    strict: StrictBool = Field(
        True,
        description="Raise an error when a host produces no parsed output",
        json_schema_extra={"presence": True},
    )
    structure: TTPStructureEnum = Field(
        TTPStructureEnum.flat_list,
        description="TTP result structure",
    )
    commands: Union[None, StrictStr, list[StrictStr]] = Field(
        None,
        description="Fallback commands to collect when template input defines none",
    )
    get: Union[None, StrictStr] = Field(
        None,
        description="TTP templates getter name to load",
    )
    plugin: NornirCliPlugin = Field(
        NornirCliPlugin.netmiko,
        description="Nornir CLI connection plugin for output collection",
    )

    @model_validator(mode="after")
    def validate_template_or_get(self) -> "ParseTTPInput":
        if not self.template and not self.get:
            raise ValueError("Either 'template' or 'get' must be provided")
        return self


class ParseTTPResult(Result):
    result: dict[StrictStr, Any] = Field(
        {},
        description="TTP parsed data keyed by host",
    )


# --------------------------------------------------------------------------
# TASK TASK MODELS
# --------------------------------------------------------------------------


class TaskInput(
    NornirCommonArgs, extra="allow", use_enum_values=True, populate_by_name=True
):
    plugin: StrictStr = Field(
        ...,
        description="Python import path or nf:// URL for a Nornir task plugin",
    )


class TaskResult(NornirSerializedResult):
    result: Union[dict[StrictStr, Any], list[Any]] = Field(
        {},
        description="Custom Nornir task results keyed by host or returned as serialized task records",
    )


# --------------------------------------------------------------------------
# TEST TASK MODELS
# --------------------------------------------------------------------------


class TestInput(
    NornirCommonArgs, extra="allow", use_enum_values=True, populate_by_name=True
):
    suite: Union[StrictStr, list[dict[StrictStr, Any]], list[Any]] = Field(
        ...,
        description="Test suite as a NorFab URL, template, or list of test definitions",
    )
    subset: Union[None, StrictStr] = Field(
        None,
        description="Glob pattern to filter tests by name",
    )
    dry_run: StrictBool = Field(
        False,
        description="Render and return tests without executing them",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    return_tests_suite: StrictBool = Field(
        False,
        description="Include rendered per-host test suites in the result",
        alias="return-tests-suite",
        json_schema_extra={"presence": True},
    )
    job_data: Union[None, StrictStr, dict[StrictStr, Any], list[Any]] = Field(
        None,
        description="Job data as a NorFab URL, dictionary, or list for Jinja2 rendering",
        alias="job-data",
    )
    extensive: StrictBool = Field(
        False,
        description="Return extensive test output and rendered suites",
        json_schema_extra={"presence": True},
    )
    groups: Union[None, list[StrictStr]] = Field(
        None, description="List of test group names to run"
    )


class TestResult(Result):
    result: Union[dict[StrictStr, Any], list[Any]] = Field(
        {},
        description="Test results keyed by host, serialized as records, or including rendered suites",
    )
