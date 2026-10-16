"""Netbox interface IP movement command."""

from typing import Any

from picle.models import Outputters

from norfab.workers.netbox_worker.netbox_models import MoveIpInput

from ..common import log_error_or_result, run_future_job
from .netbox_picle_shell_common import NetboxClientRunJobArgs


class MoveIp(
    MoveIpInput, NetboxClientRunJobArgs, use_enum_values=True, populate_by_name=True
):
    @staticmethod
    def run(*args: object, **kwargs: object) -> Any:
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)
        result = run_future_job(
            "netbox",
            "move_ip",
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
        outputter = Outputters.outputter_nested
