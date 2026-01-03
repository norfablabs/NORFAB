import logging
import builtins

from picle.models import Outputters
from pydantic import (
    StrictBool,
    StrictStr,
    Field,
)
from typing import Union, Optional, List
from ..common import log_error_or_result, listen_events
from .netbox_picle_shell_common import NetboxClientRunJobArgs
from norfab.models.netbox import NetboxCommonArgs

log = logging.getLogger(__name__)


class GetInterfaces(NetboxCommonArgs, NetboxClientRunJobArgs):
    devices: Union[StrictStr, List] = Field(
        ..., description="Devices to retrieve interface for"
    )
    ip_addresses: Optional[StrictBool] = Field(
        None,
        description="Retrieves interface IP addresses",
        json_schema_extra={"presence": True},
        alias="ip-addresses",
    )
    inventory_items: Optional[StrictBool] = Field(
        None,
        description="Retrieves interface inventory items",
        json_schema_extra={"presence": True},
        alias="inventory-items",
    )
    dry_run: Optional[StrictBool] = Field(
        None,
        description="Only return query content, do not run it",
        json_schema_extra={"presence": True},
        alias="dry-run",
    )
    interface_regex: StrictStr = Field(
        None,
        description="Regex patter to match interfaces and ports",
        alias="interface-regex",
    )

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        if isinstance(kwargs["devices"], str):
            kwargs["devices"] = [kwargs["devices"]]
        result = NFCLIENT.run_job(
            "netbox",
            "get_interfaces",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            uuid=uuid,
        )
        result = log_error_or_result(result, verbose_result=verbose_result)
        return result

    class PicleConfig:
        outputter = Outputters.outputter_json
