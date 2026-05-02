import builtins
import logging
from typing import List, Optional, Union

from picle.models import Outputters, PipeFunctionsModel
from pydantic import Field, StrictBool, StrictInt, StrictStr

from norfab.workers.netbox_worker.netbox_models import NetboxCommonArgs

from ..common import listen_events, log_error_or_result
from ..nornir.nornir_picle_shell_common import NorniHostsFilters
from .netbox_picle_shell_common import NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class SyncIpAddressesShell(NetboxCommonArgs, NetboxClientRunJobArgs, NorniHostsFilters):
    dry_run: Optional[StrictBool] = Field(
        None,
        description="Return information that would be pushed to Netbox but do not push it",
        json_schema_extra={"presence": True},
        alias="dry-run",
    )
    devices: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="List of Netbox devices to sync",
    )
    batch_size: StrictInt = Field(
        10, description="Number of devices to process at a time", alias="batch-size"
    )
    branch: StrictStr = Field(None, description="Branching plugin branch name to use")

    @staticmethod
    @listen_events
    def run(uuid: str, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        kwargs["timeout"] = timeout * 0.9
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]

        result = NFCLIENT.run_job(
            "netbox",
            "sync_device_ip",
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
