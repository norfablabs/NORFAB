import logging
import builtins

from picle.models import Outputters, PipeFunctionsModel
from pydantic import (
    StrictBool,
    StrictStr,
    Field,
)
from typing import Union, List
from ..common import log_error_or_result, listen_events
from .netbox_picle_shell_common import NetboxClientRunJobArgs
from .netbox_picle_shell_cache import CacheEnum
from norfab.workers.netbox_worker.netbox_models import NetboxCommonArgs

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
    @listen_events
    def run(uuid, *args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]
        if isinstance(kwargs.get("cid"), str):
            kwargs["cid"] = [kwargs["cid"]]

        result = NFCLIENT.run_job(
            "netbox",
            "get_circuits",
            uuid=uuid,
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_json
        pipe = PipeFunctionsModel
