import builtins
import logging
from typing import List, Union

from picle.models import Outputters, PipeFunctionsModel
from pydantic import Field, StrictStr

from norfab.workers.netbox_worker.topology_tasks import GetTopologyInput

from ..common import listen_events, log_error_or_result
from ..nornir.nornir_picle_shell_common import NorniHostsFilters
from .netbox_picle_shell_common import NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class GetTopology(GetTopologyInput, NorniHostsFilters, NetboxClientRunJobArgs):
    devices: Union[StrictStr, List[StrictStr]] = Field(
        None,
        description="List of device names to build topology for",
    )
    role: Union[StrictStr, List[StrictStr]] = Field(
        None,
        description="List of device role slugs to filter by",
    )
    platform: Union[StrictStr, List[StrictStr]] = Field(
        None,
        description="List of platform slugs to filter by",
    )
    manufacturers: Union[StrictStr, List[StrictStr]] = Field(
        None,
        description="List of manufacturer slugs to filter by",
    )
    status: Union[StrictStr, List[StrictStr]] = Field(
        None,
        description="List of device status values to filter by (e.g. 'active', 'planned')",
    )
    sites: Union[StrictStr, List[StrictStr]] = Field(
        None,
        description="List of site slugs to filter by",
    )

    @staticmethod
    @listen_events
    def run(uuid: str, *args: object, **kwargs: object) -> object:
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]
        if isinstance(kwargs.get("role"), str):
            kwargs["role"] = [kwargs["role"]]
        if isinstance(kwargs.get("platform"), str):
            kwargs["platform"] = [kwargs["platform"]]
        if isinstance(kwargs.get("manufacturers"), str):
            kwargs["manufacturers"] = [kwargs["manufacturers"]]
        if isinstance(kwargs.get("status"), str):
            kwargs["status"] = [kwargs["status"]]

        result = NFCLIENT.run_job(
            "netbox",
            "get_topology",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
            uuid=uuid,
        )

        if nowait:
            return result

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
