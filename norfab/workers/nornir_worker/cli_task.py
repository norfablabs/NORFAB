import logging
from typing import Any, Union

from nornir_salt.plugins.functions import ResultSerializer
from nornir_salt.plugins.tasks import (
    napalm_send_commands,
    netmiko_send_commands,
    nr_test,
    scrapli_send_commands,
)
from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr, model_validator

from norfab.core.exceptions import UnsupportedPluginError
from norfab.core.worker import Job, Task
from norfab.models import Result

from .nornir_models import NornirCliPlugin, NornirCommonArgs, NornirSerializedResult

log = logging.getLogger(__name__)


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


class CliTask:
    @Task(
        fastapi={"methods": ["POST"]},
        input=CliInput,
        output=CliResult,
        mcp={
            "annotations": {
                "title": "Run CLI Commands",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": False,
                "openWorldHint": True,
            }
        },
    )
    def cli(
        self,
        job: Job,
        commands: Union[str, list] = None,
        plugin: str = "netmiko",
        dry_run: bool = False,
        run_ttp: str = None,
        job_data: Any = None,
        to_dict: bool = True,
        add_details: bool = False,
        **kwargs: Any,
    ) -> Result:
        """
        Task to collect/retrieve show commands output from network devices using
        Command Line Interface (CLI).

        Must either provide list of commands to run or TTP template to run.

        Args:
            job: NorFab Job object containing relevant metadata
            commands (list, optional): List of commands to send to devices or URL to a file or template
                URL that resolves to a file.
            plugin (str, optional): Plugin name to use. Valid options are
                ``netmiko``, ``scrapli``, ``napalm``.
            dry_run (bool, optional): If True, do not send commands to devices,
                just return them.
            run_ttp (str, optional): TTP Template to run.
            job_data (str, optional): URL to YAML file with data or dictionary/list
                of data to pass on to Jinja2 rendering context.
            to_dict (bool, optional): If True, returns results as a dictionary.
            add_details (bool, optional): If True, adds task execution details
                to the results.
            **kwargs: Additional arguments to pass to the specified task plugin.

        Returns:
            dict: A dictionary with the results of the CLI task.

        Raises:
            UnsupportedPluginError: If the specified plugin is not supported.
            FileNotFoundError: If the specified TTP template or job data file
                cannot be downloaded.
        """
        job_data = job_data or {}
        timeout = job.timeout * 0.9
        ret = Result(task=f"{self.name}:cli", result={} if to_dict else [])

        filtered_nornir, no_match_result = self.filter_hosts_and_validate(kwargs, ret)
        if ret.status == "no_match":
            return ret

        # decide on what send commands task plugin to use
        if plugin == "netmiko":
            task_plugin = netmiko_send_commands
            if kwargs.get("use_ps"):
                kwargs.setdefault("timeout", timeout)
            else:
                kwargs.setdefault("read_timeout", timeout)
        elif plugin == "scrapli":
            task_plugin = scrapli_send_commands
            kwargs.setdefault("timeout_ops", timeout)
        elif plugin == "napalm":
            task_plugin = napalm_send_commands
        else:
            raise UnsupportedPluginError(f"Plugin '{plugin}' not supported")

        # download TTP template
        if self.is_url(run_ttp):
            downloaded = self.fetch_file(run_ttp)
            kwargs["run_ttp"] = downloaded
            if downloaded is None:
                msg = f"{self.name} - TTP template download failed '{run_ttp}'"
                raise FileNotFoundError(msg)
        # use TTP template as is - inline template or ttp://xyz path
        elif run_ttp:
            kwargs["run_ttp"] = run_ttp

        # download job data
        job_data = self.load_job_data(job_data)

        nr = self._add_processors(filtered_nornir, kwargs, job)  # add processors

        # render commands using Jinja2 on a per-host basis
        if commands:
            commands = commands if isinstance(commands, list) else [commands]
            for host in nr.inventory.hosts.values():
                rendered = self.jinja2_render_templates(
                    templates=commands,
                    context={
                        "host": host,
                        "norfab": self.client,
                        "job_data": job_data,
                        "netbox": self.add_jinja2_netbox(),
                    },
                    filters=self.add_jinja2_filters(),
                )
                host.data["__task__"] = {"commands": rendered}

        # run task
        log.debug(
            f"{self.name} - running cli commands '{commands}', kwargs '{kwargs}', is cli dry run - '{dry_run}'"
        )
        if dry_run is True:
            result = nr.run(
                task=nr_test, use_task_data="commands", name="dry_run", **kwargs
            )
            ret.dry_run = True
        else:
            with self.connections_lock:
                result = nr.run(task=task_plugin, **kwargs)

        ret.failed = result.failed  # failed is true if any of the hosts failed
        ret.result = ResultSerializer(result, to_dict=to_dict, add_details=add_details)

        # remove __task__ data
        for host_name, host_object in nr.inventory.hosts.items():
            _ = host_object.data.pop("__task__", None)

        self.watchdog.connections_update(nr, plugin)
        self.watchdog.connections_clean()

        return ret
