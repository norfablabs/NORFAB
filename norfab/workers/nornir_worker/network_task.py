from enum import Enum
from typing import Any, Union

from pydantic import Field, StrictBool, StrictInt, StrictStr

from norfab.core.worker import Job, Task
from norfab.models import Result

from .nornir_models import NornirCommonArgs, NornirSerializedResult

# --------------------------------------------------------------------------
# NETWORK TASK MODELS
# --------------------------------------------------------------------------


class NetworkFunction(str, Enum):
    ping = "ping"
    resolve_dns = "resolve_dns"


class NetworkInput(
    NornirCommonArgs, extra="allow", use_enum_values=True, populate_by_name=True
):
    fun: Union[NetworkFunction, StrictStr] = Field(
        ...,
        description="Nornir-Salt network utility function to call",
    )


class NetworkPingInput(
    NetworkInput, extra="allow", use_enum_values=True, populate_by_name=True
):
    fun: NetworkFunction = Field(
        NetworkFunction.ping,
        description="Nornir-Salt network utility function to call",
    )
    use_host_name: StrictBool = Field(
        None,
        description="Ping host's name instead of host's hostname",
        json_schema_extra={"presence": True},
        alias="use-host-name",
    )
    count: StrictInt = Field(None, description="Number of pings to run")
    ping_timeout: StrictInt = Field(
        None,
        description="Time in seconds before considering each non-arrived reply permanently lost",
        alias="ping-timeout",
    )
    size: StrictInt = Field(None, description="Size of the entire packet to send")
    interval: Union[int, float] = Field(
        None, description="Interval to wait between pings"
    )
    payload: str = Field(None, description="Payload content if size is not set")
    sweep_start: StrictInt = Field(
        None,
        description="If size is not set, initial size in a sweep of sizes",
        alias="sweep-start",
    )
    sweep_end: StrictInt = Field(
        None,
        description="If size is not set, final size in a sweep of sizes",
        alias="sweep-end",
    )
    df: StrictBool = Field(
        None,
        description="Don't Fragment flag value for IP Header",
        json_schema_extra={"presence": True},
    )
    match: StrictBool = Field(
        None,
        description="Do payload matching between request and reply",
        json_schema_extra={"presence": True},
    )
    source: StrictStr = Field(None, description="Source IP address")


class NetworkDnsInput(
    NetworkInput, extra="allow", use_enum_values=True, populate_by_name=True
):
    fun: NetworkFunction = Field(
        NetworkFunction.resolve_dns,
        description="Nornir-Salt network utility function to call",
    )
    use_host_name: StrictBool = Field(
        None,
        description="Ping host's name instead of host's hostname",
        json_schema_extra={"presence": True},
        alias="use-host-name",
    )
    servers: Union[StrictStr, list[StrictStr]] = Field(
        None, description="List of DNS servers to use"
    )
    dns_timeout: StrictInt = Field(
        None,
        description="Time in seconds before considering request lost",
        alias="dns-timeout",
    )
    ipv4: StrictBool = Field(
        None, description="Resolve 'A' record", json_schema_extra={"presence": True}
    )
    ipv6: StrictBool = Field(
        None, description="Resolve 'AAAA' record", json_schema_extra={"presence": True}
    )


class NetworkResult(NornirSerializedResult):
    result: Union[dict[StrictStr, Any], list[Any]] = Field(
        {},
        description="Network utility results keyed by host or returned as serialized task records",
    )


class NetworkTask:
    @Task(fastapi={"methods": ["POST"]}, input=NetworkInput, output=NetworkResult)
    def network(self, job: Job, fun: str, **kwargs: object) -> Result:
        """
        Task to call various network-related utility functions.

        Args:
            job: NorFab Job object containing relevant metadata
            fun (str): The name of the utility function to call.
            kwargs (dict): Arguments to pass to the utility function.

        Available utility functions:

        - **resolve_dns** Resolves hosts' hostname DNS, returning IP addresses using
            `nornir_salt.plugins.tasks.network.resolve_dns` Nornir-Salt function.
        - **ping** Executes ICMP ping to host using `nornir_salt.plugins.tasks.network.ping`
            Nornir-Salt function.

        Returns:
            dict: A dictionary containing the results of the network utility function.

        Raises:
            UnsupportedPluginError: If the specified utility function is not supported.
        """
        kwargs["call"] = fun
        return self.task(
            job=job,
            plugin="nornir_salt.plugins.tasks.network",
            **kwargs,
        )
