import fnmatch
import logging
from collections.abc import Iterable
from typing import Any, Union

import yaml
from pydantic import TypeAdapter

from norfab.core.worker import Job, Task
from norfab.models import Result
from norfab.utils.text import expand_alphanumeric_range

from .netbox_models import (
    InterfaceMapRule,
    NetboxFastApiArgs,
    SyncVlansInput,
    SyncVlansResult,
    VlanMapRule,
)
from .netbox_worker_utilities import (
    apply_description_policy,
    review_sync_task_result,
)

log = logging.getLogger(__name__)


def prepare_vlan_map(
    vlan_map: Union[None, list],
) -> list[dict]:
    """Normalize VLAN map rules and expand their VLAN ID criteria."""
    rules = []
    for rule in vlan_map or []:
        rule = dict(rule)
        rule["expanded_vlan_ids"] = {
            int(vlan_id)
            for vlan_range in rule.get("match_vlan_ids") or []
            for vlan_id in expand_alphanumeric_range(f"[{vlan_range}]")
        } or None
        rules.append(rule)
    return rules


def match_vlan_map(
    rules: list[dict],
    vlan_id: Union[None, int],
    vlan_name: Union[None, str],
    device_name: str,
    interface_name: Union[None, str],
) -> Union[None, str]:
    """Match the first rule; interface criteria require an interface name.

    Missing VLAN names or IDs do not restrict interface-sync lookups, which
    can resolve a VLAN by either name or VID before both values are available.
    """
    for rule in rules:
        if (
            vlan_id is not None
            and rule["expanded_vlan_ids"] is not None
            and vlan_id not in rule["expanded_vlan_ids"]
        ):
            continue
        if interface_name is None and rule.get("match_interface_names"):
            continue
        criteria = (
            (vlan_name, rule.get("vlan_names")),
            (device_name, rule.get("match_device_names")),
            (interface_name, rule.get("match_interface_names")),
        )
        if all(
            value is None
            or not patterns
            or any(fnmatch.fnmatchcase(value, pattern) for pattern in patterns)
            for value, patterns in criteria
        ):
            return rule["set_vlan_group"]
    return None


def load_device_vlan_scopes(devices: Iterable) -> dict[str, dict]:
    """Load direct NetBox scope assignments used to resolve VLANs per device."""
    device_scopes = {}
    for device in devices:
        site = device.site
        rack = device.rack
        location = device.location or (rack.location if rack else None)
        rack_group = rack.group if rack else None

        device_scopes[str(device.name)] = {
            "device_name": str(device.name),
            "site_id": site.id,
            "site_name": str(site.name),
            "region_id": site.region.id if site.region else None,
            "region_name": str(site.region.name) if site.region else None,
            "site_group_id": site.group.id if site.group else None,
            "site_group_name": str(site.group.name) if site.group else None,
            "location_id": location.id if location else None,
            "location_name": str(location.name) if location else None,
            "rack_id": rack.id if rack else None,
            "rack_name": str(rack.name) if rack else None,
            "rack_group_id": rack_group.id if rack_group else None,
            "rack_group_name": str(rack_group.name) if rack_group else None,
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

    # Each supported group scope compares with one direct device value. There
    # is deliberately no traversal through parent regions, groups, or locations.
    scope_fields = {
        "site": ("site_id", "site_name", "site"),
        "region": ("region_id", "region_name", "region"),
        "sitegroup": ("site_group_id", "site_group_name", "site group"),
        "location": ("location_id", "location_name", "location"),
        "rack": ("rack_id", "rack_name", "rack"),
        "rackgroup": ("rack_group_id", "rack_group_name", "rack group"),
    }
    if scope_type not in scope_fields:
        return (
            f"VLAN group '{vlan_group.name}' uses unsupported scope type "
            f"'{scope_type}' for device '{device_name}'"
        )

    id_field, name_field, display_type = scope_fields[scope_type]
    device_scope_id = device_scope[id_field]
    # A missing device value does not match a populated group scope.
    if device_scope_id == vlan_group.scope_id:
        return None

    device_value = device_scope[name_field]
    device_assignment = f"'{device_value}'" if device_value else "no assignment"
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

        # These lists are ordered by preference below: any compatible group,
        # the device's direct site, then a global VLAN.
        group_matches = []
        site_matches = []
        global_matches = []
        if error is None:
            for vlan in candidates_by_vid.get(live_vlan["vid"], []):
                vlan_group_id = vlan.group.id if vlan.group else None
                if selected_group_id and vlan_group_id != selected_group_id:
                    continue

                if vlan_group_id:
                    vlan_group = vlan_groups[vlan_group_id]
                    if (
                        validate_vlan_group_scope(
                            vlan_group, device_scope, live_vlan["vid"]
                        )
                        is None
                    ):
                        group_matches.append(vlan)
                elif vlan.site and vlan.site.id == device_scope["site_id"]:
                    site_matches.append(vlan)
                elif not vlan.site:
                    global_matches.append(vlan)

        # Only the highest non-empty preference level participates. Two VLANs
        # within that level are ambiguous and therefore unsafe to choose.
        matches = group_matches or site_matches or global_matches
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

        results.append(
            {
                "live": live_vlan,
                "vlan": matched_vlan,
                "error": error,
            }
        )
    return results


def resolve_vlan(
    vid: Union[None, int, str],
    nb: Any,
    job: Job,
    ret: Result,
    worker_name: str,
    site_id: Union[None, int] = None,
    vlan_group: Union[None, int, str] = None,
    _lookup_cache: Union[None, dict] = None,
    return_vid: bool = False,
) -> Union[int, None]:
    """Resolve a VLAN name or resolve/create a VLAN VID in NetBox."""
    if vid is None:
        return None
    cache = _lookup_cache if _lookup_cache is not None else {}
    group_id = None
    if vlan_group:
        group_cache_key = ("vlan_group", vlan_group)
        if group_cache_key not in cache:
            group_obj = None
            if isinstance(vlan_group, int) or str(vlan_group).isdigit():
                group_obj = nb.ipam.vlan_groups.get(id=int(vlan_group))
            if group_obj is None:
                group_obj = nb.ipam.vlan_groups.get(name=str(vlan_group))
            if group_obj is None:
                group_obj = nb.ipam.vlan_groups.get(slug=str(vlan_group))
            if group_obj is None:
                msg = f"vlan group '{vlan_group}' does not exist in NetBox"
                job.event(msg, severity="ERROR")
                log.error(f"{worker_name} - {msg}")
                ret.errors.append(msg)
            cache[group_cache_key] = group_obj.id if group_obj else None
        group_id = cache[group_cache_key]
        if group_id is None:
            return None

    by_name = isinstance(vid, str)
    scope = ("group", group_id) if group_id else ("site", site_id)
    cache_key = ("vlan_name" if by_name else "vlan", vid, *scope)
    if cache_key in cache:
        vlan = cache[cache_key]
        if by_name:
            if vlan is None:
                return None
            return int(vlan.vid) if return_vid else vlan.id
        return vlan

    filters = {"name" if by_name else "vid": vid}
    if group_id:
        filters["group_id"] = group_id
    elif site_id:
        filters["site_id"] = site_id
    try:
        candidates = nb.ipam.vlans.filter(**filters)
        if not group_id and not site_id:
            candidates = (
                vlan for vlan in candidates if not vlan.site and not vlan.group
            )
        vlan = next(
            (
                candidate
                for candidate in candidates
                if by_name or int(candidate.vid) == vid
            ),
            None,
        )
    except Exception as exc:
        msg = f"failed to fetch NetBox VLAN using filters '{filters}', error: {exc}"
        log.error(msg)
        job.event(msg, severity="ERROR")
        ret.errors.append(msg)
        return None

    if vlan:
        cache[cache_key] = vlan if by_name else vlan.id
        return int(vlan.vid) if by_name and return_vid else vlan.id
    if by_name:
        cache[cache_key] = None
        msg = f"failed to find VLAN named '{vid}' in NetBox using filters '{filters}'"
        job.event(msg, severity="ERROR")
        log.error(f"{worker_name} - {msg}")
        ret.errors.append(msg)
        return None

    payload = {"vid": vid, "name": f"VLAN_{vid}", "description": f"VLAN_{vid}"}
    if group_id:
        payload["group"] = group_id
    elif site_id:
        payload["site"] = site_id

    try:
        new_vlan = nb.ipam.vlans.create(**payload)
        msg = f"created VLAN '{vid}' in NetBox"
        if group_id:
            msg += f" in VLAN group '{vlan_group}'"
        elif site_id:
            msg += f" for site '{new_vlan.site.name}'"
        job.event(msg)
        log.info(f"{worker_name} - {msg}")
        cache[cache_key] = new_vlan.id
        return new_vlan.id
    except Exception as exc:
        msg = f"failed to create VLAN '{vid}' in NetBox: {exc}"
        job.event(msg, severity="ERROR")
        log.error(f"{worker_name} - {msg}")
        ret.errors.append(msg)
        cache[cache_key] = None
        return None


VLAN_MEMBERSHIP_FIELDS = ("tagged_interfaces", "untagged_interfaces")


def vlan_interface_updates(
    diff: dict,
    live: dict,
    interfaces: dict,
    objects: dict,
) -> list[dict]:
    """Translate the VLAN diff to interface payloads, retaining pending VLAN keys.

    Process all removals before additions so a native VLAN replacement does
    not depend on scope or VID ordering. Existing unmanaged tagged assignments
    stay in the payload. A missing VLAN ID is filled after bulk creation.
    """
    updates = {}
    changes = []
    for scope, actions in diff.items():
        for vid in actions["create"] + list(actions["update"]):
            key = (scope, vid)
            target = objects[key].id if key in objects else key
            for field in VLAN_MEMBERSHIP_FIELDS:
                change = actions["update"].get(vid, {}).get(field)
                if vid in actions["create"]:
                    change = {"old_value": [], "new_value": live[scope][vid][field]}
                if not change:
                    continue
                old, new = set(change["old_value"]), set(change["new_value"])
                for reference in old ^ new:
                    if reference not in updates:
                        interface = interfaces[reference]
                        updates[reference] = {
                            "id": interface.id,
                            "tagged_vlans": {
                                vlan.id for vlan in interface.tagged_vlans
                            },
                            "untagged_vlan": (
                                interface.untagged_vlan.id
                                if interface.untagged_vlan
                                else None
                            ),
                        }
                changes.append((field, target, old - new, new - old))
    for field, target, removals, _ in changes:
        for reference in removals:
            if field == "tagged_interfaces":
                updates[reference]["tagged_vlans"].discard(target)
            elif updates[reference]["untagged_vlan"] == target:
                updates[reference]["untagged_vlan"] = None
    for field, target, _, additions in changes:
        for reference in additions:
            if field == "tagged_interfaces":
                updates[reference]["tagged_vlans"].add(target)
            else:
                updates[reference]["untagged_vlan"] = target
    for payload in updates.values():
        if payload["tagged_vlans"]:
            payload["mode"] = "tagged"
        elif payload["untagged_vlan"] is not None:
            payload["mode"] = "access"
    return [updates[reference] for reference in sorted(updates)]


class NetboxVlansTasks:
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
            Result: Scope-keyed VLAN synchronization actions.
        """
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:sync_vlans",
            result={},
            resources=[instance],
            dry_run=dry_run,
            diff={},
        )

        job.event(f"starting VLAN sync using NetBox instance '{instance}'")
        nb = self._get_pynetbox(instance, branch=branch, job=job)
        devices = sorted(
            set(devices or [])
            | set(self.get_nornir_hosts(kwargs, timeout) if kwargs else [])
        )
        if not devices:
            job.event("no devices specified", severity="ERROR")
            log.error(f"{self.name} - Sync VLANs: no devices specified")
            ret.errors.append("no devices specified")
            ret.failed = True
            return ret
        nb_devices = {
            str(device.name): device
            for device in self.bulk_filter(
                nb.dcim.devices,
                name=devices,
                fields="id,name,site,location,rack,device_type",
            )
        }
        for device in devices:
            if device not in nb_devices:
                message = f"device '{device}' not found in NetBox"
                job.event(message, severity="ERROR")
                log.error(f"{self.name} - Sync VLANs: {message}")
                ret.errors.append(message)
        if not nb_devices:
            ret.failed = True
            return ret
        device_scopes = load_device_vlan_scopes(nb_devices.values())
        selected_vids = {
            int(vid)
            for value in filter_by_vlan_ids or []
            for vid in expand_alphanumeric_range(f"[{value}]")
        }
        if self.is_url(vlan_map):
            vlan_map = TypeAdapter(list[VlanMapRule]).validate_python(
                yaml.safe_load(self.fetch_file(vlan_map, raise_on_fail=True))
            )
        if self.is_url(interface_map):
            interface_map = TypeAdapter(list[InterfaceMapRule]).validate_python(
                yaml.safe_load(self.fetch_file(interface_map, raise_on_fail=True))
            )
        interface_map = [
            rule.model_dump() if hasattr(rule, "model_dump") else dict(rule)
            for rule in interface_map or []
        ]
        rules = prepare_vlan_map(vlan_map)
        group_names = {rule["set_vlan_group"] for rule in rules}
        if vlan_group:
            group_names.add(vlan_group)
        groups_by_name = {
            name: nb.ipam.vlan_groups.get(name=name) for name in sorted(group_names)
        }
        groups = {group.id: group for group in groups_by_name.values() if group}

        # Collect complete device records before mapping individual memberships.
        job.event(f"collecting live VLANs from {len(nb_devices)} device(s)")
        parsed = self.client.run_job(
            "nornir",
            "parse_ttp",
            workers="all",
            timeout=timeout,
            kwargs={"get": "vlans", "FL": sorted(nb_devices)},
        )
        live_by_device = {}
        for worker, response in parsed.items():
            if response.get("failed"):
                message = f"worker '{worker}' failed to collect live VLAN data"
                job.event(message, severity="ERROR")
                log.error(f"{self.name} - Sync VLANs: {message}")
                ret.errors.append(message)
                continue
            if response.get("resources_failed"):
                message = (
                    f"{worker} failed to fetch VLAN data from devices "
                    f"{', '.join(sorted(response['resources_failed']))}"
                )
                job.event(message, severity="ERROR")
                log.error(f"{self.name} - Sync VLANs: {message}")
                ret.errors.append(message)
            for device, records in response["result"].items():
                live_by_device.setdefault(device, []).extend(records)
        if not live_by_device:
            ret.failed = True
            return ret

        observations = []
        for device, records in sorted(live_by_device.items()):
            interface_rules = [
                rule
                for rule in interface_map
                if fnmatch.fnmatchcase(device, rule["device_name"])
                and fnmatch.fnmatchcase(
                    str(nb_devices[device].device_type.model), rule["device_type"]
                )
            ]
            for vlan in records:
                if selected_vids and vlan["vid"] not in selected_vids:
                    continue
                memberships = [
                    (field, name)
                    for field in VLAN_MEMBERSHIP_FIELDS
                    for name in sorted(set(vlan[field]))
                ]
                for field, interface in memberships or [(None, None)]:
                    for rule in interface_rules:
                        if interface and rule["match"] in interface:
                            interface = interface.replace(
                                rule["match"], rule["replace"]
                            )
                            break
                    mapped = match_vlan_map(
                        rules, vlan["vid"], vlan["name"].strip(), device, interface
                    )
                    group_name = mapped or vlan_group
                    group = groups_by_name.get(group_name)
                    if (group_name and group is None) or (
                        require_vlan_group and not group_name
                    ):
                        reason = (
                            f"VLAN group '{group_name}' does not exist in NetBox"
                            if group_name
                            else "no VLAN group mapping found"
                        )
                        message = (
                            f"VLAN {vlan['vid']} from device '{device}' skipped: "
                            f"{reason}"
                        )
                        job.event(f"skipping {message}", severity="ERROR")
                        log.error(f"{self.name} - Sync VLANs: {message}")
                        ret.errors.append(message)
                        continue
                    observations.append(
                        {
                            "device_name": device,
                            "vid": vlan["vid"],
                            "name": vlan["name"].strip(),
                            "description": (vlan["description"] or "").strip(),
                            "selected_group_id": group.id if group else None,
                            "group_source": "vlan_map" if mapped else "vlan_group",
                            "field": field,
                            "interface": interface,
                        }
                    )

        vids = sorted({vlan["vid"] for vlan in observations})
        candidates = (
            self.bulk_filter(
                nb.ipam.vlans, vid=vids, fields="id,vid,name,description,site,group"
            )
            if vids
            else []
        )
        missing_groups = sorted(
            {vlan.group.id for vlan in candidates if vlan.group} - groups.keys()
        )
        if missing_groups:
            groups.update(
                {
                    group.id: group
                    for group in self.bulk_filter(
                        nb.ipam.vlan_groups,
                        id=missing_groups,
                        fields="id,name,vid_ranges,scope_type,scope_id,scope",
                    )
                }
            )

        # Both snapshots have scope -> VID -> scalar attributes and flat lists.
        scope_payloads = {
            f"site:{scope['site_name']}": {"site": scope["site_id"]}
            for scope in device_scopes.values()
        }
        scope_payloads.update(
            {
                f"group:{group.name}": {"group": group.id}
                for group in groups_by_name.values()
                if group
            }
        )
        live = {scope: {} for scope in scope_payloads}
        current = {scope: {} for scope in scope_payloads}
        objects, sources, managed_devices = {}, {}, {}
        for resolved in resolve_live_vlans(
            observations, candidates, groups, device_scopes
        ):
            observation, existing = resolved["live"], resolved["vlan"]
            device, vid = observation["device_name"], observation["vid"]
            if resolved["error"]:
                message = (
                    f"vlan {vid} from device '{device}' skipped: {resolved['error']}"
                )
                if observation["selected_group_id"]:
                    mapping_fix = (
                        "fix the VLAN map mapping"
                        if observation["group_source"] == "vlan_map"
                        else "fix the vlan_group setting"
                    )
                    message += (
                        f"; fix the VLAN group scope or VID ranges, or {mapping_fix}"
                    )
                job.event(message, severity="ERROR")
                log.error(f"{self.name} - Sync VLANs: {message}")
                ret.errors.append(message)
                continue
            if existing:
                if existing.group:
                    scope = f"group:{existing.group.name}"
                    payload = {"group": existing.group.id}
                elif existing.site:
                    scope = f"site:{existing.site.name}"
                    payload = {"site": existing.site.id}
                else:
                    scope, payload = "global", {}
            elif observation["selected_group_id"]:
                group = groups[observation["selected_group_id"]]
                scope, payload = f"group:{group.name}", {"group": group.id}
            else:
                device_scope = device_scopes[device]
                scope, payload = f"site:{device_scope['site_name']}", {
                    "site": device_scope["site_id"]
                }
            scope_payloads[scope] = payload
            key = (scope, vid)
            values = (observation["name"], observation["description"])
            if key not in sources:
                sources[key] = (device, values)
                live.setdefault(scope, {})[vid] = {
                    "name": values[0],
                    "description": values[1],
                    "tagged_interfaces": [],
                    "untagged_interfaces": [],
                }
                if existing:
                    objects[key] = existing
                    current.setdefault(scope, {})[vid] = {
                        "name": str(existing.name).strip(),
                        "description": str(existing.description or "").strip(),
                        "tagged_interfaces": [],
                        "untagged_interfaces": [],
                    }
                    live[scope][vid]["description"] = apply_description_policy(
                        observation["description"],
                        current[scope][vid]["description"],
                        preserve_description,
                    )
                else:
                    current.setdefault(scope, {})
            elif sources[key][1] != values:
                message = (
                    f"{scope} VLAN {vid} source conflict: using VLAN name '{sources[key][1][0]}' "
                    f"from device '{sources[key][0]}'; conflicting device '{device}' "
                    f"reports VLAN name '{observation['name']}'"
                )
                if message not in ret.errors:
                    job.event(message, severity="ERROR")
                    log.error(f"{self.name} - Sync VLANs: {message}")
                    ret.errors.append(message)
            managed_devices.setdefault(key, set()).add(device)
            if observation["field"]:
                live[scope][vid][observation["field"]].append(
                    f"{device}:{observation['interface']}"
                )

        interfaces = {
            f"{interface.device.name}:{interface.name}": interface
            for interface in self.bulk_filter(
                nb.dcim.interfaces,
                device_id=[nb_devices[device].id for device in sorted(live_by_device)],
                fields="id,name,device,tagged_vlans,untagged_vlan",
            )
        }
        object_keys = {vlan.id: key for key, vlan in objects.items()}
        for reference, interface in interfaces.items():
            memberships = {
                "tagged_interfaces": interface.tagged_vlans,
                "untagged_interfaces": (
                    [interface.untagged_vlan] if interface.untagged_vlan else []
                ),
            }
            for field, vlans in memberships.items():
                for vlan in vlans:
                    key = object_keys.get(vlan.id)
                    if (
                        key is None
                        or str(interface.device.name) not in managed_devices[key]
                    ):
                        continue
                    scope, vid = key
                    current[scope][vid][field].append(reference)

        # Show replaced native VLANs even when they fall outside the VID filter.
        native_targets = {}
        referenced_interfaces = set()
        membership_error = False
        for scope, vlans in live.items():
            for vid, vlan in vlans.items():
                for field in VLAN_MEMBERSHIP_FIELDS:
                    vlan[field] = sorted(set(vlan[field]))
                    referenced_interfaces.update(vlan[field])
                for reference in vlan["untagged_interfaces"]:
                    if reference in native_targets and native_targets[reference] != (
                        scope,
                        vid,
                    ):
                        message = (
                            f"interface '{reference}' has multiple live untagged VLANs"
                        )
                        job.event(message, severity="ERROR")
                        log.error(f"{self.name} - Sync VLANs: {message}")
                        ret.errors.append(message)
                        membership_error = True
                    native_targets[reference] = (scope, vid)
        for reference in sorted(referenced_interfaces - interfaces.keys()):
            message = f"interface '{reference}' not found in NetBox"
            job.event(message, severity="ERROR")
            log.error(f"{self.name} - Sync VLANs: {message}")
            ret.errors.append(message)
            membership_error = True
        if membership_error:
            ret.failed = True
            return ret
        replaced_ids = {
            interfaces[reference].untagged_vlan.id
            for reference in native_targets
            if interfaces[reference].untagged_vlan
            and interfaces[reference].untagged_vlan.id not in object_keys
        }
        replaced_vlans = (
            self.bulk_filter(
                nb.ipam.vlans,
                id=sorted(replaced_ids),
                fields="id,vid,name,description,site,group",
            )
            if replaced_ids
            else []
        )
        for vlan in replaced_vlans:
            if vlan.group:
                scope, payload = f"group:{vlan.group.name}", {"group": vlan.group.id}
            elif vlan.site:
                scope, payload = f"site:{vlan.site.name}", {"site": vlan.site.id}
            else:
                scope, payload = "global", {}
            key = (scope, vlan.vid)
            scope_payloads[scope] = payload
            objects[key] = vlan
            object_keys[vlan.id] = key
            current.setdefault(scope, {})[vlan.vid] = {
                "name": str(vlan.name).strip(),
                "description": str(vlan.description or "").strip(),
                "tagged_interfaces": [],
                "untagged_interfaces": [],
            }
            live.setdefault(scope, {})[vlan.vid] = {
                "name": str(vlan.name).strip(),
                "description": str(vlan.description or "").strip(),
                "tagged_interfaces": [],
                "untagged_interfaces": [],
            }
        for reference, target in native_targets.items():
            previous = interfaces[reference].untagged_vlan
            if not previous:
                continue
            old_key = object_keys[previous.id]
            if old_key != target:
                scope, vid = old_key
                current[scope][vid]["untagged_interfaces"].append(reference)
                if reference in live[scope][vid]["untagged_interfaces"]:
                    live[scope][vid]["untagged_interfaces"].remove(reference)
        for snapshot in (live, current):
            for vlans in snapshot.values():
                for vlan in vlans.values():
                    for field in VLAN_MEMBERSHIP_FIELDS:
                        vlan[field] = sorted(set(vlan[field]))

        job.event("calculating VLAN attributes and interface membership diff")
        diff = self.make_diff(live, current)
        # Enrich create actions directly from the same live snapshot for review.
        preview = {
            scope: {
                **actions,
                "update": {
                    str(vid): changes for vid, changes in actions["update"].items()
                },
                "create_details": {
                    str(vid): live[scope][vid] for vid in actions["create"]
                },
            }
            for scope, actions in sorted(diff.items())
        }
        ret.diff = preview
        ret.result = preview
        interface_updates = vlan_interface_updates(diff, live, interfaces, objects)
        if dry_run:
            job.event("dry-run requested, returning VLAN sync diff without changes")
            return ret
        if with_approval and not review_sync_task_result(job, "vlan sync", preview):
            ret.status = "skipped"
            ret.dry_run = True
            ret.messages.append("review declined; changes were not applied")
            return ret

        ret.result = {
            scope: {
                "created": [],
                "updated": [],
                "deleted": [],
                "in_sync": actions["in_sync"],
            }
            for scope, actions in diff.items()
        }
        # Complete all creations before any VLAN updates or interface writes.
        for scope, actions in sorted(diff.items()):
            if not actions["create"]:
                continue
            payloads = [
                {
                    "vid": vid,
                    "name": live[scope][vid]["name"],
                    "description": live[scope][vid]["description"],
                    **scope_payloads[scope],
                }
                for vid in actions["create"]
            ]
            try:
                created = nb.ipam.vlans.create(payloads)
                for vlan in created:
                    objects[(scope, vlan.vid)] = vlan
                    ret.result[scope]["created"].append(vlan.vid)
            except Exception as exc:
                message = f"failed to create VLANs in {scope}: {exc}"
                job.event(message, severity="ERROR")
                log.error(f"{self.name} - Sync VLANs: {message}")
                ret.errors.append(message)
                ret.failed = True
                return ret
            job.event(f"{scope}: created {len(created)} VLAN(s)")
        try:
            for scope, actions in sorted(diff.items()):
                payloads = []
                for vid, changes in actions["update"].items():
                    values = {
                        field: live[scope][vid][field]
                        for field in ("name", "description")
                        if field in changes
                    }
                    if values:
                        payloads.append({"id": objects[(scope, vid)].id, **values})
                if payloads:
                    nb.ipam.vlans.update(payloads)
            # Resolve pending scoped references using IDs returned by creation.
            for payload in interface_updates:
                payload["tagged_vlans"] = sorted(
                    objects[value].id if isinstance(value, tuple) else value
                    for value in payload["tagged_vlans"]
                )
                if isinstance(payload["untagged_vlan"], tuple):
                    payload["untagged_vlan"] = objects[payload["untagged_vlan"]].id
            if interface_updates:
                nb.dcim.interfaces.update(interface_updates)
        except Exception as exc:
            message = f"failed to apply VLAN sync changes: {exc}"
            job.event(message, severity="ERROR")
            log.error(f"{self.name} - Sync VLANs: {message}")
            ret.errors.append(message)
            ret.failed = True
            return ret
        for scope, actions in diff.items():
            ret.result[scope]["updated"] = sorted(actions["update"])
        job.event("vlan sync complete")
        log.info(f"{self.name} - Sync VLANs complete")
        return ret
