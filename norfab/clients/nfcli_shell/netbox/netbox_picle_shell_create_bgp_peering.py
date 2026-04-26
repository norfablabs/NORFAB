import builtins
import json
import logging

from picle.models import Outputters, PipeFunctionsModel

from norfab.workers.netbox_worker.bgp_peerings_tasks import (
    CreateBgpPeeringInput,
)

from ..common import listen_events, log_error_or_result
from .netbox_picle_shell_common import NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class CreateBgpPeeringShell(NetboxClientRunJobArgs, CreateBgpPeeringInput):

    @staticmethod
    @listen_events
    def run(uuid: str, *args: object, **kwargs: object):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        # Parse JSON strings for bulk and asn_source arguments
        if isinstance(kwargs.get("bulk_create"), str):
            kwargs["bulk_create"] = json.loads(kwargs["bulk_create"])
        if isinstance(kwargs.get("asn_source"), str):
            # Try to parse as JSON dict; leave as string if it fails (dot-path str)
            try:
                kwargs["asn_source"] = json.loads(kwargs["asn_source"])
            except (json.JSONDecodeError, ValueError):
                pass
        if isinstance(kwargs.get("import_policies"), str):
            kwargs["import_policies"] = [
                p.strip() for p in kwargs["import_policies"].split(",") if p.strip()
            ]
        if isinstance(kwargs.get("export_policies"), str):
            kwargs["export_policies"] = [
                p.strip() for p in kwargs["export_policies"].split(",") if p.strip()
            ]

        result = NFCLIENT.run_job(
            "netbox",
            "create_bgp_peering",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            uuid=uuid,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
