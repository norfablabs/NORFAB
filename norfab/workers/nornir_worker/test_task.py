import copy
import hashlib
import json
import logging
import yaml

from typing import Union, Any
from norfab.models import Result
from norfab.core.worker import Task, Job
from nornir_salt.plugins.tasks import nr_test
from nornir_salt.plugins.functions import FFun_functions, ResultSerializer
from nornir_salt.utils.pydantic_models import modelTestsProcessorSuite

log = logging.getLogger(__name__)


class TestTask:
    @Task(fastapi={"methods": ["POST"]})
    def test(
        self,
        job: Job,
        suite: Union[list, str],
        subset: str = None,
        dry_run: bool = False,
        remove_tasks: bool = True,
        failed_only: bool = False,
        return_tests_suite: bool = False,
        job_data: Any = None,
        extensive: bool = False,
        groups: list = None,
        **kwargs: Any,
    ) -> Result:
        """
        Function to test networks using a suite of tests.

        Args:
            job: NorFab Job object containing relevant metadata
            suite (Union[list, str]): URL Path to YAML file with tests or a list of test definitions
                or template URL that resolves to a file path.
            subset (str, optional): List or string with comma-separated non-case-sensitive glob
                patterns to filter tests by name. Ignored if dry_run is True.
            dry_run (bool, optional): If True, returns produced per-host tests suite content only.
            remove_tasks (bool, optional): If False, results will include other tasks output.
            failed_only (bool, optional): If True, returns test results for failed tests only.
            return_tests_suite (bool, optional): If True, returns rendered per-host tests suite
                content in addition to test results using a dictionary with ``results`` and ``suite`` keys.
            job_data (str, optional): URL to YAML file with data or dictionary/list of data
                to pass on to Jinja2 rendering context.
            extensive (bool, optional): return extensive results, equivalent to using these arguments:

                - remove_tasks = False
                - return_tests_suite = True
                - add_details = True
                - to_dict = False

            groups (list, optional): list of test group names to run

            **kwargs: Any additional arguments to pass on to the Nornir service task.

        Returns:
            dict: A dictionary containing the test results. If `return_tests_suite` is True,
                the dictionary will contain both the test results and the rendered test suite.

        Note:
            Result `failed` attribute is set to True if any of the tests failed for any of the hosts.

        Raises:
            RuntimeError: If there is an error in rendering the Jinja2 templates or loading the YAML.
        """
        tests = {}  # dictionary to hold per-host test suites
        # set extensive details flags
        if extensive is True:
            kwargs["add_details"] = True
            kwargs["to_dict"] = False
            remove_tasks = False
            return_tests_suite = True
        add_details = kwargs.get("add_details", False)  # ResultSerializer
        to_dict = kwargs.get("to_dict", True)  # ResultSerializer
        filters = {k: kwargs.get(k) for k in list(kwargs.keys()) if k in FFun_functions}
        ret = Result(task=f"{self.name}:test", result={} if to_dict else [])
        suites = {}  # dictionary to hold combined test suites

        filtered_nornir, ret = self.filter_hosts_and_validate(kwargs, ret)
        if ret.status == "no_match":
            if return_tests_suite is True:
                ret.result = {"test_results": [], "suite": {}}
            return ret

        # download job data
        job_data = self.load_job_data(job_data)

        # generate per-host test suites
        for host_name, host in filtered_nornir.inventory.hosts.items():
            # render suite using Jinja2
            try:
                rendered_suite = self.jinja2_render_templates(
                    templates=[suite],
                    context={
                        "host": host,
                        "norfab": self.client,
                        "job_data": job_data,
                        "netbox": self.add_jinja2_netbox(),
                    },
                    filters=self.add_jinja2_filters(),
                )
            except Exception as e:
                msg = f"{self.name} - '{suite}' Jinja2 rendering failed: '{type(e).__name__}:{e}'"
                raise RuntimeError(msg) from e
            # load suit using YAML
            try:
                tests[host_name] = yaml.safe_load(rendered_suite) or []
            except Exception as e:
                msg = f"{self.name} - '{suite}' YAML load failed: '{type(e).__name__}:{e}'"
                raise RuntimeError(msg) from e

        # validate tests suite
        try:
            _ = modelTestsProcessorSuite(tests=tests)
        except Exception as e:
            msg = f"{self.name} - '{suite}' suite validation failed: '{type(e).__name__}:{e}'"
            raise RuntimeError(msg) from e

        # download pattern, schema and custom function files
        for host_name in tests.keys():
            for index, item in enumerate(tests[host_name]):
                for k in ["pattern", "schema", "function_file"]:
                    if self.is_url(item.get(k)):
                        item[k] = self.fetch_file(
                            item[k], raise_on_fail=True, read=True
                        )
                        if k == "function_file":
                            item["function_text"] = item.pop(k)
                tests[host_name][index] = item

        # save per-host tests suite content before mutating it
        if return_tests_suite is True:
            return_suite = copy.deepcopy(tests)

        log.debug(f"{self.name} - running test '{suite}', is dry run - '{dry_run}'")
        # run dry run task
        if dry_run is True:
            result = filtered_nornir.run(
                task=nr_test, name="tests_dry_run", ret_data_per_host=tests
            )
            ret.result = ResultSerializer(
                result, to_dict=to_dict, add_details=add_details
            )
        # combine per-host tests in suites based on task and arguments
        # Why - to run tests using any nornir service tasks with various arguments
        else:
            for host_name, host_tests in tests.items():
                for test in host_tests:
                    dhash = hashlib.md5()
                    test_args = test.pop("norfab", {})
                    nrtask = test_args.get("nrtask", "cli")
                    assert nrtask in [
                        "cli",
                        "network",
                        "cfg",
                        "task",
                    ], f"{self.name} - unsupported NorFab Nornir Service task '{nrtask}'"
                    test_json = json.dumps(test_args, sort_keys=True).encode()
                    dhash.update(test_json)
                    test_hash = dhash.hexdigest()
                    suites.setdefault(test_hash, {"params": test_args, "tests": {}})
                    suites[test_hash]["tests"].setdefault(host_name, [])
                    suites[test_hash]["tests"][host_name].append(test)
            log.debug(
                f"{self.name} - combined per-host tests suites based on NorFab Nornir Service task and arguments:\n{suites}"
            )
            # run test suites collecting output from devices
            for tests_suite in suites.values():
                nrtask = tests_suite["params"].pop("nrtask", "cli")
                function_kwargs = {
                    **tests_suite["params"],
                    **kwargs,
                    **filters,
                    "tests": tests_suite["tests"],
                    "remove_tasks": remove_tasks,
                    "failed_only": failed_only,
                    "subset": subset,
                    "groups": groups,
                }
                result = getattr(self, nrtask)(
                    job=job, **function_kwargs
                )  # returns Result object
                # save test results into overall results
                if to_dict == True:
                    for host_name, host_res in result.result.items():
                        ret.result.setdefault(host_name, {})
                        ret.result[host_name].update(host_res)
                        # set return result failed to true if any of the tests failed
                        for test_res in host_res.values():
                            if add_details:
                                if test_res["result"] != "PASS":
                                    ret.failed = True
                            elif test_res != "PASS":
                                ret.failed = True
                else:
                    ret.result.extend(result.result)
                    # set return result failed to true if any of the tests failed
                    if any(r["result"] != "PASS" for r in result.result):
                        ret.failed = True

        # check if need to return tests suite content
        if return_tests_suite is True:
            ret.result = {"test_results": ret.result, "suite": return_suite}

        return ret
