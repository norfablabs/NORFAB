import logging

from picle.models import Outputters, PipeFunctionsModel
from pydantic import Field

from norfab.workers.netbox_worker.netbox_models import GetCircuitsInput

from ..common import log_error_or_result, run_future_job
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
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]
        if isinstance(kwargs.get("cid"), str):
            kwargs["cid"] = [kwargs["cid"]]

        result = run_future_job(
            "netbox",
            "get_circuits",
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
