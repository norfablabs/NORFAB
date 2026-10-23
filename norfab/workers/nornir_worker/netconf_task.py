import logging
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

from nornir_salt.plugins.functions import ResultSerializer
from nornir_salt.plugins.tasks import ncclient_call, scrapli_netconf_call

from norfab.core.exceptions import UnsupportedPluginError
from norfab.core.worker import Job, Task
from norfab.models import Result

from .nornir_models import (
    NetconfCommitInput,
    NetconfEditConfigInput,
    NetconfGetCapabilitiesInput,
    NetconfGetConfigInput,
    NetconfGetInput,
    NetconfGetSchemaInput,
    NetconfResult,
    NetconfTransactionInput,
    NetconfValidateInput,
)

log = logging.getLogger(__name__)

NETCONF_GETTERS = {
    "ietf_interfaces": '<interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces"/>',
    "openconfig_interfaces": '<interfaces xmlns="http://openconfig.net/yang/interfaces"/>',
    "openconfig_lldp": '<lldp xmlns="http://openconfig.net/yang/lldp"/>',
    "openconfig_bgp": '<network-instances xmlns="http://openconfig.net/yang/network-instance"><network-instance><protocols><protocol><bgp/></protocol></protocols></network-instance></network-instances>',
    "openconfig_system": '<system xmlns="http://openconfig.net/yang/system"/>',
    "ietf_routing": '<routing xmlns="urn:ietf:params:xml:ns:yang:ietf-routing"/>',
    "ietf_hardware": '<hardware xmlns="urn:ietf:params:xml:ns:yang:ietf-hardware"/>',
}

# --------------------------------------------------------------------------
# NETCONF TASK MODELS
# --------------------------------------------------------------------------


class NetconfTask:
    def _run_netconf(
        self,
        job: Job,
        call: str,
        plugin: str,
        render: dict[str, str] = None,
        job_data: Any = None,
        **kwargs: Any,
    ) -> Result:
        """Run a NETCONF plugin with common filtering, processors and serialization.

        Args:
            job: NorFab job metadata.
            call: Backend operation name.
            plugin: ncclient or scrapli.
            render: Backend argument names mapped to per-host templates.
            job_data: Template context data or YAML URL.
            **kwargs: Backend and common Nornir arguments.

        Returns:
            Result: Serialized per-host operation results.

        Raises:
            UnsupportedPluginError: If the plugin is unknown.
        """
        # Match each task callable to its connection name for watchdog tracking.
        if plugin == "ncclient":
            task_plugin, connection = ncclient_call, "ncclient"
        elif plugin == "scrapli":
            task_plugin, connection = scrapli_netconf_call, "scrapli_netconf"
        else:
            raise UnsupportedPluginError(f"plugin '{plugin}' not supported")
        # Consume serialization options before forwarding backend arguments.
        to_dict = kwargs.pop("to_dict", True)
        add_details = kwargs.pop("add_details", False)
        ret = Result(task=f"{self.name}:netconf_{call}", result={} if to_dict else [])
        # Extract host filters and return without device I/O when nothing matches.
        nr, _ = self.filter_hosts_and_validate(kwargs, ret)
        if ret.status == "no_match":
            log.debug("no hosts matched NETCONF %s using %s", call, plugin)
            return ret
        # Attach standard processors and consume their options from kwargs.
        nr = self._add_processors(nr, kwargs, job)
        # Reuse compiled file templates across hosts within this job.
        template_cache = {}
        try:
            # Render operation payloads before acquiring the connection lock.
            if render:
                log.debug(
                    "rendering NETCONF %s arguments %s for %s hosts using %s",
                    call,
                    ", ".join(render),
                    len(nr.inventory.hosts),
                    plugin,
                )
                context_data = self.load_job_data(job_data)
                filters = self.add_jinja2_filters()
                netbox = self.add_jinja2_netbox()
                for host in nr.inventory.hosts.values():
                    host.data["__task__"] = {
                        argument: self.jinja2_render_templates(
                            templates=[template],
                            context={
                                "host": host,
                                "job_data": context_data,
                                "norfab": self.client,
                                "netbox": netbox,
                            },
                            filters=filters,
                            template_cache=template_cache,
                        )
                        for argument, template in render.items()
                    }
            message = f"running NETCONF {call} using {plugin} on {len(nr.inventory.hosts)} hosts"
            log.info(message)
            job.event(message)
            # Only device execution and connection tracking require the lock.
            with self.connections_lock:
                result = nr.run(task=task_plugin, call=call, **kwargs)
                # Refresh connection activity before watchdog idle cleanup.
                self.watchdog.connections_update(nr, connection)
            # Preserve host failures and apply the requested public result format.
            self.update_nornir_result(result, ret)
            ret.failed = result.failed
            ret.result = ResultSerializer(
                result, to_dict=to_dict, add_details=add_details
            )
            message = (
                f"completed NETCONF {call} using {plugin} on {len(nr.inventory.hosts)} hosts"
                + (" with host failures" if ret.failed else "")
            )
            if ret.failed:
                log.warning(message)
                job.event(message, severity="WARNING")
            else:
                log.info(message)
                job.event(message)
            return ret
        except Exception as exc:
            # Report the failure type without exposing configuration or template data.
            message = f"netconf {call} using {plugin} failed ({type(exc).__name__})"
            log.error(message)
            job.event(message, severity="ERROR")
            raise
        finally:
            # Remove temporary payloads even if rendering or execution raises.
            for host in nr.inventory.hosts.values():
                host.data.pop("__task__", None)
            self.watchdog.connections_clean()

    @Task(
        fastapi={"methods": ["POST"]},
        input=NetconfGetConfigInput,
        output=NetconfResult,
        mcp={
            "annotations": {
                "title": "NETCONF Get Configuration",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def netconf_get_config(
        self,
        job: Job,
        source: str = "running",
        plugin: str = "ncclient",
        filter_subtree: str = None,
        filter_xpath: str = None,
        job_data: Any = None,
        **kwargs: Any,
    ) -> Result:
        """Retrieve device configuration from a NETCONF datastore.

        Args:
            job: NorFab job metadata.
            source: Datastore to read: running, candidate, or startup. The device
                must support the selected datastore. Defaults to running.
            plugin: NETCONF backend: ncclient (default) or scrapli.
            filter_subtree: Optional XML subtree or NorFab template URL. Rendered
                per host with host, job_data, norfab and netbox context variables.
                Mutually exclusive with filter_xpath. Omit both filters to
                retrieve the complete datastore.
            filter_xpath: XPath expression or NorFab template URL, rendered with
                the same context as filter_subtree. Requires the device XPath
                capability. Explicit namespace mappings are not exposed. This
                filters on the server; the common xpath processor instead
                filters replies locally after retrieval.
            job_data: Optional template context data or URL to a YAML data file.
            **kwargs: Common Nornir host filters, processors, retry options,
                XML processors (xmltodict, xpath, xml_flake), to_dict and
                add_details serialization options.

        Returns:
            Result: XML replies under each host's get_config key, or serialized
                records when to_dict is false. RPC and connection errors mark
                host results as failed; unmatched hosts return status no_match.

        Raises:
            FileNotFoundError: If a referenced template cannot be fetched.

        """
        template = None
        filter_type = None
        if filter_subtree is not None:
            template = filter_subtree
            filter_type = "subtree"
        if filter_xpath is not None:
            template = filter_xpath
            filter_type = "xpath"
        render = None
        if template is not None:
            if plugin == "ncclient":
                render = {"filter": template}
                kwargs["ftype"] = filter_type
            else:
                render = {"filter_": template}
                kwargs["filter_type"] = filter_type
        return self._run_netconf(
            job,
            call="get_config",
            plugin=plugin,
            source=source,
            render=render,
            job_data=job_data,
            **kwargs,
        )

    @Task(
        fastapi={"methods": ["POST"]},
        input=NetconfEditConfigInput,
        output=NetconfResult,
        mcp={
            "annotations": {
                "title": "NETCONF Edit Configuration",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": False,
                "openWorldHint": True,
            }
        },
    )
    def netconf_edit_config(
        self,
        job: Job,
        config: str,
        target: str = "running",
        plugin: str = "ncclient",
        job_data: Any = None,
        **kwargs: Any,
    ) -> Result:
        """Edit a device NETCONF configuration datastore.

        Args:
            job: NorFab job metadata.
            config: XML configuration including the NETCONF config wrapper, or a
                NorFab template URL. Rendered per host with host, job_data,
                norfab and netbox context variables.
            target: Datastore to edit: running (default) or candidate. Requires
                device support. Running edits take effect immediately.
            plugin: Backend name: ncclient (default) or scrapli.
            job_data: Template context data or URL to a YAML data file.
            **kwargs: Common Nornir host filters, processors, retry options,
                XML processors (xmltodict, xpath, xml_flake), to_dict and
                add_details serialization options.

        Returns:
            Result: XML replies under each host's edit_config key, or serialized
                records with to_dict=False. RPC and connection errors mark hosts
                as failed; unmatched hosts return status no_match. No datastore
                locking, validation, commit, or rollback is performed. Candidate
                edits remain pending. Retries may repeat edits.

        Raises:
            FileNotFoundError: If a referenced template cannot be fetched.

        """
        return self._run_netconf(
            job,
            call="edit_config",
            plugin=plugin,
            target=target,
            render={"config": config},
            job_data=job_data,
            **kwargs,
        )

    @Task(
        fastapi={"methods": ["POST"]},
        input=NetconfGetSchemaInput,
        output=NetconfResult,
        mcp={
            "annotations": {
                "title": "NETCONF Get Schema",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def netconf_get_schema(
        self,
        job: Job,
        identifier: str,
        version: str = None,
        format: str = "yang",
        plugin: str = "ncclient",
        **kwargs: Any,
    ) -> Result:
        """Retrieve a YANG module using NETCONF monitoring get-schema.

        Args:
            job: NorFab job metadata.
            identifier: Module name from capabilities, YANG Library, or the
                NETCONF monitoring schema list. Capabilities may be incomplete.
            version: Optional module revision, normally YYYY-MM-DD. Omit to let
                the server select a version.
            format: Schema format: yang (default) or yin.
            plugin: Backend name: ncclient (default) or scrapli.
            **kwargs: Common host filters, retries, XML processors (xmltodict,
                xpath, xml_flake) and serialization options applicable to this task.

        Returns:
            Result: XML replies containing schema text under get_schema for
                ncclient or rpc for Scrapli. Missing modules and unsupported
                schema retrieval mark hosts as failed. Unmatched hosts return
                status no_match. Imports are not downloaded automatically.
                Requires the device to implement NETCONF monitoring get-schema.
        """
        if plugin == "scrapli":
            rpc = Element(
                "get-schema",
                xmlns="urn:ietf:params:xml:ns:yang:ietf-netconf-monitoring",
            )
            SubElement(rpc, "identifier").text = identifier
            if version is not None:
                SubElement(rpc, "version").text = version
            SubElement(rpc, "format").text = format
            return self._run_netconf(
                job,
                call="rpc",
                plugin=plugin,
                filter_=tostring(rpc, encoding="unicode"),
                **kwargs,
            )
        return self._run_netconf(
            job,
            call="get_schema",
            plugin=plugin,
            identifier=identifier,
            version=version,
            format=format,
            **kwargs,
        )

    @Task(
        fastapi={"methods": ["POST"]},
        input=NetconfGetCapabilitiesInput,
        output=NetconfResult,
        mcp={
            "annotations": {
                "title": "NETCONF Get Capabilities",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def netconf_get_capabilities(
        self,
        job: Job,
        plugin: str = "ncclient",
        capab_filter: str = None,
        **kwargs: Any,
    ) -> Result:
        """List NETCONF capabilities advertised by devices.

        Args:
            job: NorFab job metadata.
            plugin: Backend name: ncclient (default) or scrapli.
            capab_filter: Optional case-sensitive glob pattern to filter capability
                URIs. Omit to return all capabilities advertised for the session.
            **kwargs: Common host filters, retries and serialization options.

        Returns:
            Result: Capability URI lists under each host's server_capabilities
                key, or serialized records with to_dict=False. An unmatched
                capability filter returns an empty list. Unmatched host filters
                return status no_match. Connection errors mark hosts as failed.
                Capabilities describe the current session and do not necessarily
                provide a complete inventory of available YANG modules.
        """
        return self._run_netconf(
            job,
            call="server_capabilities",
            plugin=plugin,
            capab_filter=capab_filter,
            **kwargs,
        )

    @Task(
        fastapi={"methods": ["POST"]},
        input=NetconfGetInput,
        output=NetconfResult,
        mcp={
            "annotations": {
                "title": "NETCONF Get Data",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def netconf_get(
        self,
        job: Job,
        plugin: str = "ncclient",
        filter_subtree: str = None,
        filter_xpath: str = None,
        job_data: Any = None,
        ietf_interfaces: bool = False,
        openconfig_interfaces: bool = False,
        openconfig_lldp: bool = False,
        openconfig_bgp: bool = False,
        openconfig_system: bool = False,
        ietf_routing: bool = False,
        ietf_hardware: bool = False,
        **kwargs: Any,
    ) -> Result:
        """Retrieve device configuration and operational state using NETCONF get.

        Args:
            job: NorFab job metadata.
            plugin: NETCONF backend: ncclient (default) or scrapli.
            filter_subtree: Optional XML subtree or NorFab template URL. Rendered
                per host with host, job_data, norfab and netbox context variables.
                Mutually exclusive with filter_xpath and predefined getters. Omit
                all selections to retrieve available configuration and state data.
            filter_xpath: XPath expression or NorFab template URL, rendered with
                the same context as filter_subtree. Requires the device XPath
                capability. Explicit namespace mappings are not exposed. This
                filters on the server; the common xpath processor instead
                filters replies locally after retrieval.
            job_data: Optional template context data or URL to a YAML data file.
            ietf_interfaces: Retrieve the standard IETF interfaces subtree.
                Defaults to false. Mutually exclusive with filter_subtree and
                filter_xpath. Requires device support for ietf-interfaces;
                empty replies remain successful. Does not select the legacy
                interfaces-state subtree. Only one getter or explicit filter
                may be selected. All getters require device model support;
                empty replies remain successful.
            openconfig_interfaces: Retrieve the OpenConfig interfaces subtree. Defaults to false.
            openconfig_lldp: Retrieve the OpenConfig LLDP subtree. Defaults to false.
            openconfig_bgp: Retrieve OpenConfig BGP configuration and state across
                network instances. Defaults to false. May include large RIB data.
            openconfig_system: Retrieve the OpenConfig system subtree. Defaults to false.
            ietf_routing: Retrieve the IETF routing subtree. Defaults to false.
            ietf_hardware: Retrieve the IETF hardware subtree. Defaults to false.
            **kwargs: Common Nornir host filters, processors, retry options,
                XML processors (xmltodict, xpath, xml_flake), to_dict and
                add_details serialization options.

        Returns:
            Result: XML replies under each host's get key (rpc for unfiltered
                Scrapli requests), or serialized
                records when to_dict is false. RPC and connection errors mark
                host results as failed; unmatched hosts return status no_match.

        Raises:
            FileNotFoundError: If a referenced template cannot be fetched.

        """
        for getter, selected in {
            "ietf_interfaces": ietf_interfaces,
            "openconfig_interfaces": openconfig_interfaces,
            "openconfig_lldp": openconfig_lldp,
            "openconfig_bgp": openconfig_bgp,
            "openconfig_system": openconfig_system,
            "ietf_routing": ietf_routing,
            "ietf_hardware": ietf_hardware,
        }.items():
            if selected:
                filter_subtree = NETCONF_GETTERS[getter]
        # Scrapli get requires a filter; use an unfiltered RPC when omitted.
        if plugin == "scrapli" and filter_subtree is None and filter_xpath is None:
            return self._run_netconf(
                job, call="rpc", plugin=plugin, filter_="<get/>", **kwargs
            )
        template = None
        filter_type = None
        if filter_subtree is not None:
            template = filter_subtree
            filter_type = "subtree"
        if filter_xpath is not None:
            template = filter_xpath
            filter_type = "xpath"
        render = None
        if template is not None:
            if plugin == "ncclient":
                render = {"filter": template}
                kwargs["ftype"] = filter_type
            else:
                render = {"filter_": template}
                kwargs["filter_type"] = filter_type
        return self._run_netconf(
            job,
            call="get",
            plugin=plugin,
            render=render,
            job_data=job_data,
            **kwargs,
        )

    @Task(
        fastapi={"methods": ["POST"]},
        input=NetconfTransactionInput,
        output=NetconfResult,
        mcp={
            "annotations": {
                "title": "NETCONF Transaction",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": False,
                "openWorldHint": True,
            }
        },
    )
    def netconf_transaction(
        self,
        job: Job,
        config: str,
        target: str = None,
        plugin: str = "ncclient",
        job_data: Any = None,
        validate: bool = True,
        confirmed: bool = True,
        confirm_delay: int = 60,
        commit_final_delay: int = 1,
        edit_rpc: str = "edit_config",
        edit_arg: dict[str, Any] = None,
        commit_arg: dict[str, Any] = None,
        **kwargs: Any,
    ) -> Result:
        """Apply configuration using Nornir-Salt's NETCONF transaction call.

        Args:
            job: NorFab job metadata.
            config: XML including the config wrapper or a NorFab template URL.
                Rendered per host with host, job_data, norfab and netbox context.
            target: Datastore to edit. Omit to let the backend choose candidate
                when supported, otherwise running.
            plugin: Backend name: ncclient (default) or scrapli.
            job_data: Template context data or URL to a YAML data file.
            validate: Request validation when supported. Defaults to true.
            confirmed: Request confirmed commit when supported. Defaults to true.
            confirm_delay: Confirmed commit rollback timeout in seconds. Defaults to 60.
            commit_final_delay: Seconds before automatic final confirmation. Defaults to 1.
            edit_rpc: ncclient edit RPC name. Defaults to edit_config; ignored by Scrapli.
            edit_arg: Additional ncclient edit RPC arguments; ignored by Scrapli.
                The backend supplies config and target.
            commit_arg: Additional ncclient first commit arguments; ignored by Scrapli.
            **kwargs: Common host filters, processors, retries and serialization
                options, plus additional Nornir-Salt backend arguments.

        Returns:
            Result: Per-host transaction step lists under the transaction key,
                or serialized records with to_dict=False. Nornir-Salt owns locking,
                candidate discard, editing, validation, commit and failure cleanup.
                Existing candidate changes are discarded. Running edits cannot be
                rolled back by discarding candidate changes. Transactions are per
                host, and retries may repeat them. RPC failures mark hosts failed;
                unmatched hosts return status no_match.

        Raises:
            FileNotFoundError: If a referenced template cannot be fetched.
        """
        if target is not None:
            kwargs["target"] = target
        return self._run_netconf(
            job,
            call="transaction",
            plugin=plugin,
            render={"config": config},
            job_data=job_data,
            validate=validate,
            confirmed=confirmed,
            confirm_delay=confirm_delay,
            commit_final_delay=commit_final_delay,
            edit_rpc=edit_rpc,
            edit_arg=edit_arg if edit_arg is not None else {},
            commit_arg=commit_arg if commit_arg is not None else {},
            **kwargs,
        )

    @Task(
        fastapi={"methods": ["POST"]},
        input=NetconfValidateInput,
        output=NetconfResult,
        mcp={
            "annotations": {
                "title": "NETCONF Validate Configuration",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def netconf_validate(
        self,
        job: Job,
        source: str = "candidate",
        plugin: str = "ncclient",
        **kwargs: Any,
    ) -> Result:
        """Validate a device configuration datastore without applying changes.

        Args:
            job: NorFab job metadata.
            source: Datastore to validate: candidate (default), running, or
                startup. Requires device support for the selected datastore.
            plugin: NETCONF backend: ncclient (default) or scrapli.
            **kwargs: Common Nornir host filters, processors, retry options,
                XML processors (xmltodict, xpath, xml_flake), to_dict and
                add_details serialization options.

        Returns:
            Result: XML replies under each host's validate key, normally an
                ok reply on success, or serialized records when to_dict=False.
                Validation, capability and connection errors mark hosts as
                failed; unmatched hosts return status no_match. Requires the
                NETCONF validate capability. Does not edit, lock, commit, or
                discard configuration. A successful validation does not check
                connectivity or service health.
        """
        return self._run_netconf(
            job, call="validate", plugin=plugin, source=source, **kwargs
        )

    @Task(
        fastapi={"methods": ["POST"]},
        input=NetconfCommitInput,
        output=NetconfResult,
        mcp={
            "annotations": {
                "title": "NETCONF Commit Configuration",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": False,
                "openWorldHint": True,
            }
        },
    )
    def netconf_commit(
        self,
        job: Job,
        plugin: str = "ncclient",
        confirmed: bool = False,
        confirm_delay: int = None,
        persist: str = None,
        persist_id: str = None,
        **kwargs: Any,
    ) -> Result:
        """Commit candidate configuration or confirm a pending confirmed commit.

        Args:
            job: NorFab job metadata.
            plugin: NETCONF backend: ncclient (default) or scrapli.
            confirmed: Start a confirmed commit with automatic rollback unless
                subsequently confirmed. Defaults to false. Requires device support.
            confirm_delay: Rollback timeout in seconds for a confirmed commit.
                Omit for the device default. Requires confirmed=True. This is
                separate from the client's job timeout.
            persist: Token allowing a confirmed commit to survive session closure.
                Requires confirmed=True and NETCONF persistent commit support.
            persist_id: Token from a previous persistent confirmed commit to
                confirm. Mutually exclusive with confirmed=True and persist.
            **kwargs: Common host filters, processors, retries, XML processors
                (xmltodict, xpath, xml_flake), to_dict and add_details options.

        Returns:
            Result: XML replies under each host's commit key, normally an ok
                reply, or serialized records when to_dict=False. RPC, capability
                and connection errors mark hosts failed; unmatched hosts return
                status no_match. Requires candidate support. Commits all pending
                candidate changes without editing, locking, or validating them.
                Confirmed commits are not automatically finalized by this task;
                call again without confirmed to confirm, supplying persist_id
                for a persistent commit. Nonpersistent confirmation requires the
                original NETCONF session. Retries may repeat commits.
        """
        if confirm_delay is not None:
            kwargs["timeout"] = (
                str(confirm_delay) if plugin == "ncclient" else confirm_delay
            )
        return self._run_netconf(
            job,
            call="commit",
            plugin=plugin,
            confirmed=confirmed,
            persist=persist,
            persist_id=persist_id,
            **kwargs,
        )

    def netconf_cancel_commit(self, job: Job, **kwargs: Any) -> Result:
        raise NotImplementedError("netconf_cancel_commit is not implemented")

    def netconf_discard_changes(self, job: Job, **kwargs: Any) -> Result:
        raise NotImplementedError("netconf_discard_changes is not implemented")

    def netconf_lock(self, job: Job, **kwargs: Any) -> Result:
        raise NotImplementedError("netconf_lock is not implemented")

    def netconf_unlock(self, job: Job, **kwargs: Any) -> Result:
        raise NotImplementedError("netconf_unlock is not implemented")

    def netconf_copy_config(self, job: Job, **kwargs: Any) -> Result:
        raise NotImplementedError("netconf_copy_config is not implemented")

    def netconf_delete_config(self, job: Job, **kwargs: Any) -> Result:
        raise NotImplementedError("netconf_delete_config is not implemented")

    def netconf_rpc(self, job: Job, **kwargs: Any) -> Result:
        raise NotImplementedError("netconf_rpc is not implemented")
