import json
import logging
from typing import Any, Union

from norfab.core.worker import Job, Task
from norfab.models import Result
from norfab.utils.text import expand_alphanumeric_range

from .netbox_models import (
    NetboxFastApiArgs,
    SyncVlansInput,
    SyncVlansResult,
)
from .netbox_worker_utilities import (
    build_vlan_payload,
    find_vlan,
    match_vlan_map,
    prepare_vlan_map,
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
        vlan_map: Union[None, list] = None,
        filter_by_vlan_ids: Union[None, list[str]] = None,
        **kwargs: Any,
    ) -> Result:
        """Synchronize live VLAN names and descriptions with NetBox.

        VLANs are mapped by the first matching ``vlan_map`` rule. Rule criteria
        match VLAN IDs, VLAN names, and device names; populated criteria are
        combined with AND. Interface name criteria are ignored because VLAN
        records have no interface context. VLANs which match no rule use
        ``vlan_group`` when supplied, otherwise they use their device site.

        Args:
            job: NorFab job object.
            instance: NetBox instance name. Uses the default instance when omitted.
            dry_run: Return the calculated diff without writing to NetBox.
            with_approval: Ask for approval before applying the prepared diff.
            timeout: Timeout in seconds for Nornir host resolution and parsing.
            devices: Explicit NetBox and Nornir device names.
            branch: NetBox Branching plugin branch name.
            vlan_group: Group for VLANs not matched by ``vlan_map``.
            vlan_map: Ordered VLAN-to-group mapping rules.
            filter_by_vlan_ids: VLAN IDs or inclusive ranges to reconcile.
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

        def vlan_identity(metadata: dict, vid: int, name: str) -> str:
            if metadata["type"] == "group":
                return f"{vid}:{metadata['name']}"
            return f"{vid}:{name}:{metadata['name']}"

        def normalize_netbox_vlan(vlan: Any) -> dict:
            return {
                "vid": int(vlan.vid),
                "name": str(vlan.name).strip(),
                "description": str(getattr(vlan, "description", None) or "").strip(),
            }

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
                fields="id,name,site",
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

        # Expand filters and resolve every VLAN group before collecting live data.
        expanded_filter = {
            int(vlan_id)
            for vlan_range in filter_by_vlan_ids or []
            for vlan_id in expand_alphanumeric_range(f"[{vlan_range}]")
        }
        rules = prepare_vlan_map(vlan_map)
        job.event(
            f"prepared {len(rules)} VLAN map rule(s) and "
            f"{len(expanded_filter)} VLAN filter ID(s)"
        )

        vlan_groups = {}
        group_names = [rule["vlan_group"] for rule in rules]
        if vlan_group:
            group_names.append(vlan_group)
        for group_name in dict.fromkeys(group_names):
            group = nb.ipam.vlan_groups.get(name=group_name)
            if group is None:
                msg = f"vlan group '{group_name}' does not exist in NetBox"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - Sync VLANs: {msg}")
                ret.errors.append(msg)
                ret.failed = True
                return ret
            vlan_groups[group_name] = group
        rules = prepare_vlan_map(rules, vlan_groups)
        if vlan_groups:
            job.event(f"resolved {len(vlan_groups)} NetBox VLAN group(s)")

        # Build the site and group scopes used for comparison.
        scope_metadata = {}
        site_scopes = {}
        group_scopes = {}
        for device_name in devices:
            device = nb_devices[device_name]
            scope = f"site:{device.site.id}:{device.site.name}"
            site_scopes[device_name] = scope
            scope_metadata[scope] = {
                "type": "site",
                "id": device.site.id,
                "name": device.site.name,
            }
        for group in vlan_groups.values():
            scope = f"group:{group.id}:{group.name}"
            group_scopes[group.name] = scope
            scope_metadata[scope] = {
                "type": "group",
                "id": group.id,
                "name": group.name,
            }
        job.event(f"resolved {len(scope_metadata)} VLAN scope(s)")

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
        for worker_name, worker_data in parse_data.items():
            if worker_data.get("failed"):
                msg = f"worker '{worker_name}' failed to collect live VLAN data"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - Sync VLANs: {msg}")
                ret.errors.append(msg)
                continue
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
            if device_name not in live_by_device:
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

        # Map live observations to a group or site identity. Group identities use
        # VID because groups enforce VID uniqueness. Site identities include the
        # VLAN name because a site may contain multiple VLANs with the same VID.
        observations = {scope: {} for scope in scope_metadata}
        for device_name in sorted(live_by_device):
            for vlan in live_by_device[device_name]:
                selected_group_name = (
                    match_vlan_map(
                        rules,
                        vlan_id=vlan["vid"],
                        vlan_name=vlan["name"],
                        device_name=device_name,
                        interface_name=None,
                    )
                    or vlan_group
                )
                if selected_group_name:
                    scope = group_scopes[selected_group_name]
                else:
                    scope = site_scopes[device_name]
                metadata = scope_metadata[scope]
                identity = vlan_identity(
                    metadata,
                    vlan["vid"],
                    vlan["name"],
                )
                observations[scope].setdefault(identity, []).append(
                    {"device": device_name, **vlan}
                )

        # Collapse identical observations. A conflict is limited to one complete
        # identity, so differently named site VLANs with the same VID remain valid.
        normalized_live = {scope: {} for scope in scope_metadata}
        conflicting_identities = {scope: set() for scope in scope_metadata}
        source_conflict_count = 0
        for scope in sorted(observations):
            for identity in sorted(observations[scope]):
                records = observations[scope][identity]
                desired_values = {
                    (record["name"], record["description"]) for record in records
                }
                if len(desired_values) > 1:
                    conflict = [
                        {
                            "device": record["device"],
                            "name": record["name"],
                            "description": record["description"],
                        }
                        for record in sorted(records, key=lambda item: item["device"])
                    ]
                    msg = (
                        f"{scope} VLAN {records[0]['vid']} source conflict: "
                        f"{json.dumps(conflict)}"
                    )
                    job.event(msg, severity="ERROR")
                    log.error(f"{self.name} - Sync VLANs: {msg}")
                    ret.errors.append(msg)
                    conflicting_identities[scope].add(identity)
                    source_conflict_count += 1
                    continue
                normalized_live[scope][identity] = {
                    "vid": records[0]["vid"],
                    "name": records[0]["name"],
                    "description": records[0]["description"],
                }

        # Load current NetBox VLANs once. Matching happens in two passes below so
        # exact VID/name/scope matches are reserved before broader VID/scope matches.
        job.event(f"loading NetBox VLANs from {len(scope_metadata)} scope(s)")
        netbox_by_vid = {scope: {} for scope in scope_metadata}
        netbox_vlan_count = 0
        for scope in sorted(scope_metadata):
            metadata = scope_metadata[scope]
            scope_filter = {f"{metadata['type']}_id": metadata["id"]}
            for vlan in self.bulk_filter(
                nb.ipam.vlans,
                fields="id,vid,name,description",
                **scope_filter,
            ):
                vid = int(vlan.vid)
                if expanded_filter and vid not in expanded_filter:
                    continue
                name = str(vlan.name).strip()
                if vlan_identity(metadata, vid, name) in conflicting_identities[scope]:
                    continue
                netbox_vlan_count += 1
                netbox_by_vid[scope].setdefault(vid, []).append(vlan)
        job.event(f"loaded {netbox_vlan_count} in-scope NetBox VLAN record(s)")

        normalized_netbox = {scope: {} for scope in scope_metadata}
        netbox_objects = {scope: {} for scope in scope_metadata}
        used_netbox_ids = set()
        exact_match_count = 0
        fallback_match_count = 0

        # Resolve all exact matches before falling back to VID and scope only.
        for exact_match in (True, False):
            for scope in sorted(normalized_live):
                for identity, desired in sorted(normalized_live[scope].items()):
                    if identity in normalized_netbox[scope]:
                        continue
                    match = find_vlan(
                        netbox_by_vid[scope].get(desired["vid"], []),
                        vid=desired["vid"],
                        name=desired["name"] if exact_match else None,
                        excluded_ids=used_netbox_ids,
                    )
                    if match is None:
                        continue
                    normalized_netbox[scope][identity] = normalize_netbox_vlan(match)
                    netbox_objects[scope][identity] = match
                    used_netbox_ids.add(match.id)
                    if exact_match:
                        exact_match_count += 1
                    else:
                        fallback_match_count += 1
        job.event(
            f"resolved {exact_match_count} exact and "
            f"{fallback_match_count} fallback NetBox VLAN match(es)"
        )
        log.info(
            f"{self.name} - Sync VLANs: {exact_match_count} exact, "
            f"{fallback_match_count} fallback NetBox match(es)"
        )

        # DeepDiff compares only the normalized compound-key structures. Convert
        # entity identities back to VIDs before exposing the standard task result.
        job.event("calculating VLAN sync diff")
        internal_diff = self.make_diff(normalized_live, normalized_netbox)

        def entity_vid(scope: str, identity: str) -> int:
            return normalized_live[scope][identity]["vid"]

        full_diff = {
            scope: {
                "create": sorted(entity_vid(scope, key) for key in actions["create"]),
                "update": {
                    entity_vid(scope, key): actions["update"][key]
                    for key in sorted(actions["update"])
                },
                "delete": [],
                "in_sync": sorted(entity_vid(scope, key) for key in actions["in_sync"]),
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
            create_identities = sorted(
                actions["create"], key=lambda key: (entity_vid(scope, key), key)
            )
            update_identities = sorted(
                actions["update"], key=lambda key: (entity_vid(scope, key), key)
            )
            job.event(
                f"applying {scope}: {len(create_identities)} create, "
                f"{len(update_identities)} update"
            )

            scope_arg = {f"{metadata['type']}_id": metadata["id"]}
            create_payloads = [
                build_vlan_payload(
                    **normalized_live[scope][identity],
                    **scope_arg,
                )
                for identity in create_identities
            ]
            if create_payloads:
                nb.ipam.vlans.create(create_payloads)
                ret.result[scope]["created"].extend(
                    entity_vid(scope, identity) for identity in create_identities
                )
                job.event(f"{scope}: created {len(create_payloads)} VLAN(s)")

            update_payloads = []
            for identity in update_identities:
                field_changes = actions["update"][identity]
                desired = normalized_live[scope][identity]
                payload = {"id": netbox_objects[scope][identity].id}
                for field in ("name", "description"):
                    if field in field_changes:
                        payload[field] = desired[field]
                update_payloads.append(payload)
            if update_payloads:
                nb.ipam.vlans.update(update_payloads)
                ret.result[scope]["updated"].extend(
                    entity_vid(scope, identity) for identity in update_identities
                )
                job.event(f"{scope}: updated {len(update_payloads)} VLAN(s)")
            job.event(f"completed VLAN changes for {scope}")

        job.event("vlan sync complete")
        log.info(
            f"{self.name} - Sync VLANs complete: {create_count} created, "
            f"{update_count} updated, {in_sync_count} in sync"
        )
        return ret
