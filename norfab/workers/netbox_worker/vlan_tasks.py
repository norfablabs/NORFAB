import fnmatch
import logging
from collections.abc import Iterable
from typing import Any, Union

import yaml
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
    SyncActionSummary,
    SyncVlansInput,
    SyncVlansResult,
    SyncVlansResultPayload,
    VlanMapRule,
)
from .netbox_worker_utilities import (
    apply_description_policy,
    map_interface_name,
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
        """Create or update one site-scoped VLAN group."""
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
        """Create, update, or allocate one VLAN in a VLAN group."""
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
        if tags is not None:
            payload["tags"] = [{"name": tag} for tag in tags]
        if custom_fields is not None:
            payload["custom_fields"] = custom_fields

        if nb_vlan:
            nb_vlan.update(payload)
            ret.status = "updated"
        elif filters.get("vid") is None:
            nb_vlan = group.available_vlans.create(payload)
            ret.status = "created"
        else:
            nb_vlan = nb.ipam.vlans.create({"vid": vid, "group": group.id, **payload})
            ret.status = "created"

        ret.result = {
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
        **kwargs: Any,
    ) -> Result:
        """Synchronize live VLAN attributes and interface memberships with NetBox.

        VLANs are mapped by the first matching ``vlan_map`` rule. Rule criteria
        match VLAN IDs, VLAN names, device names, and each interface name;
        populated criteria are combined with AND. VLANs which match no rule use
        ``vlan_group`` when supplied. Otherwise, they use their device site
        unless ``require_vlan_group=True``.

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
            **kwargs: Nornir FFun host filters.

        Returns:
            Result: VLAN actions keyed by scope and interface actions keyed by device.
        """
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:sync_vlans",
            result=SyncVlansResultPayload().model_dump(),
            resources=[instance],
            dry_run=dry_run,
            diff={"vlans": {}, "interfaces": {}},
        )

        message = f"starting VLAN sync using NetBox instance '{instance}'"
        job.event(message)
        log.info(message)
        nb = self._get_pynetbox(instance, branch=branch, job=job)
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
        # Resolve the requested devices once; later stages use this same object map.
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
        message = f"loaded VLAN scopes for {len(nb_devices)} NetBox device(s)"
        job.event(message)
        log.info(message)
        selected_vids = set()
        for value in filter_by_vlan_ids or []:
            selected_vids.update(
                int(vid) for vid in expand_alphanumeric_range(f"[{value}]")
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
        interface_map = [dict(rule) for rule in interface_map or []]
        # Expand rule VID ranges once and discard missing groups from later lookups.
        rules = []
        for rule in vlan_map or []:
            rule = dict(rule)
            expanded_vlan_ids = set()
            for value in rule.get("match_vlan_ids") or []:
                expanded_vlan_ids.update(
                    int(vid) for vid in expand_alphanumeric_range(f"[{value}]")
                )
            rule["expanded_vlan_ids"] = expanded_vlan_ids or None
            rules.append(rule)
        configured_groups = {rule["set_vlan_group"] for rule in rules}
        if vlan_group:
            configured_groups.add(vlan_group)
        group_records = []
        if configured_groups:
            group_records = self.bulk_filter(
                nb.ipam.vlan_groups,
                name=sorted(configured_groups),
                fields="id,name,vid_ranges,scope_type,scope_id,scope",
            )
        groups_by_name = {str(group.name): group for group in group_records}
        for name in sorted(configured_groups - groups_by_name.keys()):
            message = f"vlan group '{name}' does not exist in NetBox"
            job.event(message, severity="ERROR")
            log.error(message)
            ret.errors.append(message)
        groups = {group.id: group for group in groups_by_name.values()}
        message = (
            f"validated {len(rules)} VLAN map rule(s) and loaded {len(groups)} group(s)"
        )
        job.event(message)
        log.info(message)

        # Collect all worker results before choosing names, mappings, and memberships.
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
                message = (
                    f"{worker} failed to fetch VLAN data from devices "
                    f"{', '.join(sorted(resources_failed))}"
                )
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
        if not live_by_device:
            message = "no live VLAN data collected"
            job.event(message, severity="ERROR")
            log.error(message)
            ret.errors.append(message)
            ret.failed = True
            return ret

        # Produce one record per device and VID while preserving parser order.
        live_vlans = []
        interface_names_by_device = {}
        for device, records in sorted(live_by_device.items()):
            device_model = str(nb_devices[device].device_type.model)
            interface_names = {}
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
                            live_interface,
                            interface_map,
                            device,
                            device_model,
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
                # Prefer useful text when duplicate records from one device differ.
                if description and not vlan["description"]:
                    vlan["description"] = description
                for field in VLAN_MEMBERSHIP_FIELDS:
                    for name in record[field]:
                        if name not in vlan[field]:
                            vlan[field].append(name)

            for vlan in device_vlans.values():
                mapped_interfaces = []
                for field in VLAN_MEMBERSHIP_FIELDS:
                    for name in vlan[field]:
                        mapped_interfaces.append(interface_names[name])
                mapped = match_vlan_map(
                    rules,
                    vlan["vid"],
                    vlan["name"],
                    device,
                    mapped_interfaces,
                )
                group_name = mapped or vlan_group
                group = groups_by_name.get(group_name)
                if group_name and group is None:
                    continue
                if require_vlan_group and not group_name:
                    message = (
                        f"skipping VLAN {vlan['vid']} from device '{device}': "
                        "no VLAN group mapping found"
                    )
                    job.event(message, severity="ERROR")
                    log.error(message)
                    ret.errors.append(message)
                    continue
                vlan["selected_group_id"] = group.id if group else None
                live_vlans.append(vlan)
            interface_names_by_device[device] = interface_names
        message = (
            f"normalized {len(live_vlans)} live VLAN record(s) from "
            f"{len(live_by_device)} device(s)"
        )
        job.event(message)
        log.info(message)

        # Fetch all same-VID candidates because scope, rather than name, selects identity.
        vids = sorted({vlan["vid"] for vlan in live_vlans})
        candidates = []
        if vids:
            candidates = self.bulk_filter(
                nb.ipam.vlans, vid=vids, fields="id,vid,name,description,site,group"
            )
        candidate_group_ids = {vlan.group.id for vlan in candidates if vlan.group}
        missing_groups = sorted(candidate_group_ids - groups.keys())
        if missing_groups:
            candidate_groups = self.bulk_filter(
                nb.ipam.vlan_groups,
                id=missing_groups,
                fields="id,name,vid_ranges,scope_type,scope_id,scope",
            )
            for group in candidate_groups:
                groups[group.id] = group

        # Resolve VLAN attributes and interface memberships from the same observations.
        scope_payloads = {}
        vlan_live = {}
        vlan_current = {}
        vlan_objects = {}
        name_sources = {}
        description_sources = {}
        interface_targets = {}
        claimed_interfaces = {}
        for resolved in resolve_live_vlans(
            live_vlans, candidates, groups, device_scopes
        ):
            observation, existing = resolved["live"], resolved["vlan"]
            device, vid = observation["device_name"], observation["vid"]
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
            scope_payloads[scope] = resolved["scope_payload"]
            key = (scope, vid)
            if key not in name_sources:
                name_sources[key] = (device, observation["name"])
                description_sources[key] = (device, observation["description"])
                vlan_live.setdefault(scope, {})[vid] = {
                    "name": observation["name"],
                    "description": observation["description"],
                }
                if existing:
                    vlan_objects[key] = existing
                    vlan_current.setdefault(scope, {})[vid] = {
                        "name": str(existing.name).strip(),
                        "description": str(existing.description or "").strip(),
                    }
                    vlan_live[scope][vid]["description"] = apply_description_policy(
                        observation["description"],
                        vlan_current[scope][vid]["description"],
                        preserve_description,
                    )
                else:
                    vlan_current.setdefault(scope, {})
            elif name_sources[key][1] != observation["name"]:
                source_device, source_name = name_sources[key]
                conflict_device, conflict_name = device, observation["name"]
                automatic_name = f"VLAN{vid}".casefold()
                source_is_automatic = source_name.casefold() == automatic_name
                conflict_is_automatic = observation["name"].casefold() == automatic_name
                # Replace an autogenerated source name with a descriptive one.
                if source_is_automatic and not conflict_is_automatic:
                    vlan_live[scope][vid]["name"] = observation["name"]
                    name_sources[key] = (device, observation["name"])
                    conflict_device, conflict_name = source_device, source_name
                    source_device = device
                # Only different descriptive names represent a genuine conflict.
                if not source_is_automatic and not conflict_is_automatic:
                    message = (
                        f"{scope} VLAN {vid} source conflict (name): using VLAN name "
                        f"'{vlan_live[scope][vid]['name']}' from device "
                        f"'{source_device}'; conflicting device '{conflict_device}' "
                        f"reports VLAN name '{conflict_name}'"
                    )
                    if message not in ret.errors:
                        job.event(message, severity="ERROR")
                        log.error(message)
                        ret.errors.append(message)
            source_description = description_sources[key][1]
            # Let the first non-empty device description replace an empty source.
            if observation["description"] and not source_description:
                description_sources[key] = (device, observation["description"])
                netbox_description = (
                    vlan_current.get(scope, {}).get(vid, {}).get("description", "")
                )
                vlan_live[scope][vid]["description"] = apply_description_policy(
                    observation["description"],
                    netbox_description,
                    preserve_description,
                )
            # Empty descriptions are ignored; only differing useful text conflicts.
            elif (
                source_description
                and observation["description"]
                and source_description != observation["description"]
            ):
                source_device = description_sources[key][0]
                message = (
                    f"{scope} VLAN {vid} source conflict (description): using live "
                    f"description from device '{source_device}'; conflicting device "
                    f"'{device}' reports a different description"
                )
                if message not in ret.errors:
                    job.event(message, severity="ERROR")
                    log.error(message)
                    ret.errors.append(message)
            vlan_reference = f"{scope}/{vid}"
            for field in VLAN_MEMBERSHIP_FIELDS:
                for live_interface in observation[field]:
                    interface = interface_names_by_device[device][live_interface]
                    interface_key = (device, interface)
                    owner = claimed_interfaces.setdefault(interface_key, live_interface)
                    if owner != live_interface:
                        continue
                    target = interface_targets.setdefault(
                        interface_key,
                        {"tagged_vlans": set(), "untagged_vlan": None},
                    )
                    if field == "tagged_interfaces":
                        target["tagged_vlans"].add(vlan_reference)
                    else:
                        target["untagged_vlan"] = vlan_reference

        # Keep a descriptive NetBox name when live data only supplies VLAN<VID>.
        for scope, vid in vlan_objects:
            live_name = vlan_live[scope][vid]["name"]
            if live_name.upper() == f"VLAN{vid}".upper():
                vlan_live[scope][vid]["name"] = vlan_current[scope][vid]["name"]

        # NetBox requires VLAN names to be unique within their group or site.
        # Validate proposed creations and renames before sending a bulk write so
        # one conflict does not reject every VLAN in the batch.
        proposed_names = {
            values["name"] for vlans in vlan_live.values() for values in vlans.values()
        }
        name_matches = []
        if proposed_names:
            name_matches = self.bulk_filter(
                nb.ipam.vlans,
                name=sorted(proposed_names),
                fields="id,vid,name,site,group",
            )
        for existing in name_matches:
            if existing.group:
                scope = f"group:{existing.group.name}"
            elif existing.site:
                scope = f"site:{existing.site.name}"
            else:
                scope = "global"
            for vid, values in list(vlan_live.get(scope, {}).items()):
                if values["name"] != str(existing.name):
                    continue
                current = vlan_current.get(scope, {}).get(vid)
                if current and vlan_objects[(scope, vid)].id == existing.id:
                    continue
                action = "update" if current else "create"
                if current:
                    vlan_live[scope][vid] = dict(current)
                else:
                    del vlan_live[scope][vid]
                    vlan_reference = f"{scope}/{vid}"
                    for target in interface_targets.values():
                        target["tagged_vlans"].discard(vlan_reference)
                        if target["untagged_vlan"] == vlan_reference:
                            target["untagged_vlan"] = None
                message = (
                    f"VLAN {vid} name '{values['name']}' overlaps with VLAN "
                    f"{existing.vid} in scope '{scope}'; skipping VLAN {action}"
                )
                job.event(message, severity="ERROR")
                log.error(message)
                ret.errors.append(message)

        message = (
            f"resolved {sum(len(vlans) for vlans in vlan_live.values())} VLAN(s) "
            f"across {len(vlan_live)} NetBox scope(s)"
        )
        job.event(message)
        log.info(message)

        vlan_diff = self.make_diff(vlan_live, vlan_current)
        vlan_preview = {}
        for scope, actions in sorted(vlan_diff.items()):
            updates = {}
            for vid, changes in actions["update"].items():
                updates[str(vid)] = changes
            create_details = {}
            for vid in actions["create"]:
                create_details[str(vid)] = vlan_live[scope][vid]
            vlan_preview[scope] = {
                **actions,
                "update": updates,
                "create_details": create_details,
            }

        # Build interface state only for interfaces referenced by live VLAN data.
        netbox_interfaces = []
        if interface_targets:
            target_devices = sorted({device for device, _ in interface_targets})
            target_names = sorted({name for _, name in interface_targets})
            target_device_ids = [nb_devices[device].id for device in target_devices]
            netbox_interfaces = self.bulk_filter(
                nb.dcim.interfaces,
                device_id=target_device_ids,
                name=target_names,
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
        valid_interface_keys = interface_targets.keys() & interfaces.keys()
        missing_interfaces = interface_targets.keys() - valid_interface_keys
        for device, name in sorted(missing_interfaces):
            message = f"interface '{device}:{name}' not found in NetBox"
            job.event(message, severity="ERROR")
            log.error(message)
            ret.errors.append(message)

        assigned_vlan_ids = set()
        for key in valid_interface_keys:
            interface = interfaces[key]
            assigned_vlan_ids.update(vlan.id for vlan in interface.tagged_vlans)
            if interface.untagged_vlan:
                assigned_vlan_ids.add(interface.untagged_vlan.id)
        membership_vlans = {vlan.id: vlan for vlan in candidates}
        missing_vlan_ids = assigned_vlan_ids - membership_vlans.keys()
        if missing_vlan_ids:
            assigned_vlans = self.bulk_filter(
                nb.ipam.vlans,
                id=sorted(missing_vlan_ids),
                fields="id,vid,site,group",
            )
            for vlan in assigned_vlans:
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

        interface_live = {}
        interface_current = {}
        for device, name in sorted(valid_interface_keys):
            interface = interfaces[(device, name)]
            tagged_references = sorted(
                vlan_reference_by_id[vlan.id] for vlan in interface.tagged_vlans
            )
            untagged_reference = None
            if interface.untagged_vlan:
                untagged_reference = vlan_reference_by_id[interface.untagged_vlan.id]
            current = {
                "mode": interface.mode.value if interface.mode else None,
                "tagged_vlans": tagged_references,
                "untagged_vlan": untagged_reference,
            }
            target = interface_targets[(device, name)]
            tagged_vlans = set(current["tagged_vlans"])
            tagged_vlans.update(target["tagged_vlans"])
            untagged_vlan = current["untagged_vlan"]
            if target["untagged_vlan"] is not None:
                untagged_vlan = target["untagged_vlan"]
            mode = current["mode"]
            if tagged_vlans:
                mode = "tagged"
            elif untagged_vlan:
                mode = "access"
            interface_current.setdefault(device, {})[name] = current
            interface_live.setdefault(device, {})[name] = {
                "mode": mode,
                "tagged_vlans": sorted(tagged_vlans),
                "untagged_vlan": untagged_vlan,
            }

        message = "calculating VLAN and interface diffs"
        job.event(message)
        log.info(message)
        interface_diff = self.make_diff(interface_live, interface_current)
        preview = {"vlans": vlan_preview, "interfaces": interface_diff}
        ret.diff = preview
        ret.result = preview
        create_count = sum(len(actions["create"]) for actions in vlan_diff.values())
        vlan_update_count = sum(
            len(actions["update"]) for actions in vlan_diff.values()
        )
        interface_update_count = sum(
            len(actions["update"]) for actions in interface_diff.values()
        )
        message = (
            f"prepared {create_count} VLAN creation(s), {vlan_update_count} VLAN "
            f"update(s), and {interface_update_count} interface update(s)"
        )
        job.event(message)
        log.info(message)
        if dry_run:
            message = "dry-run requested, returning VLAN sync diff without changes"
            job.event(message)
            log.info(message)
            return ret
        if with_approval and not review_sync_task_result(job, "vlan sync", preview):
            ret.status = "skipped"
            ret.dry_run = True
            ret.messages.append("review declined; changes were not applied")
            return ret

        vlan_result = {}
        for scope, actions in vlan_diff.items():
            vlan_result[scope] = SyncActionSummary(
                in_sync=actions["in_sync"]
            ).model_dump()
        interface_result = {}
        for device, actions in interface_diff.items():
            interface_result[device] = SyncActionSummary(
                in_sync=actions["in_sync"]
            ).model_dump()
        ret.result = SyncVlansResultPayload(
            vlans=vlan_result, interfaces=interface_result
        ).model_dump()

        # Complete all creations before any VLAN updates or interface writes.
        create_items = []
        for scope, actions in sorted(vlan_diff.items()):
            for vid in actions["create"]:
                create_items.append(
                    (
                        (scope, vid),
                        {
                            "vid": vid,
                            "name": vlan_live[scope][vid]["name"],
                            "description": vlan_live[scope][vid]["description"],
                            **scope_payloads[scope],
                        },
                    )
                )
        if create_items:
            total_batches = (len(create_items) + batch_size - 1) // batch_size
            for batch_start in range(0, len(create_items), batch_size):
                batch = create_items[batch_start : batch_start + batch_size]
                batch_number = batch_start // batch_size + 1
                message = f"creating VLAN batch {batch_number}/{total_batches} ({len(batch)} VLAN(s))"
                job.event(message)
                log.info(message)
                try:
                    created = nb.ipam.vlans.create([payload for _, payload in batch])
                except Exception as exc:
                    message = f"failed to create VLAN batch {batch_number}/{total_batches}: {exc}"
                    job.event(message, severity="ERROR")
                    log.error(message)
                    ret.errors.append(message)
                    ret.failed = True
                    return ret
                for (key, _), vlan in zip(batch, created):
                    scope, vid = key
                    vlan_objects[key] = vlan
                    vlan_id_by_reference[f"{scope}/{vid}"] = vlan.id
                    ret.result["vlans"][scope]["created"].append(vid)
            message = f"created {len(create_items)} VLAN(s)"
            job.event(message)
            log.info(message)

        vlan_updates = []
        for scope, actions in sorted(vlan_diff.items()):
            for vid, changes in actions["update"].items():
                values = {}
                for field in ("name", "description"):
                    if field in changes:
                        values[field] = vlan_live[scope][vid][field]
                if values:
                    vlan_updates.append(
                        (
                            (scope, vid),
                            {"id": vlan_objects[(scope, vid)].id, **values},
                        )
                    )
        if vlan_updates:
            total_batches = (len(vlan_updates) + batch_size - 1) // batch_size
            for batch_start in range(0, len(vlan_updates), batch_size):
                batch = vlan_updates[batch_start : batch_start + batch_size]
                batch_number = batch_start // batch_size + 1
                message = f"updating VLAN batch {batch_number}/{total_batches} ({len(batch)} VLAN(s))"
                job.event(message)
                log.info(message)
                try:
                    nb.ipam.vlans.update([payload for _, payload in batch])
                except Exception as exc:
                    message = f"failed to update VLAN batch {batch_number}/{total_batches}: {exc}"
                    job.event(message, severity="ERROR")
                    log.error(message)
                    ret.errors.append(message)
                    ret.failed = True
                    return ret
                for (scope, vid), _ in batch:
                    ret.result["vlans"][scope]["updated"].append(vid)
            message = f"updated {len(vlan_updates)} VLAN object(s)"
            job.event(message)
            log.info(message)

        interface_updates = []
        for device, actions in sorted(interface_diff.items()):
            for name in sorted(actions["update"]):
                desired = interface_live[device][name]
                tagged_vlan_ids = [
                    vlan_id_by_reference[reference]
                    for reference in desired["tagged_vlans"]
                ]
                untagged_vlan_id = None
                if desired["untagged_vlan"]:
                    untagged_vlan_id = vlan_id_by_reference[desired["untagged_vlan"]]
                interface_updates.append(
                    (
                        (device, name),
                        {
                            "id": interfaces[(device, name)].id,
                            "mode": desired["mode"],
                            "tagged_vlans": tagged_vlan_ids,
                            "untagged_vlan": untagged_vlan_id,
                        },
                    )
                )
        if interface_updates:
            total_batches = (len(interface_updates) + batch_size - 1) // batch_size
            for batch_start in range(0, len(interface_updates), batch_size):
                batch = interface_updates[batch_start : batch_start + batch_size]
                batch_number = batch_start // batch_size + 1
                message = f"updating VLAN membership batch {batch_number}/{total_batches} ({len(batch)} interface(s))"
                job.event(message)
                log.info(message)
                try:
                    nb.dcim.interfaces.update([payload for _, payload in batch])
                except Exception as exc:
                    message = f"failed to update VLAN membership batch {batch_number}/{total_batches}: {exc}"
                    job.event(message, severity="ERROR")
                    log.error(message)
                    ret.errors.append(message)
                    ret.failed = True
                    return ret
                for (device, name), _ in batch:
                    ret.result["interfaces"][device]["updated"].append(name)
            message = (
                f"updated VLAN membership on {len(interface_updates)} interface(s)"
            )
            job.event(message)
            log.info(message)
        message = "vlan sync complete"
        job.event(message)
        log.info(message)
        return ret
