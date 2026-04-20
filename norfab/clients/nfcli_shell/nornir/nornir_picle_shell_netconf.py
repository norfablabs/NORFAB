import builtins
from enum import Enum

from picle.models import Outputters, PipeFunctionsModel
from pydantic import (
    BaseModel,
    Field,
    StrictStr,
)

from ..common import ClientRunJobArgs, listen_events, log_error_or_result
from .nornir_picle_shell_common import (
    NorniHostsFilters,
    NornirCommonArgs,
)


class EnumNetconfPlugins(str, Enum):
    scrapli = "scrapli"
    ncclient = "ncclient"


class EnumConfigSource(str, Enum):
    running = "running"
    candidate = "candidate"


class NrNetconfPluginNcclient(BaseModel):

    @staticmethod
    def run(*args: object, **kwargs: object):
        kwargs["plugin"] = "netmiko"
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


class CallGetConfig(NorniHostsFilters, NornirCommonArgs, ClientRunJobArgs):
    plugin: EnumNetconfPlugins = Field(
        description="NETCONF plugin to use", default="ncclient"
    )
    source: EnumConfigSource = Field(
        description="Configuration source to retrieve", default="running"
    )
    filter_subtree: StrictStr = Field(
        None,
        description="XML subtree to retrieve portion of configuration",
        alias="filter-subtree",
    )

    @staticmethod
    def run(*args: object, **kwargs: object):
        kwargs["call"] = "get_config"
        return NornirNetconfShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class CallCapabilities(NorniHostsFilters, NornirCommonArgs, ClientRunJobArgs):
    plugin: EnumNetconfPlugins = Field(
        description="NETCONF plugin to use", default="ncclient"
    )
    capab_filter: StrictStr = Field(
        None, description="Glob pattern to filter capabilities", alias="capab-filter"
    )

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
    @listen_events
    def run(uuid: str, *args: object, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = NFCLIENT.run_job(
            "nornir",
            "netconf",
            workers=workers,
            args=args,
            kwargs=kwargs,
            uuid=uuid,
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
