import logging
from typing import List, Union

from picle.models import Outputters
from pydantic import (
    BaseModel,
    Field,
    StrictStr,
)

from norfab.workers.netbox_worker.netbox_models import SyncDeviceInventoryInput

from ..common import log_error_or_result, run_future_job, ClientRunJobArgs
from ..nornir.nornir_picle_shell_common import NorniHostsFilters, NornirCommonArgs
from .netbox_picle_shell_common import NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class SyncDeviceInventoryDatasourcesNornir(
    NornirCommonArgs,
    NorniHostsFilters,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object):
        return SyncDeviceInventoryShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class UpdateDeviceInventoryDatasources(BaseModel):
    nornir: SyncDeviceInventoryDatasourcesNornir = Field(
        None,
        description="Use Nornir service to retrieve data from devices",
    )


class SyncDeviceInventoryShell(
    NetboxClientRunJobArgs,
    SyncDeviceInventoryInput,
    use_enum_values=True,
    populate_by_name=True,
):
    devices: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="List of Netbox devices to sync",
    )
    filter_by_module: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="Glob patterns selecting normalized module type names",
        alias="filter-by-module",
    )
    filter_by_slot: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="Glob patterns selecting normalized module bay names",
        alias="filter-by-slot",
    )
    ignore_modules: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="Glob patterns excluding normalized module type names",
        alias="ignore-modules",
    )
    ignore_slots: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="Glob patterns excluding normalized module bay names",
        alias="ignore-slots",
    )
    datasource: UpdateDeviceInventoryDatasources = Field(
        "nornir",
        description="Service to use to retrieve device data",
    )

    @staticmethod
    def source_inventory_map(choice: str) -> list:
        completions = ClientRunJobArgs.walk_norfab_files(choice)
        return completions

    @staticmethod
    def source_inventory_transform(choice: str) -> list:
        completions = ClientRunJobArgs.walk_norfab_files(choice)
        return completions

    @staticmethod
    def run(**kwargs: object):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        if nowait and kwargs.get("with_review"):
            raise ValueError("'with-review' cannot be combined with 'nowait'")

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]
        if isinstance(kwargs.get("filter_by_module"), str):
            kwargs["filter_by_module"] = [kwargs["filter_by_module"]]
        if isinstance(kwargs.get("filter_by_slot"), str):
            kwargs["filter_by_slot"] = [kwargs["filter_by_slot"]]
        if isinstance(kwargs.get("ignore_modules"), str):
            kwargs["ignore_modules"] = [kwargs["ignore_modules"]]
        if isinstance(kwargs.get("ignore_slots"), str):
            kwargs["ignore_slots"] = [kwargs["ignore_slots"]]
        kwargs.pop("datasource", None)

        result = run_future_job(
            "netbox",
            "sync_device_inventory",
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
