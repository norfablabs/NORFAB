import builtins
import logging
from typing import List, Union

from picle.models import Outputters, PipeFunctionsModel
from pydantic import (
    Field,
    StrictBool,
    StrictStr,
)

from norfab.workers.netbox_worker.netbox_models import NetboxCommonArgs

from ..common import listen_events, log_error_or_result
from .netbox_picle_shell_cache import CacheEnum
from .netbox_picle_shell_common import NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class GetConnections(NetboxCommonArgs, NetboxClientRunJobArgs):
    devices: Union[StrictStr, List[StrictStr]] = Field(
        None, description="Device names to query data for"
    )
    dry_run: StrictBool = Field(
        None,
        description="Only return query content, do not run it",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    cache: CacheEnum = Field(True, description="How to use cache")
    interface_regex: StrictStr = Field(
        None,
        description="Regex pattern to match interfaces and ports",
        alias="interface-regex",
    )

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

        result = NFCLIENT.run_job(
            "netbox",
            "get_connections",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
            uuid=uuid,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_json
        pipe = PipeFunctionsModel
