import logging

from typing import Any
from norfab.models import Result
from norfab.core.worker import Task, Job
from nornir_salt.plugins.functions import ResultSerializer

log = logging.getLogger(__name__)


class TaskTask:
    @Task(fastapi={"methods": ["POST"]})
    def task(self, job: Job, plugin: str, **kwargs: Any) -> Result:
        """
        Execute a Nornir task plugin.

        This method dynamically imports and executes a specified Nornir task plugin,
        using the provided arguments and keyword arguments. The `plugin` attribute
        can refer to a file to fetch from a file service, which must contain a function
        named `task` that accepts a Nornir task object as the first positional argument.

        Example of a custom task function file:

        ```python
        # define connection name for RetryRunner to properly detect it
        CONNECTION_NAME = "netmiko"

        # create task function
        def task(nornir_task_object, **kwargs):
            pass
        ```

        Note:
            The `CONNECTION_NAME` must be defined within the custom task function file if
            RetryRunner is in use. Otherwise, the connection retry logic is skipped, and
            connections to all hosts are initiated simultaneously up to the number of `num_workers`.

        Args:
            job: NorFab Job object containing relevant metadata
            plugin (str): The path to the plugin function to import, or a NorFab
                URL to download a custom task or template URL that resolves to a file.
            **kwargs (Any): Additional arguments to pass to the specified task plugin.

        Notes:
            - `add_details` (bool): If True, adds task execution details to the results.
            - `to_dict` (bool): If True, returns results as a dictionary. Defaults to True.
            - Host filters: keys matching `FFun_functions` are treated as Nornir host filters.

        Returns:
            Result: An instance of the Result class containing the task execution results.

        Raises:
            FileNotFoundError: If the specified plugin file cannot be downloaded.
        """
        # extract attributes
        add_details = kwargs.pop("add_details", False)  # ResultSerializer
        to_dict = kwargs.pop("to_dict", True)  # ResultSerializer
        ret = Result(task=f"{self.name}:task", result={} if to_dict else [])

        filtered_nornir, no_match_result = self.filter_hosts_and_validate(kwargs, ret)
        if ret.status == "no_match":
            return ret

        # download task from broker and load it
        if plugin.startswith("nf://"):
            function_text = self.fetch_file(plugin)
            if function_text is None:
                raise FileNotFoundError(
                    f"{self.name} - '{plugin}' task plugin download failed"
                )

            # load task function running exec
            globals_dict = {}
            exec(function_text, globals_dict, globals_dict)
            task_function = globals_dict["task"]
        # import task function
        elif "." in plugin:
            # below same as "from nornir.plugins.tasks import task_fun as task_function"
            module_name, func_name = plugin.rsplit(".", 1)
            module = __import__(module_name, fromlist=[func_name])  # nosec
            task_function = getattr(module, func_name)
        else:
            raise RuntimeError(
                f"{self.name} - '{plugin}' task should either be a path "
                f"to a file or a module import string"
            )

        nr = self._add_processors(filtered_nornir, kwargs, job)  # add processors

        # run task
        log.debug(f"{self.name} - running Nornir task '{plugin}', kwargs '{kwargs}'")
        with self.connections_lock:
            result = nr.run(task=task_function, **kwargs)

        ret.failed = result.failed  # failed is true if any of the hosts failed
        ret.result = ResultSerializer(result, to_dict=to_dict, add_details=add_details)

        self.watchdog.connections_clean()

        return ret
