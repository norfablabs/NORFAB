import logging
from typing import Union

from norfab.core.worker import Job, Task
from norfab.models import Result

from .fakenos_models import GetNornirInventoryInput

log = logging.getLogger(__name__)


class FakeNOSNornirInventoryTasks:

    @Task(input=GetNornirInventoryInput, fastapi={"methods": ["GET"]})
    def get_nornir_inventory(
        self,
        job: Job,
        network: Union[str, None] = None,
        groups: Union[None, list] = None,
    ) -> Result:
        """
        Retrieve and construct Nornir inventory from FakeNOS data.

        Args:
            job: NorFab Job object containing relevant metadata
            network: Name of the FakeNOS network to build inventory for.
                If None, inventory is built for all networks.
            groups: List of Nornir group names to assign to every host.

        Returns:
            Result: A Result object whose ``result`` attribute is a dict with
                a ``hosts`` key containing hostname-keyed Nornir host entries.
        """
        groups = groups or []
        hosts = {}
        inventory = {"hosts": hosts}
        ret = Result(task=f"{self.name}:get_nornir_inventory", result=inventory)

        # retrieve network details from FakeNOS
        inspect = self.inspect_networks(job=job, network=network, details=True)

        if inspect.failed:
            ret.failed = True
            ret.errors = inspect.errors
            return ret

        # if a specific network was requested but not found, fail
        if network and not inspect.result:
            ret.failed = True
            ret.errors = [f"Network '{network}' not found"]
            return ret

        # FakeNOS listens on localhost
        hostname = "127.0.0.1"

        for net_name, net_info in inspect.result.items():
            for host in net_info.get("hosts", []):
                host_name = host.get("name")
                if not host_name:
                    continue

                hosts[host_name] = {
                    "hostname": hostname,
                    "port": host.get("port"),
                    "platform": host.get("platform"),
                    "username": host.get("username"),
                    "password": host.get("password"),
                    "groups": groups,
                }

                log.info(
                    f"{self.name} - added '{host_name}' from network '{net_name}' "
                    f"to Nornir inventory, port {host.get('port')}, "
                    f"platform {host.get('platform')})"
                )

        return ret
