import copy
import logging
from typing import Any, Union

from norfab.core.exceptions import UnsupportedServiceError
from norfab.core.worker import Job, Task
from norfab.models import Result
from norfab.utils.text import slugify

from .netbox_models import (
    CheckDeviceSyncInput,
    CheckDeviceSyncResult,
    GetDevicesInput,
    GetDevicesResult,
    NetboxFastApiArgs,
    SyncAllInput,
    SyncAllResult,
    SyncDeviceFactsInput,
    SyncDeviceFactsResult,
    SyncDeviceInventoryInput,
    SyncDeviceInventoryResult,
)

log = logging.getLogger(__name__)


def normalise_inventory_serial(value: Any) -> str:
    """Normalise serial values and treat BUILTIN as unusable."""
    serial = str(value or "").strip()
    if serial.upper() == "BUILTIN":
        return ""
    return serial


def is_chassis_inventory_record(record: dict) -> bool:
    """Return True when a parser inventory record represents chassis hardware."""
    slot = str(record.get("slot") or record.get("name") or "").strip().lower()
    role = str(
        record.get("inventory_type") or record.get("type") or record.get("role") or ""
    ).strip().lower()

    return role == "chassis" or slot == "chassis" or slot.startswith("chassis ")


def is_real_module_identity(module_name: Any) -> bool:
    """Return True when the parser value can identify a real module type."""
    module_name = str(module_name or "").strip()
    return bool(module_name) and module_name.upper() not in {"N/A", "NA", "NONE"}


def flatten_inventory_records(data: Any) -> list[dict]:
    """Flatten common TTP result shapes into a list of inventory dictionaries."""
    records = []

    if isinstance(data, dict):
        has_inventory_fields = False
        for key in ("slot", "module", "serial", "description"):
            if key in data:
                has_inventory_fields = True
                break
        if has_inventory_fields:
            return [data]
        for value in data.values():
            records.extend(flatten_inventory_records(value))
    elif isinstance(data, list):
        for item in data:
            records.extend(flatten_inventory_records(item))

    return records


def get_device_manufacturer_name(nb: object, device: object) -> tuple[str, str]:
    """Resolve device type manufacturer name and slug for module type fallback."""
    device_type = device.device_type
    manufacturer = None
    if hasattr(device_type, "manufacturer"):
        manufacturer = device_type.manufacturer
    manufacturer_name = ""
    manufacturer_slug = ""
    if manufacturer:
        manufacturer_name = manufacturer.name
        manufacturer_slug = manufacturer.slug

    if manufacturer_name:
        return manufacturer_name, manufacturer_slug or slugify(manufacturer_name)

    if device_type.id:
        device_type = nb.dcim.device_types.get(id=device_type.id)
        manufacturer = None
        if device_type:
            manufacturer = device_type.manufacturer
        manufacturer_name = ""
        manufacturer_slug = ""
        if manufacturer:
            manufacturer_name = manufacturer.name
            manufacturer_slug = manufacturer.slug

    return manufacturer_name, manufacturer_slug or slugify(manufacturer_name or "")


def normalise_live_inventory_records(
    records: list[dict],
    fallback_manufacturer: str,
) -> tuple[dict, list[dict], set[str], str]:
    """Build desired inventory state for one device from parser records."""
    live_state = {}
    ignored = []
    skipped_slots = set()
    chassis_candidates = []

    for record in records:
        slot = str(record.get("slot") or record.get("name") or "").strip()
        module_name = str(
            record.get("module")
            or record.get("model")
            or record.get("part_number")
            or record.get("pid")
            or ""
        ).strip()
        serial = normalise_inventory_serial(
            record.get("serial") or record.get("serial_number") or record.get("sn")
        )
        description = str(record.get("description") or record.get("descr") or "")
        manufacturer = str(record.get("manufacturer") or fallback_manufacturer or "")

        if is_chassis_inventory_record(record):
            if serial:
                chassis_candidates.append({"slot": slot, "serial": serial})
            else:
                ignored.append(
                    {
                        "slot": slot or "chassis",
                        "reason": "chassis serial is empty",
                        "record": record,
                    }
                )
            continue

        if not slot:
            ignored.append(
                {
                    "slot": slot,
                    "reason": "slot is empty",
                    "record": record,
                }
            )
            continue

        if not is_real_module_identity(module_name):
            ignored.append(
                {
                    "slot": slot,
                    "reason": "module identity is empty or N/A",
                    "record": record,
                }
            )
            skipped_slots.add(slot)
            continue

        if not serial:
            ignored.append(
                {
                    "slot": slot,
                    "reason": "serial is empty or BUILTIN",
                    "record": record,
                }
            )
            skipped_slots.add(slot)
            continue

        live_state[slot] = {
            "slot": slot,
            "inventory_type": "module",
            "manufacturer": manufacturer,
            "module_type": module_name,
            "part_number": str(record.get("part_number") or module_name),
            "serial": serial,
            "description": description,
            "status": str(record.get("status") or "active"),
        }

    chassis_serials = {candidate["serial"] for candidate in chassis_candidates}
    if len(chassis_serials) > 1:
        return live_state, ignored, skipped_slots, "multiple chassis records found"
    if chassis_candidates:
        live_state["chassis"] = {
            "slot": "chassis",
            "inventory_type": "chassis",
            "serial": chassis_candidates[0]["serial"],
        }

    return live_state, ignored, skipped_slots, ""


def normalise_netbox_module(module: object, nb: object) -> dict:
    """Build comparable state for a NetBox installed module."""
    module_type = module.module_type
    module_type_id = None
    manufacturer = None
    manufacturer_name = ""
    part_number = ""
    model = ""
    if module_type:
        module_type_id = module_type.id
        if hasattr(module_type, "manufacturer"):
            manufacturer = module_type.manufacturer
        if manufacturer:
            manufacturer_name = manufacturer.name
        part_number = module_type.part_number
        model = module_type.model

    if module_type_id and (not manufacturer_name or part_number is None or not model):
        module_type = nb.dcim.module_types.get(id=module_type_id)
        manufacturer = None
        manufacturer_name = ""
        part_number = ""
        model = ""
        if module_type:
            manufacturer = module_type.manufacturer
            if manufacturer:
                manufacturer_name = manufacturer.name
            part_number = module_type.part_number
            model = module_type.model

    slot = str(module.module_bay.name or "").strip()

    return {
        "slot": slot,
        "inventory_type": "module",
        "manufacturer": str(manufacturer_name or ""),
        "module_type": str(model or ""),
        "part_number": str(part_number or model or ""),
        "serial": str(module.serial or ""),
        "description": str(module.description or ""),
        "status": str(module.status.value or ""),
    }


def find_module_type_id(
    nb: object,
    manufacturer_name: str,
    manufacturer_slug: str,
    model: str,
    part_number: str,
    lookup_cache: dict,
) -> Union[int, None]:
    """Resolve a NetBox module type ID using manufacturer/model/part number."""
    cache_key = (manufacturer_slug or manufacturer_name or "", model, part_number)
    if cache_key in lookup_cache:
        return lookup_cache[cache_key]

    candidates = []
    filter_attempts = []
    if manufacturer_slug and model:
        filter_attempts.append({"manufacturer": manufacturer_slug, "model": model})
    if manufacturer_slug and part_number:
        filter_attempts.append(
            {"manufacturer": manufacturer_slug, "part_number": part_number}
        )

    for filters in filter_attempts:
        try:
            candidates = list(nb.dcim.module_types.filter(**filters))
        except Exception:
            candidates = []
        if candidates:
            break

    if not candidates and model:
        candidates = list(nb.dcim.module_types.filter(model=model))
        if len(candidates) != 1:
            candidates = []

    module_type_id = None
    if candidates:
        module_type_id = int(candidates[0].id)
    lookup_cache[cache_key] = module_type_id
    return module_type_id


def get_or_create_module_type_id(
    nb: object,
    job: Job,
    ret: Result,
    device_name: str,
    slot: str,
    desired: dict,
    create_module_types: bool,
    lookup_cache: dict,
) -> tuple[Union[int, None], Union[str, None]]:
    """Resolve or create the module type needed for a module create/update."""
    manufacturer_name = desired.get("manufacturer") or ""
    manufacturer_slug = slugify(manufacturer_name)
    model = desired.get("module_type") or desired.get("part_number")
    part_number = desired.get("part_number") or model
    module_type_id = find_module_type_id(
        nb,
        manufacturer_name=manufacturer_name,
        manufacturer_slug=manufacturer_slug,
        model=model,
        part_number=part_number,
        lookup_cache=lookup_cache,
    )
    if module_type_id:
        return module_type_id, None

    module_type_label = f"{manufacturer_name} {model}".strip()
    if not create_module_types:
        msg = f"{device_name}:{slot} - module type '{module_type_label}' not found"
        ret.errors.append(msg)
        log.error(msg)
        job.event(msg, severity="ERROR")
        return None, module_type_label

    manufacturer = None
    if manufacturer_slug:
        manufacturer = nb.dcim.manufacturers.get(slug=manufacturer_slug)
    if not manufacturer and manufacturer_name:
        manufacturer = nb.dcim.manufacturers.get(name=manufacturer_name)
    if not manufacturer:
        msg = (
            f"{device_name}:{slot} - manufacturer '{manufacturer_name}' not found, "
            f"cannot create module type '{model}'"
        )
        ret.errors.append(msg)
        log.error(msg)
        job.event(msg, severity="ERROR")
        return None, module_type_label

    created = nb.dcim.module_types.create(
        manufacturer=int(manufacturer.id),
        model=model,
        part_number=part_number,
    )
    module_type_id = int(created.id)
    lookup_cache[(manufacturer_slug, model, part_number)] = module_type_id
    job.event(f"created module type '{module_type_label}'")
    log.info(f"Created module type '{module_type_label}'")
    return module_type_id, module_type_label


class NetboxDevicesTasks:

    @Task(
        input=GetDevicesInput,
        output=GetDevicesResult,
        fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()},
        mcp={
            "annotations": {
                "title": "Get Devices",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def get_devices(
        self,
        job: Job,
        filters: Union[None, list] = None,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        devices: Union[None, list] = None,
        cache: Union[None, bool, str] = None,
    ) -> Result:
        """
        Retrieve device data from Netbox REST API using Pynetbox.

        Args:
            job: NorFab Job object
            filters: list of filter dicts applied to ``dcim/devices/`` endpoint, e.g. ``[{"site": "NYC", "status": "active"}]``
            instance: Netbox instance name, uses default if omitted
            dry_run: if True returns filter params without making REST calls
            devices: list of device names to fetch, merged into filters as ``{"name": devices}``
            cache: ``True`` - use cache if up to date; ``False`` - skip cache;
                ``"refresh"`` - fetch and overwrite cache; ``"force"`` - use cache without staleness check

        Returns:
            dict keyed by device name with fields: last_updated, custom_field_data, tags, device_type,
            role, config_context, tenant, platform, serial, asset_tag, site, location, rack, status,
            primary_ip4, primary_ip6, airflow, position, id
        """
        instance = instance or self.default_instance
        ret = Result(task=f"{self.name}:get_devices", result={}, resources=[instance])
        cache = self.cache_use if cache is None else cache
        filters = list(filters) if filters else []
        devices = devices or []
        devices_to_fetch = []
        sites_data = {}
        nb = self._get_pynetbox(instance)

        # merge named devices into filters as a name filter
        if devices:
            filters.append({"name": devices})

        # return dry run result
        if dry_run is True:
            ret.result["get_devices_dry_run"] = {"filters": filters}
            ret.dry_run = True
            return ret

        job.event(
            f"retrieving device data for {len(devices)} device(s) from instance '{instance}'"
            if devices
            else f"retrieving device data from instance '{instance}' using {len(filters)} filter(s)"
        )

        filters_to_fetch = list(filters)

        if cache == True or cache == "force":
            job.event("checking cache for up-to-date device data")
            self.cache.expire()  # remove expired items from cache
            # retrieve last_updated data from Netbox for all filters using REST
            for filter_item in filters:
                result = nb.dcim.devices.filter(
                    **filter_item,
                    fields="name,last_updated",
                )
                for device in result:
                    device_name = device.name
                    last_updated = device.last_updated
                    # try to retrieve device data from cache
                    device_cache_key = f"get_devices::{device_name}"
                    # check if cache is up to date and use it if so
                    if device_cache_key in self.cache and (
                        self.cache[device_cache_key].get("last_updated") == last_updated
                        or cache == "force"
                    ):
                        ret.result[device_name] = self.cache[device_cache_key]
                        job.event(f"serving '{device_name}' from cache")
                    # cache old or no cache, fetch device data
                    else:
                        devices_to_fetch.append(device_name)
                        job.event(
                            f"'{device_name}' cache miss or stale, fetching fresh data"
                        )

            # only fetch devices missing from or stale in cache
            filters_to_fetch = [{"name": devices_to_fetch}] if devices_to_fetch else []
        # ignore cache, fetch data from Netbox
        elif cache == False or cache == "refresh":
            pass  # filters_to_fetch already set to all filters above

        # fetch full device data from Netbox
        if filters_to_fetch:
            job.event(f"fetching device data from NetBox instance '{instance}'")
            nb = self._get_pynetbox(instance)
            all_devices_raw = {}

            for filter_item in filters_to_fetch:
                for device in nb.dcim.devices.filter(**filter_item):
                    all_devices_raw.setdefault(device.name, device)

            job.event(f"retrieved {len(all_devices_raw)} device(s) from NetBox")

            # process devices data
            for device_name, device in all_devices_raw.items():
                if device_name not in ret.result:
                    device_data = dict(device)
                    if device.site.name not in sites_data:
                        sites_data[device.site.name] = dict(
                            nb.dcim.sites.get(id=device.site.id)
                        )
                    device_data["site"] = sites_data[device.site.name]
                    # cache device data
                    if cache != False:
                        cache_key = f"get_devices::{device_name}"
                        self.cache.set(cache_key, device_data, expire=self.cache_ttl)
                        log.info(
                            f"{self.name} - Cached device data for '{device_name}'"
                        )
                        job.event(f"cached device data for '{device_name}'")
                    # add device data to return result
                    ret.result[device_name] = device_data

        log.info(f"{self.name} - get_devices returning {len(ret.result)} device(s)")
        job.event(f"fetched {len(ret.result)} device(s)")

        return ret

    @Task(
        input=SyncDeviceFactsInput,
        output=SyncDeviceFactsResult,
        fastapi={"methods": ["PATCH"], "schema": NetboxFastApiArgs.model_json_schema()},
        mcp={
            "annotations": {
                "title": "Sync Device Facts",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def sync_device_facts(
        self,
        job: Job,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        datasource: str = "nornir",
        timeout: int = 60,
        devices: Union[None, list] = None,
        batch_size: int = 10,
        branch: str = None,
        **kwargs: Any,
    ) -> Result:
        """
        Updates device facts in NetBox, this task updates this device attributes:

        - serial number

        Args:
            job: NorFab Job object containing relevant metadata
            instance (str, optional): The NetBox instance to use.
            dry_run (bool, optional): If True, no changes will be made to NetBox.
            datasource (str, optional): The data source to use. Supported datasources:

                - **nornir** - uses Nornir Service parse task to retrieve devices' data
                    using NAPALM `get_facts` getter

            timeout (int, optional): The timeout for the job execution. Defaults to 60.
            devices (list, optional): The list of devices to update.
            batch_size (int, optional): The number of devices to process in each batch.
            branch (str, optional): Branch name to use, need to have branching plugin installed,
                automatically creates branch if it does not exist in Netbox.
            **kwargs: Additional keyword arguments to pass to the datasource job.

        Returns:
            dict: A dictionary containing the results of the update operation.

        Raises:
            Exception: If a device does not exist in NetBox.
            UnsupportedServiceError: If the specified datasource is not supported.
        """
        devices = devices or []
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:sync_device_facts",
            resources=[instance],
            dry_run=dry_run,
            diff={},
            result={},
        )
        nb = self._get_pynetbox(instance, branch=branch)
        kwargs["add_details"] = True

        if datasource == "nornir":
            # source hosts list from Nornir
            if kwargs:
                job.event("resolving devices from Nornir filters")
                nornir_hosts = self.get_nornir_hosts(kwargs, timeout)
                devices.extend(nornir_hosts)
                devices = list(set(devices))
                job.event(
                    f"resolved {len(nornir_hosts)} device(s) from Nornir filters, "
                    f"{len(devices)} total device(s) selected"
                )
                job.event(
                    f"syncing device facts for {len(devices)} devices, dry_run={dry_run}"
                )
                log.info(
                    f"{self.name} - sync_device_facts starting for {len(devices)} device(s): {', '.join(devices)}"
                )
            # fetch devices data from Netbox
            job.event(f"fetching current device data from NetBox instance '{instance}'")
            nb_devices = self.get_devices(
                job=job,
                instance=instance,
                devices=copy.copy(devices),
                cache="refresh",
            ).result
            # remove devices that does not exist in Netbox
            for d in list(devices):
                if d not in nb_devices:
                    msg = f"'{d}' device does not exist in Netbox"
                    ret.errors.append(msg)
                    log.error(msg)
                    job.event(msg, severity="ERROR")
                    devices.remove(d)
            if not devices:
                job.event(
                    "no valid NetBox devices remain after validation", severity="ERROR"
                )
                ret.failed = True
                return ret
            # iterate over devices in batches
            for i in range(0, len(devices), batch_size):
                kwargs["FL"] = devices[i : i + batch_size]
                kwargs["getters"] = "get_facts"
                job.event(f"retrieving facts for devices {', '.join(kwargs['FL'])}")
                data = self.client.run_job(
                    "nornir",
                    "parse_napalm",
                    kwargs=kwargs,
                    workers="all",
                    timeout=timeout,
                )

                # Collect devices to update in bulk
                devices_to_update = []
                job.event(f"processing facts for {len(kwargs['FL'])} device(s)")

                for worker, results in data.items():
                    if results["failed"]:
                        msg = f"{worker} get_facts failed, errors: {'; '.join(results['errors'])}"
                        ret.errors.append(msg)
                        log.error(msg)
                        job.event(msg, severity="ERROR")
                        continue
                    for host, host_data in results["result"].items():
                        if host_data["napalm_get"]["failed"]:
                            msg = f"{host} facts update failed: '{host_data['napalm_get']['exception']}'"
                            ret.errors.append(msg)
                            log.error(msg)
                            job.event(msg, severity="ERROR")
                            continue

                        nb_device = nb_devices[host]

                        facts = host_data["napalm_get"]["result"]["get_facts"]
                        desired_state = {
                            "serial": facts["serial_number"],
                        }
                        current_state = {
                            "serial": nb_device["serial"],
                        }
                        # Compare and get fields that need updating
                        updates, diff = self.compare_netbox_object_state(
                            desired_state=desired_state,
                            current_state=current_state,
                        )

                        # Only update if there are changes
                        if updates:
                            updates["id"] = int(nb_device["id"])
                            devices_to_update.append(updates)
                            ret.diff[host] = diff
                            log.debug(f"{self.name} - '{host}' facts differ: {diff}")

                        ret.result[host] = {
                            (
                                "sync_device_facts_dry_run"
                                if dry_run
                                else "sync_device_facts"
                            ): (updates if updates else "Device facts in sync")
                        }
                        if branch is not None:
                            ret.result[host]["branch"] = branch

                # Perform bulk update
                if devices_to_update and not dry_run:
                    try:
                        nb.dcim.devices.update(devices_to_update)
                        job.event(
                            f"bulk updated facts for {len(devices_to_update)} device(s)"
                        )
                        log.info(
                            f"{self.name} - Bulk updated facts for {len(devices_to_update)} device(s)"
                        )
                    except Exception as e:
                        msg = f"Bulk update failed: {e}"
                        ret.errors.append(msg)
                        log.error(f"{self.name} - {msg}")
                elif devices_to_update and dry_run:
                    job.event(
                        f"dry-run, would update facts for {len(devices_to_update)} device(s)"
                    )
                else:
                    job.event("all device facts are already in sync, no updates needed")
        else:
            raise UnsupportedServiceError(
                f"'{datasource}' datasource service not supported"
            )

        job.event("device facts sync complete")
        return ret

    @Task(
        input=SyncDeviceInventoryInput,
        output=SyncDeviceInventoryResult,
        fastapi={"methods": ["PATCH"], "schema": NetboxFastApiArgs.model_json_schema()},
        mcp={
            "annotations": {
                "title": "Sync Device Inventory",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def sync_device_inventory(
        self,
        job: Job,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        timeout: int = 60,
        devices: Union[None, list] = None,
        branch: str = None,
        process_deletions: bool = False,
        create_module_types: bool = False,
        create_module_bays: bool = False,
        message: Union[None, str] = None,
        **kwargs: Any,
    ) -> Result:
        """Synchronize chassis serial and installed module inventory into NetBox.

        Live inventory is collected from the Nornir service using
        ``parse_ttp(get="inventory")``. The chassis record updates the NetBox
        device serial. All non-chassis records with a usable module identity
        and serial are reconciled as NetBox modules installed in device-level
        module bays.

        Module deletions are disabled by default. Missing module bays and
        module types are reported unless explicitly created with
        ``create_module_bays`` or ``create_module_types``.

        Args:
            job: NorFab job object used for progress events.
            instance: NetBox instance name to target. Defaults to the worker's
                default NetBox instance.
            dry_run: Return the planned inventory diff without writing changes
                to NetBox.
            timeout: Timeout in seconds for the Nornir ``parse_ttp`` job.
            devices: NetBox device names to synchronize.
            branch: NetBox Branching plugin branch name.
            process_deletions: Delete stale NetBox modules when they are absent
                from live inventory.
            create_module_types: Create missing NetBox module types from live
                module model data.
            create_module_bays: Create missing NetBox module bays from live
                inventory slot names.
            message: NetBox changelog message to attach to write operations.
            **kwargs: Additional Nornir filters and execution options forwarded
                to ``parse_ttp``.

        Returns:
            Result object containing the normalized diff, per-device sync
            outcome, and any partial errors.
        """
        devices = devices or []
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:sync_device_inventory",
            result={},
            resources=[instance],
            dry_run=dry_run,
            diff={},
        )
        nb = self._get_pynetbox(instance, branch=branch)

        if message:
            job.event("setting NetBox changelog message for inventory sync")
            nb.http_session.headers["X-Changelog-Message"] = message

        if kwargs:
            job.event("resolving devices from Nornir filters")
            nornir_hosts = self.get_nornir_hosts(kwargs, timeout)
            for host in nornir_hosts:
                if host not in devices:
                    devices.append(host)
            job.event(
                f"resolved {len(nornir_hosts)} device(s) from Nornir filters, "
                f"{len(devices)} total device(s) selected"
            )

        if not devices:
            msg = "no devices specified"
            job.event(msg, severity="ERROR")
            ret.errors.append(msg)
            ret.failed = True
            return ret

        devices = sorted(set(devices))
        log.info(
            f"{self.name} - Sync device inventory for {len(devices)} device(s) in '{instance}', dry_run={dry_run}"
        )
        job.event(
            f"syncing device inventory for {len(devices)} device(s), dry_run={dry_run}"
        )

        # Fetch and validate NetBox devices.
        job.event(f"validating {len(devices)} device(s) exist in NetBox")
        nb_devices_data = {}
        for device in self.bulk_filter(nb.dcim.devices, "name", devices):
            manufacturer_name, manufacturer_slug = get_device_manufacturer_name(
                nb, device
            )
            nb_devices_data[device.name] = {
                "id": int(device.id),
                "name": device.name,
                "serial": str(device.serial or ""),
                "manufacturer": manufacturer_name or "",
                "manufacturer_slug": manufacturer_slug or "",
            }

        for device_name in list(devices):
            if device_name not in nb_devices_data:
                msg = f"{device_name} - device not found in Netbox"
                log.error(msg)
                job.event(msg, severity="ERROR")
                ret.errors.append(msg)
                devices.remove(device_name)

        if not devices:
            job.event(
                "no valid NetBox devices remain after validation", severity="ERROR"
            )
            ret.failed = True
            return ret
        job.event(f"validated {len(devices)} device(s) in NetBox")

        # Fetch current module bays and installed modules.
        job.event("fetching current module bay data from NetBox")
        nb_module_bays = {device_name: {} for device_name in devices}
        for module_bay in self.bulk_filter(nb.dcim.module_bays, "device", devices):
            device_name = module_bay.device.name
            bay_name = str(module_bay.name or "").strip()
            if device_name in nb_module_bays and bay_name:
                nb_module_bays[device_name][bay_name] = {
                    "id": int(module_bay.id),
                    "name": bay_name,
                }

        job.event("fetching installed module data from NetBox")
        nb_modules = {device_name: {} for device_name in devices}
        nb_module_ids = {device_name: {} for device_name in devices}
        for module in self.bulk_filter(nb.dcim.modules, "device", devices):
            device_name = ""
            if module.device:
                device_name = module.device.name
            if not device_name and module.module_bay.device:
                device_name = module.module_bay.device.name
            bay_name = str(module.module_bay.name or "").strip()
            if device_name in nb_modules and bay_name:
                nb_modules[device_name][bay_name] = normalise_netbox_module(module, nb)
                nb_module_ids[device_name][bay_name] = int(module.id)

        # Collect live inventory from Nornir.
        job.event(f"retrieving live inventory for {len(devices)} device(s)")
        nornir_kwargs = dict(kwargs)
        nornir_kwargs["get"] = "inventory"
        nornir_kwargs["strict"] = False
        if devices:
            nornir_kwargs["FL"] = devices
        parse_data = self.client.run_job(
            "nornir",
            "parse_ttp",
            workers="all",
            timeout=timeout,
            kwargs=nornir_kwargs,
        )
        if parse_data is None:
            msg = "nornir parse_ttp inventory returned no data"
            ret.errors.append(msg)
            ret.failed = True
            job.event(msg, severity="ERROR")
            return ret

        live_records_by_device = {device_name: [] for device_name in devices}
        parse_worker_errors = []
        for worker_name, worker_data in parse_data.items():
            if worker_data.get("failed"):
                msg = f"{worker_name} - failed to parse inventory data from devices"
                parse_worker_errors.append(msg)
                log.warning(f"{msg}: {worker_data.get('errors')}")
                job.event(msg, severity="WARNING")
                continue
            for device_name, host_inventory in (worker_data.get("result") or {}).items():
                if device_name not in live_records_by_device:
                    continue
                records = flatten_inventory_records(host_inventory)
                if records:
                    live_records_by_device[device_name].extend(records)

        # Normalize live and NetBox state.
        job.event("normalising live and NetBox inventory data")
        normalised_live_all = {}
        normalised_nb_all = {}
        ignored_by_device = {}
        skipped_slots_by_device = {}
        devices_with_live_data = []

        for device_name in devices:
            records = live_records_by_device.get(device_name) or []
            if not records:
                msg = f"{device_name} - parsing returned no inventory data, skipping device"
                ret.errors.append(msg)
                log.error(msg)
                job.event(msg, severity="ERROR")
                continue

            live_state, ignored, skipped_slots, device_error = (
                normalise_live_inventory_records(
                    records,
                    fallback_manufacturer=nb_devices_data[device_name][
                        "manufacturer"
                    ],
                )
            )
            ignored_by_device[device_name] = ignored
            skipped_slots_by_device[device_name] = skipped_slots

            if device_error:
                msg = f"{device_name} - {device_error}, skipping device"
                ret.errors.append(msg)
                log.error(msg)
                job.event(msg, severity="ERROR")
                continue

            if "chassis" not in live_state:
                msg = f"{device_name} - no chassis serial found"
                ret.errors.append(msg)
                log.warning(msg)
                job.event(msg, severity="WARNING")

            normalised_live_all[device_name] = live_state
            normalised_nb_all[device_name] = dict(nb_modules.get(device_name, {}))
            if "chassis" in live_state:
                normalised_nb_all[device_name]["chassis"] = {
                    "slot": "chassis",
                    "inventory_type": "chassis",
                    "serial": nb_devices_data[device_name]["serial"],
                }
            devices_with_live_data.append(device_name)

        if not devices_with_live_data:
            msg = "no inventory parsing results collected for devices"
            ret.errors.append(msg)
            ret.errors.extend(parse_worker_errors)
            ret.failed = True
            job.event(msg, severity="ERROR")
            return ret
        ret.messages.extend(parse_worker_errors)

        ignored_error_messages = set()
        for device_name, ignored_records in ignored_by_device.items():
            for ignored_record in ignored_records:
                slot = ignored_record.get("slot") or "unknown"
                reason = ignored_record.get("reason") or "ignored"
                msg = f"{device_name}:{slot} - ignored inventory record, {reason}"
                if msg in ignored_error_messages:
                    continue
                ignored_error_messages.add(msg)
                ret.errors.append(msg)
                log.warning(msg)
                job.event(msg, severity="WARNING")

        # Diff desired live state against current NetBox state.
        job.event("calculating inventory sync diff")
        full_diff = self.make_diff(normalised_live_all, normalised_nb_all)

        # Suppress deletes for slots where live inventory existed but was incomplete.
        for device_name, skipped_slots in skipped_slots_by_device.items():
            if device_name not in full_diff:
                continue

            safe_delete_slots = []
            for slot in full_diff[device_name]["delete"]:
                if slot in skipped_slots:
                    continue
                safe_delete_slots.append(slot)
            full_diff[device_name]["delete"] = safe_delete_slots

        create_count = 0
        update_count = 0
        delete_count = 0
        in_sync_count = 0
        for actions in full_diff.values():
            create_count += len(actions["create"])
            update_count += len(actions["update"])
            delete_count += len(actions["delete"])
            in_sync_count += len(actions["in_sync"])
        job.event(
            "inventory sync diff complete: "
            f"{create_count} create, {update_count} update, "
            f"{delete_count} delete, {in_sync_count} in sync"
        )

        if dry_run is True:
            job.event(
                "dry-run requested, returning inventory sync diff without changes"
            )
            ret.result = full_diff
            ret.dry_run = True
            return ret
        else:
            ret.diff = full_diff

        module_type_lookup_cache = {}

        device_results = {}
        for device_name, actions in full_diff.items():
            device_results[device_name] = {
                "created": [],
                "updated": [],
                "deleted": [],
                "in_sync": actions["in_sync"],
            }
        ret.result = device_results

        # Device serial updates from the synthetic chassis slot.
        job.event("applying chassis serial updates")
        for device_name, actions in full_diff.items():
            chassis_diff = actions["update"].get("chassis", {})
            if "serial" not in chassis_diff:
                continue
            new_serial = chassis_diff["serial"]["new_value"]
            if not new_serial:
                continue
            try:
                nb.dcim.devices.update(
                    [{"id": nb_devices_data[device_name]["id"], "serial": new_serial}]
                )
                device_results[device_name]["updated"].append("chassis")
                job.event(f"{device_name} chassis serial updated")
            except Exception as exc:
                msg = f"{device_name} - failed to update chassis serial: {exc}"
                ret.errors.append(msg)
                log.error(msg)
                job.event(msg, severity="ERROR")

        # Optional module bay creation.
        if create_module_bays:
            job.event("creating missing module bays")
            for device_name, actions in full_diff.items():
                for slot in actions["create"]:
                    if slot == "chassis":
                        continue
                    if slot in nb_module_bays.get(device_name, {}):
                        continue
                    desired = normalised_live_all[device_name].get(slot)
                    if not desired:
                        continue
                    try:
                        created = nb.dcim.module_bays.create(
                            device=nb_devices_data[device_name]["id"],
                            name=slot,
                            label=slot,
                        )
                        nb_module_bays[device_name][slot] = {
                            "id": int(created.id),
                            "name": slot,
                        }
                        device_results[device_name]["created"].append(slot)
                        job.event(f"{device_name}:{slot} module bay created")
                    except Exception as exc:
                        msg = f"{device_name}:{slot} - failed to create module bay: {exc}"
                        ret.errors.append(msg)
                        log.error(msg)
                        job.event(msg, severity="ERROR")

        # Module creates.
        job.event("creating missing modules")
        for device_name, actions in full_diff.items():
            for slot in actions["create"]:
                if slot == "chassis":
                    continue
                desired = normalised_live_all[device_name][slot]
                if slot not in nb_module_bays.get(device_name, {}):
                    msg = f"{device_name}:{slot} - module bay not found"
                    ret.errors.append(msg)
                    log.error(msg)
                    job.event(msg, severity="ERROR")
                    continue

                module_type_id, module_type_label = get_or_create_module_type_id(
                    nb,
                    job,
                    ret,
                    device_name,
                    slot,
                    desired,
                    create_module_types,
                    module_type_lookup_cache,
                )
                if not module_type_id:
                    continue
                if module_type_label and create_module_types:
                    device_results[device_name]["created"].append(module_type_label)

                payload = {
                    "device": nb_devices_data[device_name]["id"],
                    "module_bay": nb_module_bays[device_name][slot]["id"],
                    "module_type": module_type_id,
                    "status": desired["status"],
                    "serial": desired["serial"],
                }
                if desired.get("description"):
                    payload["description"] = desired["description"]

                try:
                    created = nb.dcim.modules.create(**payload)
                    nb_module_ids[device_name][slot] = int(created.id)
                    device_results[device_name]["created"].append(slot)
                    job.event(f"{device_name}:{slot} module created")
                except Exception as exc:
                    msg = f"{device_name}:{slot} - failed to create module: {exc}"
                    ret.errors.append(msg)
                    log.error(msg)
                    job.event(msg, severity="ERROR")

        # Module updates.
        job.event("updating changed modules")
        for device_name, actions in full_diff.items():
            for slot, changes in actions["update"].items():
                if slot == "chassis":
                    continue
                desired = normalised_live_all[device_name][slot]
                module_id = nb_module_ids.get(device_name, {}).get(slot)
                if not module_id:
                    continue

                payload = {"id": module_id}
                if "serial" in changes:
                    payload["serial"] = desired["serial"]
                if "status" in changes:
                    payload["status"] = desired["status"]
                if "description" in changes:
                    payload["description"] = desired["description"]
                module_identity_changed = (
                    "module_type" in changes
                    or "part_number" in changes
                    or "manufacturer" in changes
                )
                if module_identity_changed:
                    module_type_id, module_type_label = get_or_create_module_type_id(
                        nb,
                        job,
                        ret,
                        device_name,
                        slot,
                        desired,
                        create_module_types,
                        module_type_lookup_cache,
                    )
                    if not module_type_id:
                        continue
                    if module_type_label and create_module_types:
                        device_results[device_name]["created"].append(
                            module_type_label
                        )
                    payload["module_type"] = module_type_id

                module_update_has_changes = len(payload) > 1
                if not module_update_has_changes:
                    continue

                try:
                    nb.dcim.modules.update([payload])
                    device_results[device_name]["updated"].append(slot)
                    job.event(f"{device_name}:{slot} module updated")
                except Exception as exc:
                    msg = f"{device_name}:{slot} - failed to update module: {exc}"
                    ret.errors.append(msg)
                    log.error(msg)
                    job.event(msg, severity="ERROR")

        # Optional module deletions.
        if process_deletions:
            job.event("deleting stale modules")
            for device_name, actions in full_diff.items():
                for slot in actions["delete"]:
                    if slot == "chassis":
                        continue
                    module_id = nb_module_ids.get(device_name, {}).get(slot)
                    if not module_id:
                        continue
                    try:
                        module = nb.dcim.modules.get(id=module_id)
                        module.delete()
                        device_results[device_name]["deleted"].append(slot)
                        job.event(f"{device_name}:{slot} module deleted")
                    except Exception as exc:
                        msg = f"{device_name}:{slot} - failed to delete module: {exc}"
                        ret.errors.append(msg)
                        log.error(msg)
                        job.event(msg, severity="ERROR")
        elif delete_count:
            job.event(
                f"skipping {delete_count} module deletion(s), process_deletions=False"
            )

        # Keep result lists deterministic and unique.
        for device_result in device_results.values():
            for key in ("created", "updated", "deleted", "in_sync"):
                device_result[key] = sorted(set(device_result[key]))

        job.event("device inventory sync complete")
        return ret

    @Task(
        fastapi={"methods": ["PATCH"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=CheckDeviceSyncInput,
        output=CheckDeviceSyncResult,
        mcp={
            "annotations": {
                "title": "Check Device Sync",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def check_device_sync(
        self,
        job: Job,
        instance: Union[None, str] = None,
        timeout: int = 60,
        devices: Union[None, list] = None,
        branch: str = None,
        check_interfaces: bool = True,
        check_mac_addresses: bool = True,
        check_ip_addresses: bool = True,
        check_bgp_peerings: bool = True,
        **kwargs: Any,
    ) -> Result:
        """
        Check if NetBox device data is in sync with live device data.

        Calls ``sync_device_interfaces``, ``sync_mac_addresses``, ``sync_device_ip``,
        and ``sync_bgp_peerings`` in dry-run mode and produces a per-device report
        indicating which items are in sync and which are not.

        ``Result.diff`` contains the full dry-run detail from each sub-task, keyed by
        sub-task name (``interfaces``, ``mac_addresses``, ``ip_addresses``,
        ``bgp_peerings``).

        Args:
            job: NorFab Job object.
            instance (str, optional): NetBox instance name.
            timeout (int): Timeout in seconds for Nornir jobs. Defaults to 60.
            devices (list, optional): List of device names to check.
            branch (str, optional): NetBox branching plugin branch name.
            check_interfaces (bool): Check interface sync state. Defaults to True.
            check_mac_addresses (bool): Check MAC address sync state. Defaults to True.
            check_ip_addresses (bool): Check IP address sync state. Defaults to True.
            check_bgp_peerings (bool): Check BGP peering sync state. Defaults to True.
            **kwargs: Nornir host filter arguments (e.g. ``FL``, ``FC``, ``FB``).

        Returns:
            Result: Per-device sync summary keyed by device name::

                {
                    "<device>": {
                        "in_sync": True | False,
                        "interfaces":    True | False,
                        "mac_addresses": True | False,
                        "ip_addresses":  True | False,
                        "bgp_peerings":  True | False,
                    }
                }
        """
        devices = devices or []
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:check_device_sync",
            result={},
            resources=[instance],
            diff={},
        )

        # resolve devices from Nornir filters
        if kwargs:
            job.event("resolving devices from Nornir filters")
            nornir_hosts = self.get_nornir_hosts(kwargs, timeout)
            for host in nornir_hosts:
                if host not in devices:
                    devices.append(host)
            job.event(
                f"resolved {len(nornir_hosts)} device(s) from Nornir filters, "
                f"{len(devices)} total device(s) selected"
            )

        if not devices:
            msg = "no devices specified"
            job.event(msg, severity="ERROR")
            ret.errors.append(msg)
            ret.failed = True
            return ret

        log.info(
            f"{self.name} - Check device sync for {len(devices)} device(s) in '{instance}'"
        )
        job.event(f"checking sync state for {len(devices)} device(s)")

        # initialize per-device result structure
        for device in devices:
            ret.result[device] = {}

        # --- check interfaces ---
        if check_interfaces:
            job.event("checking interfaces sync state")
            intf_result = self.sync_device_interfaces(
                job=job,
                instance=instance,
                dry_run=True,
                timeout=timeout,
                devices=list(devices),
                branch=branch,
            )
            if intf_result.errors:
                ret.errors.extend(intf_result.errors)
            for device, data in intf_result.result.items():
                in_sync = (
                    not data.get("create")
                    and not data.get("update")
                    and not data.get("delete")
                )
                ret.result.setdefault(device, {})["interfaces"] = in_sync
            ret.diff["interfaces"] = intf_result.result

        # --- check MAC addresses ---
        if check_mac_addresses:
            job.event("checking MAC addresses sync state")
            mac_result = self.sync_mac_addresses(
                job=job,
                instance=instance,
                dry_run=True,
                timeout=timeout,
                devices=list(devices),
                branch=branch,
            )
            if mac_result.errors:
                ret.errors.extend(mac_result.errors)
            for device, data in mac_result.result.items():
                in_sync = not data.get("created") and not data.get("updated")
                ret.result.setdefault(device, {})["mac_addresses"] = in_sync
            ret.diff["mac_addresses"] = mac_result.result

        # --- check IP addresses ---
        if check_ip_addresses:
            job.event("checking IP addresses sync state")
            ip_result = self.sync_device_ip(
                job=job,
                instance=instance,
                dry_run=True,
                timeout=timeout,
                devices=list(devices),
                branch=branch,
            )
            if ip_result.errors:
                ret.errors.extend(ip_result.errors)
            for device, data in ip_result.result.items():
                in_sync = not data.get("created") and not data.get("updated")
                ret.result.setdefault(device, {})["ip_addresses"] = in_sync
            ret.diff["ip_addresses"] = ip_result.result

        # --- check BGP peerings ---
        if check_bgp_peerings:
            job.event("checking BGP peerings sync state")
            bgp_result = self.sync_bgp_peerings(
                job=job,
                instance=instance,
                dry_run=True,
                timeout=timeout,
                devices=list(devices),
                branch=branch,
            )
            if bgp_result.errors:
                ret.errors.extend(bgp_result.errors)
            for device, data in bgp_result.result.items():
                in_sync = (
                    not data.get("create")
                    and not data.get("update")
                    and not data.get("delete")
                )
                ret.result.setdefault(device, {})["bgp_peerings"] = in_sync
            ret.diff["bgp_peerings"] = bgp_result.result

        checked_categories = {
            "interfaces": check_interfaces,
            "mac_addresses": check_mac_addresses,
            "ip_addresses": check_ip_addresses,
            "bgp_peerings": check_bgp_peerings,
        }
        for device, device_data in ret.result.items():
            device_data["in_sync"] = all(
                device_data.get(category) is True
                for category, checked in checked_categories.items()
                if checked
            )

        log.info(
            f"{self.name} - Check device sync complete for {len(ret.result)} device(s)"
        )
        return ret

    @Task(
        fastapi={"methods": ["PATCH"], "schema": NetboxFastApiArgs.model_json_schema()},
        input=SyncAllInput,
        output=SyncAllResult,
        mcp={
            "annotations": {
                "title": "Sync All Device Data",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def sync_all(
        self,
        job: Job,
        instance: Union[None, str] = None,
        timeout: int = 60,
        devices: Union[None, list] = None,
        branch: str = None,
        dry_run: bool = False,
        process_deletions: bool = False,
        interfaces_filter_by_name: Union[None, str] = None,
        interfaces_filter_by_description: Union[None, str] = None,
        interfaces_update_type: Union[None, bool] = False,
        interfaces_vlan_group: Union[None, str, int] = None,
        mac_filter_by_name: Union[None, str] = None,
        mac_filter_by_description: Union[None, str] = None,
        mac_filter_by_mac: Union[None, str] = None,
        ip_anycast_ranges: Union[None, list] = None,
        ip_ignore_ranges: Union[None, list] = None,
        ip_create_prefixes: bool = True,
        ip_filter_by_name: Union[None, str] = None,
        ip_filter_by_description: Union[None, str] = None,
        ip_filter_by_prefix: Union[None, str] = None,
        ip_filter_by_ip: Union[None, str] = None,
        bgp_status: str = "active",
        bgp_rir: Union[None, str] = None,
        bgp_message: Union[None, str] = None,
        bgp_name_template: str = "{device}_{name}",
        bgp_filter_by_remote_as: Union[None, list] = None,
        bgp_filter_by_peer_group: Union[None, list] = None,
        bgp_filter_by_description: Union[None, str] = None,
        bgp_ignore_peer_ranges: Union[None, list] = None,
        bgp_vrf_custom_field: str = "vrf",
        **kwargs: Any,
    ) -> Result:
        """
        Synchronize all device data from live devices into NetBox in sequence:
        interfaces → MAC addresses → IP addresses → BGP peerings.

        Pass ``dry_run=True`` to preview changes without writing to NetBox.

        ``Result.result`` is keyed by device name, then by category::

            {
                "<device>": {
                    "interfaces":    {"created": [...], "updated": {...}, "deleted": [...], "in_sync": [...]},
                    "mac_addresses": {"created": [...], "updated": [...], "in_sync": [...]},
                    "ip_addresses":  {"created": [...], "updated": [...], "in_sync": [...]},
                    "bgp_peerings":  {"create": [...],  "update": {...},  "delete": [...],  "in_sync": [...]},
                }
            }

        Args:
            job: NorFab Job object.
            instance (str, optional): NetBox instance name.
            timeout (int): Timeout in seconds for Nornir jobs. Defaults to 60.
            devices (list, optional): List of device names to sync.
            branch (str, optional): NetBox branching plugin branch name.
            dry_run (bool): If True, preview changes without writing to NetBox. Defaults to False.
            process_deletions (bool): Process deletions for interfaces and BGP peerings. Defaults to False.
            interfaces_filter_by_name (str, optional): Glob pattern to filter interfaces by name.
            interfaces_filter_by_description (str, optional): Glob pattern to filter interfaces by description.
            interfaces_update_type (bool, optional): Update existing NetBox interface types.
            interfaces_vlan_group (str, int, optional): VLAN group name, slug, or ID for interface VLAN resolution.
            mac_filter_by_name (str, optional): Glob pattern to filter MAC sync interfaces by name.
            mac_filter_by_description (str, optional): Glob pattern to filter MAC sync interfaces by description.
            mac_filter_by_mac (str, optional): Glob pattern to filter MAC addresses.
            ip_anycast_ranges (list, optional): IP prefixes to classify as anycast.
            ip_ignore_ranges (list, optional): IP prefixes to exclude from IP sync.
            ip_create_prefixes (bool): Create missing prefixes during IP sync.
            ip_filter_by_name (str, optional): Glob pattern to filter IP sync interfaces by name.
            ip_filter_by_description (str, optional): Glob pattern to filter IP sync interfaces by description.
            ip_filter_by_prefix (str, optional): IP prefix to restrict synced IP addresses.
            ip_filter_by_ip (str, optional): Glob pattern to restrict synced IP addresses.
            bgp_status (str): Status to set on created/updated BGP sessions.
            bgp_rir (str, optional): RIR name to use when creating new ASNs.
            bgp_message (str, optional): Changelog message for BGP operations.
            bgp_name_template (str): Template string for BGP session names.
            bgp_filter_by_remote_as (list, optional): Only sync sessions matching remote AS numbers.
            bgp_filter_by_peer_group (list, optional): Only sync sessions matching peer groups.
            bgp_filter_by_description (str, optional): Only sync sessions matching description glob.
            bgp_ignore_peer_ranges (list, optional): Prefixes to ignore BGP peers.
            bgp_vrf_custom_field (str): BGP session custom field name used to store VRF reference.
            **kwargs: Nornir host filter arguments (e.g. ``FL``, ``FC``, ``FB``).

        Returns:
            Result: Per-device sync results keyed by device name and category.
        """
        devices = devices or []
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:sync_all",
            result={},
            resources=[instance],
            diff={},
        )

        # resolve devices from Nornir filters
        if kwargs:
            nornir_hosts = self.get_nornir_hosts(kwargs, timeout)
            for host in nornir_hosts:
                if host not in devices:
                    devices.append(host)

        if not devices:
            ret.errors.append("no devices specified")
            ret.failed = True
            return ret

        log.info(
            f"{self.name} - Sync all for {len(devices)} device(s) in '{instance}', dry_run={dry_run}"
        )
        job.event(f"SYNCING all data for {len(devices)} device(s), dry_run={dry_run}")

        # initialize per-device result structure
        for device in devices:
            ret.result[device] = {}

        # --- sync interfaces ---
        job.event("SYNCING interfaces")
        intf_result = self.sync_device_interfaces(
            job=job,
            instance=instance,
            dry_run=dry_run,
            timeout=timeout,
            devices=list(devices),
            branch=branch,
            process_deletions=process_deletions,
            filter_by_name=interfaces_filter_by_name,
            filter_by_description=interfaces_filter_by_description,
            update_type=interfaces_update_type,
            vlan_group=interfaces_vlan_group,
        )
        if intf_result.errors:
            job.event("interface sync completed with errors", severity="WARNING")
            ret.errors.extend(intf_result.errors)
        for device, data in intf_result.result.items():
            ret.result.setdefault(device, {})["interfaces"] = data

        # --- sync MAC addresses ---
        job.event("SYNCING MAC addresses")
        mac_result = self.sync_mac_addresses(
            job=job,
            instance=instance,
            dry_run=dry_run,
            timeout=timeout,
            devices=list(devices),
            branch=branch,
            filter_by_name=mac_filter_by_name,
            filter_by_description=mac_filter_by_description,
            filter_by_mac=mac_filter_by_mac,
        )
        if mac_result.errors:
            job.event("MAC address sync completed with errors", severity="WARNING")
            ret.errors.extend(mac_result.errors)
        for device, data in mac_result.result.items():
            ret.result.setdefault(device, {})["mac_addresses"] = data

        # --- sync IP addresses ---
        job.event("SYNCING IP addresses")
        ip_result = self.sync_device_ip(
            job=job,
            instance=instance,
            dry_run=dry_run,
            timeout=timeout,
            devices=list(devices),
            branch=branch,
            anycast_ranges=ip_anycast_ranges,
            ignore_ranges=ip_ignore_ranges,
            create_prefixes=ip_create_prefixes,
            filter_by_name=ip_filter_by_name,
            filter_by_description=ip_filter_by_description,
            filter_by_prefix=ip_filter_by_prefix,
            filter_by_ip=ip_filter_by_ip,
        )
        if ip_result.errors:
            job.event("IP address sync completed with errors", severity="WARNING")
            ret.errors.extend(ip_result.errors)
        for device, data in ip_result.result.items():
            ret.result.setdefault(device, {})["ip_addresses"] = data

        # --- sync BGP peerings ---
        job.event("SYNCING BGP peerings")
        bgp_result = self.sync_bgp_peerings(
            job=job,
            instance=instance,
            status=bgp_status,
            dry_run=dry_run,
            timeout=timeout,
            devices=list(devices),
            branch=branch,
            process_deletions=process_deletions,
            rir=bgp_rir,
            message=bgp_message,
            name_template=bgp_name_template,
            filter_by_remote_as=bgp_filter_by_remote_as,
            filter_by_peer_group=bgp_filter_by_peer_group,
            filter_by_description=bgp_filter_by_description,
            ignore_peer_ranges=bgp_ignore_peer_ranges,
            vrf_custom_field=bgp_vrf_custom_field,
        )
        if bgp_result.errors:
            job.event("BGP peerings sync completed with errors", severity="WARNING")
            ret.errors.extend(bgp_result.errors)
        for device, data in bgp_result.result.items():
            ret.result.setdefault(device, {})["bgp_peerings"] = data

        log.info(f"{self.name} - Sync all complete for {len(ret.result)} device(s)")
        job.event(f"sync all complete for {len(ret.result)} device(s)")
        return ret
