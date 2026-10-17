import ipaddress
from copy import deepcopy
from typing import Any, Union

from jinja2 import Environment, StrictUndefined, TemplateError

from norfab.core.worker import Job, Task
from norfab.models import Result

from .netbox_models import (
    NetboxFastApiArgs,
    SyncActionSummary,
    SyncVrrpInput,
    SyncVrrpResult,
)
from .netbox_worker_utilities import review_sync_task_result, sync_diff_has_changes

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
        vip_use_vrf: bool = False,
        **kwargs: Any,
    ) -> Result:
        """Update NetBox VRRP groups and virtual IPs from live device data.

        Create missing records and update group names, authentication, VIP roles,
        and interface priorities. Support the same VIP in different VRFs.
        Existing records are never deleted. Existing VIP masks and VRFs are
        preserved, and synchronized VIPs receive the role ``vrrp``.

        Args:
            job: NorFab job object.
            instance: NetBox instance. Defaults to the worker's default instance.
            dry_run: Preview changes without applying them.
            with_approval: Ask for approval before applying changes.
            timeout: Seconds allowed for device lookup and live data collection.
            devices: Device names present in both NetBox and Nornir.
            branch: Optional NetBox Branching plugin branch name.
            name_template: Jinja2 text or an ``nf://`` file for group names.
                Defaults to ``{{ device.name }}_{{ interface }}_VRRP{{ group_id }}``.
                Groups with peers outside the selection keep their names.
            vip_use_vrf: Set new VIPs to the live interface VRF. Defaults to False
                (global). Named VRFs must already exist. Existing VIPs keep their
                VRFs regardless of this setting.
            **kwargs: Nornir host filters, combined with the device names.

        Returns:
            Result: Per-device ``created``, ``updated``, ``deleted``, and
            ``in_sync`` lists. Dry runs and declined approval return a preview
            with ``create``, ``update``, ``delete``, and ``in_sync`` actions
            instead. The ``diff`` field always contains the preview.
            Errors describe collection failures, missing objects, IP ownership
            conflicts, or ambiguous group matches.
        """
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:sync_vrrp",
            result={},
            resources=[instance],
            dry_run=dry_run,
            diff={},
        )
        job.event(f"starting VRRP sync using NetBox instance '{instance}'")
        nb = self._get_pynetbox(instance, branch=branch, job=job)
        devices = sorted(
            set(devices or [])
            | set(self.get_nornir_hosts(kwargs, timeout) if kwargs else [])
        )
        if not devices:
            ret.errors.append("no devices specified")
            ret.failed = True
            return ret

        # Resolve templates and selected interfaces before collecting live data.
        name_template = name_template or VRRP_NAME_TEMPLATE
        if self.is_url(name_template):
            name_template = self.fetch_file(name_template, raise_on_fail=True).strip()
        try:
            template = VRRP_NAME_TEMPLATE_ENV.from_string(name_template)
        except TemplateError as exc:
            ret.errors.append(f"invalid VRRP group name template: {exc}")
            ret.failed = True
            return ret
        nb_devices = {
            device.name: device
            for device in self.bulk_filter(
                nb.dcim.devices,
                name=devices,
                fields="id,name,platform,role,device_type,site",
            )
        }
        for device in devices:
            if device not in nb_devices:
                ret.errors.append(f"device '{device}' not found in NetBox")
        devices = [device for device in devices if device in nb_devices]
        if not devices:
            ret.failed = True
            return ret
        interfaces = {
            interface.id: interface
            for interface in self.bulk_filter(
                nb.dcim.interfaces,
                device_id=[nb_devices[name].id for name in devices],
                fields="id,name,device,vrf",
            )
        }
        interface_ids = {
            (interface.device.name, interface.name): interface_id
            for interface_id, interface in interfaces.items()
        }

        # The getter validates record types and supplies defaults. Only translate
        # device values to NetBox values and resolve the actual NetBox interface.
        job.event("collecting live VRRP data")
        parsed = self.client.run_job(
            "nornir",
            "parse_ttp",
            workers="all",
            kwargs={"get": "vrrp", "FL": devices},
            timeout=timeout,
        )
        live = {}
        seen = set()
        for worker, data in parsed.items():
            failed = data["resources_failed"]
            ret.resources_failed = sorted(set(ret.resources_failed) | set(failed))
            if failed:
                ret.errors.append(
                    f"{worker} failed to fetch VRRP data from {', '.join(failed)}"
                )
            if data["failed"]:
                ret.errors.append(f"worker '{worker}' failed to collect live VRRP data")
                continue
            for device, records in data["result"].items():
                if device not in devices:
                    continue
                seen.add(device)
                for record in records:
                    interface = record["interface"]
                    interface_id = interface_ids.get((device, interface))
                    if interface_id is None:
                        ret.errors.append(
                            f"interface '{device}:{interface}' not found in NetBox"
                        )
                        continue
                    group_id = record["group"]
                    protocol = VRRP_PROTOCOLS[record["protocol"]]
                    vrrp_vip_identity = str(
                        ipaddress.ip_interface(record["virtual_address"]).ip
                    )
                    auth = record["authentication_type"]
                    if auth in ("text", "simple", "plain", "cleartext"):
                        auth = "plaintext"
                    vrrp_interface_identity = f"{interface}:{protocol}:{group_id}"
                    live[(device, vrrp_interface_identity)] = dict(
                        record,
                        protocol=protocol,
                        virtual_address=vrrp_vip_identity,
                        authentication_type=auth,
                        interface_id=interface_id,
                    )
        for device in set(devices) - seen - set(ret.resources_failed):
            ret.errors.append(f"device '{device}' is missing a live VRRP result")
        peers = {}
        # Sort peers so a shared group's name always uses the same first peer.
        for member, data in sorted(live.items()):
            vrrp_peer_identity = (
                data["protocol"],
                data["group"],
                data["virtual_address"],
                data["vrf"],
            )
            peers.setdefault(vrrp_peer_identity, []).append(member)

        # Load selected memberships and all matching VIP owners. These two
        # sources discover relevant groups, including unselected peer devices.
        job.event("loading NetBox VRRP groups, VIPs, and memberships")
        selected_assignments = self.bulk_filter(
            nb.ipam.fhrp_group_assignments,
            device=devices,
            fields="id,group,interface_type,interface_id,priority",
        )
        addresses = sorted({data["virtual_address"] for data in live.values()})
        matching_ips = (
            self.bulk_filter(
                nb.ipam.ip_addresses,
                address=addresses,
                fields="id,address,role,vrf,assigned_object_type,assigned_object_id",
            )
            if addresses
            else []
        )
        group_ids = {item.group.id for item in selected_assignments}
        group_ids.update(
            ip.assigned_object_id
            for ip in matching_ips
            if ip.assigned_object_type == "ipam.fhrpgroup"
            and ip.assigned_object_id is not None
        )
        groups = {}
        if group_ids:
            for group in self.bulk_filter(
                nb.ipam.fhrp_groups,
                id=sorted(group_ids),
                fields="id,name,protocol,group_id,auth_type",
            ):
                if group.protocol not in VRRP_PROTOCOLS.values():
                    continue
                groups[f"group:{group.id}"] = dict(
                    id=group.id,
                    data=dict(
                        name=group.name,
                        protocol=group.protocol,
                        group_id=group.group_id,
                        auth_type=group.auth_type,
                    ),
                    vrfs=set(),
                    shared=False,
                    vips={},
                )
        owned_ips = (
            self.bulk_filter(
                nb.ipam.ip_addresses,
                assigned_object_type="ipam.fhrpgroup",
                assigned_object_id=[group["id"] for group in groups.values()],
                fields="id,address,role,vrf,assigned_object_type,assigned_object_id",
            )
            if groups
            else []
        )
        memberships = (
            self.bulk_filter(
                nb.ipam.fhrp_group_assignments,
                group_id=[group["id"] for group in groups.values()],
                fields="id,group,interface_type,interface_id",
            )
            if groups
            else []
        )
        # Keep API fields ready for comparison, with the update ID alongside.
        assignments = {device: {} for device in devices}
        for item in selected_assignments:
            vrrp_group_identity = f"group:{item.group.id}"
            if (
                item.interface_type != "dcim.interface"
                or vrrp_group_identity not in groups
            ):
                continue
            interface = interfaces[item.interface_id]
            fields = groups[vrrp_group_identity]["data"]
            vrrp_interface_identity = (
                f"{interface.name}:{fields['protocol']}:{fields['group_id']}"
            )
            assignments[interface.device.name][vrrp_interface_identity] = dict(
                id=item.id,
                data=dict(
                    group=vrrp_group_identity,
                    interface_type="dcim.interface",
                    interface_id=item.interface_id,
                    priority=item.priority,
                ),
            )

        # Normalize IPs once. Group VIPs and address lookups share the same data,
        # including whether an unassigned IP has already been reserved by a plan.
        ips, candidates = {}, {}
        for ip in {ip.id: ip for ip in [*matching_ips, *owned_ips]}.values():
            vrrp_vip_identity = str(ipaddress.ip_interface(str(ip.address)).ip)
            owner = (
                f"group:{ip.assigned_object_id}"
                if ip.assigned_object_type == "ipam.fhrpgroup"
                else ip.assigned_object_id
            )
            ip_data = dict(
                id=ip.id,
                vrf=ip.vrf.name if ip.vrf else None,
                reserved=False,
                data=dict(
                    address=str(ip.address),
                    role=ip.role.value if ip.role else None,
                    assigned_object_type=ip.assigned_object_type,
                    assigned_object_id=owner,
                ),
            )
            ips.setdefault(vrrp_vip_identity, []).append(ip_data)
            if owner in groups:
                group = groups[owner]
                group["vips"][vrrp_vip_identity] = ip_data
                if ip_data["vrf"] is not None:
                    group["vrfs"].add(ip_data["vrf"])
                fields = group["data"]
                candidates.setdefault(
                    (fields["protocol"], fields["group_id"], vrrp_vip_identity), set()
                ).add(owner)
        for matches in ips.values():
            matches.sort(
                key=lambda ip: (ip["data"]["role"] not in ("vip", "vrrp"), ip["id"])
            )

        # Named VIP VRFs define group context. Otherwise infer it from every
        # assigned interface, including peers outside the selected devices.
        for group in groups.values():
            group["infer_vrf"] = not group["vrfs"]
        external_ids = set()
        for item in memberships:
            group = groups[f"group:{item.group.id}"]
            if (
                item.interface_type != "dcim.interface"
                or item.interface_id not in interfaces
            ):
                group["shared"] = True
                if item.interface_type == "dcim.interface" and group["infer_vrf"]:
                    external_ids.add(item.interface_id)
        if external_ids:
            interfaces.update(
                {
                    interface.id: interface
                    for interface in self.bulk_filter(
                        nb.dcim.interfaces,
                        id=sorted(external_ids),
                        fields="id,name,device,vrf",
                    )
                }
            )
        for item in memberships:
            group = groups[f"group:{item.group.id}"]
            if item.interface_type == "dcim.interface" and group["infer_vrf"]:
                interface = interfaces[item.interface_id]
                group["vrfs"].add(interface.vrf.name if interface.vrf else None)
        vrf_names = sorted(
            {data["vrf"] for data in live.values() if data["vrf"] is not None}
        )
        existing_vrfs = (
            {
                vrf.name
                for vrf in self.bulk_filter(nb.ipam.vrfs, name=vrf_names, fields="name")
            }
            if vip_use_vrf and vrf_names
            else set()
        )
        group_live, vip_live = {}, {}
        assignment_live = {device: {} for device in devices}
        new_vips = {}

        # Resolve each live peer bucket once. Membership anchors support VIP
        # and authentication changes; new peers discover groups by VIP/context.
        for vrrp_peer_identity, members in peers.items():
            protocol, group_id, vrrp_vip_identity, vrf = vrrp_peer_identity
            desired = live[members[0]]
            anchors = {
                assignments[device][vrrp_interface_identity]["data"]["group"]
                for device, vrrp_interface_identity in members
                if vrrp_interface_identity in assignments[device]
            }
            possible = candidates.get((protocol, group_id, vrrp_vip_identity), set())
            mixed = {
                identity for identity in possible if len(groups[identity]["vrfs"]) > 1
            }
            matches = {
                identity for identity in possible if groups[identity]["vrfs"] == {vrf}
            }
            found = anchors | matches
            if len(found) > 1 or mixed:
                ret.errors.append(
                    f"ambiguous NetBox VRRP groups for {members!r}; "
                    f"matching group IDs {sorted(groups[identity]['id'] for identity in found)}, "
                    f"groups with mixed interface VRFs {sorted(groups[identity]['id'] for identity in mixed)}"
                )
                ret.failed = True
                return ret
            vrrp_group_identity = next(
                iter(found), f"new:{members[0][0]}:{members[0][1]}"
            )
            group = groups.get(vrrp_group_identity)
            if group is not None and group["vrfs"] != {vrf}:
                ret.errors.append(
                    f"existing VRRP assignment '{members[0][0]}:{members[0][1]}' "
                    f"has NetBox group interface/VIP VRFs {group['vrfs']!r}, different from live VRF {vrf!r}"
                )
                continue
            if any(
                live[member]["authentication_type"] != desired["authentication_type"]
                for member in members
            ):
                ret.errors.append(
                    f"inconsistent live VRRP authentication for {members!r}"
                )
                ret.failed = True
                return ret
            ip_record = group["vips"].get(vrrp_vip_identity) if group else None
            conflict = None
            if ip_record is None:
                for ip in ips.get(vrrp_vip_identity, []):
                    if ip["reserved"]:
                        continue
                    owner = ip["data"]["assigned_object_id"]
                    if owner is None:
                        if ip["vrf"] is None or ip["vrf"] == vrf:
                            ip_record = ip
                            break
                        continue
                    if (
                        owner in groups
                        and len(groups[owner]["vrfs"]) == 1
                        and groups[owner]["vrfs"] != {vrf}
                    ):
                        continue
                    conflict = ip
                if ip_record is None and conflict is not None:
                    owner = conflict["data"]["assigned_object_id"]
                    if conflict["data"]["assigned_object_type"] == "ipam.fhrpgroup":
                        owner = owner.removeprefix("group:")
                    ret.errors.append(
                        f"matching NetBox IP '{conflict['data']['address']}' is already assigned to "
                        f"{conflict['data']['assigned_object_type']} {owner}; "
                        f"cannot use it for VRRP assignment '{members[0][0]}:{members[0][1]}'"
                    )
                    continue
            if (
                ip_record is None
                and vip_use_vrf
                and vrf is not None
                and vrf not in existing_vrfs
            ):
                ret.errors.append(
                    f"vrf '{vrf}' not found in NetBox; cannot create VIP for "
                    f"VRRP assignment '{members[0][0]}:{members[0][1]}'"
                )
                continue
            try:
                name = (
                    group["data"]["name"]
                    if group is not None and group["shared"]
                    else template.render(
                        device=nb_devices[members[0][0]],
                        interface=desired["interface"],
                        protocol=protocol,
                        group_id=group_id,
                        virtual_address=vrrp_vip_identity,
                    ).strip()
                )
                if (group is None or not group["shared"]) and (
                    not name or len(name) > 100
                ):
                    raise ValueError("group name must contain 1 to 100 characters")
            except (TemplateError, ValueError) as exc:
                ret.errors.append(f"failed to render VRRP group name: {exc}")
                ret.failed = True
                return ret
            fields = dict(
                protocol=protocol,
                group_id=group_id,
                name=name,
                auth_type=desired["authentication_type"],
            )
            if (
                vrrp_group_identity in group_live
                and group_live[vrrp_group_identity] != fields
            ):
                ret.errors.append(
                    f"inconsistent live VRRP state for group '{vrrp_group_identity}'"
                )
                ret.failed = True
                return ret
            group_live[vrrp_group_identity] = fields
            if group is None:
                group = groups[vrrp_group_identity] = dict(
                    id=None, data={}, vrfs={vrf}, shared=False, vips={}
                )
            vip = dict(
                address=vrrp_vip_identity,
                role="vrrp",
                assigned_object_type="ipam.fhrpgroup",
                assigned_object_id=vrrp_group_identity,
            )
            if ip_record is None:
                new_vips.setdefault(ipaddress.ip_address(vrrp_vip_identity), []).append(
                    vip
                )
                vip["status"] = "active"
                if vip_use_vrf:
                    vip["vrf"] = {"name": vrf} if vrf is not None else None
            else:
                ip_record["reserved"] = True
                vip["address"] = ip_record["data"]["address"]
                group["vips"][vrrp_vip_identity] = ip_record
            vip_live.setdefault(vrrp_group_identity, {})[vrrp_vip_identity] = vip
            for device, vrrp_interface_identity in members:
                data = live[(device, vrrp_interface_identity)]
                assignment_live[device][vrrp_interface_identity] = dict(
                    group=vrrp_group_identity,
                    interface_type="dcim.interface",
                    interface_id=data["interface_id"],
                    priority=data["priority"],
                )

        # Comparable fields are already prepared. Extra current records become
        # deletion candidates, which this additive sync never applies.
        assignment_current = {
            device: {identity: item["data"] for identity, item in records.items()}
            for device, records in assignments.items()
        }
        group_current = {
            identity: group["data"]
            for identity, group in groups.items()
            if group["id"] is not None
        }
        vip_current = {
            identity: {address: ip["data"] for address, ip in group["vips"].items()}
            for identity, group in groups.items()
        }

        # Resolve masks once per new address and share them across VRF groups.
        if new_vips:
            ancestors = {
                str(ipaddress.ip_network(f"{host}/{length}", strict=False))
                for host in new_vips
                for length in range(host.max_prefixlen + 1)
            }
            networks = [
                ipaddress.ip_network(str(prefix.prefix), strict=False)
                for prefix in self.bulk_filter(
                    nb.ipam.prefixes, prefix=sorted(ancestors), fields="id,prefix"
                )
            ]
            for host, vips in new_vips.items():
                length = max(
                    (network.prefixlen for network in networks if host in network),
                    default=host.max_prefixlen,
                )
                for vip in vips:
                    vip["address"] = f"{host}/{length}"

        # Three comparisons, each shaped like the API objects it controls.
        # Local group references connect all three plans before new IDs exist.
        group_diff = self.make_diff({"groups": group_live}, {"groups": group_current})[
            "groups"
        ]
        vip_diff = self.make_diff(vip_live, vip_current)
        assignment_diff = self.make_diff(assignment_live, assignment_current)
        # Add group/VIP changes to each affected membership's public preview.
        # Copy the assignment diff so the original still drives only its own writes.
        preview = deepcopy(assignment_diff)
        for device, actions in preview.items():
            for vrrp_interface_identity, assignment in assignment_live[device].items():
                if vrrp_interface_identity in actions["create"]:
                    continue
                vrrp_group_identity = assignment["group"]
                address = live[(device, vrrp_interface_identity)]["virtual_address"]
                changes = dict(group_diff["update"].get(vrrp_group_identity, {}))
                if "auth_type" in changes:
                    changes["authentication_type"] = changes.pop("auth_type")
                vip_changes = vip_diff[vrrp_group_identity]["update"].get(address, {})
                if (
                    address in vip_diff[vrrp_group_identity]["create"]
                    or "assigned_object_id" in vip_changes
                ):
                    old_addresses = [
                        address
                        for address, ip in vip_current[vrrp_group_identity].items()
                        if ip["assigned_object_id"] == vrrp_group_identity
                    ]
                    changes["virtual_address"] = {
                        "old_value": (
                            old_addresses[0] if len(old_addresses) == 1 else None
                        ),
                        "new_value": address,
                    }
                if "role" in vip_changes:
                    changes["role"] = vip_changes["role"]
                if changes:
                    actions["update"].setdefault(vrrp_interface_identity, {}).update(
                        changes
                    )
                    if vrrp_interface_identity in actions["in_sync"]:
                        actions["in_sync"].remove(vrrp_interface_identity)
            actions["update"] = dict(sorted(actions["update"].items()))
        ret.diff = preview
        if dry_run:
            ret.result = preview
            return ret
        ret.result = {
            device: SyncActionSummary(
                created=actions["create"],
                updated=list(actions["update"]),
                in_sync=actions["in_sync"],
            ).model_dump()
            for device, actions in preview.items()
        }
        if not sync_diff_has_changes(preview, ignore_deletions=True):
            job.event("no VRRP changes required; deletion candidates are retained")
            return ret
        if with_approval and not review_sync_task_result(job, "VRRP sync", preview):
            ret.status = "skipped"
            ret.dry_run = True
            ret.result = preview
            ret.messages.append("review declined; changes were not applied")
            return ret

        # Apply in dependency order. Generic object relations require IDs;
        # ordinary VRF relations use the name already supplied by the getter.
        job.event("applying VRRP group changes")
        for vrrp_group_identity in group_diff["create"]:
            groups[vrrp_group_identity]["id"] = nb.ipam.fhrp_groups.create(
                **group_live[vrrp_group_identity]
            ).id
        updates = [
            dict(
                id=groups[vrrp_group_identity]["id"],
                **{field: change["new_value"] for field, change in changes.items()},
            )
            for vrrp_group_identity, changes in group_diff["update"].items()
        ]
        if updates:
            nb.ipam.fhrp_groups.update(updates)
        # VIPs and memberships have the same create/update workflow. Only their
        # endpoint, grouping, and group-relation field differ.
        job.event("applying VRRP VIP and interface assignment changes")
        for endpoint, desired, diff, records, relation in (
            (
                nb.ipam.ip_addresses,
                vip_live,
                vip_diff,
                {identity: group["vips"] for identity, group in groups.items()},
                "assigned_object_id",
            ),
            (
                nb.ipam.fhrp_group_assignments,
                assignment_live,
                assignment_diff,
                assignments,
                "group",
            ),
        ):
            creates, updates = [], []
            for scope, actions in diff.items():
                creates.extend(
                    dict(desired[scope][identity]) for identity in actions["create"]
                )
                updates.extend(
                    dict(
                        id=records[scope][identity]["id"],
                        **{
                            field: change["new_value"]
                            for field, change in changes.items()
                        },
                    )
                    for identity, changes in actions["update"].items()
                )
            for fields in [*creates, *updates]:
                if relation in fields:
                    fields[relation] = groups[fields[relation]]["id"]
            if creates:
                endpoint.create(creates)
            if updates:
                endpoint.update(updates)

        job.event("vrrp sync complete; deletion candidates are retained")
        return ret
