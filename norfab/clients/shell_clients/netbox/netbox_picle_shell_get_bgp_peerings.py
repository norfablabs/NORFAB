import logging
import json
import builtins

from picle.models import Outputters
from pydantic import (
    StrictBool,
    StrictStr,
    Field,
)
from typing import Union, List
from ..common import log_error_or_result, listen_events
from .netbox_picle_shell_common import NetboxClientRunJobArgs
from .netbox_picle_shell_cache import CacheEnum
from norfab.models.netbox import NetboxCommonArgs

log = logging.getLogger(__name__)


class GetBGPPeerings(NetboxCommonArgs, NetboxClientRunJobArgs):
    devices: Union[StrictStr, List[StrictStr]] = Field(
        ..., description="Device names to query data for"
    )
    dry_run: StrictBool = Field(
        None,
        description="Only return query content, do not run it",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    cache: CacheEnum = Field(True, description="How to use cache")

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]
        if isinstance(kwargs.get("filters"), str):
            kwargs["filters"] = json.loads(kwargs["filters"])

        result = NFCLIENT.run_job(
            "netbox",
            "get_bgp_peerings",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            uuid=uuid,
        )

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_json
