import pprint
import pytest

pytestmark = [pytest.mark.nornir, pytest.mark.parse, pytest.mark.task_nornir_parse]


@pytest.mark.task_nornir_parse
class TestNornirParseTasks:

    def test_nornir_parse_napalm_get_facts(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_napalm",
            workers=["nornir-worker-1"],
            kwargs={"getters": "get_facts"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert (
                    "napalm_get" in res
                ), f"{worker}:{host} did not return napalm_get result"
                assert res["napalm_get"][
                    "get_facts"
                ], f"{worker}:{host} get facts are empty"

    def test_nornir_parse_napalm_unsupported_getter(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_napalm",
            workers=["nornir-worker-1"],
            kwargs={"getters": "get_ntp_peers"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert (
                results["failed"] is True
            ), f"{worker} should have failed to run the task"
            for host, res in results["result"].items():
                assert "NotImplementedError" in res["napalm_get"]

    def test_nornir_parse_napalm_multiple_getters(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_napalm",
            workers=["nornir-worker-1"],
            kwargs={"getters": ["get_facts", "get_interfaces"]},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert (
                    "napalm_get" in res
                ), f"{worker}:{host} did not return napalm_get result"
                assert res["napalm_get"][
                    "get_interfaces"
                ], f"{worker}:{host} get_interfaces are empty"
                assert res["napalm_get"][
                    "get_facts"
                ], f"{worker}:{host} get_facts are empty"

    def test_nornir_parse_ttp_templates_template_with_commands(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_ttp",
            workers=["nornir-worker-1"],
            kwargs={
                "template": "ttp://platform/arista_eos_show_hostname.txt",
                "commands": "show hostname",
                "enable": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert (
                    "fqdn" in res[0] and "hostname" in res[0]
                ), f"{host} unexpected parsing results"

    def test_nornir_parse_ttp_templates_template(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_ttp",
            workers=["nornir-worker-1"],
            kwargs={
                "template": "ttp://misc/Netbox/parse_arista_eos_config.txt",
                "enable": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert res[0] and len(res[0]) > 2, f"{host} unexpected parsing results"

    def test_nornir_parse_ttp_file_template(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_ttp",
            workers=["nornir-worker-1"],
            kwargs={
                "template": "nf://ttp/parse_eos_intf.txt",
                "enable": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert res and len(res) > 2, f"{host} unexpected parsing results"

    def test_nornir_parse_ttp_plugin_netmiko(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_ttp",
            workers=["nornir-worker-1"],
            kwargs={
                "template": "nf://ttp/parse_eos_intf.txt",
                "enable": True,
                "plugin": "netmiko",
                "use_ps": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert res and len(res) > 2, f"{host} unexpected parsing results"

    def test_nornir_parse_ttp_plugin_scrapli(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_ttp",
            workers=["nornir-worker-1"],
            kwargs={
                "template": "nf://ttp/parse_eos_intf.txt",
                "plugin": "scrapli",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert res and len(res) > 2, f"{host} unexpected parsing results"

    def test_nornir_parse_ttp_plugin_napalm(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_ttp",
            workers=["nornir-worker-1"],
            kwargs={
                "template": "Clock source: {{ source }}",
                "commands": "show clock",
                "plugin": "napalm",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert res, f"{host} unexpected parsing results"

    def test_nornir_parse_inline_ttp_template(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_ttp",
            workers=["nornir-worker-1"],
            kwargs={
                "template": "Clock source: {{ source }}",
                "commands": "show clock",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert (
                    res[0] and "source" in res[0]
                ), f"{host} unexpected parsing results"

    def test_nornir_parse_ttp_templates_inventory_getter(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_ttp",
            workers=["nornir-worker-1"],
            kwargs={"get": "inventory", "FC": "spine", "enable": True},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert len(res) > 0, f"{host} unexpected parsing results"

    def test_nornir_parse_ttp_requires_template_or_get(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_ttp",
            workers=["nornir-worker-1"],
            kwargs={"commands": "show clock"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is True, f"{worker} should fail validation"
            assert (
                "ValidationError" in results["errors"][0]
            ), f"{worker} did not raise ValidationError"
            assert (
                "Either 'template' or 'get' must be provided" in results["errors"][0]
            ), f"{worker} returned unexpected validation error"

    # parse_napalm additional tests

    def test_nornir_parse_napalm_to_dict_false(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_napalm",
            workers=["nornir-worker-1"],
            kwargs={"getters": "get_facts", "to_dict": False},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert isinstance(
                results["result"], list
            ), f"{worker} result is not a list when to_dict=False"
            assert results["result"], f"{worker} returned empty results"

    def test_nornir_parse_napalm_add_details_true(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_napalm",
            workers=["nornir-worker-1"],
            kwargs={"getters": "get_facts", "add_details": True},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert results["result"], f"{worker} returned no results"
            for host, res in results["result"].items():
                assert "napalm_get" in res, f"{worker}:{host} missing napalm_get key"
                # add_details includes task metadata fields alongside the getter results
                assert isinstance(
                    res["napalm_get"], dict
                ), f"{worker}:{host} napalm_get is not a dict"

    def test_nornir_parse_napalm_with_host_filter(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_napalm",
            workers=["nornir-worker-1"],
            kwargs={"getters": "get_facts", "FC": "spine"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert results["result"], f"{worker} returned no results"
            for host in results["result"]:
                assert "spine" in host, f"{worker} returned unexpected host '{host}'"

    def test_nornir_parse_napalm_no_matching_hosts(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_napalm",
            workers=["nornir-worker-1"],
            kwargs={"getters": "get_facts", "FC": "nonexistent_host_xyz"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert (
                results["failed"] is False
            ), f"{worker} should not mark as failed for no-match"
            assert not results["result"], f"{worker} unexpectedly returned results"

    # parse_ttp additional tests

    def test_nornir_parse_ttp_structure_flat_list(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_ttp",
            workers=["nornir-worker-1"],
            kwargs={
                "template": "Clock source: {{ source }}",
                "commands": "show clock",
                "structure": "flat_list",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert results["result"], f"{worker} returned no results"
            for host, res in results["result"].items():
                assert isinstance(
                    res, list
                ), f"{worker}:{host} result is not a list for flat_list structure"
                assert res, f"{worker}:{host} flat_list result is empty"

    def test_nornir_parse_ttp_structure_list(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_ttp",
            workers=["nornir-worker-1"],
            kwargs={
                "template": "Clock source: {{ source }}",
                "commands": "show clock",
                "structure": "list",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert results["result"], f"{worker} returned no results"
            for host, res in results["result"].items():
                assert isinstance(
                    res, list
                ), f"{worker}:{host} result is not a list for list structure"
                assert res, f"{worker}:{host} list result is empty"

    def test_nornir_parse_ttp_structure_dictionary(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_ttp",
            workers=["nornir-worker-1"],
            kwargs={
                "template": "Clock source: {{ source }}",
                "commands": "show clock",
                "structure": "dictionary",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert results["result"], f"{worker} returned no results"
            for host, res in results["result"].items():
                assert isinstance(
                    res, dict
                ), f"{worker}:{host} result is not a dict for dictionary structure"

    def test_nornir_parse_ttp_strict_false_no_match(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_ttp",
            workers=["nornir-worker-1"],
            kwargs={
                "template": "NONMATCHING_PATTERN_XYZ {{ field }}",
                "commands": "show clock",
                "strict": False,
            },
        )
        pprint.pprint(ret)

        # with strict=False, empty TTP results should not raise an error
        for worker, results in ret.items():
            assert (
                results["failed"] is False
            ), f"{worker} should not fail when strict=False and no TTP match"

    def test_nornir_parse_ttp_strict_true_no_match(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_ttp",
            workers=["nornir-worker-1"],
            kwargs={
                "template": "NONMATCHING_PATTERN_XYZ {{ field }}",
                "commands": "show clock",
                "strict": True,
            },
        )
        pprint.pprint(ret)

        # with strict=True, empty TTP results should cause task failure
        for worker, results in ret.items():
            assert (
                results["failed"] is True
            ), f"{worker} should fail when strict=True and no TTP match"

    def test_nornir_parse_ttp_commands_as_list(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_ttp",
            workers=["nornir-worker-1"],
            kwargs={
                "template": "Clock source: {{ source }}",
                "commands": ["show clock"],
                "strict": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert results["result"], f"{worker} returned no results"
            for host, res in results["result"].items():
                assert res, f"{worker}:{host} TTP parsing results are empty"

    def test_nornir_parse_ttp_with_host_filter(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_ttp",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "template": "Clock source: {{ source }}",
                "commands": "show clock",
                "FC": "spine",
            },
        )
        pprint.pprint(ret)

        assert ret["nornir-worker-1"]["result"]["ceos-spine-1"] == [{"source": "local"}]
        assert ret["nornir-worker-1"]["result"]["ceos-spine-2"] == [{"source": "local"}]
        assert (
            ret["nornir-worker-2"]["result"] == {}
        ), f"{nornir-worker-2} returned unexpected results"

    def test_nornir_parse_ttp_no_matching_hosts(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_ttp",
            workers=["nornir-worker-1"],
            kwargs={
                "template": "Clock source: {{ source }}",
                "commands": "show clock",
                "FC": "nonexistent_host_xyz",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} should not fail for no-match"
            assert not results["result"], f"{worker} unexpectedly returned results"

    def test_nornir_parse_textfsm(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_textfsm",
            workers=["nornir-worker-1"],
            kwargs={
                "commands": "show hostname",
                "FC": "spine",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} should not fail for no-match"
            for host, res in results["result"].items():
                for command, parsing_res in res.items():
                    assert (
                        "fqdn" in parsing_res[0] and "hostname" in parsing_res[0]
                    ), f"{host} returned unexpected textfsm parsing results"

    def test_nornir_parse_textfsm_multiple_commands(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_textfsm",
            workers=["nornir-worker-1"],
            kwargs={
                "commands": ["show hostname", "show version"],
                "FC": "spine",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert results["result"], f"{worker} returned no results"
            for host, res in results["result"].items():
                assert (
                    len(res) == 2
                ), f"{host} expected 2 command results, got {len(res)}"

    def test_nornir_parse_textfsm_to_dict_false(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_textfsm",
            workers=["nornir-worker-1"],
            kwargs={
                "commands": "show hostname",
                "FC": "spine",
                "to_dict": False,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert isinstance(
                results["result"], list
            ), f"{worker} result is not a list when to_dict=False"
            assert results["result"], f"{worker} returned empty results"

    def test_nornir_parse_textfsm_add_details_true(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_textfsm",
            workers=["nornir-worker-1"],
            kwargs={
                "commands": "show hostname",
                "FC": "spine",
                "add_details": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert results["result"], f"{worker} returned no results"
            for host, res in results["result"].items():
                for command, parsing_res in res.items():
                    assert isinstance(
                        parsing_res, dict
                    ), f"{host}:{command} expected dict with details, got {type(parsing_res)}"
                    assert (
                        "result" in parsing_res
                    ), f"{host}:{command} missing 'result' key in details"

    def test_nornir_parse_textfsm_with_host_filter(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_textfsm",
            workers=["nornir-worker-1"],
            kwargs={
                "commands": "show hostname",
                "FC": "spine",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert results["result"], f"{worker} returned no results"
            for host in results["result"]:
                assert "spine" in host, f"{worker} returned unexpected host '{host}'"

    def test_nornir_parse_textfsm_no_matching_hosts(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_textfsm",
            workers=["nornir-worker-1"],
            kwargs={
                "commands": "show hostname",
                "FC": "nonexistent_host_xyz",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} should not fail for no-match"
            assert not results["result"], f"{worker} unexpectedly returned results"

    def test_nornir_parse_textfsm_file_template(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse_textfsm",
            workers=["nornir-worker-1"],
            kwargs={
                "commands": "show hostname",
                "template": "nf://textfsm/arista_eos_show_hostname.textfsm",
                "FC": "spine",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert results["result"], f"{worker} returned no results"
            for host, res in results["result"].items():
                for command, parsing_res in res.items():
                    assert parsing_res, f"{host}:{command} textfsm result is empty"


# ----------------------------------------------------------------------------
# NORNIR JINJA2 FILTERS
# ----------------------------------------------------------------------------
