import builtins
import logging
from typing import List, Union

from picle.models import Outputters, PipeFunctionsModel
from pydantic import (
    Field,
    StrictInt,
    StrictStr,
)
from rich.console import Console

from norfab.workers.containerlab_worker.containerlab_models import DeployNetboxInput

from ..common import ClientRunJobArgs, listen_events, log_error_or_result
from ..netbox.netbox_picle_shell_get_containerlab_inventory import (
    NetboxDeviceFilters,
)

RICHCONSOLE = Console()
SERVICE = "containerlab"
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------------------------
# CONTAINERLAB DEPLOY NETBOX COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class DeployNetboxDeviceFilters(NetboxDeviceFilters):
    @staticmethod
    def run(*args: object, **kwargs: object):
        filters = {
            k: kwargs.pop(k)
            for k in [
                "tenant",
                "q",
                "model",
                "platform",
                "region",
                "role",
                "site",
                "status",
                "tag",
            ]
            if k in kwargs
        }
        # need to be a list
        kwargs["filters"] = [filters]
        return DeployNetboxCommand.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel


class DeployNetboxCommand(
    ClientRunJobArgs,
    DeployNetboxInput,
    use_enum_values=True,
    populate_by_name=True,
):
    filters: DeployNetboxDeviceFilters = Field(
        None, description="Netbox device filters to generate lab inventory for"
    )
    devices: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="List of devices to generate lab inventory for",
    )
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "any", description="Filter worker to target"
    )
    instance: StrictStr = Field(
        None,
        description="Name of Netbox instance to pull inventory from",
        alias="netbox-instance",
    )
    ports: List[StrictInt] = Field(
        [12000, 15000],
        description="Range of TCP/UDP ports to use for nodes",
    )

    @staticmethod
    def source_lab_name() -> list:
        NFCLIENT = builtins.NFCLIENT
        ret = []
        result = NFCLIENT.run_job("containerlab", "get_running_labs")
        for wname, wres in result.items():
            ret.extend(wres["result"])
        return ret

    @staticmethod
    @listen_events
    def run(uuid: str, *args: object, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        verbose_result = kwargs.pop("verbose_result")
        workers = kwargs.pop("workers", "any")
        nowait = kwargs.pop("nowait", False)

        if not any(k in kwargs for k in ["devices", "filters", "tenant"]):
            raise ValueError(
                "Devices list or Netbox filters or Tenant name must be provided."
            )

        if not any(k in kwargs for k in ["lab_name", "tenant"]):
            raise ValueError("Lab name or Tenant name must be provided.")

        if kwargs.get("devices"):
            if not isinstance(kwargs.get("devices"), list):
                kwargs["devices"] = [kwargs["devices"]]

        result = NFCLIENT.run_job(
            "containerlab",
            "deploy_netbox",
            workers=workers,
            kwargs=kwargs,
            args=args,
            uuid=uuid,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(
            result, verbose_result=verbose_result, verbose_on_fail=True
        )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
