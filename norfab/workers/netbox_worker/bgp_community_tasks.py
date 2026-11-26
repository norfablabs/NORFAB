import logging
from typing import Any, Union

from norfab.core.worker import Job, Task
from norfab.models import Result

from .netbox_models import (
    NetboxFastApiArgs,
    SyncBgpCommunityInput,
    SyncBgpCommunityResult,
)
from .netbox_worker_utilities import review_sync_task_result

log = logging.getLogger(__name__)

NO_COMMUNITY_NAME = "__no_name__"


def normalise_community_name_field(
    current_value: str,
    community_name_field: Union[str, bool],
    live_value: str,
) -> dict:
    """Append missing live names to the current NetBox custom-field value."""
    if not community_name_field:
        return {}

    current_names = [name.strip() for name in current_value.split(",") if name.strip()]
    current_names_set = set(current_names)
    for name in live_value.split(","):
        name = name.strip()
        if name and name not in current_names_set:
            current_names.append(name)
            current_names_set.add(name)

    return {community_name_field: ", ".join(sorted(current_names))}


class NetboxBgpCommunityTasks:
    @Task(
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=SyncBgpCommunityInput,
        output=SyncBgpCommunityResult,
        mcp={
            "annotations": {
                "title": "Sync BGP Communities",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def sync_bgp_community(
        self,
        job: Job,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        with_approval: bool = False,
        timeout: int = 600,
        devices: Union[None, list] = None,
        branch: Union[None, str] = None,
        community_name_field: Union[str, bool] = "community_name",
        device_custom_field: str = "devices",
        batch_size: int = 1000,
        **kwargs: Any,
    ) -> Result:
        """Synchronize live BGP communities with NetBox.

        Route-target communities are stored as IPAM route targets. Every other
        community type is stored as a NetBox BGP plugin community. Route
        targets are keyed by community value. BGP plugin communities are keyed
        by community value and live community-set name, allowing NetBox to hold
        several standard communities with the same value. Objects are never
        deleted. When the configured custom field exists, it stores the sorted,
        comma-separated live community-set names observed for each object. The
        selected device custom field records devices on which each community was
        observed. Existing records can be updated only when that field applies
        to their object type. Platforms without a parser are reported in
        `resources_unsupported`. Missing live data is reported per device.

        Args:
            job: NorFab job object.
            instance: NetBox instance name. Uses the default instance when omitted.
            dry_run: Return the calculated diff without writing to NetBox.
            with_approval: Ask for approval before applying the prepared diff.
            timeout: Timeout in seconds for Nornir host resolution and parsing.
            devices: Explicit NetBox and Nornir device names.
            branch: NetBox Branching plugin branch name.
            community_name_field: Optional custom field for community-set names.
            device_custom_field: Community custom field containing associated devices.
            batch_size: Maximum number of records per NetBox write.
            **kwargs: Nornir FFun host filters.

        Returns:
            Result: Per-device route-target and BGP community synchronization actions.
        """
        devices = list(devices or [])
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:sync_bgp_community",
            result={},
            resources=[instance],
            dry_run=dry_run,
            diff={},
        )

        msg = (
            f"starting BGP community sync using NetBox instance '{instance}' for "
            f"{len(devices)} explicit device(s), dry_run={dry_run}"
        )
        job.event(msg)
        log.info(f"{self.name} - {msg}")

        msg = f"validating NetBox BGP plugin for '{instance}'"
        job.event(msg)
        log.info(f"{self.name} - {msg}")
        has_bgp_plugin = self.has_plugin("netbox_bgp", instance)
        if not has_bgp_plugin:
            msg = (
                f"netbox instance '{instance}' has no BGP plugin installed; "
                "syncing route targets only"
            )
            job.event(msg, severity="WARNING")
            log.warning(f"{self.name} - {msg}")

        nb = self._get_pynetbox(instance, branch=branch, job=job)

        if kwargs:
            msg = "resolving devices from Nornir filters"
            job.event(msg)
            log.info(f"{self.name} - {msg}")
            devices.extend(self.get_nornir_hosts(kwargs, timeout))
        devices = sorted(set(devices))
        if not devices:
            msg = "no devices specified"
            job.event(msg, severity="ERROR")
            log.error(f"{self.name} - {msg}")
            ret.errors.append(msg)
            ret.failed = True
            return ret

        netbox_devices = {
            device.name: device
            for device in self.bulk_filter(
                nb.dcim.devices,
                name=devices,
                fields="id,name",
            )
        }
        for device_name in [name for name in devices if name not in netbox_devices]:
            msg = f"device '{device_name}' not found in NetBox"
            job.event(msg, severity="ERROR")
            log.error(f"{self.name} - {msg}")
            ret.errors.append(msg)
            ret.resources_failed.append(device_name)
        devices = [name for name in devices if name in netbox_devices]
        if not devices:
            ret.failed = True
            return ret
        msg = f"validated {len(devices)} NetBox device(s)"
        job.event(msg)
        log.info(f"{self.name} - {msg}")

        if community_name_field and not nb.extras.custom_fields.get(
            name=community_name_field
        ):
            msg = (
                f"custom field '{community_name_field}' not found in NetBox; "
                "community name synchronization disabled"
            )
            job.event(msg, severity="WARNING")
            log.warning(f"{self.name} - {msg}")
            community_name_field = False

        endpoints = {
            "route_targets": (nb.ipam.route_targets, "name", "ipam.routetarget"),
        }
        if has_bgp_plugin:
            endpoints["communities"] = (
                nb.plugins.bgp.community,
                "value",
                "netbox_bgp.community",
            )
        device_field = nb.extras.custom_fields.get(name=device_custom_field)
        device_object_types = (
            getattr(device_field, "object_types", None)
            or getattr(device_field, "content_types", None)
            or []
        )

        msg = f"collecting live BGP communities from {len(devices)} device(s)"
        job.event(msg)
        log.info(f"{self.name} - {msg}")
        parsed = self.client.run_job(
            "nornir",
            "parse_ttp",
            kwargs={"get": "bgp_communities", "FL": devices},
            workers="all",
            timeout=timeout,
        )
        # Keep each device's live names separate until comparison.
        observations = {}
        identities = {community_type: {} for community_type in endpoints}
        reported_failures = set()
        unsupported = set()
        parsed_count = 0
        for worker_name, worker_data in parsed.items():
            ret.messages.extend(worker_data.get("messages") or [])
            unsupported.update(worker_data.get("resources_unsupported") or [])
            failures = (
                set(worker_data.get("resources_failed") or []) & netbox_devices.keys()
            )
            if failures:
                reported_failures.update(failures)
                msg = (
                    f"{worker_name} failed to fetch BGP community data from devices "
                    f"{', '.join(sorted(failures))}"
                )
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - {msg}")
                ret.errors.append(msg)
            if worker_data.get("failed"):
                msg = f"worker '{worker_name}' failed to collect BGP communities"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - {msg}")
                ret.errors.append(msg)
                continue
            records_by_device = worker_data.get("result")
            if not isinstance(records_by_device, dict):
                msg = f"worker '{worker_name}' returned malformed community data"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - {msg}")
                ret.errors.append(msg)
                continue
            for device, records in records_by_device.items():
                if device not in netbox_devices or device in failures:
                    continue
                if not isinstance(records, list):
                    msg = f"device '{device}' community result is not a list"
                    job.event(msg, severity="ERROR")
                    log.error(f"{self.name} - {msg}")
                    ret.errors.append(msg)
                    reported_failures.add(device)
                    continue
                if any(
                    not isinstance(record, dict)
                    or not all(
                        isinstance(record.get(field), str) and record[field].strip()
                        for field in ("value", "type")
                    )
                    for record in records
                ):
                    msg = f"device '{device}' returned malformed community record"
                    job.event(msg, severity="ERROR")
                    log.error(f"{self.name} - {msg}")
                    ret.errors.append(msg)
                    reported_failures.add(device)
                    continue
                # An empty parser result still confirms that the device was collected.
                community_types = observations.setdefault(
                    device, {community_type: {} for community_type in endpoints}
                )
                for record in records:
                    value = record["value"].strip()
                    if ":" not in value:
                        continue
                    name = record.get("name")
                    name = name.strip() if isinstance(name, str) else ""
                    community_type = (
                        "route_targets"
                        if record["type"].strip().lower() == "rt"
                        else "communities"
                    )
                    if community_type not in endpoints:
                        continue
                    parsed_count += 1
                    key = (
                        value
                        if community_type == "route_targets"
                        else f"{value}::{name or NO_COMMUNITY_NAME}"
                    )
                    identities[community_type][key] = (value, name)
                    names = community_types[community_type].setdefault(key, set())
                    if name:
                        names.add(name)

        # A usable result takes precedence over another worker's unsupported report.
        unsupported = (unsupported & netbox_devices.keys()) - observations.keys()
        ret.resources_unsupported = sorted(unsupported - reported_failures)
        missing = (
            netbox_devices.keys() - observations.keys() - set(ret.resources_unsupported)
        )
        for device in sorted(missing - reported_failures):
            msg = f"device '{device}' is missing a live community result"
            job.event(msg, severity="ERROR")
            log.error(f"{self.name} - {msg}")
            ret.errors.append(msg)
        ret.resources_failed.extend(sorted(missing))
        if not observations:
            ret.failed = bool(ret.errors)
            return ret
        msg = (
            f"parsed {parsed_count} live community record(s) from "
            f"{len(observations)} device(s)"
        )
        job.event(msg)
        log.info(f"{self.name} - {msg}")

        live = {device: {} for device in sorted(observations)}
        netbox = {device: {} for device in live}
        matched = {}
        for community_type, (endpoint, value_field, object_type) in endpoints.items():
            has_devices = object_type in device_object_types
            keys = identities[community_type]
            values = sorted({value for value, _ in keys.values()})
            label = (
                "route targets"
                if community_type == "route_targets"
                else "BGP plugin communities"
            )
            msg = f"matching live {label} with NetBox"
            job.event(msg)
            log.info(f"{self.name} - {msg}")
            candidates = {}
            if values:
                fields = f"id,{value_field},custom_fields"
                if community_type == "communities":
                    fields += ",description"
                for row in self.bulk_filter(
                    endpoint, fields=fields, **{value_field: values}
                ):
                    candidates.setdefault(str(getattr(row, value_field)), []).append(
                        row
                    )

            # Prefer a stored alias, then a matching description, then an unlabeled record.
            for key, (value, name) in sorted(keys.items()):
                identity = (community_type, key)
                rows = candidates.get(value, [])
                if not rows:
                    continue
                if community_type == "route_targets" or not name:
                    matched[identity] = rows[0]
                    continue
                named, described, unlabeled = None, None, None
                for row in rows:
                    custom_fields = row.custom_fields or {}
                    names = {
                        item.strip()
                        for item in str(
                            custom_fields.get(community_name_field) or ""
                        ).split(",")
                        if item.strip()
                    }
                    description = (row.description or "").strip()
                    if name in names:
                        named = row
                        break
                    if described is None and name == description:
                        described = row
                    if unlabeled is None and not names and not description:
                        unlabeled = row
                row = named or described or unlabeled
                if row is not None:
                    matched[identity] = row

            # Add only this device's ID and names to the stored values.
            for device in live:
                device_id = netbox_devices[device].id
                desired = live[device]
                current = netbox[device]
                for key, names in sorted(observations[device][community_type].items()):
                    identity = (community_type, key)
                    row = matched.get(identity)
                    custom_fields = (row.custom_fields or {}) if row is not None else {}
                    stored_names = str(custom_fields.get(community_name_field) or "")
                    device_ids = (
                        {
                            member["id"]
                            for member in custom_fields.get(device_custom_field) or []
                        }
                        if has_devices
                        else set()
                    )
                    desired[identity] = normalise_community_name_field(
                        stored_names, community_name_field, ", ".join(sorted(names))
                    )
                    if has_devices or row is not None:
                        desired[identity][device_custom_field] = sorted(
                            device_ids | {device_id}
                        )
                    if row is not None:
                        current[identity] = normalise_community_name_field(
                            stored_names, community_name_field, ""
                        )
                        current[identity][device_custom_field] = (
                            sorted(device_ids) if has_devices else None
                        )

        # Compare both community types together and unpack the tuple keys for callers.
        diff = self.make_diff(live, netbox)
        for device in live:
            ret.diff[device] = {
                community_type: {
                    "create": [],
                    "delete": [],
                    "update": {},
                    "in_sync": [],
                }
                for community_type in endpoints
            }
            for action, identities_for_action in diff[device].items():
                for identity in identities_for_action:
                    community_type, key = identity
                    entries = ret.diff[device][community_type][action]
                    if action == "update":
                        entries[key] = identities_for_action[identity]
                    else:
                        entries.append(key)

        # Merge writes by physical record and track which device actions each write fulfills.
        writes = {}
        for community_type, (_, value_field, object_type) in endpoints.items():
            has_devices = object_type in device_object_types
            keys = identities[community_type]
            writes[community_type] = {"create": {}, "update": {}}
            blocked = set()
            for device in live:
                actions = ret.diff[device][community_type]
                for action in ("create", "update"):
                    for key in actions[action]:
                        identity = (community_type, key)
                        if action == "update" and not has_devices:
                            blocked.add(device)
                            continue
                        if action == "create":
                            value, name = keys[key]
                            payload = {value_field: value}
                            if community_type == "communities" and name:
                                payload["description"] = name
                            write_key = key
                        else:
                            write_key = matched[identity].id
                            payload = {"id": write_key}
                        payload, affected = writes[community_type][action].setdefault(
                            write_key, (payload, [])
                        )
                        affected.append((device, key))
                        fields = live[device][identity]
                        if action == "update":
                            fields = {
                                field: change["new_value"]
                                for field, change in actions[action][key].items()
                            }
                        if not fields:
                            continue
                        custom_fields = payload.setdefault("custom_fields", {})
                        if device_custom_field in fields:
                            custom_fields[device_custom_field] = sorted(
                                set(custom_fields.get(device_custom_field, []))
                                | set(fields[device_custom_field])
                            )
                        if community_name_field in fields:
                            custom_fields.update(
                                normalise_community_name_field(
                                    custom_fields.get(community_name_field, ""),
                                    community_name_field,
                                    fields[community_name_field],
                                )
                            )
            if blocked:
                msg = (
                    f"custom field '{device_custom_field}' unavailable for "
                    f"{community_type.replace('_', ' ')}; existing records cannot be updated "
                    f"for {', '.join(sorted(blocked))}"
                )
                ret.messages.append(msg)
                job.event(msg, severity="WARNING")

        create_count = sum(len(actions["create"]) for actions in writes.values())
        update_count = sum(len(actions["update"]) for actions in writes.values())
        in_sync_count = sum(
            len(actions["in_sync"])
            for community_types in ret.diff.values()
            for actions in community_types.values()
        )
        msg = (
            f"bgp community sync diff complete: "
            f"{create_count} create, {update_count} update, {in_sync_count} in sync"
        )
        job.event(msg)
        log.info(f"{self.name} - {msg}")

        if dry_run:
            ret.result = ret.diff
            return ret
        has_writes = bool(create_count or update_count)
        if (
            with_approval
            and has_writes
            and not review_sync_task_result(job, "BGP community sync", ret.diff)
        ):
            ret.status = "skipped"
            ret.dry_run = True
            ret.result = ret.diff
            ret.messages.append("review declined; changes were not applied")
            return ret

        for device, community_types in ret.diff.items():
            ret.result[device] = {
                community_type: {
                    "created": [],
                    "updated": [],
                    "deleted": [],
                    "in_sync": actions["in_sync"],
                }
                for community_type, actions in community_types.items()
            }
        if not has_writes:
            job.event("no BGP community sync changes required")
            return ret

        for community_type, actions in writes.items():
            endpoint = endpoints[community_type][0]
            if community_type == "route_targets":
                label, plural, unit = "route target", "route target(s)", "targets"
            else:
                label, plural, unit = (
                    "BGP community",
                    "BGP community object(s)",
                    "objects",
                )
            creates = actions["create"]
            create_keys = list(creates)
            if create_keys:
                msg = f"creating {len(create_keys)} {plural} in NetBox"
                job.event(msg)
                log.info(f"{self.name} - {msg}")
            total_batches = (len(create_keys) + batch_size - 1) // batch_size
            for start in range(0, len(create_keys), batch_size):
                batch = create_keys[start : start + batch_size]
                batch_number = start // batch_size + 1
                msg = (
                    f"creating {label} batch {batch_number}/{total_batches} "
                    f"({len(batch)} {unit})"
                )
                job.event(msg)
                log.info(msg)
                try:
                    endpoint.create([creates[key][0] for key in batch])
                except Exception as exc:
                    msg = f"failed to create {label} batch {batch_number}/{total_batches}: {exc}"
                    job.event(msg, severity="ERROR")
                    log.error(msg)
                    ret.errors.append(msg)
                    ret.failed = True
                    break
                for write_key in batch:
                    _, affected = creates.pop(write_key)
                    for device, key in affected:
                        ret.result[device][community_type]["created"].append(key)
            if ret.failed:
                break

            updates = actions["update"]
            update_keys = list(updates)
            if update_keys:
                msg = f"updating {len(update_keys)} {plural} in NetBox"
                job.event(msg)
                log.info(f"{self.name} - {msg}")
            total_batches = (len(update_keys) + batch_size - 1) // batch_size
            for start in range(0, len(update_keys), batch_size):
                batch = update_keys[start : start + batch_size]
                batch_number = start // batch_size + 1
                msg = (
                    f"updating {label} batch {batch_number}/{total_batches} "
                    f"({len(batch)} {unit})"
                )
                job.event(msg)
                log.info(msg)
                try:
                    endpoint.update([updates[key][0] for key in batch])
                except Exception as exc:
                    msg = f"failed to update {label} batch {batch_number}/{total_batches}: {exc}"
                    job.event(msg, severity="ERROR")
                    log.error(msg)
                    ret.errors.append(msg)
                    ret.failed = True
                    break
                for write_key in batch:
                    _, affected = updates.pop(write_key)
                    for device, key in affected:
                        ret.result[device][community_type]["updated"].append(key)
            if ret.failed:
                break

        for community_types in ret.result.values():
            for actions in community_types.values():
                actions["created"].sort()
                actions["updated"].sort()
        # Successful batches were removed from the plan, leaving failed and pending writes.
        if ret.failed:
            ret.resources_failed = sorted(
                set(ret.resources_failed)
                | {
                    device
                    for actions in writes.values()
                    for items in actions.values()
                    for _, affected in items.values()
                    for device, _ in affected
                }
            )
            return ret
        msg = (
            f"bgp community sync complete: {create_count} created, "
            f"{update_count} updated, {in_sync_count} in sync"
        )
        job.event(msg)
        log.info(f"{self.name} - {msg}")
        return ret
