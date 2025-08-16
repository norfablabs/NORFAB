import logging

from picle.models import PipeFunctionsModel, Outputters
from enum import Enum
from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    StrictFloat,
    StrictStr,
    Field,
)
from ..common import ClientRunJobArgs, log_error_or_result, listen_events
from typing import Union, Optional, List, Any, Dict, Tuple
from .fastapi_picle_shell_auth import FastAPIAuthCommandsModel
from .fastapi_picle_shell_discover import Discover

SERVICE = "fastapi"
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# FASTAPI SERVICE SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class FastAPIShowOpenAPISchema(ClientRunJobArgs):
    paths: StrictBool = Field(
        None,
        description="show FastAPI app paths only",
        json_schema_extra={"presence": True},
    )

    class PicleConfig:
        outputter = Outputters.outputter_json
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)

        result = NFCLIENT.run_job(
            "fastapi",
            "get_openapi_schema",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
        )
        return log_error_or_result(result, verbose_result=verbose_result)


class FastAPIShowInventoryModel(ClientRunJobArgs):
    class PicleConfig:
        outputter = Outputters.outputter_yaml
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)

        result = NFCLIENT.run_job(
            "fastapi",
            "get_inventory",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
        )
        return log_error_or_result(result, verbose_result=verbose_result)


class FastAPIShowCommandsModel(BaseModel):
    inventory: FastAPIShowInventoryModel = Field(
        None,
        description="show FastAPI inventory data",
    )
    version: Any = Field(
        None,
        description="show FastAPI service version report",
        json_schema_extra={
            "outputter": Outputters.outputter_yaml,
            "absolute_indent": 2,
            "function": "get_version",
        },
    )
    openapi_schema: FastAPIShowOpenAPISchema = Field(
        None, description="show FastAPI OpenAPI schema", alias="openapi-schema"
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def get_version(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job("fastapi", "get_version", workers=workers)
        return log_error_or_result(result)


# ---------------------------------------------------------------------------------------------
# FASTAPI SERVICE MAIN SHELL MODEL
# ---------------------------------------------------------------------------------------------


class FastAPIServiceCommands(BaseModel):
    auth: FastAPIAuthCommandsModel = Field(None, description="Manage auth tokens")
    discover: Discover = Field(
        None, description="Discover NorFab services tasks and create API"
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[fastapi]#"
