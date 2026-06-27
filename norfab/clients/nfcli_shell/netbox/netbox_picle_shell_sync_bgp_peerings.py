import logging
from typing import List, Union

from picle.models import Outputters, PipeFunctionsModel
from pydantic import Field, StrictInt, StrictStr

from norfab.workers.netbox_worker.netbox_models import SyncBgpPeeringsInput

from ..common import log_error_or_result, run_future_job
from ..nornir.nornir_picle_shell_common import NorniHostsFilters
from .netbox_picle_shell_common import NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class SyncBgpPeeringsShell(
    NetboxClientRunJobArgs,
    SyncBgpPeeringsInput,
    NorniHostsFilters,
    use_enum_values=True,
    populate_by_name=True,
):
    devices: Union[None, List[str], str] = Field(
        None,
        description="List of device names to create BGP peerings for",
    )
    filter_by_remote_as: Union[None, List[StrictInt], StrictInt] = Field(
        None,
        description="Only sync sessions whose remote AS number matches one of the provided integer values",
        alias="filter-by-remote-as",
    )
    filter_by_peer_group: Union[None, List[StrictStr], StrictStr] = Field(
        None,
        description="Only sync sessions whose peer group name matches one of the provided values",
        alias="filter-by-peer-group",
    )

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 60)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        if nowait and kwargs.get("with_review"):
            raise ValueError("'with-review' cannot be combined with 'nowait'")

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]
        if isinstance(kwargs.get("filter_by_remote_as"), int):
            kwargs["filter_by_remote_as"] = [kwargs["filter_by_remote_as"]]
        if isinstance(kwargs.get("filter_by_peer_group"), str):
            kwargs["filter_by_peer_group"] = [kwargs["filter_by_peer_group"]]
        if isinstance(kwargs.get("ignore_peer_ranges"), str):
            kwargs["ignore_peer_ranges"] = [kwargs["ignore_peer_ranges"]]

        result = run_future_job(
            "netbox",
            "sync_bgp_peerings",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
