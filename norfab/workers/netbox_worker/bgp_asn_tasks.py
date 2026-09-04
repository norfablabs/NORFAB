import logging
from typing import Any, Union

from norfab.core.worker import Job, Task
from norfab.models import Result
from norfab.utils.text import expand_alphanumeric_range

from .netbox_models import NetboxFastApiArgs, SyncBgpAsnInput, SyncBgpAsnResult
from .netbox_worker_utilities import apply_description_policy, review_sync_task_result

log = logging.getLogger(__name__)


class NetboxBgpAsnTasks:
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
        **kwargs: Any,
    ) -> Result:
        """Synchronize globally unique live BGP ASNs with NetBox.

        Existing ASNs are updated without requiring an RIR. Missing ASNs are
        created only when ``rir`` identifies an existing NetBox RIR. The
        selected ASN custom field records devices on which each ASN was
        observed. ASNs and device associations are never deleted.

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
            preserve_description: Keep existing NetBox ASN descriptions unchanged.
            **kwargs: Nornir FFun host filters.

        Returns:
            Result: Global ASN synchronization actions.
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

        nb_devices = {
            device.name: device
            for device in self.bulk_filter(
                nb.dcim.devices,
                name=devices,
                fields="id,name",
            )
        }
        for device_name in [name for name in devices if name not in nb_devices]:
            msg = f"device '{device_name}' not found in NetBox"
            job.event(msg, severity="ERROR")
            log.error(f"{self.name} - Sync BGP ASNs: {msg}")
            ret.errors.append(msg)
        devices = [name for name in devices if name in nb_devices]
        if not devices:
            ret.failed = True
            return ret
        job.event(f"validated {len(devices)} NetBox device(s)")

        if not nb.extras.custom_fields.get(name=device_custom_field):
            device_custom_field = None

        ignored_asns = {
            int(asn)
            for asn_range in ignore_asn_by_range or []
            for asn in expand_alphanumeric_range(f"[{asn_range}]")
        }

        job.event(f"collecting live BGP ASNs from {len(devices)} device(s)")
        parse_data = self.client.run_job(
            "nornir",
            "parse_ttp",
            kwargs={"get": "bgp_asn", "FL": devices},
            workers="all",
            timeout=timeout,
        )
        observations = {}
        result_devices = set()
        failed_devices = set()
        parsed_count = 0
        for worker_name, worker_data in parse_data.items():
            if worker_data["failed"]:
                msg = f"worker '{worker_name}' failed to collect live BGP ASN data"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - Sync BGP ASNs: {msg}")
                ret.errors.append(msg)
                continue
            resources_failed = worker_data.get("resources_failed") or []
            if resources_failed:
                failed_devices.update(resources_failed)
                msg = (
                    f"{worker_name} failed to fetch BGP ASN data from devices "
                    f"{', '.join(sorted(resources_failed))}"
                )
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - Sync BGP ASNs: {msg}")
                ret.errors.append(msg)
            for device_name, records in worker_data["result"].items():
                if device_name not in nb_devices:
                    continue
                result_devices.add(device_name)
                for record in records:
                    if record["asn"] in ignored_asns:
                        continue
                    observations.setdefault(record["asn"], []).append(
                        {
                            "device": device_name,
                            "description": record["description"] or "",
                            "local_asn": record.get("local_asn", True),
                        }
                    )
                    parsed_count += 1

        for device_name in devices:
            if device_name not in result_devices and device_name not in failed_devices:
                msg = f"device '{device_name}' is missing a live BGP ASN result"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - Sync BGP ASNs: {msg}")
                ret.errors.append(msg)
        if not result_devices:
            ret.failed = True
            return ret
        job.event(
            f"parsed {parsed_count} live BGP ASN record(s) from "
            f"{len(result_devices)} device(s)"
        )

        live_asns = {}
        for asn in sorted(observations):
            records = sorted(observations[asn], key=lambda item: item["device"])
            live_asns[asn] = {
                "description": next(
                    (
                        record["description"]
                        for record in records
                        if record["description"]
                    ),
                    "",
                )
            }
            if device_custom_field:
                live_asns[asn][device_custom_field] = sorted(
                    {
                        nb_devices[record["device"]].id
                        for record in records
                        if record["local_asn"] is True
                    }
                )

        netbox_asns = {}
        netbox_objects = {}
        asn_numbers = list(live_asns)
        netbox_asn_records = (
            self.bulk_filter(
                nb.ipam.asns,
                asn=asn_numbers,
                fields="id,asn,description,custom_fields",
            )
            if asn_numbers
            else []
        )
        for asn in netbox_asn_records:
            current = {"description": asn.description}
            live_asns[asn.asn]["description"] = apply_description_policy(
                live_asns[asn.asn]["description"],
                current["description"],
                preserve_description,
            )
            if device_custom_field:
                current[device_custom_field] = [
                    device["id"]
                    for device in (asn.custom_fields[device_custom_field] or [])
                ]
                live_asns[asn.asn][device_custom_field] = sorted(
                    set(current[device_custom_field])
                    | set(live_asns[asn.asn][device_custom_field])
                )
            netbox_asns[asn.asn] = current
            netbox_objects[asn.asn] = asn

        asn_diff = self.make_diff(
            {"asns": live_asns},
            {"asns": netbox_asns},
        )["asns"]
        asn_diff["delete"] = []
        create_numbers = asn_diff["create"]
        update = asn_diff["update"]
        in_sync = asn_diff["in_sync"]
        full_diff = {
            "global": {
                "create": create_numbers,
                "update": {str(asn): changes for asn, changes in update.items()},
                "delete": [],
                "in_sync": in_sync,
            }
        }
        job.event(
            "bgp asn sync diff complete: "
            f"{len(create_numbers)} create, {len(update)} update, "
            f"{len(in_sync)} in sync"
        )

        if dry_run:
            ret.result = full_diff
            ret.dry_run = True
            return ret
        if with_approval and not review_sync_task_result(
            job, "BGP ASN sync", full_diff
        ):
            ret.status = "skipped"
            ret.result = full_diff
            ret.dry_run = True
            ret.messages.append("review declined; changes were not applied")
            return ret

        rir_obj = nb.ipam.rirs.get(name=rir) if rir else None
        if rir and not rir_obj:
            msg = f"RIR '{rir}' not found in NetBox, ASN creation will be skipped"
            job.event(msg, severity="WARNING")
            log.warning(f"{self.name} - {msg}")
            ret.errors.append(msg)

        ret.diff = full_diff
        ret.result = {
            "global": {
                "created": [],
                "updated": [],
                "deleted": [],
                "in_sync": in_sync,
            }
        }
        create_payloads = []
        if rir_obj:
            for asn in create_numbers:
                desired = live_asns[asn]
                payload = {
                    "asn": asn,
                    "rir": rir_obj.id,
                    "description": desired["description"],
                }
                if device_custom_field:
                    payload["custom_fields"] = {
                        device_custom_field: desired[device_custom_field]
                    }
                create_payloads.append(payload)
        elif create_numbers and not rir:
            msg = "cannot create missing ASNs: no RIR provided, use 'rir' parameter"
            job.event(msg, severity="WARNING")
            log.warning(f"{self.name} - {msg}")
            ret.errors.append(msg)
        if create_payloads:
            nb.ipam.asns.create(create_payloads)
            ret.result["global"]["created"].extend(create_numbers)
            job.event(f"created {len(create_payloads)} NetBox ASN(s)")

        update_payloads = []
        for asn in sorted(update):
            desired = live_asns[asn]
            payload = {"id": netbox_objects[asn].id}
            for field in update[asn]:
                if field == "description":
                    payload[field] = desired[field]
                elif field == device_custom_field:
                    payload["custom_fields"] = {
                        device_custom_field: desired[device_custom_field]
                    }
            update_payloads.append(payload)
        if update_payloads:
            nb.ipam.asns.update(update_payloads)
            ret.result["global"]["updated"].extend(sorted(update))
            job.event(f"updated {len(update_payloads)} NetBox ASN(s)")

        job.event("bgp asn sync complete")
        log.info(
            f"{self.name} - Sync BGP ASNs complete: "
            f"{len(ret.result['global']['created'])} created, "
            f"{len(update)} updated, {len(in_sync)} in sync"
        )
        return ret
