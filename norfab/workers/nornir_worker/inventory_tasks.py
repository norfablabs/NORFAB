import logging

from typing import Any, Dict, List, Optional, Union

from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictStr,
    model_validator,
)

from nornir_salt.plugins.functions import InventoryFun
from norfab.core.worker import Job, Task
from norfab.models import Result
from norfab.core.inventory import merge_recursively
from .nornir_models import NornirHostsFilters

log = logging.getLogger(__name__)

# -----------------------------------------------------------------------------------------
# Task Pydantic Models
# -----------------------------------------------------------------------------------------

class GetNornirHosts(NornirHostsFilters, extra="forbid"):
    """
    Pydantic model for Nornir get_nornir_hosts task.
    """

    job: object = Field(None, description="Job instance running this task")
    details: Optional[StrictBool] = Field(
        None, description="get_nornir_hosts task input arguments schema"
    )


class HostDetails(BaseModel, extra="forbid"):
    platform: StrictStr = Field(None, description="Host's platform name")
    hostname: StrictStr = Field(None, description="Host's hostname")
    port: StrictStr = Field(None, description="Host's port to initiate connection with")
    groups: List[StrictStr] = Field(None, description="Host's groups")
    username: StrictStr = Field(None, description="Host's username")


class GetNornirHostsResponse(Result):
    result: Union[List[StrictStr], Dict[StrictStr, HostDetails], None] = Field(
        None, description="get_nornir_host results schema"
    )


# -----------------------------------------------------------------------------------------
# Tasks
# -----------------------------------------------------------------------------------------

class InventoryTasks:
    @Task(fastapi={"methods": ["POST"]})
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

        # form Netbox inventory load arguments
        if isinstance(self.nornir_worker_inventory.get("netbox"), dict):
            kwargs = self.nornir_worker_inventory["netbox"]
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

        job.event("completed processing Nornir inventory from Netbox")

        return ret

    @Task(fastapi={"methods": ["POST"]})
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
            raise RuntimeError(msg)

        job.event(f"pulled Containerlab '{lab_name or 'all'}' lab inventory")

        if dry_run is True:
            ret.result = {w: r["result"] for w, r in clab_inventory_data.items()}
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
            raise RuntimeError(msg)

        job.event(
            f"merged Containerlab '{lab_name or 'all'}' lab inventory with Nornir runtime inventory"
        )

        if re_init_nornir is True:
            self.init_nornir(self.nornir_worker_inventory)
            job.event("nornir instance re-initialized")

        return ret
        
    @Task(fastapi={"methods": ["GET"]})
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
        input=GetNornirHosts,
        output=GetNornirHostsResponse,
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

    @Task(fastapi={"methods": ["POST"]})
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
