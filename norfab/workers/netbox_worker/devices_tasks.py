import copy
import logging
from typing import Any, Dict, List, Union

from pydantic import BaseModel

from norfab.core.exceptions import UnsupportedServiceError
from norfab.core.worker import Job, Task
from norfab.models import Result

from .netbox_models import NetboxFastApiArgs

log = logging.getLogger(__name__)


class GetDevicesSite(BaseModel):
    name: str
    slug: str
    tags: List[str] = []


class GetDevicesIP(BaseModel):
    address: str


class GetDevicesResult(BaseModel):
    id: str
    last_updated: str
    device_type: str
    role: str
    custom_field_data: Dict[str, Any] = {}
    tags: List[str] = []
    config_context: Dict[str, Any] = {}
    tenant: Union[str, None] = None
    platform: Union[str, None] = None
    serial: Union[str, None] = None
    asset_tag: Union[str, None] = None
    site: Union[GetDevicesSite, None] = None
    location: Union[str, None] = None
    rack: Union[str, None] = None
    status: str = None
    primary_ip4: Union[GetDevicesIP, None] = None
    primary_ip6: Union[GetDevicesIP, None] = None
    airflow: Union[str, None] = None
    position: Union[str, None] = None


class GetDevicesOutput(Result):
    result: Dict[str, GetDevicesResult]


class NetboxDevicesTasks:

    @Task(
        fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()},
        output=GetDevicesOutput,
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

        # merge named devices into filters as a name filter
        if devices:
            filters.append({"name": devices})

        # return dry run result
        if dry_run:
            ret.result["get_devices_dry_run"] = {"filters": filters}
            return ret

        filters_to_fetch = list(filters)

        if cache == True or cache == "force":
            # retrieve last_updated data from Netbox for all filters using REST
            last_updated_data = {}
            for filter_item in filters:
                result = self.rest(
                    job=job,
                    instance=instance,
                    api="dcim/devices",
                    params={**filter_item, "fields": "name,last_updated"},
                )
                for device in result.result.get("results", []):
                    last_updated_data[device["name"]] = device["last_updated"]

            # try to retrieve device data from cache
            self.cache.expire()  # remove expired items from cache
            devices_to_fetch = []
            for device_name, last_updated in last_updated_data.items():
                device_cache_key = f"get_devices::{device_name}"
                # check if cache is up to date and use it if so
                if device_cache_key in self.cache and (
                    self.cache[device_cache_key].get("last_updated") == last_updated
                    or cache == "force"
                ):
                    ret.result[device_name] = self.cache[device_cache_key]
                # cache old or no cache, fetch device data
                else:
                    devices_to_fetch.append(device_name)

            # only fetch devices missing from or stale in cache
            filters_to_fetch = [{"name": devices_to_fetch}] if devices_to_fetch else []
        # ignore cache, fetch data from Netbox
        elif cache == False or cache == "refresh":
            pass  # filters_to_fetch already set to all filters above

        # fetch full device data from Netbox
        if filters_to_fetch:
            nb = self._get_pynetbox(instance)
            all_devices_raw = {}

            for filter_item in filters_to_fetch:
                for device in nb.dcim.devices.filter(**filter_item):
                    all_devices_raw.setdefault(device.name, device)

            # process devices data
            for device_name, device in all_devices_raw.items():
                if device_name not in ret.result:
                    device_data = {
                        "last_updated": str(device.last_updated),
                        "custom_field_data": (
                            dict(device.custom_fields) if device.custom_fields else {}
                        ),
                        "tags": [t.name for t in device.tags] if device.tags else [],
                        "device_type": device.device_type.model,
                        "role": device.role.name,
                        "config_context": (
                            dict(device.config_context) if device.config_context else {}
                        ),
                        "tenant": device.tenant.name,
                        "platform": device.platform.name if device.platform else None,
                        "serial": device.serial,
                        "asset_tag": device.asset_tag,
                        "site": {
                            "name": device.site.name,
                            "slug": device.site.slug,
                            "tags": device.site.tags,
                        },
                        "location": device.location.name if device.location else None,
                        "rack": device.rack.name if device.rack else None,
                        "status": device.status.value,
                        "primary_ip4": (
                            {"address": device.primary_ip4.address}
                            if device.primary_ip4
                            else None
                        ),
                        "primary_ip6": (
                            {"address": device.primary_ip6.address}
                            if device.primary_ip6
                            else None
                        ),
                        "airflow": device.airflow.value if device.airflow else None,
                        "position": (
                            str(device.position)
                            if device.position is not None
                            else None
                        ),
                        "id": str(device.id),
                    }
                    # cache device data
                    if cache != False:
                        cache_key = f"get_devices::{device_name}"
                        self.cache.set(cache_key, device_data, expire=self.cache_ttl)
                    # add device data to return result
                    ret.result[device_name] = device_data

        return ret

    @Task(
        fastapi={"methods": ["PATCH"], "schema": NetboxFastApiArgs.model_json_schema()}
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
                devices.extend(self.get_nornir_hosts(kwargs, timeout))
                devices = list(set(devices))
                job.event(f"Syncing {len(devices)} devices")
            # fetch devices data from Netbox
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
                    devices.remove(d)
            # iterate over devices in batches
            for i in range(0, len(devices), batch_size):
                kwargs["FL"] = devices[i : i + batch_size]
                kwargs["getters"] = "get_facts"
                job.event(f"retrieving facts for devices {', '.join(kwargs['FL'])}")
                data = self.client.run_job(
                    "nornir",
                    "parse",
                    kwargs=kwargs,
                    workers="all",
                    timeout=timeout,
                )

                # Collect devices to update in bulk
                devices_to_update = []

                for worker, results in data.items():
                    if results["failed"]:
                        msg = f"{worker} get_facts failed, errors: {'; '.join(results['errors'])}"
                        ret.errors.append(msg)
                        log.error(msg)
                        continue
                    for host, host_data in results["result"].items():
                        if host_data["napalm_get"]["failed"]:
                            msg = f"{host} facts update failed: '{host_data['napalm_get']['exception']}'"
                            ret.errors.append(msg)
                            log.error(msg)
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
                    except Exception as e:
                        ret.errors.append(f"Bulk update failed: {e}")
        else:
            raise UnsupportedServiceError(
                f"'{datasource}' datasource service not supported"
            )

        return ret
