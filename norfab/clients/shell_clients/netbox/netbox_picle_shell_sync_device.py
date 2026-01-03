import logging
import builtins

from picle.models import Outputters
from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    StrictStr,
    Field,
)
from typing import Union, Optional, List
from ..common import log_error_or_result, listen_events
from ..nornir.nornir_picle_shell_common import NornirCommonArgs, NorniHostsFilters
from .netbox_picle_shell_common import NetboxClientRunJobArgs
from norfab.models.netbox import NetboxCommonArgs

log = logging.getLogger(__name__)


class SyncDeviceFactsDatasourcesNornir(NornirCommonArgs, NorniHostsFilters):
    @staticmethod
    def run(*args, **kwargs):
        kwargs["datasource"] = "nornir"
        return SyncDeviceFactsCommand.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class UpdateDeviceFactsDatasources(BaseModel):
    nornir: SyncDeviceFactsDatasourcesNornir = Field(
        None,
        description="Use Nornir service to retrieve data from devices",
    )


class SyncDeviceFactsCommand(NetboxCommonArgs, NetboxClientRunJobArgs):
    dry_run: Optional[StrictBool] = Field(
        None,
        description="Return information that would be pushed to Netbox but do not push it",
        json_schema_extra={"presence": True},
        alias="dry-run",
    )
    devices: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="List of Netbox devices to sync",
    )
    batch_size: StrictInt = Field(
        10, description="Number of devices to process at a time", alias="batch-size"
    )
    datasource: UpdateDeviceFactsDatasources = Field(
        "nornir",
        description="Service to use to retrieve device data",
    )
    branch: StrictStr = Field(None, description="Branching plugin branch name to use")

    @staticmethod
    @listen_events
    def run(uuid, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        kwargs["timeout"] = timeout * 0.9
        verbose_result = kwargs.pop("verbose_result", False)

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]

        result = NFCLIENT.run_job(
            "netbox",
            "sync_device_facts",
            workers=workers,
            kwargs=kwargs,
            timeout=timeout,
            uuid=uuid,
        )

        result = log_error_or_result(result, verbose_result=verbose_result)

        return result

    class PicleConfig:
        outputter = Outputters.outputter_nested


class SyncDeviceInterfacesDatasourcesNornir(NornirCommonArgs, NorniHostsFilters):
    @staticmethod
    def run(*args, **kwargs):
        kwargs["datasource"] = "nornir"
        return SyncDeviceInterfacesCommand.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class SyncDeviceInterfacesDatasources(BaseModel):
    nornir: SyncDeviceInterfacesDatasourcesNornir = Field(
        None,
        description="Use Nornir service to retrieve data from devices",
    )


class SyncDeviceInterfacesCommand(NetboxCommonArgs, NetboxClientRunJobArgs):
    dry_run: Optional[StrictBool] = Field(
        None,
        description="Return information that would be pushed to Netbox but do not push it",
        json_schema_extra={"presence": True},
        alias="dry-run",
    )
    devices: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="List of Netbox devices to sync",
    )
    datasource: SyncDeviceInterfacesDatasources = Field(
        "nornir",
        description="Service to use to retrieve device data",
    )
    batch_size: StrictInt = Field(
        10, description="Number of devices to process at a time", alias="batch-size"
    )
    branch: StrictStr = Field(None, description="Branching plugin branch name to use")

    @staticmethod
    @listen_events
    def run(uuid, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        kwargs["timeout"] = timeout * 0.9
        verbose_result = kwargs.pop("verbose_result", False)

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]

        result = NFCLIENT.run_job(
            "netbox",
            "sync_device_interfaces",
            workers=workers,
            kwargs=kwargs,
            timeout=timeout,
            uuid=uuid,
        )

        result = log_error_or_result(result, verbose_result=verbose_result)

        return result

    class PicleConfig:
        outputter = Outputters.outputter_nested


class SyncDeviceIPAddressesDatasourcesNornir(NornirCommonArgs, NorniHostsFilters):
    @staticmethod
    def run(*args, **kwargs):
        kwargs["datasource"] = "nornir"
        return SyncDeviceIPAddressesCommand.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class SyncDeviceIPAddressesDatasources(BaseModel):
    nornir: SyncDeviceIPAddressesDatasourcesNornir = Field(
        None,
        description="Use Nornir service to retrieve data from devices",
    )


class SyncDeviceIPAddressesCommand(NetboxCommonArgs, NetboxClientRunJobArgs):
    dry_run: Optional[StrictBool] = Field(
        None,
        description="Return information that would be pushed to Netbox but do not push it",
        json_schema_extra={"presence": True},
        alias="dry-run",
    )
    devices: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="List of Netbox devices to sync",
    )
    datasource: SyncDeviceIPAddressesDatasources = Field(
        "nornir",
        description="Service to use to retrieve device data",
    )
    batch_size: StrictInt = Field(
        10, description="Number of devices to process at a time", alias="batch-size"
    )
    branch: StrictStr = Field(None, description="Branching plugin branch name to use")

    @staticmethod
    @listen_events
    def run(uuid, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        kwargs["timeout"] = timeout * 0.9
        verbose_result = kwargs.pop("verbose_result", False)

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]

        result = NFCLIENT.run_job(
            "netbox",
            "sync_device_ip",
            workers=workers,
            kwargs=kwargs,
            timeout=timeout,
            uuid=uuid,
        )

        result = log_error_or_result(result, verbose_result=verbose_result)

        return result

    class PicleConfig:
        outputter = Outputters.outputter_nested


class SyncDeviceCommands(BaseModel):
    facts: SyncDeviceFactsCommand = Field(
        None,
        description="Sync device facts e.g. serial number",
    )
    interfaces: SyncDeviceInterfacesCommand = Field(
        None,
        description="Sync device interfaces",
    )
    ip_addresses: SyncDeviceIPAddressesCommand = Field(
        None, description="Sync device interface IP addresses", alias="ip-addresses"
    )
