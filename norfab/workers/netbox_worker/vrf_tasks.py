import logging
from typing import Any, Union

from norfab.core.worker import Job, Task
from norfab.models import Result

from .netbox_models import NetboxFastApiArgs, SyncVrfsInput, SyncVrfsResult
from .netbox_worker_utilities import review_sync_task_result

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
        **kwargs: Any,
    ) -> Result:
        """Synchronize live VRFs and their route targets with NetBox.

        VRFs have global scope and are identified by name. Descriptions are
        synchronized, while live import/export route targets extend the
        existing NetBox associations. Route distinguishers and route policies
        returned by the parser are not stored. The selected VRF custom field
        records devices on which each VRF was observed.

        Args:
            job: NorFab job object.
            instance: NetBox instance name. Uses the default instance when omitted.
            dry_run: Return the calculated diff without writing to NetBox.
            with_approval: Ask for approval before applying the prepared diff.
            timeout: Timeout in seconds for Nornir host resolution and parsing.
            devices: Explicit NetBox and Nornir device names.
            branch: NetBox Branching plugin branch name.
            device_custom_field: VRF custom field containing associated devices.
            **kwargs: Nornir FFun host filters.

        Returns:
            Result: Global VRF synchronization actions.
        """
        devices = list(devices or [])
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:sync_vrfs",
            result={},
            resources=[instance],
            dry_run=dry_run,
            diff={},
        )

        job.event(
            f"starting VRF sync using NetBox instance '{instance}' for "
            f"{len(devices)} explicit device(s)"
        )
        log.info(f"{self.name} - Sync VRFs: instance '{instance}', dry_run={dry_run}")
        nb = self._get_pynetbox(instance, branch=branch, job=job)

        if kwargs:
            job.event("resolving devices from Nornir filters")
            devices.extend(self.get_nornir_hosts(kwargs, timeout))
        devices = sorted(set(devices))
        if not devices:
            msg = "no devices specified"
            job.event(msg, severity="ERROR")
            log.error(f"{self.name} - Sync VRFs: {msg}")
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
            log.error(f"{self.name} - Sync VRFs: {msg}")
            ret.errors.append(msg)
        devices = [name for name in devices if name in nb_devices]
        if not devices:
            ret.failed = True
            return ret
        job.event(f"validated {len(devices)} NetBox device(s)")

        custom_field = nb.extras.custom_fields.get(name=device_custom_field)
        if not custom_field:
            device_custom_field = None

        job.event(f"collecting live VRFs from {len(devices)} device(s)")
        log.info(f"{self.name} - Sync VRFs: collecting from {len(devices)} device(s)")
        parse_data = self.client.run_job(
            "nornir",
            "parse_ttp",
            kwargs={"get": "vrfs", "FL": devices},
            workers="all",
            timeout=timeout,
        )
        job.event(f"received VRF data from {len(parse_data)} Nornir worker(s)")
        observations = {}
        result_devices = set()
        failed_devices = set()
        parsed_count = 0
        for worker_name, worker_data in parse_data.items():
            if worker_data["failed"]:
                msg = f"worker '{worker_name}' failed to collect live VRF data"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - Sync VRFs: {msg}")
                ret.errors.append(msg)
                continue
            resources_failed = worker_data.get("resources_failed") or []
            if resources_failed:
                failed_devices.update(resources_failed)
                msg = (
                    f"{worker_name} failed to fetch VRF data from devices "
                    f"{', '.join(sorted(resources_failed))}"
                )
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - Sync VRFs: {msg}")
                ret.errors.append(msg)
            for device_name, records in worker_data["result"].items():
                if device_name not in nb_devices:
                    continue
                result_devices.add(device_name)
                parsed_count += len(records)
                for record in records:
                    observations.setdefault(record["name"], []).append(
                        {
                            "device": device_name,
                            "description": record["description"] or "",
                            "import_targets": record["rt_import"],
                            "export_targets": record["rt_export"],
                        }
                    )

        for device_name in devices:
            if device_name not in result_devices and device_name not in failed_devices:
                msg = f"device '{device_name}' is missing a live VRF result"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - Sync VRFs: {msg}")
                ret.errors.append(msg)
        if not result_devices:
            log.error(f"{self.name} - Sync VRFs: no usable live VRF data")
            ret.failed = True
            return ret
        job.event(
            f"parsed {parsed_count} live VRF record(s) from "
            f"{len(result_devices)} device(s)"
        )

        live_vrfs = {}
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
                "import_targets": [
                    target for record in records for target in record["import_targets"]
                ],
                "export_targets": [
                    target for record in records for target in record["export_targets"]
                ],
            }
            if device_custom_field:
                live_vrfs[vrf_name][device_custom_field] = sorted(
                    {nb_devices[record["device"]].id for record in records}
                )

        job.event("loading global NetBox VRFs")
        netbox_vrfs = {}
        netbox_objects = {}
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
            if device_custom_field:
                current[device_custom_field] = [
                    device["id"]
                    for device in (vrf.custom_fields[device_custom_field] or [])
                ]
                live_vrfs[vrf.name][device_custom_field] = sorted(
                    set(current[device_custom_field])
                    | set(live_vrfs[vrf.name][device_custom_field])
                )
            netbox_vrfs[vrf.name] = current
            netbox_objects[vrf.name] = vrf
        job.event(f"loaded {len(netbox_vrfs)} matching NetBox VRF(s)")

        job.event("calculating VRF sync diff")
        vrf_diff = self.make_diff(
            {"vrfs": live_vrfs},
            {"vrfs": netbox_vrfs},
        )["vrfs"]
        for vrf_name, changes in vrf_diff["update"].items():
            for field in ("import_targets", "export_targets"):
                if field in changes:
                    live_vrfs[vrf_name][field] = netbox_vrfs[vrf_name][field] + [
                        target
                        for target in live_vrfs[vrf_name][field]
                        if target not in netbox_vrfs[vrf_name][field]
                    ]
                    changes[field]["new_value"] = live_vrfs[vrf_name][field]
        vrf_diff["delete"] = []
        full_diff = {"global": vrf_diff}
        create_names = vrf_diff["create"]
        update = vrf_diff["update"]
        in_sync = vrf_diff["in_sync"]
        job.event(
            "vrf sync diff complete: "
            f"{len(create_names)} create, {len(update)} update, "
            f"{len(in_sync)} in sync"
        )

        if dry_run:
            job.event("dry-run requested, returning VRF sync diff without changes")
            log.info(f"{self.name} - Sync VRFs: dry-run complete")
            ret.result = full_diff
            ret.dry_run = True
            return ret
        if with_approval:
            job.event("requesting approval for the prepared VRF sync plan")
        if with_approval and not review_sync_task_result(job, "VRF sync", full_diff):
            ret.status = "skipped"
            ret.result = full_diff
            ret.dry_run = True
            ret.messages.append("review declined; changes were not applied")
            log.info(f"{self.name} - Sync VRFs: approval declined")
            return ret

        route_target_names = list(
            dict.fromkeys(
                target
                for vrf in live_vrfs.values()
                for field in ("import_targets", "export_targets")
                for target in vrf[field]
            )
        )
        route_targets = (
            {
                target.name: target
                for target in self.bulk_filter(
                    nb.ipam.route_targets,
                    name=route_target_names,
                    fields="id,name",
                )
            }
            if route_target_names
            else {}
        )
        missing_route_targets = [
            name for name in route_target_names if name not in route_targets
        ]
        if missing_route_targets:
            created_targets = nb.ipam.route_targets.create(
                [{"name": name} for name in missing_route_targets]
            )
            for target in created_targets:
                route_targets[target.name] = target
            job.event(f"created {len(created_targets)} NetBox route target(s)")

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
        for vrf_name in create_names:
            desired = live_vrfs[vrf_name]
            payload = {
                "name": vrf_name,
                "description": desired["description"],
                "import_targets": [
                    route_targets[name].id for name in desired["import_targets"]
                ],
                "export_targets": [
                    route_targets[name].id for name in desired["export_targets"]
                ],
            }
            if device_custom_field:
                payload["custom_fields"] = {
                    device_custom_field: desired[device_custom_field]
                }
            create_payloads.append(payload)
        if create_payloads:
            nb.ipam.vrfs.create(create_payloads)
            ret.result["global"]["created"].extend(create_names)
            job.event(f"created {len(create_payloads)} NetBox VRF(s)")

        update_payloads = []
        for vrf_name in sorted(update):
            desired = live_vrfs[vrf_name]
            payload = {"id": netbox_objects[vrf_name].id}
            for field in update[vrf_name]:
                if field == "description":
                    payload[field] = desired[field]
                elif field in ("import_targets", "export_targets"):
                    payload[field] = [route_targets[name].id for name in desired[field]]
                elif field == device_custom_field:
                    payload["custom_fields"] = {
                        device_custom_field: desired[device_custom_field]
                    }
            update_payloads.append(payload)
        if update_payloads:
            nb.ipam.vrfs.update(update_payloads)
            ret.result["global"]["updated"].extend(sorted(update))
            job.event(f"updated {len(update_payloads)} NetBox VRF(s)")

        job.event("vrf sync complete")
        log.info(
            f"{self.name} - Sync VRFs complete: {len(create_names)} created, "
            f"{len(update)} updated, {len(in_sync)} in sync"
        )
        return ret
