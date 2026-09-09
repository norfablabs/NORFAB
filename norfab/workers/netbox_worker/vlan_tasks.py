import logging
from typing import Any, Union

import yaml
from pydantic import TypeAdapter

from norfab.core.worker import Job, Task
from norfab.models import Result
from norfab.utils.text import expand_alphanumeric_range

from .netbox_models import (
    NetboxFastApiArgs,
    SyncVlansInput,
    SyncVlansResult,
    VlanMapRule,
)
from .netbox_worker_utilities import (
    apply_description_policy,
    build_vlan_payload,
    load_device_vlan_scopes,
    match_vlan_map,
    prepare_vlan_map,
    resolve_live_vlans,
    review_sync_task_result,
)

log = logging.getLogger(__name__)


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
        vlan_group: Union[None, str] = None,
        vlan_map: Union[None, str, list] = None,
        require_vlan_group: bool = False,
        filter_by_vlan_ids: Union[None, list[str]] = None,
        preserve_description: Union[None, bool] = None,
        **kwargs: Any,
    ) -> Result:
        """Synchronize live VLAN names and descriptions with NetBox.

        VLANs are mapped by the first matching ``vlan_map`` rule. Rule criteria
        match VLAN IDs, VLAN names, and device names; populated criteria are
        combined with AND. Interface name criteria are ignored because VLAN
        records have no interface context. VLANs which match no rule use
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
        devices = list(devices or [])
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:sync_vlans",
            result={},
            resources=[instance],
            dry_run=dry_run,
            diff={},
        )

        job.event(
            f"starting VLAN sync using NetBox instance '{instance}' for "
            f"{len(devices)} explicit device(s)"
        )
        log.info(f"{self.name} - Sync VLANs: instance '{instance}', dry_run={dry_run}")
        nb = self._get_pynetbox(instance, branch=branch, job=job)

        # Resolve and validate the complete device set.
        if kwargs:
            job.event("resolving devices from Nornir filters")
            devices.extend(self.get_nornir_hosts(kwargs, timeout))
        devices = sorted(set(devices))
        if not devices:
            msg = "no devices specified"
            job.event(msg, severity="ERROR")
            log.error(f"{self.name} - Sync VLANs: {msg}")
            ret.errors.append(msg)
            ret.failed = True
            return ret
        job.event(f"selected {len(devices)} device(s)")

        nb_devices = {
            device.name: device
            for device in self.bulk_filter(
                nb.dcim.devices,
                name=devices,
                fields="id,name,site,location,rack",
            )
        }
        missing_devices = [name for name in devices if name not in nb_devices]
        for device_name in missing_devices:
            msg = f"device '{device_name}' not found in NetBox"
            job.event(msg, severity="ERROR")
            log.error(f"{self.name} - Sync VLANs: {msg}")
            ret.errors.append(msg)
        devices = [name for name in devices if name in nb_devices]
        if not devices:
            ret.failed = True
            return ret
        job.event(f"validated {len(devices)} NetBox device(s)")
        device_scopes = load_device_vlan_scopes(nb_devices.values())

        # Expand filters and resolve every VLAN group before collecting live data.
        expanded_filter = {
            int(vlan_id)
            for vlan_range in filter_by_vlan_ids or []
            for vlan_id in expand_alphanumeric_range(f"[{vlan_range}]")
        }
        if self.is_url(vlan_map):
            vlan_map = TypeAdapter(list[VlanMapRule]).validate_python(
                yaml.safe_load(self.fetch_file(vlan_map, raise_on_fail=True))
            )
        rules = prepare_vlan_map(vlan_map)
        job.event(
            f"prepared {len(rules)} VLAN map rule(s) and "
            f"{len(expanded_filter)} VLAN filter ID(s)"
        )

        vlan_groups = {}
        group_names = [rule["set_vlan_group"] for rule in rules]
        if vlan_group:
            group_names.append(vlan_group)
        for group_name in dict.fromkeys(group_names):
            group = nb.ipam.vlan_groups.get(name=group_name)
            vlan_groups[group_name] = {
                "group": group,
                "skip": group is None,
                "skip_reason": (
                    f"VLAN group '{group_name}' does not exist in NetBox"
                    if group is None
                    else None
                ),
            }
        if vlan_groups:
            resolved_groups = sum(
                not group_data["skip"] for group_data in vlan_groups.values()
            )
            job.event(f"resolved {resolved_groups} NetBox VLAN group(s)")

        # Collect VLANs once from all Nornir workers and normalize each response.
        job.event(f"collecting live VLANs from {len(devices)} device(s)")
        log.info(f"{self.name} - Sync VLANs: collecting from {len(devices)} device(s)")
        parse_data = self.client.run_job(
            "nornir",
            "parse_ttp",
            kwargs={"get": "vlans", "FL": devices},
            workers="all",
            timeout=timeout,
        )
        job.event(f"received VLAN data from {len(parse_data)} Nornir worker(s)")
        live_by_device = {}
        failed_devices = set()
        for worker_name, worker_data in parse_data.items():
            if worker_data.get("failed"):
                msg = f"worker '{worker_name}' failed to collect live VLAN data"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - Sync VLANs: {msg}")
                ret.errors.append(msg)
                continue
            resources_failed = worker_data.get("resources_failed") or []
            if resources_failed:
                failed_devices.update(resources_failed)
                msg = (
                    f"{worker_name} failed to fetch VLAN data from devices "
                    f"{', '.join(sorted(resources_failed))}"
                )
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - Sync VLANs: {msg}")
                ret.errors.append(msg)
            worker_result = worker_data.get("result")
            if not isinstance(worker_result, dict):
                msg = f"worker '{worker_name}' returned a malformed Nornir VLAN result"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - Sync VLANs: {msg}")
                ret.errors.append(msg)
                continue
            for device_name, records in worker_result.items():
                if device_name not in nb_devices:
                    continue
                device_vlans = live_by_device.setdefault(device_name, [])
                if not isinstance(records, list):
                    msg = f"device '{device_name}' VLAN parsing result is not a list"
                    job.event(msg, severity="ERROR")
                    log.error(f"{self.name} - Sync VLANs: {msg}")
                    ret.errors.append(msg)
                    continue
                for record in records:
                    if expanded_filter and record["vid"] not in expanded_filter:
                        continue
                    device_vlans.append(
                        {
                            "vid": record["vid"],
                            "name": record["name"].strip(),
                            "description": (record.get("description") or "").strip(),
                        }
                    )

        for device_name in devices:
            if device_name not in live_by_device and device_name not in failed_devices:
                msg = f"device '{device_name}' is missing a live VLAN result"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - Sync VLANs: {msg}")
                ret.errors.append(msg)
        if not live_by_device:
            log.error(f"{self.name} - Sync VLANs: no usable live VLAN data")
            ret.failed = True
            return ret
        parsed_count = sum(len(records) for records in live_by_device.values())
        job.event(
            f"parsed {parsed_count} live VLAN record(s) from "
            f"{len(live_by_device)} device(s)"
        )

        # Select the configured group for each live VLAN before resolving all
        # same-VID NetBox candidates in one batch.
        live_vlans = []
        for device_name in sorted(live_by_device):
            for vlan in live_by_device[device_name]:
                mapped_group_name = match_vlan_map(
                    rules,
                    vlan_id=vlan["vid"],
                    vlan_name=vlan["name"],
                    device_name=device_name,
                    interface_name=None,
                )
                selected_group_name = mapped_group_name or vlan_group
                if selected_group_name:
                    group_data = vlan_groups[selected_group_name]
                    if group_data["skip"]:
                        msg = (
                            f"VLAN {vlan['vid']} from device '{device_name}' skipped: "
                            f"{group_data['skip_reason']}"
                        )
                        job.event(
                            f"skipping VLAN {vlan['vid']} from device "
                            f"'{device_name}': {group_data['skip_reason']}",
                            severity="ERROR",
                        )
                        log.error(f"{self.name} - Sync VLANs: {msg}")
                        ret.errors.append(msg)
                        continue
                elif require_vlan_group:
                    msg = (
                        f"VLAN {vlan['vid']} from device '{device_name}' skipped: "
                        "no VLAN group mapping found"
                    )
                    job.event(
                        f"skipping VLAN {vlan['vid']} from device "
                        f"'{device_name}': no VLAN group mapping found",
                        severity="ERROR",
                    )
                    log.error(f"{self.name} - Sync VLANs: {msg}")
                    ret.errors.append(msg)
                    continue
                live_vlans.append(
                    {
                        "device_name": device_name,
                        "vid": vlan["vid"],
                        "name": vlan["name"],
                        "description": vlan["description"],
                        "selected_group_id": (
                            vlan_groups[selected_group_name]["group"].id
                            if selected_group_name
                            else None
                        ),
                        "group_source": (
                            "vlan_map" if mapped_group_name else "vlan_group"
                        ),
                    }
                )

        # Fetch every same-VID candidate once; site/group compatibility is
        # evaluated locally by the shared resolver.
        live_vids = sorted({vlan["vid"] for vlan in live_vlans})
        netbox_vlans = (
            self.bulk_filter(
                nb.ipam.vlans,
                vid=live_vids,
                fields="id,vid,name,description,site,group",
            )
            if live_vids
            else []
        )
        configured_group_ids = {
            data["group"].id for data in vlan_groups.values() if not data["skip"]
        }
        # Configured groups are already loaded. Load any group referenced by an
        # additional same-VID candidate so its scope can also be validated.
        group_objects = {
            data["group"].id: data["group"]
            for data in vlan_groups.values()
            if not data["skip"]
        }
        candidate_group_ids = {
            candidate.group.id
            for candidate in netbox_vlans
            if getattr(candidate, "group", None)
        }
        missing_group_ids = sorted(candidate_group_ids - set(group_objects))
        if missing_group_ids:
            group_objects.update(
                {
                    group.id: group
                    for group in self.bulk_filter(
                        nb.ipam.vlan_groups,
                        id=missing_group_ids,
                        fields="id,name,vid_ranges,scope_type,scope_id,scope",
                    )
                }
            )
        resolved_live_vlans = resolve_live_vlans(
            live_vlans=live_vlans,
            netbox_vlans=netbox_vlans,
            vlan_groups=group_objects,
            device_scopes=device_scopes,
        )

        scope_metadata = {
            f"site:{scope['site_name']}": {
                "type": "site",
                "id": scope["site_id"],
                "name": scope["site_name"],
            }
            for scope in device_scopes.values()
        }
        scope_metadata.update(
            {
                f"group:{group.name}": {
                    "type": "group",
                    "id": group_id,
                    "name": str(group.name),
                }
                for group_id, group in group_objects.items()
                if group_id in configured_group_ids
            }
        )
        live_by_scope = {scope: {} for scope in scope_metadata}
        matched_by_scope = {}
        for resolved in resolved_live_vlans:
            live_vlan = resolved["live"]
            device_name = live_vlan["device_name"]
            if resolved["error"]:
                msg = (
                    f"vlan {live_vlan['vid']} from device '{device_name}' skipped: "
                    f"{resolved['error']}"
                )
                if live_vlan["selected_group_id"]:
                    mapping_fix = (
                        "fix the VLAN map mapping"
                        if live_vlan["group_source"] == "vlan_map"
                        else "fix the vlan_group setting"
                    )
                    msg += f"; fix the VLAN group scope or VID ranges, or {mapping_fix}"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - Sync VLANs: {msg}")
                ret.errors.append(msg)
                continue

            netbox_vlan = resolved["vlan"]
            # An existing match determines its output/write scope. With no
            # match, creation uses the explicitly selected group or device site.
            group_id = (
                netbox_vlan.group.id
                if netbox_vlan and getattr(netbox_vlan, "group", None)
                else live_vlan["selected_group_id"]
            )
            site_id = (
                netbox_vlan.site.id
                if netbox_vlan and getattr(netbox_vlan, "site", None)
                else device_scopes[device_name]["site_id"]
            )
            if group_id:
                group = group_objects[group_id]
                scope = f"group:{group.name}"
                scope_metadata[scope] = {
                    "type": "group",
                    "id": group_id,
                    "name": str(group.name),
                }
            elif netbox_vlan and not getattr(netbox_vlan, "site", None):
                # Global is an existing-VLAN fallback, not the default scope for
                # creating a missing VLAN.
                scope = "global"
                scope_metadata[scope] = {"type": "global", "id": None, "name": "global"}
            else:
                site_name = device_scopes[device_name]["site_name"]
                scope = f"site:{site_name}"
                scope_metadata[scope] = {
                    "type": "site",
                    "id": site_id,
                    "name": site_name,
                }
            live_by_scope.setdefault(scope, {}).setdefault(live_vlan["vid"], []).append(
                {"device": device_name, **live_vlan}
            )
            if netbox_vlan:
                matched_by_scope.setdefault(scope, {})[live_vlan["vid"]] = netbox_vlan

        job.event(f"resolved {len(scope_metadata)} VLAN scope(s)")

        # Collapse identical live records. The first device in sorted order is
        # authoritative; conflicting values from later devices are reported.
        normalized_live = {scope: {} for scope in scope_metadata}
        source_conflict_count = 0
        for scope in sorted(live_by_scope):
            for vid in sorted(live_by_scope[scope]):
                records = live_by_scope[scope][vid]
                desired = records[0]
                desired_values = (desired["name"], desired["description"])
                for conflicting in records[1:]:
                    if (
                        conflicting["name"],
                        conflicting["description"],
                    ) == desired_values:
                        continue
                    msg = (
                        f"{scope} VLAN {vid} source conflict: using VLAN name "
                        f"'{desired['name']}' from device '{desired['device']}'; "
                        f"conflicting device '{conflicting['device']}' reports "
                        f"VLAN name '{conflicting['name']}'"
                    )
                    job.event(msg, severity="ERROR")
                    log.error(f"{self.name} - Sync VLANs: {msg}")
                    ret.errors.append(msg)
                    source_conflict_count += 1
                normalized_live[scope][vid] = {
                    "vid": desired["vid"],
                    "name": desired["name"],
                    "description": desired["description"],
                }

        # Normalize only the device-compatible NetBox VLAN selected for each VID.
        normalized_netbox = {scope: {} for scope in scope_metadata}
        netbox_objects = {scope: {} for scope in scope_metadata}
        for scope, matched_vlans in matched_by_scope.items():
            for vid, vlan in matched_vlans.items():
                vid = vlan.vid
                normalized_netbox[scope][vid] = {
                    "vid": vid,
                    "name": str(vlan.name).strip(),
                    "description": str(
                        getattr(vlan, "description", None) or ""
                    ).strip(),
                }
                if vid in normalized_live[scope]:
                    normalized_live[scope][vid]["description"] = (
                        apply_description_policy(
                            normalized_live[scope][vid]["description"],
                            normalized_netbox[scope][vid]["description"],
                            preserve_description,
                        )
                    )
                netbox_objects[scope][vid] = vlan
        job.event(
            f"matched {sum(len(vlans) for vlans in matched_by_scope.values())} "
            "device-compatible NetBox VLAN record(s)"
        )

        # Compare the normalized VID-keyed structures.
        job.event("calculating VLAN sync diff")
        internal_diff = self.make_diff(normalized_live, normalized_netbox)

        full_diff = {
            scope: {
                "create": sorted(actions["create"]),
                "update": {
                    str(vid): actions["update"][vid]
                    for vid in sorted(actions["update"])
                },
                "delete": [],
                "in_sync": sorted(actions["in_sync"]),
            }
            for scope, actions in sorted(internal_diff.items())
        }
        create_count = sum(len(actions["create"]) for actions in full_diff.values())
        update_count = sum(len(actions["update"]) for actions in full_diff.values())
        in_sync_count = sum(len(actions["in_sync"]) for actions in full_diff.values())
        job.event(
            "vlan sync diff complete: "
            f"{create_count} create, {update_count} update, "
            f"{in_sync_count} in sync, "
            f"{source_conflict_count} source conflict(s)"
        )

        if dry_run:
            job.event("dry-run requested, returning VLAN sync diff without changes")
            log.info(f"{self.name} - Sync VLANs: dry-run complete")
            ret.result = full_diff
            ret.dry_run = True
            return ret
        if with_approval:
            job.event("requesting approval for the prepared VLAN sync plan")
        if with_approval and not review_sync_task_result(job, "VLAN sync", full_diff):
            ret.status = "skipped"
            ret.result = full_diff
            ret.dry_run = True
            ret.messages.append("review declined; changes were not applied")
            log.info(f"{self.name} - Sync VLANs: approval declined")
            return ret

        # Apply each scope independently using NetBox bulk operations.
        ret.diff = full_diff
        ret.result = {
            scope: {
                "created": [],
                "updated": [],
                "deleted": [],
                "in_sync": actions["in_sync"],
            }
            for scope, actions in full_diff.items()
        }
        for scope in sorted(internal_diff):
            actions = internal_diff[scope]
            metadata = scope_metadata[scope]
            create_vids = sorted(actions["create"])
            update_vids = sorted(actions["update"])
            job.event(
                f"applying {scope}: {len(create_vids)} create, "
                f"{len(update_vids)} update"
            )

            scope_arg = (
                {f"{metadata['type']}_id": metadata["id"]}
                if metadata["type"] != "global"
                else {}
            )
            create_payloads = [
                build_vlan_payload(
                    **normalized_live[scope][vid],
                    **scope_arg,
                )
                for vid in create_vids
            ]
            if create_payloads:
                nb.ipam.vlans.create(create_payloads)
                ret.result[scope]["created"].extend(create_vids)
                job.event(f"{scope}: created {len(create_payloads)} VLAN(s)")

            update_payloads = []
            for vid in update_vids:
                field_changes = actions["update"][vid]
                desired = normalized_live[scope][vid]
                payload = {"id": netbox_objects[scope][vid].id}
                for field in ("name", "description"):
                    if field in field_changes:
                        payload[field] = desired[field]
                update_payloads.append(payload)
            if update_payloads:
                nb.ipam.vlans.update(update_payloads)
                ret.result[scope]["updated"].extend(update_vids)
                job.event(f"{scope}: updated {len(update_payloads)} VLAN(s)")
            job.event(f"completed VLAN changes for {scope}")

        job.event("vlan sync complete")
        log.info(
            f"{self.name} - Sync VLANs complete: {create_count} created, "
            f"{update_count} updated, {in_sync_count} in sync"
        )
        return ret
