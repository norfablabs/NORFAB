import json

from picle.models import Outputters, PipeFunctionsModel
from pydantic import BaseModel, Field

from norfab.workers.nornir_worker.nornir_models import (
    GnmiCapabilitiesInput,
    GnmiDeleteInput,
    GnmiGetInput,
    GnmiSetInput,
)

from ..common import ClientRunJobArgs, log_error_or_result, run_future_job
from .nornir_picle_shell_common import NorniHostsFilters


class GnmiGetShell(GnmiGetInput, NorniHostsFilters, ClientRunJobArgs):
    path: str | list[str] = Field(
        [], description="YANG path or list of paths to retrieve"
    )

    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)
        if isinstance(kwargs.get("path"), str) and not kwargs["path"].startswith(
            "nf://"
        ):
            kwargs["path"] = [kwargs["path"]]
        result = run_future_job(
            "nornir",
            "gnmi_get",
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


class GnmiSetShell(GnmiSetInput, NorniHostsFilters, ClientRunJobArgs):
    update: str = Field("", description="JSON array of path/object pairs to merge")
    replace: str = Field("", description="JSON array of path/object pairs to replace")
    delete: str | list[str] = Field(
        [], description="Configuration path or paths to delete"
    )

    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)
        for operation in ("update", "replace"):
            value = kwargs.pop(operation, "")
            kwargs[operation] = (
                value if value.startswith("nf://") else json.loads(value or "[]")
            )
        if isinstance(kwargs.get("delete"), str) and not kwargs["delete"].startswith(
            "nf://"
        ):
            kwargs["delete"] = [kwargs["delete"]]
        result = run_future_job(
            "nornir",
            "gnmi_set",
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


class GnmiDeleteShell(GnmiDeleteInput, NorniHostsFilters, ClientRunJobArgs):
    path: str | list[str] = Field(
        ..., description="Configuration path or paths to delete"
    )

    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)
        if isinstance(kwargs.get("path"), str) and not kwargs["path"].startswith(
            "nf://"
        ):
            kwargs["path"] = [kwargs["path"]]
        result = run_future_job(
            "nornir",
            "gnmi_delete",
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


class GnmiCapabilitiesShell(GnmiCapabilitiesInput, NorniHostsFilters, ClientRunJobArgs):
    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)
        result = run_future_job(
            "nornir",
            "gnmi_get_capabilities",
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


class NornirGnmiShell(BaseModel):
    get_capabilities: GnmiCapabilitiesShell = Field(
        None,
        alias="get-capabilities",
        description="Discover gNMI models, encodings, and version",
    )
    delete: GnmiDeleteShell = Field(None, description="Delete configuration paths")
    set: GnmiSetShell = Field(
        None, description="Merge, replace, or delete configuration"
    )
    get: GnmiGetShell = Field(None, description="Retrieve configuration or state")

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir-gnmi]#"
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
