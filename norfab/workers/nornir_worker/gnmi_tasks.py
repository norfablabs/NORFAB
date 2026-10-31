from typing import Any

import yaml
from nornir_salt.plugins.functions import ResultSerializer
from nornir_salt.plugins.tasks import pygnmi_call
from pydantic import TypeAdapter

from norfab.core.worker import Job, Task
from norfab.models import Result

from .nornir_models import (
    GnmiCapabilitiesInput,
    GnmiDeleteInput,
    GnmiGetInput,
    GnmiResult,
    GnmiSetInput,
)

GNMI_GETTERS = {
    "openconfig_system": "openconfig:/system",
    "openconfig_interfaces": "openconfig:/interfaces",
    "openconfig_lldp": "openconfig:/lldp",
    "openconfig_platform": "openconfig:/components",
}


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
        input_model = {
            "get": GnmiGetInput,
            "set": GnmiSetInput,
            "delete": GnmiDeleteInput,
        }.get(call)
        loaded = False
        for argument in ("path", "update", "replace", "delete"):
            value = kwargs.get(argument)
            if isinstance(value, str) and value.startswith("nf://"):
                content = self.fetch_file(value, raise_on_fail=True)
                # Files contain lists; validate operation contents below.
                kwargs[argument] = TypeAdapter(list).validate_python(
                    yaml.safe_load(content)
                )
                loaded = True
        if loaded:
            validation_data = {
                key: value for key, value in kwargs.items() if value is not None
            }
            if call == "delete":
                validation_data["path"] = validation_data.pop("delete")
            input_model.model_validate(validation_data)
        if call == "get":
            kwargs["path"] = list(kwargs.get("path") or [])
            for getter, path in GNMI_GETTERS.items():
                if kwargs.pop(getter, False):
                    kwargs["path"].append(path)
        nr = self._add_processors(nr, kwargs, job)
        job.event(f"running gnmi {call} on {len(nr.inventory.hosts)} hosts")
        try:
            with self.connections_lock:
                result = nr.run(
                    task=pygnmi_call, call="set" if call == "delete" else call, **kwargs
                )
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
        path: list[str] | str = None,
        prefix: str = "",
        target: str = None,
        datatype: str = "all",
        encoding: str = None,
        openconfig_system: bool = False,
        openconfig_interfaces: bool = False,
        openconfig_lldp: bool = False,
        openconfig_platform: bool = False,
        **kwargs: Any,
    ) -> Result:
        """Retrieve configuration or operational state over gNMI.

        Args:
            job: NorFab job metadata.
            path: YANG paths or nf:// JSON/YAML list; requires paths or a getter.
            prefix: Common path prefix.
            target: Optional gNMI target name.
            datatype: Data selection: all, config, state, or operational.
            encoding: Optional encoding, defaults to backend negotiation.
            openconfig_system: Retrieve openconfig:/system.
            openconfig_interfaces: Retrieve openconfig:/interfaces.
            openconfig_lldp: Retrieve openconfig:/lldp.
            openconfig_platform: Retrieve openconfig:/components.
            **kwargs: Common Nornir host filters, processors, retry options,
                to_dict and add_details serialization options.

        Returns:
            Result: Host results under get containing backend notification data.
                to_dict=False returns records instead. Unmatched hosts return
                no_match. Connection and RPC errors mark hosts failed. Device
                YANG models and supported encodings determine available data.
                Configure port, credentials and TLS in connection_options.pygnmi.

        Raises:
            FileNotFoundError: If a referenced file cannot be fetched.
            yaml.YAMLError: If a file contains malformed YAML/JSON.
            pydantic.ValidationError: If file contents have an invalid payload shape.
        """
        return self.run_gnmi(
            job,
            call="get",
            path=path,
            prefix=prefix,
            target=target,
            openconfig_system=openconfig_system,
            openconfig_interfaces=openconfig_interfaces,
            openconfig_lldp=openconfig_lldp,
            openconfig_platform=openconfig_platform,
            datatype=datatype,
            encoding=encoding,
            **kwargs,
        )

    @Task(
        input=GnmiSetInput,
        output=GnmiResult,
        fastapi={"methods": ["POST"]},
        mcp={
            "annotations": {
                "title": "gNMI Set",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": False,
                "openWorldHint": True,
            }
        },
    )
    def gnmi_set(
        self,
        job: Job,
        update: list[tuple[str, dict]] | str = None,
        replace: list[tuple[str, dict]] | str = None,
        delete: list[str] | str = None,
        prefix: str = "",
        target: str = None,
        encoding: str = None,
        **kwargs: Any,
    ) -> Result:
        """Merge, replace, or delete device configuration using one Set request.

        Args:
            job: NorFab job metadata.
            update: Path/JSON-object pairs or nf:// JSON/YAML list to merge.
            replace: Path/JSON-object pairs or nf:// JSON/YAML list to replace subtrees.
            delete: Paths or nf:// JSON/YAML list to remove. At least one nonempty operation
                list is required across update, replace, and delete.
            prefix: Common path prefix for all operations.
            target: Optional gNMI target name.
            encoding: Payload encoding; defaults to backend negotiation.
            **kwargs: Common Nornir host filters, structured processors, retries,
                to_dict and add_details serialization options.

        Returns:
            Result: Per-host Set replies under set, or serialized records when
                to_dict=False. Unmatched hosts return no_match; connection and
                RPC errors mark hosts failed. Device models determine supported
                operations. Writes take effect according to device behavior;
                no backup, rollback, or cross-host transaction is provided.
                Retries may repeat applied writes after an uncertain timeout.
                Only JSON object payloads are accepted; scalar writes, templates,
                and protobuf extensions are not exposed.

        Raises:
            FileNotFoundError: If a referenced file cannot be fetched.
            yaml.YAMLError: If a file contains malformed YAML/JSON.
            pydantic.ValidationError: If file contents have an invalid payload shape.
        """
        return self.run_gnmi(
            job,
            call="set",
            update=update,
            replace=replace,
            delete=delete,
            prefix=prefix,
            target=target,
            encoding=encoding,
            **kwargs,
        )

    @Task(
        input=GnmiDeleteInput,
        output=GnmiResult,
        fastapi={"methods": ["POST"]},
        mcp={
            "annotations": {
                "title": "gNMI Delete",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": False,
                "openWorldHint": True,
            }
        },
    )
    def gnmi_delete(
        self,
        job: Job,
        path: list[str] | str,
        prefix: str = "",
        target: str = None,
        **kwargs: Any,
    ) -> Result:
        """Delete configuration paths using a gNMI Set request.

        Args:
            job: NorFab job metadata.
            path: Nonempty path list or nf:// JSON/YAML list of paths to remove.
            prefix: Common YANG path prefix.
            target: Optional gNMI target name.
            **kwargs: Common Nornir host filters, structured processors, retries,
                to_dict and add_details serialization options.

        Returns:
            Result: Backend Set replies under set, or serialized records when
                to_dict=False. The NorFab task is labelled gnmi_delete.
                Unmatched hosts return no_match; RPC and connection errors mark
                hosts failed. No backup or rollback is performed. Supported paths
                and repeated-delete behavior depend on the device. A timeout can
                leave the outcome uncertain; retries may repeat an applied delete.

        Raises:
            FileNotFoundError: If a referenced file cannot be fetched.
            yaml.YAMLError: If a file contains malformed YAML/JSON.
            pydantic.ValidationError: If file contents have an invalid payload shape.
        """
        return self.run_gnmi(
            job, call="delete", delete=path, prefix=prefix, target=target, **kwargs
        )

    @Task(
        input=GnmiCapabilitiesInput,
        output=GnmiResult,
        fastapi={"methods": ["POST"]},
        mcp={
            "annotations": {
                "title": "gNMI Capabilities",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def gnmi_get_capabilities(self, job: Job, **kwargs: Any) -> Result:
        """Retrieve advertised gNMI models, encodings, and protocol version.

        Args:
            job: NorFab job metadata.
            **kwargs: Common Nornir host filters, structured processors, retries,
                to_dict and add_details serialization options.

        Returns:
            Result: Per-host replies under capabilities containing supported_models,
                supported_encodings, and gnmi_version when advertised by the device.
                to_dict=False returns serialized records. Unmatched hosts return
                no_match; connection and RPC errors mark hosts failed. Advertised
                models and encodings do not guarantee support for every path or
                operation. Model metadata does not include YANG schema contents.
        """
        return self.run_gnmi(job, call="capabilities", **kwargs)
