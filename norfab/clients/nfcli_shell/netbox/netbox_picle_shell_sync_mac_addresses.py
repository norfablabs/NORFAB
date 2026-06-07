import logging
from typing import List, Union

from picle.models import Outputters, PipeFunctionsModel
from pydantic import Field, StrictStr

from norfab.workers.netbox_worker.netbox_models import SyncMacAddressesInput

from ..common import log_error_or_result, run_future_job
from ..nornir.nornir_picle_shell_common import NorniHostsFilters
from .netbox_picle_shell_common import NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class SyncMacAddressesShell(
    NetboxClientRunJobArgs,
    SyncMacAddressesInput,
    NorniHostsFilters,
    use_enum_values=True,
    populate_by_name=True,
):
    devices: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="List of Netbox devices to sync MAC addresses for",
    )

    @staticmethod
    def run(**kwargs: object):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        kwargs["timeout"] = int(timeout * 0.9)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]

        result = run_future_job(
            "netbox",
            "sync_mac_addresses",
            workers=workers,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        result = log_error_or_result(result, verbose_result=verbose_result)

        return result

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
