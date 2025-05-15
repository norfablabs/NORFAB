import logging
import json
import yaml

from picle.models import PipeFunctionsModel, Outputters
from enum import Enum
from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    StrictFloat,
    StrictStr,
    conlist,
    Field,
)
from typing import Union, Optional, List, Any, Dict, Callable, Tuple
from ..common import ClientRunJobArgs, log_error_or_result, listen_events
from ..nornir.nornir_picle_shell import NornirCommonArgs, NorniHostsFilters
from .netbox_picle_shell_common import NetboxCommonArgs, NetboxClientRunJobArgs
from .netbox_picle_shell_cache import CacheEnum

log = logging.getLogger(__name__)


class GetConnections(NetboxClientRunJobArgs, NetboxCommonArgs):
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
    add_cables: StrictBool = Field(
        None,
        description="Add interfaces directly attached cables details",
        alias="add-cables",
    )

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]

        result = NFCLIENT.run_job(
            "netbox",
            "get_connections",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
        )

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_json
        pipe = PipeFunctionsModel
