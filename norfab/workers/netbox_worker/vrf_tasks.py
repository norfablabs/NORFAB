import logging
from typing import Any, Union

import yaml
from pydantic import TypeAdapter

from norfab.core.worker import Job, Task
from norfab.models import Result

from .netbox_models import (
    InterfaceMapRule,
    NetboxFastApiArgs,
    SyncVrfsInput,
    SyncVrfsResult,
)
from .netbox_worker_utilities import (
    apply_description_policy,
    map_interface_name,
    review_sync_task_result,
)

log = logging.getLogger(__name__)


class NetboxVrfsTasks:
    @Task(
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=SyncVrfsInput,
        output=SyncVrfsResult,
        mcp={
            "annotations": {
                "title": "Sync VRFs",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def sync_vrfs(
        self,
        job: Job,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        with_approval: bool = False,
        timeout: int = 600,
        devices: Union[None, list] = None,
        branch: Union[None, str] = None,
        device_custom_field: str = "devices",
        rpl_import_ipv4: str = "rpl_import_ipv4",
        rpl_import_ipv6: str = "rpl_import_ipv6",
        rpl_export_ipv4: str = "rpl_export_ipv4",
        rpl_export_ipv6: str = "rpl_export_ipv6",
        preserve_description: Union[None, bool] = None,
        interface_map: Union[None, str, list] = None,
        batch_size: int = 1000,
        **kwargs: Any,
    ) -> Result:
        """Compare each device's live VRFs and synchronize shared NetBox records.

        VRFs have global scope and are identified by name. Descriptions are
        synchronized, while live import/export route targets extend the
        existing NetBox associations. Routing-policy references are added to
        the configured VRF custom fields when the BGP plugin is installed.
        The configured devices field records which devices reported each VRF.
        The task assigns existing mapped interfaces to their live VRFs.
        Route distinguishers are outside this task's scope.

        Args:
            job: NorFab job object.
            instance: NetBox instance name. Uses the default instance when omitted.
            dry_run: Return the calculated diff without writing to NetBox.
            with_approval: Ask for approval before applying the prepared diff.
            timeout: Timeout in seconds for Nornir host resolution and parsing.
            devices: Explicit NetBox and Nornir device names.
            branch: NetBox Branching plugin branch name.
            device_custom_field: VRF custom field containing associated devices.
            rpl_import_ipv4: VRF custom field for IPv4 import routing policies.
            rpl_import_ipv6: VRF custom field for IPv6 import routing policies.
            rpl_export_ipv4: VRF custom field for IPv4 export routing policies.
            rpl_export_ipv6: VRF custom field for IPv6 export routing policies.
            preserve_description: Description preservation policy. ``None`` preserves
                NetBox text when the live description is empty, ``True`` always
                preserves NetBox text, and ``False`` always uses live text.
            interface_map: Ordered interface rename rules, or an ``nf://`` YAML
                file containing them.
            batch_size: Maximum number of records per NetBox write.
            **kwargs: Nornir FFun host filters.

        Returns:
            Result: Per-device VRF, route-target, routing-policy, and interface actions.
                Missing collection, and missing mapped interfaces are reported through `resources_failed`.
        """
        # Resolve the selected devices and collect covered live observations.
        instance = instance or self.default_instance
        devices = list(devices or [])
        if kwargs:
            devices.extend(self.get_nornir_hosts(kwargs, timeout))
        devices = sorted(set(devices))
        if self.is_url(interface_map):
            interface_map = TypeAdapter(list[InterfaceMapRule]).validate_python(
                yaml.safe_load(self.fetch_file(interface_map, raise_on_fail=True)) or []
            )
        interface_map = [
            rule.model_dump() if hasattr(rule, "model_dump") else rule
            for rule in interface_map or []
        ]
        ret = Result(
            task=f"{self.name}:sync_vrfs",
            resources=[instance],
            dry_run=dry_run,
            result={},
            diff={},
        )
        if not devices:
            message = "no devices specified"
            job.event(message, severity="ERROR")
            log.error(message)
            ret.errors.append(message)
            ret.failed = True
            return ret

        job.event(
            f"starting VRF sync on NetBox instance '{instance}' "
            f"for {len(devices)} device(s), dry_run={dry_run}"
        )
        nb = self._get_pynetbox(instance, branch=branch, job=job)
        nb_devices = {
            row.name: row
            for row in self.bulk_filter(
                nb.dcim.devices, name=devices, fields="id,name,device_type"
            )
        }
        if not nb_devices:
            message = f"requested devices not found in NetBox: {', '.join(devices)}"
            job.event(message, severity="ERROR")
            log.error(message)
            ret.errors.append(message)
            ret.resources_failed = devices
            ret.failed = True
            return ret

        # Use only custom fields available on this NetBox instance.
        policy_fields = {}
        if self.has_plugin("netbox_bgp", instance):
            policy_fields = {
                ("ipv4", "import"): rpl_import_ipv4,
                ("ipv6", "import"): rpl_import_ipv6,
                ("ipv4", "export"): rpl_export_ipv4,
                ("ipv6", "export"): rpl_export_ipv6,
            }
        else:
            message = (
                "netbox BGP plugin is not installed; skipping VRF routing policies"
            )
            job.event(message, severity="WARNING")
            log.warning(message)
        available_fields = {
            field.name
            for field in self.bulk_filter(
                nb.extras.custom_fields,
                name=sorted({device_custom_field, *policy_fields.values()}),
            )
        }
        device_field = device_custom_field in available_fields
        policy_fields = {
            key: name for key, name in policy_fields.items() if name in available_fields
        }

        # Collect live data in one job so each device can be checked independently.
        job.event(f"collecting live VRFs for {len(nb_devices)} device(s)")
        parsed = self.client.run_job(
            "nornir",
            "parse_ttp",
            kwargs={"get": "vrfs", "FL": sorted(nb_devices)},
            workers="all",
            timeout=timeout,
        )
        records_by_device = {}
        for worker, response in (parsed or {}).items():
            worker_failures = response.get("resources_failed") or []
            ret.resources_failed.extend(worker_failures)
            if worker_failures:
                ret.errors.append(
                    f"worker '{worker}' failed to collect live VRF data for "
                    f"{', '.join(sorted(worker_failures))}"
                )
            elif response.get("failed"):
                ret.errors.append(f"worker '{worker}' failed to collect live VRF data")
            if not response.get("failed"):
                records_by_device.update(response.get("result") or {})

        live_vrfs = {}
        live_interfaces = {}
        policy_field_names = sorted(set(policy_fields.values()))
        target_fields = ("import_targets", "export_targets")
        additive_fields = (*target_fields, *policy_field_names)
        # Keep empty results distinct from missing or invalid device data.
        for device in devices:
            records = records_by_device.get(device)
            if (
                device not in nb_devices
                or device in ret.resources_failed
                or not isinstance(records, list)
            ):
                ret.resources_failed.append(device)
                reason = (
                    "not found in NetBox"
                    if device not in nb_devices
                    else "missing usable live VRF data"
                )
                ret.errors.append(f"device '{device}' {reason}")
                continue
            live_vrfs[device] = {}

        # Collect comparable VRF fields and mapped interface assignments.
        for device, record in (
            (device, record)
            for device in live_vrfs
            for record in records_by_device[device]
        ):
            if record.get("instance_type") not in (None, "", "vrf"):
                continue
            name = record["name"]
            if not name or name in live_vrfs[device]:
                raise ValueError(f"invalid or duplicate VRF name {name!r}")
            families = record["address_families"]
            desired = {"description": record["description"] or ""}
            for direction, field in zip(("import", "export"), target_fields):
                desired[field] = sorted(
                    {
                        target
                        for family in families.values()
                        for target in family[f"rt_{direction}"]
                    }
                )
            for field in policy_field_names:
                desired[field] = []
            for (family, direction), field in policy_fields.items():
                policy = families[family][f"route_policy_{direction}"]
                if policy:
                    desired[field].append(policy)
            device_type = str(nb_devices[device].device_type.model)
            live_vrfs[device][name] = desired
            for live_name in record["interfaces"]:
                interface = map_interface_name(
                    live_name, interface_map, device, device_type
                )
                key = (device, interface)
                previous = live_interfaces.get(key)
                if previous is not None and previous != name:
                    raise ValueError(
                        f"conflicting VRF assignments for interface {interface!r}"
                    )
                live_interfaces[key] = name

        if not live_vrfs:
            ret.errors.append("no usable live VRF data")
            for message in ret.errors:
                job.event(message, severity="ERROR")
                log.error(message)
            ret.resources_failed = sorted(
                set(ret.resources_failed).intersection(devices)
            )
            ret.failed = True
            return ret

        # Load current interfaces and select one physical NetBox record per VRF name.
        job.event("loading current VRFs and interface assignments from NetBox")
        interface_objects = {}
        interface_names_by_device = {}
        for device, name in live_interfaces:
            interface_names_by_device.setdefault(device, set()).add(name)
        for device, names in interface_names_by_device.items():
            rows = self.bulk_filter(
                nb.dcim.interfaces,
                device_id=nb_devices[device].id,
                name=sorted(names),
                fields="id,name,device,vrf",
            )
            for interface in rows:
                if (
                    interface.device.id == nb_devices[device].id
                    and interface.name in names
                ):
                    interface_objects[device, interface.name] = interface

        candidate_names = {name for vrfs in live_vrfs.values() for name in vrfs}
        netbox_vrfs_by_name = {}
        duplicate_names = set()
        rows = []
        if candidate_names:
            rows = self.bulk_filter(
                nb.ipam.vrfs,
                name=sorted(candidate_names),
                fields="id,name,description,import_targets,export_targets,custom_fields",
            )
        for vrf in sorted(rows, key=lambda row: row.id):
            name = vrf.name
            if name in netbox_vrfs_by_name:
                duplicate_names.add(name)
                message = (
                    f"multiple NetBox VRFs named '{name}'; "
                    f"using ID {netbox_vrfs_by_name[name]['id']}"
                )
                job.event(message, severity="WARNING")
                log.warning(message)
                continue

            # Keep IDs with the normalized fields used for comparison.
            custom_fields = vrf.custom_fields or {}
            current = {
                "description": vrf.description or "",
                "import_targets": sorted(
                    {target.name for target in vrf.import_targets}
                ),
                "export_targets": sorted(
                    {target.name for target in vrf.export_targets}
                ),
            }
            for field in policy_field_names:
                current[field] = sorted(
                    {
                        policy.get("name") or policy["display"]
                        for policy in custom_fields.get(field) or []
                    }
                )
            if device_field:
                current[device_custom_field] = sorted(
                    {
                        member["id"]
                        for member in custom_fields.get(device_custom_field) or []
                    }
                )
            netbox_vrfs_by_name[name] = {"id": vrf.id, "fields": current}

        # DeepDiff compares device VRFs and mapped interface assignments independently.
        netbox_vrfs = {device: {} for device in live_vrfs}
        netbox_interfaces = {device: {} for device in live_vrfs}
        desired_interfaces = {device: {} for device in live_vrfs}
        for (device, interface), name in live_interfaces.items():
            current = interface_objects.get((device, interface))
            if current is None:
                ret.resources_failed.append(device)
                ret.errors.append(
                    f"interface '{device}:{interface}' not found in NetBox"
                )
                continue
            current_name = current.vrf.name if current.vrf else None
            desired = {"vrf": name}
            comparable = {"vrf": current_name}
            if current_name == name and name in duplicate_names:
                desired["vrf_id"] = netbox_vrfs_by_name[name]["id"]
                comparable["vrf_id"] = current.vrf.id
            desired_interfaces[device][interface] = desired
            netbox_interfaces[device][interface] = comparable

        descriptions = {}
        for device, vrfs in live_vrfs.items():
            device_id = nb_devices[device].id
            # Keep the first nonempty live description for the shared write.
            for name, desired in vrfs.items():
                current = netbox_vrfs_by_name.get(name, {}).get("fields", {})
                if not descriptions.get(name):
                    descriptions[name] = desired["description"]
                for field in additive_fields:
                    desired[field] = sorted(
                        set(desired[field]) | set(current.get(field, []))
                    )
                if device_field:
                    device_members = set(current.get(device_custom_field, []))
                    desired[device_custom_field] = sorted(device_members | {device_id})
                if not current:
                    continue

                desired["description"] = apply_description_policy(
                    desired["description"], current["description"], preserve_description
                )
                netbox_vrfs[device][name] = current

        vrf_diffs = self.make_diff(live_vrfs, netbox_vrfs)
        interface_diffs = self.make_diff(desired_interfaces, netbox_interfaces)

        # Merge per-device changes by VRF name so each NetBox record gets one write.
        creates_by_name = {}
        updates_by_name = {}
        for device, actions in vrf_diffs.items():
            for name in actions["create"]:
                fields = creates_by_name.setdefault(name, {})
                desired = live_vrfs[device][name]
                for field in desired.keys() - {"description"}:
                    fields.setdefault(field, set()).update(desired[field])
            for name, changes in actions["update"].items():
                fields = updates_by_name.setdefault(name, {})
                for field in changes.keys() - {"description"}:
                    fields.setdefault(field, set()).update(changes[field]["new_value"])

        for name, fields in creates_by_name.items():
            fields.update({field: sorted(values) for field, values in fields.items()})
            fields["description"] = descriptions[name]
        for name, raw_description in descriptions.items():
            if name not in netbox_vrfs_by_name:
                continue
            current_description = netbox_vrfs_by_name[name]["fields"]["description"]
            description = apply_description_policy(
                raw_description, current_description, preserve_description
            )
            if description != current_description:
                updates_by_name.setdefault(name, {})["description"] = description
        for name, fields in list(updates_by_name.items()):
            if not fields:
                del updates_by_name[name]
                continue
            for field in fields.keys() - {"description"}:
                fields[field] = sorted(fields[field])

        # Resolve target and policy IDs before building the VRF payloads.
        dependency_ids = {}
        missing_dependencies = {}
        dependencies = (
            ("route_targets", target_fields, nb.ipam.route_targets),
            (
                "routing_policies",
                policy_field_names,
                nb.plugins.bgp.routing_policy if policy_fields else None,
            ),
        )
        for section, fields, endpoint in dependencies:
            names = sorted(
                {
                    value
                    for change in (*creates_by_name.values(), *updates_by_name.values())
                    for field in fields
                    for value in change.get(field, [])
                }
            )
            ids = {}
            if names:
                ids = {
                    row.name: row.id
                    for row in self.bulk_filter(endpoint, name=names, fields="id,name")
                }
            dependency_ids[section] = ids
            missing_dependencies[section] = sorted(set(names) - ids.keys())

        # Assemble the per-device preview before preparing any apply state.
        for device, vrfs in live_vrfs.items():
            diff = {"vrfs": vrf_diffs[device], "interfaces": interface_diffs[device]}
            for section, fields, _ in dependencies:
                required = {
                    value
                    for vrf in vrfs.values()
                    for field in fields
                    for value in vrf[field]
                }
                diff[section] = {
                    "create": sorted(
                        required.intersection(missing_dependencies[section])
                    ),
                    "update": {},
                    "delete": [],
                    "in_sync": [],
                }
            ret.diff[device] = diff
        for message in ret.errors:
            job.event(message, severity="ERROR")
            log.error(message)
        ret.resources_failed = sorted(set(ret.resources_failed).intersection(devices))
        interface_update_count = sum(
            len(diff["update"]) for diff in interface_diffs.values()
        )
        job.event(
            f"vrf sync diff complete for {len(live_vrfs)} device(s): "
            f"{len(creates_by_name)} VRF create(s), "
            f"{len(updates_by_name)} VRF update(s), "
            f"{interface_update_count} interface update(s)"
        )
        if dry_run:
            ret.result = ret.diff
            return ret

        has_writes = bool(creates_by_name or updates_by_name or interface_update_count)
        if with_approval and has_writes:
            if not review_sync_task_result(job, "VRF sync", ret.diff):
                ret.status = "skipped"
                ret.result = ret.diff
                ret.dry_run = True
                ret.messages.append("review declined; changes were not applied")
                job.event("vrf sync approval declined")
                return ret

        for device, diff in ret.diff.items():
            ret.result[device] = {
                section: {
                    "created": [],
                    "updated": [],
                    "deleted": [],
                    "in_sync": actions["in_sync"],
                }
                for section, actions in diff.items()
            }
        if not has_writes:
            job.event("no VRF sync changes required")
            return ret

        # Write dependencies before building VRF payloads that reference their IDs.
        dependencies_created = 0
        for section, _, endpoint in dependencies:
            names = missing_dependencies[section]
            for start in range(0, len(names), batch_size):
                batch = [{"name": name} for name in names[start : start + batch_size]]
                batch_number = start // batch_size + 1
                job.event(
                    f"applying {section} create batch {batch_number} ({len(batch)} records)"
                )
                try:
                    rows = endpoint.create(batch)
                except Exception as exc:
                    message = f"failed to create {section} batch {batch_number}: {exc}"
                    ret.errors.append(message)
                    job.event(message, severity="ERROR")
                    log.error(message)
                    ret.failed = True
                    return ret
                for row in rows:
                    dependency_ids[section][row.name] = row.id
                dependencies_created += len(rows)
                for device, name in (
                    (device, row.name)
                    for row in rows
                    for device, diff in ret.diff.items()
                    if row.name in diff[section]["create"]
                ):
                    ret.result[device][section]["created"].append(name)

        # Build full payloads for new VRFs and field-only patches for existing VRFs.
        vrf_creates = []
        vrf_updates = []
        vrf_names_by_id = {}
        for name in sorted(creates_by_name.keys() | updates_by_name.keys()):
            is_update = name in updates_by_name
            fields = updates_by_name[name] if is_update else creates_by_name[name]
            payload = {
                field: [dependency_ids["route_targets"][target] for target in value]
                for field, value in fields.items()
                if field in target_fields
            }
            if "description" in fields:
                payload["description"] = fields["description"]
            custom_fields = {
                field: [dependency_ids["routing_policies"][policy] for policy in value]
                for field, value in fields.items()
                if field in policy_field_names
            }
            if device_field and device_custom_field in fields:
                custom_fields[device_custom_field] = fields[device_custom_field]
            if custom_fields:
                payload["custom_fields"] = custom_fields
            if is_update:
                object_id = netbox_vrfs_by_name[name]["id"]
                payload["id"] = object_id
                vrf_updates.append(payload)
                vrf_names_by_id[object_id] = name
            else:
                payload["name"] = name
                vrf_creates.append(payload)

        # Create VRFs first so interface assignments can reference the new IDs.
        vrfs_created = 0
        for start in range(0, len(vrf_creates), batch_size):
            batch = vrf_creates[start : start + batch_size]
            batch_number = start // batch_size + 1
            job.event(
                f"applying vrfs create batch {batch_number} ({len(batch)} records)"
            )
            try:
                rows = nb.ipam.vrfs.create(batch)
            except Exception as exc:
                message = f"failed to create vrfs batch {batch_number}: {exc}"
                ret.errors.append(message)
                job.event(message, severity="ERROR")
                log.error(message)
                ret.failed = True
                return ret
            for row in rows:
                netbox_vrfs_by_name[row.name] = {
                    "id": row.id,
                    "fields": creates_by_name[row.name],
                }
            vrfs_created += len(rows)
            for device, name in (
                (device, row.name)
                for row in rows
                for device, diff in ret.diff.items()
                if row.name in diff["vrfs"]["create"]
            ):
                ret.result[device]["vrfs"]["created"].append(name)

        # Patch existing VRFs and credit only devices whose changes were applied.
        for start in range(0, len(vrf_updates), batch_size):
            batch = vrf_updates[start : start + batch_size]
            batch_number = start // batch_size + 1
            job.event(
                f"applying vrfs update batch {batch_number} ({len(batch)} records)"
            )
            try:
                nb.ipam.vrfs.update(batch)
            except Exception as exc:
                message = f"failed to update vrfs batch {batch_number}: {exc}"
                ret.errors.append(message)
                job.event(message, severity="ERROR")
                log.error(message)
                ret.failed = True
                return ret
            updated_names = [vrf_names_by_id[payload["id"]] for payload in batch]
            for device, name, changes in (
                (device, name, diff["vrfs"]["update"][name])
                for name in updated_names
                for device, diff in ret.diff.items()
                if name in diff["vrfs"]["update"]
            ):
                if any(
                    field in changes
                    and (field != "description" or value == changes[field]["new_value"])
                    for field, value in updates_by_name[name].items()
                ):
                    ret.result[device]["vrfs"]["updated"].append(name)

        # Build interface assignments after all destination VRF IDs are known.
        interface_updates = []
        interface_names_by_id = {}
        for device in live_vrfs:
            for interface in sorted(interface_diffs[device]["update"]):
                vrf_name = live_interfaces[device, interface]
                payload = {
                    "id": interface_objects[device, interface].id,
                    "vrf": netbox_vrfs_by_name[vrf_name]["id"],
                }
                interface_updates.append(payload)
                interface_names_by_id[payload["id"]] = (device, interface)

        for start in range(0, len(interface_updates), batch_size):
            batch = interface_updates[start : start + batch_size]
            batch_number = start // batch_size + 1
            job.event(
                f"applying interfaces update batch {batch_number} ({len(batch)} records)"
            )
            try:
                nb.dcim.interfaces.update(batch)
            except Exception as exc:
                message = f"failed to update interfaces batch {batch_number}: {exc}"
                ret.errors.append(message)
                job.event(message, severity="ERROR")
                log.error(message)
                ret.resources_failed = sorted(
                    set(ret.resources_failed)
                    | {interface_names_by_id[payload["id"]][0] for payload in batch}
                )
                ret.failed = True
                return ret
            for payload in batch:
                device, interface = interface_names_by_id[payload["id"]]
                ret.result[device]["interfaces"]["updated"].append(interface)

        job.event(
            f"vrf sync complete: {dependencies_created} dependencies created, "
            f"{vrfs_created} VRFs created, {len(vrf_updates)} VRFs updated, "
            f"{len(interface_updates)} interfaces updated"
        )
        return ret
