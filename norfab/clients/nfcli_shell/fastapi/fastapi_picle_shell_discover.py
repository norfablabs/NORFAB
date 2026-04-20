import builtins
import logging
from typing import Optional

from picle.models import Outputters
from pydantic import (
    Field,
    StrictBool,
    StrictStr,
)

from ..common import ClientRunJobArgs, listen_events, log_error_or_result

log = logging.getLogger(__name__)


class Discover(ClientRunJobArgs):
    service: StrictStr = Field(
        "all", description="Service name to discover tasks and generate API for"
    )
    progress: Optional[StrictBool] = Field(
        True,
        description="Display progress events",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    @listen_events
    def run(uuid: str, *args: object, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = NFCLIENT.run_job(
            "fastapi",
            "discover",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            uuid=uuid,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested
