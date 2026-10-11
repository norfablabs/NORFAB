"""Render NetBox designs and dispatch supported object collections."""

import inspect
import logging
import os
from copy import deepcopy
from functools import partial
from ipaddress import ip_interface, ip_network
from typing import Any, Union

import yaml
from datamodel_code_generator import DataModelType, InputFileType, generate
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

from norfab.core.worker import Job, Task
from norfab.models import Result
from norfab.utils.text import slugify

from .netbox_models import (
    DesignDeployInput,
    DesignDeployResult,
    DesignDocument,
    NetboxFastApiArgs,
)
from .netbox_worker_utilities import (
    merge_array_values,
    merge_resolved_custom_fields,
)

log = logging.getLogger(__name__)


def flatten_design(design: dict) -> dict:
    """Collect device-owned definitions into flat lists without changing the input.

    Parent device/interface names are added to child records. Named VLAN
    terminations become VLAN definitions and group/VID references. Inline
    relationship definitions become top-level records; identity-only dictionaries
    remain references. No NetBox queries or writes are performed here.
    """
    design = deepcopy(design)
    for device in design.get("devices", []):
        if "custom_function" in device:
            continue
        context = device.pop("local_context_data", None)
        if context is not None:
            record = {
                "device": device["name"],
                "site": device["site"],
                "local_context_data": context,
            }
            if "tenant" in device:
                record["tenant"] = device["tenant"]
            design.setdefault("local_context_data", []).append(record)
        for name, interface in device.pop("interfaces", {}).items():
            design.setdefault("interfaces", []).append(
                {**interface, "name": name, "device": device["name"]}
            )
        for collection in (
            "power_ports",
            "console_ports",
            "power_outlets",
            "console_server_ports",
        ):
            for name, port in device.pop(collection, {}).items():
                design.setdefault(collection, []).append(
                    {**port, "name": name, "device": device["name"]}
                )
        for peering in device.pop("bgp_peerings", []):
            design.setdefault("bgp_peerings", []).append(
                {**peering, "device": device["name"]}
            )

    for interface in design.get("interfaces", []):
        if "custom_function" in interface:
            continue
        device = interface["device"]
        if isinstance(device, dict):
            device = device["name"]
        name = interface["name"]
        for address in interface.pop("ip_addresses", []):
            if "create_ip" in address:
                address["create_ip"].update(device=device, interface=name)
            else:
                address.update(device=device, interface=name)
            design.setdefault("ip_addresses", []).append(address)
        for peering in interface.pop("bgp_peerings", []):
            design.setdefault("bgp_peerings", []).append(
                {
                    **peering,
                    "device": device,
                    "local_interface": name,
                }
            )
        connection = interface.pop("connection", None)
        if connection is not None:
            remote_device = connection.pop("device")
            remote_interface = connection.pop("interface")
            design.setdefault("connections", []).append(
                {
                    **connection,
                    "a_terminations": [{"device": device, "interface": name}],
                    "b_terminations": [
                        {"device": remote_device, "interface": remote_interface}
                    ],
                }
            )
        vrf = interface.get("vrf")
        if isinstance(vrf, dict) and set(vrf) - {"name", "id"}:
            if vrf not in design.setdefault("vrfs", []):
                design["vrfs"].append(vrf)
            interface["vrf"] = {"name": vrf["name"]}
            if "rd" in vrf:
                interface["vrf"]["rd"] = vrf["rd"]
        for field in ("untagged_vlan", "tagged_vlans"):
            vlans = (
                interface.get(field, [])
                if field == "tagged_vlans"
                else [interface.get(field)]
            )
            references = []
            for vlan in vlans:
                if isinstance(vlan, dict) and "name" in vlan and "vid" in vlan:
                    if vlan not in design.setdefault("vlans", []):
                        design["vlans"].append(vlan)
                    references.append(
                        {key: vlan[key] for key in ("group", "vid") if key in vlan}
                    )
                else:
                    references.append(vlan)
            if field in interface:
                interface[field] = (
                    references if field == "tagged_vlans" else references[0]
                )
        vrrp = interface.pop("vrrp", None)
        if vrrp is not None:
            group = {
                key: value
                for key, value in vrrp.items()
                if key not in ("vip", "priority")
            }
            group.setdefault("protocol", "vrrp2")
            group.setdefault("name", f"VRRP {group['group_id']}")
            group["vip"] = vrrp["vip"]
            if group not in design.setdefault("vrrp_groups", []):
                design["vrrp_groups"].append(group)
            design.setdefault("vrrp_group_assignments", []).append(
                {
                    "group_id": group["group_id"],
                    "protocol": group["protocol"],
                    "device": device,
                    "interface": name,
                    "priority": vrrp["priority"],
                }
            )
    for collection, endpoint_name in (
        ("power_ports", "power_port"),
        ("console_ports", "console_port"),
        ("power_outlets", "power_outlet"),
        ("console_server_ports", "console_server_port"),
    ):
        for port in design.get(collection, []):
            if "custom_function" in port:
                continue
            connection = port.pop("connection", None)
            if connection is not None:
                remote_device = connection.pop("device")
                remote_type = next(
                    name
                    for name in (
                        "power_port",
                        "power_outlet",
                        "console_port",
                        "console_server_port",
                    )
                    if name in connection
                )
                remote_name = connection.pop(remote_type)
                design.setdefault("connections", []).append(
                    {
                        **connection,
                        "a_terminations": [
                            {"device": port["device"], endpoint_name: port["name"]}
                        ],
                        "b_terminations": [
                            {"device": remote_device, remote_type: remote_name}
                        ],
                    }
                )
    for group in design.get("vrrp_groups", []):
        if "custom_function" in group:
            continue
        vip = group.pop("vip", None)
        if vip:
            design.setdefault("ip_addresses", []).append(
                {
                    "address": vip,
                    "fhrp_group": {
                        "protocol": group["protocol"],
                        "group_id": group["group_id"],
                    },
                }
            )
        for assignment in group.pop("assignments", []):
            design.setdefault("vrrp_group_assignments", []).append(
                {
                    **assignment,
                    "protocol": group["protocol"],
                    "group_id": group["group_id"],
                }
            )

    # A route target can appear at the top level and in several VRFs or L2VPNs.
    # NetBox identifies it by name, so keep the first definition for that name.
    route_target_names = {
        target["name"]
        for target in design.get("route_targets", [])
        if "custom_function" not in target
    }
    for collection in ("vrfs", "l2vpns"):
        for record in design.get(collection, []):
            if "custom_function" in record:
                continue
            for field in ("import_route_targets", "export_route_targets"):
                for target in record.get(field, []):
                    if (
                        isinstance(target, dict)
                        and "query" not in target
                        and target["name"] not in route_target_names
                    ):
                        design.setdefault("route_targets", []).append(target)
                        route_target_names.add(target["name"])
            if collection == "l2vpns":
                for termination in record.pop("terminations", []):
                    design.setdefault("l2vpn_terminations", []).append(
                        {**termination, "l2vpn": record["name"]}
                    )

    # Collect inline termination VLANs before the VLAN deployment stage.
    vlan_keys = {
        (vlan["group"], vlan["vid"])
        for vlan in design.get("vlans", [])
        if "custom_function" not in vlan and "vid" in vlan
    }
    for termination in design.get("l2vpn_terminations", []):
        if any(
            field in termination for field in ("custom_function", "device", "interface")
        ) or not all(field in termination for field in ("group", "vid", "name")):
            continue
        key = (termination["group"], termination["vid"])
        if key not in vlan_keys:
            design.setdefault("vlans", []).append(
                {
                    field: value
                    for field, value in termination.items()
                    if field != "l2vpn"
                }
            )
            vlan_keys.add(key)
        for field in list(termination):
            if field not in ("l2vpn", "group", "vid"):
                termination.pop(field)

    # Device and interface peerings are now in the top-level collection. Set
    # the design default on every ordinary peering before it reaches the task.
    for peering in design.get("bgp_peerings", []):
        if "custom_function" not in peering:
            peering.setdefault("create_reverse", False)

    # Deploy peer groups before sessions, keeping only their names on peerings.
    for peering in design.get("bgp_peerings", []):
        if "custom_function" in peering:
            continue
        peer_group = peering.get("peer_group")
        if peer_group is None:
            continue
        peer_group = {"name": peer_group} if isinstance(peer_group, str) else peer_group
        if peer_group not in design.setdefault("peer_groups", []):
            design["peer_groups"].append(peer_group)
        peering["peer_group"] = peer_group.get("name")

    # Turn policy names into definitions for the earlier routing-policy stage.
    # The peering processor later converts these dictionaries back to names.
    for peering in design.get("bgp_peerings", []):
        if "custom_function" in peering:
            continue
        for field in ("import_policies", "export_policies"):
            if field not in peering:
                continue
            peering[field] = [
                {"name": policy} if isinstance(policy, str) else policy
                for policy in peering[field]
            ]
            for policy in peering[field]:
                if isinstance(policy, dict):
                    if policy not in design.setdefault("routing_policies", []):
                        design["routing_policies"].append(policy)
    return design


def build_lookup_cache(worker: Any, nb: Any, design: DesignDocument) -> dict:
    """Seed one deployment's reference cache from NetBox objects and fields.

    Handlers add IDs for objects created later. Exclude sites defined by this
    design because the site handler will fetch and cache those itself. Object
    and multiobject custom-field definitions are grouped by applicable type.
    """
    cache = {
        "vlans": {},
        "sites": {},
        "route_targets": {},
        "vrfs": {},
        "l2vpns": {},
        "interfaces": {},
        "power_ports": {},
        "console_ports": {},
        "power_outlets": {},
        "console_server_ports": {},
        "fhrp_groups": {},
        "ip_addresses": {},
        "custom_fields": {},
    }
    # Fetch custom-field definitions to resolve object references, including
    # multiobject arrays, in design records to NetBox object IDs.
    for field in worker.bulk_filter(
        nb.extras.custom_fields, type=["object", "multiobject"]
    ):
        for object_type in field.object_types:
            fields = cache["custom_fields"].setdefault(
                object_type, {"object": [], "multiobject": []}
            )
            fields[field.type.value].append(field)
    # Site handlers cache sites created by this design later, so fetch only
    # references to sites that must already exist in NetBox.
    site_names = {
        record["site"]
        for collection in (design.vlan_groups, design.devices, design.prefixes)
        for record in collection
        if "custom_function" not in record and record.get("site")
    }
    site_names.update(
        name
        for record in design.asns
        if "custom_function" not in record
        for name in (record.get("sites") or [])
    )
    site_names.difference_update(
        record["name"]
        for record in design.sites
        if "custom_function" not in record and "name" in record
    )
    if site_names:
        cache["sites"].update(
            {
                site.name: site.id
                for site in worker.bulk_filter(
                    nb.dcim.sites, name=list(site_names), fields="id,name"
                )
            }
        )

    # Terminations can refer to an L2VPN without a matching L2VPN definition
    # in this design, so include both sources in the lookup.
    l2vpn_names = {
        record["name"]
        for record in design.l2vpns
        if "custom_function" not in record and "name" in record
    }
    l2vpn_names.update(
        record["l2vpn"]
        for record in design.l2vpn_terminations
        if "custom_function" not in record and "l2vpn" in record
    )
    if l2vpn_names:
        cache["l2vpns"].update(
            {
                item.name: item.id
                for item in worker.bulk_filter(
                    nb.vpn.l2vpns, name=list(l2vpn_names), fields="id,name"
                )
            }
        )

    # Group and VID identify a VLAN; VID alone may match multiple groups.
    vlan_keys = {
        (record["group"], record["vid"])
        for record in design.vlans
        if "custom_function" not in record and "vid" in record
    }
    for record in design.interfaces:
        if "custom_function" in record:
            continue
        for vlan in record.get("tagged_vlans", []):
            vlan_keys.add((vlan["group"], vlan["vid"]))
        if isinstance(record.get("untagged_vlan"), dict):
            vlan = record["untagged_vlan"]
            vlan_keys.add((vlan["group"], vlan["vid"]))
    for record in design.prefixes:
        if "custom_function" in record:
            continue
        if isinstance(record.get("vlan"), dict) and "group" in record["vlan"]:
            vlan = record["vlan"]
            vlan_keys.add((vlan["group"], vlan["vid"]))
    for record in design.l2vpn_terminations:
        if "custom_function" in record:
            continue
        if "group" in record:
            vlan_keys.add((record["group"], record["vid"]))
    if vlan_keys:
        for vlan in worker.bulk_filter(
            nb.ipam.vlans,
            vid=list({vid for _, vid in vlan_keys}),
            fields="id,vid,name,group,tags,custom_fields",
        ):
            if vlan.group and (vlan.group.name, vlan.vid) in vlan_keys:
                cache["vlans"][(vlan.group.name, vlan.vid)] = {
                    "id": vlan.id,
                    "name": vlan.name,
                    "tags": vlan.tags,
                    "custom_fields": vlan.custom_fields,
                    "object": vlan,
                }
    return cache


def execute_custom_functions(
    nb: Any,
    context: dict,
    records: list[dict],
    functions: dict,
    dry_run: bool,
    results: dict,
) -> None:
    """Execute a collection's custom calls in order and append their results.

    Pass sibling arguments unchanged, plus context, netbox, and dry_run. Exceptions
    propagate to the deployment error handler; completed results are retained.
    """
    for record in records:
        if "custom_function" not in record:
            continue
        arguments = {
            key: value for key, value in record.items() if key != "custom_function"
        }
        log.info(
            "executing custom design function '%s', dry_run=%s",
            record["custom_function"],
            dry_run,
        )
        value = functions[record["custom_function"]](
            **arguments, context=context, netbox=nb, dry_run=dry_run
        )
        results.setdefault("custom", []).append(
            {"function": record["custom_function"], "result": value}
        )
        log.info("completed custom design function '%s'", record["custom_function"])


def merge_design_array_fields(
    worker: Any,
    nb: Any,
    lookup_cache: dict,
    endpoint: Any,
    object_type: str,
    created: list[dict],
    updated: list[dict],
    array_fields: tuple[str, ...] = (),
    existing_by_id: dict[int, Any] | None = None,
    array_value_attribute: str = "id",
) -> None:
    """Resolve custom-field names and add requested list members on updates.

    Args:
        worker: NetBox worker used to resolve related object names.
        nb: NetBox API for name resolution.
        lookup_cache: Custom-field definitions cached for this deployment.
        endpoint: NetBox endpoint for reading updated objects by ID.
        object_type: NetBox content type of the records.
        created: Create payloads, modified in place.
        updated: Update payloads, modified in place.
        array_fields: Explicit native relationship arrays that accept additions.
        existing_by_id: Existing NetBox records already read by the processor.
        array_value_attribute: Related object attribute expected by the receiving
            task. Most processors send IDs; BGP peering updates send policy names.
    """
    definitions = lookup_cache["custom_fields"].get(object_type, {})
    for record in created:
        if "tags" in record:
            record["tags"] = merge_array_values([], record["tags"], attribute="name")
        if "custom_fields" in record:
            _, record["custom_fields"] = merge_resolved_custom_fields(
                worker,
                nb,
                None,
                record["custom_fields"],
                definitions.get("object", []),
                definitions.get("multiobject", []),
            )
    for record in updated:
        if not any(
            field in record for field in ("tags", "custom_fields", *array_fields)
        ):
            continue
        current = (
            existing_by_id[record["id"]]
            if existing_by_id is not None
            else endpoint.get(record["id"])
        )
        if "tags" in record:
            record["tags"] = merge_array_values(
                current.tags, record["tags"], attribute="name"
            )
        if "custom_fields" in record:
            _, record["custom_fields"] = merge_resolved_custom_fields(
                worker,
                nb,
                current,
                record["custom_fields"],
                definitions.get("object", []),
                definitions.get("multiobject", []),
            )
        for field in array_fields:
            if field in record:
                if array_value_attribute == "name":
                    record[field] = merge_array_values(
                        [item.name for item in getattr(current, field)], record[field]
                    )
                else:
                    record[field] = merge_array_values(
                        getattr(current, field), record[field], attribute="id"
                    )


def process_tenants(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match tenants by name, then bulk-create or bulk-update them.

    Generate a slug for new records only; optional group is a name reference.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    log.debug(
        "process_tenants: processing %d records, dry_run=%s", len(records), dry_run
    )
    names = [record["name"] for record in records]
    existing = (
        {
            tenant.name: tenant
            for tenant in worker.bulk_filter(
                nb.tenancy.tenants, name=names, fields="id,name"
            )
        }
        if names
        else {}
    )
    created = [record for record in records if record["name"] not in existing]
    updated = [
        {**record, "id": existing[record["name"]].id}
        for record in records
        if record["name"] in existing
    ]
    for record in created:
        record.setdefault("slug", slugify(record["name"]))
    created = [dict(record) for record in created]
    for record in created + updated:
        for field in ("group",):
            if record.get(field) is not None:
                record[field] = {"name": record[field]}
    merge_design_array_fields(
        worker, nb, lookup_cache, nb.tenancy.tenants, "tenancy.tenant", created, updated
    )
    if not dry_run:
        if created:
            nb.tenancy.tenants.create(created)
        if updated:
            nb.tenancy.tenants.update(updated)
    changes = {
        "created": [record["name"] for record in created],
        "updated": [record["name"] for record in updated],
    }
    return changes


def process_regions(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match regions by name and bulk-write supplied fields.

    Parent is a region name. The handler does not sort parent/child records;
    a referenced parent must already exist when NetBox processes the write.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    log.debug(
        "process_regions: processing %d records, dry_run=%s", len(records), dry_run
    )
    names = [record["name"] for record in records]
    existing = (
        {
            region.name: region
            for region in worker.bulk_filter(
                nb.dcim.regions, name=names, fields="id,name"
            )
        }
        if names
        else {}
    )
    created = [record for record in records if record["name"] not in existing]
    updated = [
        {**record, "id": existing[record["name"]].id}
        for record in records
        if record["name"] in existing
    ]
    for record in created:
        record.setdefault("slug", slugify(record["name"]))
    created = [dict(record) for record in created]
    for record in created + updated:
        for field in ("parent",):
            if record.get(field) is not None:
                record[field] = {"name": record[field]}
    merge_design_array_fields(
        worker, nb, lookup_cache, nb.dcim.regions, "dcim.region", created, updated
    )
    if not dry_run:
        if created:
            nb.dcim.regions.create(created)
        if updated:
            nb.dcim.regions.update(updated)
    changes = {
        "created": [record["name"] for record in created],
        "updated": [record["name"] for record in updated],
    }
    return changes


def process_manufacturers(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match manufacturers by name and bulk-write supplied fields.

    New manufacturers receive a generated slug.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    log.debug(
        "process_manufacturers: processing %d records, dry_run=%s",
        len(records),
        dry_run,
    )
    names = [record["name"] for record in records]
    existing = (
        {
            manufacturer.name: manufacturer
            for manufacturer in worker.bulk_filter(
                nb.dcim.manufacturers, name=names, fields="id,name"
            )
        }
        if names
        else {}
    )
    created = [record for record in records if record["name"] not in existing]
    updated = [
        {**record, "id": existing[record["name"]].id}
        for record in records
        if record["name"] in existing
    ]
    for record in created:
        record.setdefault("slug", slugify(record["name"]))
    merge_design_array_fields(
        worker,
        nb,
        lookup_cache,
        nb.dcim.manufacturers,
        "dcim.manufacturer",
        created,
        updated,
    )
    if not dry_run:
        if created:
            nb.dcim.manufacturers.create(created)
        if updated:
            nb.dcim.manufacturers.update(updated)
    changes = {
        "created": [record["name"] for record in created],
        "updated": [record["name"] for record in updated],
    }
    return changes


def process_platforms(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match platforms by name and bulk-write supplied fields.

    Manufacturer, when set, refers to an already existing name.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    log.debug(
        "process_platforms: processing %d records, dry_run=%s", len(records), dry_run
    )
    names = [record["name"] for record in records]
    existing = (
        {
            platform.name: platform
            for platform in worker.bulk_filter(
                nb.dcim.platforms, name=names, fields="id,name"
            )
        }
        if names
        else {}
    )
    created = [record for record in records if record["name"] not in existing]
    updated = [
        {**record, "id": existing[record["name"]].id}
        for record in records
        if record["name"] in existing
    ]
    for record in created:
        record.setdefault("slug", slugify(record["name"]))
    created = [dict(record) for record in created]
    for record in created + updated:
        for field in ("manufacturer",):
            if record.get(field) is not None:
                record[field] = {"name": record[field]}
    merge_design_array_fields(
        worker, nb, lookup_cache, nb.dcim.platforms, "dcim.platform", created, updated
    )
    if not dry_run:
        if created:
            nb.dcim.platforms.create(created)
        if updated:
            nb.dcim.platforms.update(updated)
    changes = {
        "created": [record["name"] for record in created],
        "updated": [record["name"] for record in updated],
    }
    return changes


def process_device_types(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match device types by manufacturer name and model.

    Manufacturer and default platform must exist before this handler runs.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    log.debug(
        "process_device_types: processing %d records, dry_run=%s", len(records), dry_run
    )
    models = [record["model"] for record in records]
    existing = (
        {
            (item.manufacturer.name, item.model): item
            for item in worker.bulk_filter(
                nb.dcim.device_types, model=models, fields="id,model,manufacturer"
            )
        }
        if models
        else {}
    )
    created = []
    updated = []
    for record in records:
        key = (record["manufacturer"], record["model"])
        if key in existing:
            updated.append({**record, "id": existing[key].id})
        else:
            created.append(record)
    for record in created:
        record.setdefault("slug", slugify(record["model"]))
    created = [dict(record) for record in created]
    for record in created + updated:
        for field in ("manufacturer", "default_platform"):
            if record.get(field) is not None:
                record[field] = {"name": record[field]}
    merge_design_array_fields(
        worker,
        nb,
        lookup_cache,
        nb.dcim.device_types,
        "dcim.devicetype",
        created,
        updated,
    )
    if not dry_run:
        if created:
            nb.dcim.device_types.create(created)
        if updated:
            nb.dcim.device_types.update(updated)
    changes = {
        "created": [record["model"] for record in created],
        "updated": [record["model"] for record in updated],
    }
    return changes


def process_device_roles(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match device roles by slug and bulk-write supplied fields.

    Use an explicit slug when supplied, otherwise slugify the role name.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    log.debug(
        "process_device_roles: processing %d records, dry_run=%s", len(records), dry_run
    )
    for record in records:
        record.setdefault("slug", slugify(record["name"]))
    slugs = [record["slug"] for record in records]
    existing = (
        {
            role.slug: role
            for role in worker.bulk_filter(
                nb.dcim.device_roles, slug=slugs, fields="id,name,slug"
            )
        }
        if slugs
        else {}
    )
    created = [record for record in records if record["slug"] not in existing]
    updated = [
        {**record, "id": existing[record["slug"]].id}
        for record in records
        if record["slug"] in existing
    ]
    merge_design_array_fields(
        worker,
        nb,
        lookup_cache,
        nb.dcim.device_roles,
        "dcim.devicerole",
        created,
        updated,
    )
    if not dry_run:
        if created:
            nb.dcim.device_roles.create(created)
        if updated:
            nb.dcim.device_roles.update(updated)
    changes = {
        "created": [record["name"] for record in created],
        "updated": [record["name"] for record in updated],
    }
    return changes


def process_sites(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match sites by name, bulk-write them, and cache their IDs.

    Region and tenant are existing name references for NetBox to resolve.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    log.debug("process_sites: processing %d records, dry_run=%s", len(records), dry_run)
    names = [record["name"] for record in records]
    existing = (
        {
            site.name: site
            for site in worker.bulk_filter(nb.dcim.sites, name=names, fields="id,name")
        }
        if names
        else {}
    )
    lookup_cache["sites"].update({name: site.id for name, site in existing.items()})
    created = [record for record in records if record["name"] not in existing]
    updated = [
        {**record, "id": existing[record["name"]].id}
        for record in records
        if record["name"] in existing
    ]
    for record in created:
        record.setdefault("slug", slugify(record["name"]))
    created = [dict(record) for record in created]
    for record in created + updated:
        for field in ("region", "tenant"):
            if record.get(field) is not None:
                record[field] = {"name": record[field]}
    merge_design_array_fields(
        worker, nb, lookup_cache, nb.dcim.sites, "dcim.site", created, updated
    )
    if not dry_run:
        if created:
            lookup_cache["sites"].update(
                {item.name: item.id for item in nb.dcim.sites.create(created)}
            )
        if updated:
            nb.dcim.sites.update(updated)
    changes = {
        "created": [record["name"] for record in created],
        "updated": [record["name"] for record in updated],
    }
    return changes


def process_roles(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match IPAM roles by name and bulk-write supplied fields.

    Generate a slug only for new roles.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    log.debug("process_roles: processing %d records, dry_run=%s", len(records), dry_run)
    names = [record["name"] for record in records]
    existing = (
        {
            role.name: role
            for role in worker.bulk_filter(nb.ipam.roles, name=names, fields="id,name")
        }
        if names
        else {}
    )
    created = [record for record in records if record["name"] not in existing]
    updated = [
        {**record, "id": existing[record["name"]].id}
        for record in records
        if record["name"] in existing
    ]
    for record in created:
        record.setdefault("slug", slugify(record["name"]))
    merge_design_array_fields(
        worker, nb, lookup_cache, nb.ipam.roles, "ipam.role", created, updated
    )
    if not dry_run:
        if created:
            nb.ipam.roles.create(created)
        if updated:
            nb.ipam.roles.update(updated)
    changes = {
        "created": [record["name"] for record in created],
        "updated": [record["name"] for record in updated],
    }
    return changes


def process_rirs(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match RIRs by name and bulk-write supplied fields.

    Generate a slug only for new RIRs.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    log.debug("process_rirs: processing %d records, dry_run=%s", len(records), dry_run)
    names = [record["name"] for record in records]
    existing = (
        {
            rir.name: rir
            for rir in worker.bulk_filter(nb.ipam.rirs, name=names, fields="id,name")
        }
        if names
        else {}
    )
    created = [record for record in records if record["name"] not in existing]
    updated = [
        {**record, "id": existing[record["name"]].id}
        for record in records
        if record["name"] in existing
    ]
    for record in created:
        record.setdefault("slug", slugify(record["name"]))
    merge_design_array_fields(
        worker, nb, lookup_cache, nb.ipam.rirs, "ipam.rir", created, updated
    )
    if not dry_run:
        if created:
            nb.ipam.rirs.create(created)
        if updated:
            nb.ipam.rirs.update(updated)
    changes = {
        "created": [record["name"] for record in created],
        "updated": [record["name"] for record in updated],
    }
    return changes


def process_vlan_groups(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match VLAN groups by name and resolve an optional Netbox scope.

    Supports rack, location, site, site group, region, cluster, and cluster
    group scopes. Site disambiguates rack or location names when supplied
    alongside either. Referenced scopes must already exist.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    log.debug(
        "process_vlan_groups: processing %d records, dry_run=%s", len(records), dry_run
    )
    names = [record["name"] for record in records]
    existing = (
        {
            group.name: group
            for group in worker.bulk_filter(
                nb.ipam.vlan_groups, name=names, fields="id,name"
            )
        }
        if names
        else {}
    )
    created = [dict(record) for record in records if record["name"] not in existing]
    updated = [
        {**record, "id": existing[record["name"]].id}
        for record in records
        if record["name"] in existing
    ]
    for record in created:
        record.setdefault("slug", slugify(record["name"]))
    for record in created + updated:
        for field, endpoint, scope_type in (
            ("rack", nb.dcim.racks, "dcim.rack"),
            ("location", nb.dcim.locations, "dcim.location"),
            ("site", nb.dcim.sites, "dcim.site"),
            ("site_group", nb.dcim.site_groups, "dcim.sitegroup"),
            ("region", nb.dcim.regions, "dcim.region"),
            ("cluster", nb.virtualization.clusters, "virtualization.cluster"),
            (
                "cluster_group",
                nb.virtualization.cluster_groups,
                "virtualization.clustergroup",
            ),
        ):
            if record.get(field):
                filters = {"name": record[field]}
                if field in ("rack", "location") and record.get("site"):
                    site_id = lookup_cache["sites"].get(record["site"])
                    if site_id is None:
                        site = nb.dcim.sites.get(name=record["site"])
                        site_id = site.id if site else None
                    if site_id is None:
                        raise ValueError(
                            f"vlan group site '{record['site']}' not found"
                        )
                    filters["site_id"] = site_id
                scope_id = (
                    lookup_cache["sites"].get(record[field])
                    if field == "site"
                    else None
                )
                scope = endpoint.get(**filters) if scope_id is None else None
                if scope_id is None and scope is None:
                    raise ValueError(
                        f"vlan group scope {field} '{record[field]}' not found"
                    )
                record.update(scope_type=scope_type, scope_id=scope_id or scope.id)
                break
        for field in (
            "rack",
            "location",
            "site",
            "site_group",
            "region",
            "cluster",
            "cluster_group",
        ):
            record.pop(field, None)
    merge_design_array_fields(
        worker,
        nb,
        lookup_cache,
        nb.ipam.vlan_groups,
        "ipam.vlangroup",
        created,
        updated,
    )
    if not dry_run:
        if created:
            nb.ipam.vlan_groups.create(created)
        if updated:
            nb.ipam.vlan_groups.update(updated)
    changes = {
        "created": [record["name"] for record in created],
        "updated": [record["name"] for record in updated],
    }
    return changes


def process_asn_ranges(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match ASN ranges by name and bulk-write supplied bounds.

    An optional RIR name must refer to an existing RIR.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    log.debug(
        "process_asn_ranges: processing %d records, dry_run=%s", len(records), dry_run
    )
    names = [record["name"] for record in records]
    existing = (
        {
            asn_range.name: asn_range
            for asn_range in worker.bulk_filter(
                nb.ipam.asn_ranges, name=names, fields="id,name"
            )
        }
        if names
        else {}
    )
    created = [record for record in records if record["name"] not in existing]
    updated = [
        {**record, "id": existing[record["name"]].id}
        for record in records
        if record["name"] in existing
    ]
    for record in created:
        record.setdefault("slug", slugify(record["name"]))
    created = [dict(record) for record in created]
    for record in created + updated:
        for field in ("rir",):
            if record.get(field) is not None:
                record[field] = {"name": record[field]}
    merge_design_array_fields(
        worker, nb, lookup_cache, nb.ipam.asn_ranges, "ipam.asnrange", created, updated
    )
    if not dry_run:
        if created:
            nb.ipam.asn_ranges.create(created)
        if updated:
            nb.ipam.asn_ranges.update(updated)
    changes = {
        "created": [record["name"] for record in created],
        "updated": [record["name"] for record in updated],
    }
    return changes


def process_rack_roles(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match rack roles by name and bulk-write supplied fields.

    Generate a slug only for new roles.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    log.debug(
        "process_rack_roles: processing %d records, dry_run=%s", len(records), dry_run
    )
    names = [record["name"] for record in records]
    existing = (
        {
            role.name: role
            for role in worker.bulk_filter(
                nb.dcim.rack_roles, name=names, fields="id,name"
            )
        }
        if names
        else {}
    )
    created = [record for record in records if record["name"] not in existing]
    updated = [
        {**record, "id": existing[record["name"]].id}
        for record in records
        if record["name"] in existing
    ]
    for record in created:
        record.setdefault("slug", slugify(record["name"]))
    merge_design_array_fields(
        worker, nb, lookup_cache, nb.dcim.rack_roles, "dcim.rackrole", created, updated
    )
    if not dry_run:
        if created:
            nb.dcim.rack_roles.create(created)
        if updated:
            nb.dcim.rack_roles.update(updated)
    changes = {
        "created": [record["name"] for record in created],
        "updated": [record["name"] for record in updated],
    }
    return changes


def process_route_targets(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match route targets by name and cache IDs for later VRF writes.

    Tenant, when supplied, is resolved by name.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    log.debug(
        "process_route_targets: processing %d records, dry_run=%s",
        len(records),
        dry_run,
    )
    names = [record["name"] for record in records]
    existing = (
        {
            item.name: item
            for item in worker.bulk_filter(
                nb.ipam.route_targets, name=names, fields="id,name"
            )
        }
        if names
        else {}
    )
    targets = lookup_cache["route_targets"]
    targets.update({name: item.id for name, item in existing.items()})
    created = [dict(record) for record in records if record["name"] not in existing]
    updated = [
        {**record, "id": existing[record["name"]].id}
        for record in records
        if record["name"] in existing
    ]
    for record in created + updated:
        if record.get("tenant") is not None:
            record["tenant"] = {"name": record["tenant"]}
    merge_design_array_fields(
        worker,
        nb,
        lookup_cache,
        nb.ipam.route_targets,
        "ipam.routetarget",
        created,
        updated,
    )
    if not dry_run:
        if created:
            targets.update(
                {item.name: item.id for item in nb.ipam.route_targets.create(created)}
            )
        if updated:
            nb.ipam.route_targets.update(updated)
    return {
        "created": [record["name"] for record in created],
        "updated": [record["name"] for record in updated],
    }


def process_vrfs(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match VRFs by name and RD, resolving route-target lists to IDs.

    Query entries select all existing matches and fail when none match.
    Targets are created earlier or fetched in one batch; cache VRF IDs for
    prefix and IP identity checks. An absent RD is part of the identity.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    # Queries select existing targets; named entries keep their deployment behavior.
    for record in records:
        for field in ("import_route_targets", "export_route_targets"):
            if field not in record:
                continue
            references = {}
            for target in record[field]:
                if "query" in target:
                    matches = list(nb.ipam.route_targets.filter(**target["query"]))
                    if not matches:
                        raise ValueError(
                            f"route-target query matched no targets: {target['query']}"
                        )
                    for match in matches:
                        lookup_cache["route_targets"][match.name] = match.id
                        references[match.name] = {"name": match.name}
                else:
                    references[target["name"]] = target
            record[field] = list(references.values())

    log.debug("process_vrfs: processing %d records, dry_run=%s", len(records), dry_run)
    target_names = list(
        {
            target["name"]
            for record in records
            for field in ("import_route_targets", "export_route_targets")
            for target in record.get(field, [])
        }
    )
    targets = lookup_cache["route_targets"]
    missing_targets = set(target_names) - targets.keys()
    if missing_targets:
        targets.update(
            {
                target.name: target.id
                for target in worker.bulk_filter(
                    nb.ipam.route_targets, name=list(missing_targets), fields="id,name"
                )
            }
        )
    names = [record["name"] for record in records]
    existing = (
        {
            (item.name, item.rd): item
            for item in worker.bulk_filter(
                nb.ipam.vrfs, name=names, fields="id,name,rd"
            )
        }
        if names
        else {}
    )
    vrfs = lookup_cache["vrfs"]
    vrfs.update({key: item.id for key, item in existing.items()})
    created = []
    updated = []
    for record in records:
        key = (record["name"], record.get("rd"))
        if key in existing:
            updated.append({**record, "id": existing[key].id})
        else:
            created.append(record)
    created = [dict(record) for record in created]
    for record in created + updated:
        for field in ("tenant",):
            if record.get(field) is not None:
                record[field] = {"name": record[field]}
    for record in created + updated:
        for source, destination in (
            ("import_route_targets", "import_targets"),
            ("export_route_targets", "export_targets"),
        ):
            if source in record:
                record[destination] = [
                    targets.get(target["name"]) if dry_run else targets[target["name"]]
                    for target in record.pop(source)
                ]
    merge_design_array_fields(
        worker,
        nb,
        lookup_cache,
        nb.ipam.vrfs,
        "ipam.vrf",
        created,
        updated,
        ("import_targets", "export_targets"),
    )
    if not dry_run:
        if created:
            vrfs.update(
                {(item.name, item.rd): item.id for item in nb.ipam.vrfs.create(created)}
            )
        if updated:
            nb.ipam.vrfs.update(updated)
    changes = {
        "created": [record["name"] for record in created],
        "updated": [record["name"] for record in updated],
    }
    return changes


def process_l2vpns(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match L2VPNs by name and resolve their import and export route targets.

    Query entries select all existing matches and fail when none match.
    Inline targets are deployed earlier. New L2VPN IDs are cached for
    termination writes; dry runs report planned changes without writing.

    Args:
        worker: NetBox worker used for bulk reads.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened L2VPN records.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job; not used by this handler.
        instance: NetBox instance; not used by this handler.
        branch: NetBox branch; not used by this handler.

    Returns:
        dict: L2VPN names grouped under ``created`` and ``updated``.
    """
    # Queries select existing targets; named entries keep their deployment behavior.
    for record in records:
        for field in ("import_route_targets", "export_route_targets"):
            if field not in record:
                continue
            references = {}
            for target in record[field]:
                if "query" in target:
                    matches = list(nb.ipam.route_targets.filter(**target["query"]))
                    if not matches:
                        raise ValueError(
                            f"route-target query matched no targets: {target['query']}"
                        )
                    for match in matches:
                        lookup_cache["route_targets"][match.name] = match.id
                        references[match.name] = {"name": match.name}
                else:
                    references[target["name"]] = target
            record[field] = list(references.values())

    l2vpns = lookup_cache["l2vpns"]
    targets = lookup_cache["route_targets"]
    target_names = {
        target["name"]
        for record in records
        for field in ("import_route_targets", "export_route_targets")
        for target in record.get(field, [])
    }
    missing = target_names - targets.keys()
    if missing:
        targets.update(
            {
                item.name: item.id
                for item in worker.bulk_filter(
                    nb.ipam.route_targets, name=list(missing), fields="id,name"
                )
            }
        )
    created, updated = [], []
    for source in records:
        payload = dict(source)
        name = payload["name"]
        if name in l2vpns:
            payload["id"] = l2vpns[name]
            updated.append(payload)
        else:
            payload.setdefault("slug", slugify(name))
            created.append(payload)
        if payload.get("tenant") is not None:
            payload["tenant"] = {"name": payload["tenant"]}
        for source_field, destination in (
            ("import_route_targets", "import_targets"),
            ("export_route_targets", "export_targets"),
        ):
            if source_field in payload:
                payload[destination] = [
                    targets.get(target["name"]) if dry_run else targets[target["name"]]
                    for target in payload.pop(source_field)
                ]
    merge_design_array_fields(
        worker,
        nb,
        lookup_cache,
        nb.vpn.l2vpns,
        "vpn.l2vpn",
        created,
        updated,
        ("import_targets", "export_targets"),
    )
    if not dry_run:
        if created:
            l2vpns.update(
                {item.name: item.id for item in nb.vpn.l2vpns.create(created)}
            )
        if updated:
            nb.vpn.l2vpns.update(updated)
    return {
        "created": [record["name"] for record in created],
        "updated": [record["name"] for record in updated],
    }


def process_l2vpn_terminations(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Attach L2VPNs to device interfaces or VLANs without moving attachments.

    NetBox permits only one L2VPN termination per attached object. Existing
    attachments to a different L2VPN raise an error instead of being moved.

    Args:
        worker: NetBox worker used for bulk reads.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened termination records with an L2VPN name and attachment.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job; not used by this handler.
        instance: NetBox instance; not used by this handler.
        branch: NetBox branch; not used by this handler.

    Returns:
        dict: Attachment identities grouped under ``created`` and ``updated``.

    Raises:
        ValueError: If an attachment belongs to another L2VPN.
        KeyError: If a referenced L2VPN, interface, or VLAN does not exist.
    """
    l2vpns = lookup_cache["l2vpns"]
    missing_l2vpns = {record["l2vpn"] for record in records} - l2vpns.keys()
    if missing_l2vpns:
        l2vpns.update(
            {
                item.name: item.id
                for item in worker.bulk_filter(
                    nb.vpn.l2vpns, name=list(missing_l2vpns), fields="id,name"
                )
            }
        )
    interfaces = lookup_cache["interfaces"]
    missing_devices = {
        record["device"]
        for record in records
        if "device" in record
        and (record["device"], record["interface"]) not in interfaces
    }
    if missing_devices:
        interfaces.update(
            {
                (item.device.name, item.name): item
                for item in worker.bulk_filter(
                    nb.dcim.interfaces,
                    device=list(missing_devices),
                    fields="id,name,device",
                )
            }
        )
    assignments = []
    for record in records:
        if "device" in record:
            object_type = "dcim.interface"
            key = (record["device"], record["interface"])
            if key in interfaces:
                object_id = interfaces[key].id
            elif dry_run:
                object_id = None
            else:
                raise KeyError(f"interface {key} does not exist")
            identity = f"{record['l2vpn']}:{record['device']}:{record['interface']}"
        else:
            object_type = "ipam.vlan"
            key = (record["group"], record["vid"])
            vlan = lookup_cache["vlans"].get(key)
            if vlan:
                object_id = vlan["id"]
            elif dry_run:
                object_id = None
            else:
                raise KeyError(f"VLAN {key} does not exist")
            identity = f"{record['l2vpn']}:{record['group']}:{record['vid']}"
        if record["l2vpn"] not in l2vpns and not dry_run:
            raise KeyError(f"L2VPN '{record['l2vpn']}' does not exist")
        assignments.append((record, object_type, object_id, identity))
    existing = {}
    for object_type, filter_name in (
        ("dcim.interface", "interface_id"),
        ("ipam.vlan", "vlan_id"),
    ):
        object_ids = list(
            {item[2] for item in assignments if item[1] == object_type and item[2]}
        )
        if object_ids:
            existing.update(
                {
                    (item.assigned_object_type, item.assigned_object_id): item
                    for item in worker.bulk_filter(
                        nb.vpn.l2vpn_terminations,
                        fields="id,l2vpn,assigned_object_type,assigned_object_id",
                        **{filter_name: object_ids},
                    )
                }
            )
    created, updated = [], []
    changes = {"created": [], "updated": []}
    for record, object_type, object_id, identity in assignments:
        previous = existing.get((object_type, object_id))
        if previous and previous.l2vpn.name != record["l2vpn"]:
            raise ValueError(f"{identity} is already attached to {previous.l2vpn.name}")
        payload = {
            key: value
            for key, value in record.items()
            if key not in {"l2vpn", "device", "interface", "group", "vid"}
        }
        payload.update(
            l2vpn=l2vpns.get(record["l2vpn"]) if dry_run else l2vpns[record["l2vpn"]],
            assigned_object_type=object_type,
            assigned_object_id=object_id,
        )
        if previous:
            updated.append({**payload, "id": previous.id})
            changes["updated"].append(identity)
        else:
            created.append(payload)
            changes["created"].append(identity)
    merge_design_array_fields(
        worker,
        nb,
        lookup_cache,
        nb.vpn.l2vpn_terminations,
        "vpn.l2vpntermination",
        created,
        updated,
    )
    if not dry_run:
        if created:
            nb.vpn.l2vpn_terminations.create(created)
        if updated:
            nb.vpn.l2vpn_terminations.update(updated)
    return changes


def process_racks(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match racks by site name and rack name.

    Site, role, and tenant names are NetBox relationship references.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    log.debug("process_racks: processing %d records, dry_run=%s", len(records), dry_run)
    names = [record["name"] for record in records]
    existing = (
        {
            (item.site.name, item.name): item
            for item in worker.bulk_filter(
                nb.dcim.racks, name=names, fields="id,name,site"
            )
        }
        if names
        else {}
    )
    created = []
    updated = []
    for record in records:
        key = (record["site"], record["name"])
        if key in existing:
            updated.append({**record, "id": existing[key].id})
        else:
            created.append(record)
    created = [dict(record) for record in created]
    for record in created + updated:
        for field in ("site", "role", "tenant"):
            if record.get(field) is not None:
                record[field] = {"name": record[field]}
    merge_design_array_fields(
        worker, nb, lookup_cache, nb.dcim.racks, "dcim.rack", created, updated
    )
    if not dry_run:
        if created:
            nb.dcim.racks.create(created)
        if updated:
            nb.dcim.racks.update(updated)
    changes = {
        "created": [record["name"] for record in created],
        "updated": [record["name"] for record in updated],
    }
    return changes


def process_devices(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match devices by name, using tenant only to resolve duplicate names.

    Nested interfaces and peerings are flattened before this handler; it
    writes devices only. A unique name matches regardless of site or tenant;
    supplied site and tenant are update attributes. Duplicate names require
    a supplied tenant that selects exactly one device, otherwise matching fails.
    Omitted site leaves an existing device's site unchanged; new devices must
    still supply the attributes required by NetBox.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    log.debug(
        "process_devices: processing %d records, dry_run=%s", len(records), dry_run
    )
    names = [record["name"] for record in records]
    site_names = list({record["site"] for record in records if record.get("site")})
    sites = lookup_cache["sites"]
    missing_sites = set(site_names) - sites.keys()
    if missing_sites:
        sites.update(
            {
                item.name: item.id
                for item in worker.bulk_filter(
                    nb.dcim.sites, name=list(missing_sites), fields="id,name"
                )
            }
        )
    existing = (
        list(
            worker.bulk_filter(
                nb.dcim.devices,
                name=names,
                fields="id,name,site,tenant",
            )
        )
        if names
        else []
    )
    created, updated = [], []
    for record in records:
        matches = [item for item in existing if item.name == record["name"]]
        if len(matches) > 1:
            if "tenant" in record:
                matches = [
                    item
                    for item in matches
                    if (item.tenant.name if item.tenant else None) == record["tenant"]
                ]
            if len(matches) != 1:
                raise ValueError(
                    f"ambiguous device {record['name']}: multiple devices matched by name; "
                    "provide a tenant that selects exactly one device"
                )
        if matches:
            updated.append({**record, "id": matches[0].id})
        else:
            created.append(record)
    created = [dict(record) for record in created]
    for record in created + updated:
        for field in ("site", "role", "platform", "tenant"):
            if record.get(field) is not None:
                record[field] = {"name": record[field]}
    for record in created + updated:
        if "device_type" in record:
            device_type = dict(record["device_type"])
            device_type["manufacturer__name"] = device_type.pop("manufacturer")
            record["device_type"] = device_type
    merge_design_array_fields(
        worker, nb, lookup_cache, nb.dcim.devices, "dcim.device", created, updated
    )
    if not dry_run:
        if created:
            nb.dcim.devices.create(created)
        if updated:
            nb.dcim.devices.update(updated)
    changes = {
        "created": [record["name"] for record in created],
        "updated": [record["name"] for record in updated],
    }
    return changes


def process_interfaces(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match interfaces by device and name, then write them in two passes.

    Independent parents are written before interfaces using parent, LAG, or
    bridge links. VLAN IDs and parent IDs come from the deployment cache.
    A dependent interface cannot itself be the parent of another interface
    created in the same deployment; that would require a further pass.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    log.debug(
        "process_interfaces: processing %d records, dry_run=%s", len(records), dry_run
    )
    devices = [record["device"] for record in records]
    existing = (
        {
            (item.device.name, item.name): item
            for item in worker.bulk_filter(
                nb.dcim.interfaces, device=devices, fields="id,name,device,cable"
            )
        }
        if devices
        else {}
    )
    interface_cache = lookup_cache["interfaces"]
    interface_cache.update(existing)
    created, updated = [], []
    changes = {"created": [], "updated": []}
    vlan_cache = lookup_cache["vlans"]
    for record, device in zip(records, devices):
        payload = {**record, "device": {"name": device}}
        if isinstance(payload.get("vrf"), str):
            payload["vrf"] = {"name": payload["vrf"]}
        for field in ("parent", "lag", "bridge"):
            payload.pop(field, None)
        for field in ("tagged_vlans", "untagged_vlan"):
            if field not in payload:
                continue
            vlans = payload[field] if field == "tagged_vlans" else [payload[field]]
            references = [
                (
                    vlan_cache.get((vlan["group"], vlan["vid"]), {}).get("id")
                    if dry_run
                    else vlan_cache[(vlan["group"], vlan["vid"])]["id"]
                )
                for vlan in vlans
            ]
            payload[field] = references if field == "tagged_vlans" else references[0]
        key = (device, record["name"])
        if key in existing:
            updated.append({**payload, "id": existing[key].id})
            changes["updated"].append(f"{device}:{record['name']}")
        else:
            created.append(payload)
            changes["created"].append(f"{device}:{record['name']}")
    merge_design_array_fields(
        worker,
        nb,
        lookup_cache,
        nb.dcim.interfaces,
        "dcim.interface",
        created,
        updated,
        ("tagged_vlans",),
    )
    if not dry_run:
        dependent_names = {
            (record["device"], record["name"])
            for record in records
            if any(field in record for field in ("parent", "lag", "bridge"))
        }
        base_created = [
            record
            for record in created
            if (record["device"]["name"], record["name"]) not in dependent_names
        ]
        base_updated = [
            record
            for record in updated
            if (record["device"]["name"], record["name"]) not in dependent_names
        ]
        if base_created:
            interface_cache.update(
                {
                    (item.device.name, item.name): item
                    for item in nb.dcim.interfaces.create(base_created)
                }
            )
        if base_updated:
            nb.dcim.interfaces.update(base_updated)
        if dependent_names:
            for payload in created + updated:
                device = payload["device"]["name"]
                if (device, payload["name"]) not in dependent_names:
                    continue
                source = next(
                    record
                    for record in records
                    if record["device"] == device and record["name"] == payload["name"]
                )
                for field in ("parent", "lag", "bridge"):
                    if field in source:
                        reference = source[field]
                        payload[field] = interface_cache[
                            (reference.get("device", device), reference["name"])
                        ].id
            dependent_created = [
                record
                for record in created
                if (record["device"]["name"], record["name"]) in dependent_names
            ]
            dependent_updated = [
                record
                for record in updated
                if (record["device"]["name"], record["name"]) in dependent_names
            ]
            if dependent_created:
                interface_cache.update(
                    {
                        (item.device.name, item.name): item
                        for item in nb.dcim.interfaces.create(dependent_created)
                    }
                )
            if dependent_updated:
                nb.dcim.interfaces.update(dependent_updated)
    return changes


def process_prefixes(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Bulk-write explicit prefixes, then run create_prefix allocations.

    Identity is prefix plus VRF. Scope chooses location, site, site group,
    then region; VLAN references use group and VID. A location with a site
    is looked up within that site. Missing scopes fail; missing VLANs fail
    outside dry-run mode. Existing prefix tags and custom-field lists gain
    new values without losing current members.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    log.debug(
        "process_prefixes: processing %d records, dry_run=%s", len(records), dry_run
    )
    explicit = [record for record in records if "prefix" in record]
    prefixes = [str(ip_network(record["prefix"], strict=False)) for record in explicit]
    existing = (
        {
            (item.prefix, item.vrf.id if item.vrf else None): item
            for item in worker.bulk_filter(
                nb.ipam.prefixes,
                prefix=prefixes,
                fields="id,prefix,vrf,tags,custom_fields",
            )
        }
        if prefixes
        else {}
    )
    created, updated = [], []
    for record, prefix in zip(explicit, prefixes):
        vrf = record.get("vrf")
        if isinstance(vrf, dict):
            key = (vrf.get("name"), vrf.get("rd"))
            vrf = lookup_cache["vrfs"].get(key) or nb.ipam.vrfs.get(**vrf).id
        elif isinstance(vrf, str):
            vrf = lookup_cache["vrfs"].get((vrf, None)) or nb.ipam.vrfs.get(name=vrf).id
        payload = {**record, "prefix": prefix}
        key = (prefix, vrf)
        if key in existing:
            updated.append({**payload, "id": existing[key].id})
        else:
            created.append(payload)
    created = [dict(record) for record in created]
    for record in created + updated:
        for field in ("tenant", "role"):
            if record.get(field) is not None:
                record[field] = {"name": record[field]}
        if isinstance(record.get("vrf"), str):
            record["vrf"] = {"name": record["vrf"]}
        for field, endpoint, scope_type in (
            ("location", nb.dcim.locations, "dcim.location"),
            ("site", nb.dcim.sites, "dcim.site"),
            ("site_group", nb.dcim.site_groups, "dcim.sitegroup"),
            ("region", nb.dcim.regions, "dcim.region"),
        ):
            if record.get(field):
                filters = {"name": record[field]}
                if field == "location" and record.get("site"):
                    filters["site_id"] = lookup_cache["sites"][record["site"]]
                scope_id = (
                    lookup_cache["sites"].get(record[field])
                    if field == "site"
                    else None
                )
                scope = endpoint.get(**filters) if scope_id is None else None
                if scope_id is None and scope is None:
                    raise ValueError(
                        f"prefix scope {field} '{record[field]}' not found"
                    )
                record.update(scope_type=scope_type, scope_id=scope_id or scope.id)
                break
        for field in ("location", "site", "site_group", "region"):
            record.pop(field, None)
        if isinstance(record.get("vlan"), dict) and "group" in record["vlan"]:
            vlan = record["vlan"]
            cached = lookup_cache["vlans"].get((vlan["group"], vlan["vid"]))
            record["vlan"] = cached["id"] if cached else None
            if not dry_run and record["vlan"] is None:
                raise ValueError(f"prefix VLAN {vlan['group']}:{vlan['vid']} not found")
    # The initial prefix read already has the fields needed for additive updates.
    merge_design_array_fields(
        worker,
        nb,
        lookup_cache,
        nb.ipam.prefixes,
        "ipam.prefix",
        created,
        updated,
        existing_by_id={item.id: item for item in existing.values()},
    )
    if not dry_run:
        if created:
            nb.ipam.prefixes.create(created)
        if updated:
            nb.ipam.prefixes.update(updated)
    changes = {
        "created": [record["prefix"] for record in created],
        "updated": [record["prefix"] for record in updated],
    }
    for record in records:
        if "create_prefix" in record:
            result = worker.create_prefix(
                **record["create_prefix"],
                job=job,
                instance=instance,
                branch=branch,
                dry_run=dry_run,
            )
            if result.failed or result.errors:
                raise ValueError("; ".join(result.errors) or "prefix allocation failed")
            if result.status in changes:
                changes[result.status].append(result.result["prefix"])
    return changes


def process_ip_addresses(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Bulk-write explicit IPs, then run create_ip allocations.

    Identity is address plus VRF and, for shared IPs, assignment. Assignments
    resolve interfaces or FHRP groups from the cache; allocated addresses may
    require later reads.
    If both assignment forms appear on one record, the interface wins.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    log.debug(
        "process_ip_addresses: processing %d records, dry_run=%s", len(records), dry_run
    )
    explicit = [record for record in records if "address" in record]
    addresses = [str(ip_interface(record["address"])) for record in explicit]
    existing = {}
    if addresses:
        for item in worker.bulk_filter(
            nb.ipam.ip_addresses,
            address=addresses,
            fields="id,address,vrf,role,assigned_object_type,assigned_object_id",
        ):
            existing.setdefault(
                (item.address, item.vrf.id if item.vrf else None), []
            ).append(item)
    ip_cache = lookup_cache["ip_addresses"]
    ip_cache.update(
        {
            (item.address, item.vrf.name if item.vrf else None): item.id
            for items in existing.values()
            for item in items
        }
    )
    interfaces = lookup_cache["interfaces"]
    missing_devices = {
        record["device"]
        for record in explicit
        if "device" in record
        and (record["device"], record["interface"]) not in interfaces
    }
    if missing_devices:
        interfaces.update(
            {
                (item.device.name, item.name): item
                for item in worker.bulk_filter(
                    nb.dcim.interfaces,
                    device=list(missing_devices),
                    fields="id,name,device,cable",
                )
            }
        )
    fhrp_groups = lookup_cache["fhrp_groups"]
    missing_group_ids = {
        record["fhrp_group"]["group_id"]
        for record in explicit
        if "fhrp_group" in record
        and (
            record["fhrp_group"]["protocol"],
            record["fhrp_group"]["group_id"],
        )
        not in fhrp_groups
    }
    if missing_group_ids:
        fhrp_groups.update(
            {
                (
                    (
                        item.protocol.value
                        if hasattr(item.protocol, "value")
                        else str(item.protocol)
                    ),
                    item.group_id,
                ): item.id
                for item in worker.bulk_filter(
                    nb.ipam.fhrp_groups,
                    group_id=list(missing_group_ids),
                    fields="id,protocol,group_id",
                )
            }
        )
    created, updated = [], []
    role_updates = []
    claimed_unassigned = set()
    for record, address in zip(explicit, addresses):
        payload = {
            key: value
            for key, value in record.items()
            if key not in ("device", "interface")
        }
        payload["address"] = address
        if "fhrp_group" in payload:
            group = payload.pop("fhrp_group")
            payload.update(
                assigned_object_type="ipam.fhrpgroup",
                assigned_object_id=fhrp_groups[(group["protocol"], group["group_id"])],
            )
        if "device" in record:
            interface = interfaces.get((record["device"], record["interface"]))
            if interface is not None:
                payload.update(
                    assigned_object_type="dcim.interface",
                    assigned_object_id=interface.id,
                )
            elif not dry_run:
                raise ValueError(
                    f"interface '{record['device']}:{record['interface']}' not found"
                )
        vrf = record.get("vrf")
        if isinstance(vrf, dict):
            key = (vrf.get("name"), vrf.get("rd"))
            vrf = lookup_cache["vrfs"].get(key) or nb.ipam.vrfs.get(**vrf).id
        elif isinstance(vrf, str):
            vrf = lookup_cache["vrfs"].get((vrf, None)) or nb.ipam.vrfs.get(name=vrf).id
        key = (address, vrf)
        matches = existing.get(key, [])
        assignment = (
            payload.get("assigned_object_type"),
            payload.get("assigned_object_id"),
        )
        current = next(
            (
                item
                for item in matches
                if (item.assigned_object_type, item.assigned_object_id) == assignment
            ),
            None,
        )
        if current is None:
            current = next(
                (
                    item
                    for item in matches
                    if not item.assigned_object_id and item.id not in claimed_unassigned
                ),
                None,
            )
        if (
            current is None
            and payload.get("role") in ("vip", "anycast")
            and assignment[1]
        ):
            # NetBox requires existing copies to have a shared role before a
            # second assignment can use the same address.
            for item in matches:
                if getattr(item.role, "value", item.role) != payload["role"]:
                    role_updates.append({"id": item.id, "role": payload["role"]})
            created.append(payload)
        elif current is None and matches:
            updated.append({**payload, "id": matches[0].id})
        elif current is None:
            created.append(payload)
        else:
            updated.append({**payload, "id": current.id})
            # An unassigned record can only be claimed once in this deployment.
            if not current.assigned_object_id:
                claimed_unassigned.add(current.id)
    created = [dict(record) for record in created]
    for record in created + updated:
        for field in ("tenant",):
            if record.get(field) is not None:
                record[field] = {"name": record[field]}
        if isinstance(record.get("vrf"), str):
            record["vrf"] = {"name": record["vrf"]}
    merge_design_array_fields(
        worker,
        nb,
        lookup_cache,
        nb.ipam.ip_addresses,
        "ipam.ipaddress",
        created,
        updated,
    )
    if not dry_run:
        if role_updates:
            nb.ipam.ip_addresses.update(role_updates)
        if created:
            ip_cache.update(
                {
                    (item.address, item.vrf.name if item.vrf else None): item.id
                    for item in nb.ipam.ip_addresses.create(created)
                }
            )
        if updated:
            nb.ipam.ip_addresses.update(updated)
    changes = {
        "created": [record["address"] for record in created],
        "updated": [record["address"] for record in updated],
    }
    for record in records:
        if "create_ip" in record:
            result = worker.create_ip(
                **record["create_ip"],
                job=job,
                instance=instance,
                branch=branch,
                dry_run=dry_run,
            )
            if result.failed or result.errors:
                raise ValueError("; ".join(result.errors) or "IP allocation failed")
            if result.status in changes:
                changes[result.status].append(result.result["address"])
    return changes


def process_asns(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Bulk-write numbered ASNs, then run create_asn range allocations.

    ASN number identifies explicit records; named sites resolve to cached IDs.
    Existing ASN site and tag arrays retain their members and add new values.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    log.debug("process_asns: processing %d records, dry_run=%s", len(records), dry_run)
    explicit = [record for record in records if "asn" in record]
    numbers = [record["asn"] for record in explicit]
    existing = (
        {
            item.asn: item
            for item in worker.bulk_filter(
                nb.ipam.asns, asn=numbers, fields="id,asn,sites,tags,custom_fields"
            )
        }
        if numbers
        else {}
    )
    created = [record for record in explicit if record["asn"] not in existing]
    updated = [
        {**record, "id": existing[record["asn"]].id}
        for record in explicit
        if record["asn"] in existing
    ]
    site_names = [name for record in explicit for name in (record.get("sites") or [])]
    # This is the shared cache dictionary; newly resolved sites remain available to later handlers.
    sites = lookup_cache["sites"]
    missing_sites = set(site_names) - sites.keys()
    if missing_sites:
        sites.update(
            {
                item.name: item.id
                for item in worker.bulk_filter(
                    nb.dcim.sites, name=list(missing_sites), fields="id,name"
                )
            }
        )
    created = [dict(record) for record in created]
    # NetBox ASN writes require site IDs; the shared helper handles list additions.
    for record in created:
        for field in ("rir", "tenant", "role"):
            if record.get(field) is not None:
                record[field] = {"name": record[field]}
        if "sites" in record:
            record["sites"] = [sites[name] for name in record["sites"]]
    for record in updated:
        for field in ("rir", "tenant", "role"):
            if record.get(field) is not None:
                record[field] = {"name": record[field]}
        if "sites" in record:
            record["sites"] = [sites[name] for name in record["sites"] or []]
    merge_design_array_fields(
        worker,
        nb,
        lookup_cache,
        nb.ipam.asns,
        "ipam.asn",
        created,
        updated,
        ("sites",),
        existing_by_id={item.id: item for item in existing.values()},
    )
    if not dry_run:
        if created:
            nb.ipam.asns.create(created)
        if updated:
            nb.ipam.asns.update(updated)
    changes = {
        "created": [record["asn"] for record in created],
        "updated": [record["asn"] for record in updated],
    }
    for record in records:
        if "create_asn" in record:
            result = worker.create_asn(
                **record["create_asn"],
                job=job,
                instance=instance,
                branch=branch,
                dry_run=dry_run,
            )
            if result.failed or result.errors:
                raise ValueError("; ".join(result.errors) or "ASN creation failed")
            action = result.result["status"] + "d" if dry_run else result.status
            changes[action].append(result.result["asn"])
    return changes


def process_vlans(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Bulk-write known VLAN IDs before create_vlan allocations.

    Group and VID form the identity. Existing tags and custom-field lists gain
    new values without losing current members. Created IDs populate the cache
    for interface and prefix references later in the deployment.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    log.debug("process_vlans: processing %d records, dry_run=%s", len(records), dry_run)
    explicit = [record for record in records if "vid" in record]
    vlan_cache = lookup_cache["vlans"]
    created, updated = [], []
    for record in explicit:
        group = record["group"]
        payload = {**record}
        key = (group, record["vid"])
        if key in vlan_cache:
            updated.append({**payload, "id": vlan_cache[key]["id"]})
        else:
            created.append(payload)
    created = [dict(record) for record in created]
    for record in created + updated:
        for field in ("group", "role", "tenant"):
            if record.get(field) is not None:
                record[field] = {"name": record[field]}
    # The lookup cache keeps existing VLAN records with tags and custom fields.
    merge_design_array_fields(
        worker,
        nb,
        lookup_cache,
        nb.ipam.vlans,
        "ipam.vlan",
        created,
        updated,
        existing_by_id={
            item["id"]: item["object"]
            for item in vlan_cache.values()
            if "object" in item
        },
    )
    if not dry_run:
        if created:
            for item in nb.ipam.vlans.create(created):
                vlan_cache[(item.group.name, item.vid)] = {
                    "id": item.id,
                    "name": item.name,
                }
        if updated:
            nb.ipam.vlans.update(updated)
            for record in updated:
                vlan_cache[(record["group"]["name"], record["vid"])] = {
                    "id": record["id"],
                    "name": record["name"],
                }
    changes = {
        "created": [record["vid"] for record in created],
        "updated": [record["vid"] for record in updated],
    }
    for record in records:
        if "create_vlan" in record:
            result = worker.create_vlan(
                **record["create_vlan"],
                job=job,
                instance=instance,
                branch=branch,
                dry_run=dry_run,
            )
            if result.failed or result.errors:
                raise ValueError("; ".join(result.errors) or "VLAN creation failed")
            action = result.result["status"] + "d" if dry_run else result.status
            changes[action].append(result.result["vid"])
            if not dry_run:
                vlan_cache[(result.result["vlan_group"], result.result["vid"])] = {
                    "id": result.result["id"],
                    "name": result.result["name"],
                }
    return changes


def process_routing_policies(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match BGP routing policies by name and bulk-write supplied fields.

    Policies are created before sessions that refer to them.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    log.debug(
        "process_routing_policies: processing %d records, dry_run=%s",
        len(records),
        dry_run,
    )
    identities = [record["name"] for record in records]
    existing = (
        {
            item.name: item
            for item in worker.bulk_filter(
                nb.plugins.bgp.routing_policy, name=identities, fields="id,name"
            )
        }
        if identities
        else {}
    )
    created = [dict(record) for record in records if record["name"] not in existing]
    updated = [
        {**record, "id": existing[record["name"]].id}
        for record in records
        if record["name"] in existing
    ]
    merge_design_array_fields(
        worker,
        nb,
        lookup_cache,
        nb.plugins.bgp.routing_policy,
        "netbox_bgp.routingpolicy",
        created,
        updated,
    )
    if not dry_run:
        if created:
            nb.plugins.bgp.routing_policy.create(created)
        if updated:
            nb.plugins.bgp.routing_policy.update(updated)
    return {
        "created": [record["name"] for record in created],
        "updated": [record["name"] for record in updated],
    }


def process_peer_groups(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Create or update BGP peer groups by name before their sessions.

    Args:
        worker: NetBox worker used for bulk reads and custom-field resolution.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened peer-group definitions.
        dry_run: Report planned writes without changing NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current design job.
        instance: NetBox instance name.
        branch: NetBox branch name, if any.

    Returns:
        dict: Peer-group names grouped under ``created`` and ``updated``.
    """
    identities = [record["name"] for record in records]
    existing = (
        {
            item.name: item
            for item in worker.bulk_filter(
                nb.plugins.bgp.peer_group, name=identities, fields="id,name"
            )
        }
        if identities
        else {}
    )
    created = [dict(record) for record in records if record["name"] not in existing]
    updated = [
        {**record, "id": existing[record["name"]].id}
        for record in records
        if record["name"] in existing
    ]
    merge_design_array_fields(
        worker,
        nb,
        lookup_cache,
        nb.plugins.bgp.peer_group,
        "netbox_bgp.peergroup",
        created,
        updated,
    )
    if not dry_run:
        if created:
            nb.plugins.bgp.peer_group.create(created)
        if updated:
            nb.plugins.bgp.peer_group.update(updated)
    return {
        "created": [record["name"] for record in created],
        "updated": [record["name"] for record in updated],
    }


def process_bgp_communities(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match BGP communities by value and optional description, then bulk-write.

    Tenant, when supplied, is resolved by name.
    A supplied description must match exactly. A different description creates
    a separate community. Without a description, value alone must be unique.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    log.debug(
        "process_bgp_communities: processing %d records, dry_run=%s",
        len(records),
        dry_run,
    )
    identities = [record["value"] for record in records]
    existing = (
        list(
            worker.bulk_filter(
                nb.plugins.bgp.community,
                value=identities,
                fields="id,value,description",
            )
        )
        if identities
        else []
    )
    created, updated = [], []
    for record in records:
        matches = [
            item
            for item in existing
            if item.value == record["value"]
            and (
                "description" not in record or item.description == record["description"]
            )
        ]
        if len(matches) > 1:
            raise ValueError(f"ambiguous BGP community: {record['value']}")
        if matches:
            updated.append({**record, "id": matches[0].id})
        else:
            created.append(dict(record))
    for record in created + updated:
        if record.get("tenant") is not None:
            record["tenant"] = {"name": record["tenant"]}
    merge_design_array_fields(
        worker,
        nb,
        lookup_cache,
        nb.plugins.bgp.community,
        "netbox_bgp.community",
        created,
        updated,
    )
    if not dry_run:
        if created:
            nb.plugins.bgp.community.create(created)
        if updated:
            nb.plugins.bgp.community.update(updated)
    return {
        "created": [record["value"] for record in created],
        "updated": [record["value"] for record in updated],
    }


def process_bgp_peerings(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Create missing BGP sessions and leave existing sessions unchanged.

    Local/remote create_asn wrappers allocate ASNs before session creation.
    Routing-policy dictionaries become names. Reverse-session creation is
    batched separately because the worker task takes one flag per batch.
    The create task derives missing names and checks NetBox for existing sessions.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    records = [dict(record) for record in records]
    for record in records:
        # Allocate nested ASNs before passing numeric references to the peering task.
        for field in ("local_as", "remote_as"):
            if isinstance(record.get(field), dict):
                result = worker.create_asn(
                    **record[field]["create_asn"],
                    job=job,
                    instance=instance,
                    branch=branch,
                    dry_run=dry_run,
                )
                if result.failed or result.errors:
                    raise ValueError(
                        "; ".join(result.errors) or "ASN allocation failed"
                    )
                record[field] = result.result["asn"]
        for field in ("import_policies", "export_policies"):
            if field in record:
                record[field] = [policy["name"] for policy in record[field]]
    log.debug(
        "process_bgp_peerings: processing %d records, dry_run=%s", len(records), dry_run
    )
    changes = {"created": [], "updated": []}
    for create_reverse in (False, True):
        batch = [
            record
            for record in records
            if record.get("create_reverse", True) == create_reverse
        ]
        if batch:
            result = worker.create_bgp_peering(
                bulk_create=batch,
                create_reverse=create_reverse,
                dry_run=dry_run,
                job=job,
                instance=instance,
                branch=branch,
                lookup_cache=lookup_cache,
            )
            if result.failed or result.errors:
                raise ValueError("; ".join(result.errors) or "BGP creation failed")
            changes["created"].extend(result.result["create" if dry_run else "created"])
    return changes


def process_power_ports(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Create or update device power ports by device and name.

    Existing ports are patched without diff checks. New and existing port IDs
    are cached for the later cable handler; a dry run does not cache new IDs.

    Args:
        worker: NetBox worker providing bulk reads.
        nb: Pynetbox API for this instance and branch.
        records: Flat port definitions, each with device and name.
        dry_run: Report changes without writing to NetBox.
        lookup_cache: Per-deployment object references.
        job: Current design job.
        instance: NetBox instance name.
        branch: Optional NetBox branch name.

    Returns:
        dict: Port identities grouped as created and updated.
    """
    device_names = list({record["device"] for record in records})
    existing = (
        {
            (item.device.name, item.name): item
            for item in worker.bulk_filter(
                nb.dcim.power_ports, device=device_names, fields="id,name,device,cable"
            )
        }
        if device_names
        else {}
    )
    lookup_cache["power_ports"].update(existing)
    created, updated = [], []
    for record in records:
        payload = {**record, "device": {"name": record["device"]}}
        key = (record["device"], record["name"])
        if key in existing:
            updated.append({**payload, "id": existing[key].id})
        else:
            created.append(payload)
    merge_design_array_fields(
        worker,
        nb,
        lookup_cache,
        nb.dcim.power_ports,
        "dcim.powerport",
        created,
        updated,
    )
    if not dry_run:
        if created:
            lookup_cache["power_ports"].update(
                {
                    (item.device.name, item.name): item
                    for item in nb.dcim.power_ports.create(created)
                }
            )
        if updated:
            nb.dcim.power_ports.update(updated)
    return {
        "created": [
            f'{record["device"]["name"]}:{record["name"]}' for record in created
        ],
        "updated": [
            f'{record["device"]["name"]}:{record["name"]}' for record in updated
        ],
    }


def process_console_ports(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Create or update device console ports by device and name.

    Existing ports are patched without diff checks. New and existing port IDs
    are cached for the later cable handler; a dry run does not cache new IDs.

    Args:
        worker: NetBox worker providing bulk reads.
        nb: Pynetbox API for this instance and branch.
        records: Flat port definitions, each with device and name.
        dry_run: Report changes without writing to NetBox.
        lookup_cache: Per-deployment object references.
        job: Current design job.
        instance: NetBox instance name.
        branch: Optional NetBox branch name.

    Returns:
        dict: Port identities grouped as created and updated.
    """
    device_names = list({record["device"] for record in records})
    existing = (
        {
            (item.device.name, item.name): item
            for item in worker.bulk_filter(
                nb.dcim.console_ports,
                device=device_names,
                fields="id,name,device,cable",
            )
        }
        if device_names
        else {}
    )
    lookup_cache["console_ports"].update(existing)
    created, updated = [], []
    for record in records:
        payload = {**record, "device": {"name": record["device"]}}
        key = (record["device"], record["name"])
        if key in existing:
            updated.append({**payload, "id": existing[key].id})
        else:
            created.append(payload)
    merge_design_array_fields(
        worker,
        nb,
        lookup_cache,
        nb.dcim.console_ports,
        "dcim.consoleport",
        created,
        updated,
    )
    if not dry_run:
        if created:
            lookup_cache["console_ports"].update(
                {
                    (item.device.name, item.name): item
                    for item in nb.dcim.console_ports.create(created)
                }
            )
        if updated:
            nb.dcim.console_ports.update(updated)
    return {
        "created": [
            f'{record["device"]["name"]}:{record["name"]}' for record in created
        ],
        "updated": [
            f'{record["device"]["name"]}:{record["name"]}' for record in updated
        ],
    }


def process_power_outlets(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Create or update device power outlets by device and name.

    Existing ports are patched without diff checks. New and existing port IDs
    are cached for the later cable handler; a dry run does not cache new IDs.

    Args:
        worker: NetBox worker providing bulk reads.
        nb: Pynetbox API for this instance and branch.
        records: Flat port definitions, each with device and name.
        dry_run: Report changes without writing to NetBox.
        lookup_cache: Per-deployment object references.
        job: Current design job.
        instance: NetBox instance name.
        branch: Optional NetBox branch name.

    Returns:
        dict: Port identities grouped as created and updated.
    """
    device_names = list({record["device"] for record in records})
    existing = (
        {
            (item.device.name, item.name): item
            for item in worker.bulk_filter(
                nb.dcim.power_outlets,
                device=device_names,
                fields="id,name,device,cable",
            )
        }
        if device_names
        else {}
    )
    lookup_cache["power_outlets"].update(existing)
    created, updated = [], []
    for record in records:
        payload = {**record, "device": {"name": record["device"]}}
        key = (record["device"], record["name"])
        if key in existing:
            updated.append({**payload, "id": existing[key].id})
        else:
            created.append(payload)
    merge_design_array_fields(
        worker,
        nb,
        lookup_cache,
        nb.dcim.power_outlets,
        "dcim.poweroutlet",
        created,
        updated,
    )
    if not dry_run:
        if created:
            lookup_cache["power_outlets"].update(
                {
                    (item.device.name, item.name): item
                    for item in nb.dcim.power_outlets.create(created)
                }
            )
        if updated:
            nb.dcim.power_outlets.update(updated)
    return {
        "created": [
            f'{record["device"]["name"]}:{record["name"]}' for record in created
        ],
        "updated": [
            f'{record["device"]["name"]}:{record["name"]}' for record in updated
        ],
    }


def process_console_server_ports(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Create or update device console server ports by device and name.

    Existing ports are patched without diff checks. New and existing port IDs
    are cached for the later cable handler; a dry run does not cache new IDs.

    Args:
        worker: NetBox worker providing bulk reads.
        nb: Pynetbox API for this instance and branch.
        records: Flat port definitions, each with device and name.
        dry_run: Report changes without writing to NetBox.
        lookup_cache: Per-deployment object references.
        job: Current design job.
        instance: NetBox instance name.
        branch: Optional NetBox branch name.

    Returns:
        dict: Port identities grouped as created and updated.
    """
    device_names = list({record["device"] for record in records})
    existing = (
        {
            (item.device.name, item.name): item
            for item in worker.bulk_filter(
                nb.dcim.console_server_ports,
                device=device_names,
                fields="id,name,device,cable",
            )
        }
        if device_names
        else {}
    )
    lookup_cache["console_server_ports"].update(existing)
    created, updated = [], []
    for record in records:
        payload = {**record, "device": {"name": record["device"]}}
        key = (record["device"], record["name"])
        if key in existing:
            updated.append({**payload, "id": existing[key].id})
        else:
            created.append(payload)
    merge_design_array_fields(
        worker,
        nb,
        lookup_cache,
        nb.dcim.console_server_ports,
        "dcim.consoleserverport",
        created,
        updated,
    )
    if not dry_run:
        if created:
            lookup_cache["console_server_ports"].update(
                {
                    (item.device.name, item.name): item
                    for item in nb.dcim.console_server_ports.create(created)
                }
            )
        if updated:
            nb.dcim.console_server_ports.update(updated)
    return {
        "created": [
            f'{record["device"]["name"]}:{record["name"]}' for record in created
        ],
        "updated": [
            f'{record["device"]["name"]}:{record["name"]}' for record in updated
        ],
    }


def process_connections(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match or create interface, console, or power cables.

    Occupied endpoints connected elsewhere are rejected, never disconnected.
    Top-level and flattened port connections share this handler. Each side
    names one device and one supported termination type. Duplicate endpoints
    fail. Ports connected elsewhere are never disconnected.
    Tenant names are converted to NetBox references; dictionaries pass through.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    endpoints_by_type = {
        "interface": ("interfaces", "dcim.interface"),
        "console_port": ("console_ports", "dcim.consoleport"),
        "console_server_port": ("console_server_ports", "dcim.consoleserverport"),
        "power_port": ("power_ports", "dcim.powerport"),
        "power_outlet": ("power_outlets", "dcim.poweroutlet"),
    }
    for endpoint_type, (collection, _) in endpoints_by_type.items():
        missing_devices = {
            endpoint["device"]
            for record in records
            for field in ("a_terminations", "b_terminations")
            for endpoint in record[field]
            if endpoint_type in endpoint
            and (endpoint["device"], endpoint[endpoint_type])
            not in lookup_cache[collection]
        }
        if missing_devices:
            lookup_cache[collection].update(
                {
                    (item.device.name, item.name): item
                    for item in worker.bulk_filter(
                        getattr(nb.dcim, collection),
                        device=list(missing_devices),
                        fields="id,name,device,cable",
                    )
                }
            )
    created, updated = [], []
    changes = {"created": [], "updated": []}
    used = set()
    for record in records:
        a = record["a_terminations"][0]
        b = record["b_terminations"][0]
        endpoint_types = [
            next(name for name in endpoints_by_type if name in endpoint)
            for endpoint in (a, b)
        ]
        keys = [
            (endpoint_type, endpoint["device"], endpoint[endpoint_type])
            for endpoint_type, endpoint in zip(endpoint_types, (a, b))
        ]
        label = (
            record.get("label")
            or f"{keys[0][1]}:{keys[0][2]} - {keys[1][1]}:{keys[1][2]}"
        )
        if any(key in used for key in keys):
            raise ValueError(f"connection endpoint specified more than once: {label}")
        used.update(keys)
        endpoints = [
            lookup_cache[endpoints_by_type[key[0]][0]].get((key[1], key[2]))
            for key in keys
        ]
        if any(endpoint is None for endpoint in endpoints):
            if dry_run:
                changes["created"].append(label)
                continue
            raise ValueError(f"connection termination not found: {label}")
        cable_ids = [
            endpoint.cable.id if endpoint.cable else None for endpoint in endpoints
        ]
        payload = {
            key: value
            for key, value in record.items()
            if key not in ("a_terminations", "b_terminations")
        }
        if isinstance(payload.get("tenant"), str):
            payload["tenant"] = {"name": payload["tenant"]}
        if any(cable_ids):
            if not cable_ids[0] or cable_ids[0] != cable_ids[1]:
                raise ValueError(
                    f"connection endpoint already cabled elsewhere: {label}"
                )
            updated.append({**payload, "id": cable_ids[0]})
            changes["updated"].append(label)
        else:
            payload["a_terminations"] = [
                {
                    "object_type": endpoints_by_type[keys[0][0]][1],
                    "object_id": endpoints[0].id,
                }
            ]
            payload["b_terminations"] = [
                {
                    "object_type": endpoints_by_type[keys[1][0]][1],
                    "object_id": endpoints[1].id,
                }
            ]
            created.append(payload)
            changes["created"].append(label)
    merge_design_array_fields(
        worker, nb, lookup_cache, nb.dcim.cables, "dcim.cable", created, updated
    )
    if not dry_run:
        if created:
            nb.dcim.cables.create(created)
        if updated:
            nb.dcim.cables.update(updated)
    return changes


def process_vrrp_groups(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match FHRP groups by protocol and group ID and cache their IDs.

    Group records are written before VIPs and interface assignments.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    ids = [record["group_id"] for record in records]
    existing = (
        {
            (
                (
                    item.protocol.value
                    if hasattr(item.protocol, "value")
                    else str(item.protocol)
                ),
                item.group_id,
            ): item
            for item in worker.bulk_filter(
                nb.ipam.fhrp_groups, group_id=ids, fields="id,protocol,group_id"
            )
        }
        if ids
        else {}
    )
    groups = lookup_cache["fhrp_groups"]
    groups.update({key: item.id for key, item in existing.items()})
    created, updated = [], []
    for record in records:
        key = (record["protocol"], record["group_id"])
        if key in existing:
            updated.append({**record, "id": existing[key].id})
        else:
            created.append(record)
    merge_design_array_fields(
        worker,
        nb,
        lookup_cache,
        nb.ipam.fhrp_groups,
        "ipam.fhrpgroup",
        created,
        updated,
    )
    if not dry_run:
        if created:
            groups.update(
                {
                    (
                        (
                            item.protocol.value
                            if hasattr(item.protocol, "value")
                            else str(item.protocol)
                        ),
                        item.group_id,
                    ): item.id
                    for item in nb.ipam.fhrp_groups.create(created)
                }
            )
        if updated:
            nb.ipam.fhrp_groups.update(updated)
    return {
        "created": [record["group_id"] for record in created],
        "updated": [record["group_id"] for record in updated],
    }


def process_vrrp_group_assignments(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Match FHRP assignments by group ID and interface ID.

    Groups and interfaces must exist first. Only DCIM interface assignments
    are handled; priority is sent on both create and update. An absent group
    or interface fails rather than creating it here.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    groups = lookup_cache["fhrp_groups"]
    missing_group_ids = {
        record["group_id"]
        for record in records
        if (record["protocol"], record["group_id"]) not in groups
    }
    if missing_group_ids:
        groups.update(
            {
                (
                    (
                        item.protocol.value
                        if hasattr(item.protocol, "value")
                        else str(item.protocol)
                    ),
                    item.group_id,
                ): item.id
                for item in worker.bulk_filter(
                    nb.ipam.fhrp_groups,
                    group_id=list(missing_group_ids),
                    fields="id,protocol,group_id",
                )
            }
        )
    interfaces = lookup_cache["interfaces"]
    missing_devices = {
        record["device"]
        for record in records
        if (record["device"], record["interface"]) not in interfaces
    }
    if missing_devices:
        interfaces.update(
            {
                (item.device.name, item.name): item
                for item in worker.bulk_filter(
                    nb.dcim.interfaces,
                    device=list(missing_devices),
                    fields="id,name,device,cable",
                )
            }
        )
    existing = (
        {
            (item.group.id, item.interface_id): item
            for item in worker.bulk_filter(
                nb.ipam.fhrp_group_assignments,
                group_id=list(groups.values()),
                fields="id,group,interface_id",
            )
        }
        if records
        else {}
    )
    created, updated = [], []
    for record in records:
        group_id = groups[(record["protocol"], record["group_id"])]
        interface_id = interfaces[(record["device"], record["interface"])].id
        payload = {
            "group": group_id,
            "interface_type": "dcim.interface",
            "interface_id": interface_id,
            "priority": record["priority"],
        }
        if (group_id, interface_id) in existing:
            updated.append({**payload, "id": existing[(group_id, interface_id)].id})
        else:
            created.append(payload)
    if not dry_run:
        if created:
            nb.ipam.fhrp_group_assignments.create(created)
        if updated:
            nb.ipam.fhrp_group_assignments.update(updated)
    return {
        "created": [record["interface_id"] for record in created],
        "updated": [record["interface_id"] for record in updated],
    }


def process_primary_ip(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Set primary IPs after IP address creation.

    Device matching uses site and name, plus tenant when supplied; the
    address is matched with VRF. This sends updates even when unchanged.

    Args:
        worker: NetBox worker used for bulk reads and delegated tasks.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Flattened records for this object collection.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Mutable references shared across collection handlers.
        job: Current job, forwarded to delegated tasks when applicable.
        instance: NetBox instance for delegated worker tasks.
        branch: NetBox branch for delegated worker tasks, if any.

    Returns:
        dict: Object identities grouped under ``created`` and ``updated``.
    """
    devices = (
        worker.bulk_filter(
            nb.dcim.devices,
            name=[record["device"] for record in records],
            fields="id,name,site,tenant",
        )
        if records
        else []
    )
    addresses = lookup_cache["ip_addresses"]
    missing_addresses = {
        str(ip_interface(record["address"]))
        for record in records
        if (str(ip_interface(record["address"])), record.get("vrf")) not in addresses
    }
    if missing_addresses:
        addresses.update(
            {
                (item.address, item.vrf.name if item.vrf else None): item.id
                for item in worker.bulk_filter(
                    nb.ipam.ip_addresses,
                    address=list(missing_addresses),
                    fields="id,address,vrf",
                )
            }
        )
    updated = []
    for record in records:
        matches = [
            item
            for item in devices
            if item.name == record["device"]
            and item.site.name == record["site"]
            and (
                "tenant" not in record
                or (item.tenant.name if item.tenant else None) == record["tenant"]
            )
        ]
        if len(matches) != 1:
            raise ValueError(
                f"primary IP device match is not unique: {record['site']}:{record['device']}"
            )
        device = matches[0]
        address = addresses[(str(ip_interface(record["address"])), record.get("vrf"))]
        updated.append({"id": device.id, record.get("field", "primary_ip4"): address})
    if updated and not dry_run:
        nb.dcim.devices.update(updated)
    return {"created": [], "updated": [record["device"] for record in records]}


def process_local_context_data(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
    custom_functions: dict,
    context: dict,
) -> dict:
    """Patch per-device local context data after all other design objects.

    Match by site and device name, plus tenant when supplied. A static
    ``local_context_data`` dictionary is sent unchanged. A custom function
    receives the pynetbox device record, design ``context``, ``netbox``,
    ``dry_run``, and sibling
    fields inside the local context dictionary as keyword arguments. It must
    return a dictionary. Existing data is replaced, not merged. In dry-run,
    functions are skipped for devices that
    have not yet been created, because no device record exists to pass them.

    Args:
        worker: NetBox worker used to bulk-read matching devices.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: Device identity and static or function-backed context records.
        dry_run: Plan updates without writing to NetBox.
        lookup_cache: Deployment reference cache; not used by this handler.
        job: Current job; not used by this handler.
        instance: NetBox instance; not used by this handler.
        branch: NetBox branch; not used by this handler.
        custom_functions: Callable functions registered by the design.
        context: Validated design input context.

    Returns:
        dict: Matched device names under ``updated``; ``created`` is always empty.
            A dry run omits devices that do not yet exist.

    Raises:
        ValueError: If a device match is ambiguous or a function returns
            something other than a dictionary.
    """
    names = [record["device"] for record in records]
    devices = (
        worker.bulk_filter(
            nb.dcim.devices,
            name=names,
            fields=(
                None
                if any(
                    "custom_function" in record["local_context_data"]
                    for record in records
                )
                else "id,name,site,tenant"
            ),
        )
        if names
        else []
    )
    updated = []
    updated_names = []
    for record in records:
        matches = [
            device
            for device in devices
            if device.name == record["device"]
            and device.site.name == record["site"]
            and (
                "tenant" not in record
                or (device.tenant.name if device.tenant else None) == record["tenant"]
            )
        ]
        if len(matches) != 1:
            if dry_run and not matches:
                continue
            raise ValueError(
                f"local context device match is not unique: "
                f"{record['site']}:{record['device']}"
            )
        device = matches[0]
        local_data = record["local_context_data"]
        if "custom_function" in local_data:
            function_kwargs = {
                key: value
                for key, value in local_data.items()
                if key != "custom_function"
            }
            local_data = custom_functions[local_data["custom_function"]](
                device=device,
                context=context,
                netbox=nb,
                dry_run=dry_run,
                **function_kwargs,
            )
            if not isinstance(local_data, dict):
                raise ValueError(
                    f"local context function '{record['local_context_data']['custom_function']}' "
                    "must return a dictionary"
                )
        updated.append({"id": device.id, "local_context_data": local_data})
        updated_names.append(record["device"])
    if updated and not dry_run:
        nb.dcim.devices.update(updated)
    return {"created": [], "updated": updated_names}


def process_config_context(
    worker: Any,
    nb: Any,
    records: list[dict],
    dry_run: bool,
    lookup_cache: dict,
    job: Job,
    instance: str,
    branch: str | None,
) -> dict:
    """Bulk-write reusable NetBox ConfigContext objects by name.

    A ``sites`` list contains site names, resolved to IDs before writing.
    Without a scope, NetBox applies the context globally, so designs should
    scope contexts deliberately. Existing sites gain new members; data is
    sent as supplied, without merging.

    Args:
        worker: NetBox worker used for bulk reads.
        nb: Pynetbox API bound to this deployment's instance and branch.
        records: ConfigContext records containing name, data, and optional scope.
        dry_run: Plan actions without writing to NetBox.
        lookup_cache: Shared site IDs, including sites created by this design.
        job: Current job; not used by this handler.
        instance: NetBox instance; not used by this handler.
        branch: NetBox branch; not used by this handler.

    Returns:
        dict: Context names grouped under ``created`` and ``updated``.
    """
    names = [record["name"] for record in records]
    existing = (
        {
            item.name: item.id
            for item in worker.bulk_filter(
                nb.extras.config_contexts, name=names, fields="id,name"
            )
        }
        if names
        else {}
    )
    sites = lookup_cache["sites"]
    missing_sites = {
        name
        for record in records
        for name in record.get("sites", [])
        if name not in sites
    }
    if missing_sites:
        sites.update(
            {
                item.name: item.id
                for item in worker.bulk_filter(
                    nb.dcim.sites, name=list(missing_sites), fields="id,name"
                )
            }
        )
    created, updated = [], []
    for record in records:
        payload = dict(record)
        if "sites" in payload:
            payload["sites"] = [sites[name] for name in payload["sites"]]
        if record["name"] in existing:
            updated.append({**payload, "id": existing[record["name"]]})
        else:
            created.append(payload)
    merge_design_array_fields(
        worker,
        nb,
        lookup_cache,
        nb.extras.config_contexts,
        "extras.configcontext",
        created,
        updated,
        (
            "regions",
            "site_groups",
            "sites",
            "locations",
            "device_types",
            "roles",
            "platforms",
            "cluster_groups",
            "clusters",
            "tenant_groups",
            "tenants",
        ),
    )
    if not dry_run:
        if created:
            nb.extras.config_contexts.create(created)
        if updated:
            nb.extras.config_contexts.update(updated)
    return {
        "created": [record["name"] for record in created],
        "updated": [record["name"] for record in updated],
    }


DESIGN_HANDLERS_ORDER = {
    "tenants": process_tenants,
    "regions": process_regions,
    "manufacturers": process_manufacturers,
    "platforms": process_platforms,
    "device_types": process_device_types,
    "device_roles": process_device_roles,
    "sites": process_sites,
    "rack_roles": process_rack_roles,
    "racks": process_racks,
    "roles": process_roles,
    "rirs": process_rirs,
    "asn_ranges": process_asn_ranges,
    "asns": process_asns,
    "vlan_groups": process_vlan_groups,
    "vlans": process_vlans,
    "route_targets": process_route_targets,
    "vrfs": process_vrfs,
    "l2vpns": process_l2vpns,
    "prefixes": process_prefixes,
    "devices": process_devices,
    "interfaces": process_interfaces,
    "l2vpn_terminations": process_l2vpn_terminations,
    "power_ports": process_power_ports,
    "console_ports": process_console_ports,
    "power_outlets": process_power_outlets,
    "console_server_ports": process_console_server_ports,
    "connections": process_connections,
    "vrrp_groups": process_vrrp_groups,
    "ip_addresses": process_ip_addresses,
    "vrrp_group_assignments": process_vrrp_group_assignments,
    "primary_ip": process_primary_ip,
    "bgp_communities": process_bgp_communities,
    "routing_policies": process_routing_policies,
    "peer_groups": process_peer_groups,
    "bgp_peerings": process_bgp_peerings,
    "config_context": process_config_context,
    "local_context_data": process_local_context_data,
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
        dry_run_render: bool = False,
    ) -> Result:
        """Render and flatten a design, validate it, then deploy ordered collections.

        Updates add tags, custom-field list entries, and the supported native
        relationship lists. Scalar fields and context-data dictionaries replace
        their current values. Object custom-field names resolve to NetBox IDs.

        Args:
            job: NorFab job injected by the task framework.
            design: YAML text, NorFab file URL, or parsed design dictionary.
            context: Jinja2 variables, optionally checked by design_input_schema.
            instance: NetBox instance name; defaults to the worker's instance.
            dry_run: Return planned writes without changing NetBox.
            branch: NetBox Branching plugin branch name.
            dry_run_render: Return rendered text before YAML parsing, flattening,
                validation, or deployment. Dictionary designs return unchanged.
                Takes precedence over dry_run; context validation and Jinja2
                functions still run.

        Returns:
            Object identities grouped by collection and creation/update action,
            or rendered text (the original dictionary for dictionary designs)
            with dry_run=True when dry_run_render is enabled. Preparation and
            deployment errors are reported in a failed Result.
        """
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:design_deploy",
            result={},
            resources=[instance],
            dry_run=dry_run,
        )
        msg = f"starting netbox design deployment: instance={instance}, branch={branch}, dry_run={dry_run}"
        log.info(msg)
        job.event(msg)
        try:
            if isinstance(context, str):
                if self.is_url(context):
                    context = self.fetch_file(context, raise_on_fail=True)
                context = yaml.safe_load(context) or {}
            if not isinstance(context, dict):
                raise TypeError("Design context must be a YAML mapping")

            design_url = (
                design if isinstance(design, str) and self.is_url(design) else None
            )
            if isinstance(design, dict):
                document = design
                metadata = DesignDocument.model_validate(
                    {
                        "design_input_schema": design.get("design_input_schema"),
                        "jinja_functions": design.get("jinja_functions", {}),
                    }
                )
                template = None
            elif isinstance(design, str):
                source = (
                    self.fetch_file(design_url, raise_on_fail=True)
                    if design_url
                    else design
                )
                metadata_lines = []
                for line in source.splitlines():
                    if (
                        line
                        and not line[0].isspace()
                        and not line.startswith(
                            (
                                "#",
                                "design_input_schema:",
                                "jinja_functions:",
                                "custom_functions:",
                            )
                        )
                    ):
                        break
                    metadata_lines.append(line)
                metadata = DesignDocument.model_validate(
                    yaml.safe_load("\n".join(metadata_lines)) or {}
                )
                template = source
            else:
                raise TypeError("Design must be YAML text, a file URL, or a dictionary")

            input_schema = metadata.design_input_schema
            jinja_functions = metadata.jinja_functions

            if input_schema:
                if isinstance(input_schema, str):
                    if not self.is_url(input_schema):
                        raise ValueError(
                            "Design input model must use an nf:// or git:// URL"
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
                        "Design input schema must be JSON Schema or a model URL"
                    )
                model_globals = {}
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

            filters = {}
            for name, url in jinja_functions.items():
                if not self.is_url(url):
                    raise ValueError(
                        f"Jinja function '{name}' must use an nf:// or git:// URL"
                    )
                namespace = {}
                exec(
                    self.fetch_file(url, raise_on_fail=True), namespace, namespace
                )  # nosec B102
                function = namespace.get(name)
                if not callable(function):
                    raise ValueError(
                        f"Jinja function '{name}' is not callable in '{url}'"
                    )
                filters[name] = function

            nb = self._get_pynetbox(instance, branch=branch, job=job)
            if template is not None:
                loader = None
                if design_url:
                    loader = FileSystemLoader(
                        os.path.dirname(self.jinja2_fetch_template(design_url))
                    )
                environment = Environment(loader=loader)
                environment.filters.update(filters)
                environment.globals.update(filters)
                environment.globals["netbox"] = nb
                document = environment.from_string(template).render(context=context)

            if dry_run_render:
                ret.result = document
                ret.dry_run = True
                return ret

            if template is not None:
                document = yaml.safe_load(document) or {}

            msg = "flattening and validating netbox design"
            log.info(msg)
            job.event(msg)
            flattened = flatten_design(document)
            validated = DesignDocument.model_validate(flattened)
            lookup_cache = build_lookup_cache(self, nb, validated)
            custom_functions = {}
            for name, url in validated.custom_functions.items():
                if not self.is_url(url):
                    raise ValueError(f"custom function '{name}' must use a file URL")
                namespace = {}
                exec(
                    self.fetch_file(url, raise_on_fail=True), namespace, namespace
                )  # nosec B102
                function = namespace.get(name)
                if not callable(function):
                    raise ValueError(
                        f"custom function '{name}' is not callable in '{url}'"
                    )
                custom_functions[name] = function
            for collection in DESIGN_HANDLERS_ORDER:
                for record in getattr(validated, collection):
                    if "custom_function" in record:
                        function = custom_functions[record["custom_function"]]
                        arguments = {
                            key: value
                            for key, value in record.items()
                            if key != "custom_function"
                        }
                        inspect.signature(function).bind(
                            **arguments, context=context, netbox=nb, dry_run=dry_run
                        )
            for record in validated.local_context_data:
                local_context = record["local_context_data"]
                if "custom_function" in local_context:
                    function_kwargs = {
                        key: value
                        for key, value in local_context.items()
                        if key != "custom_function"
                    }
                    inspect.signature(
                        custom_functions[local_context["custom_function"]]
                    ).bind(
                        device=None,
                        context=context,
                        netbox=nb,
                        dry_run=dry_run,
                        **function_kwargs,
                    )
            handlers = dict(DESIGN_HANDLERS_ORDER)
            handlers["local_context_data"] = partial(
                process_local_context_data,
                custom_functions=custom_functions,
                context=context,
            )
        except Exception as exc:
            msg = f"failed to prepare netbox design: {exc}"
            log.exception(msg)
            job.event(msg, severity="ERROR")
            ret.errors.append(msg)
            ret.failed = True
            return ret
        for collection, handler in handlers.items():
            records = getattr(validated, collection)
            if not records:
                ret.result[collection] = {"created": [], "updated": []}
                continue
            msg = f"deploying {collection}: {len(records)} records, dry_run={dry_run}"
            log.info(msg)
            job.event(msg)
            try:
                ret.result[collection] = handler(
                    self,
                    nb,
                    [record for record in records if "custom_function" not in record],
                    dry_run,
                    lookup_cache=lookup_cache,
                    job=job,
                    instance=instance,
                    branch=branch,
                )
                execute_custom_functions(
                    nb,
                    context,
                    records,
                    custom_functions,
                    dry_run,
                    ret.result[collection],
                )
                changes = ret.result[collection]
                msg = (
                    f"completed {collection}: {len(changes['created'])} created, "
                    f"{len(changes['updated'])} updated, "
                    f"{len(changes.get('custom', []))} custom calls"
                )
                log.info(msg)
                job.event(msg)
            except Exception as exc:
                message = f"failed to deploy {collection}: {exc}"
                log.exception(message)
                job.event(message, severity="ERROR")
                ret.errors.append(message)
                ret.failed = True
                return ret
        msg = (
            f"netbox design complete: "
            f"{sum(len(items['created']) for items in ret.result.values())} objects created, "
            f"{sum(len(items['updated']) for items in ret.result.values())} objects updated"
        )
        log.info(msg)
        job.event(msg)
        return ret
