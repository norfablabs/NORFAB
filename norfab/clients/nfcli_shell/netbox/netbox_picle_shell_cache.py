import builtins
import logging
from enum import Enum
from typing import List, Union

from picle.models import Outputters, PipeFunctionsModel
from pydantic import (
    BaseModel,
    Field,
    StrictStr,
)

from norfab.workers.netbox_worker.netbox_models import (
    CacheClearInput,
    CacheGetInput,
    CacheListInput,
)

from ..common import BoolEnum, log_error_or_result
from .netbox_picle_shell_common import NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class CacheEnum(Enum):
    TRUE = True
    FALSE = False
    REFRESH = "refresh"
    FORCE = "force"


class CacheList(
    NetboxClientRunJobArgs, CacheListInput, use_enum_values=True, populate_by_name=True
):
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Filter worker to target"
    )
    table: BoolEnum = Field(
        True,
        description="Print key details in table format",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    def source_workers() -> list:
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.mmi(
            "mmi.service.broker", "show_workers", kwargs={"service": "netbox"}
        )
        reply = reply["results"]
        return ["all", "any"] + [w["name"] for w in reply]

    @staticmethod
    def run(*args: object, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers")
        timeout = kwargs.pop("timeout", 600)
        details = kwargs.get("details", False)
        table = kwargs.pop("table", False)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = NFCLIENT.run_job(
            "netbox",
            "cache_list",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        result = log_error_or_result(result, verbose_result=verbose_result)

        if details:
            ret = [
                {
                    "worker": w_name,
                    "key": i["key"],
                    "age": i["age"],
                    "creation": i["creation"],
                    "expires": i["expires"],
                }
                for w_name, w_res in result.items()
                for i in w_res
            ]
            if table:
                return ret, Outputters.outputter_rich_table
            else:
                return ret, Outputters.outputter_json
        else:
            return result

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_nested


class CacheClear(
    NetboxClientRunJobArgs,
    CacheClearInput,
    use_enum_values=True,
    populate_by_name=True,
):
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Filter worker to target"
    )

    @staticmethod
    def source_workers() -> list:
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.mmi(
            "mmi.service.broker", "show_workers", kwargs={"service": "netbox"}
        )
        reply = reply["results"]
        return ["all", "any"] + [w["name"] for w in reply]

    @staticmethod
    def run(*args: object, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = NFCLIENT.run_job(
            "netbox",
            "cache_clear",
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


class CacheGet(
    NetboxClientRunJobArgs, CacheGetInput, use_enum_values=True, populate_by_name=True
):
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Filter worker to target"
    )

    @staticmethod
    def source_workers() -> list:
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.mmi(
            "mmi.service.broker", "show_workers", kwargs={"service": "netbox"}
        )
        reply = reply["results"]
        return ["all", "any"] + [w["name"] for w in reply]

    @staticmethod
    def run(*args: object, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = NFCLIENT.run_job(
            "netbox",
            "cache_get",
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


class NetboxServiceCache(BaseModel):
    list_: CacheList = Field(None, description="List cache keys", alias="list")
    clear: CacheClear = Field(None, description="Clear cache data")
    get: CacheGet = Field(None, description="Get cache data")
