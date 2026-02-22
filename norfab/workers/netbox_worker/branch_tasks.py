import logging

from norfab.core.worker import Task, Job
from norfab.models import Result
from norfab.models.netbox import NetboxFastApiArgs

log = logging.getLogger(__name__)


class NetboxBranchTasks:

    @Task(
        fastapi={"methods": ["DELETE"], "schema": NetboxFastApiArgs.model_json_schema()}
    )
    def delete_branch(
        self,
        job: Job,
        branch: str = None,
        instance: str = None,
    ) -> Result:
        """
        Deletes a branch with the specified name from the NetBox instance.

        Args:
            job (Job): The job context for the operation.
            branch (str, optional): The name of the branch to delete.
            instance (str, optional): The NetBox instance name.

        Returns:
            Result: An object containing the outcome of the deletion operation,
                including whether the branch was found and deleted.
        """
        instance = instance or self.default_instance
        ret = Result(
            task=f"{self.name}:delete_branch",
            result=None,
            resources=[instance],
        )
        nb = self._get_pynetbox(instance)

        job.event(f"Deleting branch '{branch}', Netbo instance '{instance}'")

        nb_branch = nb.plugins.branching.branches.get(name=branch)

        if nb_branch:
            nb_branch.delete()
            ret.result = True
            job.event(f"'{branch}' deleted from '{instance}' Netbox instance")
        else:
            msg = f"'{branch}' branch does not exist in '{instance}' Netbox instance"
            ret.result = None
            ret.messages.append(msg)
            job.event(msg)

        return ret
