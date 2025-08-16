import logging
import json
import yaml

from picle.models import PipeFunctionsModel, Outputters
from enum import Enum
from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    StrictFloat,
    StrictStr,
    conlist,
    Field,
    model_validator,
)
from typing import Union, Optional, List, Any, Dict, Callable, Tuple
from ..common import ClientRunJobArgs, log_error_or_result, listen_events
from ..nornir.nornir_picle_shell import NornirCommonArgs, NorniHostsFilters
from .netbox_picle_shell_common import NetboxCommonArgs, NetboxClientRunJobArgs
from .netbox_picle_shell_cache import CacheEnum

log = logging.getLogger(__name__)


class NetboxDeviceFilters(BaseModel):
    tenant: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="Filter devices by tenants",
    )
    q: StrictStr = Field(
        None, description="Filter devices by name pattern", alias="device-name-contains"
    )
    model: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="Filter devices by models",
    )
    platform: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="Filter devices by platforms",
    )
    region: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="Filter devices by regions",
    )
    role: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="Filter devices by roles",
    )
    site: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="Filter devices by sites",
    )
    status: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="Filter devices by statuses",
    )
    tag: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="Filter devices by tags",
    )

    @staticmethod
    def run(*args, **kwargs):
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
        return GetContainerlabInventoryCommand.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_yaml
        pipe = PipeFunctionsModel


class GetContainerlabInventoryCommand(ClientRunJobArgs):
    lab_name: StrictStr = Field(
        None, description="Lab name to generate lab inventory for", alias="lab-name"
    )
    tenant: StrictStr = Field(
        None, description="Tenant name to generate lab inventory for"
    )
    filters: NetboxDeviceFilters = Field(
        None, description="Netbox device filters to generate lab inventory for"
    )
    devices: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="List of devices to generate lab inventory for",
    )
    progress: Optional[StrictBool] = Field(
        True,
        description="Display progress events",
        json_schema_extra={"presence": True},
    )
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "any", description="Filter worker to target"
    )
    instance: StrictStr = Field(
        None,
        description="Name of Netbox instance to pull inventory from",
        alias="netbox-instance",
    )
    ipv4_subnet: StrictStr = Field(
        "172.100.100.0/24",
        description="IPv4 management subnet to use for lab",
        alias="ipv4-subnet",
    )
    image: StrictStr = Field(
        None,
        description="Docker image to use for all nodes",
    )
    ports: List[StrictInt] = Field(
        [12000, 13000],
        description="Range of TCP/UDP ports to use for nodes",
    )

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        verbose_result = kwargs.pop("verbose_result")
        workers = kwargs.pop("workers", "any")

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
            "netbox",
            "get_containerlab_inventory",
            workers=workers,
            kwargs=kwargs,
            args=args,
            uuid=uuid,
        )

        return log_error_or_result(
            result, verbose_result=verbose_result, verbose_on_fail=True
        )

    class PicleConfig:
        outputter = Outputters.outputter_yaml
        pipe = PipeFunctionsModel
