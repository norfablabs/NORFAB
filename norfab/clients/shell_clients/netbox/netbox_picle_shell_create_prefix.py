import logging
import json
import builtins

from picle.models import Outputters
from ..common import log_error_or_result, listen_events
from norfab.models.netbox import NetboxCommonArgs, CreatePrefixInput
from .netbox_picle_shell_common import NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class CreatePrefixShell(NetboxClientRunJobArgs, CreatePrefixInput):
    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)

        if isinstance(kwargs.get("tags"), str):
            kwargs["tags"] = [kwargs["tags"]]

        if "{" in kwargs["parent"] and "}" in kwargs["parent"]:
            kwargs["parent"] = json.loads(kwargs["parent"])

        result = NFCLIENT.run_job(
            "netbox",
            "create_prefix",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            uuid=uuid,
        )

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested
