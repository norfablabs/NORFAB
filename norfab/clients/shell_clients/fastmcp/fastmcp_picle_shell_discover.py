import logging
import builtins

from picle.models import Outputters
from pydantic import (
    StrictBool,
    StrictStr,
    Field,
)
from ..common import ClientRunJobArgs, log_error_or_result, listen_events
from typing import Optional

log = logging.getLogger(__name__)


class Discover(ClientRunJobArgs):
    service: StrictStr = Field(
        "all", description="Service name to discover tasks and generate tools for"
    )
    progress: Optional[StrictBool] = Field(
        True,
        description="Display progress events",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)

        result = NFCLIENT.run_job(
            "fastmcp",
            "discover",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            uuid=uuid,
        )

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested
