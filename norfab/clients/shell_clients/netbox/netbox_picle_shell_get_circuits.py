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
from ..common import log_error_or_result
from .netbox_picle_shell_common import NetboxClientRunJobArgs
from .netbox_picle_shell_cache import CacheEnum
from norfab.models.netbox import NetboxCommonArgs

log = logging.getLogger(__name__)


class GetCircuits(NetboxCommonArgs, NetboxClientRunJobArgs):
    devices: Union[StrictStr, List[StrictStr]] = Field(
        None, description="Device names to query data for", alias="device-list"
    )
    dry_run: StrictBool = Field(
        None,
        description="Only return query content, do not run it",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    cid: Union[StrictStr, List[StrictStr]] = Field(
        None, description="List of circuit identifiers to retrieve data for"
    )
    cache: CacheEnum = Field(True, description="How to use cache")

    @staticmethod
    def run(*args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]
        if isinstance(kwargs.get("cid"), str):
            kwargs["cid"] = json.loads(kwargs["cid"])

        result = NFCLIENT.run_job(
            "netbox",
            "get_circuits",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
        )

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_json
