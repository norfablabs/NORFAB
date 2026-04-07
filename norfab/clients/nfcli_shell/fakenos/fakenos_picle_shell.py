import builtins
from typing import Any

from picle.models import Outputters, PipeFunctionsModel
from pydantic import (
    BaseModel,
    Field,
    StrictBool,
)

from norfab.workers.fakenos_worker.fakenos_models import (
    FakeNOSListNetworksInput,
    FakeNOSRestartInput,
    FakeNOSStartInput,
    FakeNOSStopInput,
)
from norfab.workers.fakenos_worker.nornir_inventory_tasks import GetNornirInventoryInput

from ..common import ClientRunJobArgs, listen_events, log_error_or_result

# ---------------------------------------------------------------------------------------------
# FAKENOS SERVICE SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class FakeNOSShowInventoryModel(BaseModel):
    class PicleConfig:
        outputter = Outputters.outputter_yaml

    @staticmethod
    def run(*args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = NFCLIENT.run_job(
            "fakenos",
            "get_inventory",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
        )
        if nowait:
            return result

        return log_error_or_result(result, verbose_result=verbose_result)


class FakeNOSShowNetworksCommand(FakeNOSListNetworksInput):
    details: StrictBool = Field(
        False, description="show network details", json_schema_extra={"presence": True}
    )

    class PicleConfig:
        outputter = Outputters.outputter_yaml

    @staticmethod
    def source_network():
        ret = []
        NFCLIENT = builtins.NFCLIENT
        response = NFCLIENT.run_job("fakenos", "inspect_networks")
        for wname, wres in response.items():
            ret.extend(wres["result"])
        return ret

    @staticmethod
    def run(*args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = NFCLIENT.run_job(
            "fakenos",
            "inspect_networks",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
        )
        if nowait:
            return result

        return log_error_or_result(result, verbose_result=verbose_result)


class FakeNOSShowCommands(BaseModel):
    inventory: FakeNOSShowInventoryModel = Field(
        None,
        description="show FakeNOS inventory data",
    )
    version: Any = Field(
        None,
        description="show FakeNOS service version report",
        json_schema_extra={
            "outputter": Outputters.outputter_yaml,
            "absolute_indent": 2,
            "function": "get_version",
        },
    )
    networks: FakeNOSShowNetworksCommand = Field(
        None,
        description="show FakeNOS networks details",
    )

    @staticmethod
    def get_version(**kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        nowait = kwargs.pop("nowait", False)
        result = NFCLIENT.run_job(
            "fakenos", "get_version", workers=workers, nowait=nowait
        )
        if nowait:
            return result
        return log_error_or_result(result)


# ---------------------------------------------------------------------------------------------
# FAKENOS SERVICE MAIN SHELL MODEL
# ---------------------------------------------------------------------------------------------


class FakeNOSStartCommand(ClientRunJobArgs, FakeNOSStartInput):

    class PicleConfig:
        outputter = Outputters.outputter_nested

    @staticmethod
    def source_inventory():
        return ClientRunJobArgs.walk_norfab_files()

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = NFCLIENT.run_job(
            "fakenos",
            "start",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            nowait=nowait,
            uuid=uuid,
        )
        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)


class FakeNOSStopCommand(ClientRunJobArgs, FakeNOSStopInput):

    class PicleConfig:
        outputter = Outputters.outputter_nested

    @staticmethod
    def source_network():
        ret = []
        NFCLIENT = builtins.NFCLIENT
        response = NFCLIENT.run_job("fakenos", "inspect_networks")
        for wname, wres in response.items():
            ret.extend(wres["result"])
        return ret

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = NFCLIENT.run_job(
            "fakenos",
            "stop",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            uuid=uuid,
            nowait=nowait,
        )
        if nowait:
            return result

        return log_error_or_result(result, verbose_result=verbose_result)


class FakeNOSRestartCommand(ClientRunJobArgs, FakeNOSRestartInput):

    class PicleConfig:
        outputter = Outputters.outputter_nested

    @staticmethod
    def source_network():
        ret = []
        NFCLIENT = builtins.NFCLIENT
        response = NFCLIENT.run_job("fakenos", "inspect_networks")
        for wname, wres in response.items():
            ret.extend(wres["result"])
        return ret

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = NFCLIENT.run_job(
            "fakenos",
            "restart",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            uuid=uuid,
            nowait=nowait,
        )
        if nowait:
            return result

        return log_error_or_result(result, verbose_result=verbose_result)


class GetFakeNOSNornirInventoryCommand(ClientRunJobArgs, GetNornirInventoryInput):

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def source_network():
        ret = []
        NFCLIENT = builtins.NFCLIENT
        response = NFCLIENT.run_job("fakenos", "inspect_networks")
        for wname, wres in response.items():
            ret.extend(wres["result"])
        return ret

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        # extract groups from kwargs
        groups = kwargs.pop("groups", None)
        if groups:
            if isinstance(groups, str):
                groups = [groups]
            kwargs["groups"] = groups

        result = NFCLIENT.run_job(
            "fakenos",
            "get_nornir_inventory",
            workers=workers,
            kwargs=kwargs,
            args=args,
            timeout=timeout,
            nowait=nowait,
            uuid=uuid,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(
            result, verbose_result=verbose_result, verbose_on_fail=True
        )


class FakeNOSServiceCommands(BaseModel):
    start: FakeNOSStartCommand = Field(None, description="FakeNOS start command")
    stop: FakeNOSStopCommand = Field(None, description="FakeNOS stop command")
    restart: FakeNOSRestartCommand = Field(None, description="FakeNOS restart command")
    get_nornir_inventory: GetFakeNOSNornirInventoryCommand = Field(
        None,
        description="Get Nornir inventory from FakeNOS networks",
        alias="get-nornir-inventory",
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[fakenos]#"
        pipe = PipeFunctionsModel
