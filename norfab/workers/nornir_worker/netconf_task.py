from typing import Any

from norfab.core.worker import Job, Task
from norfab.models import Result


class NetconfTask:
    @Task(fastapi={"methods": ["POST"]})
    def netconf(
        self,
        job: Job,
        call: str,
        plugin: str = "ncclient",
        data: str = None,
        **kwargs: Any,
    ) -> Result:
        """
        Interact with devices using NETCONF protocol utilizing one of the supported plugins.

        This method provides a unified interface to interact with network devices using
        NETCONF protocol through different backend plugins.

        Args:
            job (Job): NorFab Job object containing relevant metadata.
            call (str): The ncclient manager or scrapli netconf object method to call.
            plugin (str, optional): Name of netconf plugin to use. Available plugins:

                - ``ncclient`` (default): ``nornir-salt`` built-in plugin that uses ``ncclient``
                  library to interact with devices. Uses `ncclient_call`_ task plugin.
                - ``scrapli``: Uses ``scrapli_netconf`` connection plugin that is part of
                  ``nornir_scrapli`` library. Uses `scrapli_netconf_call`_ task plugin.

            data (str, optional): Path to file for ``rpc`` method call or rpc content.
            **kwargs (Any): Additional arguments to pass to the underlying plugin.

                - method_name (str): Name of method to provide docstring for, used only by ``help`` call.

        Returns:
            Result: A Result object containing the NETCONF operation results.

        Note:
            Special ``call`` arguments/methods available:

            - ``dir``: Returns methods supported by Ncclient connection manager object.
            - ``help``: Returns ``method_name`` docstring.
            - ``transaction``: Same as ``edit_config``, but runs a more reliable workflow:

                1. Lock target configuration datastore
                2. If server supports it - Discard previous changes if any
                3. Perform configuration edit using RPC specified in ``edit_rpc`` argument
                4. If server supports it - validate configuration if ``validate`` argument is True
                5. If server supports it - do commit confirmed if ``confirmed`` argument is True
                   using ``confirm_delay`` timer with ``commit_arg`` argument
                6. If confirmed commit requested, wait for ``commit_final_delay`` timer before
                   sending final commit, final commit does not use ``commit_arg`` arguments
                7. If server supports it - do commit operation
                8. Unlock target configuration datastore
                9. If server supports it - discard all changes if any of steps 3, 4, 5 or 7 fail
                10. Return results list of dictionaries keyed by step name

        Warning:
            Beware of differences in keywords required by different plugins, e.g. ``filter`` for
            ``ncclient`` vs ``filter_``/``filters`` for ``scrapli_netconf``. Refer to modules' API
            documentation for required arguments.

        Examples:
            Examples using ``ncclient`` plugin::

                salt nrp1 nr.nc server_capabilities FB="*"
                salt nrp1 nr.nc get_config filter='["subtree", "salt://rpc/get_config_data.xml"]' source="running"
                salt nrp1 nr.nc edit_config target="running" config="salt://rpc/edit_config_data.xml" FB="ceos1"
                salt nrp1 nr.nc transaction target="candidate" config="salt://rpc/edit_config_data.xml"
                salt nrp1 nr.nc commit
                salt nrp1 nr.nc rpc data="salt://rpc/iosxe_rpc_edit_interface.xml"
                salt nrp1 nr.nc get_schema identifier="ietf-interfaces"
                salt nrp1 nr.nc get filter='<system-time xmlns="http://cisco.com/ns/yang/Cisco-IOS-XR-shellutil-oper"/>'

            Examples using ``scrapli_netconf`` plugin::

                salt nrp1 nr.nc get filter_=salt://rpc/get_config_filter_ietf_interfaces.xml plugin=scrapli
                salt nrp1 nr.nc get_config source=running plugin=scrapli
                salt nrp1 nr.nc server_capabilities FB="*" plugin=scrapli
                salt nrp1 nr.nc rpc filter_=salt://rpc/get_config_rpc_ietf_interfaces.xml plugin=scrapli
                salt nrp1 nr.nc transaction target="candidate" config="salt://rpc/edit_config_ietf_interfaces.xml" plugin=scrapli

            Python API usage from Salt-Master::

                import salt.client
                client = salt.client.LocalClient()

                task_result = client.cmd(
                    tgt="nrp1",
                    fun="nr.nc",
                    arg=["get_config"],
                    kwarg={"source": "running", "plugin": "ncclient"},
                )

            Using special calls::

                salt nrp1 nr.nc dir
                salt nrp1 nr.nc help method_name=edit_config
                salt nrp1 nr.nc transaction target="candidate" config="salt://path/to/config_file.xml" FB="*core-1"

        .. _ncclient_call: https://nornir-salt.readthedocs.io/en/latest/Tasks/ncclient_call.html
        .. _scrapli_netconf_call: https://nornir-salt.readthedocs.io/en/latest/Tasks/scrapli_netconf_call.html
        """
        # TODO implement files download and rendering
        # kwargs.setdefault(
        #     "render", ["rpc", "config", "data", "filter", "filter_", "filters"]
        # )

        # decide on plugin to use
        if plugin.lower() == "ncclient":
            task_fun = "nornir_salt.plugins.tasks.ncclient_call"
            kwargs["connection_name"] = "ncclient"
            # TODO implement filters handling

        elif plugin.lower() == "scrapli":
            task_fun = "nornir_salt.plugins.tasks.scrapli_netconf_call"
            kwargs["connection_name"] = "scrapli_netconf"
            # TODO implement filters handling

        # run task
        return self.task(job=job, plugin=task_fun, call=call, **kwargs)
