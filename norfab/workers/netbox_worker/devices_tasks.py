import logging

import copy

from typing import Union, Any
from norfab.core.worker import Task, Job
from norfab.models import Result
from .netbox_models import NetboxFastApiArgs
from .netbox_exceptions import UnsupportedNetboxVersion
from norfab.core.exceptions import UnsupportedServiceError

log = logging.getLogger(__name__)


class NetboxDevicesTasks:

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_devices(
        self,
        job: Job,
        filters: Union[None, list] = None,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        devices: Union[None, list] = None,
        cache: Union[bool, str] = None,
    ) -> Result:
        """
        Retrieves device data from Netbox using the GraphQL API.

        Args:
            job: NorFab Job object containing relevant metadata
            filters (list, optional): A list of filter dictionaries to filter devices.
            instance (str, optional): The Netbox instance name.
            dry_run (bool, optional): If True, only returns the query content without executing it. Defaults to False.
            devices (list, optional): A list of device names to query data for.
            cache (Union[bool, str], optional): Cache usage options:

                - True: Use data stored in cache if it is up to date, refresh it otherwise.
                - False: Do not use cache and do not update cache.
                - "refresh": Ignore data in cache and replace it with data fetched from Netbox.
                - "force": Use data in cache without checking if it is up to date.

        Returns:
            dict: A dictionary keyed by device name with device data.

        Raises:
            Exception: If the GraphQL query fails or if there are errors in the query result.
        """
        instance = instance or self.default_instance
        ret = Result(task=f"{self.name}:get_devices", result={}, resources=[instance])
        cache = self.cache_use if cache is None else cache
        filters = filters or []
        devices = devices or []
        queries = {}  # devices queries
        device_fields = [
            "name",
            "last_updated",
            "custom_field_data",
            "tags {name}",
            "device_type {model}",
            "role {name}",
            "config_context",
            "tenant {name}",
            "platform {name}",
            "serial",
            "asset_tag",
            "site {name slug tags{name} }",
            "location {name}",
            "rack {name}",
            "status",
            "primary_ip4 {address}",
            "primary_ip6 {address}",
            "airflow",
            "position",
            "id",
        ]

        if cache == True or cache == "force":
            # retrieve last updated data from Netbox for devices
            last_updated_query = {
                f"devices_by_filter_{index}": {
                    "obj": "device_list",
                    "filters": filter_item,
                    "fields": ["name", "last_updated"],
                }
                for index, filter_item in enumerate(filters)
            }
            if devices:
                # use cache data without checking if it is up to date for cached devices
                if cache == "force":
                    for device_name in list(devices):
                        device_cache_key = f"get_devices::{device_name}"
                        if device_cache_key in self.cache:
                            devices.remove(device_name)
                            ret.result[device_name] = self.cache[device_cache_key]
                # query netbox last updated data for devices
                if self.nb_version[instance] >= (4, 4, 0):
                    dlist = '["{dl}"]'.format(dl='", "'.join(devices))
                    filters_dict = {"name": f"{{in_list: {dlist}}}"}
                else:
                    raise UnsupportedNetboxVersion(
                        f"{self.name} - Netbox version {self.nb_version[instance]} is not supported, "
                        f"minimum required version is {self.compatible_ge_v4}"
                    )
                last_updated_query["devices_by_devices_list"] = {
                    "obj": "device_list",
                    "filters": filters_dict,
                    "fields": ["name", "last_updated"],
                }
            last_updated = self.graphql(
                job=job,
                queries=last_updated_query,
                instance=instance,
                dry_run=dry_run,
            )
            last_updated.raise_for_status(f"{self.name} - get devices query failed")

            # return dry run result
            if dry_run:
                ret.result["get_devices_dry_run"] = last_updated.result
                return ret

            # try to retrieve device data from cache
            self.cache.expire()  # remove expired items from cache
            for devices_list in last_updated.result.values():
                for device in devices_list:
                    device_cache_key = f"get_devices::{device['name']}"
                    # check if cache is up to date and use it if so
                    if device_cache_key in self.cache and (
                        self.cache[device_cache_key].get("last_updated")
                        == device["last_updated"]
                        or cache == "force"
                    ):
                        ret.result[device["name"]] = self.cache[device_cache_key]
                        # remove device from list of devices to retrieve
                        if device["name"] in devices:
                            devices.remove(device["name"])
                    # cache old or no cache, fetch device data
                    elif device["name"] not in devices:
                        devices.append(device["name"])
        # ignore cache data, fetch data from netbox
        elif cache == False or cache == "refresh":
            queries = {
                f"devices_by_filter_{index}": {
                    "obj": "device_list",
                    "filters": filter_item,
                    "fields": device_fields,
                }
                for index, filter_item in enumerate(filters)
            }

        # fetch devices data from Netbox
        if devices or queries:
            if devices:
                if self.nb_version[instance] >= (4, 4, 0):
                    dlist = '["{dl}"]'.format(dl='", "'.join(devices))
                    filters_dict = {"name": f"{{in_list: {dlist}}}"}
                else:
                    raise UnsupportedNetboxVersion(
                        f"{self.name} - Netbox version {self.nb_version[instance]} is not supported, "
                        f"minimum required version is {self.compatible_ge_v4}"
                    )
                queries["devices_by_devices_list"] = {
                    "obj": "device_list",
                    "filters": filters_dict,
                    "fields": device_fields,
                }

            # send queries
            query_result = self.graphql(
                job=job, queries=queries, instance=instance, dry_run=dry_run
            )

            # check for errors
            if query_result.errors:
                msg = f"{self.name} - get devices query failed with errors:\n{query_result.errors}"
                raise Exception(msg)

            # return dry run result
            if dry_run:
                ret.result["get_devices_dry_run"] = query_result.result
                return ret

            # process devices data
            devices_data = query_result.result
            for devices_list in devices_data.values():
                for device in devices_list:
                    if device["name"] not in ret.result:
                        device_name = device.pop("name")
                        # cache device data
                        if cache != False:
                            cache_key = f"get_devices::{device_name}"
                            self.cache.set(cache_key, device, expire=self.cache_ttl)
                        # add device data to return result
                        ret.result[device_name] = device

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
