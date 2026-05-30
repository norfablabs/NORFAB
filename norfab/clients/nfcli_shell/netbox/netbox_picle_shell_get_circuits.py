import builtins
import logging

from picle.models import Outputters, PipeFunctionsModel
from pydantic import Field

from norfab.workers.netbox_worker.circuits_tasks import GetCircuitsInput

from ..common import listen_events, log_error_or_result
from .netbox_picle_shell_cache import CacheEnum
from .netbox_picle_shell_common import NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class GetCircuits(
    NetboxClientRunJobArgs,
    GetCircuitsInput,
    use_enum_values=True,
    populate_by_name=True,
):
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
