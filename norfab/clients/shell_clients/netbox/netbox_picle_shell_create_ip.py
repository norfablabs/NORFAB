import logging
import json
import builtins

from picle.models import Outputters
from enum import Enum
from pydantic import (
    StrictBool,
    StrictInt,
    StrictStr,
    Field,
)
from typing import Union
from ..common import log_error_or_result, listen_events
from .netbox_picle_shell_common import NetboxClientRunJobArgs
from norfab.models.netbox import NetboxCommonArgs

log = logging.getLogger(__name__)


class IpStatusEnum(str, Enum):
    active = "active"
    reserved = "reserved"
    deprecated = "deprecated"
    dhcp = "dhcp"
    slaac = "slaac"


class CreateIp(NetboxCommonArgs, NetboxClientRunJobArgs, use_enum_values=True):
    prefix: StrictStr = Field(
        ...,
        description="Prefix to allocate IP address from, can also provide prefix name or filters",
    )
    device: StrictStr = Field(
        None, description="Device name to associate IP address with"
    )
    interface: StrictStr = Field(
        None, description="Device interface name to associate IP address with"
    )
    description: StrictStr = Field(None, description="IP address description")
    vrf: StrictStr = Field(None, description="VRF to associate with IP address")
    tags: Union[StrictStr, list[StrictStr]] = Field(
        None, description="Tags to add to IP address"
    )
    dns_name: StrictStr = Field(None, description="IP address DNS name")
    tenant: StrictStr = Field(
        None, description="Tenant name to associate with IP address"
    )
    comments: StrictStr = Field(None, description="IP address comments field")
    role: StrictStr = Field(None, description="IP address functional role")
    dry_run: StrictBool = Field(
        None,
        description="Do not commit to database",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    branch: StrictStr = Field(None, description="Branching plugin branch name to use")
    mask_len: StrictInt = Field(
        None, description="Mask length to use for IP address", alias="mask-len"
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
    def run(uuid, *args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]
        if isinstance(kwargs.get("tags"), str):
            kwargs["tags"] = [kwargs["tags"]]

        if "{" in kwargs["prefix"] and "}" in kwargs["prefix"]:
            kwargs["prefix"] = json.loads(kwargs["prefix"])

        result = NFCLIENT.run_job(
            "netbox",
            "create_ip",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            uuid=uuid,
        )

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested
