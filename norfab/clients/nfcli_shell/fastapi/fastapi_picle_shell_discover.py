import logging

from picle.models import Outputters

from norfab.workers.fastapi_worker.fastapi_models import DiscoverInput

from ..common import ClientRunJobArgs, log_error_or_result, run_future_job

log = logging.getLogger(__name__)


class Discover(
    ClientRunJobArgs, DiscoverInput, use_enum_values=True, populate_by_name=True
):
    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "fastapi",
            "discover",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested
