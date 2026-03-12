import logging
from typing import Any, Union

from nornir_salt.plugins.functions import ResultSerializer
from nornir_salt.plugins.tasks import (
    napalm_configure,
    netmiko_send_config,
    nr_test,
    scrapli_send_config,
)

from norfab.core.exceptions import UnsupportedPluginError
from norfab.core.worker import Job, Task
from norfab.models import Result

log = logging.getLogger(__name__)


class CfgTask:
    @Task(
        fastapi={"methods": ["POST"]},
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
