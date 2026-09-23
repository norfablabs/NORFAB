import logging
import os
from types import SimpleNamespace
from typing import Any, Union

import yaml
from datamodel_code_generator import DataModelType, InputFileType, generate
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

from norfab.core.worker import Job, Task
from norfab.models import Result
from norfab.utils.text import expand_alphanumeric_range, slugify

from .netbox_crud import _get_pynetbox_accessor
from .netbox_models import DesignDeployInput, DesignDeployResult, NetboxFastApiArgs

log = logging.getLogger(__name__)


COLLECTION_OBJECT_TYPES = {
    "tenants": "tenancy.tenants",
    "regions": "dcim.regions",
    "site_groups": "dcim.site-groups",
    "manufacturers": "dcim.manufacturers",
    "platforms": "dcim.platforms",
    "device_roles": "dcim.device-roles",
    "device_types": "dcim.device-types",
    "rack_roles": "dcim.rack-roles",
    "rirs": "ipam.rirs",
    "roles": "ipam.roles",
    "route_targets": "ipam.route-targets",
    "vrfs": "ipam.vrfs",
    "l2vpns": "vpn.l2vpns",
    "providers": "circuits.providers",
    "circuit_types": "circuits.circuit-types",
    "cluster_types": "virtualization.cluster-types",
    "cluster_groups": "virtualization.cluster-groups",
    "sites": "dcim.sites",
    "asn_ranges": "ipam.asn-ranges",
    "vlan_groups": "ipam.vlan-groups",
    "locations": "dcim.locations",
    "asns": "ipam.asns",
    "provider_networks": "circuits.provider-networks",
    "prefixes": "ipam.prefixes",
    "vlans": "ipam.vlans",
    "circuits": "circuits.circuits",
    "clusters": "virtualization.clusters",
    "racks": "dcim.racks",
    "rack_reservations": "dcim.rack-reservations",
    "power_panels": "dcim.power-panels",
    "power_feeds": "dcim.power-feeds",
    "devices": "dcim.devices",
    "virtual_machines": "virtualization.virtual-machines",
    "circuit_terminations": "circuits.circuit-terminations",
    "interfaces": "dcim.interfaces",
    "mac_addresses": "dcim.mac-addresses",
    "front_ports": "dcim.front-ports",
    "rear_ports": "dcim.rear-ports",
    "console_ports": "dcim.console-ports",
    "console_server_ports": "dcim.console-server-ports",
    "power_ports": "dcim.power-ports",
    "power_outlets": "dcim.power-outlets",
    "device_bays": "dcim.device-bays",
    "module_bays": "dcim.module-bays",
    "inventory_items": "dcim.inventory-items",
    "vm_interfaces": "virtualization.interfaces",
    "ip_addresses": "ipam.ip-addresses",
    "connections": "dcim.cables",
    "cables": "dcim.cables",
    "virtual_chassis": "dcim.virtual-chassis",
    "services": "ipam.services",
    "fhrp_groups": "ipam.fhrp-groups",
    "fhrp_group_assignments": "ipam.fhrp-group-assignments",
    "vrrp_groups": "ipam.fhrp-groups",
    "vrrp_group_assignments": "ipam.fhrp-group-assignments",
    "l2vpn_terminations": "vpn.l2vpn-terminations",
    "bgp_sessions": "plugins.bgp.session",
}

CREATE_ORDER = list(COLLECTION_OBJECT_TYPES)

IDENTITY_FIELDS = {
    "device_types": ("model",),
    "devices": ("name",),
    "interfaces": ("device", "name"),
    "mac_addresses": ("mac_address",),
    "vm_interfaces": ("virtual_machine", "name"),
    "prefixes": ("vrf", "prefix"),
    "ip_addresses": ("vrf", "address"),
    "vlans": ("group", "vid"),
    "asns": ("asn",),
    "racks": ("site", "location", "name"),
    "circuits": ("provider", "cid"),
    "bgp_sessions": ("name",),
    "connections": ("label",),
    "cables": ("label",),
    "l2vpns": ("name",),
    "route_targets": ("name",),
    "vrrp_groups": ("protocol", "group_id"),
    "fhrp_groups": ("protocol", "group_id"),
    "l2vpn_terminations": ("l2vpn", "interface"),
    "vrrp_group_assignments": ("group", "interface"),
    "fhrp_group_assignments": ("group", "interface"),
}

IDENTITY_RELATIONS = {
    ("interfaces", "device"): ("dcim.devices", "device_id"),
    ("vm_interfaces", "virtual_machine"): (
        "virtualization.virtual-machines",
        "virtual_machine_id",
    ),
    ("prefixes", "vrf"): ("ipam.vrfs", "vrf_id"),
    ("ip_addresses", "vrf"): ("ipam.vrfs", "vrf_id"),
    ("vlans", "group"): ("ipam.vlan-groups", "group_id"),
    ("racks", "site"): ("dcim.sites", "site_id"),
    ("racks", "location"): ("dcim.locations", "location_id"),
    ("circuits", "provider"): ("circuits.providers", "provider_id"),
}

RELATION_FIELDS = {
    "platforms": {"manufacturer": "name"},
    "device_types": {"manufacturer": "name", "default_platform": "name"},
    "sites": {"region": "name", "group": "name", "tenant": "name"},
    "locations": {"site": "name", "parent": "name", "tenant": "name"},
    "devices": {
        "device_type": "model",
        "role": "name",
        "tenant": "name",
        "site": "name",
        "location": "name",
        "rack": "name",
        "platform": "name",
        "cluster": "name",
    },
    "interfaces": {"device": "name", "vrf": "name"},
    "prefixes": {
        "site": "name",
        "tenant": "name",
        "vrf": "name",
        "role": "name",
        "vlan": "vid",
    },
    "ip_addresses": {"tenant": "name", "vrf": "name", "role": "name"},
    "vlan_groups": {"tenant": "name"},
    "vlans": {
        "group": "name",
        "site": "name",
        "tenant": "name",
        "role": "name",
    },
    "asns": {"rir": "name", "tenant": "name"},
    "asn_ranges": {"rir": "name", "tenant": "name"},
    "racks": {
        "site": "name",
        "location": "name",
        "role": "name",
        "tenant": "name",
    },
    "l2vpns": {"tenant": "name"},
}

NESTED_FIELDS = {
    "devices": ("interfaces", "bgp", "bgp_sessions"),
    "interfaces": ("ip_addresses", "mac_addresses"),
    "prefixes": ("ip_addresses",),
}

SLUG_FIELDS = {
    "tenants": "name",
    "regions": "name",
    "site_groups": "name",
    "manufacturers": "name",
    "platforms": "name",
    "device_roles": "name",
    "device_types": "model",
    "rack_roles": "name",
    "rirs": "name",
    "roles": "name",
    "asn_ranges": "name",
    "vlan_groups": "name",
    "l2vpns": "name",
    "providers": "name",
    "circuit_types": "name",
    "cluster_types": "name",
    "cluster_groups": "name",
    "locations": "name",
    "sites": "name",
}


class NetboxDesignTasks:
    @Task(
        input=DesignDeployInput,
        output=DesignDeployResult,
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()},
        mcp={
            "annotations": {
                "title": "Deploy Design",
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def design_deploy(
        self,
        job: Job,
        design: Union[str, dict],
        context: Union[str, dict] = {},
        instance: str = None,
        dry_run: bool = False,
        branch: str = None,
    ) -> Result:
        """Render, validate, and deploy an additive NetBox design.

        Args:
            job: NorFab job injected by the task framework.
            design: YAML design text, an ``nf://`` or ``git://`` design URL,
                or an already parsed design mapping.
            context: User input exposed to Jinja2 through the ``context``
                variable. If the design declares ``design_input_schema``, the
                input is validated before the template is rendered.
            instance: NetBox instance name. Uses the worker default when omitted.
            dry_run: Calculate and return changes without applying them.
            branch: NetBox Branching plugin branch name.

        Returns:
            Result containing created, updated, and unchanged objects and diffs.

        Raises:
            TypeError: If the design, design specification, or input data has
                an invalid type.
            ValueError: If input validation fails, a declared Jinja function
                cannot be loaded, or the rendered design is invalid.
        """
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:design_deploy",
            result={"created": {}, "updated": {}, "unchanged": {}},
            resources=[instance],
            dry_run=dry_run,
            diff={},
        )
        if self.is_url(context):
            context = self.fetch_file(context, raise_on_fail=True)
        if isinstance(context, str):
            context = yaml.safe_load(context) or {}
        if not isinstance(context, dict):
            raise TypeError("Design context must be a dictionary or YAML mapping")

        if isinstance(design, dict):
            design = dict(design)
            input_schema = design.pop("design_input_schema", None)
            jinja_functions = design.pop("jinja_functions", {})
        elif isinstance(design, str):
            design_source = (
                self.fetch_file(design, raise_on_fail=True)
                if self.is_url(design)
                else design
            )
            header_source, separator, _ = design_source.partition("\n---")
            if separator and any(
                marker in header_source for marker in ("{{", "{%", "{#")
            ):
                if not self.is_url(design):
                    raise ValueError(
                        "Jinja2 includes in the design header require an nf:// or git:// URL"
                    )
                filepath = self.jinja2_fetch_template(design)
                header_source = (
                    Environment(loader=FileSystemLoader(os.path.dirname(filepath)))
                    .from_string(header_source)
                    .render()
                )
            has_design_header = any(
                line.startswith(("design_input_schema:", "jinja_functions:"))
                for line in header_source.splitlines()
            )
            if (
                has_design_header
                and not separator
                and any(marker in design_source for marker in ("{{", "{%", "{#"))
            ):
                raise ValueError(
                    "Separate the design metadata header from its Jinja2 body with ---"
                )
            design_header = (
                yaml.safe_load(header_source if separator else design_source) or {}
                if has_design_header
                else {}
            )
            input_schema = design_header.get("design_input_schema")
            jinja_functions = design_header.get("jinja_functions", {})
        else:
            raise TypeError("Design must be YAML text, a file URL, or a dictionary")

        if input_schema:
            model_globals = {}
            if isinstance(input_schema, str):
                if not self.is_url(input_schema):
                    raise ValueError(
                        "Design input schema model must use an nf:// or git:// URL"
                    )
                model_source = self.fetch_file(input_schema, raise_on_fail=True)
            elif isinstance(input_schema, dict):
                model_source = generate(
                    input_schema,
                    input_file_type=InputFileType.JsonSchema,
                    output_model_type=DataModelType.PydanticV2BaseModel,
                    class_name="DesignInput",
                    disable_timestamp=True,
                    formatters=[],
                )
            else:
                raise TypeError(
                    "Design input schema must be JSON Schema or a Pydantic model URL"
                )
            exec(model_source, model_globals, model_globals)  # nosec B102
            input_model = model_globals.get("DesignInput")
            if not isinstance(input_model, type) or not issubclass(
                input_model, BaseModel
            ):
                raise ValueError(
                    "Design input schema must define a Pydantic DesignInput model"
                )
            input_model.model_rebuild(_types_namespace=model_globals)
            context = input_model.model_validate(context).model_dump()

        loaded_functions = {}
        pending_ip_assignments = []
        inline_results = []
        if not isinstance(jinja_functions, dict):
            raise TypeError("Design jinja_functions must be a mapping")
        for function_name, function_url in jinja_functions.items():
            if not self.is_url(function_url):
                raise ValueError(
                    f"Jinja function '{function_name}' must use an nf:// or git:// URL"
                )
            function_source = self.fetch_file(function_url, raise_on_fail=True)
            function_globals = {}
            exec(function_source, function_globals, function_globals)  # nosec B102
            function = function_globals.get(function_name)
            if not callable(function):
                raise ValueError(
                    f"Jinja function file '{function_url}' must define "
                    f"callable '{function_name}'"
                )
            loaded_functions[function_name] = function

        nb = self._get_pynetbox(instance, branch=branch, job=job)

        if isinstance(design, str):

            def create_ip(
                prefix: Union[str, dict],
                device: Union[str, None] = None,
                interface: Union[str, None] = None,
                **kwargs: Any,
            ) -> str:
                target_device = device and nb.dcim.devices.get(name=device)
                target_exists = (
                    target_device
                    and interface
                    and nb.dcim.interfaces.get(
                        device_id=target_device.id, name=interface
                    )
                )
                allocation = self.create_ip(
                    job=job,
                    prefix=prefix,
                    device=device if target_exists else None,
                    interface=interface if target_exists else None,
                    **{
                        **kwargs,
                        "instance": instance,
                        "branch": branch,
                        "dry_run": dry_run,
                    },
                )
                if device and interface and not target_exists:
                    pending_ip_assignments.append(
                        (allocation.result["address"], device, interface)
                    )
                return allocation.result["address"]

            def create_object(collection: str, **data: Any) -> Any:
                result = self.design_deploy(
                    job=job,
                    design={collection: [data]},
                    instance=instance,
                    dry_run=dry_run,
                    branch=branch,
                )
                if result.failed:
                    raise ValueError("; ".join(result.errors))
                inline_results.append(result)
                for field in ("name", "prefix", "address", "asn", "vid", "model"):
                    if field in data:
                        return data[field]
                return data

            allocation_filters = {
                "netbox.create_object": create_object,
                "netbox.create_ip": create_ip,
                "netbox.create_prefix": lambda parent, description, prefixlen=30, **kwargs: self.create_prefix(
                    job=job,
                    parent=parent,
                    description=description,
                    prefixlen=prefixlen,
                    **{
                        **kwargs,
                        "instance": instance,
                        "branch": branch,
                        "dry_run": dry_run,
                    },
                ).result[
                    "prefix"
                ],
                "netbox.create_asn": lambda asn_range, description=None, **kwargs: self.create_asn(
                    job=job,
                    asn_range=asn_range,
                    description=description,
                    **{
                        **kwargs,
                        "instance": instance,
                        "branch": branch,
                        "dry_run": dry_run,
                    },
                ).result[
                    "asn"
                ],
                "netbox.create_vlan": lambda vlan_group, name, **kwargs: self.create_vlan(
                    job=job,
                    vlan_group=vlan_group,
                    name=name,
                    **{
                        **kwargs,
                        "instance": instance,
                        "branch": branch,
                        "dry_run": dry_run,
                    },
                ).result[
                    "vid"
                ],
                "netbox.create_vlan_group": lambda name, site, vid_ranges, **kwargs: self.create_vlan_group(
                    job=job,
                    name=name,
                    site=site,
                    vid_ranges=vid_ranges,
                    **{
                        **kwargs,
                        "instance": instance,
                        "branch": branch,
                        "dry_run": dry_run,
                    },
                ).result[
                    "name"
                ],
            }
            try:
                rendered_design = self.jinja2_render_templates(
                    templates=[design],
                    context={
                        "context": context,
                        **loaded_functions,
                        "dry_run": dry_run,
                        "netbox": SimpleNamespace(
                            **{
                                name.removeprefix("netbox."): function
                                for name, function in allocation_filters.items()
                            }
                        ),
                    },
                    filters={
                        **loaded_functions,
                        "expand_range": expand_alphanumeric_range,
                        **allocation_filters,
                    },
                )
            except Exception as exc:
                message = (
                    f"Design rendering or allocation failed: {exc}. "
                    "Create allocation dependencies at the top of the design."
                )
                job.event(message, severity="ERROR")
                ret.failed = True
                ret.errors.append(message)
                return ret
            rendered_documents = [
                document
                for document in yaml.safe_load_all(rendered_design)
                if document is not None
            ]
            if rendered_documents:
                rendered_documents[0].pop("design_input_schema", None)
                rendered_documents[0].pop("jinja_functions", None)
                if not rendered_documents[0]:
                    rendered_documents.pop(0)
            if len(rendered_documents) != 1:
                raise ValueError("Design must render to one YAML target-state document")
            design = rendered_documents[0]
            for inline_result in inline_results:
                for action, collections in inline_result.result.items():
                    for collection, labels in collections.items():
                        ret.result[action].setdefault(collection, []).extend(labels)
                for collection, changes in inline_result.diff.items():
                    ret.diff.setdefault(collection, {}).update(changes)
        if not isinstance(design, dict) or not design:
            raise ValueError("Design must be a non-empty YAML mapping")

        for collection, objects in design.items():
            if collection not in COLLECTION_OBJECT_TYPES:
                raise ValueError(f"Unsupported design collection '{collection}'")
            if not isinstance(objects, list):
                raise TypeError(f"Design collection '{collection}' must be a list")
            if not all(isinstance(item, dict) for item in objects):
                raise TypeError(
                    f"Every object in design collection '{collection}' must be a mapping"
                )

        target_state = design
        devices = target_state.get("devices", [])
        if devices:
            target_state.setdefault("regions", [])
            target_state.setdefault("sites", [])
            target_state.setdefault("manufacturers", [])
            target_state.setdefault("device_roles", [])
            target_state.setdefault("device_types", [])
            if not any(
                item.get("name") == "undefined" for item in target_state["regions"]
            ):
                target_state["regions"].insert(0, {"name": "undefined"})
            if not any(
                item.get("name") == "undefined" for item in target_state["sites"]
            ):
                target_state["sites"].insert(
                    0,
                    {"name": "undefined", "region": "undefined", "status": "active"},
                )
            if not any(
                item.get("name") == "undefined"
                for item in target_state["manufacturers"]
            ):
                target_state["manufacturers"].insert(0, {"name": "undefined"})
            if not any(
                item.get("name") == "undefined" for item in target_state["device_roles"]
            ):
                target_state["device_roles"].insert(0, {"name": "undefined"})
            if not any(
                item.get("model") == "undefined"
                for item in target_state["device_types"]
            ):
                target_state["device_types"].insert(
                    0, {"model": "undefined", "manufacturer": "undefined"}
                )
            for device in devices:
                device.setdefault("site", "undefined")
                device.setdefault("role", "undefined")
                device.setdefault("device_type", "undefined")
                device.setdefault("status", "active")

        for site in target_state.get("sites", []):
            site.setdefault("region", "undefined")
            site.setdefault("status", "active")
        for device_type in target_state.get("device_types", []):
            device_type.setdefault("manufacturer", "undefined")
        for interface in target_state.get("interfaces", []):
            interface.setdefault("type", "other")

        collection_sources = {
            collection: list(objects) for collection, objects in target_state.items()
        }
        for device in devices:
            for interface in device.get("interfaces", []):
                interface.setdefault("device", device["name"])
                interface.setdefault("type", "other")
                collection_sources.setdefault("interfaces", []).append(interface)
                for ip_address in interface.get("ip_addresses", []):
                    ip_address.setdefault(
                        "interface",
                        {"device": device["name"], "name": interface["name"]},
                    )
                    collection_sources.setdefault("ip_addresses", []).append(ip_address)
                for mac_address in interface.get("mac_addresses", []):
                    mac_address.setdefault(
                        "interface",
                        {"device": device["name"], "name": interface["name"]},
                    )
                    collection_sources.setdefault("mac_addresses", []).append(
                        mac_address
                    )
            bgp = device.get("bgp", {})
            for session in [
                *device.get("bgp_sessions", []),
                *bgp.get("sessions", []),
            ]:
                session.setdefault("device", device["name"])
                if bgp.get("local_as") is not None:
                    session.setdefault("local_as", bgp["local_as"])
                collection_sources.setdefault("bgp_sessions", []).append(session)
        for prefix in target_state.get("prefixes", []):
            collection_sources.setdefault("ip_addresses", []).extend(
                prefix.get("ip_addresses", [])
            )
        for vrf in target_state.get("vrfs", []):
            for field in ("import_targets", "export_targets"):
                for target in vrf.get(field, []):
                    target = {"name": target} if isinstance(target, str) else target
                    if not any(
                        item["name"] == target["name"]
                        for item in collection_sources.setdefault("route_targets", [])
                    ):
                        collection_sources["route_targets"].append(target)

        ordered_collections = [
            collection
            for collection in CREATE_ORDER
            if collection in collection_sources
        ]
        ordered_collections.extend(
            collection
            for collection in collection_sources
            if collection not in ordered_collections
        )

        for collection in ordered_collections:
            object_type = COLLECTION_OBJECT_TYPES[collection]
            endpoint = _get_pynetbox_accessor(nb, object_type)
            create_payloads = []
            update_payloads = []
            create_labels = []
            update_labels = []

            for source in collection_sources[collection]:
                if not isinstance(source, dict):
                    continue
                payload = {
                    field: value
                    for field, value in source.items()
                    if field not in NESTED_FIELDS.get(collection, ())
                }
                special_filters = None
                special_label = None
                if collection == "interfaces":
                    for field in ("untagged_vlan", "tagged_vlans"):
                        references = payload.get(field)
                        if references is None:
                            continue
                        references = (
                            references if isinstance(references, list) else [references]
                        )
                        resolved = []
                        for reference in references:
                            if isinstance(reference, int):
                                vlan = nb.ipam.vlans.get(reference)
                            else:
                                vlan_filters = dict(reference)
                                if "group" in vlan_filters:
                                    vlan_filters["group__name"] = vlan_filters.pop(
                                        "group"
                                    )
                                vlan = nb.ipam.vlans.get(**vlan_filters)
                            if not vlan:
                                raise ValueError(
                                    f"Unable to resolve interface VLAN {reference}"
                                )
                            resolved.append(vlan.id)
                        payload[field] = (
                            resolved if field == "tagged_vlans" else resolved[0]
                        )
                if collection == "vrfs":
                    for field in ("import_targets", "export_targets"):
                        if field not in payload:
                            continue
                        payload[field] = [
                            nb.ipam.route_targets.get(
                                name=(
                                    target["name"]
                                    if isinstance(target, dict)
                                    else target
                                )
                            ).id
                            for target in payload[field]
                        ]
                if collection == "prefixes" and payload.get("site"):
                    site_name = (
                        payload["site"]["name"]
                        if isinstance(payload["site"], dict)
                        else payload["site"]
                    )
                    site = nb.dcim.sites.get(name=site_name)
                    if not site:
                        raise ValueError(f"Unable to resolve prefix site '{site_name}'")
                    payload.pop("site")
                    payload["scope_type"] = "dcim.site"
                    payload["scope_id"] = site.id
                if collection == "asn_ranges" and payload.get("site"):
                    site = nb.dcim.sites.get(name=payload.pop("site"))
                    if not site:
                        raise ValueError("Unable to resolve ASN range site scope")
                    rir = nb.ipam.rirs.get(name=payload["rir"])
                    if not rir:
                        raise ValueError(
                            f"Unable to resolve ASN range RIR '{payload['rir']}'"
                        )
                    payload["rir"] = rir.id
                    payload["scope_type"] = "dcim.site"
                    payload["scope_id"] = site.id
                if collection == "vlan_groups" and payload.get("scope"):
                    if payload.get("scope_type") != "dcim.site":
                        raise ValueError("VLAN group scope must use 'dcim.site'")
                    site = nb.dcim.sites.get(name=payload.pop("scope"))
                    if not site:
                        raise ValueError("Unable to resolve VLAN group site scope")
                    payload["scope_id"] = site.id
                if collection in ("connections", "cables"):
                    for side in ("a_terminations", "b_terminations"):
                        resolved_terminations = []
                        for termination in payload[side]:
                            termination_type = termination.get(
                                "termination_type", "dcim.interface"
                            )
                            termination_endpoints = {
                                "dcim.interface": "dcim.interfaces",
                                "dcim.consoleport": "dcim.console-ports",
                                "dcim.consoleserverport": "dcim.console-server-ports",
                                "dcim.frontport": "dcim.front-ports",
                                "dcim.rearport": "dcim.rear-ports",
                                "dcim.powerport": "dcim.power-ports",
                                "dcim.poweroutlet": "dcim.power-outlets",
                            }
                            termination_endpoint = _get_pynetbox_accessor(
                                nb, termination_endpoints[termination_type]
                            )
                            termination_objects = self.bulk_filter(
                                termination_endpoint,
                                device=termination["device"],
                                name=termination["interface"],
                            )
                            if len(termination_objects) != 1:
                                raise ValueError(
                                    f"Unable to resolve {side} termination "
                                    f"'{termination['device']}:{termination['interface']}'"
                                )
                            resolved_terminations.append(
                                {
                                    "object_type": termination_type,
                                    "object_id": termination_objects[0].id,
                                }
                            )
                        payload[side] = resolved_terminations
                elif (
                    collection in ("ip_addresses", "mac_addresses")
                    and "interface" in source
                ):
                    interface = nb.dcim.interfaces.get(
                        device=source["interface"]["device"],
                        name=source["interface"]["name"],
                    )
                    if not interface:
                        raise ValueError(
                            f"Unable to resolve {collection} interface {source['interface']}"
                        )
                    payload.pop("interface")
                    payload["assigned_object_type"] = "dcim.interface"
                    payload["assigned_object_id"] = interface.id
                elif collection == "l2vpn_terminations":
                    l2vpn = nb.vpn.l2vpns.get(name=source["l2vpn"])
                    interface = nb.dcim.interfaces.get(
                        device=source["interface"]["device"],
                        name=source["interface"]["name"],
                    )
                    if not l2vpn or not interface:
                        raise ValueError(
                            f"Unable to resolve L2VPN termination {source}"
                        )
                    payload = {
                        key: value
                        for key, value in payload.items()
                        if key not in ("l2vpn", "interface")
                    }
                    payload.update(
                        {
                            "l2vpn": l2vpn.id,
                            "assigned_object_type": "dcim.interface",
                            "assigned_object_id": interface.id,
                        }
                    )
                    special_filters = {
                        "l2vpn_id": l2vpn.id,
                        "interface_id": interface.id,
                    }
                    special_label = (
                        f"{source['l2vpn']}:"
                        f"{source['interface']['device']}:"
                        f"{source['interface']['name']}"
                    )
                elif collection in (
                    "vrrp_group_assignments",
                    "fhrp_group_assignments",
                ):
                    group = nb.ipam.fhrp_groups.get(name=source["group"])
                    interface = nb.dcim.interfaces.get(
                        device=source["interface"]["device"],
                        name=source["interface"]["name"],
                    )
                    if not group or not interface:
                        raise ValueError(f"Unable to resolve VRRP assignment {source}")
                    payload = {
                        "group": group.id,
                        "interface_type": "dcim.interface",
                        "interface_id": interface.id,
                        "priority": source.get("priority", 100),
                    }
                    special_filters = {
                        "group_id": group.id,
                        "interface_id": interface.id,
                    }
                    special_label = (
                        f"{source['group']}:"
                        f"{source['interface']['device']}:"
                        f"{source['interface']['name']}"
                    )
                slug_source = SLUG_FIELDS.get(collection)
                if slug_source and slug_source in payload and "slug" not in payload:
                    payload["slug"] = slugify(str(payload[slug_source]))
                for field, lookup_field in RELATION_FIELDS.get(collection, {}).items():
                    if field in payload and isinstance(payload[field], str):
                        payload[field] = {lookup_field: payload[field]}

                identity_fields = IDENTITY_FIELDS.get(collection)
                if identity_fields is None:
                    identity_fields = next(
                        (
                            (field,)
                            for field in (
                                "name",
                                "slug",
                                "model",
                                "prefix",
                                "address",
                                "asn",
                                "vid",
                                "cid",
                            )
                            if field in source
                        ),
                        None,
                    )
                if identity_fields is None:
                    raise ValueError(
                        f"Unable to identify {collection} object from {source}"
                    )

                filters = special_filters or {}
                for field in (() if special_filters else identity_fields):
                    if source.get(field) is None:
                        continue
                    value = source[field]
                    relation_identity = IDENTITY_RELATIONS.get((collection, field))
                    if relation_identity:
                        related_type, filter_field = relation_identity
                        lookup_field = RELATION_FIELDS[collection][field]
                        lookup_value = (
                            value[lookup_field] if isinstance(value, dict) else value
                        )
                        related = self.bulk_filter(
                            _get_pynetbox_accessor(nb, related_type),
                            **{lookup_field: lookup_value},
                        )
                        if len(related) != 1:
                            raise ValueError(
                                f"Unable to resolve {collection}.{field} "
                                f"reference '{lookup_value}'"
                            )
                        filters[filter_field] = related[0].id
                    elif isinstance(value, dict):
                        lookup_field = RELATION_FIELDS.get(collection, {}).get(field)
                        if lookup_field and lookup_field in value:
                            filters[field] = value[lookup_field]
                        else:
                            for key, nested_value in value.items():
                                filters[f"{field}__{key}"] = nested_value
                    elif field in RELATION_FIELDS.get(collection, {}):
                        filters[field] = value
                    else:
                        filters[field] = value
                if not filters:
                    raise ValueError(
                        f"Unable to build identity for {collection} object from {source}"
                    )

                matches = self.bulk_filter(endpoint, **filters)
                if (
                    not matches
                    and collection in ("prefixes", "ip_addresses")
                    and source.get("vrf") is not None
                    and source.get("description") is not None
                ):
                    address_field = "prefix" if collection == "prefixes" else "address"
                    matches = self.bulk_filter(
                        endpoint,
                        **{
                            address_field: source[address_field],
                            "description": source["description"],
                        },
                    )
                if len(matches) > 1:
                    raise ValueError(
                        f"Ambiguous {collection} identity {filters}: "
                        f"matched {len(matches)} objects"
                    )

                label = special_label or str(
                    source.get("name")
                    or source.get("model")
                    or source.get("prefix")
                    or source.get("address")
                    or source.get("mac_address")
                    or source.get("asn")
                    or source.get("vid")
                    or source.get("cid")
                )
                if not matches:
                    create_payloads.append(payload)
                    create_labels.append(label)
                    ret.diff.setdefault(collection, {})[label] = {
                        "action": "create",
                        "fields": payload,
                    }
                    continue

                current = dict(matches[0])
                changes = {}
                for field, desired in payload.items():
                    if collection in ("connections", "cables") and field in (
                        "a_terminations",
                        "b_terminations",
                    ):
                        continue
                    if collection == "l2vpn_terminations" and field in (
                        "l2vpn",
                        "assigned_object_type",
                        "assigned_object_id",
                    ):
                        continue
                    if collection in (
                        "vrrp_group_assignments",
                        "fhrp_group_assignments",
                    ) and field in ("group", "interface_type", "interface_id"):
                        continue
                    actual = current.get(field)
                    if (
                        collection in ("ip_addresses", "mac_addresses")
                        and field == "assigned_object_id"
                    ):
                        actual = (current.get("assigned_object") or {}).get("id")
                    if collection == "interfaces" and field in (
                        "untagged_vlan",
                        "tagged_vlans",
                    ):
                        if field == "untagged_vlan":
                            actual = (
                                actual.get("id") if isinstance(actual, dict) else None
                            )
                        else:
                            actual = sorted(item["id"] for item in actual or [])
                            desired = sorted(desired)
                    if collection == "vrfs" and field in (
                        "import_targets",
                        "export_targets",
                    ):
                        actual = sorted(item["id"] for item in actual or [])
                        desired = sorted(desired)
                    if isinstance(desired, dict):
                        if not isinstance(actual, dict):
                            actual = (
                                actual.serialize()
                                if hasattr(actual, "serialize")
                                else {}
                            )
                        if any(
                            str(actual.get(key)) != str(value)
                            for key, value in desired.items()
                        ):
                            changes[field] = {"old": actual, "new": desired}
                    else:
                        if collection == "bgp_sessions" and isinstance(actual, dict):
                            bgp_value_fields = {
                                "device": "name",
                                "local_address": "address",
                                "remote_address": "address",
                                "local_as": "asn",
                                "remote_as": "asn",
                            }
                            if field in bgp_value_fields:
                                actual = actual.get(bgp_value_fields[field])
                                if (
                                    field in ("local_address", "remote_address")
                                    and actual
                                ):
                                    actual = str(actual).split("/")[0]
                        if (
                            collection == "interfaces"
                            and field == "untagged_vlan"
                            and isinstance(actual, dict)
                        ):
                            actual = actual.get("id")
                        if isinstance(actual, dict) and "value" in actual:
                            actual = actual["value"]
                        elif hasattr(actual, "value"):
                            actual = actual.value
                        if collection == "asn_ranges" and field == "rir":
                            actual = (
                                actual.get("id")
                                if isinstance(actual, dict)
                                else getattr(actual, "id", actual)
                            )
                    if not isinstance(desired, dict) and actual != desired:
                        changes[field] = {"old": actual, "new": desired}
                if changes:
                    update_payloads.append({"id": matches[0].id, **payload})
                    update_labels.append(label)
                    ret.diff.setdefault(collection, {})[label] = {
                        "action": "update",
                        "fields": changes,
                    }
                else:
                    ret.result["unchanged"].setdefault(collection, []).append(label)

            if create_payloads:
                ret.result["created"].setdefault(collection, []).extend(create_labels)
                if not dry_run:
                    if collection == "interfaces":
                        interfaces_by_device = {}
                        for payload in create_payloads:
                            device = payload["device"]["name"]
                            interfaces_by_device.setdefault(device, []).append(
                                {
                                    field: value
                                    for field, value in payload.items()
                                    if field != "device"
                                }
                            )
                        for device, interfaces_data in interfaces_by_device.items():
                            self.create_device_interfaces(
                                job=job,
                                devices=[device],
                                interfaces_data=interfaces_data,
                                instance=instance,
                                branch=branch,
                            )
                    elif collection == "bgp_sessions":
                        self.create_bgp_peering(
                            job=job,
                            bulk_create=create_payloads,
                            create_reverse=False,
                            instance=instance,
                            branch=branch,
                        )
                    else:
                        self.crud_create(
                            job=job,
                            object_type=object_type,
                            data=create_payloads,
                            instance=instance,
                            branch=branch,
                        )
            if update_payloads:
                ret.result["updated"].setdefault(collection, []).extend(update_labels)
                if not dry_run:
                    if collection == "bgp_sessions":
                        self.update_bgp_peering(
                            job=job,
                            bulk_update=[
                                {
                                    field: value
                                    for field, value in payload.items()
                                    if field != "id"
                                }
                                for payload in update_payloads
                            ],
                            instance=instance,
                            branch=branch,
                        )
                    else:
                        self.crud_update(
                            job=job,
                            object_type=object_type,
                            data=update_payloads,
                            instance=instance,
                            branch=branch,
                        )

        for address, device, interface in pending_ip_assignments:
            if dry_run:
                continue
            nb_interface = nb.dcim.interfaces.get(device=device, name=interface)
            nb_ip = nb.ipam.ip_addresses.get(address=address)
            if not nb_interface or not nb_ip:
                raise ValueError(
                    f"Unable to assign '{address}' to '{device}:{interface}'"
                )
            nb_ip.update(
                {
                    "assigned_object_type": "dcim.interface",
                    "assigned_object_id": nb_interface.id,
                }
            )

        job.event(
            f"netbox design complete: "
            f"{sum(len(items) for items in ret.result['created'].values())} create, "
            f"{sum(len(items) for items in ret.result['updated'].values())} update, "
            f"{sum(len(items) for items in ret.result['unchanged'].values())} unchanged"
        )
        return ret
