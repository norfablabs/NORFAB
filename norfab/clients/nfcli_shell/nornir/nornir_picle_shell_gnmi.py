from picle.models import Outputters, PipeFunctionsModel
from pydantic import BaseModel, Field

from norfab.workers.nornir_worker.nornir_models import GnmiGetInput

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
        if isinstance(kwargs.get("path"), str):
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


class NornirGnmiShell(BaseModel):
    get: GnmiGetShell = Field(None, description="Retrieve configuration or state")

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir-gnmi]#"
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
