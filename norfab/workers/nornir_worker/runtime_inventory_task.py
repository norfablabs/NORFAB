from norfab.models import Result
from norfab.core.worker import Task, Job
from nornir_salt.plugins.functions import InventoryFun
from typing import Any


class RuntimeInventoryTask:
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
        job.event(f"Performing '{action}' action")
        return Result(result=InventoryFun(self.nr, call=action, **kwargs))
