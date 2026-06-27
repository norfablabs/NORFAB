"""
PICLE Shell Client
==================

sync-all commands for Netbox service.
"""

import logging
from typing import List, Union

from picle.models import Outputters, PipeFunctionsModel
from pydantic import Field, StrictInt, StrictStr

from norfab.workers.netbox_worker.netbox_models import SyncAllInput

from ..common import log_error_or_result, run_future_job
from ..nornir.nornir_picle_shell_common import NorniHostsFilters
from .netbox_picle_shell_common import NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class SyncAllDevicesShell(
    NetboxClientRunJobArgs,
    SyncAllInput,
    NorniHostsFilters,
    use_enum_values=True,
    populate_by_name=True,
):
    devices: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="List of NetBox devices to sync all data for",
    )
    inventory_filter_by_module: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="Glob patterns selecting normalized module type names",
        alias="inventory-filter-by-module",
    )
    inventory_filter_by_slot: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="Glob patterns selecting normalized module bay names",
        alias="inventory-filter-by-slot",
    )
    inventory_ignore_modules: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="Glob patterns excluding normalized module type names",
        alias="inventory-ignore-modules",
    )
    inventory_ignore_slots: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="Glob patterns excluding normalized module bay names",
        alias="inventory-ignore-slots",
    )
    bgp_filter_by_remote_as: Union[List[StrictInt], StrictInt] = Field(
        None,
        description="Only sync BGP sessions matching remote AS numbers",
        alias="bgp-filter-by-remote-as",
    )
    bgp_filter_by_peer_group: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="Only sync BGP sessions matching peer groups",
        alias="bgp-filter-by-peer-group",
    )
    bgp_ignore_peer_ranges: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="Prefix(es) to ignore BGP peers",
        alias="bgp-ignore-peer-ranges",
    )

    @staticmethod
    def run(**kwargs: object):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        kwargs["timeout"] = int(timeout * 0.9)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        if nowait and kwargs.get("with_review"):
            raise ValueError("'with-review' cannot be combined with 'nowait'")

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]
        if isinstance(kwargs.get("inventory_filter_by_module"), str):
            kwargs["inventory_filter_by_module"] = [
                kwargs["inventory_filter_by_module"]
            ]
        if isinstance(kwargs.get("inventory_filter_by_slot"), str):
            kwargs["inventory_filter_by_slot"] = [kwargs["inventory_filter_by_slot"]]
        if isinstance(kwargs.get("inventory_ignore_modules"), str):
            kwargs["inventory_ignore_modules"] = [kwargs["inventory_ignore_modules"]]
        if isinstance(kwargs.get("inventory_ignore_slots"), str):
            kwargs["inventory_ignore_slots"] = [kwargs["inventory_ignore_slots"]]
        if isinstance(kwargs.get("bgp_filter_by_remote_as"), int):
            kwargs["bgp_filter_by_remote_as"] = [kwargs["bgp_filter_by_remote_as"]]
        if isinstance(kwargs.get("bgp_filter_by_peer_group"), str):
            kwargs["bgp_filter_by_peer_group"] = [kwargs["bgp_filter_by_peer_group"]]
        if isinstance(kwargs.get("bgp_ignore_peer_ranges"), str):
            kwargs["bgp_ignore_peer_ranges"] = [kwargs["bgp_ignore_peer_ranges"]]

        result = run_future_job(
            "netbox",
            "sync_all",
            workers=workers,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
            outputter=Outputters.outputter_nested,
        )

        if nowait:
            return result, Outputters.outputter_nested

        result = log_error_or_result(result, verbose_result=verbose_result)

        return result

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
