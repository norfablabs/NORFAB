from picle.models import Outputters, PipeFunctionsModel
from pydantic import BaseModel, Field

from norfab.workers.nornir_worker.nornir_models import (
    NetconfCapabilitiesInput,
    NetconfGetConfigInput,
)

from ..common import ClientRunJobArgs, log_error_or_result, run_future_job
from .nornir_picle_shell_common import NorniHostsFilters


class NrNetconfPluginNcclient(BaseModel):

    @staticmethod
    def run(*args: object, **kwargs: object):
        kwargs["plugin"] = "ncclient"
        return NornirNetconfShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class NrNetconfPluginScrapli(BaseModel):

    @staticmethod
    def run(*args: object, **kwargs: object):
        kwargs["plugin"] = "scrapli"
        return NornirNetconfShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class NrNetconfPlugins(BaseModel):
    ncclient: NrNetconfPluginNcclient = Field(None, description="Use Ncclient plugin")
    scrapli: NrNetconfPluginScrapli = Field(
        None, description="Use Scrapli-Netconf plugin"
    )


class CallGetConfig(
    NetconfGetConfigInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object):
        kwargs["call"] = "get_config"
        return NornirNetconfShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class CallCapabilities(
    NetconfCapabilitiesInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object):
        kwargs["call"] = "server_capabilities"
        return NornirNetconfShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class NornirNetconfShell(BaseModel):
    capabilities: CallCapabilities = Field(
        None, description="Display NETCONF capabilities supported by devices"
    )
    get_config: CallGetConfig = Field(
        None,
        description="Get configuration",
        alias="get-config",
    )

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "nornir",
            "netconf",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        ret = log_error_or_result(result, verbose_result=verbose_result)

        return ret

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir-netconf]#"
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
