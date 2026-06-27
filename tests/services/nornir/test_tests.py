import pprint

import pytest

pytestmark = [pytest.mark.nornir, pytest.mark.tests, pytest.mark.task_nornir_tests]


@pytest.mark.task_nornir_tests
class TestNornirTest:
    def test_nornir_test_suite(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={"suite": "nf://nornir_test_suites/suite_1.txt"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results[
                "failed"
            ], f"{worker} some tests failed, result should be failed as well"
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name, test_res in res.items():
                    assert (
                        "Traceback" not in test_res
                    ), f"{worker}:{host}:{test_name} test output contains error"
                    assert test_res in [
                        "PASS",
                        "FAIL",
                    ], f"{worker}:{host}:{test_name} unexpected test result"

    def test_nornir_test_suite_with_groups(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/test_suite_with_groups.txt",
                "FC": "spine",
                "groups": ["SYS"],
                "add_details": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name, test_res in res.items():
                    assert (
                        "SYS" in test_res["groups"]
                    ), f"{worker}:{host}:{test_name} unexpected test, not part of SYS group"

    def test_nornir_test_suite_with_comments(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/test_suite_with_comments.txt",
                "FC": "spine",
                "add_details": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name, test_res in res.items():
                    assert (
                        "comments" in test_res
                    ), f"{worker}:{host}:{test_name} no comments in result"
                    assert (
                        "description" in test_res
                    ), f"{worker}:{host}:{test_name} no description in result"

    def test_nornir_test_suite_empty_suite(self, nfclient):
        # this test renders empty test for any host except for spine 1
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/suite_empty_tests.txt",
                "FC": "spine",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name, test_res in res.items():
                    assert (
                        "Traceback" not in test_res
                    ), f"{worker}:{host}:{test_name} test output contains error"
                    assert test_res in [
                        "PASS",
                        "FAIL",
                    ], f"{worker}:{host}:{test_name} unexpected test result"

    def test_nornir_test_suite_with_details(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "add_details": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results[
                "failed"
            ], f"{worker} some tests failed, result should be failed as well"
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name, test_res in res.items():
                    assert isinstance(test_res, dict)
                    assert test_res["result"] in [
                        "PASS",
                        "FAIL",
                    ], f"{worker}:{host}:{test_name} unexpected test result"

    def test_nornir_test_suite_list_result(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={"suite": "nf://nornir_test_suites/suite_1.txt", "to_dict": False},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results[
                "failed"
            ], f"{worker} some tests failed, result should be failed as well"
            assert results["result"], f"{worker} returned no test results"
            assert isinstance(
                results["result"], list
            ), f"{worker} did not return list result"
            for host_res in results["result"]:
                assert isinstance(host_res, dict)
                assert host_res["result"] in [
                    "PASS",
                    "FAIL",
                ], f"{worker} unexpected test result - {host_res}"

    def test_nornir_test_suite_list_result_with_details(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "to_dict": False,
                "add_details": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results[
                "failed"
            ], f"{worker} some tests failed, result should be failed as well"
            assert results["result"], f"{worker} returned no test results"
            assert isinstance(
                results["result"], list
            ), f"{worker} did not return list result"
            for host_res in results["result"]:
                assert isinstance(host_res, dict)
                assert host_res["result"] in [
                    "PASS",
                    "FAIL",
                ], f"{worker} unexpected test result - {host_res}"
                assert "exception" in host_res
                assert "diff" in host_res, f"{worker} details added"

    def test_nornir_test_suite_template(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={"suite": "nf://nornir_test_suites/suite_2.txt"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert (
                results["failed"] is False
            ), f"{worker} no tests failed, result should not be failed as well"
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name, test_res in res.items():
                    assert (
                        "Traceback" not in test_res
                    ), f"{worker}:{host}:{test_name} test output contains error"
                    assert test_res in [
                        "PASS",
                        "FAIL",
                    ], f"{worker}:{host}:{test_name} unexpected test result"

    def test_nornir_test_suite_subset(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "subset": "check*version",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                assert (
                    len(res) == 1
                ), f"{worker}:{host} was expecting results for single test only"
                assert (
                    "check ceos version" in res
                ), f"{worker}:{host} was expecting 'check ceos version' results"

    def test_nornir_test_dry_run(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                assert (
                    "tests_dry_run" in res
                ), f"{worker}:{host} no tests_dry_run results"
                assert isinstance(
                    res["tests_dry_run"], list
                ), f"{worker}:{host} was expecting list of tests"
                for i in res["tests_dry_run"]:
                    assert all(
                        k in i for k in ["name", "pattern", "task", "test"]
                    ), f"{worker}:{host} test missing some keys"

    def test_nornir_test_to_dict_true(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "to_dict": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name, test_res in res.items():
                    assert (
                        "Traceback" not in test_res
                    ), f"{worker}:{host}:{test_name} test output contains error"
                    assert test_res in [
                        "PASS",
                        "FAIL",
                    ], f"{worker}:{host}:{test_name} unexpected test result"

    def test_nornir_test_to_dict_false(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "to_dict": False,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            assert isinstance(results["result"], list)
            for i in results["result"]:
                assert all(
                    k in i for k in ["host", "name", "result"]
                ), f"{worker} test output does not contains all keys"

    def test_nornir_test_remove_tasks_false(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "remove_tasks": False,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                assert len(res) > 2, f"{worker}:{host} not having tasks output"
                for task_name, task_res in res.items():
                    assert (
                        "Traceback" not in task_res
                    ), f"{worker}:{host}:{test_name} test output contains error"

    def test_nornir_test_failed_only_true(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "failed_only": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name, test_res in res.items():
                    assert (
                        "Traceback" not in test_res
                    ), f"{worker}:{host}:{test_name} test output contains error"
                    assert test_res in [
                        "FAIL"
                    ], f"{worker}:{host}:{test_name} unexpected test result"

    def test_nornir_test_suite_non_existing_file(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={"suite": "nf://nornir_test_suites/suite_non_existing.txt"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert (
                "FileNotFoundError" in results["errors"][0]
            ), f"{worker} was expecting download to fail"

    def test_nornir_test_suite_bad_yaml_file(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={"suite": "nf://nornir_test_suites/suite_bad_yaml.txt"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert (
                "YAML load failed" in results["errors"][0]
            ), f"{worker} was expecting YAML load to fail"

    def test_nornir_test_suite_bad_jinja2(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={"suite": "nf://nornir_test_suites/suite_bad_jinja2.txt"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert (
                "Jinja2 template parsing failed" in results["errors"][0]
            ), f"{worker} was expecting Jinja2 rendering to fail"

    def test_nornir_test_suite_custom_functions_files(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/test_suite_custom_fun.txt",
                "FC": "ceos-spine-",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name in [
                    "test_cust_fun_1",
                    "test_cust_fun_2 show clock NTP",
                    "test_cust_fun_2 show ip int brief NTP",
                    "test_cust_fun_3 Test IP config",
                    "test_cust_fun_3 Test NTP",
                ]:
                    assert (
                        test_name in res
                    ), f"{worker}:{host} missing '{test_name}' results"
                for test_name, test_res in res.items():
                    assert (
                        "Traceback" not in test_res
                    ), f"{worker}:{host}:{test_name} test output contains error"
                    assert test_res in [
                        "FAIL"
                    ], f"{worker}:{host}:{test_name} unexpected test result"

    def test_nornir_test_with_nftask_to_dict_false(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/test_nornir_test_with_nftask.txt",
                "FC": "ceos-spine-",
                "add_details": True,
                "to_dict": False,
            },
        )
        pprint.pprint(ret)
        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for i in results["result"]:
                assert (
                    i["result"] == "PASS"
                ), f"{worker}:{i['host']}:{i['name']} unexpected test result"

    def test_nornir_test_with_nftask_to_dict_true(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/test_nornir_test_with_nftask.txt",
                "FC": "ceos-spine-",
                "add_details": True,
                "to_dict": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name, test_res in res.items():
                    assert not test_res[
                        "exception"
                    ], f"{worker}:{host}:{test_name} test output contains error"
                    assert (
                        test_res["result"] == "PASS"
                    ), f"{worker}:{host}:{test_name} unexpected test result"

    def test_nornir_test_suite_with_includes_dry_run(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/test_suite_with_include.txt",
                "FC": "ceos-spine-",
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                assert (
                    len(res["tests_dry_run"]) == 3
                ), f"{worker}:{host} not all tests rendered"
                assert res["tests_dry_run"][0]["name"] == "check hostname value"
                assert res["tests_dry_run"][1]["name"] == "check version"
                assert res["tests_dry_run"][2]["name"] == "check loopback0 present"

    def test_nornir_test_suite_with_includes(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/test_suite_with_include.txt",
                "FC": "ceos-spine-",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name, test_res in res.items():
                    assert test_name in [
                        "check hostname value",
                        "check loopback0 present",
                        "check version",
                    ], f"{worker}:{host}:{test_name} unexpected test result"

    def test_nornir_test_suite_with_job_data_dict(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/test_nornir_test_suite_with_job_data.txt",
                "FC": "ceos-spine-",
                "job_data": {"some_conditional": True},
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                assert (
                    len(res["tests_dry_run"]) == 1
                ), f"{worker}:{host} was expecting only one test item"
                assert (
                    res["tests_dry_run"][0]["name"] == "check ceos version"
                ), f"{worker}:{host} unexpected tes name"

    @pytest.mark.skip(reason="TBD")
    def test_nornir_test_suite_pattern_files(self, nfclient):
        pass

    def test_nornir_test_markdown_brief(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "FC": ["spine", "leaf"],
            },
            markdown=True,
        )
        print(ret)
        assert "No hosts test suites available" in ret
        assert "No hosts outputs available" in ret
        assert "No detailed results available" in ret
        assert "|Host|Test Name|Result|Exception|" in ret
        assert "Input Arguments (kwargs)" in ret

    def test_nornir_test_with_extensive(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "FC": ["spine", "leaf"],
                "extensive": True,
            },
        )
        pprint.pprint(ret)
        for worker, results in ret.items():
            assert (
                "test_results" in results["result"]
            ), f"{worker} returned no test results"
            assert "suite" in results["result"], f"{worker} returned no tests suite"

    def test_nornir_test_markdown_with_extensive(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "FC": ["spine", "leaf"],
                "extensive": True,
            },
            markdown=True,
        )
        print(ret)
        assert "|Host|Test Name|Result|Exception|" in ret
        assert "Input Arguments (kwargs)" in ret
        assert "Test suites definitions for each host" in ret
        assert (
            "Expandable sections containing outputs collected during test execution for each host"
            in ret
        )
        assert (
            "Hierarchical expandable sections organized by device, then test name, containing complete test result details"
            in ret
        )

    def test_nornir_test_markdown_tests_have_comments(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            kwargs={
                "suite": "nf://nornir_test_suites/test_suite_with_comments.txt",
                "FC": ["spine", "leaf"],
                "extensive": True,
            },
            markdown=True,
        )
        print(ret)
        assert "comments foo" in ret, "No comments in output"
        assert "**Groups:** SYS" in ret, "No groups in output"
        assert "**Description:** bar" in ret, "No description in output"


# ----------------------------------------------------------------------------
# NORNIR.NETWORK FUNCTION TESTS
# ----------------------------------------------------------------------------
