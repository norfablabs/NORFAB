import logging
from typing import Any, Union

import yaml
from pydantic import TypeAdapter

from norfab.core.worker import Job, Task
from norfab.models import Result

from .netbox_models import (
    InterfaceMapRule,
    NetboxFastApiArgs,
    SyncActionSummary,
    SyncVrfsInput,
    SyncVrfsResult,
    SyncVrfsResultPayload,
)
from .netbox_worker_utilities import (
    apply_description_policy,
    map_interface_name,
    review_sync_task_result,
    sync_diff_has_changes,
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
        """Synchronize live VRFs, route targets, and interface assignments with NetBox.

        VRFs have global scope and are identified by name. Descriptions are
        synchronized, while live import/export route targets extend the
        existing NetBox associations. Routing-policy references are added to
        the configured VRF custom fields when the BGP plugin is installed.
        Route distinguishers returned by the parser are not stored. The selected VRF custom field
        records devices on which each VRF was observed. Interfaces listed by
        the parser are assigned to their VRFs when they exist in NetBox.

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
            **kwargs: Nornir FFun host filters.

        Returns:
            Result: VRF, route-target, routing-policy, and interface assignment actions.
        """
        # Normalize task inputs before resolving the selected NetBox devices.
        devices = list(devices or [])
        instance = instance or self.default_instance
        if self.is_url(interface_map):
            interface_map = TypeAdapter(list[InterfaceMapRule]).validate_python(
                yaml.safe_load(self.fetch_file(interface_map, raise_on_fail=True)) or []
            )
        interface_map = [
            rule.model_dump() if hasattr(rule, "model_dump") else dict(rule)
            for rule in interface_map or []
        ]
        ret = Result(
            task=f"{self.name}:sync_vrfs",
            result=SyncVrfsResultPayload().model_dump(),
            resources=[instance],
            dry_run=dry_run,
            diff={
                "vrfs": {},
                "route_targets": {},
                "routing_policies": {},
                "interfaces": {},
            },
        )

        msg = (
            f"starting VRF sync using NetBox instance '{instance}' for "
            f"{len(devices)} explicit device(s), dry_run={dry_run}"
        )
        job.event(msg)
        log.info(f"Sync VRFs: {msg}")
        nb = self._get_pynetbox(instance, branch=branch, job=job)

        if kwargs:
            devices.extend(self.get_nornir_hosts(kwargs, timeout))
        devices = sorted(set(devices))
        if not devices:
            msg = "no devices specified"
            job.event(msg, severity="ERROR")
            log.error(f"Sync VRFs: {msg}")
            ret.errors.append(msg)
            ret.failed = True
            return ret

        nb_devices = {
            device.name: device
            for device in self.bulk_filter(
                nb.dcim.devices,
                name=devices,
                fields="id,name,device_type",
            )
        }
        for device_name in [name for name in devices if name not in nb_devices]:
            msg = f"device '{device_name}' not found in NetBox"
            job.event(msg, severity="ERROR")
            log.error(f"Sync VRFs: {msg}")
            ret.errors.append(msg)
        devices = [name for name in devices if name in nb_devices]
        if not devices:
            ret.failed = True
            return ret
        ret.result["interfaces"] = {
            device_name: SyncActionSummary().model_dump() for device_name in devices
        }

        if not nb.extras.custom_fields.get(name=device_custom_field):
            device_custom_field = None
        policy_fields = {
            ("ipv4", "import"): rpl_import_ipv4,
            ("ipv6", "import"): rpl_import_ipv6,
            ("ipv4", "export"): rpl_export_ipv4,
            ("ipv6", "export"): rpl_export_ipv6,
        }
        if self.has_plugin("netbox_bgp", instance):
            policy_fields = {
                key: name
                for key, name in policy_fields.items()
                if nb.extras.custom_fields.get(name=name)
            }
        else:
            policy_fields = {}
            msg = "netbox BGP plugin is not installed; skipping VRF routing policies"
            job.event(msg, severity="WARNING")
            log.warning(f"Sync VRFs: {msg}")

        # Collect per-device observations. Address-family route targets and
        # policies are flattened here for the global VRF reconciliation.
        msg = f"collecting live VRFs from {len(devices)} device(s)"
        job.event(msg)
        log.info(f"Sync VRFs: {msg}")
        parse_data = self.client.run_job(
            "nornir",
            "parse_ttp",
            kwargs={"get": "vrfs", "FL": devices},
            workers="all",
            timeout=timeout,
        )
        observations = {}
        result_devices = set()
        failed_devices = set()
        for worker_name, worker_data in parse_data.items():
            resources_failed = worker_data.get("resources_failed") or []
            if resources_failed:
                failed_devices.update(resources_failed)
                ret.resources_failed = sorted(
                    set(ret.resources_failed) | set(resources_failed)
                )
                msg = (
                    f"{worker_name} failed to fetch VRF data from devices "
                    f"{', '.join(sorted(resources_failed))}"
                )
                job.event(msg, severity="ERROR")
                log.error(f"Sync VRFs: {msg}")
                ret.errors.append(msg)
            if worker_data["failed"]:
                msg = f"worker '{worker_name}' failed to collect live VRF data"
                job.event(msg, severity="ERROR")
                log.error(f"Sync VRFs: {msg}")
                ret.errors.append(msg)
                continue
            for device_name, records in worker_data["result"].items():
                if device_name not in nb_devices:
                    continue
                result_devices.add(device_name)
                for record in records:
                    if record.get("instance_type") and record["instance_type"] != "vrf":
                        continue
                    address_families = record["address_families"]
                    policies = {}
                    for (family, direction), field_name in policy_fields.items():
                        policy = address_families[family][f"route_policy_{direction}"]
                        policies[field_name] = [policy] if policy else []
                    observations.setdefault(record["name"], []).append(
                        {
                            "device": device_name,
                            "description": record["description"] or "",
                            "import_targets": [
                                target
                                for family in address_families.values()
                                for target in family["rt_import"]
                            ],
                            "export_targets": [
                                target
                                for family in address_families.values()
                                for target in family["rt_export"]
                            ],
                            "routing_policies": policies,
                            "interfaces": record["interfaces"],
                        }
                    )

        for device_name in devices:
            if device_name not in result_devices and device_name not in failed_devices:
                msg = f"device '{device_name}' is missing a live VRF result"
                job.event(msg, severity="ERROR")
                log.error(f"Sync VRFs: {msg}")
                ret.errors.append(msg)
        if not result_devices:
            msg = "no usable live VRF data"
            job.event(msg, severity="ERROR")
            log.error(f"Sync VRFs: {msg}")
            ret.failed = True
            return ret

        # Build the global desired VRF state and a separate interface assignment
        # index. Sorting observations makes description precedence deterministic.
        live_vrfs = {}
        interface_targets = {}
        for vrf_name in sorted(observations):
            records = sorted(observations[vrf_name], key=lambda item: item["device"])
            live_vrfs[vrf_name] = {
                "description": next(
                    (
                        record["description"]
                        for record in records
                        if record["description"]
                    ),
                    "",
                ),
                "import_targets": list(
                    dict.fromkeys(
                        target
                        for record in records
                        for target in record["import_targets"]
                    )
                ),
                "export_targets": list(
                    dict.fromkeys(
                        target
                        for record in records
                        for target in record["export_targets"]
                    )
                ),
            }
            if device_custom_field:
                live_vrfs[vrf_name][device_custom_field] = sorted(
                    {nb_devices[record["device"]].id for record in records}
                )
            for field_name in policy_fields.values():
                live_vrfs[vrf_name][field_name] = list(
                    dict.fromkeys(
                        policy
                        for record in records
                        for policy in record["routing_policies"][field_name]
                    )
                )
            for record in records:
                device_name = record["device"]
                device_type = str(nb_devices[device_name].device_type.model)
                for live_name in record["interfaces"]:
                    interface_name = map_interface_name(
                        live_name,
                        interface_map,
                        device_name,
                        device_type,
                    )
                    key = (device_name, interface_name)
                    interface_targets[key] = vrf_name

        # Load only live VRF names. NetBox can return duplicate names, so retain
        # the lowest-ID record as the task's authoritative object and warn.
        netbox_vrfs = {}
        object_cache = {}
        vrf_names = list(live_vrfs)
        netbox_vrfs_records = (
            self.bulk_filter(
                nb.ipam.vrfs,
                name=vrf_names,
                fields="id,name,description,import_targets,export_targets,custom_fields",
            )
            if vrf_names
            else []
        )
        for vrf in netbox_vrfs_records:
            current = {
                "description": vrf.description,
                "import_targets": [target.name for target in vrf.import_targets],
                "export_targets": [target.name for target in vrf.export_targets],
            }
            live_vrfs[vrf.name]["description"] = apply_description_policy(
                live_vrfs[vrf.name]["description"],
                current["description"],
                preserve_description,
            )
            if device_custom_field:
                current[device_custom_field] = [
                    device["id"]
                    for device in (vrf.custom_fields[device_custom_field] or [])
                ]
                live_vrfs[vrf.name][device_custom_field] = sorted(
                    set(current[device_custom_field])
                    | set(live_vrfs[vrf.name][device_custom_field])
                )
            for field_name in policy_fields.values():
                current[field_name] = [
                    policy.get("name") or policy["display"]
                    for policy in (vrf.custom_fields[field_name] or [])
                ]
            existing_vrf = object_cache.get(("vrf", vrf.name))
            if existing_vrf:
                msg = (
                    f"multiple NetBox VRFs matched "
                    f"by name '{vrf.name}', using lowest ID from "
                    f"{existing_vrf.id} and {vrf.id}"
                )
                job.event(msg, severity="WARNING")
                log.warning(f"Sync VRFs: {msg}")
            if existing_vrf is None or int(vrf.id) < int(existing_vrf.id):
                netbox_vrfs[vrf.name] = current
                object_cache[("vrf", vrf.name)] = vrf

        # Route-target and routing-policy updates are additive. Retain existing
        # NetBox associations and add values newly observed in live data.
        for vrf_name, current in netbox_vrfs.items():
            for field in (
                "import_targets",
                "export_targets",
                rpl_import_ipv4,
                rpl_import_ipv6,
                rpl_export_ipv4,
                rpl_export_ipv6,
            ):
                if field in current:
                    live_vrfs[vrf_name][field] = sorted(
                        set(current[field]) | set(live_vrfs[vrf_name][field])
                    )

        vrf_diff = self.make_diff(
            {"vrfs": live_vrfs},
            {"vrfs": netbox_vrfs},
        )["vrfs"]
        vrf_diff["delete"] = []

        create_names = vrf_diff["create"]
        update = vrf_diff["update"]
        in_sync = vrf_diff["in_sync"]

        # Resolve route targets referenced by actionable VRF changes. Missing
        # objects become part of the plan but are not created until after review.
        route_target_names = list(
            dict.fromkeys(
                target
                for vrf_name in [*create_names, *sorted(update)]
                for field in ("import_targets", "export_targets")
                for target in live_vrfs[vrf_name][field]
            )
        )
        if route_target_names:
            object_cache.update(
                {
                    ("route_target", target.name): target
                    for target in self.bulk_filter(
                        nb.ipam.route_targets,
                        name=route_target_names,
                        fields="id,name",
                    )
                }
            )
        missing_route_targets = [
            name
            for name in route_target_names
            if ("route_target", name) not in object_cache
        ]
        route_target_diff = {
            "create": missing_route_targets,
            "update": {},
            "delete": [],
            "in_sync": [],
        }
        # Include missing BGP policy objects in the review plan; resolve IDs
        # only for policies referenced by VRFs that need creation or update.
        policy_names = list(
            dict.fromkeys(
                policy
                for vrf_name in [*create_names, *sorted(update)]
                for field_name in policy_fields.values()
                for policy in live_vrfs[vrf_name][field_name]
            )
        )
        if policy_names:
            object_cache.update(
                {
                    ("routing_policy", policy.name): policy
                    for policy in self.bulk_filter(
                        nb.plugins.bgp.routing_policy,
                        name=policy_names,
                        fields="id,name",
                    )
                }
            )
        missing_policies = [
            name
            for name in policy_names
            if ("routing_policy", name) not in object_cache
        ]
        policy_diff = {
            "create": missing_policies,
            "update": {},
            "delete": [],
            "in_sync": [],
        }

        # Fetch the cross-product of referenced devices and names in one request,
        # then retain exact (device, interface) matches for assignment comparison.
        interface_objects = {}
        if interface_targets:
            interface_records = self.bulk_filter(
                nb.dcim.interfaces,
                device_id=sorted(
                    {nb_devices[device].id for device, _ in interface_targets}
                ),
                name=sorted({name for _, name in interface_targets}),
                fields="id,name,device,vrf",
            )
            interface_objects = {
                (str(interface.device.name), str(interface.name)): interface
                for interface in interface_records
                if (str(interface.device.name), str(interface.name))
                in interface_targets
            }

        for device_name, interface_name in sorted(
            interface_targets.keys() - interface_objects.keys()
        ):
            msg = f"interface '{device_name}:{interface_name}' not found in NetBox"
            job.event(msg, severity="ERROR")
            log.error(f"Sync VRFs: {msg}")
            ret.errors.append(msg)

        interface_live = {}
        interface_current = {}
        for key in sorted(interface_targets.keys() & interface_objects.keys()):
            device_name, interface_name = key
            interface = interface_objects[key]
            interface_live.setdefault(device_name, {})[interface_name] = {
                "vrf": interface_targets[key]
            }
            interface_current.setdefault(device_name, {})[interface_name] = {
                "vrf": str(interface.vrf.name) if interface.vrf else None
            }

        # Interface identity is scoped by device. A different current VRF becomes
        # a normal update, while an equal assignment is reported as in sync.
        interface_diff = self.make_diff(interface_live, interface_current)
        ret.result["vrfs"]["in_sync"] = in_sync
        for device_name, actions in interface_diff.items():
            ret.result["interfaces"][device_name]["in_sync"] = actions["in_sync"]
        full_diff = {
            "vrfs": vrf_diff,
            "route_targets": route_target_diff,
            "routing_policies": policy_diff,
            "interfaces": interface_diff,
        }
        msg = (
            "vrf sync diff complete: "
            f"{len(create_names)} create, {len(update)} update, "
            f"{len(in_sync)} in sync"
        )
        job.event(msg)
        log.info(f"Sync VRFs: {msg}")

        ret.diff = full_diff
        if dry_run:
            ret.result = full_diff
            ret.dry_run = True
            return ret
        if not sync_diff_has_changes(full_diff):
            msg = "no VRF sync changes required"
            job.event(msg)
            log.info(f"Sync VRFs: {msg}")
            return ret
        if with_approval and not review_sync_task_result(job, "VRF sync", full_diff):
            ret.status = "skipped"
            ret.result = full_diff
            ret.dry_run = True
            ret.messages.append("review declined; changes were not applied")
            msg = "vrf sync approval declined"
            job.event(msg)
            log.info(f"Sync VRFs: {msg}")
            return ret

        # Apply global VRF changes first so every desired VRF ID is cached before
        # building the dependent interface assignment updates.
        if missing_route_targets:
            target_payloads = [{"name": name} for name in missing_route_targets]
            total_batches = (len(target_payloads) + batch_size - 1) // batch_size
            for batch_start in range(0, len(target_payloads), batch_size):
                batch = target_payloads[batch_start : batch_start + batch_size]
                batch_number = batch_start // batch_size + 1
                msg = f"creating route target batch {batch_number}/{total_batches} ({len(batch)} target(s))"
                job.event(msg)
                log.info(msg)
                try:
                    created_targets = nb.ipam.route_targets.create(batch)
                except Exception as exc:
                    msg = f"failed to create route target batch {batch_number}/{total_batches}: {exc}"
                    job.event(msg, severity="ERROR")
                    log.error(msg)
                    ret.errors.append(msg)
                    ret.failed = True
                    return ret
                for target in created_targets:
                    object_cache[("route_target", target.name)] = target
                    ret.result["route_targets"]["created"].append(target.name)
        if missing_policies:
            policy_payloads = [{"name": name} for name in missing_policies]
            total_batches = (len(policy_payloads) + batch_size - 1) // batch_size
            for batch_start in range(0, len(policy_payloads), batch_size):
                batch = policy_payloads[batch_start : batch_start + batch_size]
                batch_number = batch_start // batch_size + 1
                msg = f"creating routing policy batch {batch_number}/{total_batches} ({len(batch)} policy(s))"
                job.event(msg)
                log.info(msg)
                try:
                    created_policies = nb.plugins.bgp.routing_policy.create(batch)
                except Exception as exc:
                    msg = f"failed to create routing policy batch {batch_number}/{total_batches}: {exc}"
                    job.event(msg, severity="ERROR")
                    log.error(msg)
                    ret.errors.append(msg)
                    ret.failed = True
                    return ret
                for policy in created_policies:
                    object_cache[("routing_policy", policy.name)] = policy
                    ret.result["routing_policies"]["created"].append(policy.name)

        create_payloads = []
        for vrf_name in create_names:
            desired = live_vrfs[vrf_name]
            payload = {
                "name": vrf_name,
                "description": desired["description"],
                "import_targets": [
                    object_cache[("route_target", name)].id
                    for name in desired["import_targets"]
                ],
                "export_targets": [
                    object_cache[("route_target", name)].id
                    for name in desired["export_targets"]
                ],
            }
            custom_fields = {}
            if device_custom_field:
                custom_fields[device_custom_field] = desired[device_custom_field]
            for field_name in policy_fields.values():
                custom_fields[field_name] = [
                    object_cache[("routing_policy", name)].id
                    for name in desired[field_name]
                ]
            if custom_fields:
                payload["custom_fields"] = custom_fields
            create_payloads.append(payload)
        if create_payloads:
            total_batches = (len(create_payloads) + batch_size - 1) // batch_size
            for batch_start in range(0, len(create_payloads), batch_size):
                batch = create_payloads[batch_start : batch_start + batch_size]
                batch_number = batch_start // batch_size + 1
                msg = f"creating VRF batch {batch_number}/{total_batches} ({len(batch)} VRF(s))"
                job.event(msg)
                log.info(msg)
                try:
                    created_vrfs = nb.ipam.vrfs.create(batch)
                except Exception as exc:
                    msg = f"failed to create VRF batch {batch_number}/{total_batches}: {exc}"
                    job.event(msg, severity="ERROR")
                    log.error(msg)
                    ret.errors.append(msg)
                    ret.failed = True
                    return ret
                for vrf in created_vrfs:
                    object_cache[("vrf", vrf.name)] = vrf
                    ret.result["vrfs"]["created"].append(vrf.name)

        update_payloads = []
        for vrf_name in sorted(update):
            desired = live_vrfs[vrf_name]
            payload = {"id": object_cache[("vrf", vrf_name)].id}
            for field in update[vrf_name]:
                if field == "description":
                    payload[field] = desired[field]
                elif field in ("import_targets", "export_targets"):
                    payload[field] = [
                        object_cache[("route_target", name)].id
                        for name in desired[field]
                    ]
                elif field == device_custom_field:
                    payload.setdefault("custom_fields", {})[field] = desired[field]
                elif field in policy_fields.values():
                    payload.setdefault("custom_fields", {})[field] = [
                        object_cache[("routing_policy", name)].id
                        for name in desired[field]
                    ]
            update_payloads.append((vrf_name, payload))
        if update_payloads:
            total_batches = (len(update_payloads) + batch_size - 1) // batch_size
            for batch_start in range(0, len(update_payloads), batch_size):
                batch = update_payloads[batch_start : batch_start + batch_size]
                batch_number = batch_start // batch_size + 1
                msg = f"updating VRF batch {batch_number}/{total_batches} ({len(batch)} VRF(s))"
                job.event(msg)
                log.info(msg)
                try:
                    nb.ipam.vrfs.update([payload for _, payload in batch])
                except Exception as exc:
                    msg = f"failed to update VRF batch {batch_number}/{total_batches}: {exc}"
                    job.event(msg, severity="ERROR")
                    log.error(msg)
                    ret.errors.append(msg)
                    ret.failed = True
                    return ret
                ret.result["vrfs"]["updated"].extend(name for name, _ in batch)

        # Assign only interfaces classified as updates; matching assignments have
        # already been retained in the result's in_sync lists.
        interface_payloads = []
        for device_name, actions in sorted(interface_diff.items()):
            for interface_name in sorted(actions["update"]):
                vrf_name = interface_live[device_name][interface_name]["vrf"]
                interface_payloads.append(
                    (
                        (device_name, interface_name),
                        {
                            "id": interface_objects[(device_name, interface_name)].id,
                            "vrf": object_cache[("vrf", vrf_name)].id,
                        },
                    )
                )
        if interface_payloads:
            total_batches = (len(interface_payloads) + batch_size - 1) // batch_size
            for batch_start in range(0, len(interface_payloads), batch_size):
                batch = interface_payloads[batch_start : batch_start + batch_size]
                batch_number = batch_start // batch_size + 1
                msg = f"updating VRF interface batch {batch_number}/{total_batches} ({len(batch)} interface(s))"
                job.event(msg)
                log.info(msg)
                try:
                    nb.dcim.interfaces.update([payload for _, payload in batch])
                except Exception as exc:
                    msg = f"failed to update VRF interface batch {batch_number}/{total_batches}: {exc}"
                    job.event(msg, severity="ERROR")
                    log.error(msg)
                    ret.errors.append(msg)
                    ret.failed = True
                    return ret
                for (device_name, interface_name), _ in batch:
                    ret.result["interfaces"][device_name]["updated"].append(
                        interface_name
                    )
        msg = (
            "vrf sync complete: "
            f"{len(create_names)} VRF created, {len(update)} updated, "
            f"{len(in_sync)} in sync"
        )
        job.event(msg)
        log.info(f"Sync VRFs: {msg}")
        return ret
