import logging
import builtins

from picle.models import PipeFunctionsModel, Outputters
from pydantic import (
    BaseModel,
    StrictBool,
    StrictStr,
    Field,
)
from typing import Union, List
from ..common import log_error_or_result
from .netbox_picle_shell_common import NetboxClientRunJobArgs
from norfab.models.netbox import NetboxCommonArgs

log = logging.getLogger(__name__)


class UpdateInterfacesDescription(NetboxCommonArgs, NetboxClientRunJobArgs):
    devices: Union[StrictStr, List[StrictStr]] = Field(
        None, description="Device names to query data for"
    )
    description_template: StrictStr = Field(
        None,
        description="Jinja2 template to render descriptions",
        alias="description-template",
    )
    dry_run: StrictBool = Field(
        None,
        description="Only return query content, do not run it",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    interface_regex: StrictStr = Field(
        None,
        description="Regex patter to match interfaces and ports",
        alias="interface-regex",
    )

    @staticmethod
    def run(*args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]

        result = NFCLIENT.run_job(
            "netbox",
            "update_interfaces_description",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
        )

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel


class UpdateInterfaces(BaseModel):
    description: UpdateInterfacesDescription = Field(
        None,
        description=" Updates the description of interfaces for specified devices in NetBox",
    )
