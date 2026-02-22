import copy
import logging
import concurrent.futures

from typing import Union
from norfab.core.worker import Task, Job
from norfab.models import Result
from norfab.models.netbox import NetboxFastApiArgs
from .netbox_exceptions import UnsupportedNetboxVersion

log = logging.getLogger(__name__)


class NetboxCircuitsTasks:

    def _map_circuit(
        self,
        job: Job,
        circuit: dict,
        ret: Result,
        instance: str,
        devices: list,
        cache: bool,
    ) -> bool:
        """
        ThreadPoolExecutor target function to retrieve circuit details from Netbox

        Args:
            circuit (dict): The circuit data to be mapped.
            ret (Result): The result object to store the mapped data.
            instance (str): The instance of the Netbox API to use.
            devices (list): List of devices to check against the circuit endpoints.
            cache (bool): Flag to determine if the data should be cached.

        Returns:
            bool: True if the mapping is successful, False otherwise.
        """
        cid = circuit.pop("cid")
        ckt_cache_data = {}  # ckt data dictionary to save in cache
        circuit["tags"] = [i["name"] for i in circuit["tags"]]
        circuit["type"] = circuit["type"]["name"]
        circuit["provider"] = circuit["provider"]["name"]
        circuit["tenant"] = circuit["tenant"]["name"] if circuit["tenant"] else None
        circuit["provider_account"] = (
            circuit["provider_account"]["name"] if circuit["provider_account"] else None
        )
        termination_a = circuit["termination_a"]
        termination_z = circuit["termination_z"]
        termination_a = termination_a["id"] if termination_a else None
        termination_z = termination_z["id"] if termination_z else None

        msg = f"{cid} tracing circuit terminations path"
        log.info(msg)
        job.event(msg)

        # retrieve A or Z termination path using Netbox REST API
        circuit_path = None
        if termination_a is not None:
            resp = self.rest(
                job=job,
                instance=instance,
                method="get",
                api=f"circuits/circuit-terminations/{termination_a}/paths",
            )
            circuit_path = resp.result
        elif termination_z is not None:
            resp = self.rest(
                job=job,
                instance=instance,
                method="get",
                api=f"circuits/circuit-terminations/{termination_z}/paths",
            )
            circuit_path = resp.result

        # check if circuit ends connect to device or provider network
        if (
            not circuit_path
            or "name" not in circuit_path[0]["path"][0][0]
            or "name" not in circuit_path[0]["path"][-1][-1]
        ):
            msg = f"{cid} does not have two terminations, cannot trace the path"
            log.warning(msg)
            job.event(msg)
            return True

        # form A and Z connection endpoints
        end_a = {
            "device": circuit_path[0]["path"][0][0]
            .get("device", {})
            .get("name", False),
            "provider_network": "provider-network"
            in circuit_path[0]["path"][0][0]["url"],
            "name": circuit_path[0]["path"][0][0]["name"],
        }
        end_z = {
            "device": circuit_path[0]["path"][-1][-1]
            .get("device", {})
            .get("name", False),
            "provider_network": "provider-network"
            in circuit_path[0]["path"][-1][-1]["url"],
            "name": circuit_path[0]["path"][-1][-1]["name"],
        }
        circuit["is_active"] = circuit_path[0]["is_active"]

        # map path ends to devices
        if not end_a["device"] and not end_z["device"]:
            msg = f"{cid} path trace ends have no devices connected"
            log.error(msg)
            job.event(msg, severity="ERROR")
            return True
        if end_a["device"]:
            device_data = copy.deepcopy(circuit)
            device_data["interface"] = end_a["name"]
            if end_z["device"]:
                device_data["remote_device"] = end_z["device"]
                device_data["remote_interface"] = end_z["name"]
            elif end_z["provider_network"]:
                device_data["provider_network"] = end_z["name"]
            # save device data in cache
            ckt_cache_data[end_a["device"]] = device_data
            # include device data in result
            if end_a["device"] in devices:
                ret.result[end_a["device"]][cid] = device_data
        if end_z["device"]:
            device_data = copy.deepcopy(circuit)
            device_data["interface"] = end_z["name"]
            if end_a["device"]:
                device_data["remote_device"] = end_a["device"]
                device_data["remote_interface"] = end_a["name"]
            elif end_a["provider_network"]:
                device_data["provider_network"] = end_a["name"]
            # save device data in cache
            ckt_cache_data[end_z["device"]] = device_data
            # include device data in result
            if end_z["device"] in devices:
                ret.result[end_z["device"]][cid] = device_data

        # save data to cache
        if cache != False:
            ckt_cache_key = f"get_circuits::{cid}"
            if ckt_cache_data:
                self.cache.set(ckt_cache_key, ckt_cache_data, expire=self.cache_ttl)
                log.info(
                    f"{self.name}:get_circuits - {cid} cached circuit data for future use"
                )

        msg = f"{cid} circuit data mapped to devices using data from Netbox"
        log.info(msg)
        job.event(msg)
        return True

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_circuits(
        self,
        job: Job,
        devices: list,
        cid: Union[None, list] = None,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        cache: Union[bool, str] = True,
        add_interface_details: bool = False,
    ) -> Result:
        """
        Retrieve circuit information for specified devices from Netbox.

        Args:
            job: NorFab Job object containing relevant metadata
            devices (list): List of device names to retrieve circuits for.
            cid (list, optional): List of circuit IDs to filter by.
            instance (str, optional): Netbox instance to query.
            dry_run (bool, optional): If True, perform a dry run without making changes. Defaults to False.
            add_interface_details (bool, optional): If True, add interface details using `get_interfaces` call
                including interface subinterfaces - ip addresses, vrf, child interfaces with their IPs and vrf
            cache (Union[bool, str], optional): Cache usage options:

                - True: Use data stored in cache if it is up to date, refresh it otherwise.
                - False: Do not use cache and do not update cache.
                - "refresh": Ignore data in cache and replace it with data fetched from Netbox.
                - "force": Use data in cache without checking if it is up to date.

        Returns:
            dict: dictionary keyed by device names with circuits data:

                ```
                nf#netbox get circuits device-list fceos5
                {
                    "netbox-worker-1.1": {
                        "fceos5": {
                            "CID1": {
                                "comments": "",
                                "commit_rate": null,
                                "custom_fields": {},
                                "description": "",
                                "interface": "eth101",
                                "is_active": true,
                                "provider": "Provider1",
                                "provider_account": "",
                                "remote_device": "fceos4",
                                "remote_interface": "eth101",
                                "status": "active",
                                "tags": [],
                                "tenant": null,
                                "type": "DarkFibre"
                            }
                        }
                    }
                }
                nf#
                ```

        If `add_interface_details` is True returns this extra information:

        ```
        {
            "netbox-worker-1.1": {
                "fceos4": {
                    "CID2": {
                        "child_interfaces": [
                            {
                                "ip_addresses": [
                                    {
                                        "address": "10.0.0.12/24",
                                        ...
                                    }
                                ],
                                "name": "eth11.123",
                                "vrf": {
                                    "name": "MGMT"
                                }
                            }
                        ],
                        "interface": "eth11",
                        "ip_addresses": [
                            {
                                "address": "10.0.0.14/24",
                                ...
                            }
                        ],
                        "vrf": {
                            "name": "OOB_CTRL"
                        }
                    }
                }
            }
        }
        ```
        """
        cid = cid or []
        log.info(
            f"{self.name}:get_circuits - {instance or self.default_instance} Netbox, "
            f"devices {', '.join(devices)}, cid {cid}"
        )
        instance = instance or self.default_instance

        # form final result object
        ret = Result(
            task=f"{self.name}:get_circuits",
            result={d: {} for d in devices},
            resources=[instance],
        )
        cache = self.cache_use if cache is None else cache
        cid = cid or []
        circuit_fields = [
            "cid",
            "tags {name}",
            "provider {name}",
            "commit_rate",
            "description",
            "status",
            "type {name}",
            "provider_account {name}",
            "tenant {name}",
            "termination_a {id last_updated}",
            "termination_z {id last_updated}",
            "custom_fields",
            "comments",
            "last_updated",
        ]

        # form initial circuits filters based on devices' sites and cid list
        circuits_filters = {}
        device_data = self.get_devices(
            job=job, devices=copy.deepcopy(devices), instance=instance, cache=cache
        )
        sites = list(set([i["site"]["slug"] for i in device_data.result.values()]))
        if self.nb_version[instance] >= (4, 4, 0):
            slist = str(sites).replace("'", '"')  # swap quotes
            if cid:
                clist = str(cid).replace("'", '"')  # swap quotes
                circuits_filters = "{terminations: {site: {slug: {in_list: slist}}}, cid: {in_list: clist}}"
                circuits_filters = circuits_filters.replace("slist", slist).replace(
                    "clist", clist
                )
            else:
                circuits_filters = "{terminations: {site: {slug: {in_list: slist }}}}"
                circuits_filters = circuits_filters.replace("slist", slist)
        else:
            raise UnsupportedNetboxVersion(
                f"{self.name} - Netbox version {self.nb_version[instance]} is not supported, "
                f"minimum required version is {self.compatible_ge_v4}"
            )

        log.info(
            f"{self.name}:get_circuits - constructed circuits filters: '{circuits_filters}'"
        )

        if cache == True or cache == "force":
            log.info(f"{self.name}:get_circuits - retrieving circuits data from cache")
            job.event("retrieving circuits data from cache")
            cid_list = []  #  new cid list for follow up query
            # retrieve last updated data from Netbox for circuits and their terminations
            last_updated = self.graphql(
                job=job,
                obj="circuit_list",
                filters=circuits_filters,
                fields=[
                    "cid",
                    "last_updated",
                    "termination_a {id last_updated}",
                    "termination_z {id last_updated}",
                ],
                dry_run=dry_run,
                instance=instance,
            )
            last_updated.raise_for_status(f"{self.name} - get circuits query failed")

            # return dry run result
            if dry_run:
                ret.result["get_circuits_dry_run"] = last_updated.result
                return ret

            # retrieve circuits data from cache
            self.cache.expire()  # remove expired items from cache
            for device in devices:
                for circuit in last_updated.result:
                    circuit_cache_key = f"get_circuits::{circuit['cid']}"
                    log.info(
                        f"{self.name}:get_circuits - searching cache for key {circuit_cache_key}"
                    )
                    # check if cache is up to date and use it if so
                    if circuit_cache_key in self.cache:
                        cache_ckt = self.cache[circuit_cache_key]
                        # check if device uses this circuit
                        if device not in cache_ckt:
                            continue
                        # use cache forcefully
                        if cache == "force":
                            ret.result[device][circuit["cid"]] = cache_ckt[device]
                        # check circuit cache is up to date
                        if cache_ckt[device]["last_updated"] != circuit["last_updated"]:
                            continue
                        if (
                            cache_ckt[device]["termination_a"]
                            and circuit["termination_a"]
                            and cache_ckt[device]["termination_a"]["last_updated"]
                            != circuit["termination_a"]["last_updated"]
                        ):
                            continue
                        if (
                            cache_ckt[device]["termination_z"]
                            and circuit["termination_z"]
                            and cache_ckt[device]["termination_z"]["last_updated"]
                            != circuit["termination_z"]["last_updated"]
                        ):
                            continue
                        ret.result[device][circuit["cid"]] = cache_ckt[device]
                        log.info(
                            f"{self.name}:get_circuits - {circuit['cid']} retrieved data from cache"
                        )
                    elif circuit["cid"] not in cid_list:
                        cid_list.append(circuit["cid"])
                        log.info(
                            f"{self.name}:get_circuits - {circuit['cid']} no cache data found, fetching from Netbox"
                        )
            # form new filters dictionary to fetch remaining circuits data
            circuits_filters = {}
            if cid_list:
                cid_list = str(cid_list).replace("'", '"')  # swap quotes
                if self.nb_version[instance] >= (4, 4, 0):
                    circuits_filters = "{cid: {in_list: cid_list}}"
                    circuits_filters = circuits_filters.replace("cid_list", cid_list)
                else:
                    raise UnsupportedNetboxVersion(
                        f"{self.name} - Netbox version {self.nb_version[instance]} is not supported, "
                        f"minimum required version is {self.compatible_ge_v4}"
                    )
        # ignore cache data, fetch circuits from netbox
        elif cache == False or cache == "refresh":
            pass

        if circuits_filters:
            job.event("fetching circuits data from Netbox")
            query_result = self.graphql(
                job=job,
                obj="circuit_list",
                filters=circuits_filters,
                fields=circuit_fields,
                dry_run=dry_run,
                instance=instance,
            )
            query_result.raise_for_status(f"{self.name} - get circuits query failed")

            # return dry run result
            if dry_run is True:
                return query_result

            all_circuits = query_result.result

            # iterate over circuits and map them to devices
            msg = (
                f"retrieved data for {len(all_circuits)} "
                f"circuits from Netbox, mapping circuits to devices"
            )
            log.info(msg)
            job.event(msg)
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                results = [
                    executor.submit(
                        self._map_circuit, job, circuit, ret, instance, devices, cache
                    )
                    for circuit in all_circuits
                ]
                for _ in concurrent.futures.as_completed(results):
                    continue

        if add_interface_details:
            job.event("fetching circuits interface details")
            # collect devices and interfaces to get details for
            fetch_interfaces = set()
            fetch_devices = set(ret.result.keys())
            for device_name, circuits in ret.result.items():
                for ckt_data in circuits.values():
                    fetch_interfaces.add(ckt_data["interface"])
                    if ckt_data.get("remote_device"):
                        fetch_devices.add(ckt_data["remote_device"])
                        fetch_interfaces.add(ckt_data["remote_interface"])
            # fetch interfaces data with IP addresses
            interfaces_data = self.get_interfaces(
                job=job,
                devices=list(fetch_devices),
                interface_list=list(fetch_interfaces),
                ip_addresses=True,
            ).result
            # map interfaces details to circuits
            for device_name, circuits in ret.result.items():
                for circuit_id, ckt_data in circuits.items():
                    interface_name = ckt_data["interface"]
                    if interface_name in interfaces_data.get(device_name, {}):
                        interface_data = interfaces_data[device_name][interface_name]
                        ckt_data["child_interfaces"] = interface_data.get(
                            "child_interfaces", []
                        )
                        ckt_data["ip_addresses"] = interface_data.get(
                            "ip_addresses", []
                        )
                        ckt_data["vrf"] = interface_data.get("vrf", {})
                    else:
                        log.error(
                            f"{device_name}:{circuit_id} failed to find '{interface_name}' interface details"
                        )

        return ret
