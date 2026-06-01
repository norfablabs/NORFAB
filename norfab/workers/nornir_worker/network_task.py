from norfab.core.worker import Job, Task
from norfab.models import Result

from .nornir_models import (
    NetworkInput,
    NetworkResult,
)

# --------------------------------------------------------------------------
# NETWORK TASK MODELS
# --------------------------------------------------------------------------


class NetworkTask:
    @Task(
        fastapi={"methods": ["POST"]},
        input=NetworkInput,
        output=NetworkResult,
        mcp={
            "annotations": {
                "title": "Run Network Operation",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": False,
                "openWorldHint": True,
            }
        },
    )
    def network(self, job: Job, fun: str, **kwargs: object) -> Result:
        """
        Task to call various network-related utility functions.

        Args:
            job: NorFab Job object containing relevant metadata
            fun (str): The name of the utility function to call.
            kwargs (dict): Arguments to pass to the utility function.

        Available utility functions:

        - **resolve_dns** Resolves hosts' hostname DNS, returning IP addresses using
            `nornir_salt.plugins.tasks.network.resolve_dns` Nornir-Salt function.
        - **ping** Executes ICMP ping to host using `nornir_salt.plugins.tasks.network.ping`
            Nornir-Salt function.

        Returns:
            dict: A dictionary containing the results of the network utility function.

        Raises:
            UnsupportedPluginError: If the specified utility function is not supported.
        """
        kwargs["call"] = fun
        return self.task(
            job=job,
            plugin="nornir_salt.plugins.tasks.network",
            **kwargs,
        )
