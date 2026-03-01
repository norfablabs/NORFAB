from typing import Union, Any

from norfab.models import Result
from norfab.core.worker import Task, Job
from norfab.core.exceptions import UnsupportedPluginError
from nornir_salt.plugins.functions import FFun_functions, ResultSerializer
from nornir_napalm.plugins.tasks import napalm_get


class ParseTask:
    @Task(fastapi={"methods": ["POST"]})
    def parse(
        self,
        job: Job,
        plugin: str = "napalm",
        getters: Union[str, list] = "get_facts",
        template: str = None,
        commands: Union[str, list] = None,
        to_dict: bool = True,
        add_details: bool = False,
        **kwargs: Any,
    ) -> Result:
        """
        Parse network device output using specified plugin and options.

        Args:
            job: NorFab Job object containing relevant metadata
            plugin (str): The plugin to use for parsing. Options are:

                - napalm - parse devices output using NAPALM getters
                - ttp - use TTP Templates to parse devices output
                - textfsm - use TextFSM templates to parse devices output

            getters (str): The getters to use with the "napalm" plugin.
            template (str): The template to use with the "ttp" or "textfsm" plugin.
            commands (list): The list of commands to run with the "ttp" or "textfsm" plugin.
            to_dict (bool): Whether to convert the result to a dictionary.
            add_details (bool): Whether to add details to the result.
            **kwargs: Additional keyword arguments to pass to the plugin.

        Returns:
            Result: A Result object containing the parsed data.

        Raises:
            UnsupportedPluginError: If the specified plugin is not supported.
        """
        filters = {k: kwargs.get(k) for k in list(kwargs.keys()) if k in FFun_functions}
        ret = Result(task=f"{self.name}:parse", result={} if to_dict else [])

        filtered_nornir, ret = self.filter_hosts_and_validate(kwargs, ret)
        if ret.status == "no_match":
            return ret

        if plugin == "napalm":
            nr = self._add_processors(filtered_nornir, kwargs, job)  # add processors
            result = nr.run(task=napalm_get, getters=getters, **kwargs)
            ret.result = ResultSerializer(
                result, to_dict=to_dict, add_details=add_details
            )
            ret.failed = result.failed  # failed is true if any of the hosts failed
        elif plugin == "ttp":
            result = self.cli(
                job=job,
                commands=commands or [],
                run_ttp=template,
                **filters,
                **kwargs,
                to_dict=to_dict,
                add_details=add_details,
                plugin="netmiko",
            )
            ret.result = result.result
        elif plugin == "textfsm":
            result = self.cli(
                job=job,
                commands=commands,
                **filters,
                **kwargs,
                to_dict=to_dict,
                add_details=add_details,
                use_textfsm=True,
                textfsm_template=template,
                plugin="netmiko",
            )
            ret.result = result.result
        else:
            raise UnsupportedPluginError(f"Plugin '{plugin}' not supported")

        return ret
