import logging

from rich.console import Console
from picle.models import PipeFunctionsModel, Outputters
from ..netbox.netbox_picle_shell_get_containerlab_inventory import (
    NetboxDeviceFilters,
    GetContainerlabInventoryCommand,
)
from enum import Enum
from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    StrictFloat,
    StrictStr,
    conlist,
    root_validator,
    Field,
    model_validator,
)
from typing import Union, Optional, List, Any, Dict, Tuple
from ..common import log_error_or_result, ClientRunJobArgs, listen_events

RICHCONSOLE = Console()
SERVICE = "containerlab"
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------------------------
# CONTAINERLAB DEPLOY NETBOX COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class DeployNetboxDeviceFilters(NetboxDeviceFilters):
    @staticmethod
    def run(*args, **kwargs):
        filters = {
            k: kwargs.pop(k)
            for k in [
                "tenant",
                "q",
                "model",
                "platform",
                "region",
                "role",
                "site",
                "status",
                "tag",
            ]
            if k in kwargs
        }
        # need to be a list
        kwargs["filters"] = [filters]
        return DeployNetboxCommand.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel


class DeployNetboxCommand(GetContainerlabInventoryCommand):
    lab_name: StrictStr = Field(
        None, description="Lab name to generate inventory", alias="lab-name"
    )
    reconfigure: StrictBool = Field(
        False,
        description="Destroy the lab and then re-deploy it.",
        json_schema_extra={"presence": True},
    )
    filters: DeployNetboxDeviceFilters = Field(
        None, description="Netbox device filters"
    )
    dry_run: Optional[StrictBool] = Field(
        None,
        description="Do not deploy, only fetch inventory from Netbox",
        json_schema_extra={"presence": True},
        alias="dry-run",
    )

    @staticmethod
    def source_lab_name():
        ret = []
        result = NFCLIENT.run_job("containerlab", "get_running_labs")
        for wname, wres in result.items():
            ret.extend(wres["result"])
        return ret

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        verbose_result = kwargs.pop("verbose_result")
        workers = kwargs.pop("workers", "any")

        if kwargs.get("devices"):
            if not isinstance(kwargs.get("devices"), list):
                kwargs["devices"] = [kwargs["devices"]]

        result = NFCLIENT.run_job(
            "containerlab",
            "deploy_netbox",
            workers=workers,
            kwargs=kwargs,
            args=args,
            uuid=uuid,
        )

        return log_error_or_result(
            result, verbose_result=verbose_result, verbose_on_fail=True
        )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
