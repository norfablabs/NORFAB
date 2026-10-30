from typing import Any

from nornir_salt.plugins.functions import ResultSerializer
from nornir_salt.plugins.tasks import pygnmi_call

from norfab.core.worker import Job, Task
from norfab.models import Result

from .nornir_models import GnmiGetInput, GnmiResult


class GnmiTasks:
    def run_gnmi(self, job: Job, call: str, **kwargs: Any) -> Result:
        """Run a gNMI operation with standard Nornir result handling.

        Args:
            job: NorFab job metadata.
            call: Backend operation name supplied by the task.
            **kwargs: Operation, host filter, processor and serialization options.

        Returns:
            Result: Serialized per-host results, or no_match for unmatched hosts.
        """
        to_dict = kwargs.pop("to_dict", True)
        add_details = kwargs.pop("add_details", False)
        ret = Result(task=f"{self.name}:gnmi_{call}", result={} if to_dict else [])
        nr, _ = self.filter_hosts_and_validate(kwargs, ret)
        if ret.status == "no_match":
            return ret
        nr = self._add_processors(nr, kwargs, job)
        job.event(f"running gnmi {call} on {len(nr.inventory.hosts)} hosts")
        try:
            with self.connections_lock:
                result = nr.run(task=pygnmi_call, call=call, **kwargs)
                self.watchdog.connections_update(nr, "pygnmi")
            self.update_nornir_result(result, ret)
            ret.failed = result.failed
            ret.result = ResultSerializer(
                result, to_dict=to_dict, add_details=add_details
            )
            return ret
        finally:
            self.watchdog.connections_clean()

    @Task(
        input=GnmiGetInput,
        output=GnmiResult,
        fastapi={"methods": ["POST"]},
        mcp={
            "annotations": {
                "title": "gNMI Get",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def gnmi_get(
        self,
        job: Job,
        path: list[str],
        prefix: str = "",
        target: str = None,
        datatype: str = "all",
        encoding: str = None,
        **kwargs: Any,
    ) -> Result:
        """Retrieve configuration or operational state over gNMI.

        Args:
            job: NorFab job metadata.
            path: Nonempty list of YANG paths to retrieve.
            prefix: Common path prefix.
            target: Optional gNMI target name.
            datatype: Data selection: all, config, state, or operational.
            encoding: Optional encoding; defaults to backend negotiation.
            **kwargs: Common Nornir host filters, processors, retry options,
                to_dict and add_details serialization options.

        Returns:
            Result: Host results under get containing backend notification data.
                to_dict=False returns records instead. Unmatched hosts return
                no_match. Connection and RPC errors mark hosts failed. Device
                YANG models and supported encodings determine available data.
                Configure port, credentials and TLS in connection_options.pygnmi.
        """
        return self.run_gnmi(
            job,
            call="get",
            path=path,
            prefix=prefix,
            target=target,
            datatype=datatype,
            encoding=encoding,
            **kwargs,
        )
