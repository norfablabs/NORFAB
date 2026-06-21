import logging
import os
from typing import Any

from picle.models import Outputters, PipeFunctionsModel
from pydantic import (
    BaseModel,
    Field,
)
from rich.console import Console

from norfab.workers.containerlab_worker.containerlab_models import (
    DeployInput,
    DestroyLabInput,
    GetNornirInventoryInput,
    GetRunningLabsInput,
    InspectInput,
    RestartLabInput,
    SaveInput,
)

from ..common import ClientRunJobArgs, log_error_or_result, run_future_job
from .containerlab_deploy_netbox import DeployNetboxCommand

RICHCONSOLE = Console()
SERVICE = "containerlab"
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------------------------
# CONTAINERLAB DEPLOY COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class DeployCommand(
    ClientRunJobArgs, DeployInput, use_enum_values=True, populate_by_name=True
):
    @staticmethod
    def source_topology(choice: str = None) -> list:
        return ClientRunJobArgs.walk_norfab_files(choice)

    @staticmethod
    def run(*args: object, **kwargs: object):
        verbose_result = kwargs.pop("verbose_result")
        workers = kwargs.pop("workers", "any")
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "containerlab",
            "deploy",
            workers=workers,
            kwargs=kwargs,
            args=args,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(
            result, verbose_result=verbose_result, verbose_on_fail=True
        )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel


# ---------------------------------------------------------------------------------------------
# CONTAINERLAB DESTROY COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class DestroyCommand(
    ClientRunJobArgs, DestroyLabInput, use_enum_values=True, populate_by_name=True
):
    @staticmethod
    def source_lab_name() -> list:
        ret = []
        result = run_future_job("containerlab", "get_running_labs")
        for wname, wres in result.items():
            ret.extend(wres["result"])
        return ret

    @staticmethod
    def run(*args: object, **kwargs: object):
        verbose_result = kwargs.pop("verbose_result")
        workers = kwargs.pop("workers", "any")
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "containerlab",
            "destroy_lab",
            workers=workers,
            kwargs=kwargs,
            args=args,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(
            result, verbose_result=verbose_result, verbose_on_fail=True
        )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel


# ---------------------------------------------------------------------------------------------
# CONTAINERLAB DESTROY COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class RestartCommand(
    ClientRunJobArgs, RestartLabInput, use_enum_values=True, populate_by_name=True
):
    @staticmethod
    def source_lab_name() -> list:
        ret = []
        result = run_future_job("containerlab", "get_running_labs")
        for wname, wres in result.items():
            ret.extend(wres["result"])
        return ret

    @staticmethod
    def run(*args: object, **kwargs: object):
        verbose_result = kwargs.pop("verbose_result")
        workers = kwargs.pop("workers", "any")
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "containerlab",
            "restart_lab",
            workers=workers,
            kwargs=kwargs,
            args=args,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(
            result, verbose_result=verbose_result, verbose_on_fail=True
        )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel


# ---------------------------------------------------------------------------------------------
# CONTAINERLAB SAVE COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class SaveCommand(
    ClientRunJobArgs, SaveInput, use_enum_values=True, populate_by_name=True
):
    @staticmethod
    def source_lab_name() -> list:
        ret = []
        result = run_future_job("containerlab", "get_running_labs")
        for wname, wres in result.items():
            ret.extend(wres["result"])
        return ret

    @staticmethod
    def run(*args: object, **kwargs: object):
        verbose_result = kwargs.pop("verbose_result")
        workers = kwargs.pop("workers", "any")
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "containerlab",
            "save",
            workers=workers,
            kwargs=kwargs,
            args=args,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(
            result, verbose_result=verbose_result, verbose_on_fail=True
        )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel


# ---------------------------------------------------------------------------------------------
# CONTAINERLAB GET NORNIR INVENTORY COMMAND MODELS
# ---------------------------------------------------------------------------------------------


class GetNornirInventoryCommand(
    ClientRunJobArgs,
    GetNornirInventoryInput,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def source_lab_name() -> list:
        ret = []
        result = run_future_job("containerlab", "get_running_labs")
        for wname, wres in result.items():
            ret.extend(wres["result"])
        return ret

    @staticmethod
    def run(*args: object, **kwargs: object):
        verbose_result = kwargs.pop("verbose_result")
        workers = kwargs.pop("workers", "any")
        nowait = kwargs.pop("nowait", False)

        # extract groups from kwargs
        groups = kwargs.pop("groups", None)
        if groups:
            if isinstance(groups, str):
                groups = [groups]
            kwargs["groups"] = groups

        result = run_future_job(
            "containerlab",
            "get_nornir_inventory",
            workers=workers,
            kwargs=kwargs,
            args=args,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(
            result, verbose_result=verbose_result, verbose_on_fail=True
        )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel


# ---------------------------------------------------------------------------------------------
# CONTAINERLAB SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class ShowContainers(
    ClientRunJobArgs, InspectInput, use_enum_values=True, populate_by_name=True
):
    @staticmethod
    def source_lab_name() -> list:
        ret = []
        result = run_future_job("containerlab", "get_running_labs")
        for wname, wres in result.items():
            ret.extend(wres["result"])
        return ret

    @staticmethod
    def run(*args: object, **kwargs: object):
        verbose_result = kwargs.pop("verbose_result")
        workers = kwargs.pop("workers", "any")
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "containerlab",
            "inspect",
            workers=workers,
            kwargs=kwargs,
            args=args,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        ret = log_error_or_result(
            result, verbose_result=verbose_result, verbose_on_fail=True
        )

        if kwargs.get("details") or verbose_result:
            return ret
        else:
            # replace labPath with topology_file
            for wname, wres in ret.items():
                for lname, containers in wres.items():
                    for c in containers:
                        c["topology_file"] = os.path.split(c.pop("labPath"))[-1]
                        _ = c.pop("absLabPath", None)
            return (ret, Outputters.outputter_nested, {"with_tables": True})

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel


class ShowRunningLabs(
    ClientRunJobArgs, GetRunningLabsInput, use_enum_values=True, populate_by_name=True
):
    @staticmethod
    def run(*args: object, **kwargs: object):
        verbose_result = kwargs.pop("verbose_result")
        workers = kwargs.pop("workers", "any")
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "containerlab",
            "get_running_labs",
            workers=workers,
            kwargs=kwargs,
            args=args,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(
            result, verbose_result=verbose_result, verbose_on_fail=True
        )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel


class ContainerlabShowCommandsModel(BaseModel):
    inventory: Any = Field(
        None,
        description="show containerlab inventory data",
        json_schema_extra={
            "outputter": Outputters.outputter_yaml,
            "function": "get_inventory",
        },
    )
    version: Any = Field(
        None,
        description="show containerlab service version report",
        json_schema_extra={
            "outputter": Outputters.outputter_nested,
            "absolute_indent": 2,
            "function": "get_version",
        },
    )
    status: Any = Field(
        None,
        description="show containerlab status",
        json_schema_extra={"function": "get_containerlab_status"},
    )
    containers: ShowContainers = Field(
        None,
        description="show containerlab containers",
    )
    labs: ShowRunningLabs = Field(
        None,
        description="show containerlab running labs",
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def get_inventory(**kwargs: object):
        workers = kwargs.pop("workers", "all")
        result = run_future_job("containerlab", "get_inventory", workers=workers)
        result = log_error_or_result(result)
        return result

    @staticmethod
    def get_version(**kwargs: object):
        workers = kwargs.pop("workers", "all")
        result = run_future_job("containerlab", "get_version", workers=workers)
        result = log_error_or_result(result)
        return result

    @staticmethod
    def get_containerlab_status(**kwargs: object):
        workers = kwargs.pop("workers", "any")
        result = run_future_job(
            "containerlab", "get_containerlab_status", workers=workers, kwargs=kwargs
        )
        result = log_error_or_result(result)
        return result


# ---------------------------------------------------------------------------------------------
# CONTAINERLAB SERVICE MAIN SHELL MODEL
# ---------------------------------------------------------------------------------------------


class ContainerlabServiceCommands(BaseModel):
    deploy: DeployCommand = Field(
        None, description="Spins up a lab using provided topology"
    )
    deploy_netbox: DeployNetboxCommand = Field(
        None,
        description="Spins up a lab using devices data from Netbox",
        alias="deploy-netbox",
    )
    destroy: DestroyCommand = Field(
        None, description="The destroy command destroys a lab referenced by its name"
    )
    save: SaveCommand = Field(
        None,
        description="Perform configuration save for all containers running in a lab",
    )
    restart: RestartCommand = Field(None, description="Restart lab devices")
    get_nornir_inventory: GetNornirInventoryCommand = Field(
        None,
        description="Get nornir inventory for a given lab",
        alias="get-nornir-inventory",
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[containerlab]#"
