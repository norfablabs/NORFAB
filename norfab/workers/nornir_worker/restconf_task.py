"""RESTCONF device operations using the inventory HTTP connection."""

import logging
from typing import Any

from nornir_salt.plugins.functions import ResultSerializer
from nornir_salt.plugins.tasks import http_call

from norfab.core.worker import Job, Task
from norfab.models import Result

from .nornir_models import (
    NornirSerializedResult,
    RestconfDeleteInput,
    RestconfGetInput,
    RestconfPatchInput,
    RestconfPostInput,
    RestconfPutInput,
)

log = logging.getLogger(__name__)

RESTCONF_GETTERS = {
    "openconfig_interfaces": "openconfig-interfaces:interfaces",
    "openconfig_lldp": "openconfig-lldp:lldp",
    "openconfig_system": "openconfig-system:system",
}


class RestconfTask:
    def _run_restconf(
        self,
        job: Job,
        method: str,
        url: str = None,
        params: dict[str, Any] = None,
        headers: dict[str, str] = None,
        data: str = None,
        job_data: Any = None,
        **kwargs: Any,
    ) -> Result:
        """Run a RESTCONF operation using the configured Nornir runner.

        Args:
            job: NorFab job metadata.
            method: Fixed HTTP operation selected by the public task.
            url: Literal relative resource or absolute HTTP(S) URL.
            params: HTTP query parameters.
            headers: HTTP headers replacing inventory headers when supplied.
            data: Raw text payload or inline/nf:// template.
            job_data: Template context or YAML data URL.
            **kwargs: Host filters, processors, serialization and request options.

        Returns:
            Result: Serialized host replies or failures; no_match for empty scope.

        Raises:
            FileNotFoundError: If a payload template cannot be downloaded.
            ValueError: If the removed json argument is supplied.
        """
        if "json" in kwargs or "json_" in kwargs:
            raise ValueError("use data for RESTCONF payloads")
        to_dict = kwargs.pop("to_dict", True)
        add_details = kwargs.pop("add_details", False)
        on_failed = kwargs.pop("on_failed", False)
        ret = Result(
            task=f"{self.name}:restconf_{method}", result={} if to_dict else []
        )
        nr, _ = self.filter_hosts_and_validate(kwargs, ret)
        if ret.status == "no_match":
            return ret
        nr = self._add_processors(nr, kwargs, job)
        kwargs = {key: value for key, value in kwargs.items() if value is not None}
        if params is not None:
            kwargs["params"] = params
        if headers is not None:
            kwargs["headers"] = headers
        template_cache = {}
        with self.connections_lock:
            try:
                if data is not None:
                    context_data = self.load_job_data(job_data)
                    filters = self.add_jinja2_filters()
                    netbox = self.add_jinja2_netbox()
                    for host in nr.inventory.hosts.values():
                        host.data["__task__"] = {
                            "data": self.jinja2_render_templates(
                                templates=[data],
                                context={
                                    "host": host,
                                    "job_data": context_data,
                                    "norfab": self.client,
                                    "netbox": netbox,
                                },
                                filters=filters,
                                template_cache=template_cache,
                            )
                        }
                message = (
                    f"running restconf {method} on {len(nr.inventory.hosts)} hosts"
                )
                log.info(message)
                job.event(message)
                result = nr.run(
                    task=http_call,
                    method=method,
                    url=url,
                    on_failed=on_failed,
                    **kwargs,
                )
                self.watchdog.connections_update(nr, "http")
                self.update_nornir_result(result, ret)
                ret.failed = result.failed
                ret.result = ResultSerializer(
                    result, to_dict=to_dict, add_details=add_details
                )
                job.event(
                    f"completed restconf {method}",
                    severity="WARNING" if ret.failed else "INFO",
                )
                return ret
            finally:
                for host in nr.inventory.hosts.values():
                    host.data.pop("__task__", None)
                self.watchdog.connections_clean()

    @Task(
        input=RestconfGetInput,
        output=NornirSerializedResult,
        fastapi={"methods": ["POST"]},
        mcp={
            "annotations": {
                "title": "RESTCONF Get",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def restconf_get(
        self,
        job: Job,
        url: str = None,
        params: dict[str, Any] = None,
        headers: dict[str, str] = None,
        openconfig_interfaces: bool = False,
        openconfig_lldp: bool = False,
        openconfig_system: bool = False,
        **kwargs: Any,
    ) -> Result:
        """Read a RESTCONF resource.

        Args:
            job: NorFab job metadata.
            url: Literal resource relative to inventory base_url, or absolute URL.
            params: HTTP query parameters.
            headers: HTTP headers replacing inventory headers when supplied.
            openconfig_interfaces: Retrieve OpenConfig interfaces configuration and
                state. Defaults to false. Select only one getter or url. Requires
                device support for the OpenConfig interfaces model.
            openconfig_lldp: Retrieve the OpenConfig LLDP subtree. Defaults to false.
                Requires device model support. Select only one getter or url.
            openconfig_system: Retrieve the OpenConfig system subtree. Defaults to false.
                Requires device model support. Select only one getter or url.
            **kwargs: Common Nornir host filters, processors, runner and result options.

        Returns:
            Result: Per-host response payloads keyed by the HTTP verb, or list records.
                HTTP failures remain failed host results; no_match means no selected hosts.
        """
        for getter, selected in {
            "openconfig_interfaces": openconfig_interfaces,
            "openconfig_lldp": openconfig_lldp,
            "openconfig_system": openconfig_system,
        }.items():
            if selected:
                url = RESTCONF_GETTERS[getter]
        return self._run_restconf(
            job, "get", url=url, params=params, headers=headers, **kwargs
        )

    @Task(
        input=RestconfPutInput,
        output=NornirSerializedResult,
        fastapi={"methods": ["POST"]},
        mcp={
            "annotations": {
                "title": "RESTCONF Put",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def restconf_put(
        self,
        job: Job,
        url: str = None,
        params: dict[str, Any] = None,
        headers: dict[str, str] = None,
        data: str = None,
        job_data: Any = None,
        **kwargs: Any,
    ) -> Result:
        """Replace a RESTCONF resource.

        Args:
            job: NorFab job metadata.
            url: Literal resource relative to inventory base_url, or absolute URL.
            params: HTTP query parameters.
            headers: HTTP headers replacing inventory headers when supplied.
            data: Request body text or inline/nf:// Jinja2 template.
            job_data: Template context data or URL to a YAML data file.
            **kwargs: Common Nornir host filters, processors, runner and result options.

        Returns:
            Result: Per-host response payloads keyed by the HTTP verb, or list records.
                HTTP failures remain failed host results; no_match means no selected hosts.

        Raises:
            FileNotFoundError: If a template cannot be downloaded.
            ValueError: If the removed json argument is supplied.
        """
        return self._run_restconf(
            job,
            "put",
            url=url,
            params=params,
            headers=headers,
            data=data,
            job_data=job_data,
            **kwargs,
        )

    @Task(
        input=RestconfPatchInput,
        output=NornirSerializedResult,
        fastapi={"methods": ["POST"]},
        mcp={
            "annotations": {
                "title": "RESTCONF Patch",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": False,
                "openWorldHint": True,
            }
        },
    )
    def restconf_patch(
        self,
        job: Job,
        url: str = None,
        params: dict[str, Any] = None,
        headers: dict[str, str] = None,
        data: str = None,
        job_data: Any = None,
        **kwargs: Any,
    ) -> Result:
        """Update a RESTCONF resource.

        Args:
            job: NorFab job metadata.
            url: Literal resource relative to inventory base_url, or absolute URL.
            params: HTTP query parameters.
            headers: HTTP headers replacing inventory headers when supplied.
            data: Request body text or inline/nf:// Jinja2 template.
            job_data: Template context data or URL to a YAML data file.
            **kwargs: Common Nornir host filters, processors, runner and result options.

        Returns:
            Result: Per-host response payloads keyed by the HTTP verb, or list records.
                HTTP failures remain failed host results; no_match means no selected hosts.

        Raises:
            FileNotFoundError: If a template cannot be downloaded.
            ValueError: If the removed json argument is supplied.
        """
        return self._run_restconf(
            job,
            "patch",
            url=url,
            params=params,
            headers=headers,
            data=data,
            job_data=job_data,
            **kwargs,
        )

    @Task(
        input=RestconfDeleteInput,
        output=NornirSerializedResult,
        fastapi={"methods": ["POST"]},
        mcp={
            "annotations": {
                "title": "RESTCONF Delete",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def restconf_delete(
        self,
        job: Job,
        url: str = None,
        params: dict[str, Any] = None,
        headers: dict[str, str] = None,
        **kwargs: Any,
    ) -> Result:
        """Delete a RESTCONF resource.

        Args:
            job: NorFab job metadata.
            url: Literal resource relative to inventory base_url, or absolute URL.
            params: HTTP query parameters.
            headers: HTTP headers replacing inventory headers when supplied.
            **kwargs: Common Nornir host filters, processors, runner and result options.

        Returns:
            Result: Per-host response payloads keyed by the HTTP verb, or list records.
                HTTP failures remain failed host results; no_match means no selected hosts.
        """
        return self._run_restconf(
            job, "delete", url=url, params=params, headers=headers, **kwargs
        )

    @Task(
        input=RestconfPostInput,
        output=NornirSerializedResult,
        fastapi={"methods": ["POST"]},
        mcp={
            "annotations": {
                "title": "RESTCONF Post",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": False,
                "openWorldHint": True,
            }
        },
    )
    def restconf_post(
        self,
        job: Job,
        url: str = None,
        params: dict[str, Any] = None,
        headers: dict[str, str] = None,
        data: str = None,
        job_data: Any = None,
        **kwargs: Any,
    ) -> Result:
        """Create or update a RESTCONF resource using POST.

        Args:
            job: NorFab job metadata.
            url: Literal resource relative to inventory base_url, or absolute URL.
            params: HTTP query parameters.
            headers: HTTP headers replacing inventory headers when supplied.
            data: Request body text or inline/nf:// Jinja2 template.
            job_data: Template context data or URL to a YAML data file.
            **kwargs: Common Nornir host filters, processors, runner and result options.

        Returns:
            Result: Per-host response payloads keyed by the HTTP verb, or list records.
                HTTP failures remain failed host results; no_match means no selected hosts.

        Raises:
            FileNotFoundError: If a template cannot be downloaded.
            ValueError: If the removed json argument is supplied.
        """
        return self._run_restconf(
            job,
            "post",
            url=url,
            params=params,
            headers=headers,
            data=data,
            job_data=job_data,
            **kwargs,
        )
