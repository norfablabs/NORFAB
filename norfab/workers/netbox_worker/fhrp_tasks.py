import ipaddress
import logging
from typing import Any, Union

from jinja2 import Environment, StrictUndefined, TemplateError

from norfab.core.worker import Job, Task
from norfab.models import Result

from .netbox_models import NetboxFastApiArgs, SyncVrrpInput, SyncVrrpResult
from .netbox_worker_utilities import review_sync_task_result

log = logging.getLogger(__name__)

VRRP_PROTOCOLS = {"vrrpv2": "vrrp2", "vrrpv3": "vrrp3"}
VRRP_NAME_TEMPLATE = "{{ device.name }}_{{ interface }}_VRRP{{ group_id }}"
VRRP_NAME_TEMPLATE_ENV = Environment(undefined=StrictUndefined, autoescape=False)


class NetboxFhrpTasks:
    @Task(
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=SyncVrrpInput,
        output=SyncVrrpResult,
        mcp={
            "annotations": {
                "title": "Sync VRRP",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def sync_vrrp(
        self,
        job: Job,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        with_approval: bool = False,
        timeout: int = 600,
        devices: Union[None, list] = None,
        branch: Union[None, str] = None,
        name_template: str = VRRP_NAME_TEMPLATE,
        **kwargs: Any,
    ) -> Result:
        """Synchronize live VRRP state with NetBox.

        An assignment is identified by device, interface, and group ID. Virtual
        address, protocol version, assignment priority, and group
        authentication type are synchronized. Compatible peer assignments reuse
        a NetBox FHRP group when their protocol, group ID, virtual address, and
        authentication match.

        The sync is additive. Existing groups, assignments, and virtual addresses
        which are absent from live data are retained.

        Args:
            job: NorFab job object.
            instance: NetBox instance name. Uses the default instance when omitted.
            dry_run: Return the calculated diff without writing to NetBox.
            with_approval: Ask for approval before applying the prepared diff.
            timeout: Timeout in seconds for Nornir host resolution and parsing.
            devices: Explicit NetBox and Nornir device names.
            branch: NetBox Branching plugin branch name.
            name_template: Inline Jinja2 template or ``nf://`` path used to render
                the NetBox FHRP group name.
            **kwargs: Nornir FFun host filters.

        Returns:
            Result: Per-device VRRP synchronization actions.
        """
        devices = list(devices or [])
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:sync_vrrp",
            result={},
            resources=[instance],
            dry_run=dry_run,
            diff={},
        )

        job.event(
            f"starting VRRP sync using NetBox instance '{instance}' for "
            f"{len(devices)} explicit device(s)"
        )
        log.info(f"{self.name} - Sync VRRP: instance '{instance}', dry_run={dry_run}")

        name_template = name_template or VRRP_NAME_TEMPLATE
        if self.is_url(name_template):
            job.event(f"fetching VRRP group name template '{name_template}'")
            name_template = self.fetch_file(name_template, raise_on_fail=True).strip()
        try:
            group_name_template = VRRP_NAME_TEMPLATE_ENV.from_string(name_template)
        except TemplateError as exc:
            msg = f"invalid VRRP group name template: {exc}"
            job.event(msg, severity="ERROR")
            log.error(f"{self.name} - Sync VRRP: {msg}")
            ret.errors.append(msg)
            ret.failed = True
            return ret
        job.event("prepared VRRP group name template")

        nb = self._get_pynetbox(instance, branch=branch, job=job)

        # Resolve filters once and validate devices before doing network work.
        if kwargs:
            job.event("resolving devices from Nornir filters")
            devices.extend(self.get_nornir_hosts(kwargs, timeout))
        devices = sorted(set(devices))
        if not devices:
            msg = "no devices specified"
            job.event(msg, severity="ERROR")
            log.error(f"{self.name} - Sync VRRP: {msg}")
            ret.errors.append(msg)
            ret.failed = True
            return ret
        job.event(f"selected {len(devices)} device(s) for VRRP sync")

        nb_devices = {
            device.name: device
            for device in self.bulk_filter(
                nb.dcim.devices,
                name=devices,
                fields="id,name,platform,role,device_type,site",
            )
        }
        for device_name in devices:
            if device_name in nb_devices:
                continue
            msg = f"device '{device_name}' not found in NetBox"
            job.event(msg, severity="ERROR")
            log.error(f"{self.name} - Sync VRRP: {msg}")
            ret.errors.append(msg)
        devices = [name for name in devices if name in nb_devices]
        if not devices:
            ret.failed = True
            return ret

        interfaces = self.bulk_filter(
            nb.dcim.interfaces,
            device_id=[nb_devices[name].id for name in devices],
            fields="id,name,device",
        )
        interfaces_by_name = {
            (interface.device.name, interface.name): interface
            for interface in interfaces
        }
        interfaces_by_id = {interface.id: interface for interface in interfaces}
        job.event(
            f"validated {len(devices)} device(s) and loaded "
            f"{len(interfaces)} NetBox interface(s)"
        )

        # Collect live records and normalize them directly into the shape used
        # by make_diff. Getter protocol values are mapped to NetBox choices.
        job.event(f"collecting live VRRP state from {len(devices)} device(s)")
        log.info(f"{self.name} - Sync VRRP: collecting from {len(devices)} device(s)")
        parse_data = self.client.run_job(
            "nornir",
            "parse_ttp",
            kwargs={"get": "vrrp", "FL": devices},
            workers="all",
            timeout=timeout,
        )
        job.event(f"received VRRP data from {len(parse_data)} Nornir worker(s)")

        live_state = {}
        failed_devices = set()
        for worker_name, worker_data in parse_data.items():
            if worker_data.get("failed"):
                msg = f"worker '{worker_name}' failed to collect live VRRP data"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - Sync VRRP: {msg}")
                ret.errors.append(msg)
                continue

            resources_failed = worker_data.get("resources_failed") or []
            if resources_failed:
                failed_devices.update(resources_failed)
                msg = (
                    f"{worker_name} failed to fetch VRRP data from devices "
                    f"{', '.join(sorted(resources_failed))}"
                )
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - Sync VRRP: {msg}")
                ret.errors.append(msg)

            worker_result = worker_data.get("result")
            if not isinstance(worker_result, dict):
                msg = f"worker '{worker_name}' returned malformed VRRP data"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - Sync VRRP: {msg}")
                ret.errors.append(msg)
                continue

            for device_name, records in worker_result.items():
                if device_name not in nb_devices:
                    continue
                device_state = live_state.setdefault(device_name, {})
                if not isinstance(records, list):
                    msg = f"device '{device_name}' VRRP result is not a list"
                    job.event(msg, severity="ERROR")
                    log.error(f"{self.name} - Sync VRRP: {msg}")
                    ret.errors.append(msg)
                    continue

                for record in records:
                    try:
                        interface_name = str(record["interface"]).strip()
                        group_id = int(record["group"])
                        protocol = VRRP_PROTOCOLS.get(
                            str(record["protocol"]).strip().lower()
                        )
                        if protocol is None:
                            raise ValueError(
                                f"unsupported protocol '{record['protocol']}'"
                            )
                        priority = int(record["priority"])
                        virtual_address = str(
                            ipaddress.ip_interface(str(record["virtual_address"])).ip
                        )
                        authentication_type = getattr(
                            record.get("authentication_type"),
                            "value",
                            record.get("authentication_type"),
                        )
                        authentication_type = (
                            str(authentication_type).strip().lower()
                            if authentication_type
                            else None
                        )
                        if authentication_type in (
                            "cleartext",
                            "plain",
                            "simple",
                            "text",
                        ):
                            authentication_type = "plaintext"
                        if not 0 <= priority <= 255:
                            raise ValueError("priority must be between 0 and 255")
                        if authentication_type not in (None, "plaintext", "md5"):
                            raise ValueError(
                                f"unsupported authentication type "
                                f"'{authentication_type}'"
                            )
                    except (KeyError, TypeError, ValueError) as exc:
                        msg = (
                            f"device '{device_name}' returned invalid VRRP data: {exc}"
                        )
                        job.event(msg, severity="ERROR")
                        log.error(f"{self.name} - Sync VRRP: {msg}")
                        ret.errors.append(msg)
                        continue

                    if (device_name, interface_name) not in interfaces_by_name:
                        msg = (
                            f"device '{device_name}' interface '{interface_name}' "
                            "does not exist in NetBox"
                        )
                        job.event(msg, severity="ERROR")
                        log.error(f"{self.name} - Sync VRRP: {msg}")
                        ret.errors.append(msg)
                        continue

                    key = f"{interface_name}:{group_id}"
                    desired = device_state.get(key)
                    if desired is None:
                        device_state[key] = {
                            "interface": interface_name,
                            "group_id": group_id,
                            "protocol": protocol,
                            "virtual_address": virtual_address,
                            "priority": priority,
                            "authentication_type": authentication_type,
                        }
                        continue

                    if (
                        desired["protocol"] != protocol
                        or desired["virtual_address"] != virtual_address
                        or desired["priority"] != priority
                        or desired["authentication_type"] != authentication_type
                    ):
                        msg = (
                            f"device '{device_name}' VRRP assignment '{key}' has "
                            "conflicting protocol, virtual address, priority, or "
                            "authentication values"
                        )
                        job.event(msg, severity="ERROR")
                        log.error(f"{self.name} - Sync VRRP: {msg}")
                        ret.errors.append(msg)

        for device_name in devices:
            if device_name not in live_state and device_name not in failed_devices:
                msg = f"device '{device_name}' is missing a live VRRP result"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - Sync VRRP: {msg}")
                ret.errors.append(msg)
        if not live_state:
            log.error(f"{self.name} - Sync VRRP: no usable live data")
            ret.failed = True
            return ret

        live_count = sum(len(records) for records in live_state.values())
        job.event(
            f"normalized {live_count} VRRP assignment(s) from "
            f"{len(live_state)} device(s)"
        )

        # A NetBox FHRP group is shared by its peers, so render its name once
        # from the first device/interface in deterministic sorted order.
        group_names = {}
        try:
            for device_name in sorted(live_state):
                for key in sorted(live_state[device_name]):
                    desired = live_state[device_name][key]
                    group_signature = (
                        desired["protocol"],
                        desired["group_id"],
                        desired["virtual_address"],
                        desired["authentication_type"],
                    )
                    if group_signature not in group_names:
                        group_name = group_name_template.render(
                            device=nb_devices[device_name],
                            interface=desired["interface"],
                            protocol=desired["protocol"],
                            group_id=desired["group_id"],
                            virtual_address=desired["virtual_address"],
                        ).strip()
                        if not group_name:
                            raise ValueError("rendered an empty name")
                        if len(group_name) > 100:
                            raise ValueError(
                                f"rendered name '{group_name}' exceeds 100 characters"
                            )
                        group_names[group_signature] = group_name
                    desired["name"] = group_names[group_signature]
        except (TemplateError, ValueError) as exc:
            msg = f"failed to render VRRP group name: {exc}"
            job.event(msg, severity="ERROR")
            log.error(f"{self.name} - Sync VRRP: {msg}")
            ret.errors.append(msg)
            ret.failed = True
            return ret
        job.event(f"rendered {len(group_names)} VRRP group name(s)")

        # Load only groups already assigned to the selected interfaces. Global
        # FHRP groups outside this device set are not part of the comparison.
        job.event("loading current VRRP assignments from NetBox")
        assignments = self.bulk_filter(
            nb.ipam.fhrp_group_assignments,
            device=devices,
            fields="id,group,interface_type,interface_id,priority",
        )
        assignment_group_ids = sorted(
            {assignment.group.id for assignment in assignments}
        )
        groups = {}
        if assignment_group_ids:
            for group in self.bulk_filter(
                nb.ipam.fhrp_groups,
                id=assignment_group_ids,
                fields="id,protocol,group_id,name,auth_type",
            ):
                group_protocol = str(
                    getattr(group.protocol, "value", group.protocol)
                ).lower()
                if group_protocol in VRRP_PROTOCOLS.values():
                    authentication_type = getattr(
                        group.auth_type, "value", group.auth_type
                    )
                    groups[group.id] = {
                        "object": group,
                        "virtual_address": None,
                        "name": str(group.name or ""),
                        "protocol": group_protocol,
                        "authentication_type": (
                            str(authentication_type).strip().lower()
                            if authentication_type
                            else None
                        ),
                    }

        if groups:
            for ip_record in self.bulk_filter(
                nb.ipam.ip_addresses,
                assigned_object_type="ipam.fhrpgroup",
                assigned_object_id=sorted(groups),
                fields="id,address,assigned_object_id,role",
            ):
                ip_role = getattr(ip_record.role, "value", ip_record.role)
                if str(ip_role or "").lower() == "vrrp":
                    groups[ip_record.assigned_object_id]["virtual_address"] = str(
                        ipaddress.ip_interface(str(ip_record.address)).ip
                    )

        current_state = {device_name: {} for device_name in devices}
        current_objects = {}
        for assignment in sorted(assignments, key=lambda item: item.id):
            interface = interfaces_by_id.get(assignment.interface_id)
            group_data = groups.get(assignment.group.id)
            if interface is None or group_data is None:
                continue
            group = group_data["object"]

            device_name = interface.device.name
            key = f"{interface.name}:{int(group.group_id)}"
            if key in current_state[device_name]:
                msg = (
                    f"device '{device_name}' interface '{interface.name}' has "
                    f"multiple VRRP group {group.group_id} assignments; using "
                    "the lowest assignment ID"
                )
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - Sync VRRP: {msg}")
                ret.errors.append(msg)
                continue

            current_state[device_name][key] = {
                "interface": interface.name,
                "group_id": int(group.group_id),
                "protocol": group_data["protocol"],
                "virtual_address": group_data["virtual_address"],
                "name": group_data["name"],
                "priority": int(assignment.priority),
                "authentication_type": group_data["authentication_type"],
            }
            current_objects[(device_name, key)] = (assignment, group_data)

        current_count = sum(len(records) for records in current_state.values())
        job.event(
            f"loaded {current_count} VRRP assignment(s) in "
            f"{len(groups)} NetBox group(s)"
        )

        job.event("calculating VRRP synchronization diff")
        sync_diff = self.make_diff(live_state, current_state)
        for actions in sync_diff.values():
            actions["create"] = sorted(actions["create"])
            actions["update"] = {
                key: actions["update"][key] for key in sorted(actions["update"])
            }
            actions["delete"] = []

        create_count = sum(len(actions["create"]) for actions in sync_diff.values())
        update_count = sum(len(actions["update"]) for actions in sync_diff.values())
        in_sync_count = sum(len(actions["in_sync"]) for actions in sync_diff.values())
        job.event(
            "vrrp sync diff complete: "
            f"{create_count} create, {update_count} update, "
            f"{in_sync_count} in sync"
        )
        log.info(
            f"{self.name} - Sync VRRP diff: {create_count} create, "
            f"{update_count} update, {in_sync_count} in sync"
        )

        if dry_run:
            job.event("dry-run requested, returning VRRP diff without changes")
            log.info(f"{self.name} - Sync VRRP: dry-run complete")
            ret.result = sync_diff
            ret.dry_run = True
            return ret

        if with_approval:
            job.event("requesting approval for the prepared VRRP sync plan")
        if with_approval and not review_sync_task_result(job, "VRRP sync", sync_diff):
            ret.status = "skipped"
            ret.result = sync_diff
            ret.dry_run = True
            ret.messages.append("review declined; changes were not applied")
            log.info(f"{self.name} - Sync VRRP: approval declined")
            return ret

        ret.diff = sync_diff
        ret.result = {
            device_name: {
                "created": [],
                "updated": [],
                "deleted": [],
                "in_sync": actions["in_sync"],
            }
            for device_name, actions in sync_diff.items()
        }

        desired_addresses = sorted(
            {
                assignment["virtual_address"]
                for device_state in live_state.values()
                for assignment in device_state.values()
            }
        )
        job.event(
            f"fetching {len(desired_addresses)} matching IP address(es) from NetBox"
        )
        nb_ips = self.bulk_filter(
            endpoint=nb.ipam.ip_addresses,
            address=desired_addresses,
            fields="id,address,role,assigned_object_type,assigned_object_id",
        )
        job.event(f"retrieved {len(nb_ips)} matching IP address object(s) from NetBox")

        # Apply assignments in deterministic order. A new assignment reuses a
        # compatible group when possible; otherwise it gets a new VRRP group.
        for device_name in sorted(sync_diff):
            actions = sync_diff[device_name]
            changed_keys = sorted(set(actions["create"]) | set(actions["update"]))
            if not changed_keys:
                continue
            job.event(
                f"applying {device_name}: {len(actions['create'])} create, "
                f"{len(actions['update'])} update"
            )

            for key in changed_keys:
                desired = live_state[device_name][key]
                assignment, group_data = current_objects.get(
                    (device_name, key), (None, None)
                )

                if group_data is None:
                    for candidate in sorted(
                        groups.values(), key=lambda item: item["object"].id
                    ):
                        candidate_group = candidate["object"]
                        if (
                            candidate["protocol"] == desired["protocol"]
                            and int(candidate_group.group_id) == desired["group_id"]
                            and candidate["authentication_type"]
                            == desired["authentication_type"]
                            and candidate["virtual_address"]
                            == desired["virtual_address"]
                        ):
                            group_data = candidate
                            break

                # Do not steal an existing IP from another NetBox object. Check
                # this before changing or creating the FHRP group so a conflict
                # cannot leave a partially applied group behind.
                address = desired["virtual_address"]
                assign_ip = not (
                    group_data and address == group_data["virtual_address"]
                )
                ip_record = None
                if assign_ip:
                    matching_ips = [
                        ip_record
                        for ip_record in nb_ips
                        if str(ip_record.address).startswith(f"{address}/")
                    ]
                    ip_record = next(
                        (
                            item
                            for item in matching_ips
                            if group_data
                            and item.assigned_object_type == "ipam.fhrpgroup"
                            and item.assigned_object_id == group_data["object"].id
                        ),
                        None,
                    )
                    if ip_record is None:
                        unassigned_ips = [
                            item
                            for item in matching_ips
                            if item.assigned_object_id is None
                        ]
                        ip_record = next(
                            (
                                item
                                for item in unassigned_ips
                                if str(
                                    getattr(item.role, "value", item.role) or ""
                                ).lower()
                                in ("vip", "vrrp")
                            ),
                            unassigned_ips[0] if unassigned_ips else None,
                        )
                    if ip_record is None and matching_ips:
                        ip_record = matching_ips[0]
                        msg = (
                            f"matching NetBox IP '{ip_record.address}' is already "
                            f"assigned to {ip_record.assigned_object_type} "
                            f"{ip_record.assigned_object_id}; cannot use it for "
                            f"VRRP assignment '{device_name}:{key}'"
                        )
                        job.event(msg, severity="ERROR")
                        log.error(f"{self.name} - Sync VRRP: {msg}")
                        ret.errors.append(msg)
                        continue

                if group_data is None:
                    group = nb.ipam.fhrp_groups.create(
                        protocol=desired["protocol"],
                        group_id=desired["group_id"],
                        name=desired["name"],
                        auth_type=desired["authentication_type"],
                    )
                    group_data = {
                        "object": group,
                        "virtual_address": None,
                        "name": desired["name"],
                        "protocol": desired["protocol"],
                        "authentication_type": desired["authentication_type"],
                    }
                    groups[group.id] = group_data
                else:
                    group = group_data["object"]
                    group_updates = {}
                    if group_data["protocol"] != desired["protocol"]:
                        group_updates["protocol"] = desired["protocol"]
                    if group_data["name"] != desired["name"]:
                        group_updates["name"] = desired["name"]
                    if (
                        group_data["authentication_type"]
                        != desired["authentication_type"]
                    ):
                        group_updates["auth_type"] = desired["authentication_type"]
                    if group_updates:
                        group.update(group_updates)
                        group_data["name"] = desired["name"]
                        group_data["protocol"] = desired["protocol"]
                        group_data["authentication_type"] = desired[
                            "authentication_type"
                        ]

                if assign_ip:
                    if ip_record is not None:
                        ip_record.update(
                            {
                                "role": "vrrp",
                                "assigned_object_type": "ipam.fhrpgroup",
                                "assigned_object_id": group.id,
                            }
                        )
                        job.event(
                            f"reused NetBox IP '{ip_record.address}' for VRRP "
                            f"group {group.group_id}"
                        )
                        log.info(
                            f"{self.name} - Sync VRRP: reused NetBox IP "
                            f"'{ip_record.address}' for group {group.group_id}"
                        )
                    else:
                        prefixes = list(nb.ipam.prefixes.filter(contains=address))
                        prefix_length = (
                            max(
                                ipaddress.ip_network(
                                    str(prefix.prefix), strict=False
                                ).prefixlen
                                for prefix in prefixes
                            )
                            if prefixes
                            else (
                                32
                                if ipaddress.ip_address(address).version == 4
                                else 128
                            )
                        )
                        ip_record = nb.ipam.ip_addresses.create(
                            address=f"{address}/{prefix_length}",
                            status="active",
                            role="vrrp",
                            assigned_object_type="ipam.fhrpgroup",
                            assigned_object_id=group.id,
                        )
                        job.event(
                            f"created NetBox VRRP IP '{ip_record.address}' for "
                            f"VRRP group {group.group_id}"
                        )
                        log.info(
                            f"{self.name} - Sync VRRP: created NetBox VRRP IP "
                            f"'{ip_record.address}' for group {group.group_id}"
                        )
                        nb_ips.append(ip_record)
                    group_data["virtual_address"] = address

                if assignment is None:
                    interface = interfaces_by_name[(device_name, desired["interface"])]
                    nb.ipam.fhrp_group_assignments.create(
                        group=group.id,
                        interface_type="dcim.interface",
                        interface_id=interface.id,
                        priority=desired["priority"],
                    )
                    ret.result[device_name]["created"].append(key)
                else:
                    if int(assignment.priority) != desired["priority"]:
                        assignment.update({"priority": desired["priority"]})
                    ret.result[device_name]["updated"].append(key)

            job.event(f"completed VRRP changes for {device_name}")

        job.event("vrrp sync complete")
        create_count = sum(len(actions["created"]) for actions in ret.result.values())
        update_count = sum(len(actions["updated"]) for actions in ret.result.values())
        log.info(
            f"{self.name} - Sync VRRP complete: {create_count} created, "
            f"{update_count} updated, {in_sync_count} in sync"
        )
        return ret
