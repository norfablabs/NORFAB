import logging

from typing import Union, Any
from norfab.models import Result
from norfab.core.worker import Task, Job
from norfab.core.exceptions import UnsupportedPluginError
from nornir_salt.plugins.tasks import (
    netmiko_send_commands,
    scrapli_send_commands,
    napalm_send_commands,
    nr_test,
)
from nornir_salt.plugins.functions import ResultSerializer
from norfab.clients.shell_clients.nornir.nornir_picle_shell_cli import NorniCliInput

log = logging.getLogger(__name__)


class CliTask:
    @Task(
        fastapi={"methods": ["POST"]},
        input=NorniCliInput,
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
