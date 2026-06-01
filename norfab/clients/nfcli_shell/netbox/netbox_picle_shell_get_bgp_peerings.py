import builtins
import logging
from typing import List, Union

from picle.models import Outputters, PipeFunctionsModel
from pydantic import (
    Field,
    StrictStr,
)

from norfab.workers.netbox_worker.netbox_models import GetBgpPeeringsInput

from ..common import listen_events, log_error_or_result
from .netbox_picle_shell_cache import CacheEnum
from .netbox_picle_shell_common import NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class GetBGPPeerings(
    NetboxClientRunJobArgs,
    GetBgpPeeringsInput,
    use_enum_values=True,
    populate_by_name=True,
):
    devices: Union[StrictStr, List[StrictStr]] = Field(
        ..., description="Device names to query data for"
    )
    cache: CacheEnum = Field(True, description="How to use cache")

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
            "get_bgp_peerings",
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
        outputter = Outputters.outputter_json
        pipe = PipeFunctionsModel
