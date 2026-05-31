import logging
from typing import Any, Union

from nornir_salt.plugins.functions import ResultSerializer
from nornir_salt.plugins.tasks import (
    napalm_configure,
    netmiko_send_config,
    nr_test,
    scrapli_send_config,
)
from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr

from norfab.core.exceptions import UnsupportedPluginError
from norfab.core.worker import Job, Task
from norfab.models import Result

from .nornir_models import NornirCliPlugin, NornirCommonArgs, NornirSerializedResult

log = logging.getLogger(__name__)


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


class CfgTask:
    @Task(
        fastapi={"methods": ["POST"]},
        input=CfgInput,
        output=CfgResult,
        mcp={
            "annotations": {
                "title": "Configure Devices",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": False,
                "openWorldHint": True,
            }
        },
    )
    def cfg(
        self,
        job: Job,
        config: Union[str, list],
        plugin: str = "netmiko",
        dry_run: bool = False,
        to_dict: bool = True,
        add_details: bool = False,
        job_data: Any = None,
        **kwargs: Any,
    ) -> Result:
        """
        Task to send configuration commands to devices using Command Line Interface (CLI).

        Args:
            job: NorFab Job object containing relevant metadata
            config (list): List of commands to send to devices or URL to a file or template
                URL that resolves to a file.
            plugin (str, optional): Plugin name to use. Valid options are:

                - netmiko - use Netmiko to configure devices
                - scrapli - use Scrapli to configure devices
                - napalm - use NAPALM to configure devices

            dry_run (bool, optional): If True, will not send commands to devices but just return them.
            to_dict (bool, optional): If True, returns results as a dictionary. Defaults to True.
            add_details (bool, optional): If True, adds task execution details to the results.
            job_data (str, optional): URL to YAML file with data or dictionary/list of data to pass on to Jinja2 rendering context.
            **kwargs: Additional arguments to pass to the task plugin.

        Returns:
            dict: A dictionary with the results of the configuration task.

        Raises:
            UnsupportedPluginError: If the specified plugin is not supported.
            FileNotFoundError: If the specified job data file cannot be downloaded.
        """
        config = config if isinstance(config, list) else [config]
        ret = Result(task=f"{self.name}:cfg", result={} if to_dict else [])

        filtered_nornir, no_match_result = self.filter_hosts_and_validate(kwargs, ret)
        if ret.status == "no_match":
            return ret

        # decide on what send commands task plugin to use
        if plugin == "netmiko":
            task_plugin = netmiko_send_config
        elif plugin == "scrapli":
            task_plugin = scrapli_send_config
        elif plugin == "napalm":
            task_plugin = napalm_configure
        else:
            raise UnsupportedPluginError(f"Plugin '{plugin}' not supported")

        job_data = self.load_job_data(job_data)

        nr = self._add_processors(filtered_nornir, kwargs, job)  # add processors

        # render config using Jinja2 on a per-host basis
        for host in nr.inventory.hosts.values():
            rendered = self.jinja2_render_templates(
                templates=config,
                context={
                    "host": host,
                    "norfab": self.client,
                    "job_data": job_data,
                    "netbox": self.add_jinja2_netbox(),
                },
                filters=self.add_jinja2_filters(),
            )
            host.data["__task__"] = {"config": rendered}

        # run task
        log.debug(
            f"{self.name} - sending config commands '{config}', kwargs '{kwargs}', is dry_run - '{dry_run}'"
        )
        if dry_run is True:
            result = nr.run(
                task=nr_test, use_task_data="config", name="dry_run", **kwargs
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
