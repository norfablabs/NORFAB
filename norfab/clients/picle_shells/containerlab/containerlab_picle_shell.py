import logging

from rich.console import Console
from picle.models import PipeFunctionsModel, Outputters
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
)
from typing import Union, Optional, List, Any, Dict, Callable, Tuple
from ..common import log_error_or_result, ClientRunJobArgs, listen_events

RICHCONSOLE = Console()
SERVICE = "containerlab"
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------------------------
# CONTAINERLAB DEPLOY COMMANDS MODELS
# ---------------------------------------------------------------------------------------------

class DeployCommand(ClientRunJobArgs):
    topology: StrictStr = Field(..., description="URL to topology file to deploy")
    reconfigure: StrictBool = Field(False, description="Destroy the lab and then re-deploy it.", json_schema_extra={"presence": True})
    progress: Optional[StrictBool] = Field(
        True,
        description="Display progress events",
        json_schema_extra={"presence": True},
    )
    
    @staticmethod
    def source_topology():
        broker_files = NFCLIENT.get(
            "fss.service.broker", "walk", kwargs={"url": "nf://"}
        )
        return broker_files["results"]
    
    @listen_events
    @staticmethod
    def run(uuid, *args, **kwargs):
        verbose_result = kwargs.pop("verbose_result")
        workers = kwargs.pop("workers", "any")
        _ = kwargs.pop("progress", None)
        
        result = NFCLIENT.run_job(
            "containerlab", "deploy", workers=workers, kwargs=kwargs, args=args, uuid=uuid,
        )

        return log_error_or_result(result, verbose_result=verbose_result, verbose_on_fail=True)
    
    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
        
# ---------------------------------------------------------------------------------------------
# CONTAINERLAB DESTROY COMMANDS MODELS
# ---------------------------------------------------------------------------------------------

class DestroyCommand(ClientRunJobArgs):
    lab_name: StrictStr = Field(None, description="Lab name to destroy", alias="lab-name")
    progress: Optional[StrictBool] = Field(
        True,
        description="Display progress events",
        json_schema_extra={"presence": True},
    )
    
    @staticmethod
    def source_lab_name():
        ret = []
        result = NFCLIENT.run_job("containerlab", "get_running_labs")
        for wname, wres in result.items():
            ret.extend(wres["result"])
        return ret
    
    @listen_events
    @staticmethod
    def run(uuid, *args, **kwargs):
        verbose_result = kwargs.pop("verbose_result")
        workers = kwargs.pop("workers", "any")
        _ = kwargs.pop("progress", None)
        
        result = NFCLIENT.run_job(
            "containerlab", "destroy", workers=workers, kwargs=kwargs, args=args, uuid=uuid,
        )

        return log_error_or_result(result, verbose_result=verbose_result, verbose_on_fail=True)
    
    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

# ---------------------------------------------------------------------------------------------
# CONTAINERLAB DESTROY COMMANDS MODELS
# ---------------------------------------------------------------------------------------------

class RestartCommand(ClientRunJobArgs):
    lab_name: StrictStr = Field(None, description="Lab name to restart", alias="lab-name")
    progress: Optional[StrictBool] = Field(
        True,
        description="Display progress events",
        json_schema_extra={"presence": True},
    )
    
    @staticmethod
    def source_lab_name():
        ret = []
        result = NFCLIENT.run_job("containerlab", "get_running_labs")
        for wname, wres in result.items():
            ret.extend(wres["result"])
        return ret
    
    @listen_events
    @staticmethod
    def run(uuid, *args, **kwargs):
        verbose_result = kwargs.pop("verbose_result")
        workers = kwargs.pop("workers", "any")
        _ = kwargs.pop("progress", None)
        
        result = NFCLIENT.run_job(
            "containerlab", "restart", workers=workers, kwargs=kwargs, args=args, uuid=uuid,
        )

        return log_error_or_result(result, verbose_result=verbose_result, verbose_on_fail=True)
    
    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
        
# ---------------------------------------------------------------------------------------------
# CONTAINERLAB SAVE COMMANDS MODELS
# ---------------------------------------------------------------------------------------------

class SaveCommand(ClientRunJobArgs):
    lab_name: StrictStr = Field(None, description="Lab name to save configurations for", alias="lab-name")
    progress: Optional[StrictBool] = Field(
        True,
        description="Display progress events",
        json_schema_extra={"presence": True},
    )
    
    @staticmethod
    def source_lab_name():
        ret = []
        result = NFCLIENT.run_job("containerlab", "get_running_labs")
        for wname, wres in result.items():
            ret.extend(wres["result"])
        return ret
    
    @listen_events
    @staticmethod
    def run(uuid, *args, **kwargs):
        verbose_result = kwargs.pop("verbose_result")
        workers = kwargs.pop("workers", "any")
        _ = kwargs.pop("progress", None)
        
        result = NFCLIENT.run_job(
            "containerlab", "save", workers=workers, kwargs=kwargs, args=args, uuid=uuid,
        )

        return log_error_or_result(result, verbose_result=verbose_result, verbose_on_fail=True)
    
    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
        
# ---------------------------------------------------------------------------------------------
# CONTAINERLAB SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------

class ShowContainers(ClientRunJobArgs):
    details: StrictBool = Field(None, description="Show container labs details", json_schema_extra={"presence": True})
    lab_name: StrictStr = Field(None, description="Show container for given lab only", alias="lab-name")
    
    @staticmethod
    def run(*args, **kwargs):
        verbose_result = kwargs.pop("verbose_result")
        workers = kwargs.pop("workers", "any")
        _ = kwargs.pop("progress", None)
        
        result = NFCLIENT.run_job(
            "containerlab", "inspect", workers=workers, kwargs=kwargs, args=args,
        )

        return log_error_or_result(result, verbose_result=verbose_result, verbose_on_fail=True)
    
    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel        

        
class ShowRunningLabs(ClientRunJobArgs):
    
    @staticmethod
    def run(*args, **kwargs):
        verbose_result = kwargs.pop("verbose_result")
        workers = kwargs.pop("workers", "any")
        _ = kwargs.pop("progress", None)
        
        result = NFCLIENT.run_job(
            "containerlab", "get_running_labs", workers=workers, kwargs=kwargs, args=args,
        )

        return log_error_or_result(result, verbose_result=verbose_result, verbose_on_fail=True)
    
    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel    

class ContainerlabShowCommandsModel(BaseModel):
    inventory: Callable = Field(
        "get_inventory",
        description="show containerlab inventory data",
        json_schema_extra={"outputter": Outputters.outputter_rich_yaml},
    )
    version: Callable = Field(
        "get_version",
        description="show containerlab service version report",
        json_schema_extra={
            "outputter": Outputters.outputter_nested,
            "initial_indent": 2,
        },
    )
    status: Callable = Field(
        "get_containerlab_status",
        description="show containerlab status",
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
    def get_inventory(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job("containerlab", "get_inventory", workers=workers)
        result = log_error_or_result(result)
        return result

    @staticmethod
    def get_version(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job("containerlab", "get_version", workers=workers)
        result = log_error_or_result(result)
        return result

    @staticmethod
    def get_containerlab_status(**kwargs):
        workers = kwargs.pop("workers", "any")
        result = NFCLIENT.run_job(
            "containerlab", "get_containerlab_status", workers=workers, kwargs=kwargs
        )
        result = log_error_or_result(result)
        return result
    
# ---------------------------------------------------------------------------------------------
# CONTAINERLAB SERVICE MAIN SHELL MODEL
# ---------------------------------------------------------------------------------------------

class ContainerlabServiceCommands(BaseModel):
    deploy: DeployCommand = Field(None, description="Spins up a lab using provided topology")
    destroy: DestroyCommand = Field(None, description="The destroy command destroys a lab referenced by its name")
    save: SaveCommand = Field(None, description="Perform configuration save for all containers running in a lab")
    restart: RestartCommand = Field(None, description="Restart lab devices")
    
    class PicleConfig:
        subshell = True
        prompt = "nf[containerlab]#"
