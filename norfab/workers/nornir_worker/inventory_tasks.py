import logging
from typing import Any, Union

from nornir_salt.plugins.functions import InventoryFun

from norfab.core.inventory import merge_recursively
from norfab.core.worker import Job, Task
from norfab.models import Result

from .nornir_models import (
    CreateHostFromNetboxInput,
    CreateHostFromNetboxResult,
    GetInventoryInput,
    GetInventoryResult,
    GetNornirHostsInput,
    GetNornirHostsResult,
    NornirInventoryLoadContainerlabInput,
    NornirInventoryLoadContainerlabResult,
    NornirInventoryLoadNetboxInput,
    NornirInventoryLoadNetboxResult,
    RuntimeInventoryInput,
    RuntimeInventoryResult,
)

log = logging.getLogger(__name__)



# -----------------------------------------------------------------------------------------
# Tasks
# -----------------------------------------------------------------------------------------


class InventoryTasks:
    @Task(
        fastapi={"methods": ["POST"]},
        input=CreateHostFromNetboxInput,
        output=CreateHostFromNetboxResult,
        mcp={
            "annotations": {
                "title": "Create Nornir Hosts from NetBox Devices",
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def create_host_from_netbox(
        self,
        job: Job,
        devices: list[str],
        instance: str | None = None,
        netbox_workers: str | list[str] | None = "any",
        timeout: int | None = 600,
        interfaces: bool | dict | None = None,
        connections: bool | dict | None = None,
        circuits: bool | dict | None = None,
        bgp_peerings: bool | dict | None = None,
        nbdata: bool | None = None,
        primary_ip: str | None = None,
        cache: bool | str | None = True,
        groups: list[str] | None = None,
        dry_run: bool | None = False,
        progress: bool | None = True,
    ) -> Result:
        """
        Create or replace runtime Nornir hosts from explicit NetBox device names.

        The task asks the NetBox service to build Nornir-compatible host data,
        predicts which returned host names are new or existing, and delegates
        the actual in-memory host replacement to ``runtime_inventory``.
        """
        # Normalize optional list inputs used later in simple list operations.
        devices = devices or []
        groups = groups or []
        netbox_hosts = None
        ret = Result(
            task=f"{self.name}:create_host_from_netbox",
            result={"created": [], "updated": [], "missing": []},
        )

        # Start with the worker's configured NetBox inventory options, when any.
        if isinstance(self.nornir_worker_inventory.get("netbox"), dict):
            nornir_netbox_options = self.nornir_worker_inventory["netbox"].copy()
        else:
            nornir_netbox_options = {}

        # Task arguments that are present override worker inventory options.
        if interfaces is not None:
            nornir_netbox_options["interfaces"] = interfaces
        if connections is not None:
            nornir_netbox_options["connections"] = connections
        if circuits is not None:
            nornir_netbox_options["circuits"] = circuits
        if bgp_peerings is not None:
            nornir_netbox_options["bgp_peerings"] = bgp_peerings
        if nbdata is not None:
            nornir_netbox_options["nbdata"] = nbdata
        if primary_ip is not None:
            nornir_netbox_options["primary_ip"] = primary_ip
        if cache is not None:
            nornir_netbox_options["cache"] = cache
        nornir_netbox_options["devices"] = devices
        nornir_netbox_options["instance"] = instance

        # NetBox owns host data construction; Nornir owns the runtime inventory write.
        job.event(
            f"fetching Nornir inventory for {len(devices)} NetBox device(s) "
            f"from '{netbox_workers or 'any'}' worker(s)"
        )
        nb_inventory_data = self.client.run_job(
            service="netbox",
            task="get_nornir_inventory",
            workers=netbox_workers,
            kwargs=nornir_netbox_options,
            timeout=timeout,
        )

        if nb_inventory_data is None:
            msg = f"{self.name} - NetBox get_nornir_inventory returned no data"
            log.error(msg)
            ret.failed = True
            ret.status = "failed"
            ret.errors = [msg]
            return ret

        # Use the first NetBox worker that returns host inventory.
        for wname, wdata in nb_inventory_data.items():
            if wdata.get("failed") is False and wdata.get("result", {}).get("hosts"):
                netbox_hosts = wdata["result"]["hosts"]
                break

        if not netbox_hosts:
            msg = (
                f"{self.name} - NetBox worker(s) "
                f"'{', '.join(list(nb_inventory_data.keys()))}' returned no hosts data"
            )
            log.error(msg)
            ret.failed = True
            ret.status = "failed"
            ret.errors = [msg]
            return ret

        # calculate devices that are missing from netbox
        missing = sorted(set(devices) - set(netbox_hosts))
        if missing:
            msg = f"{self.name} - NetBox returned no host data for: {', '.join(missing)}"
            log.warning(msg)
            job.event(msg, severity="WARNING")

        # add host groups
        for host_data in netbox_hosts.values():
            host_data["groups"] = host_data.get("groups", []) + groups

        existing_hosts = set(self.nr.inventory.hosts)
        created = sorted(set(netbox_hosts) - existing_hosts)
        updated = sorted(set(netbox_hosts) & existing_hosts)
        ret.result = {"created": created, "updated": updated, "missing": missing}

        # Dry run stops after prediction and does not mutate Nornir runtime inventory.
        if dry_run is True:
            job.event("dry-run requested, Nornir runtime inventory not changed")
            ret.dry_run = True
            return ret

        # Runtime inventory load calls create_host once for each returned NetBox host.
        inventory_actions = [
            {"call": "create_host", "name": host_name, **host_data}
            for host_name, host_data in netbox_hosts.items()
        ]
        inventory_result = self.runtime_inventory(
            job=job,
            action="load",
            data=inventory_actions,
            progress=progress if progress is not None else False,
        )
        if inventory_result.failed:
            # Keep this task's created/updated/missing prediction and attach runtime errors.
            ret.failed = inventory_result.failed
            ret.status = inventory_result.status
            ret.errors.extend(inventory_result.errors)
            ret.messages.extend(inventory_result.messages)
            if inventory_result.result:
                ret.messages.append(str(inventory_result.result))
            return ret

        job.event(
            f"created {len(ret.result['created'])}, updated {len(ret.result['updated'])}, "
            f"missing {len(ret.result['missing'])} Nornir host(s) from NetBox"
        )
        return ret

    @Task(
        fastapi={"methods": ["POST"]},
        input=NornirInventoryLoadNetboxInput,
        output=NornirInventoryLoadNetboxResult,
        mcp={
            "annotations": {
                "title": "Load Nornir Inventory from NetBox",
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def nornir_inventory_load_netbox(
        self,
        job: Job,
        progress: bool = False,
    ) -> Result:
        """
        Queries inventory data from Netbox Service and merges it into the Nornir inventory.

        This function checks if there is Netbox data in the inventory and retrieves
        it if available. It handles retries and timeout configurations, and ensures
        that necessary filters or devices are specified. The retrieved inventory
        data is then merged into the existing Nornir inventory.

        Args:
            job: NorFab Job object containing relevant metadata

        Logs:
            - Critical: If the inventory has no hosts, filters, or devices defined.
            - Error: If no inventory data is returned from Netbox.
            - Warning: If the Netbox instance returns no hosts data.
        """
        ret = Result(task=f"{self.name}:nornir_inventory_load_netbox", result=True)

        self.status["netbox_inventory_status"] = "initialising"

        # form Netbox inventory load arguments
        if isinstance(self.nornir_worker_inventory.get("netbox"), dict):
            kwargs = self.nornir_worker_inventory["netbox"].copy()
        elif self.nornir_worker_inventory.get("netbox") is True:
            kwargs = {}
        timeout = max(10, kwargs.pop("timeout", 100))

        # check if need to add devices list
        if "filters" not in kwargs and "devices" not in kwargs:
            if self.nornir_worker_inventory.get("hosts"):
                kwargs["devices"] = list(self.nornir_worker_inventory["hosts"])
            else:
                msg = f"{self.name} - inventory has no hosts, Netbox filters or devices defined"
                log.warning(msg)
                ret.result = False
                ret.messages = [msg]
                self.status["netbox_inventory_status"] = "failed"
                return ret

        nb_inventory_data = self.client.run_job(
            service="netbox",
            task="get_nornir_inventory",
            workers="any",
            kwargs=kwargs,
            timeout=timeout,
        )

        if nb_inventory_data is None:
            msg = f"{self.name} - Netbox get_nornir_inventory no inventory returned"
            log.error(msg)
            self.status["netbox_inventory_status"] = "failed"
            raise RuntimeError(msg)

        # merge Netbox inventory into Nornir inventory
        for wname, wdata in nb_inventory_data.items():
            if wdata["failed"] is False and wdata["result"].get("hosts"):
                merge_recursively(self.nornir_worker_inventory, wdata["result"])
                break
        else:
            msg = (
                f"{self.name} - Netbox worker(s) "
                f"'{', '.join(list(nb_inventory_data.keys()))}' returned no hosts data."
            )
            log.error(msg)
            job.event(msg, severity="ERROR")
            ret.result = False
            ret.messages = [msg]
            self.status["netbox_inventory_status"] = "failed"
            return ret

        self.status["netbox_inventory_status"] = "completed"
        job.event("completed processing Nornir inventory from Netbox")

        return ret

    @Task(
        fastapi={"methods": ["POST"]},
        input=NornirInventoryLoadContainerlabInput,
        output=NornirInventoryLoadContainerlabResult,
        mcp={
            "annotations": {
                "title": "Load Nornir Inventory from Containerlab",
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def nornir_inventory_load_containerlab(
        self,
        job: Job,
        lab_name: str = None,
        groups: Union[None, list] = None,
        clab_workers: str = "all",
        use_default_credentials: bool = True,
        progress: bool = False,
        dry_run: bool = False,
        re_init_nornir: bool = True,
    ) -> Result:
        """
        Pulls the Nornir inventory from a Containerlab lab instance and merges it with the
        existing Nornir inventory.

        Args:
            job: NorFab Job object containing relevant metadata
            lab_name (str): The name of the Containerlab lab to retrieve the inventory from.
            groups (list, optional): A list of group names to include into the hosts' inventory.
            use_default_credentials (bool): Whether to use default credentials for the hosts.

        Returns:
            Result: A Result object indicating the success or failure of the operation.
                    If successful, the Nornir inventory is updated with the retrieved data.

        Notes:
            - The method retrieves inventory data from a Containerlab lab using a client job.
            - If the retrieved inventory contains host data, it is merged into the existing
              Nornir inventory using the `merge_recursively` function.
            - If no inventory or host data is returned, the method logs an error and marks
              the operation as failed.
            - After successful merging of inventory, Nornir instance is re-initialized with the
              updated inventory.
        """
        groups = groups or []
        ret = Result(
            task=f"{self.name}:nornir_inventory_load_containerlab", result=True
        )
        self.status["containerlab_inventory_status"] = "initialising"
        job.event(
            f"pulling Containerlab '{lab_name or 'all'}' inventory from '{clab_workers}' workers"
        )

        clab_inventory_data = self.client.run_job(
            service="containerlab",
            task="get_nornir_inventory",
            workers=clab_workers,
            kwargs={
                "lab_name": lab_name,
                "groups": groups,
                "use_default_credentials": use_default_credentials,
            },
        )

        if clab_inventory_data is None:
            msg = f"{self.name} - Containerlab get_nornir_inventory no data returned"
            log.error(msg)
            self.status["containerlab_inventory_status"] = "failed"
            raise RuntimeError(msg)

        job.event(f"pulled Containerlab '{lab_name or 'all'}' lab inventory")

        if dry_run is True:
            ret.result = {w: r["result"] for w, r in clab_inventory_data.items()}
            self.status["containerlab_inventory_status"] = "completed"
            return ret

        for wname, wdata in clab_inventory_data.items():
            # use inventory from first worker that returned hosts data
            if wdata["failed"] is False and wdata["result"].get("hosts"):
                merge_recursively(self.nornir_worker_inventory, wdata["result"])
                break
        else:
            msg = (
                f"{self.name} - Containerlab worker(s) '{', '.join(list(clab_inventory_data.keys()))}' "
                f"returned no hosts data for '{lab_name}' lab."
            )
            log.error(msg)
            self.status["containerlab_inventory_status"] = "failed"
            raise RuntimeError(msg)

        job.event(
            f"merged Containerlab '{lab_name or 'all'}' lab inventory with Nornir runtime inventory"
        )

        if re_init_nornir is True:
            self.init_nornir(self.nornir_worker_inventory)
            job.event("nornir instance re-initialized")

        self.status["containerlab_inventory_status"] = "completed"

        return ret

    @Task(
        fastapi={"methods": ["GET"]},
        input=GetInventoryInput,
        output=GetInventoryResult,
        mcp={
            "annotations": {
                "title": "Get Inventory",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            }
        },
    )
    def get_inventory(self, **kwargs: dict) -> Result:
        """
        Retrieve running Nornir inventory for requested hosts

        Args:
            **kwargs (dict): Fx filters used to filter the inventory.

        Returns:
            Dict: A dictionary representation of the filtered inventory.
        """
        ret = Result(task=f"{self.name}:get_inventory", result={})
        filtered_nornir, ret = self.filter_hosts_and_validate(kwargs, ret)
        if ret.status != "no_match":
            ret.result = filtered_nornir.inventory.dict()
        return ret

    @Task(
        fastapi={"methods": ["GET"]},
        input=GetNornirHostsInput,
        output=GetNornirHostsResult,
        mcp={
            "annotations": {
                "title": "Get Nornir Hosts",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            }
        },
    )
    def get_nornir_hosts(self, details: bool = False, **kwargs: dict) -> Result:
        """
        Retrieve a list of Nornir hosts managed by this worker.

        Args:
            details (bool): If True, returns detailed information about each host.
            **kwargs (dict): Hosts filters to apply when retrieving hosts.

        Returns:
            List[Dict]: A list of hosts with optional detailed information.
        """
        ret = Result(task=f"{self.name}:get_nornir_hosts", result={} if details else [])
        filtered_nornir, ret = self.filter_hosts_and_validate(kwargs, ret)
        if ret.status == "no_match":
            ret.result = None
        elif details:
            ret.result = {
                host_name: {
                    "platform": str(host.platform),
                    "hostname": str(host.hostname),
                    "port": str(host.port),
                    "groups": [str(g) for g in host.groups],
                    "username": str(host.username),
                }
                for host_name, host in filtered_nornir.inventory.hosts.items()
            }
        else:
            ret.result = list(filtered_nornir.inventory.hosts)
        return ret

    @Task(
        fastapi={"methods": ["POST"]},
        input=RuntimeInventoryInput,
        output=RuntimeInventoryResult,
        mcp={
            "annotations": {
                "title": "Update Runtime Inventory",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": False,
                "openWorldHint": False,
            }
        },
    )
    def runtime_inventory(self, job: Job, action: str, **kwargs: Any) -> Result:
        """
        Task to work with Nornir runtime (in-memory) inventory.

        Supported actions:

        - `create_host` or `create` - creates new host or replaces existing host object
        - `read_host` or `read` - read host inventory content
        - `update_host` or `update` - non recursively update host attributes if host exists
            in Nornir inventory, do not create host if it does not exist
        - `delete_host` or `delete` - deletes host object from Nornir Inventory
        - `load` - to simplify calling multiple functions
        - `read_inventory` - read inventory content for groups, default and hosts
        - `read_host_data` - to return host's data under provided path keys
        - `list_hosts` - return a list of inventory's host names
        - `list_hosts_platforms` - return a dictionary of hosts' platforms
        - `update_defaults` - non recursively update defaults attributes

        Args:
            job: NorFab Job object containing relevant metadata
            action: action to perform on inventory
            kwargs: arguments to use with the calling action
        """
        # clean up kwargs
        _ = kwargs.pop("progress", None)
        job.event(f"performing '{action}' action")
        return Result(result=InventoryFun(self.nr, call=action, **kwargs))
