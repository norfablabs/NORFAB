import fnmatch
import logging
from collections.abc import Iterable
from typing import Any, Union

import yaml
from deepdiff import DeepDiff
from pydantic import TypeAdapter

from norfab.core.worker import Job, Task
from norfab.models import Result
from norfab.utils.text import expand_alphanumeric_range, slugify

from .netbox_models import (
    CreateVlanGroupInput,
    CreateVlanGroupResult,
    CreateVlanInput,
    CreateVlanResult,
    InterfaceMapRule,
    NetboxFastApiArgs,
    SyncVlansInput,
    SyncVlansResult,
    VlanMapRule,
)
from .netbox_worker_utilities import (
    apply_description_policy,
    map_interface_name,
    merge_array_values,
    merge_resolved_custom_fields,
    review_sync_task_result,
)

log = logging.getLogger(__name__)


def match_vlan_map(
    rules: list[dict],
    vlan_id: int,
    vlan_name: str,
    device_name: str,
    interface_names: list[str],
) -> Union[None, str]:
    """Return the group from the first rule matching the VLAN."""
    for rule in rules:
        if rule["expanded_vlan_ids"] and vlan_id not in rule["expanded_vlan_ids"]:
            continue
        if rule.get("vlan_names") and not any(
            fnmatch.fnmatchcase(vlan_name, pattern) for pattern in rule["vlan_names"]
        ):
            continue
        if rule.get("match_device_names") and not any(
            fnmatch.fnmatchcase(device_name, pattern)
            for pattern in rule["match_device_names"]
        ):
            continue
        if rule.get("match_interface_names") and not any(
            fnmatch.fnmatchcase(interface_name, pattern)
            for interface_name in interface_names
            for pattern in rule["match_interface_names"]
        ):
            continue
        return rule["set_vlan_group"]
    return None


def load_device_vlan_scopes(
    devices: Iterable, nb: Any, bulk_filter: Any
) -> dict[str, dict]:
    """Load NetBox scope assignments used to resolve VLANs per device."""
    devices = list(devices)
    site_ids = sorted({device.site.id for device in devices})
    site_records = bulk_filter(
        nb.dcim.sites,
        id=site_ids,
        fields="id,name,region,group",
    )
    sites = {site.id: site for site in site_records}

    # A VLAN group scoped to a parent region also applies to sites in its child
    # regions. Load at most five levels, including each site's direct region.
    regions = {}
    pending_region_ids = {site.region.id for site in site_records if site.region}
    for _ in range(5):
        pending_region_ids -= regions.keys()
        if not pending_region_ids:
            break
        region_records = bulk_filter(
            nb.dcim.regions,
            id=sorted(pending_region_ids),
            fields="id,name,parent",
        )
        regions.update({region.id: region for region in region_records})
        pending_region_ids = {
            region.parent.id for region in region_records if region.parent
        }

    rack_ids = sorted({device.rack.id for device in devices if device.rack})
    racks = {}
    if rack_ids:
        rack_records = bulk_filter(
            nb.dcim.racks,
            id=rack_ids,
            fields="id,name,location,group",
        )
        racks = {rack.id: rack for rack in rack_records}

    device_scopes = {}
    for device in devices:
        site = sites[device.site.id]
        rack = racks.get(device.rack.id) if device.rack else None
        location = device.location or (rack.location if rack else None)
        rack_group = rack.group if rack else None
        region_ids = set()
        region = regions.get(site.region.id) if site.region else None
        while region and len(region_ids) < 5 and region.id not in region_ids:
            region_ids.add(region.id)
            region = regions.get(region.parent.id) if region.parent else None
        if site.region:
            region_ids.add(site.region.id)

        device_scopes[str(device.name)] = {
            "device_name": str(device.name),
            "site": site,
            "region": site.region,
            "region_ids": region_ids,
            "sitegroup": site.group,
            "location": location,
            "rack": rack,
            "rackgroup": rack_group,
        }
    return device_scopes


def validate_vlan_group_scope(
    vlan_group: Any,
    device_scope: dict,
    vid: int,
) -> Union[str, None]:
    """Return why a VLAN group is unavailable for a device and VID."""
    # NetBox returns VID ranges as inclusive integer pairs. Check the intervals
    # directly instead of expanding a potentially large range into every VID.
    if not any(start <= vid <= end for start, end in vlan_group.vid_ranges):
        return (
            f"VLAN {vid} is outside VLAN group '{vlan_group.name}' VID ranges "
            f"{vlan_group.vid_ranges}"
        )

    # An unscoped group is available to every device.
    if not vlan_group.scope_type:
        return None

    scope_type = str(vlan_group.scope_type).split(".")[-1].replace("_", "")
    device_name = device_scope["device_name"]
    if scope_type in {"cluster", "clustergroup"}:
        return (
            f"VLAN group '{vlan_group.name}' uses ignored scope type "
            f"'{scope_type}' for device '{device_name}'"
        )

    # Regions include bounded parent traversal; other scopes require a direct match.
    display_types = {"sitegroup": "site group", "rackgroup": "rack group"}
    if scope_type not in device_scope:
        return (
            f"VLAN group '{vlan_group.name}' uses unsupported scope type "
            f"'{scope_type}' for device '{device_name}'"
        )

    device_value = device_scope[scope_type]
    if scope_type == "region":
        matches_scope = vlan_group.scope_id in device_scope.get("region_ids", set())
    else:
        matches_scope = device_value and device_value.id == vlan_group.scope_id
    if matches_scope:
        return None

    display_type = display_types.get(scope_type, scope_type)
    device_assignment = f"'{device_value.name}'" if device_value else "no assignment"
    return (
        f"VLAN group '{vlan_group.name}' is scoped to {display_type} "
        f"'{vlan_group.scope.name}', but device '{device_name}' has "
        f"{display_type} {device_assignment}"
    )


def resolve_live_vlans(
    live_vlans: list[dict],
    netbox_vlans: Iterable,
    vlan_groups: dict[int, Any],
    device_scopes: dict[str, dict],
) -> list[dict]:
    """Resolve live VLANs by VID/group against device-compatible NetBox VLANs."""
    # One VID can exist in several NetBox sites and groups, so retain all
    # candidates instead of selecting the first API result.
    candidates_by_vid = {}
    for vlan in netbox_vlans:
        candidates_by_vid.setdefault(vlan.vid, []).append(vlan)

    results = []
    for live_vlan in live_vlans:
        device_scope = device_scopes[live_vlan["device_name"]]
        selected_group_id = live_vlan.get("selected_group_id")
        error = None
        # An explicit vlan_map/vlan_group selection is authoritative. Validate
        # it before searching and never fall back when its scope is incompatible.
        if selected_group_id:
            error = validate_vlan_group_scope(
                vlan_groups[selected_group_id], device_scope, live_vlan["vid"]
            )

        # Prefer a compatible group, then the device site, then a global VLAN.
        matches = []
        best_priority = None
        if error is None:
            for vlan in candidates_by_vid.get(live_vlan["vid"], []):
                vlan_group_id = vlan.group.id if vlan.group else None
                if selected_group_id and vlan_group_id != selected_group_id:
                    continue

                if vlan_group_id:
                    if validate_vlan_group_scope(
                        vlan_groups[vlan_group_id], device_scope, live_vlan["vid"]
                    ):
                        continue
                    priority = 0
                elif vlan.site and vlan.site.id == device_scope["site"].id:
                    priority = 1
                elif not vlan.site:
                    priority = 2
                else:
                    continue

                if best_priority is None or priority < best_priority:
                    matches = [vlan]
                    best_priority = priority
                elif priority == best_priority:
                    matches.append(vlan)

        matched_vlan = None
        if len(matches) == 1:
            matched_vlan = matches[0]
        elif len(matches) > 1:
            match_ids = ", ".join(str(vlan.id) for vlan in matches)
            error = (
                f"multiple equally preferred NetBox VLANs match VID "
                f"{live_vlan['vid']} for device '{live_vlan['device_name']}' "
                f"(VLAN IDs: {match_ids})"
            )

        scope = None
        scope_payload = None
        if error is None:
            if matched_vlan and matched_vlan.group:
                group = vlan_groups[matched_vlan.group.id]
                scope = f"group:{group.name}"
                scope_payload = {"group": group.id}
            elif matched_vlan and matched_vlan.site:
                scope = f"site:{device_scope['site'].name}"
                scope_payload = {"site": matched_vlan.site.id}
            elif matched_vlan:
                scope, scope_payload = "global", {}
            elif selected_group_id:
                group = vlan_groups[selected_group_id]
                scope = f"group:{group.name}"
                scope_payload = {"group": group.id}
            else:
                scope = f"site:{device_scope['site'].name}"
                scope_payload = {"site": device_scope["site"].id}

        results.append(
            {
                "live": live_vlan,
                "vlan": matched_vlan,
                "error": error,
                "scope": scope,
                "scope_payload": scope_payload,
            }
        )
    return results


VLAN_MEMBERSHIP_FIELDS = ("tagged_interfaces", "untagged_interfaces")


class NetboxVlansTasks:
    @Task(
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=CreateVlanGroupInput,
        output=CreateVlanGroupResult,
    )
    def create_vlan_group(
        self,
        job: Job,
        name: str,
        site: str,
        vid_ranges: list,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        branch: Union[None, str] = None,
    ) -> Result:
        """Create or update a VLAN group scoped to one NetBox site.

        Groups are matched by name, not by site. An existing group is patched
        with the supplied site and VID ranges. A dry run reports the planned
        action without writing to NetBox.

        Args:
            job: Current NorFab job for events and branch provisioning.
            name: VLAN group name used to find an existing group.
            site: Name of the site that scopes the group; it must exist.
            vid_ranges: Allowed VLAN ID ranges in the NetBox API format.
            instance: NetBox instance name, or the worker default when omitted.
            dry_run: Report the planned create or update without writing.
            branch: Optional NetBox Branching plugin branch name.

        Returns:
            Result: Group name, site, and ranges with a created or updated status.

        Raises:
            ValueError: The named site does not exist.
        """
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:create_vlan_group",
            result={"name": name, "site": site, "vid_ranges": vid_ranges},
            resources=[instance],
            dry_run=dry_run,
        )
        nb = self._get_pynetbox(instance, branch=branch, job=job)
        nb_site = nb.dcim.sites.get(name=site)
        if not nb_site:
            raise ValueError(f"Site '{site}' not found in NetBox")
        group = nb.ipam.vlan_groups.get(name=name)
        payload = {
            "name": name,
            "slug": slugify(name),
            "scope_type": "dcim.site",
            "scope_id": nb_site.id,
            "vid_ranges": vid_ranges,
        }
        if dry_run:
            ret.status = "updated" if group else "created"
        elif group:
            group.update(payload)
            ret.status = "updated"
        else:
            nb.ipam.vlan_groups.create(payload)
            ret.status = "created"
        job.event(f"{ret.status} VLAN group '{name}'")
        return ret

    @Task(
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=CreateVlanInput,
        output=CreateVlanResult,
        mcp={
            "annotations": {
                "title": "Create VLAN",
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def create_vlan(
        self,
        job: Job,
        vlan_group: str,
        name: str,
        vid: Union[None, int] = None,
        status: str = "active",
        description: Union[None, str] = None,
        tenant: Union[None, str] = None,
        role: Union[None, str] = None,
        tags: Union[None, list] = None,
        custom_fields: Union[None, dict] = None,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        branch: Union[None, str] = None,
    ) -> Result:
        """Create, update, or allocate a VLAN in an existing group.

        A supplied VID identifies the VLAN within its group. Without a VID,
        an existing VLAN is matched by group and name, or the first available
        VID is allocated. Repeated calls without a VID and with the same name
        reuse that VLAN. Tags and array custom fields add values on updates;
        scalar custom fields replace their values.
        Existing VLANs are patched without a local diff check.
        Dry-run reports the selected VID but does not write attributes.

        Args:
            job: Current NorFab job for events and branch provisioning.
            vlan_group: Name of the existing VLAN group.
            name: VLAN name to create or assign to the matched VLAN.
            vid: Explicit VLAN ID; omit to allocate from the group.
            status: NetBox VLAN status, defaulting to active.
            description: Optional VLAN description.
            tenant: Optional tenant name.
            role: Optional IPAM role name.
            tags: Optional tag names to add without removing existing tags.
            custom_fields: Optional NetBox custom-field values. Arrays add
                missing values; empty arrays preserve existing arrays. Null and
                scalar values replace existing values. Object and multiobject
                fields accept related object names or IDs.
            instance: NetBox instance name, or the worker default when omitted.
            dry_run: Select a VLAN without creating or updating it.
            branch: Optional NetBox Branching plugin branch name.

        Returns:
            Result: Selected VLAN ID, name, group, and action. Applied results
            also include the NetBox object ID.

        Raises:
            ValueError: The group is missing, the match is ambiguous, or no
                VLAN IDs remain available for allocation.
        """
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:create_vlan",
            result={},
            resources=[instance],
            dry_run=dry_run,
        )
        nb = self._get_pynetbox(instance, branch=branch, job=job)
        group = nb.ipam.vlan_groups.get(name=vlan_group)
        if not group:
            raise ValueError(f"VLAN group '{vlan_group}' not found in NetBox")

        filters = (
            {"group_id": group.id, "vid": vid}
            if vid
            else {
                "group_id": group.id,
                "name": name,
            }
        )
        matches = self.bulk_filter(nb.ipam.vlans, **filters)
        if len(matches) > 1:
            raise ValueError(f"VLAN identity {filters} matched more than one VLAN")
        nb_vlan = matches[0] if matches else None

        if not nb_vlan and vid is None:
            available = group.available_vlans.list()
            if not available:
                raise ValueError(f"VLAN group '{vlan_group}' has no available VLAN IDs")
            vid = int(getattr(available[0], "vid", available[0]))
        if dry_run:
            ret.result = {
                "vid": int(nb_vlan.vid) if nb_vlan else vid,
                "name": name,
                "vlan_group": vlan_group,
                "status": "update" if nb_vlan else "create",
            }
            return ret

        payload = {"name": name, "status": status}
        if description is not None:
            payload["description"] = description
        if tenant is not None:
            payload["tenant"] = {"name": tenant}
        if role is not None:
            payload["role"] = {"name": role}
        if tags:
            payload["tags"] = [{"name": tag} for tag in tags]
        if custom_fields is not None:
            reference_fields = self.bulk_filter(
                nb.extras.custom_fields,
                object_type="ipam.vlan",
                type=["object", "multiobject"],
            )
            # Resolve names on creation and merge with current values on updates.
            _, payload["custom_fields"] = merge_resolved_custom_fields(
                self,
                nb,
                nb_vlan,
                custom_fields,
                [field for field in reference_fields if field.type.value == "object"],
                [
                    field
                    for field in reference_fields
                    if field.type.value == "multiobject"
                ],
            )

        if nb_vlan:
            if tags:
                payload["tags"] = merge_array_values(
                    nb_vlan.tags, tags, attribute="name"
                )
            nb_vlan.update(payload)
            ret.status = "updated"
        elif filters.get("vid") is None:
            nb_vlan = group.available_vlans.create(payload)
            ret.status = "created"
        else:
            nb_vlan = nb.ipam.vlans.create({"vid": vid, "group": group.id, **payload})
            ret.status = "created"

        ret.result = {
            "id": nb_vlan.id,
            "vid": int(nb_vlan.vid),
            "name": nb_vlan.name,
            "vlan_group": vlan_group,
            "status": ret.status,
        }
        job.event(f"{ret.status} VLAN {nb_vlan.vid} '{nb_vlan.name}'")
        return ret

    @Task(
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=SyncVlansInput,
        output=SyncVlansResult,
        mcp={
            "annotations": {
                "title": "Sync VLANs",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def sync_vlans(
        self,
        job: Job,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        with_approval: bool = False,
        timeout: int = 600,
        devices: Union[None, list] = None,
        branch: Union[None, str] = None,
        interface_map: Union[None, str, list] = None,
        vlan_group: Union[None, str] = None,
        vlan_map: Union[None, str, list] = None,
        require_vlan_group: bool = False,
        filter_by_vlan_ids: Union[None, list[str]] = None,
        preserve_description: Union[None, bool] = None,
        batch_size: int = 1000,
        preserve_name: bool = False,
        **kwargs: Any,
    ) -> Result:
        """Synchronize live VLAN attributes and interface memberships with NetBox.

        VLANs are mapped by the first matching ``vlan_map`` rule. Rule criteria
        match VLAN IDs, VLAN names, device names, and each interface name;
        populated criteria are combined with AND. VLANs which match no rule use
        ``vlan_group`` when supplied. Otherwise, they use their device site
        unless ``require_vlan_group=True``.

        Name conflicts with NetBox or between proposed VLANs in the same scope
        are reported and skipped. The first proposed name is retained; skipped
        creations are also removed from interface membership targets.

        Args:
            job: NorFab job object.
            instance: NetBox instance name. Uses the default instance when omitted.
            dry_run: Return the calculated diff without writing to NetBox.
            with_approval: Ask for approval before applying the prepared diff.
            timeout: Timeout in seconds for Nornir host resolution and parsing.
            devices: Explicit NetBox and Nornir device names.
            branch: NetBox Branching plugin branch name.
            interface_map: Interface rename rules shared with interface sync.
            vlan_group: Group for VLANs not matched by ``vlan_map``.
            vlan_map: Ordered VLAN-to-group mapping rules, or an ``nf://`` YAML
                file containing them.
            require_vlan_group: Require every VLAN to resolve to a VLAN group
                instead of falling back to its device site.
            filter_by_vlan_ids: VLAN IDs or inclusive ranges to reconcile.
            preserve_description: Description preservation policy. ``None`` preserves
                NetBox text when the live description is empty, ``True`` always
                preserves NetBox text, and ``False`` always uses live text.
            batch_size: Maximum number of objects per bulk write.
            preserve_name: Keep existing NetBox VLAN names when ``True``.
                Defaults to ``False`` to use descriptive live names. New VLANs
                always use live names; generated ``VLAN<VID>`` live names never
                replace existing NetBox names.
            **kwargs: Nornir FFun host filters.

        Returns:
            Result: Per-device created, updated, deleted and in_sync references.
                Diff contains per-device VLAN actions by scope and interface field changes.
        """
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:sync_vlans",
            result={},
            resources=[instance],
            dry_run=dry_run,
            diff={},
        )
        message = f"starting VLAN sync using NetBox instance '{instance}'"
        job.event(message)
        log.info(message)
        nb = self._get_pynetbox(instance, branch=branch, job=job)
        # Combine explicit devices and host filters without processing duplicates.
        selected_devices = set(devices or [])
        if kwargs:
            selected_devices.update(self.get_nornir_hosts(kwargs, timeout))
        devices = sorted(selected_devices)
        if not devices:
            message = "no devices specified"
            job.event(message, severity="ERROR")
            log.error(message)
            ret.errors.append(message)
            ret.failed = True
            return ret
        # Prepare VID filters and mapping rules before collecting device data.
        selected_vids = set()
        for value in filter_by_vlan_ids or []:
            selected_vids.update(
                (int(vid) for vid in expand_alphanumeric_range(f"[{value}]"))
            )
        try:
            if self.is_url(vlan_map):
                vlan_map = TypeAdapter(list[VlanMapRule]).validate_python(
                    yaml.safe_load(self.fetch_file(vlan_map, raise_on_fail=True)) or []
                )
            if self.is_url(interface_map):
                interface_map = TypeAdapter(list[InterfaceMapRule]).validate_python(
                    yaml.safe_load(self.fetch_file(interface_map, raise_on_fail=True))
                    or []
                )
        except Exception as exc:
            message = f"failed to load VLAN sync mapping: {exc}"
            job.event(message, severity="ERROR")
            log.error(message)
            ret.errors.append(message)
            ret.failed = True
            return ret
        # Expand rule ranges once rather than for every VLAN match.
        interface_map = [dict(rule) for rule in interface_map or []]
        rules = []
        for rule in vlan_map or []:
            rule = dict(rule)
            expanded_vlan_ids = set()
            for value in rule.get("match_vlan_ids") or []:
                expanded_vlan_ids.update(
                    (int(vid) for vid in expand_alphanumeric_range(f"[{value}]"))
                )
            rule["expanded_vlan_ids"] = expanded_vlan_ids or None
            rules.append(rule)

        # Load device context used to validate VLAN scopes.
        netbox_devices = self.bulk_filter(
            nb.dcim.devices,
            name=devices,
            fields="id,name,site,location,rack,device_type",
        )
        nb_devices = {str(device.name): device for device in netbox_devices}
        for device in devices:
            if device not in nb_devices:
                message = f"device '{device}' not found in NetBox"
                job.event(message, severity="ERROR")
                log.error(message)
                ret.errors.append(message)
        if not nb_devices:
            ret.failed = True
            return ret
        device_scopes = load_device_vlan_scopes(
            nb_devices.values(), nb, self.bulk_filter
        )
        # Collect and normalize live VLANs before loading their NetBox matches.
        message = f"collecting live VLANs from {len(nb_devices)} device(s)"
        job.event(message)
        log.info(message)
        parsed = self.client.run_job(
            "nornir",
            "parse_ttp",
            workers="all",
            timeout=timeout,
            kwargs={"get": "vlans", "FL": sorted(nb_devices)},
        )
        live_by_device = {}
        for worker, response in parsed.items():
            resources_failed = response.get("resources_failed") or []
            if resources_failed:
                ret.resources_failed = sorted(
                    set(ret.resources_failed) | set(resources_failed)
                )
                message = f"{worker} failed to fetch VLAN data from devices {', '.join(sorted(resources_failed))}"
                job.event(message, severity="ERROR")
                log.error(message)
                ret.errors.append(message)
            if response.get("failed"):
                message = f"worker '{worker}' failed to collect live VLAN data"
                job.event(message, severity="ERROR")
                log.error(message)
                ret.errors.append(message)
                continue
            for device, records in response["result"].items():
                live_by_device.setdefault(device, []).extend(records)
        live_vlans = []
        interface_names_by_device = {}
        for device, records in sorted(live_by_device.items()):
            device_model = str(nb_devices[device].device_type.model)
            interface_names = {}
            # Merge duplicate parser records before choosing a scope.
            device_vlans = {}
            for record in records:
                vid = record["vid"]
                if selected_vids and vid not in selected_vids:
                    continue
                for field in VLAN_MEMBERSHIP_FIELDS:
                    for live_interface in record[field]:
                        if live_interface in interface_names:
                            continue
                        interface_names[live_interface] = map_interface_name(
                            live_interface, interface_map, device, device_model
                        )
                name = record["name"].strip()
                description = (record["description"] or "").strip()
                vlan = device_vlans.setdefault(
                    vid,
                    {
                        "device_name": device,
                        "vid": vid,
                        "name": name,
                        "description": description,
                        "tagged_interfaces": [],
                        "untagged_interfaces": [],
                    },
                )
                if (
                    vlan["name"].casefold() == f"vlan{vid}".casefold()
                    and name.casefold() != f"vlan{vid}".casefold()
                ):
                    vlan["name"] = name
                if description and (not vlan["description"]):
                    vlan["description"] = description
                for field in VLAN_MEMBERSHIP_FIELDS:
                    for name in record[field]:
                        if name not in vlan[field]:
                            vlan[field].append(name)
            # Match rules against the interface names used in NetBox.
            for vlan in device_vlans.values():
                mapped_interfaces = []
                for field in VLAN_MEMBERSHIP_FIELDS:
                    for name in vlan[field]:
                        mapped_interfaces.append(interface_names[name])
                group_name = (
                    match_vlan_map(
                        rules, vlan["vid"], vlan["name"], device, mapped_interfaces
                    )
                    or vlan_group
                )
                if require_vlan_group and (not group_name):
                    message = f"skipping VLAN {vlan['vid']} from device '{device}': no VLAN group mapping found"
                    job.event(message, severity="ERROR")
                    log.error(message)
                    ret.errors.append(message)
                    continue
                vlan["selected_group_name"] = group_name
                live_vlans.append(vlan)
            interface_names_by_device[device] = interface_names
        message = f"normalized {len(live_vlans)} live VLAN record(s) from {len(live_by_device)} device(s)"
        job.event(message)
        log.info(message)
        # Load VLAN candidates, then all explicit and discovered groups together.
        vids = sorted({vlan["vid"] for vlan in live_vlans})
        candidates = []
        if vids:
            candidates = self.bulk_filter(
                nb.ipam.vlans, vid=vids, fields="id,vid,name,description,site,group"
            )
        configured_groups = {rule["set_vlan_group"] for rule in rules}
        if vlan_group:
            configured_groups.add(vlan_group)
        groups_by_name = {}
        if configured_groups:
            groups_by_name = {
                str(group.name): group
                for group in self.bulk_filter(
                    nb.ipam.vlan_groups,
                    name=sorted(configured_groups),
                    fields="id,name,vid_ranges,scope_type,scope_id,scope",
                )
            }
        for name in sorted(configured_groups - groups_by_name.keys()):
            message = f"vlan group '{name}' does not exist in NetBox"
            job.event(message, severity="ERROR")
            log.error(message)
            ret.errors.append(message)
        groups = {group.id: group for group in groups_by_name.values()}
        missing_groups = sorted(
            {vlan.group.id for vlan in candidates if vlan.group} - groups.keys()
        )
        if missing_groups:
            for group in self.bulk_filter(
                nb.ipam.vlan_groups,
                id=missing_groups,
                fields="id,name,vid_ranges,scope_type,scope_id,scope",
            ):
                groups[group.id] = group
        if not live_by_device:
            message = "no live VLAN data collected"
            job.event(message, severity="ERROR")
            log.error(message)
            ret.errors.append(message)
            ret.failed = True
            return ret
        live_vlans = [
            vlan
            for vlan in live_vlans
            if not vlan["selected_group_name"]
            or vlan["selected_group_name"] in groups_by_name
        ]
        for vlan in live_vlans:
            group = groups_by_name.get(vlan.pop("selected_group_name"))
            vlan["selected_group_id"] = group.id if group else None

        message = f"loaded {len(candidates)} NetBox VLAN candidate(s) and {len(groups)} VLAN group(s)"
        job.event(message)
        log.info(message)
        # Resolve VLAN scopes and apply per-device preservation and shared-source rules.
        contributors = {}
        from_live = {
            device: {"vlans": {}, "interfaces": {}} for device in live_by_device
        }
        from_netbox = {
            device: {"vlans": {}, "interfaces": {}} for device in live_by_device
        }
        ret.diff = {
            device: {
                "vlans": {},
                "interfaces": {"create": [], "update": {}, "delete": [], "in_sync": []},
            }
            for device in from_live
        }
        preview = {
            device: {
                action: set() for action in ("created", "updated", "deleted", "in_sync")
            }
            for device in from_live
        }
        completed_refs = {}
        scope_payloads = {}
        vlan_records = {}
        sources = {}
        interface_targets = {}
        for resolved in resolve_live_vlans(
            live_vlans, candidates, groups, device_scopes
        ):
            observation, existing = (resolved["live"], resolved["vlan"])
            device, vid = (observation["device_name"], observation["vid"])
            if resolved["error"]:
                message = (
                    f"vlan {vid} from device '{device}' skipped: {resolved['error']}"
                )
                if observation["selected_group_id"]:
                    message += (
                        "; fix the VLAN group scope, VID ranges, or group mapping"
                    )
                job.event(message, severity="ERROR")
                log.error(message)
                ret.errors.append(message)
                continue
            scope = resolved["scope"]
            contributors.setdefault((scope, vid), set()).add(device)
            # Keep each device's values so shared VLANs do not mix their diffs.
            desired = {
                "name": observation["name"],
                "description": observation["description"],
            }
            if existing is not None:
                current = {
                    "name": str(existing.name).strip(),
                    "description": str(existing.description or "").strip(),
                }
                from_netbox[device]["vlans"][vid, scope] = current
                if preserve_name or desired["name"].casefold() == f"vlan{vid}":
                    desired["name"] = current["name"]
                desired["description"] = apply_description_policy(
                    desired["description"], current["description"], preserve_description
                )
            from_live[device]["vlans"][vid, scope] = desired
            scope_payloads[scope] = resolved["scope_payload"]
            key = (scope, vid)
            vlan_records[key] = existing
            # Remember which device supplies each field when VLANs are shared.
            if key not in sources:
                sources[key] = {
                    field: (device, observation[field])
                    for field in ("name", "description")
                }
            else:
                source_device, source_name = sources[key]["name"]
                name = observation["name"]
                automatic_name = f"VLAN{vid}".casefold()
                if (
                    source_name.casefold() == automatic_name
                    and name.casefold() != automatic_name
                ):
                    sources[key]["name"] = (device, name)
                elif (
                    source_name != name
                    and source_name.casefold() != automatic_name
                    and name.casefold() != automatic_name
                ):
                    message = f"{scope} VLAN {vid} source conflict (name): using VLAN name '{source_name}' from device '{source_device}'; conflicting device '{device}' reports VLAN name '{name}'"
                    if message not in ret.errors:
                        job.event(message, severity="ERROR")
                        log.error(message)
                        ret.errors.append(message)
                source_device, description = sources[key]["description"]
                if observation["description"] and not description:
                    sources[key]["description"] = (device, observation["description"])
                elif (
                    description
                    and observation["description"]
                    and description != observation["description"]
                ):
                    message = f"{scope} VLAN {vid} source conflict (description): using live description from device '{source_device}'; conflicting device '{device}' reports a different description"
                    if message not in ret.errors:
                        job.event(message, severity="ERROR")
                        log.error(message)
                        ret.errors.append(message)
            vlan_reference = f"{scope}/{vid}"
            for field in VLAN_MEMBERSHIP_FIELDS:
                for live_interface in observation[field]:
                    interface = interface_names_by_device[device][live_interface]
                    target = interface_targets.setdefault(
                        (device, interface),
                        {"tagged_vlans": set(), "untagged_vlan": None},
                    )
                    if field == "tagged_interfaces":
                        target["tagged_vlans"].add(vlan_reference)
                    else:
                        target["untagged_vlan"] = vlan_reference
        skipped_vlans = set()
        # Catch name conflicts before one invalid VLAN can fail a whole batch.
        proposed_names = {
            from_live[fields["name"][0]]["vlans"][vid, scope]["name"]
            for (scope, vid), fields in sources.items()
        }
        name_matches = []
        if proposed_names:
            name_matches = self.bulk_filter(
                nb.ipam.vlans,
                name=sorted(proposed_names),
                fields="id,vid,name,site,group",
            )
        names_in_netbox = {}
        for vlan in name_matches:
            scope = (
                f"group:{vlan.group.name}"
                if vlan.group
                else f"site:{vlan.site.name}" if vlan.site else "global"
            )
            names_in_netbox.setdefault((scope, str(vlan.name)), []).append(vlan)
        seen_names = {}
        for (scope, vid), fields in sources.items():
            name = from_live[fields["name"][0]]["vlans"][vid, scope]["name"]
            existing = vlan_records[scope, vid]
            conflicts = [
                vlan.vid
                for vlan in names_in_netbox.get((scope, name), ())
                if existing is None or vlan.id != existing.id
            ]
            conflict = conflicts[0] if conflicts else seen_names.get((scope, name))
            if conflict is None:
                seen_names[scope, name] = vid
                continue
            action = "update" if existing is not None else "create"
            skipped_vlans.add((scope, vid))
            if existing is not None:
                seen_names[scope, str(existing.name).strip()] = vid
            else:
                # Remove assignments to VLANs whose creation was skipped.
                reference = f"{scope}/{vid}"
                for target in interface_targets.values():
                    target["tagged_vlans"].discard(reference)
                    if target["untagged_vlan"] == reference:
                        target["untagged_vlan"] = None
            label = "VLAN" if conflicts else "vlan"
            message = f"{label} {vid} name '{name}' overlaps with VLAN {conflict} in scope '{scope}'; skipping VLAN {action}"
            job.event(message, severity="ERROR")
            log.error(message)
            ret.errors.append(message)
        # Compare all device VLANs before collecting shared NetBox writes.
        vlan_diff = DeepDiff(
            {device: data["vlans"] for device, data in from_netbox.items()},
            {device: data["vlans"] for device, data in from_live.items()},
            ignore_order=True,
            view="tree",
            threshold_to_diff_deeper=0,
        )
        changed_vlans = {
            tuple(change.path(output_format="list")[:2])
            for changes in vlan_diff.values()
            for change in changes
        }
        # Report VLAN drift per device, even when devices share one NetBox VLAN.
        for device in from_live:
            ret.result[device] = {action: [] for action in preview[device]}
            before = from_netbox[device]["vlans"]
            after = from_live[device]["vlans"]
            for vid, scope in sorted(before.keys() | after.keys()):
                key = (vid, scope)
                summary = ret.diff[device]["vlans"].setdefault(
                    scope, {"create": [], "update": {}, "delete": [], "in_sync": []}
                )
                if key not in before:
                    summary["create"].append(vid)
                elif key not in after:
                    summary["delete"].append(vid)
                elif (device, key) in changed_vlans:
                    summary["update"][str(vid)] = {
                        field: {"old_value": before[key][field], "new_value": value}
                        for field, value in after[key].items()
                        if value != before[key][field]
                    }
                else:
                    summary["in_sync"].append(vid)
                    preview[device]["in_sync"].add(f"{scope}:{vid}")

        # Deduplicate writes when several device diffs target the same VLAN.
        creates, updates = {}, {}
        for changes in vlan_diff.values():
            for change in changes:
                path = change.path(output_format="list")
                device, (vid, scope) = path[:2]
                if (vid, scope) not in from_live[device]["vlans"]:
                    continue
                # Keep skipped VLAN drift visible without including it in write batches.
                if (scope, vid) in skipped_vlans:
                    continue
                existing = vlan_records[scope, vid]
                if existing is None:
                    creates[scope, vid] = {
                        "vid": vid,
                        **{
                            field: from_live[source]["vlans"][vid, scope][field]
                            for field, (source, _) in sources[scope, vid].items()
                        },
                        **scope_payloads[scope],
                    }
                else:
                    # Read only the changed field from the device selected for that field.
                    field = path[2]
                    source, _ = sources[scope, vid][field]
                    value = from_live[source]["vlans"][vid, scope][field]
                    # Another device's drift may select a value already present in NetBox.
                    if value != from_netbox[device]["vlans"][vid, scope][field]:
                        updates.setdefault((scope, vid), {"id": existing.id})[
                            field
                        ] = value
        creates, updates = sorted(creates.items()), sorted(updates.items())
        # Report each shared VLAN write under every device that contributed to it.
        for action, items in (("created", creates), ("updated", updates)):
            for (scope, vid), _ in items:
                refs = [
                    (device, action, f"{scope}:{vid}")
                    for device in sorted(contributors[scope, vid])
                ]
                completed_refs[action, (scope, vid)] = refs
                for device, _, label in refs:
                    preview[device][action].add(label)

        # Load interface assignments and preserve VLANs outside the selected filter.
        netbox_interfaces = self.bulk_filter(
            nb.dcim.interfaces,
            device_id=sorted((device.id for device in nb_devices.values())),
            fields="id,name,device,mode,tagged_vlans,untagged_vlan",
        )
        interfaces = {}
        for interface in netbox_interfaces:
            key = (str(interface.device.name), str(interface.name))
            if key in interface_targets:
                interfaces[key] = interface
        message = f"loaded {len(interfaces)} NetBox interface(s) for VLAN membership"
        job.event(message)
        log.info(message)
        for device, name in sorted(interface_targets.keys() - interfaces.keys()):
            message = f"interface '{device}:{name}' not found in NetBox"
            job.event(message, severity="ERROR")
            log.error(message)
            ret.errors.append(message)
        assigned_vlan_ids = set()
        for key in interfaces:
            interface = interfaces[key]
            assigned_vlan_ids.update((vlan.id for vlan in interface.tagged_vlans))
            if interface.untagged_vlan:
                assigned_vlan_ids.add(interface.untagged_vlan.id)
        membership_vlans = {vlan.id: vlan for vlan in candidates}
        # Include assigned VLANs outside the filter so existing memberships survive.
        missing_vlan_ids = assigned_vlan_ids - membership_vlans.keys()
        if missing_vlan_ids:
            for vlan in self.bulk_filter(
                nb.ipam.vlans,
                id=sorted(missing_vlan_ids),
                fields="id,vid,name,description,site,group",
            ):
                membership_vlans[vlan.id] = vlan
        vlan_id_by_reference = {}
        vlan_reference_by_id = {}
        for vlan in membership_vlans.values():
            if vlan.group:
                scope = f"group:{vlan.group.name}"
            elif vlan.site:
                scope = f"site:{vlan.site.name}"
            else:
                scope = "global"
            vlan_reference = f"{scope}/{vlan.vid}"
            vlan_id_by_reference[vlan_reference] = vlan.id
            vlan_reference_by_id[vlan.id] = vlan_reference
        # Compare memberships separately from VLAN names and descriptions.
        interface_states = {}
        for device, name in sorted(interface_targets):
            interface = interfaces.get((device, name))
            untagged_reference = None
            if interface and interface.untagged_vlan:
                untagged_reference = vlan_reference_by_id[interface.untagged_vlan.id]
            current = {
                "mode": interface.mode.value if interface and interface.mode else None,
                "tagged_vlans": sorted(
                    (vlan_reference_by_id[vlan.id] for vlan in interface.tagged_vlans)
                    if interface
                    else ()
                ),
                "untagged_vlan": untagged_reference,
            }
            target = interface_targets[device, name]
            # Add live tagged VLANs while retaining existing NetBox assignments.
            tagged_vlans = set(current["tagged_vlans"])
            tagged_vlans.update(target["tagged_vlans"])
            untagged_vlan = current["untagged_vlan"]
            # Replace the native VLAN only when the device reports one.
            if target["untagged_vlan"] is not None:
                untagged_vlan = target["untagged_vlan"]
            mode = current["mode"]
            if tagged_vlans:
                mode = "tagged"
            elif untagged_vlan:
                mode = "access"
            desired = {
                "mode": mode,
                "tagged_vlans": sorted(tagged_vlans),
                "untagged_vlan": untagged_vlan,
            }
            interface_states[device, name] = (current, desired)
            for snapshot, state in ((from_netbox, current), (from_live, desired)):
                references = set(state["tagged_vlans"])
                if state["untagged_vlan"]:
                    references.add(state["untagged_vlan"])
                # Include tagging and mode in each device/interface/VLAN/scope entry.
                for reference in references:
                    scope, vid = reference.rsplit("/", 1)
                    snapshot[device]["interfaces"][name, int(vid), scope] = {
                        "tagged": reference in state["tagged_vlans"],
                        "untagged": reference == state["untagged_vlan"],
                        "mode": state["mode"],
                    }
        interface_diff = DeepDiff(
            {device: data["interfaces"] for device, data in from_netbox.items()},
            {device: data["interfaces"] for device, data in from_live.items()},
            ignore_order=True,
            view="tree",
            threshold_to_diff_deeper=0,
        )
        changed_memberships = {
            tuple(change.path(output_format="list")[:2])
            for changes in interface_diff.values()
            for change in changes
        }
        changed_interfaces = {
            (device, identity[0]) for device, identity in changed_memberships
        }
        interface_updates = {}
        for (device, name), (current, desired) in interface_states.items():
            if (device, name) not in changed_interfaces:
                ret.diff[device]["interfaces"]["in_sync"].append(name)
                continue
            # Format field changes only for interfaces selected by DeepDiff.
            ret.diff[device]["interfaces"]["update"][name] = {
                field: {"old_value": current[field], "new_value": value}
                for field, value in desired.items()
                if value != current[field]
            }
            if (device, name) in interfaces:
                interface_updates[device, name] = desired
        # Track membership actions to report when each interface write succeeds.
        for device in from_live:
            before = from_netbox[device]["interfaces"]
            after = from_live[device]["interfaces"]
            for key in sorted(before.keys() | after.keys()):
                name, vid, scope = key
                label = f"{scope}:{vid}"
                if (
                    key in before
                    and key in after
                    and (device, key) not in changed_memberships
                ):
                    if (device, (vid, scope)) not in changed_vlans:
                        preview[device]["in_sync"].add(label)
                    continue
                if (device, name) in interfaces:
                    # Membership changes update VLAN usage, not the VLAN record's existence.
                    preview[device]["updated"].add(label)
                    completed_refs.setdefault(
                        ("interfaces", (device, name)), []
                    ).append((device, "updated", label))
        # Finalize the preview before approval or any NetBox writes.
        for device, actions in preview.items():
            actions["in_sync"] -= (
                actions["created"] | actions["updated"] | actions["deleted"]
            )
            ret.result[device]["in_sync"] = sorted(actions["in_sync"])
        for actions in preview.values():
            for action, values in actions.items():
                actions[action] = sorted(values)
        message = f"prepared {len(creates)} VLAN creation(s), {len(updates)} VLAN update(s), and {len(interface_updates)} interface update(s)"
        job.event(message)
        log.info(message)
        if dry_run:
            message = "dry-run requested, returning VLAN sync preview without changes"
            job.event(message)
            log.info(message)
            ret.result = preview
            return ret
        if with_approval and any(
            (
                actions[action]
                for actions in preview.values()
                for action in ("created", "updated", "deleted")
            )
        ):
            if not review_sync_task_result(job, "vlan sync", preview):
                ret.status, ret.dry_run, ret.result = ("skipped", True, preview)
                ret.messages.append("review declined; changes were not applied")
                message = "vlan sync review declined; changes were not applied"
                job.event(message)
                log.info(message)
                return ret
        # Create VLANs first so interface writes can use their new NetBox IDs.
        for stage, endpoint in (
            ("created", nb.ipam.vlans.create),
            ("updated", nb.ipam.vlans.update),
            ("interfaces", nb.dcim.interfaces.update),
        ):
            if stage == "created":
                items = creates
            elif stage == "updated":
                items = updates
            else:
                items = []
                for (device, name), desired in sorted(interface_updates.items()):
                    items.append(
                        (
                            (device, name),
                            {
                                "id": interfaces[device, name].id,
                                "mode": desired["mode"],
                                "tagged_vlans": [
                                    vlan_id_by_reference[ref]
                                    for ref in desired["tagged_vlans"]
                                ],
                                "untagged_vlan": vlan_id_by_reference.get(
                                    desired["untagged_vlan"]
                                ),
                            },
                        )
                    )
            operation = {
                "created": "VLAN creation",
                "updated": "VLAN update",
                "interfaces": "interface update",
            }[stage]
            total = (len(items) + batch_size - 1) // batch_size
            # Batch writes across all devices, separately for each API operation.
            for start in range(0, len(items), batch_size):
                batch = items[start : start + batch_size]
                message = f"applying {operation} batch {start // batch_size + 1}/{total} ({len(batch)} object(s))"
                job.event(message)
                log.info(message)
                try:
                    response = endpoint([payload for _, payload in batch])
                except Exception as exc:
                    message = f"{message} failed: {exc}"
                    ret.errors.append(message)
                    ret.failed = True
                    job.event(message, severity="ERROR")
                    log.error(message)
                    return ret
                if stage == "created":
                    for ((scope, vid), _), vlan in zip(batch, response):
                        vlan_id_by_reference[f"{scope}/{vid}"] = vlan.id
                # Record completed actions only after the batch succeeds.
                for key, _ in batch:
                    for device, action, label in completed_refs[stage, key]:
                        ret.result[device][action].append(label)
        for actions in ret.result.values():
            for action, values in actions.items():
                actions[action] = sorted(set(values))
        message = "vlan sync complete"
        job.event(message)
        log.info(message)
        return ret
