"""NFCLI RESTCONF commands."""

from picle.models import Outputters, PipeFunctionsModel
from pydantic import BaseModel, Field

from norfab.workers.nornir_worker.nornir_models import (
    RestconfDeleteInput,
    RestconfGetInput,
    RestconfPatchInput,
    RestconfPostInput,
    RestconfPutInput,
)

from ..common import ClientRunJobArgs, log_error_or_result, run_future_job
from .nornir_picle_shell_common import NorniHostsFilters


class RestconfGetShell(
    RestconfGetInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        return NornirRestconfShell.run(*args, _task="restconf_get", **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class RestconfPutShell(
    RestconfPutInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        return NornirRestconfShell.run(*args, _task="restconf_put", **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class RestconfPostShell(
    RestconfPostInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        return NornirRestconfShell.run(*args, _task="restconf_post", **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class RestconfPatchShell(
    RestconfPatchInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        return NornirRestconfShell.run(*args, _task="restconf_patch", **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class RestconfDeleteShell(
    RestconfDeleteInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        return NornirRestconfShell.run(*args, _task="restconf_delete", **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class NornirRestconfShell(BaseModel):
    get: RestconfGetShell = Field(None, description="RESTCONF GET operation")
    post: RestconfPostShell = Field(None, description="RESTCONF POST operation")
    put: RestconfPutShell = Field(None, description="RESTCONF PUT operation")
    patch: RestconfPatchShell = Field(None, description="RESTCONF PATCH operation")
    delete: RestconfDeleteShell = Field(None, description="RESTCONF DELETE operation")

    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        task = kwargs.pop("_task")
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)
        result = run_future_job(
            "nornir",
            task,
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
        subshell = True
        prompt = "nf[nornir-restconf]#"
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
