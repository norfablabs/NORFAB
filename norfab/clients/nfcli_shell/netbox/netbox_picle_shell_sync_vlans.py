from typing import Any, List, Union

from picle.models import Outputters, PipeFunctionsModel
from pydantic import Field, StrictStr

from norfab.workers.netbox_worker.netbox_models import SyncVlansInput

from ..common import log_error_or_result, run_future_job
from ..nornir.nornir_picle_shell_common import NorniHostsFilters
from .netbox_picle_shell_common import NetboxClientRunJobArgs


class SyncVlansShell(
    NetboxClientRunJobArgs,
    SyncVlansInput,
    use_enum_values=True,
    populate_by_name=True,
):
    devices: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="List of NetBox devices to collect VLANs from",
    )
    filter_by_vlan_ids: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="VLAN IDs or inclusive ranges to reconcile",
        alias="vlan-ids",
    )

    @staticmethod
    def source_FL() -> list:
        return NorniHostsFilters.source_hosts()

    @staticmethod
    def run(**kwargs: object) -> Any:
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        kwargs["timeout"] = int(timeout * 0.9)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        if nowait and kwargs.get("with_approval"):
            raise ValueError("'with-approval' cannot be combined with 'nowait'")
        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]
        if isinstance(kwargs.get("filter_by_vlan_ids"), str):
            kwargs["filter_by_vlan_ids"] = [kwargs["filter_by_vlan_ids"]]

        result = run_future_job(
            "netbox",
            "sync_vlans",
            workers=workers,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )
        if nowait:
            return result, Outputters.outputter_nested
        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
