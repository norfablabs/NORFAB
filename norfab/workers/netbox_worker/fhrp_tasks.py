import ipaddress
import logging
from typing import Any, Union

from jinja2 import Environment, StrictUndefined, TemplateError

from norfab.core.worker import Job, Task
from norfab.models import Result

from .netbox_models import (
    NetboxFastApiArgs,
    SyncActionSummary,
    SyncActionSummaryMap,
    SyncVrrpInput,
    SyncVrrpResult,
)
from .netbox_worker_utilities import review_sync_task_result, sync_diff_has_changes

log = logging.getLogger(__name__)

VRRP_PROTOCOLS = {"vrrpv2": "vrrp2", "vrrpv3": "vrrp3"}
VRRP_NAME_TEMPLATE = "{{ device.name }}_{{ interface }}_VRRP{{ group_id }}"
VRRP_NAME_TEMPLATE_ENV = Environment(undefined=StrictUndefined, autoescape=False)


def _group_signature(group: dict) -> tuple:
    """Return the peer identity shared by live and NetBox VRRP groups."""
    return tuple(
        group[field]
        for field in (
            "protocol",
            "group_id",
            "virtual_address",
            "authentication_type",
            "vrf",
        )
    )


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
        vip_use_vrf: bool = False,
        **kwargs: Any,
    ) -> Result:
        """Synchronize live VRRP state with NetBox.

        An assignment is identified by device, interface, protocol, and group
        ID. Virtual address, assignment priority, and group
        authentication type are synchronized. Compatible peer assignments reuse
        a NetBox FHRP group when their protocol, group ID, virtual address,
        authentication, and VRF match, including peers discovered in later calls.
        A named VIP VRF identifies the NetBox group's VRF; global VIPs use the
        VRF of the group's assigned interfaces. Missing live VRFs mean global.
        Global VIP discovery requires accurate NetBox interface VRFs and at
        least one assigned interface. Ambiguous peer groups and global VIP groups
        with mixed interface VRFs are reported as errors.
        Names of groups assigned to interfaces outside the selected devices
        are retained.

        The sync is additive. Existing groups, assignments, and virtual addresses
        which are absent from live data are retained.
        Group-owned VIP roles are normalized to ``vrrp`` without changing their VRF.
        Group, VIP, and assignment changes are prepared before diff calculation;
        ownership conflicts and missing required VRFs are reported during dry runs too.
        Existing assignments with a conflicting group VRF are reported without
        moving the assignment. IPs assigned to other interfaces or competing
        groups in the same VRF are never reassigned.

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
            vip_use_vrf: Use the live interface VRF when creating VIP addresses.
                Defaults to False. Existing VIP VRFs are always preserved.
                A missing named NetBox VRF is reported and VIP creation is skipped.
            **kwargs: Nornir FFun host filters.

        Returns:
            Result: Per-device VRRP synchronization actions.
        """
        devices = list(devices or [])
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:sync_vrrp",
            result=SyncActionSummaryMap().model_dump(),
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
            fields="id,name,device,vrf",
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
            resources_failed = worker_data.get("resources_failed") or []
            if resources_failed:
                failed_devices.update(resources_failed)
                ret.resources_failed = sorted(
                    set(ret.resources_failed) | set(resources_failed)
                )
                msg = (
                    f"{worker_name} failed to fetch VRRP data from devices "
                    f"{', '.join(sorted(resources_failed))}"
                )
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - Sync VRRP: {msg}")
                ret.errors.append(msg)
            if worker_data.get("failed"):
                msg = f"worker '{worker_name}' failed to collect live VRRP data"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - Sync VRRP: {msg}")
                ret.errors.append(msg)
                continue

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
                        priority_value = record.get("priority")
                        priority = (
                            100
                            if priority_value is None or not str(priority_value).strip()
                            else int(priority_value)
                        )
                        virtual_address_value = str(
                            record.get("virtual_address") or ""
                        ).strip()
                        if not virtual_address_value:
                            raise ValueError(
                                f"{interface_name} virtual address is missing"
                            )
                        virtual_address = str(
                            ipaddress.ip_interface(virtual_address_value).ip
                        )
                        vrf = record.get("vrf")
                        if vrf is not None:
                            if not isinstance(vrf, str):
                                raise ValueError("VRF must be a name string or null")
                            vrf = vrf.strip() or None
                            if vrf and vrf.lower() in ("global", "default"):
                                vrf = None
                        authentication_type = record.get("authentication_type")
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

                    # Priority belongs to this device/interface assignment;
                    # the VIP and authentication belong to the shared group.
                    key = f"{interface_name}:{protocol}:{group_id}"
                    device_state[key] = {
                        "interface": interface_name,
                        "group_id": group_id,
                        "protocol": protocol,
                        "virtual_address": virtual_address,
                        "priority": priority,
                        "authentication_type": authentication_type,
                        "vrf": vrf,
                        "role": "vrrp",
                    }

        for device_name in devices:
            if device_name not in live_state and device_name not in failed_devices:
                msg = f"device '{device_name}' is missing a live VRRP result"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - Sync VRRP: {msg}")
                ret.errors.append(msg)
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
                    group_signature = _group_signature(desired)
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

        # Discover VIP owners before calculating the diff. A later peer may
        # have no assignment yet, while its VIP already belongs to a group.
        # Reuse these IP records during writes to avoid another matching query.
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
        # An empty address filter can become an unfiltered API request.
        nb_ips = (
            self.bulk_filter(
                endpoint=nb.ipam.ip_addresses,
                address=desired_addresses,
                fields="id,address,role,vrf,assigned_object_type,assigned_object_id",
            )
            if desired_addresses
            else []
        )
        job.event(f"retrieved {len(nb_ips)} matching IP address object(s) from NetBox")
        # Index once by host address; a VIP's mask does not identify its group.
        ips_by_address = {}
        for ip_record in nb_ips:
            address = str(ipaddress.ip_interface(str(ip_record.address)).ip)
            ips_by_address.setdefault(address, []).append(ip_record)

        # Include groups owning live VIPs, even when their peers are outside
        # the selected devices.
        job.event("loading current VRRP assignments from NetBox")
        assignments = self.bulk_filter(
            nb.ipam.fhrp_group_assignments,
            device=devices,
            fields="id,group,interface_type,interface_id,priority",
        )
        assignment_group_ids = sorted(
            {assignment.group.id for assignment in assignments}
            | {
                ip_record.assigned_object_id
                for ip_record in nb_ips
                if ip_record.assigned_object_type == "ipam.fhrpgroup"
                and ip_record.assigned_object_id is not None
            }
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
                        "group_id": int(group.group_id),
                        "vrf": None,
                        "vrf_known": False,
                        "ip": None,
                        "role": None,
                        "authentication_type": (
                            str(authentication_type).strip().lower()
                            if authentication_type
                            else None
                        ),
                    }

        # Compare bare host addresses so an existing /24 VIP matches live data
        # without a prefix. A group-owned VIP with another role is normalized
        # during writes, so include its actual role in the comparison state.
        if groups:
            for ip_record in self.bulk_filter(
                nb.ipam.ip_addresses,
                assigned_object_type="ipam.fhrpgroup",
                assigned_object_id=sorted(groups),
                fields="id,address,assigned_object_type,assigned_object_id,role,vrf",
            ):
                group_data = groups[ip_record.assigned_object_id]
                ip_role = getattr(ip_record.role, "value", ip_record.role)
                group_data["ip"] = ip_record
                group_data["virtual_address"] = str(
                    ipaddress.ip_interface(str(ip_record.address)).ip
                )
                # A named VIP VRF is authoritative. A global VIP needs its
                # assigned interfaces to establish the group's VRF below.
                group_data["vrf"] = ip_record.vrf.name if ip_record.vrf else None
                group_data["vrf_known"] = ip_record.vrf is not None
                group_data["role"] = str(ip_role).lower() if ip_role else None

        # Preserve names of groups shared with peers outside this sync. A
        # device-based template must not rename their group when a peer joins.
        shared_group_ids = set()
        interface_vrfs = {group_id: set() for group_id in groups}
        if groups:
            group_assignments = self.bulk_filter(
                nb.ipam.fhrp_group_assignments,
                group_id=sorted(groups),
                fields="id,group,interface_type,interface_id",
            )
            shared_group_ids = {
                assignment.group.id
                for assignment in group_assignments
                if assignment.interface_type != "dcim.interface"
                or assignment.interface_id not in interfaces_by_id
            }
            peer_interface_ids = sorted(
                {
                    assignment.interface_id
                    for assignment in group_assignments
                    if assignment.interface_type == "dcim.interface"
                    and assignment.interface_id not in interfaces_by_id
                    and not groups[assignment.group.id]["vrf_known"]
                }
            )
            peer_interfaces = dict(interfaces_by_id)
            if peer_interface_ids:
                peer_interfaces.update(
                    {
                        interface.id: interface
                        for interface in self.bulk_filter(
                            nb.dcim.interfaces,
                            id=peer_interface_ids,
                            fields="id,name,device,vrf",
                        )
                    }
                )
            for assignment in group_assignments:
                if (
                    assignment.interface_type != "dcim.interface"
                    or groups[assignment.group.id]["vrf_known"]
                ):
                    continue
                interface = peer_interfaces.get(assignment.interface_id)
                if interface is not None:
                    interface_vrfs[assignment.group.id].add(
                        interface.vrf.name if interface.vrf else None
                    )

        groups_by_signature = {}
        mixed_groups_by_signature = {}
        for group_id, group_data in groups.items():
            # Resolve once. None is a known global VRF only when interfaces
            # establish it; an unassigned global VIP has no group VRF evidence.
            if not group_data["vrf_known"]:
                vrfs = interface_vrfs[group_id]
                if len(vrfs) > 1:
                    mixed_groups_by_signature.setdefault(
                        _group_signature(group_data)[:-1], []
                    ).append(group_id)
                if len(vrfs) != 1:
                    continue
                group_data["vrf"] = next(iter(vrfs))
                group_data["vrf_known"] = True
            groups_by_signature.setdefault(_group_signature(group_data), []).append(
                group_data
            )

        ambiguous_groups = False
        for device_name, device_state in live_state.items():
            for key, desired in device_state.items():
                candidates = groups_by_signature.get(_group_signature(desired), [])
                mixed_groups = mixed_groups_by_signature.get(
                    _group_signature(desired)[:-1], []
                )
                if len(candidates) > 1 or mixed_groups:
                    ambiguous_groups = True
                    msg = (
                        f"ambiguous NetBox VRRP groups for '{device_name}:{key}' "
                        f"in VRF {desired['vrf']!r}; matching group IDs "
                        f"{[data['object'].id for data in candidates]}, "
                        f"groups with mixed interface VRFs {mixed_groups}"
                    )
                    job.event(msg, severity="ERROR")
                    log.error(f"{self.name} - {msg}")
                    ret.errors.append(msg)
                    continue
                # Retain a shared group's name before calculating the diff;
                # joining it must not rename a group used by an unselected peer.
                if candidates and candidates[0]["object"].id in shared_group_ids:
                    desired["name"] = candidates[0]["name"]
        if ambiguous_groups:
            ret.failed = True
            return ret

        # Only selected devices contribute assignments to the diff. Other
        # groups remain available for peer discovery without becoming deletions.
        # Keep API objects separately for applying updates after approval.
        current_state = {device_name: {} for device_name in devices}
        current_objects = {}
        for assignment in sorted(assignments, key=lambda item: item.id):
            interface = interfaces_by_id.get(assignment.interface_id)
            group_data = groups.get(assignment.group.id)
            if (
                assignment.interface_type != "dcim.interface"
                or interface is None
                or group_data is None
            ):
                continue
            group = group_data["object"]

            device_name = interface.device.name
            key = f"{interface.name}:{group_data['protocol']}:{int(group.group_id)}"
            current_state[device_name][key] = {
                "interface": interface.name,
                "group_id": int(group.group_id),
                "protocol": group_data["protocol"],
                "virtual_address": group_data["virtual_address"],
                "name": group_data["name"],
                "priority": int(assignment.priority),
                "authentication_type": group_data["authentication_type"],
                "vrf": group_data["vrf"],
                "role": group_data["role"],
            }
            current_objects[(device_name, key)] = (assignment, group_data)

        current_count = sum(len(records) for records in current_state.values())
        job.event(
            f"loaded {current_count} VRRP assignment(s) in "
            f"{len(groups)} NetBox group(s)"
        )

        # Prepare API-shaped states for the three objects managed by sync.
        # A stable local group reference connects new groups, VIPs and peers
        # before NetBox IDs exist. API records stay outside the comparable data.
        object_live = {"groups": {}, "vips": {}, "assignments": {}}
        object_current = {"groups": {}, "vips": {}, "assignments": {}}
        object_records = {"groups": {}, "vips": {}, "assignments": {}}
        new_group_refs = {}
        reserved_ip_ids = set()

        # Match peers against both current groups and the desired state of
        # existing assignments. A group being repaired must remain joinable.
        group_targets = {
            signature: candidates[0]
            for signature, candidates in groups_by_signature.items()
        }
        for (device_name, key), (_, group_data) in sorted(current_objects.items()):
            desired = live_state.get(device_name, {}).get(key)
            if desired is None or group_data["vrf"] != desired["vrf"]:
                continue
            group_targets.setdefault(_group_signature(desired), group_data)

        # Only VIP creation needs VRF IDs. Existing VIP VRFs are preserved.
        vrf_names = sorted(
            {
                desired["vrf"]
                for device_state in live_state.values()
                for desired in device_state.values()
                if desired["vrf"] is not None
            }
        )
        vrf_ids = {}
        if vip_use_vrf and vrf_names:
            vrf_ids = {
                vrf.name: vrf.id
                for vrf in self.bulk_filter(
                    nb.ipam.vrfs, name=vrf_names, fields="id,name"
                )
            }

        for device_name in sorted(live_state):
            for key, desired in sorted(live_state[device_name].items()):
                assignment, group_data = current_objects.get(
                    (device_name, key), (None, None)
                )
                signature = _group_signature(desired)
                if group_data is None:
                    group_data = group_targets.get(signature)
                elif group_data["vrf"] != desired["vrf"]:
                    msg = (
                        f"existing VRRP assignment '{device_name}:{key}' has "
                        f"NetBox group VRF {group_data['vrf']!r}, "
                        f"different from live VRF {desired['vrf']!r}"
                    )
                    job.event(msg, severity="ERROR")
                    log.error(f"{self.name} - {msg}")
                    ret.errors.append(msg)
                    continue

                if group_data:
                    group_ref = str(group_data["object"].id)
                else:
                    group_ref = new_group_refs.setdefault(
                        signature, f"new:{device_name}:{key}"
                    )

                # Peers share one group and VIP plan; assignment priority is
                # prepared separately for every device/interface below.
                if group_ref not in object_live["groups"]:
                    address = desired["virtual_address"]
                    ip_record = None
                    if group_data and group_data["virtual_address"] == address:
                        ip_record = group_data["ip"]
                    if ip_record is None:
                        unassigned_ips = []
                        conflicting_ip = None
                        for candidate in ips_by_address.get(address, []):
                            if candidate.id in reserved_ip_ids:
                                continue
                            if candidate.assigned_object_id is None:
                                # A global unassigned IP can be reused; a named
                                # IP VRF must match the live interface VRF.
                                if (
                                    candidate.vrf
                                    and candidate.vrf.name != desired["vrf"]
                                ):
                                    continue
                                unassigned_ips.append(candidate)
                                continue
                            owner = None
                            if candidate.assigned_object_type == "ipam.fhrpgroup":
                                owner = groups.get(candidate.assigned_object_id)
                            # Independent groups may own the same VIP in
                            # different VRFs, including global VIP records.
                            if owner and owner["vrf_known"]:
                                if owner["vrf"] != desired["vrf"]:
                                    continue
                            conflicting_ip = candidate
                        unassigned_ips.sort(
                            key=lambda item: getattr(item.role, "value", item.role)
                            not in ("vip", "vrrp")
                        )
                        if unassigned_ips:
                            ip_record = unassigned_ips[0]
                        elif conflicting_ip is not None:
                            msg = (
                                f"matching NetBox IP '{conflicting_ip.address}' is already "
                                f"assigned to {conflicting_ip.assigned_object_type} "
                                f"{conflicting_ip.assigned_object_id}; cannot use it for "
                                f"VRRP assignment '{device_name}:{key}'"
                            )
                            job.event(msg, severity="ERROR")
                            log.error(f"{self.name} - Sync VRRP: {msg}")
                            ret.errors.append(msg)
                            continue
                    if (
                        ip_record is None
                        and vip_use_vrf
                        and desired["vrf"] is not None
                        and desired["vrf"] not in vrf_ids
                    ):
                        msg = (
                            f"vrf '{desired['vrf']}' not found in NetBox; cannot create "
                            f"VIP for VRRP assignment '{device_name}:{key}'"
                        )
                        job.event(msg, severity="ERROR")
                        log.error(f"{self.name} - {msg}")
                        ret.errors.append(msg)
                        continue

                    object_live["groups"][group_ref] = {
                        "protocol": desired["protocol"],
                        "group_id": desired["group_id"],
                        "name": desired["name"],
                        "auth_type": desired["authentication_type"],
                    }
                    if group_data:
                        object_records["groups"][group_ref] = group_data["object"]
                        object_current["groups"][group_ref] = {
                            "protocol": group_data["protocol"],
                            "group_id": group_data["group_id"],
                            "name": group_data["name"],
                            "auth_type": group_data["authentication_type"],
                        }
                    vip = {
                        "address": address,
                        "role": "vrrp",
                        "assigned_object_type": "ipam.fhrpgroup",
                        "assigned_object_id": group_ref,
                    }
                    if ip_record is None:
                        vip["status"] = "active"
                        if vip_use_vrf:
                            vip["vrf"] = vrf_ids.get(desired["vrf"])
                    else:
                        reserved_ip_ids.add(ip_record.id)
                        vip["address"] = str(ip_record.address)
                        object_records["vips"][group_ref] = ip_record
                        object_current["vips"][group_ref] = {
                            "address": str(ip_record.address),
                            "role": getattr(ip_record.role, "value", ip_record.role),
                            "assigned_object_type": ip_record.assigned_object_type,
                            "assigned_object_id": (
                                group_ref if ip_record.assigned_object_id else None
                            ),
                        }
                    object_live["vips"][group_ref] = vip

                assignment_ref = f"{device_name}:{key}"
                interface = interfaces_by_name[(device_name, desired["interface"])]
                object_live["assignments"][assignment_ref] = {
                    "group": group_ref,
                    "interface_type": "dcim.interface",
                    "interface_id": interface.id,
                    "priority": desired["priority"],
                }
                if assignment:
                    object_records["assignments"][assignment_ref] = assignment
                    object_current["assignments"][assignment_ref] = {
                        "group": group_ref,
                        "interface_type": "dcim.interface",
                        "interface_id": interface.id,
                        "priority": int(assignment.priority),
                    }

        # Resolve masks for new VIPs once, before diffing. Existing IP masks
        # stay unchanged. REST contains is scalar, so query exact ancestors in bulk.
        new_vips = {
            reference: ipaddress.ip_address(vip["address"])
            for reference, vip in object_live["vips"].items()
            if reference not in object_current["vips"]
        }
        if new_vips:
            ancestor_prefixes = set()
            for host in new_vips.values():
                for length in range(host.max_prefixlen + 1):
                    ancestor_prefixes.add(
                        str(ipaddress.ip_network(f"{host}/{length}", strict=False))
                    )
            networks = [
                ipaddress.ip_network(str(prefix.prefix), strict=False)
                for prefix in self.bulk_filter(
                    nb.ipam.prefixes,
                    prefix=sorted(ancestor_prefixes),
                    fields="id,prefix",
                )
            ]
            for reference, host in new_vips.items():
                length = max(
                    (network.prefixlen for network in networks if host in network),
                    default=host.max_prefixlen,
                )
                object_live["vips"][reference]["address"] = f"{host}/{length}"

        job.event("calculating VRRP synchronization diff")
        object_diff = self.make_diff(object_live, object_current)
        # Preserve the public per-device assignment diff; the internal object
        # diff above drives writes without rediscovering groups or VIPs.
        sync_diff = self.make_diff(live_state, current_state)
        for actions in sync_diff.values():
            actions["update"] = {
                key: actions["update"][key] for key in sorted(actions["update"])
            }

        create_count = sum(len(actions["create"]) for actions in sync_diff.values())
        update_count = sum(len(actions["update"]) for actions in sync_diff.values())
        delete_count = sum(len(actions["delete"]) for actions in sync_diff.values())
        in_sync_count = sum(len(actions["in_sync"]) for actions in sync_diff.values())
        job.event(
            "vrrp sync diff complete: "
            f"{create_count} create, {update_count} update, {delete_count} delete, "
            f"{in_sync_count} in sync"
        )
        log.info(
            f"{self.name} - Sync VRRP diff: {create_count} create, "
            f"{update_count} update, {delete_count} delete, {in_sync_count} in sync"
        )

        ret.result = {
            device_name: SyncActionSummary(in_sync=actions["in_sync"]).model_dump()
            for device_name, actions in sync_diff.items()
        }
        ret.diff = sync_diff
        if dry_run:
            job.event("dry-run requested, returning VRRP diff without changes")
            log.info(f"{self.name} - Sync VRRP: dry-run complete")
            ret.result = sync_diff
            ret.dry_run = True
            return ret

        if not sync_diff_has_changes(object_diff, ignore_deletions=True):
            if delete_count:
                job.event(
                    f"skipping {delete_count} VRRP deletion(s); deletion is not supported"
                )
            else:
                job.event("no VRRP sync changes required")
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

        # Apply the object diff in dependency order. References are resolved
        # to IDs here; group/VIP selection and validation are already complete.
        for object_type, endpoint, relation in (
            ("groups", nb.ipam.fhrp_groups, None),
            ("vips", nb.ipam.ip_addresses, "assigned_object_id"),
            ("assignments", nb.ipam.fhrp_group_assignments, "group"),
        ):
            actions = object_diff[object_type]
            for reference in actions["create"]:
                payload = dict(object_live[object_type][reference])
                if relation:
                    payload[relation] = object_records["groups"][payload[relation]].id
                object_records[object_type][reference] = endpoint.create(**payload)
                job.event(f"created VRRP record '{object_type}:{reference}'")
            for reference, changes in sorted(actions["update"].items()):
                payload = {
                    field: change["new_value"] for field, change in changes.items()
                }
                if relation in payload:
                    payload[relation] = object_records["groups"][payload[relation]].id
                object_records[object_type][reference].update(payload)
                job.event(f"updated VRRP record '{object_type}:{reference}'")

        # Keep the public result keyed by device/interface assignments. Group
        # or VIP updates also count as updates to the affected assignments.
        for device_name, actions in sync_diff.items():
            for action, result_action in (("create", "created"), ("update", "updated")):
                ret.result[device_name][result_action] = [
                    key
                    for key in actions[action]
                    if f"{device_name}:{key}" in object_live["assignments"]
                ]

        job.event("vrrp sync complete")
        if delete_count:
            job.event(
                f"skipping {delete_count} VRRP deletion(s); deletion is not supported"
            )
        create_count = sum(len(actions["created"]) for actions in ret.result.values())
        update_count = sum(len(actions["updated"]) for actions in ret.result.values())
        log.info(
            f"{self.name} - Sync VRRP complete: {create_count} created, "
            f"{update_count} updated, {in_sync_count} in sync"
        )
        return ret
