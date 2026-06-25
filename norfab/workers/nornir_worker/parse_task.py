import logging
from typing import Any, Union

from nornir_salt.plugins.functions import FFun_functions
from ttp import ttp
from ttp_templates import get_template

from norfab.core.worker import Job, Task
from norfab.models import Result

from .nornir_models import (
    ParseNapalmInput,
    ParseNapalmResult,
    ParseTTPInput,
    ParseTTPResult,
    ParseTextfsmInput,
    ParseTextfsmResult,
)

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# PARSE TASK MODELS
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------------------
# PARSE TASKS
# --------------------------------------------------------------------------------------


class ParseTask:

    @Task(
        fastapi={"methods": ["POST"]},
        input=ParseNapalmInput,
        output=ParseNapalmResult,
        mcp={
            "annotations": {
                "title": "Parse NAPALM Output",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def parse_napalm(
        self,
        job: Job,
        getters: Union[str, list[str]] = "get_facts",
        to_dict: bool = True,
        add_details: bool = False,
        **kwargs: Any,
    ) -> Result:
        """
        Parse network device output using NAPALM getters.

        Args:
            job: NorFab Job object containing relevant metadata.
            getters: NAPALM getter name(s) to call, e.g. ``get_facts``.
            to_dict: If True, return results as a dictionary keyed by hostname.
            add_details: If True, include extra task details in the result.
            **kwargs: Additional arguments forwarded to Nornir host filtering.

        Returns:
            Result containing parsed NAPALM getter data.
        """
        ret = self.task(
            job=job,
            plugin="nornir_napalm.plugins.tasks.napalm_get",
            getters=getters,
            to_dict=to_dict,
            add_details=add_details,
            **kwargs,
        )
        ret.task = f"{self.name}:parse_napalm"
        return ret

    @Task(
        fastapi={"methods": ["POST"]},
        input=ParseTextfsmInput,
        output=ParseTextfsmResult,
        mcp={
            "annotations": {
                "title": "Parse TextFSM Output",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def parse_textfsm(
        self,
        job: Job,
        commands: Union[str, list[str], None] = None,
        template: Union[str, None] = None,
        to_dict: bool = True,
        add_details: bool = False,
        **kwargs: Any,
    ) -> Result:
        """
        Parse network device output using TextFSM templates.

        Collects CLI output from devices and parses it using a TextFSM template.
        When no template is provided, NTC-Templates auto-detection is used based
        on the device platform and command.

        Args:
            job: NorFab Job object containing relevant metadata.
            commands: Command(s) to collect from devices.
            template: Path to a TextFSM template file, or ``nf://`` URL to a
                file stored in NorFab file sharing. If omitted, NTC-Templates
                auto-detection is used.
            to_dict: If True, return results as a dictionary keyed by hostname.
            add_details: If True, include extra task details in the result.
            **kwargs: Additional arguments forwarded to Nornir host filtering
                and the CLI collection task.

        Returns:
            Result containing per-host TextFSM parsed output.
        """
        ret = Result(task=f"{self.name}:parse_textfsm", result={} if to_dict else [])

        filtered_nornir, ret = self.filter_hosts_and_validate(kwargs, ret)
        if ret.status == "no_match":
            return ret

        # resolve template from URL or local nf:// path
        if template and self.is_url(template):
            template = self.fetch_file(template, raise_on_fail=True, read=False)

        result = self.cli(
            job=job,
            commands=commands,
            plugin="netmiko",
            to_dict=to_dict,
            add_details=add_details,
            use_textfsm=True,
            textfsm_template=template,
            **kwargs,
        )
        ret.result = result.result
        ret.failed = result.failed
        ret.errors = result.errors

        return ret

    @Task(
        fastapi={"methods": ["POST"]},
        input=ParseTTPInput,
        output=ParseTTPResult,
        mcp={
            "annotations": {
                "title": "Parse TTP Output",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def parse_ttp(
        self,
        job: Job,
        template: Union[str, None] = None,
        strict: bool = False,
        structure: str = "flat_list",
        commands: Union[str, list[str], None] = None,
        get: Union[str, None] = None,
        plugin: str = "netmiko",
        **kwargs: Any,
    ) -> Result:
        """
        Parse network device output using a TTP template.

        Fetches CLI output from devices based on the template's input
        definitions, then parses the collected output with TTP.

        Args:
            job: NorFab Job object containing relevant metadata.
            template: TTP template string, URL, or ``ttp://`` path.
            strict: If True, raise ``RuntimeError`` when any host yields no parsed output.
            structure: TTP result structure one of ``flat_list``, ``list``, or ``dictionary``.
            commands: Fallback commands to collect when the template defines no explicit input commands.
            get: TTP getter template name to use.
            plugin: Nornir connection plugin for CLI collection (default ``netmiko``).
            **kwargs: Additional arguments forwarded to Nornir host filtering and the CLI collection task.

        Returns:
            Result containing per-host TTP parsing output.

        Raises:
            RuntimeError: If ``strict=True`` and a host produces empty results.
        """
        kwargs["to_dict"] = True
        kwargs["add_details"] = True
        filters = {k: kwargs[k] for k in kwargs.keys() if k in FFun_functions}
        ret = Result(task=f"{self.name}:parse_ttp", result={})

        # check has hosts to run for
        filtered_nornir, ret = self.filter_hosts_and_validate(kwargs, ret)
        if ret.status == "no_match":
            return ret

        # download TTP template
        if self.is_url(template):
            template = self.fetch_file(template, raise_on_fail=True, read=True)
        elif template and template.startswith("ttp://"):
            template = get_template(path=template)
        elif get:
            template = get_template(get=get)

        # go over template's inputs and collect commands to fetch from devices
        cli_runs = []
        parser = ttp(template=template, log_level="ERROR")
        for template_name, inputs in parser.get_input_load().items():
            inputs = inputs or {"Default_Input": {}}
            for input_name, input_params in inputs.items():
                cli_runs.append(
                    {
                        "commands": input_params.get("commands") or commands,
                        "input_name": input_name,
                        "template_name": template_name,
                        "params": input_params,
                    }
                )

        job.event(
            f"collecting output from {len(filtered_nornir.inventory.hosts)} devices for {len(cli_runs)} TTP template input(s)"
        )

        # collect commands output from devices
        for cli_run in cli_runs:
            cli_run_filters = {
                k: cli_run["params"][k]
                for k in cli_run["params"].keys()
                if k in FFun_functions
            }
            cli_run_kwargs = {
                **filters,
                **kwargs,
                **cli_run_filters,
            }
            if cli_run["params"].get("platform"):
                cli_run_kwargs["FM"] = cli_run["params"]["platform"]
            result = self.cli(
                job=job, commands=cli_run["commands"], **cli_run_kwargs, plugin=plugin
            )
            if result.failed:
                ret.failed = True
                log.error(
                    f"Failed collecting commands output, errors: {result.errors or result.messages}"
                )
                job.event("failed collecting commands output", severity="ERROR")
                ret.errors.extend(result.errors)
                ret.messages.extend(result.messages)
                if not result.result or not isinstance(result.result, dict):
                    continue
            # parse commands output for each host
            for hname, hres in result.result.items():
                input_data = []
                for cmdname, cmdres in hres.items():
                    if cmdres["failed"]:
                        msg = f"Failed collecting command '{cmdname}' output from '{hname}', error: {cmdres['exception']}"
                        log.error(msg)
                        ret.errors.append(msg)
                        job.event(msg, severity="ERROR")
                        continue
                    input_data.append(cmdres["result"])
                # parse command results
                if input_data:
                    parser = ttp(template=template, log_level="ERROR")
                    parser.add_input(
                        data="\n\n".join(input_data),
                        input_name=cli_run["input_name"],
                        template_name=cli_run["template_name"],
                    )
                    # run parsing in single process
                    parser.parse(one=True)
                    ret.result[hname] = parser.result(
                        structure=structure, templates=cli_run["template_name"]
                    )
                else:
                    msg = f"No input data collected for '{hname}' device"
                    log.error(msg)
                    ret.errors.append(msg)
                    ret.result[hname] = None
                    job.event(msg, severity="ERROR")

        # if strict - check hosts parsing results and raise error if empty
        if strict:
            for hname, hres in ret.result.items():
                if not hres or hres in [[{}], [], {}, [[]]]:
                    raise RuntimeError(f"{hname} host parsing produced no results")

        return ret
