"""
PICLE Shell CLient
==================

check-sync commands for Netbox service.
"""

import builtins
import logging
from typing import List, Union

from picle.models import Outputters, PipeFunctionsModel
from pydantic import BaseModel, Field, StrictStr

from norfab.workers.netbox_worker.netbox_models import CheckDeviceSyncInput

from ..common import listen_events, log_error_or_result
from ..nornir.nornir_picle_shell_common import NorniHostsFilters
from .netbox_picle_shell_common import NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class CheckSyncDevicesShell(
    NetboxClientRunJobArgs,
    CheckDeviceSyncInput,
    NorniHostsFilters,
    use_enum_values=True,
    populate_by_name=True,
):
    devices: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="List of NetBox devices to check sync state for",
    )

    @staticmethod
    @listen_events
    def run(uuid: str, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        kwargs["timeout"] = int(timeout * 0.9)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]

        result = NFCLIENT.run_job(
            "netbox",
            "check_device_sync",
            workers=workers,
            kwargs=kwargs,
            timeout=timeout,
            uuid=uuid,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        result = log_error_or_result(result, verbose_result=verbose_result)

        return result

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel


class CheckSyncCommands(BaseModel):
    devices: CheckSyncDevicesShell = Field(
        None,
        description="Check if device data in NetBox is in sync with live device state",
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[netbox-check-sync]#"
