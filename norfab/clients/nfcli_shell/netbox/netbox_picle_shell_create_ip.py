import builtins
import json
import logging
from enum import Enum
from typing import Union

from picle.models import Outputters
from pydantic import (
    Field,
    StrictBool,
    StrictStr,
)

from norfab.workers.netbox_worker.ip_tasks import CreateIpInput

from ..common import listen_events, log_error_or_result
from .netbox_picle_shell_common import NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class IpStatusEnum(str, Enum):
    active = "active"
    reserved = "reserved"
    deprecated = "deprecated"
    dhcp = "dhcp"
    slaac = "slaac"


class CreateIp(
    CreateIpInput,
    NetboxClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    tags: Union[None, StrictStr, list[StrictStr]] = Field(
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
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested
