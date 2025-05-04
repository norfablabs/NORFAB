import json

from enum import Enum
from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    StrictStr,
    Field,
)
from ..common import ClientRunJobArgs, log_error_or_result, listen_events
from typing import Union, Optional, List, Any, Dict, Callable, Tuple
from picle.models import Outputters, PipeFunctionsModel
from .nornir_picle_shell_common import NorniHostsFilters


class CreateHostModel(ClientRunJobArgs):
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "any", description="Nornir workers to target"
    )
    name: StrictStr = Field(..., description="Name of the host", required=True)
    username: StrictInt = Field(None, description="Host connections username")
    password: StrictInt = Field(None, description="Host connections password")
    platform: StrictInt = Field(
        None, description="Host platform recognized by connection plugin"
    )
    hostname: StrictStr = Field(
        None,
        description="Hostname of the host to initiate connection with, IP address or FQDN",
    )
    port: StrictInt = Field(22, description="TCP port to initiate connection with")
    connection_options: Dict = Field(
        None,
        description="JSON string with connection options",
        alias="connection-options",
    )
    groups: List[StrictStr] = Field(
        None, description="List of groups to associate with this host"
    )
    data: Dict = Field(None, description="JSON string with arbitrary host data")
    progress: Optional[StrictBool] = Field(
        True,
        description="Display progress events",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        workers = kwargs.pop("workers")
        timeout = kwargs.pop("timeout", 600)
        kwargs["action"] = "create_host"
        verbose_result = kwargs.pop("verbose_result", False)

        if kwargs.get("connection_options"):
            kwargs["connection_options"] = json.loads(kwargs["connection_options"])
        if kwargs.get("data"):
            kwargs["data"] = json.loads(kwargs["data"])
        if kwargs.get("groups") and isinstance(kwargs["groups"], str):
            kwargs["groups"] = [kwargs["groups"]]

        result = NFCLIENT.run_job(
            "nornir",
            "runtime_inventory",
            workers=workers,
            args=args,
            kwargs=kwargs,
            uuid=uuid,
            timeout=timeout,
        )

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class GroupsUpdateAction(str, Enum):
    append = "append"
    insert = "insert"
    remove = "remove"


class UpdateHostModel(ClientRunJobArgs):
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Nornir workers to target"
    )
    name: StrictStr = Field(..., description="Name of the host", required=True)
    username: StrictInt = Field(None, description="Host connections username")
    password: StrictInt = Field(None, description="Host connections password")
    platform: StrictInt = Field(
        None, description="Host platform recognized by connection plugin"
    )
    hostname: StrictStr = Field(
        None,
        description="Hostname of the host to initiate connection with, IP address or FQDN",
    )
    port: StrictInt = Field(22, description="TCP port to initiate connection with")
    connection_options: Dict = Field(
        None,
        description="JSON string with connection options",
        alias="connection-options",
    )
    groups: List[StrictStr] = Field(
        None, description="List of groups to associate with this host"
    )
    groups_action: GroupsUpdateAction = Field(
        "append", description="Action to perform with groups", alias="groups-action"
    )
    data: Dict = Field(None, description="JSON string with arbitrary host data")
    progress: Optional[StrictBool] = Field(
        True,
        description="Display progress events",
        json_schema_extra={"presence": True},
    )

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_nested

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        workers = kwargs.pop("workers")
        timeout = kwargs.pop("timeout", 600)
        kwargs["action"] = "update_host"
        verbose_result = kwargs.pop("verbose_result", False)

        if kwargs.get("connection_options"):
            kwargs["connection_options"] = json.loads(kwargs["connection_options"])
        if kwargs.get("data"):
            kwargs["data"] = json.loads(kwargs["data"])
        if kwargs.get("groups") and isinstance(kwargs["groups"], str):
            kwargs["groups"] = [kwargs["groups"]]

        result = NFCLIENT.run_job(
            "nornir",
            "runtime_inventory",
            workers=workers,
            args=args,
            kwargs=kwargs,
            uuid=uuid,
            timeout=timeout,
        )

        return log_error_or_result(result, verbose_result=verbose_result)


class DeleteHostModel(ClientRunJobArgs):
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Nornir workers to target"
    )
    name: StrictStr = Field(..., description="Name of the host", required=True)
    progress: Optional[StrictBool] = Field(
        True,
        description="Display progress events",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        workers = kwargs.pop("workers")
        timeout = kwargs.pop("timeout", 600)
        kwargs["action"] = "delete_host"
        verbose_result = kwargs.pop("verbose_result", False)

        result = NFCLIENT.run_job(
            "nornir",
            "runtime_inventory",
            workers=workers,
            args=args,
            kwargs=kwargs,
            uuid=uuid,
            timeout=timeout,
        )

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class ReadHostDataKeyModel(NorniHostsFilters, ClientRunJobArgs):
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Nornir workers to target"
    )
    keys: Union[StrictStr, List[StrictStr]] = Field(
        ...,
        description="Dot separated path within host data",
        examples="config.interfaces.Lo0",
    )
    progress: Optional[StrictBool] = Field(
        True,
        description="Display progress events",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        workers = kwargs.pop("workers")
        timeout = kwargs.pop("timeout", 600)
        kwargs["action"] = "read_host_data"
        verbose_result = kwargs.pop("verbose_result", False)

        if isinstance(kwargs["keys"], str):
            kwargs["keys"] = [kwargs["keys"]]

        result = NFCLIENT.run_job(
            "nornir",
            "runtime_inventory",
            workers=workers,
            args=args,
            kwargs=kwargs,
            uuid=uuid,
            timeout=timeout,
        )

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_json


class InventoryLoadContainerlabModel(ClientRunJobArgs):
    workers: Union[StrictStr, List[StrictStr]] = Field(
        ...,
        description="Nornir workers to load inventory into",
    )
    clab_workers: Union[StrictStr, List[StrictStr]] = Field(
        None,
        description="Containerlab workers to load inventory from",
        alias="clab-workers",
    )
    progress: Optional[StrictBool] = Field(
        True,
        description="Display progress events",
        json_schema_extra={"presence": True},
    )
    lab_name: StrictStr = Field(
        None,
        description="Name of Containerlab lab to load hosts' inventory",
        alias="lab-name",
    )
    groups: Union[StrictStr, List[StrictStr]] = Field(
        None,
        description="List of Nornir groups to associate with hosts",
    )
    use_default_credentials: StrictBool = Field(
        None,
        description="Use Containerlab default credentials for all hosts",
        alias="use-default-credentials",
    )
    dry_run: StrictBool = Field(
        None,
        description="Do not refresh Nornir, only return pulled inventory",
        json_schema_extra={"presence": True},
        alias="dry-run",
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def source_workers():
        reply = NFCLIENT.get(
            "mmi.service.broker", "show_workers", kwargs={"service": "nornir"}
        )
        workers = [i["name"] for i in reply["results"]]

        return ["all", "any"] + workers

    @staticmethod
    def source_lab_name():
        ret = []
        result = NFCLIENT.run_job("containerlab", "get_running_labs")
        for wname, wres in result.items():
            ret.extend(wres["result"])
        return ret

    @staticmethod
    def source_clab_workers():
        reply = NFCLIENT.get(
            "mmi.service.broker", "show_workers", kwargs={"service": "containerlab"}
        )
        workers = [i["name"] for i in reply["results"]]

        return ["all", "any"] + workers

    @staticmethod
    @listen_events
    def run(uuid, **kwargs):
        workers = kwargs.pop("workers")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result")

        if isinstance(kwargs.get("groups"), str):
            kwargs["groups"] = [kwargs["groups"]]

        result = NFCLIENT.run_job(
            "nornir",
            "nornir_inventory_load_containerlab",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            uuid=uuid,
        )

        return log_error_or_result(result, verbose_result=verbose_result)


class InventoryLoadModel(BaseModel):
    containerlab: InventoryLoadContainerlabModel = Field(
        None, description="Load inventory from running Containerlab lab(s)"
    )


class NornirInventoryShell(BaseModel):
    create_host: CreateHostModel = Field(
        None, description="Create new host", alias="create-host"
    )
    update_host: UpdateHostModel = Field(
        None, description="Update existing host details", alias="update-host"
    )
    delete_host: DeleteHostModel = Field(
        None, description="Delete host from inventory", alias="delete-host"
    )
    read_host_data: ReadHostDataKeyModel = Field(
        None,
        description="Return host data at given dor-separated key path",
        alias="read-host-data",
    )
    load: InventoryLoadModel = Field(
        None, description="Load inventory from external source"
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir-inventory]#"
