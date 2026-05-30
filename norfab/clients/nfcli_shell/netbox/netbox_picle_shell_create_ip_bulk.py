import builtins
import json
import logging
from enum import Enum
from typing import List, Union

from picle.models import Outputters
from pydantic import (
    Field,
    StrictBool,
    StrictStr,
)

from norfab.workers.netbox_worker.ip_tasks import CreateIpBulkInput

from ..common import listen_events, log_error_or_result
from .netbox_picle_shell_common import NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class IpStatusEnum(str, Enum):
    active = "active"
    reserved = "reserved"
    deprecated = "deprecated"
    dhcp = "dhcp"
    slaac = "slaac"


class CreateIpBulk(
    CreateIpBulkInput,
    NetboxClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    devices: Union[StrictStr, List[StrictStr]] = Field(
        ..., description="List of device names to create IP address for"
    )
    interface_list: Union[None, StrictStr, List[StrictStr]] = Field(
        None,
        description="List of interface names to create IP address for",
        alias="interface-list",
    )
    tags: Union[None, StrictStr, List[StrictStr]] = Field(
        None, description="Tags to add to IP address"
    )
    create_peer_ip: StrictBool = Field(
        None,
        description="Create link peer IP address as well",
        alias="create-peer-ip",
        json_schema_extra={"presence": True},
    )
    status: IpStatusEnum = Field(None, description="IP address status")

    @staticmethod
    @listen_events
    def run(uuid: str, *args: object, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)
        print(kwargs)

        if "{" in kwargs["prefix"] and "}" in kwargs["prefix"]:
            kwargs["prefix"] = json.loads(kwargs["prefix"])
        if "[" in kwargs["interface_list"] and "]" in kwargs["interface_list"]:
            kwargs["interface_list"] = json.loads(kwargs["interface_list"])

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]
        if isinstance(kwargs.get("interface_list"), str):
            kwargs["interface_list"] = [kwargs["interface_list"]]
        if isinstance(kwargs.get("tags"), str):
            kwargs["tags"] = [kwargs["tags"]]

        result = NFCLIENT.run_job(
            "netbox",
            "create_ip_bulk",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            uuid=uuid,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested
