import logging
import os
from enum import Enum
from typing import Any, Union

from nornir_netmiko.tasks import netmiko_file_transfer
from nornir_salt.plugins.functions import ResultSerializer
from nornir_salt.plugins.tasks import nr_test
from pydantic import BaseModel, Field, StrictBool, StrictFloat, StrictInt, StrictStr

from norfab.core.exceptions import UnsupportedPluginError
from norfab.core.worker import Job, Task
from norfab.models import Result

from .nornir_models import NornirCommonArgs, NornirSerializedResult

log = logging.getLogger(__name__)


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


class FileCopyTask:
    @Task(fastapi={"methods": ["POST"]}, input=FileCopyInput, output=FileCopyResult)
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
            ret.dry_run = True
        else:
            with self.connections_lock:
                result = nr.run(task=task_plugin, **kwargs)

        ret.failed = result.failed  # failed is true if any of the hosts failed
        ret.result = ResultSerializer(result, to_dict=to_dict, add_details=add_details)

        self.watchdog.connections_update(nr, plugin)
        self.watchdog.connections_clean()

        return ret
