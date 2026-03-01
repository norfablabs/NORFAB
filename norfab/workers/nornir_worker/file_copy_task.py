import logging
import os

from typing import Any
from norfab.models import Result
from norfab.core.worker import Task, Job
from norfab.core.exceptions import UnsupportedPluginError
from nornir_netmiko.tasks import netmiko_file_transfer
from nornir_salt.plugins.tasks import nr_test
from nornir_salt.plugins.functions import ResultSerializer

log = logging.getLogger(__name__)


class FileCopyTask:
    @Task(fastapi={"methods": ["POST"]})
    def file_copy(
        self,
        job: Job,
        source_file: str,
        plugin: str = "netmiko",
        to_dict: bool = True,
        add_details: bool = False,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> Result:
        """
        Task to transfer files to and from hosts using SCP.

        Args:
            job: NorFab Job object containing relevant metadata
            source_file (str): The path or URL of the source file to be copied in
                ``nf://path/to/file`` format
            plugin (str, optional): The plugin to use for file transfer. Supported plugins:

                - netmiko - uses `netmiko_file_transfer` task plugin.

            to_dict (bool, optional): Whether to return the result as a dictionary. Defaults to True.
            add_details (bool, optional): Whether to add detailed information to the result. Defaults to False.
            dry_run (bool, optional): If True, performs a dry run without making any changes. Defaults to False.
            **kwargs: Additional arguments to pass to the file transfer plugin.

        Returns:
            dict: The result of the file copy operation.

        Raises:
            UnsupportedPluginError: If the specified plugin is not supported.
        """
        timeout = job.timeout * 0.9
        ret = Result(task=f"{self.name}:file_copy", result={} if to_dict else [])

        filtered_nornir, ret = self.filter_hosts_and_validate(kwargs, ret)
        if ret.status == "no_match":
            return ret

        # download file from broker
        if self.is_url(source_file):
            source_file_local = self.fetch_file(
                source_file, raise_on_fail=True, read=False
            )

        # decide on what send commands task plugin to use
        if plugin == "netmiko":
            task_plugin = netmiko_file_transfer
            kwargs["source_file"] = source_file_local
            kwargs.setdefault("socket_timeout", timeout / 5)
            kwargs.setdefault("dest_file", os.path.split(source_file_local)[-1])
        else:
            raise UnsupportedPluginError(f"Plugin '{plugin}' not supported")

        nr = self._add_processors(filtered_nornir, kwargs, job)  # add processors

        # run task
        log.debug(
            f"{self.name} - running file copy with arguments '{kwargs}', is dry run - '{dry_run}'"
        )
        if dry_run is True:
            result = nr.run(task=nr_test, name="file_copy_dry_run", **kwargs)
        else:
            with self.connections_lock:
                result = nr.run(task=task_plugin, **kwargs)

        ret.failed = result.failed  # failed is true if any of the hosts failed
        ret.result = ResultSerializer(result, to_dict=to_dict, add_details=add_details)

        self.watchdog.connections_update(nr, plugin)
        self.watchdog.connections_clean()

        return ret
