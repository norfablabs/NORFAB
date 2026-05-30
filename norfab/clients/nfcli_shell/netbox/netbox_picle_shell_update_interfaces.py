import builtins
import logging
from typing import List, Union

from picle.models import Outputters, PipeFunctionsModel
from pydantic import (
    BaseModel,
    Field,
    StrictStr,
)

from norfab.workers.netbox_worker.interfaces_tasks import (
    UpdateInterfacesDescriptionInput,
)

from ..common import log_error_or_result
from .netbox_picle_shell_common import NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class UpdateInterfacesDescription(
    NetboxClientRunJobArgs,
    UpdateInterfacesDescriptionInput,
    use_enum_values=True,
    populate_by_name=True,
):
    devices: Union[StrictStr, List[StrictStr]] = Field(
        None, description="Device names to query data for"
    )

    @staticmethod
    def run(*args: object, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]

        result = NFCLIENT.run_job(
            "netbox",
            "update_interfaces_description",
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
        pipe = PipeFunctionsModel


class UpdateInterfaces(BaseModel):
    description: UpdateInterfacesDescription = Field(
        None,
        description=" Updates the description of interfaces for specified devices in NetBox",
    )
