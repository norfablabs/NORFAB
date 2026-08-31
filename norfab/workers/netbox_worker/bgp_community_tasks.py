import logging
from typing import Any, Union

from norfab.core.worker import Job, Task
from norfab.models import Result

from .netbox_models import (
    BgpCommunitySyncInput,
    BgpCommunitySyncResult,
    NetboxFastApiArgs,
)
from .netbox_worker_utilities import review_sync_task_result

log = logging.getLogger(__name__)


class NetboxBgpCommunityTasks:
    @Task(
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=BgpCommunitySyncInput,
        output=BgpCommunitySyncResult,
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
    def bgp_community_sync(
        self,
        job: Job,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        with_approval: bool = False,
        timeout: int = 600,
        devices: Union[None, list] = None,
        branch: Union[None, str] = None,
        community_name_field: Union[str, bool] = "community_name",
        **kwargs: Any,
    ) -> Result:
        """Synchronize live BGP communities with NetBox.

        Route-target communities are stored as IPAM route targets. Every other
        community type is stored as a NetBox BGP plugin community. Objects are
        keyed by community value and are never deleted. When the configured
        custom field exists, it stores the sorted, comma-separated live
        community-set names observed for each value.

        Args:
            job: NorFab job object.
            instance: NetBox instance name. Uses the default instance when omitted.
            dry_run: Return the calculated diff without writing to NetBox.
            with_approval: Ask for approval before applying the prepared diff.
            timeout: Timeout in seconds for Nornir host resolution and parsing.
            devices: Explicit NetBox and Nornir device names.
            branch: NetBox Branching plugin branch name.
            community_name_field: Optional custom field for community-set names.
            **kwargs: Nornir FFun host filters.

        Returns:
            Result: Route-target and BGP community synchronization actions.
        """
        devices = list(devices or [])
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:bgp_community_sync",
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
            device.name
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

        msg = f"collecting live BGP communities from {len(devices)} device(s)"
        job.event(msg)
        log.info(f"{self.name} - {msg}")
        parse_data = self.client.run_job(
            "nornir",
            "parse_ttp",
            kwargs={"get": "bgp_communities", "FL": devices},
            workers="all",
            timeout=timeout,
        )

        # Build one live state dictionary for DeepDiff. Route targets always
        # participate; plugin communities are included only when available.
        normalised_live = {"route_targets": {}}
        if has_bgp_plugin:
            normalised_live["communities"] = {}
        result_devices = set()
        parsed_count = 0
        for worker_name, worker_data in parse_data.items():
            if worker_data.get("failed"):
                msg = f"worker '{worker_name}' failed to collect BGP communities"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - {msg}")
                ret.errors.append(msg)
                continue
            worker_result = worker_data.get("result")
            if not isinstance(worker_result, dict):
                msg = f"worker '{worker_name}' returned malformed community data"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - {msg}")
                ret.errors.append(msg)
                continue
            for device_name, records in worker_result.items():
                if device_name not in netbox_devices:
                    continue
                result_devices.add(device_name)
                if not isinstance(records, list):
                    msg = f"device '{device_name}' community result is not a list"
                    job.event(msg, severity="ERROR")
                    log.error(f"{self.name} - {msg}")
                    ret.errors.append(msg)
                    continue
                for record in records:
                    if not isinstance(record, dict) or not all(
                        isinstance(record.get(field), str) and record[field].strip()
                        for field in ("value", "type", "name")
                    ):
                        msg = f"device '{device_name}' returned malformed community record"
                        job.event(msg, severity="ERROR")
                        log.error(f"{self.name} - {msg}")
                        ret.errors.append(msg)
                        continue
                    value = record["value"].strip()
                    if record["type"].strip().lower() == "rt":
                        scope = "route_targets"
                    elif has_bgp_plugin:
                        scope = "communities"
                    else:
                        continue
                    normalised_live[scope].setdefault(value, set()).add(
                        record["name"].strip()
                    )
                    parsed_count += 1

        for device_name in devices:
            if device_name not in result_devices:
                msg = f"device '{device_name}' is missing a live community result"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - {msg}")
                ret.errors.append(msg)
        if not result_devices:
            ret.failed = True
            return ret
        msg = (
            f"parsed {parsed_count} live community record(s) from "
            f"{len(result_devices)} device(s)"
        )
        job.event(msg)
        log.info(f"{self.name} - {msg}")

        for scope in normalised_live:
            for sname, names in sorted(normalised_live[scope].items()):
                normalised_live[scope][sname] = (
                    {community_name_field: ", ".join(sorted(names))}
                    if community_name_field
                    else {}
                )

        # Fetch matching NetBox objects directly, keyed the same way as live
        # data so DeepDiff sees only create, update, and in-sync candidates.
        normalised_nb = {"route_targets": {}}
        nb_community_objects = {"route_targets": {}}

        route_target_snames = list(normalised_live["route_targets"])
        nb_communities_result = (
            self.bulk_filter(
                nb.ipam.route_targets,
                name=route_target_snames,
                fields="id,name,custom_fields",
            )
            if route_target_snames
            else []
        )
        for nb_community in nb_communities_result:
            sname = str(nb_community.name)
            normalised_nb["route_targets"][sname] = (
                {
                    community_name_field: str(
                        (nb_community.custom_fields or {}).get(community_name_field)
                        or ""
                    )
                }
                if community_name_field
                else {}
            )
            nb_community_objects["route_targets"][sname] = nb_community

        if has_bgp_plugin:
            normalised_nb["communities"] = {}
            nb_community_objects["communities"] = {}
            community_snames = list(normalised_live["communities"])
            nb_communities_result = (
                self.bulk_filter(
                    nb.plugins.bgp.community,
                    value=community_snames,
                    fields="id,value,custom_fields",
                )
                if community_snames
                else []
            )
            for nb_community in nb_communities_result:
                sname = str(nb_community.value)
                normalised_nb["communities"][sname] = (
                    {
                        community_name_field: str(
                            (nb_community.custom_fields or {}).get(community_name_field)
                            or ""
                        )
                    }
                    if community_name_field
                    else {}
                )
                nb_community_objects["communities"][sname] = nb_community

        communities_diff = self.make_diff(normalised_live, normalised_nb)
        full_diff = {}
        for scope, actions in sorted(communities_diff.items()):
            actions["delete"] = []
            full_diff[scope] = {
                "create": sorted(actions["create"]),
                "update": {
                    sname: actions["update"][sname]
                    for sname in sorted(actions["update"])
                },
                "delete": [],
                "in_sync": sorted(actions["in_sync"]),
            }

        create_count = sum(len(actions["create"]) for actions in full_diff.values())
        update_count = sum(len(actions["update"]) for actions in full_diff.values())
        in_sync_count = sum(len(actions["in_sync"]) for actions in full_diff.values())
        msg = (
            "bgp community sync diff complete: "
            f"{create_count} create, {update_count} update, "
            f"{in_sync_count} in sync"
        )
        job.event(msg)
        log.info(f"{self.name} - {msg}")

        if dry_run:
            ret.result = full_diff
            ret.dry_run = True
            return ret
        if with_approval and not review_sync_task_result(
            job, "BGP community sync", full_diff
        ):
            ret.status = "skipped"
            ret.result = full_diff
            ret.dry_run = True
            ret.messages.append("review declined; changes were not applied")
            return ret

        # Apply route targets and plugin communities separately to keep the
        # NetBox API writes explicit.
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
        create_snames = full_diff["route_targets"]["create"]
        create_payloads = []
        for sname in create_snames:
            payload = {"name": sname}
            if community_name_field:
                payload["custom_fields"] = {
                    community_name_field: normalised_live["route_targets"][sname][
                        community_name_field
                    ]
                }
            create_payloads.append(payload)
        if create_payloads:
            msg = f"creating {len(create_payloads)} route target(s) in NetBox"
            job.event(msg)
            log.info(f"{self.name} - {msg}")
            nb.ipam.route_targets.create(create_payloads)
            ret.result["route_targets"]["created"].extend(create_snames)

        update_snames = list(full_diff["route_targets"]["update"])
        update_payloads = [
            {
                "id": nb_community_objects["route_targets"][sname].id,
                "custom_fields": {
                    community_name_field: normalised_live["route_targets"][sname][
                        community_name_field
                    ]
                },
            }
            for sname in update_snames
            if community_name_field
        ]
        if update_payloads:
            msg = f"updating {len(update_payloads)} route target(s) in NetBox"
            job.event(msg)
            log.info(f"{self.name} - {msg}")
            nb.ipam.route_targets.update(update_payloads)
            ret.result["route_targets"]["updated"].extend(update_snames)

        if has_bgp_plugin:
            create_snames = full_diff["communities"]["create"]
            create_payloads = []
            for sname in create_snames:
                payload = {"value": sname}
                if community_name_field:
                    payload["custom_fields"] = {
                        community_name_field: normalised_live["communities"][sname][
                            community_name_field
                        ]
                    }
                create_payloads.append(payload)
            if create_payloads:
                msg = (
                    f"creating {len(create_payloads)} BGP community object(s) in NetBox"
                )
                job.event(msg)
                log.info(f"{self.name} - {msg}")
                nb.plugins.bgp.community.create(create_payloads)
                ret.result["communities"]["created"].extend(create_snames)

            update_snames = list(full_diff["communities"]["update"])
            update_payloads = [
                {
                    "id": nb_community_objects["communities"][sname].id,
                    "custom_fields": {
                        community_name_field: normalised_live["communities"][sname][
                            community_name_field
                        ]
                    },
                }
                for sname in update_snames
                if community_name_field
            ]
            if update_payloads:
                msg = (
                    f"updating {len(update_payloads)} BGP community object(s) in NetBox"
                )
                job.event(msg)
                log.info(f"{self.name} - {msg}")
                nb.plugins.bgp.community.update(update_payloads)
                ret.result["communities"]["updated"].extend(update_snames)

        msg = (
            f"bgp community sync complete: {create_count} created, "
            f"{update_count} updated, {in_sync_count} in sync"
        )
        job.event(msg)
        log.info(f"{self.name} - {msg}")
        return ret
