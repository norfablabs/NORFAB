import logging
from typing import Any, Union

from pynetbox import RequestError

from norfab.core.worker import Job, Task
from norfab.models import Result

from .netbox_models import (
    CreateBgpAsnInput,
    CreateBgpAsnResult,
    NetboxFastApiArgs,
    SyncBgpAsnInput,
    SyncBgpAsnResult,
)
from .netbox_worker_utilities import (
    apply_description_policy,
    merge_array_values,
    merge_resolved_custom_fields,
    review_sync_task_result,
)

log = logging.getLogger(__name__)


class NetboxBgpAsnTasks:
    @Task(
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=CreateBgpAsnInput,
        output=CreateBgpAsnResult,
        mcp={
            "annotations": {
                "title": "Create BGP ASN",
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def create_asn(
        self,
        job: Job,
        asn_range: Union[None, str] = None,
        asn: Union[None, int] = None,
        rir: Union[None, str] = None,
        description: Union[None, str] = None,
        tenant: Union[None, str] = None,
        tags: Union[None, list] = None,
        custom_fields: Union[None, dict] = None,
        sites: Union[None, list[str]] = None,
        role: Union[None, str] = None,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        branch: Union[None, str] = None,
    ) -> Result:
        """Create, update, or allocate one ASN in NetBox.

        An explicit ASN is matched globally by number. Without one, range searches
        use role and sites when both are supplied, matching an ASN in the range
        with that role assigned to any requested site. Otherwise, it matches
        by description within the range. If the selected lookup finds no match,
        it allocates the first available number. Without either lookup, repeated
        range calls can allocate different ASNs. A non-empty sites
        list adds to the ASN's site assignments; an empty or omitted list
        leaves them alone. Tags and array custom fields are also additive.
        Dry-run reports the selected number without writing relationships.

        Args:
            job: Current NorFab job for events and branch provisioning.
            asn_range: Existing range name for next-available allocation.
            asn: Explicit ASN number; omit to allocate from ``asn_range``.
            rir: Existing RIR name required whenever an explicit ASN is
                supplied without a range, including updates.
            description: Description used to reuse allocations within a range.
            tenant: Optional tenant name.
            tags: Optional tag names to add without removing existing tags.
            custom_fields: Optional NetBox custom-field values. Object and
                multiobject fields accept related object names or IDs; names
                must identify exactly one object. Arrays merged with existing values;
                empty arrays preserve existing arrays. Null and scalar values
                replace existing values.
            sites: Optional site names to add to the ASN's assignments. With role,
                also used to reuse a range allocation assigned to any of these sites.
            role: Optional IPAM role name. With sites, also used for range lookup
                before description matching.
            instance: NetBox instance name, or the worker default when omitted.
            dry_run: Select an ASN without creating or updating it.
            branch: Optional NetBox Branching plugin branch name.

        Returns:
            Result: Selected ASN, description, and action. Dry-run actions
            are ``create`` or ``update``; applied actions are ``created`` or
            ``updated``.

        Raises:
            ValueError: The range, RIR, site, or related custom-field object is
                missing; a related name is ambiguous; more than one ASN matches
                the description or role/sites; or the range has no free ASNs.
        """
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:create_asn",
            result={},
            resources=[instance],
            dry_run=dry_run,
        )
        nb = self._get_pynetbox(instance, branch=branch, job=job)
        nb_range = nb.ipam.asn_ranges.get(name=asn_range) if asn_range else None
        if asn_range and not nb_range:
            raise ValueError(f"ASN range '{asn_range}' not found in NetBox")

        matches = []
        if asn is not None:
            existing = nb.ipam.asns.get(asn=asn)
            matches = [existing] if existing else []
        elif nb_range and role and sites:
            matches = self.bulk_filter(
                nb.ipam.asns,
                asn__gte=nb_range.start,
                asn__lte=nb_range.end,
                role=nb.ipam.roles.get(name=role).slug,
                site=[
                    site.slug for site in self.bulk_filter(nb.dcim.sites, name=sites)
                ],
            )
        elif nb_range and description:
            matches = self.bulk_filter(
                nb.ipam.asns,
                description=description,
                asn__gte=nb_range.start,
                asn__lte=nb_range.end,
            )
        if len(matches) > 1:
            raise ValueError(
                f"ASN lookup matched more than one ASN in range '{asn_range}' (description={description!r}, role={role!r}, sites={sites!r})"
            )

        nb_asn = matches[0] if matches else None
        if not nb_asn and asn is None:
            available = list(nb_range.available_asns.list())
            if not available:
                raise ValueError(f"ASN range '{asn_range}' has no available ASNs")
            asn = int(
                available[0]["asn"]
                if isinstance(available[0], dict)
                else getattr(available[0], "asn", available[0])
            )
        if dry_run:
            ret.result = {
                "asn": int(nb_asn.asn) if nb_asn else asn,
                "description": description,
                "status": "update" if nb_asn else "create",
            }
            return ret

        if not nb_asn and nb_range:
            nb_asn = nb.ipam.asns.create({"asn": asn, "rir": nb_range.rir.id})
        elif not nb_asn:
            rir_object = nb.ipam.rirs.get(name=rir)
            if not rir_object:
                raise ValueError(f"RIR '{rir}' not found in NetBox")
            nb_asn = nb.ipam.asns.create({"asn": asn, "rir": rir_object.id})

        changed = False
        if description is not None and nb_asn.description != description:
            nb_asn.description = description
            changed = True
        if tenant is not None and str(nb_asn.tenant) != tenant:
            nb_asn.tenant = {"name": tenant}
            changed = True
        if role is not None and str(nb_asn.role) != role:
            nb_asn.role = {"name": role}
            changed = True
        site_names = list(dict.fromkeys(sites or []))
        if site_names:
            nb_sites = self.bulk_filter(nb.dcim.sites, name=site_names)
            site_ids = {item.name: item.id for item in nb_sites}
            if len(site_ids) != len(site_names):
                raise ValueError(
                    f"ASN sites not found: {set(site_names) - set(site_ids)}"
                )
            current_ids = [site.id for site in nb_asn.sites]
            merged_ids = merge_array_values(
                current_ids, [site_ids[name] for name in site_names]
            )
            if merged_ids != current_ids:
                nb_asn.sites = merged_ids
                changed = True
        if tags:
            current_names = [tag.name for tag in nb_asn.tags]
            merged_names = merge_array_values(current_names, tags)
            if merged_names != current_names:
                nb_asn.tags = [{"name": name} for name in merged_names]
                changed = True
        if custom_fields is not None:
            reference_fields = self.bulk_filter(
                nb.extras.custom_fields,
                object_type="ipam.asn",
                type=["object", "multiobject"],
            )
            object_fields = [
                field for field in reference_fields if field.type.value == "object"
            ]
            multiobject_fields = [
                field for field in reference_fields if field.type.value == "multiobject"
            ]
            current_fields, merged_fields = merge_resolved_custom_fields(
                self,
                nb,
                nb_asn,
                custom_fields,
                object_fields,
                multiobject_fields,
            )
            if merged_fields != current_fields:
                nb_asn.custom_fields = merged_fields
                changed = True
        if changed:
            nb_asn.save()

        ret.status = "updated" if matches else "created"
        ret.result = {
            "asn": int(nb_asn.asn),
            "description": nb_asn.description,
            "status": ret.status,
        }
        job.event(f"{ret.status} ASN {nb_asn.asn}")
        return ret

    @Task(
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=SyncBgpAsnInput,
        output=SyncBgpAsnResult,
        mcp={
            "annotations": {
                "title": "Sync BGP ASNs",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def sync_bgp_asn(
        self,
        job: Job,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        with_approval: bool = False,
        timeout: int = 600,
        devices: Union[None, list] = None,
        branch: Union[None, str] = None,
        rir: Union[None, str] = None,
        device_custom_field: str = "devices",
        ignore_asn_by_range: Union[None, list] = None,
        preserve_description: bool = True,
        batch_size: int = 1000,
        **kwargs: Any,
    ) -> Result:
        """Synchronize globally unique live BGP ASNs with NetBox.

        Existing ASNs are updated without requiring an RIR. Missing ASNs are
        created only when ``rir`` identifies an existing NetBox RIR. The
        selected ASN custom field and NetBox BGP sessions provide device
        association evidence. Existing ASN updates apply only to devices that
        report the ASN as local. Without association evidence sources for a
        device, the task only compares ASN existence.
        ASNs, memberships, and peerings are never deleted by this task.

        Args:
            job: NorFab job object.
            instance: NetBox instance name. Uses the default instance when omitted.
            dry_run: Return the calculated diff without writing to NetBox.
            with_approval: Ask for approval before applying the prepared diff.
            timeout: Timeout in seconds for Nornir host resolution and parsing.
            devices: Explicit NetBox and Nornir device names.
            branch: NetBox Branching plugin branch name.
            rir: NetBox RIR name required when creating missing ASNs.
            device_custom_field: ASN custom field containing associated devices.
            ignore_asn_by_range: ASN values or numerical ranges to ignore.
            preserve_description: Keep existing NetBox ASN descriptions unchanged
                by default. False applies the selected peer-group label.
            batch_size: Maximum number of ASN records per write request.
            **kwargs: Nornir FFun host filters.

        Returns:
            Result: Per-device ASN synchronization actions.
        """
        devices = list(devices or [])
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:sync_bgp_asn",
            result={},
            resources=[instance],
            dry_run=dry_run,
            diff={},
        )

        job.event(
            f"starting BGP ASN sync using NetBox instance '{instance}' for "
            f"{len(devices)} explicit device(s)"
        )
        log.info(
            f"{self.name} - Sync BGP ASNs: instance '{instance}', dry_run={dry_run}"
        )
        nb = self._get_pynetbox(instance, branch=branch, job=job)

        # Validate creation prerequisites before collecting reconciliation data.
        rir_obj = None
        if rir is not None:
            rir_matches = self.bulk_filter(nb.ipam.rirs, name=rir, fields="id,name")
            if len(rir_matches) != 1:
                msg = f"RIR '{rir}' must match exactly one NetBox RIR"
                job.event(msg, severity="ERROR")
                ret.errors.append(msg)
                ret.failed = True
                return ret
            rir_obj = rir_matches[0]

        if kwargs:
            job.event("resolving devices from Nornir filters")
            devices.extend(self.get_nornir_hosts(kwargs, timeout))
        devices = sorted(set(devices))
        if not devices:
            msg = "no devices specified"
            job.event(msg, severity="ERROR")
            log.error(f"{self.name} - Sync BGP ASNs: {msg}")
            ret.errors.append(msg)
            ret.failed = True
            return ret

        # Keep ignore ranges as bounds, including reversed ranges and comma lists.
        ignored_ranges = []
        for expression in ignore_asn_by_range or []:
            for token in expression.split(","):
                first, separator, last = token.strip().partition("-")
                try:
                    start, end = int(first), int(last if separator else first)
                except ValueError:
                    msg = f"invalid ignored ASN range '{token}'"
                    job.event(msg, severity="ERROR")
                    ret.errors.append(msg)
                    ret.failed = True
                    return ret
                ignored_ranges.append((min(start, end), max(start, end)))

        # Collect ASN numbers, labels, and the parser's local ownership marker.
        job.event(f"collecting live BGP ASNs from {len(devices)} device(s)")
        parse_data = self.client.run_job(
            "nornir",
            "parse_ttp",
            kwargs={"get": "bgp_asn", "FL": devices},
            workers="all",
            timeout=timeout,
        )
        live_asn = {}
        for worker_data in (parse_data or {}).values():
            ret.messages.extend(worker_data.get("messages") or [])
            ret.resources_unsupported.extend(
                worker_data.get("resources_unsupported") or []
            )
            ret.resources_failed.extend(worker_data.get("resources_failed") or [])
            if worker_data.get("failed"):
                continue
            for device, records in (worker_data.get("result") or {}).items():
                if device not in devices or not isinstance(records, list):
                    continue
                device_asns = {}
                for record in records:
                    asn = int(record["asn"])
                    if any(start <= asn <= end for start, end in ignored_ranges):
                        continue
                    label, local = device_asns.get(asn, ("", False))
                    device_asns[asn] = (
                        label or record.get("description") or "",
                        local or record.get("local_asn") is True,
                    )
                collected = live_asn.setdefault(device, {})
                for asn, (label, local) in device_asns.items():
                    previous_label, previous_local = collected.get(asn, ("", False))
                    collected[asn] = (previous_label or label, previous_local or local)

        ret.resources_unsupported = sorted(
            set(ret.resources_unsupported) - live_asn.keys()
        )
        ret.resources_failed = sorted(set(ret.resources_failed) - live_asn.keys())
        if ret.resources_unsupported:
            devices = sorted(set(devices) - set(ret.resources_unsupported))
            if not devices:
                ret.failed = True
                return ret

        # Resolve the selected devices and discard live data for missing devices.
        nb_devices = {
            device.name: device
            for device in self.bulk_filter(
                nb.dcim.devices,
                name=devices,
                fields="id,name",
            )
        }
        for device_name in devices:
            if device_name not in nb_devices:
                msg = f"device '{device_name}' not found in NetBox"
                job.event(msg, severity="ERROR")
                ret.errors.append(msg)
                ret.resources_failed.append(device_name)
        live_asn = {
            device: asns for device, asns in live_asn.items() if device in nb_devices
        }

        for device in devices:
            if device in nb_devices and device not in live_asn:
                ret.resources_failed.append(device)
                msg = f"device '{device}' is missing a live BGP ASN result"
                job.event(msg, severity="ERROR")
                ret.errors.append(msg)
        ret.resources_failed = sorted(set(ret.resources_failed))
        if not live_asn:
            ret.failed = True
            return ret

        # Read the configured ASN field, the shared ASN catalog, and NetBox sessions.
        if device_custom_field:
            definitions = self.bulk_filter(
                nb.extras.custom_fields,
                name=device_custom_field,
                object_type="ipam.asn",
                type="multiobject",
                fields="name,related_object_type",
            )
            if not any(
                field.related_object_type == "dcim.device" for field in definitions
            ):
                device_custom_field = None

        asn_devices = {}
        for device in sorted(live_asn):
            for asn in sorted(live_asn[device]):
                asn_devices.setdefault(asn, []).append(device)
        netbox_objects = {
            int(record.asn): record
            for record in (
                self.bulk_filter(
                    nb.ipam.asns,
                    asn=sorted(asn_devices),
                    fields="id,asn,description,custom_fields",
                )
                if asn_devices
                else []
            )
        }

        # Index both ASN references on each session by its NetBox device.
        session_members = {}
        devices_with_sessions = set()
        if asn_devices:
            devices_by_id = {nb_devices[device].id: device for device in live_asn}
            try:
                sessions = self.bulk_filter(
                    nb.plugins.bgp.session,
                    device_id=list(devices_by_id),
                    fields="device,local_as,remote_as",
                )
            except RequestError as exc:
                job.event(
                    f"netbox BGP sessions are unavailable: {exc}", severity="WARNING"
                )
            else:
                for session in sessions:
                    if session.device is None or session.device.id not in devices_by_id:
                        continue
                    for reference in (session.local_as, session.remote_as):
                        if reference is not None:
                            devices_with_sessions.add(session.device.id)
                            session_members.setdefault(int(reference.asn), set()).add(
                                session.device.id
                            )

        # Build comparable ASN records for each device.
        live = {device: {} for device in live_asn}
        netbox_asn = {device: {} for device in live_asn}
        create_descriptions = {}
        stored_members = {}
        for asn, observers in asn_devices.items():
            record = netbox_objects.get(asn)
            local_observers = [
                device for device in observers if live_asn[device][asn][1]
            ]
            description_sources = observers
            if record is not None:
                description_sources = [
                    device
                    for device in local_observers
                    if device_custom_field
                    or nb_devices[device].id in devices_with_sessions
                ]
            source = next(
                (device for device in description_sources if live_asn[device][asn][0]),
                description_sources[0] if description_sources else None,
            )
            description = live_asn[source][asn][0] if source is not None else ""
            members = set()
            if record is None:
                create_descriptions[asn] = description
            elif device_custom_field:
                members = {
                    int(
                        value["id"]
                        if isinstance(value, dict)
                        else getattr(value, "id", value)
                    )
                    for value in (record.custom_fields or {}).get(device_custom_field)
                    or []
                }
                stored_members[asn] = members

            for device in observers:
                live[device][asn] = {}
                if record is not None:
                    netbox_asn[device][asn] = {}
                device_id = nb_devices[device].id
                if device in local_observers and (
                    device_custom_field or device_id in devices_with_sessions
                ):
                    associated = (
                        device_id in members
                        or device_id in session_members.get(asn, ())
                    )
                    field = device_custom_field or "device_associated"
                    live[device][asn][field] = True
                    if record is not None:
                        netbox_asn[device][asn][field] = associated
            if record is not None and source is not None:
                live[source][asn]["description"] = apply_description_policy(
                    description, record.description, preserve_description
                )
                netbox_asn[source][asn]["description"] = record.description or ""

        device_diffs = self.make_diff(live, netbox_asn)

        # Publish the same per-device diff for dry runs, approval, and applied results.
        for device, diff in device_diffs.items():
            ret.diff[device] = {
                **diff,
                "update": {
                    str(asn): changes for asn, changes in diff["update"].items()
                },
            }
            ret.result[device] = {
                "created": [],
                "updated": [],
                "deleted": [],
                "in_sync": diff["in_sync"],
            }

        if dry_run:
            ret.result = ret.diff
            return ret
        if ret.failed:
            return ret
        # Merge device-level actions into one payload per ASN.
        creates = {}
        updates = {}
        for device, diff in sorted(device_diffs.items()):
            for asn in diff["create"]:
                creates.setdefault(asn, []).append(device)
            for asn, changes in diff["update"].items():
                if "description" not in changes and device_custom_field not in changes:
                    continue
                payload, affected = updates.setdefault(
                    asn, ({"id": netbox_objects[asn].id}, [])
                )
                if "description" in changes:
                    payload["description"] = changes["description"]["new_value"]
                if device_custom_field in changes:
                    if "custom_fields" not in payload:
                        payload["custom_fields"] = {
                            device_custom_field: stored_members[asn].copy()
                        }
                    payload["custom_fields"][device_custom_field].add(
                        nb_devices[device].id
                    )
                affected.append(device)

        # Prepare create payloads only when a valid RIR is available.
        create_items = []
        if rir_obj:
            for asn, devices in sorted(creates.items()):
                payload = {
                    "asn": asn,
                    "rir": rir_obj.id,
                    "description": create_descriptions[asn],
                }
                if device_custom_field:
                    payload["custom_fields"] = {
                        device_custom_field: sorted(
                            nb_devices[device].id
                            for device in devices
                            if live[device][asn].get(device_custom_field)
                        )
                    }
                create_items.append((asn, payload, devices))
        elif creates:
            msg = "cannot create missing ASNs: no RIR provided, use 'rir' parameter"
            job.event(msg, severity="WARNING")
            log.warning(f"{self.name} - {msg}")
            ret.errors.append(msg)

        update_items = []
        for asn, (payload, affected) in sorted(updates.items()):
            if "custom_fields" in payload:
                fields = payload["custom_fields"]
                fields[device_custom_field] = sorted(fields[device_custom_field])
            update_items.append((asn, payload, affected))

        if not create_items and not update_items:
            job.event("no BGP ASN writes planned")
            return ret
        job.event(
            f"planned {len(create_items)} ASN creates and {len(update_items)} updates"
        )
        if with_approval and not review_sync_task_result(job, "BGP ASN sync", ret.diff):
            ret.status = "skipped"
            ret.result = ret.diff
            ret.dry_run = True
            ret.messages.append("review declined; changes were not applied")
            return ret

        # Create missing ASNs in batches and record each successful create.
        total_batches = (len(create_items) + batch_size - 1) // batch_size
        for offset in range(0, len(create_items), batch_size):
            batch = create_items[offset : offset + batch_size]
            batch_number = offset // batch_size + 1
            msg = f"creating ASN batch {batch_number}/{total_batches} ({len(batch)} ASN(s))"
            job.event(msg)
            log.info(msg)
            try:
                nb.ipam.asns.create([payload for _, payload, _ in batch])
            except Exception as exc:
                msg = f"failed ASN create batch {batch_number}/{total_batches}: {exc}"
                job.event(msg, severity="ERROR")
                ret.errors.append(msg)
                ret.failed = True
                # Include the failed batch and writes skipped after the failure.
                ret.resources_failed = sorted(
                    set(ret.resources_failed)
                    | {
                        device
                        for _, _, devices in create_items[offset:] + update_items
                        for device in devices
                    }
                )
                return ret
            for asn, _, devices in batch:
                for device in devices:
                    ret.result[device]["created"].append(asn)

        # Update existing ASNs in batches and credit only devices that needed the update.
        total_batches = (len(update_items) + batch_size - 1) // batch_size
        for offset in range(0, len(update_items), batch_size):
            batch = update_items[offset : offset + batch_size]
            batch_number = offset // batch_size + 1
            msg = f"updating ASN batch {batch_number}/{total_batches} ({len(batch)} ASN(s))"
            job.event(msg)
            log.info(msg)
            try:
                nb.ipam.asns.update([payload for _, payload, _ in batch])
            except Exception as exc:
                msg = f"failed ASN update batch {batch_number}/{total_batches}: {exc}"
                job.event(msg, severity="ERROR")
                ret.errors.append(msg)
                ret.failed = True
                ret.resources_failed = sorted(
                    set(ret.resources_failed)
                    | {
                        device
                        for _, _, devices in update_items[offset:]
                        for device in devices
                    }
                )
                return ret
            for asn, _, devices in batch:
                for device in devices:
                    ret.result[device]["updated"].append(asn)

        job.event("bgp asn sync complete")
        return ret
