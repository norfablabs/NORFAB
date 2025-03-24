import json
import logging
import sys
import importlib.metadata
import yaml
import os
from norfab.core.worker import NFPWorker, Result
from typing import Union, Dict, List

SERVICE = "workflow"

log = logging.getLogger(__name__)


class WorkflowWorker(NFPWorker):
    """
    WorkflowWorker class for managing and executing workflows.

    This class extends the NFPWorker class and provides methods to load inventory,
    retrieve version information, manage workflow results, and execute workflows.

    Attributes:
        init_done_event (threading.Event): Event to signal the completion of initialization.
        workflow_worker_inventory (dict): Inventory loaded from the broker.

    Args:
        inventory: The inventory object to be used by the worker.
        broker (str): The broker address.
        worker_name (str): The name of the worker.
        exit_event (threading.Event, optional): Event to signal the worker to exit. Defaults to None.
        init_done_event (threading.Event, optional): Event to signal that initialization is done. Defaults to None.
        log_level (str, optional): The logging level. Defaults to "WARNING".
        log_queue (object, optional): The logging queue. Defaults to None.
    """

    def __init__(
        self,
        inventory,
        broker: str,
        worker_name: str,
        exit_event=None,
        init_done_event=None,
        log_level: str = "WARNING",
        log_queue: object = None,
    ):
        super().__init__(
            inventory, broker, SERVICE, worker_name, exit_event, log_level, log_queue
        )
        self.init_done_event = init_done_event

        # get inventory from broker
        self.workflow_worker_inventory = self.load_inventory()

        self.init_done_event.set()
        log.info(f"{self.name} - Started")

    def worker_exit(self):
        pass

    def get_version(self):
        """
        Generate a report of the versions of specific Python packages and system information.

        This method collects the version information of several Python packages and system details,
        including the Python version, platform, and a specified language model.

        Returns:
            Result: An object containing a dictionary with the package names as keys and their
                    respective version numbers as values. If a package is not found, its version
                    will be an empty string.
        """
        libs = {
            "norfab": "",
            "python": sys.version.split(" ")[0],
            "platform": sys.platform,
        }
        # get version of packages installed
        for pkg in libs.keys():
            try:
                libs[pkg] = importlib.metadata.version(pkg)
            except importlib.metadata.PackageNotFoundError:
                pass

        return Result(result=libs)

    def get_inventory(self):
        """
        NorFab task to retrieve the workflow's worker inventory.

        Returns:
            Result: An instance of the Result class containing the workflow's worker inventory.
        """
        return Result(result=self.workflow_worker_inventory)

    def remove_empty_results(self, results: Dict) -> Dict:
        """
        Remove empty results from the workflow results.

        Args:
            results (Dict): The workflow results.

        Returns:
            Dict: The workflow results with empty results removed.
        """
        ret = {}
        for step, task_results in results.items():
            ret[step] = {}
            for worker_name, worker_result in task_results.items():
                # add non empty results for tasks that did not fail
                if worker_result["failed"] is False:
                    if worker_result["result"]:
                        ret[step][worker_name] = worker_result
                # add failed tasks irregardless of result content
                else:
                    ret[step][worker_name] = worker_result
        return ret

    def skip_step(self, results: dict, step: str, data: dict) -> bool:
        """
        Determines whether a step should be skipped based on the provided conditions.

        Args:
            results (dict): The results of previous steps.
            step (str): The name of the current step.
            data (dict): A dictionary containing conditions for skipping the step. Possible keys are:

                         - "run_if_fail_any": List of step names. Skip if any of these steps have failed.
                         - "run_if_pass_any": List of step names. Skip if any of these steps have passed.
                         - "run_if_fail_all": List of step names. Skip if all of these steps have failed.
                         - "run_if_pass_all": List of step names. Skip if all of these steps have passed.

        Returns:
            bool: True if the step should be skipped, False otherwise.
        """
        if data.get("run_if_fail_any"):
            # check if have results for all needed steps
            for k in data["run_if_fail_any"]:
                if k not in results:
                    raise KeyError(
                        f"run_if_fail_any check failed for '{step}', '{k}' results not found"
                    )
            # check if any of the steps failed
            for step_name in data["run_if_fail_any"]:
                for worker_result in results[step_name].values():
                    if worker_result["failed"] is True:
                        return (
                            False  # do not skip this step since one of the steps failed
                        )
            else:
                return True  # skip this step since none of the steps failed
        if data.get("run_if_pass_any"):
            # check if have results for all needed steps
            for k in data["run_if_pass_any"]:
                if k not in results:
                    raise KeyError(
                        f"run_if_pass_any check failed for '{step}', '{k}' results not found"
                    )
            # check if any of the steps passed
            for step_name, job_results in results.items():
                if step_name not in data["run_if_pass_any"]:
                    continue
                for worker_name, worker_result in job_results.items():
                    if worker_result["failed"] is False:
                        return (
                            False  # do not skip this step since one of the steps passed
                        )
                else:
                    return True  # skip this step since none of the steps passed
        if data.get("run_if_fail_all"):
            # check if have results for all needed steps
            for k in data["run_if_fail_all"]:
                if k not in results:
                    raise KeyError(
                        f"run_if_fail_all check failed for '{step}', '{k}' results not found"
                    )
            for step_name, job_results in results.items():
                if step_name not in data["run_if_fail_all"]:
                    continue
                for worker_name, worker_result in job_results.items():
                    if worker_result["failed"] is False:
                        return True  # skip this step since not all steps failed
        if data.get("run_if_pass_all"):
            # check if have results for all needed steps
            for k in data["run_if_pass_all"]:
                if k not in results:
                    raise KeyError(
                        f"run_if_pass_all check failed for '{step}', '{k}' results not found"
                    )
            for step_name, job_results in results.items():
                if step_name not in data["run_if_pass_all"]:
                    continue
                for worker_name, worker_result in job_results.items():
                    if worker_result["failed"] is True:
                        return True  # skip this step since not all steps passed

        return False  # do not skip this step

    def stop_workflow(self, result: dict, step: str, data: dict) -> bool:
        """
        Determines whether to stop the workflow based on the result of
        a specific step and provided data.

        Args:
            result (dict): The results dictionary for given step.
            step (str): The specific step to check within the result.
            data (dict): A dictionary containing step data, including a flag
                to stop if a failure occurs.

        Returns:
            bool: True if the workflow should be stopped due to a failure in
                the specified step and the stop_on_failure flag is set; otherwise, False.
        """
        if data.get("stop_on_failure") is True:
            for step_name, job_results in result.items():
                for worker_name, worker_result in job_results.items():
                    if worker_result["failed"] is True:
                        return True  # stop the workflow since a failure occurred
        return False

    def run(self, workflow: Union[str, Dict]) -> Dict:
        """
        Executes a workflow defined by a dictionary.

        Args:
            workflow (Union[str, Dict]): The workflow to execute. This can be a URL to a YAML file.
            remove_empty_results (bool, optional): Whether to remove empty results from the final output. Defaults to True.

        Returns:
            Dict: A dictionary containing the results of the workflow execution.

        Raises:
            ValueError: If the workflow is not a valid URL or dictionary.
        """
        ret = Result(task=f"{self.name}:run", result={})

        # load workflow from URL
        if self.is_url(workflow):
            workflow_name = (
                os.path.split(workflow)[-1].replace(".yaml", "").replace(".yml", "")
            )
            workflow = self.jinja2_render_templates([workflow])
            workflow = yaml.safe_load(workflow)

        # extract workflow parameters
        workflow_name = workflow.pop("name", "workflow")
        workflow_description = workflow.pop("description", "")
        remove_empty_results = workflow.pop("remove_empty_results", True)

        self.event(f"Starting workflow '{workflow_name}'")
        log.info(f"Starting workflow '{workflow_name}': {workflow_description}")

        ret.result[workflow_name] = {}

        # run each step in the workflow
        for step, data in workflow.items():

            # check if need to skip step based on run_if_x flags
            if self.skip_step(ret.result[workflow_name], step, data):
                ret.result[workflow_name][step] = {
                    "all": {
                        "failed": True,
                        "result": None,
                        "status": "skipped",
                        "task": data["task"],
                        "errors": [],
                        "messages": [],
                        "juuid": None,
                    }
                }
                self.event(
                    f"Skipping workflow step '{step}', one of run_if_x conditions not satisfied"
                )
                continue

            self.event(f"Doing workflow step '{step}'")

            ret.result[workflow_name][step] = self.client.run_job(
                service=data["service"],
                task=data["task"],
                workers=data.get("workers", "all"),
                kwargs=data.get("kwargs", {}),
                args=data.get("args", []),
                timeout=data.get("timeout", 600),
            )

            # check if need to stop workflow based on stop_if_fail flag
            if self.stop_workflow(ret.result[workflow_name][step], step, data):
                break

        if remove_empty_results:
            ret.result[workflow_name] = self.remove_empty_results(
                ret.result[workflow_name]
            )

        return ret
