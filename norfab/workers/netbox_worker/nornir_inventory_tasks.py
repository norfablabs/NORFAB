import logging

from typing import Union, List
from norfab.core.worker import Task, Job
from norfab.models import Result
from norfab.models.netbox import NetboxFastApiArgs

log = logging.getLogger(__name__)


class NetboxNornirInventoryTasks:

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_nornir_inventory(
        self,
        job: Job,
        filters: Union[None, list] = None,
        devices: Union[None, list] = None,
        instance: Union[None, str] = None,
        interfaces: Union[dict, bool] = False,
        connections: Union[dict, bool] = False,
        circuits: Union[dict, bool] = False,
        nbdata: bool = True,
        bgp_peerings: Union[dict, bool] = False,
        primary_ip: str = "ip4",
    ) -> Result:
        """
        Retrieve and construct Nornir inventory from NetBox data.

        Args:
            job: NorFab Job object containing relevant metadata
            filters (list, optional): List of filters to apply when retrieving devices from NetBox.
            devices (list, optional): List of specific devices to retrieve from NetBox.
            instance (str, optional): NetBox instance to use.
            interfaces (Union[dict, bool], optional): If True, include interfaces data
                    in the inventory. If a dict, use it as arguments for the get_interfaces method.
            connections (Union[dict, bool], optional): If True, include connections data
                    in the inventory. If a dict, use it as arguments for the get_connections method.
            circuits (Union[dict, bool], optional): If True, include circuits data in the
                    inventory. If a dict, use it as arguments for the get_circuits method.
            nbdata (bool, optional): If True, include a copy of NetBox device's data in the host's data.
            primary_ip (str, optional): Specify whether to use 'ip4' or 'ip6' for the primary
                    IP address. Defaults to 'ip4'.

        Returns:
            dict: Nornir inventory dictionary containing hosts and their respective data.
        """
        hosts = {}
        filters = filters or []
        devices = devices or []
        inventory = {"hosts": hosts}
        ret = Result(task=f"{self.name}:get_nornir_inventory", result=inventory)

        # check Netbox status
        netbox_status = self.get_netbox_status(job=job, instance=instance)
        if netbox_status.result[instance or self.default_instance]["status"] is False:
            return ret

        # retrieve devices data
        nb_devices = self.get_devices(
            job=job, filters=filters, devices=devices, instance=instance
        )

        # form Nornir hosts inventory
        for device_name, device in nb_devices.result.items():
            host = device["config_context"].pop("nornir", {})
            host.setdefault("data", {})
            name = host.pop("name", device_name)
            hosts[name] = host
            # add platform if not provided in device config context
            if not host.get("platform"):
                if device["platform"]:
                    host["platform"] = device["platform"]["name"]
                else:
                    log.warning(f"{self.name} - no platform found for '{name}' device")
            # add hostname if not provided in config context
            if not host.get("hostname"):
                if device["primary_ip4"] and primary_ip in ["ip4", "ipv4"]:
                    host["hostname"] = device["primary_ip4"]["address"].split("/")[0]
                elif device["primary_ip6"] and primary_ip in ["ip6", "ipv6"]:
                    host["hostname"] = device["primary_ip6"]["address"].split("/")[0]
                else:
                    host["hostname"] = name
            # add netbox data to host's data
            if nbdata is True:
                host["data"].update(device)

        # return if no hosts found for provided parameters
        if not hosts:
            log.warning(f"{self.name} - no viable hosts returned by Netbox")
            return ret

        # add interfaces data
        if interfaces:
            # decide on get_interfaces arguments
            kwargs = interfaces if isinstance(interfaces, dict) else {}
            # add 'interfaces' key to all hosts' data
            for host in hosts.values():
                host["data"].setdefault("interfaces", {})
            # query interfaces data from netbox
            nb_interfaces = self.get_interfaces(
                job=job, devices=list(hosts), instance=instance, **kwargs
            )
            # save interfaces data to hosts' inventory
            while nb_interfaces.result:
                device, device_interfaces = nb_interfaces.result.popitem()
                hosts[device]["data"]["interfaces"] = device_interfaces

        # add connections data
        if connections:
            # decide on get_interfaces arguments
            kwargs = connections if isinstance(connections, dict) else {}
            # add 'connections' key to all hosts' data
            for host in hosts.values():
                host["data"].setdefault("connections", {})
            # query connections data from netbox
            nb_connections = self.get_connections(
                job=job, devices=list(hosts), instance=instance, **kwargs
            )
            # save connections data to hosts' inventory
            while nb_connections.result:
                device, device_connections = nb_connections.result.popitem()
                hosts[device]["data"]["connections"] = device_connections

        # add circuits data
        if circuits:
            # decide on get_interfaces arguments
            kwargs = circuits if isinstance(circuits, dict) else {}
            # add 'circuits' key to all hosts' data
            for host in hosts.values():
                host["data"].setdefault("circuits", {})
            # query circuits data from netbox
            nb_circuits = self.get_circuits(
                job=job, devices=list(hosts), instance=instance, **kwargs
            )
            # save circuits data to hosts' inventory
            while nb_circuits.result:
                device, device_circuits = nb_circuits.result.popitem()
                hosts[device]["data"]["circuits"] = device_circuits

        # add bgp peerings data
        if bgp_peerings:
            # decide on get_interfaces arguments
            kwargs = bgp_peerings if isinstance(bgp_peerings, dict) else {}
            # add 'bgp_peerings' key to all hosts' data
            for host in hosts.values():
                host["data"].setdefault("bgp_peerings", {})
            # query bgp_peerings data from netbox
            nb_bgp_peerings = self.get_bgp_peerings(
                job=job, devices=list(hosts), instance=instance, **kwargs
            )
            # save circuits data to hosts' inventory
            while nb_bgp_peerings.result:
                device, device_bgp_peerings = nb_bgp_peerings.result.popitem()
                hosts[device]["data"]["bgp_peerings"] = device_bgp_peerings

        return ret

    def get_nornir_hosts(self, kwargs: dict, timeout: int) -> List[str]:
        """
        Retrieves a list of unique Nornir hosts from Nornir service based on provided filter criteria.

        Args:
            kwargs (dict): Dictionary of keyword arguments, where keys starting with 'F' are used as filters.
            timeout (int): Timeout value (in seconds) for the job execution.

        Returns:
            list: Sorted list of unique Nornir host names that match the filter criteria.

        Notes:
            - Only filters with keys starting with 'F' are considered.
            - Hosts are collected from all workers where the job did not fail.
        """
        ret = []
        filters = {k: v for k, v in kwargs.items() if k.startswith("F")}
        if filters:
            nornir_hosts = self.client.run_job(
                "nornir",
                "get_nornir_hosts",
                kwargs=filters,
                workers="all",
                timeout=timeout,
            )
            for w, r in nornir_hosts.items():
                if r["failed"] is False and isinstance(r["result"], list):
                    ret.extend(r["result"])

        return list(sorted(set(ret)))
