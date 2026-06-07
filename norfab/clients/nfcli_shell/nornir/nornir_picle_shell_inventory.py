import builtins
import json
from typing import List, Union

from picle.models import Outputters, PipeFunctionsModel
from pydantic import (
    BaseModel,
    Field,
    StrictStr,
)

from norfab.workers.nornir_worker.nornir_models import (
    NornirInventoryLoadContainerlabInput,
    RuntimeCreateHostInput,
    RuntimeDeleteHostInput,
    RuntimeReadHostDataInput,
    RuntimeUpdateHostInput,
)

from ..common import ClientRunJobArgs, log_error_or_result, run_future_job
from .nornir_picle_shell_common import NorniHostsFilters


class CreateHostModel(
    RuntimeCreateHostInput,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "any", description="Nornir workers to target"
    )

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers")
        timeout = kwargs.pop("timeout", 600)
        kwargs["action"] = "create_host"
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        if kwargs.get("connection_options"):
            kwargs["connection_options"] = json.loads(kwargs["connection_options"])
        if kwargs.get("data"):
            kwargs["data"] = json.loads(kwargs["data"])
        if kwargs.get("groups") and isinstance(kwargs["groups"], str):
            kwargs["groups"] = [kwargs["groups"]]

        result = run_future_job(
            "nornir",
            "runtime_inventory",
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


class UpdateHostModel(
    RuntimeUpdateHostInput,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Nornir workers to target"
    )

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_nested

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers")
        timeout = kwargs.pop("timeout", 600)
        kwargs["action"] = "update_host"
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        if kwargs.get("connection_options"):
            kwargs["connection_options"] = json.loads(kwargs["connection_options"])
        if kwargs.get("data"):
            kwargs["data"] = json.loads(kwargs["data"])
        if kwargs.get("groups") and isinstance(kwargs["groups"], str):
            kwargs["groups"] = [kwargs["groups"]]

        result = run_future_job(
            "nornir",
            "runtime_inventory",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)


class DeleteHostModel(
    RuntimeDeleteHostInput,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Nornir workers to target"
    )

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers")
        timeout = kwargs.pop("timeout", 600)
        kwargs["action"] = "delete_host"
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "nornir",
            "runtime_inventory",
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


class ReadHostDataKeyModel(
    RuntimeReadHostDataInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Nornir workers to target"
    )

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers")
        timeout = kwargs.pop("timeout", 600)
        kwargs["action"] = "read_host_data"
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        if isinstance(kwargs["keys"], str):
            kwargs["keys"] = [kwargs["keys"]]

        result = run_future_job(
            "nornir",
            "runtime_inventory",
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


class InventoryLoadContainerlabModel(
    NornirInventoryLoadContainerlabInput,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    workers: Union[StrictStr, List[StrictStr]] = Field(
        ...,
        description="Nornir workers to load inventory into",
    )
    clab_workers: Union[StrictStr, List[StrictStr]] = Field(
        None,
        description="Containerlab workers to load inventory from",
        alias="clab-workers",
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

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def source_workers() -> list:
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.mmi(
            "mmi.service.broker", "show_workers", kwargs={"service": "nornir"}
        )
        workers = [i["name"] for i in reply["results"]]

        return ["all", "any"] + workers

    @staticmethod
    def source_lab_name() -> list:
        ret = []
        result = run_future_job("containerlab", "get_running_labs")
        for wname, wres in result.items():
            ret.extend(wres["result"])
        return ret

    @staticmethod
    def source_clab_workers() -> list:
        NFCLIENT = builtins.NFCLIENT
        reply = NFCLIENT.mmi(
            "mmi.service.broker", "show_workers", kwargs={"service": "containerlab"}
        )
        workers = [i["name"] for i in reply["results"]]

        return ["all", "any"] + workers

    @staticmethod
    def run(**kwargs: object):
        workers = kwargs.pop("workers")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result")
        nowait = kwargs.pop("nowait", False)

        if isinstance(kwargs.get("groups"), str):
            kwargs["groups"] = [kwargs["groups"]]

        result = run_future_job(
            "nornir",
            "nornir_inventory_load_containerlab",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

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
