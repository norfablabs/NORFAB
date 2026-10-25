"""NETCONF task tests; live tests require the cEOS and CSR1000v integration lab."""

from xml.etree import ElementTree

import pytest

pytestmark = [pytest.mark.nornir, pytest.mark.nornir_netconf]


class TestNetconfCancelCommit:
    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    @pytest.mark.parametrize("to_dict", [True, False])
    def test_cancel_own_commit(
        self, nfclient: object, plugin: str, to_dict: bool
    ) -> None:
        """Start and cancel a test-owned confirmed commit."""
        common = {"plugin": plugin, "FL": ["csr1k-r1"], "on_failed": True}
        token = "norfab-cancel-commit-test"
        committed = nfclient.run_job(
            "nornir",
            "netconf_commit",
            workers="nornir-worker-6",
            kwargs={
                **common,
                "confirmed": True,
                "confirm_delay": 30,
                "persist": token,
                "run_task_retry": 0,
            },
        )["nornir-worker-6"]
        assert committed["failed"] is False, committed
        result = None
        try:
            result = nfclient.run_job(
                "nornir",
                "netconf_cancel_commit",
                workers="nornir-worker-6",
                kwargs={
                    **common,
                    "persist_id": token,
                    "to_dict": to_dict,
                    "add_details": True,
                    "run_task_retry": 0,
                },
            )["nornir-worker-6"]
            assert result["failed"] is False, result
            operation = "rpc" if plugin == "scrapli" else "cancel_commit"
            if to_dict:
                record = result["result"]["csr1k-r1"][operation]
            else:
                record = result["result"][0]
                assert record["host"] == "csr1k-r1"
                assert record["name"] == operation
            assert record["failed"] is False, record
            root = ElementTree.fromstring(record["result"])
            assert any(node.tag.split("}")[-1] == "ok" for node in root.iter())
        finally:
            if result is None or result["failed"]:
                # Retry only this test's cancellation; otherwise its timer expires.
                nfclient.run_job(
                    "nornir",
                    "netconf_cancel_commit",
                    workers="nornir-worker-6",
                    kwargs={**common, "persist_id": token, "run_task_retry": 0},
                )

    @pytest.mark.parametrize(
        "kwargs", [{"plugin": "invalid"}, {"persist_id": ""}, {"persist_id": 1}]
    )
    def test_invalid_arguments(self, nfclient: object, kwargs: dict) -> None:
        result = nfclient.run_job(
            "nornir", "netconf_cancel_commit", workers="nornir-worker-1", kwargs=kwargs
        )["nornir-worker-1"]
        assert result["failed"] is True, result
        assert result["errors"], result

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    @pytest.mark.parametrize("persist_id", [None, "norfab-test"])
    def test_no_match(self, nfclient: object, plugin: str, persist_id: str) -> None:
        result = nfclient.run_job(
            "nornir",
            "netconf_cancel_commit",
            workers="nornir-worker-1",
            kwargs={
                "plugin": plugin,
                "persist_id": persist_id,
                "FB": "no-such-netconf-host",
            },
        )["nornir-worker-1"]
        assert result["status"] == "no_match"
        assert result["result"] == {}


class TestNetconfCommit:
    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    @pytest.mark.parametrize("to_dict", [True, False])
    @pytest.mark.parametrize("confirmed", [False, True])
    def test_commit_candidate(
        self, nfclient: object, plugin: str, to_dict: bool, confirmed: bool
    ) -> None:
        """Commit candidate configuration with either backend and result format."""
        host = "csr1k-r1"
        worker = "nornir-worker-6"
        common = {"plugin": plugin, "FL": [host], "on_failed": True}
        options = {}
        if confirmed:
            options = {
                "confirmed": True,
                "confirm_delay": 30,
                "persist": "norfab-commit-test",
            }
        try:
            result = nfclient.run_job(
                "nornir",
                "netconf_commit",
                workers=worker,
                kwargs={
                    **common,
                    **options,
                    "run_task_retry": 0,
                    "to_dict": to_dict,
                    "add_details": True,
                },
            )[worker]
            assert result["failed"] is False, result
            if to_dict:
                record = result["result"][host]["commit"]
            else:
                record = result["result"][0]
                assert record["host"] == host
                assert record["name"] == "commit"
            assert record["failed"] is False, record
            root = ElementTree.fromstring(record["result"])
            assert any(node.tag.split("}")[-1] == "ok" for node in root.iter())
        finally:
            if confirmed:
                confirmation = nfclient.run_job(
                    "nornir",
                    "netconf_commit",
                    workers=worker,
                    kwargs={
                        **common,
                        "persist_id": "norfab-commit-test",
                        "run_task_retry": 0,
                    },
                )[worker]
                assert confirmation["failed"] is False, confirmation

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"plugin": "invalid"},
            {"confirmed": "yes"},
            {"confirmed": True, "confirm_delay": 0},
            {"confirm_delay": 30},
            {"persist": "test"},
            {"persist_id": ""},
            {"persist": "test", "persist_id": "test", "confirmed": True},
            {"persist_id": "test", "confirmed": True},
        ],
    )
    def test_invalid_arguments(self, nfclient: object, kwargs: dict) -> None:
        result = nfclient.run_job(
            "nornir",
            "netconf_commit",
            workers="nornir-worker-1",
            kwargs=kwargs,
        )["nornir-worker-1"]
        assert result["failed"] is True, result
        assert result["errors"], result

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    @pytest.mark.parametrize(
        "options",
        [
            {},
            {"confirmed": True, "confirm_delay": 30, "persist": "norfab-test"},
            {"persist_id": "norfab-test"},
        ],
    )
    def test_no_match(self, nfclient: object, plugin: str, options: dict) -> None:
        result = nfclient.run_job(
            "nornir",
            "netconf_commit",
            workers="nornir-worker-1",
            kwargs={"plugin": plugin, "FB": "no-such-netconf-host", **options},
        )["nornir-worker-1"]
        assert result["status"] == "no_match"
        assert result["result"] == {}


class TestNetconfValidate:
    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    @pytest.mark.parametrize("source", ["candidate", "running", "startup"])
    def test_datastore(self, nfclient: object, plugin: str, source: str) -> None:
        """Return the device's validation reply, including existing lab errors."""
        capabilities = nfclient.run_job(
            "nornir",
            "netconf_get_capabilities",
            workers="nornir-worker-1",
            kwargs={"plugin": plugin, "FL": ["ceos-spine-1"], "on_failed": True},
        )["nornir-worker-1"]
        assert capabilities["failed"] is False, capabilities
        supports_validate = any(
            ":validate:" in capability
            for capability in capabilities["result"]["ceos-spine-1"][
                "server_capabilities"
            ]
        )
        result = nfclient.run_job(
            "nornir",
            "netconf_validate",
            workers="nornir-worker-1",
            kwargs={
                "plugin": plugin,
                "source": source,
                "FL": ["ceos-spine-1"],
                "on_failed": True,
                "run_task_retry": 0,
            },
        )["nornir-worker-1"]
        reply = result["result"]["ceos-spine-1"]["validate"]
        if not supports_validate:
            assert result["failed"] is True, result
            assert (
                "MissingCapabilityError" in reply or "CapabilityNotSupported" in reply
            ), reply
            return
        if result["failed"]:
            # cEOS can reject existing configuration or unsupported datastores.
            assert "rpc-error" in reply or "RPCError" in reply, reply
        else:
            root = ElementTree.fromstring(reply)
            assert any(node.tag.split("}")[-1] == "ok" for node in root.iter())

    @pytest.mark.parametrize(
        "kwargs", [{"source": "invalid"}, {"source": ""}, {"plugin": "invalid"}]
    )
    def test_invalid_arguments(self, nfclient: object, kwargs: dict) -> None:
        result = nfclient.run_job(
            "nornir",
            "netconf_validate",
            workers="nornir-worker-1",
            kwargs=kwargs,
        )["nornir-worker-1"]
        assert result["failed"] is True, result
        assert result["errors"], result

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    @pytest.mark.parametrize("to_dict", [True, False])
    def test_no_match(self, nfclient: object, plugin: str, to_dict: bool) -> None:
        result = nfclient.run_job(
            "nornir",
            "netconf_validate",
            workers="nornir-worker-1",
            kwargs={
                "plugin": plugin,
                "FB": "no-such-netconf-host",
                "to_dict": to_dict,
            },
        )["nornir-worker-1"]
        assert result["status"] == "no_match"
        assert result["result"] == ({} if to_dict else [])

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    def test_list_result(self, nfclient: object, plugin: str) -> None:
        """Preserve validation replies and failures in detailed list results."""
        result = nfclient.run_job(
            "nornir",
            "netconf_validate",
            workers="nornir-worker-1",
            kwargs={
                "plugin": plugin,
                "source": "running",
                "FL": ["ceos-spine-1"],
                "on_failed": True,
                "run_task_retry": 0,
                "to_dict": False,
                "add_details": True,
            },
        )["nornir-worker-1"]
        assert isinstance(result["result"], list) and result["result"], result
        record = result["result"][0]
        assert record["host"] == "ceos-spine-1"
        assert record["name"] == "validate"
        assert record["failed"] == result["failed"]
        assert record["result"], record


class TestNetconfGetConfig:
    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    @pytest.mark.parametrize("filtered", [False, True])
    def test_running(self, nfclient: object, plugin: str, filtered: bool) -> None:
        """Read real XML from every configured cEOS host with either backend."""
        hosts = [
            "ceos-spine-1",
            "ceos-spine-2",
            "ceos-leaf-1",
            "ceos-leaf-2",
            "ceos-leaf-3",
        ]
        kwargs = {"plugin": plugin, "FL": hosts, "on_failed": True}
        if filtered:
            kwargs["filter_subtree"] = (
                '<system xmlns="http://openconfig.net/yang/system"><config><hostname/></config></system>'
            )
        ret = nfclient.run_job(
            "nornir",
            "netconf_get_config",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs=kwargs,
        )
        seen = set()
        assert ret
        for worker, result in ret.items():
            assert result["failed"] is False, (worker, result)
            for host, operations in result["result"].items():
                root = ElementTree.fromstring(operations["get_config"])
                assert any(node.text == host for node in root.iter()), operations
                seen.add(host)
        assert seen == set(hosts)

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    def test_no_match(self, nfclient: object, plugin: str) -> None:
        ret = nfclient.run_job(
            "nornir",
            "netconf_get_config",
            workers="nornir-worker-1",
            kwargs={"plugin": plugin, "FB": "no-such-netconf-host"},
        )
        assert ret["nornir-worker-1"]["status"] == "no_match"

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"plugin": "invalid"},
            {"source": "invalid"},
            {"filter_subtree": ""},
            {"filter_xpath": ""},
            {"filter_subtree": "<system/>", "filter_xpath": "/system"},
            {"filter-subtree": "<system/>", "filter-xpath": "/system"},
        ],
    )
    def test_invalid_arguments(self, nfclient: object, kwargs: dict) -> None:
        """Validate rejected inputs through the worker's public interface."""
        result = nfclient.run_job(
            "nornir",
            "netconf_get_config",
            workers="nornir-worker-1",
            kwargs=kwargs,
        )["nornir-worker-1"]
        assert result["failed"] is True, result
        assert result["errors"], result

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    def test_template_file_and_details(self, nfclient: object, plugin: str) -> None:
        """Fetch a filter file, render host context, and include task details."""
        ret = nfclient.run_job(
            "nornir",
            "netconf_get_config",
            workers="nornir-worker-1",
            kwargs={
                "plugin": plugin,
                "FL": ["ceos-spine-1"],
                "on_failed": True,
                "filter_subtree": "nf://netconf/get_system.xml",
                "add_details": True,
            },
        )
        result = ret["nornir-worker-1"]
        assert result["failed"] is False, result
        assert set(result["result"]) == {"ceos-spine-1"}
        operation = result["result"]["ceos-spine-1"]["get_config"]
        assert operation["failed"] is False
        assert "ceos-spine-1" in operation["result"]

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    def test_list_result(self, nfclient: object, plugin: str) -> None:
        ret = nfclient.run_job(
            "nornir",
            "netconf_get_config",
            workers="nornir-worker-1",
            kwargs={
                "plugin": plugin,
                "FL": ["ceos-spine-1"],
                "on_failed": True,
                "to_dict": False,
                "add_details": True,
            },
        )
        result = ret["nornir-worker-1"]
        assert result["failed"] is False, result
        assert isinstance(result["result"], list) and result["result"]
        assert all(record["host"] == "ceos-spine-1" for record in result["result"])

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    def test_invalid_xml_and_recovery(self, nfclient: object, plugin: str) -> None:
        """A malformed filter fails without contaminating the next operation."""
        kwargs = {"plugin": plugin, "FL": ["ceos-spine-1"], "on_failed": True}
        ret = nfclient.run_job(
            "nornir",
            "netconf_get_config",
            workers="nornir-worker-1",
            kwargs={**kwargs, "filter_subtree": "<broken"},
        )
        assert ret["nornir-worker-1"]["failed"] is True
        ret = nfclient.run_job(
            "nornir",
            "netconf_get_config",
            workers="nornir-worker-1",
            kwargs=kwargs,
        )
        result = ret["nornir-worker-1"]
        assert result["failed"] is False, result
        assert "ceos-spine-1" in result["result"]["ceos-spine-1"]["get_config"]

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    @pytest.mark.parametrize(
        "expression",
        [
            "/*[local-name()='system']/*[local-name()='config']/*[local-name()='hostname']",
            "nf://netconf/get_hostname.xpath",
        ],
    )
    def test_xpath(self, nfclient: object, plugin: str, expression: str) -> None:
        """Check XPath replies or explicit failure on devices without support."""
        capabilities = nfclient.run_job(
            "nornir",
            "netconf_get_capabilities",
            workers="nornir-worker-1",
            kwargs={
                "plugin": plugin,
                "FL": ["ceos-spine-1"],
                "on_failed": True,
            },
        )["nornir-worker-1"]
        assert capabilities["failed"] is False, capabilities
        supports_xpath = (
            "urn:ietf:params:netconf:capability:xpath:1.0"
            in capabilities["result"]["ceos-spine-1"]["server_capabilities"]
        )
        ret = nfclient.run_job(
            "nornir",
            "netconf_get_config",
            workers="nornir-worker-1",
            kwargs={
                "plugin": plugin,
                "FL": ["ceos-spine-1"],
                "on_failed": True,
                "filter_xpath": expression,
            },
        )
        result = ret["nornir-worker-1"]
        if not supports_xpath:
            assert result["failed"] is True, result
            error = str(result["result"]).lower()
            assert "xpath" in error or "filter" in error, result
            return
        assert result["failed"] is False, result
        root = ElementTree.fromstring(result["result"]["ceos-spine-1"]["get_config"])
        assert any(node.text == "ceos-spine-1" for node in root.iter())
        assert not any(node.tag.split("}")[-1] == "interfaces" for node in root.iter())


class TestNetconfEditConfig:
    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    def test_edit_and_restore(self, nfclient: object, plugin: str) -> None:
        """Create a test-owned loopback, verify its description, and delete it."""
        common = {"plugin": plugin, "FL": ["ceos-spine-1"], "on_failed": True}
        subtree = '<interfaces xmlns="http://openconfig.net/yang/interfaces"><interface><name>Loopback3999</name></interface></interfaces>'
        before = nfclient.run_job(
            "nornir",
            "netconf_get_config",
            workers="nornir-worker-1",
            kwargs={**common, "filter_subtree": subtree},
        )["nornir-worker-1"]
        assert before["failed"] is False, before
        assert (
            "Loopback3999" not in before["result"]["ceos-spine-1"]["get_config"]
        ), "test interface already exists"
        try:
            result = nfclient.run_job(
                "nornir",
                "netconf_edit_config",
                workers="nornir-worker-1",
                kwargs={
                    **common,
                    "config": "nf://netconf/edit_loopback.xml",
                    "job_data": {"description": "norfab-netconf-edit-test"},
                },
            )["nornir-worker-1"]
            assert result["failed"] is False, result
            assert "ok" in result["result"]["ceos-spine-1"]["edit_config"]
            read = nfclient.run_job(
                "nornir",
                "netconf_get_config",
                workers="nornir-worker-1",
                kwargs={**common, "filter_subtree": subtree},
            )["nornir-worker-1"]
            assert read["failed"] is False, read
            assert (
                "norfab-netconf-edit-test"
                in read["result"]["ceos-spine-1"]["get_config"]
            )
        finally:
            cleanup = nfclient.run_job(
                "nornir",
                "netconf_edit_config",
                workers="nornir-worker-1",
                kwargs={
                    **common,
                    "config": '<config><interfaces xmlns="http://openconfig.net/yang/interfaces"><interface xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0" nc:operation="remove"><name>Loopback3999</name></interface></interfaces></config>',
                },
            )["nornir-worker-1"]
            assert cleanup["failed"] is False, cleanup
        after = nfclient.run_job(
            "nornir",
            "netconf_get_config",
            workers="nornir-worker-1",
            kwargs={**common, "filter_subtree": subtree},
        )["nornir-worker-1"]
        assert after["failed"] is False, after
        assert "Loopback3999" not in after["result"]["ceos-spine-1"]["get_config"]

    @pytest.mark.parametrize(
        "kwargs",
        [
            {},
            {"config": ""},
            {"config": "<config/>", "target": "startup"},
        ],
    )
    def test_invalid_arguments(self, nfclient: object, kwargs: dict) -> None:
        """Validate rejected inputs through the worker's public interface."""
        result = nfclient.run_job(
            "nornir",
            "netconf_edit_config",
            workers="nornir-worker-1",
            kwargs=kwargs,
        )["nornir-worker-1"]
        assert result["failed"] is True, result
        assert result["errors"], result

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    def test_no_match(self, nfclient: object, plugin: str) -> None:
        result = nfclient.run_job(
            "nornir",
            "netconf_edit_config",
            workers="nornir-worker-1",
            kwargs={
                "plugin": plugin,
                "config": "<config/>",
                "FB": "no-such-netconf-host",
            },
        )["nornir-worker-1"]
        assert result["status"] == "no_match"

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    def test_invalid_configuration(self, nfclient: object, plugin: str) -> None:
        result = nfclient.run_job(
            "nornir",
            "netconf_edit_config",
            workers="nornir-worker-1",
            kwargs={
                "plugin": plugin,
                "FL": ["ceos-spine-1"],
                "on_failed": True,
                "config": '<config><norfab-invalid xmlns="urn:norfab:invalid"/></config>',
            },
        )["nornir-worker-1"]
        assert result["failed"] is True, result


class TestNetconfTransaction:
    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    @pytest.mark.parametrize("template_file", [False, True])
    def test_edit_and_restore(
        self, nfclient: object, plugin: str, template_file: bool
    ) -> None:
        """Create a test-owned loopback, verify its description, and delete it."""
        common = {"plugin": plugin, "FL": ["ceos-spine-1"], "on_failed": True}
        transaction = {**common, "target": "running", "validate": False}
        subtree = '<interfaces xmlns="http://openconfig.net/yang/interfaces"><interface><name>Loopback3998</name></interface></interfaces>'
        before = nfclient.run_job(
            "nornir",
            "netconf_get_config",
            workers="nornir-worker-1",
            kwargs={**common, "filter_subtree": subtree},
        )["nornir-worker-1"]
        assert before["failed"] is False, before
        assert (
            "Loopback3998" not in before["result"]["ceos-spine-1"]["get_config"]
        ), "test interface already exists"
        try:
            result = nfclient.run_job(
                "nornir",
                "netconf_transaction",
                workers="nornir-worker-1",
                kwargs={
                    **transaction,
                    "config": (
                        "nf://netconf/transaction_loopback.xml"
                        if template_file
                        else '<config><interfaces xmlns="http://openconfig.net/yang/interfaces"><interface><name>Loopback3998</name><config><name>Loopback3998</name><type xmlns:ianaift="urn:ietf:params:xml:ns:yang:iana-if-type">ianaift:softwareLoopback</type><description>{{ job_data.description }}</description></config></interface></interfaces></config>'
                    ),
                    "job_data": {"description": "norfab-netconf-transaction-test"},
                    "to_dict": not template_file,
                    "add_details": template_file,
                },
            )["nornir-worker-1"]
            assert result["failed"] is False, result
            if template_file:
                record = result["result"][0]
                assert record["host"] == "ceos-spine-1"
                assert record["failed"] is False
                steps = record["result"]
            else:
                steps = result["result"]["ceos-spine-1"]["transaction"]
            assert isinstance(steps, list) and steps
            assert any("edit_config" in step for step in steps)
            read = nfclient.run_job(
                "nornir",
                "netconf_get_config",
                workers="nornir-worker-1",
                kwargs={**common, "filter_subtree": subtree},
            )["nornir-worker-1"]
            assert read["failed"] is False, read
            assert (
                "norfab-netconf-transaction-test"
                in read["result"]["ceos-spine-1"]["get_config"]
            )
        finally:
            cleanup = nfclient.run_job(
                "nornir",
                "netconf_transaction",
                workers="nornir-worker-1",
                kwargs={
                    **transaction,
                    "config": '<config><interfaces xmlns="http://openconfig.net/yang/interfaces"><interface xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0" nc:operation="remove"><name>Loopback3998</name></interface></interfaces></config>',
                },
            )["nornir-worker-1"]
            assert cleanup["failed"] is False, cleanup
        after = nfclient.run_job(
            "nornir",
            "netconf_get_config",
            workers="nornir-worker-1",
            kwargs={**common, "filter_subtree": subtree},
        )["nornir-worker-1"]
        assert after["failed"] is False, after
        assert "Loopback3998" not in after["result"]["ceos-spine-1"]["get_config"]

    @pytest.mark.parametrize(
        "kwargs",
        [
            {},
            {"config": ""},
            {"config": "<config/>", "target": "startup"},
            {"config": "<config/>", "plugin": "invalid"},
            {"config": "<config/>", "confirm_delay": 0},
            {"config": "<config/>", "commit_final_delay": -1},
        ],
    )
    def test_invalid_arguments(self, nfclient: object, kwargs: dict) -> None:
        """Validate rejected inputs through the worker's public interface."""
        result = nfclient.run_job(
            "nornir",
            "netconf_transaction",
            workers="nornir-worker-1",
            kwargs=kwargs,
        )["nornir-worker-1"]
        assert result["failed"] is True, result
        assert result["errors"], result

    def test_invalid_configuration(self, nfclient: object) -> None:
        """Propagate ncclient RPC failure; cEOS stalls on this edit via Scrapli."""
        result = nfclient.run_job(
            "nornir",
            "netconf_transaction",
            workers="nornir-worker-1",
            kwargs={
                "plugin": "ncclient",
                "FL": ["ceos-spine-1"],
                "on_failed": True,
                "target": "running",
                "validate": False,
                "run_task_retry": 0,
                "config": '<config><norfab-invalid xmlns="urn:norfab:invalid"/></config>',
            },
        )["nornir-worker-1"]
        assert result["failed"] is True, result


class TestNetconfGetSchema:
    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    def test_advertised_module(self, nfclient: object, plugin: str) -> None:
        """Select an advertised module and retrieve its YANG source."""
        from urllib.parse import parse_qs, urlsplit

        common = {"FL": ["ceos-spine-1"], "on_failed": True}
        caps = nfclient.run_job(
            "nornir",
            "netconf_get_capabilities",
            workers="nornir-worker-1",
            kwargs={**common, "plugin": plugin},
        )["nornir-worker-1"]
        assert caps["failed"] is False, caps
        modules = [
            parse_qs(urlsplit(cap).query)
            for cap in caps["result"]["ceos-spine-1"]["server_capabilities"]
        ]
        modules = [module for module in modules if module.get("module")]
        assert modules, "device did not advertise any modules"
        module = next(
            (m for m in modules if m["module"][0] == "openconfig-system"), modules[0]
        )
        identifier = module["module"][0]
        result = nfclient.run_job(
            "nornir",
            "netconf_get_schema",
            workers="nornir-worker-1",
            kwargs={**common, "plugin": plugin, "identifier": identifier},
        )["nornir-worker-1"]
        assert result["failed"] is False, result
        reply = result["result"]["ceos-spine-1"][
            "get_schema" if plugin == "ncclient" else "rpc"
        ]
        root = ElementTree.fromstring(reply)
        text = "".join(root.itertext())
        assert identifier in text and "module " in text, text

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    def test_missing_module(self, nfclient: object, plugin: str) -> None:
        result = nfclient.run_job(
            "nornir",
            "netconf_get_schema",
            workers="nornir-worker-1",
            kwargs={
                "plugin": plugin,
                "identifier": "norfab-nonexistent-module",
                "FL": ["ceos-spine-1"],
                "on_failed": True,
            },
        )["nornir-worker-1"]
        assert result["failed"] is True, result

    @pytest.mark.parametrize(
        "kwargs",
        [{}, {"identifier": ""}, {"identifier": "ietf-interfaces", "format": "xml"}],
    )
    def test_invalid_arguments(self, nfclient: object, kwargs: dict) -> None:
        """Validate rejected inputs through the worker's public interface."""
        result = nfclient.run_job(
            "nornir",
            "netconf_get_schema",
            workers="nornir-worker-1",
            kwargs=kwargs,
        )["nornir-worker-1"]
        assert result["failed"] is True, result
        assert result["errors"], result


class TestNetconfGetCapabilities:
    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    @pytest.mark.parametrize(
        "pattern", [None, "*netconf*", "norfab-no-such-capability"]
    )
    def test_capabilities(
        self, nfclient: object, plugin: str, pattern: str | None
    ) -> None:
        from fnmatch import fnmatchcase

        result = nfclient.run_job(
            "nornir",
            "netconf_get_capabilities",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "plugin": plugin,
                "capab_filter": pattern,
                "FB": "ceos-*",
                "on_failed": True,
            },
        )
        seen = set()
        for worker, record in result.items():
            assert record["failed"] is False, (worker, record)
            for host, operations in record["result"].items():
                seen.add(host)
                caps = operations["server_capabilities"]
                assert isinstance(caps, list)
                if pattern == "norfab-no-such-capability":
                    assert caps == []
                else:
                    assert caps
                    assert all(isinstance(cap, str) for cap in caps)
                    if pattern:
                        assert all(fnmatchcase(cap, pattern) for cap in caps)
                    else:
                        assert "urn:ietf:params:netconf:base:1.0" in caps
        assert seen == {
            "ceos-spine-1",
            "ceos-spine-2",
            "ceos-leaf-1",
            "ceos-leaf-2",
            "ceos-leaf-3",
        }

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    def test_no_match(self, nfclient: object, plugin: str) -> None:
        result = nfclient.run_job(
            "nornir",
            "netconf_get_capabilities",
            workers="nornir-worker-1",
            kwargs={"plugin": plugin, "FB": "no-such-netconf-host"},
        )
        assert result["nornir-worker-1"]["status"] == "no_match"


class TestNetconfGet:
    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    @pytest.mark.parametrize("filtered", [False, True])
    def test_running(self, nfclient: object, plugin: str, filtered: bool) -> None:
        """Read real XML from every configured cEOS host with either backend."""
        hosts = [
            "ceos-spine-1",
            "ceos-spine-2",
            "ceos-leaf-1",
            "ceos-leaf-2",
            "ceos-leaf-3",
        ]
        kwargs = {"plugin": plugin, "FL": hosts, "on_failed": True}
        if filtered:
            kwargs["filter_subtree"] = (
                '<system xmlns="http://openconfig.net/yang/system"><config><hostname/></config></system>'
            )
        ret = nfclient.run_job(
            "nornir",
            "netconf_get",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs=kwargs,
        )
        seen = set()
        assert ret
        for worker, result in ret.items():
            assert result["failed"] is False, (worker, result)
            for host, operations in result["result"].items():
                operation = "rpc" if plugin == "scrapli" and not filtered else "get"
                root = ElementTree.fromstring(operations[operation])
                assert any(node.text == host for node in root.iter()), operations
                seen.add(host)
        assert seen == set(hosts)

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    def test_operational_state(self, nfclient: object, plugin: str) -> None:
        """Get returns operational state as well as configuration data."""
        result = nfclient.run_job(
            "nornir",
            "netconf_get",
            workers="nornir-worker-1",
            kwargs={
                "plugin": plugin,
                "FL": ["ceos-spine-1"],
                "on_failed": True,
                "filter_subtree": '<system xmlns="http://openconfig.net/yang/system"><state><hostname/></state></system>',
            },
        )["nornir-worker-1"]
        assert result["failed"] is False, result
        root = ElementTree.fromstring(result["result"]["ceos-spine-1"]["get"])
        states = [node for node in root.iter() if node.tag.split("}")[-1] == "state"]
        assert any(
            node.text == "ceos-spine-1" for state in states for node in state.iter()
        )

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    def test_no_match(self, nfclient: object, plugin: str) -> None:
        ret = nfclient.run_job(
            "nornir",
            "netconf_get",
            workers="nornir-worker-1",
            kwargs={"plugin": plugin, "FB": "no-such-netconf-host"},
        )
        assert ret["nornir-worker-1"]["status"] == "no_match"

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"plugin": "invalid"},
            {"ietf_interfaces": "true"},
            {"openconfig_interfaces": True, "ietf_interfaces": True},
            {"openconfig-interfaces": True, "filter-xpath": "/system"},
            {"openconfig_lldp": True, "ietf_interfaces": True},
            {"openconfig-lldp": True, "filter-xpath": "/system"},
            {"openconfig_bgp": True, "ietf_interfaces": True},
            {"openconfig-bgp": True, "filter-xpath": "/system"},
            {"openconfig_system": True, "ietf_interfaces": True},
            {"openconfig-system": True, "filter-xpath": "/system"},
            {"ietf_routing": True, "ietf_interfaces": True},
            {"ietf-routing": True, "filter-xpath": "/system"},
            {"ietf_hardware": True, "ietf_interfaces": True},
            {"ietf-hardware": True, "filter-xpath": "/system"},
            {"ietf_interfaces": True, "filter_subtree": "<system/>"},
            {"ietf_interfaces": True, "filter_xpath": "/system"},
            {"ietf-interfaces": True, "filter-subtree": "<system/>"},
            {"filter_subtree": ""},
            {"filter_xpath": ""},
            {"filter_subtree": "<system/>", "filter_xpath": "/system"},
            {"filter-subtree": "<system/>", "filter-xpath": "/system"},
        ],
    )
    def test_invalid_arguments(self, nfclient: object, kwargs: dict) -> None:
        """Validate rejected inputs through the worker's public interface."""
        result = nfclient.run_job(
            "nornir",
            "netconf_get",
            workers="nornir-worker-1",
            kwargs=kwargs,
        )["nornir-worker-1"]
        assert result["failed"] is True, result
        assert result["errors"], result

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    def test_template_file_and_details(self, nfclient: object, plugin: str) -> None:
        """Fetch a filter file, render host context, and include task details."""
        ret = nfclient.run_job(
            "nornir",
            "netconf_get",
            workers="nornir-worker-1",
            kwargs={
                "plugin": plugin,
                "FL": ["ceos-spine-1"],
                "on_failed": True,
                "filter_subtree": "nf://netconf/get_system.xml",
                "add_details": True,
            },
        )
        result = ret["nornir-worker-1"]
        assert result["failed"] is False, result
        assert set(result["result"]) == {"ceos-spine-1"}
        operation = result["result"]["ceos-spine-1"]["get"]
        assert operation["failed"] is False
        assert "ceos-spine-1" in operation["result"]

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    def test_list_result(self, nfclient: object, plugin: str) -> None:
        ret = nfclient.run_job(
            "nornir",
            "netconf_get",
            workers="nornir-worker-1",
            kwargs={
                "plugin": plugin,
                "FL": ["ceos-spine-1"],
                "on_failed": True,
                "to_dict": False,
                "add_details": True,
            },
        )
        result = ret["nornir-worker-1"]
        assert result["failed"] is False, result
        assert isinstance(result["result"], list) and result["result"]
        assert all(record["host"] == "ceos-spine-1" for record in result["result"])

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    def test_invalid_xml_and_recovery(self, nfclient: object, plugin: str) -> None:
        """A malformed filter fails without contaminating the next operation."""
        kwargs = {"plugin": plugin, "FL": ["ceos-spine-1"], "on_failed": True}
        ret = nfclient.run_job(
            "nornir",
            "netconf_get",
            workers="nornir-worker-1",
            kwargs={**kwargs, "filter_subtree": "<broken"},
        )
        assert ret["nornir-worker-1"]["failed"] is True
        ret = nfclient.run_job(
            "nornir",
            "netconf_get",
            workers="nornir-worker-1",
            kwargs=kwargs,
        )
        result = ret["nornir-worker-1"]
        assert result["failed"] is False, result
        assert (
            "ceos-spine-1"
            in result["result"]["ceos-spine-1"]["rpc" if plugin == "scrapli" else "get"]
        )

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    @pytest.mark.parametrize(
        "expression",
        [
            "/*[local-name()='system']/*[local-name()='config']/*[local-name()='hostname']",
            "nf://netconf/get_hostname.xpath",
        ],
    )
    def test_xpath(self, nfclient: object, plugin: str, expression: str) -> None:
        """Check XPath replies or explicit failure on devices without support."""
        capabilities = nfclient.run_job(
            "nornir",
            "netconf_get_capabilities",
            workers="nornir-worker-1",
            kwargs={
                "plugin": plugin,
                "FL": ["ceos-spine-1"],
                "on_failed": True,
            },
        )["nornir-worker-1"]
        assert capabilities["failed"] is False, capabilities
        supports_xpath = (
            "urn:ietf:params:netconf:capability:xpath:1.0"
            in capabilities["result"]["ceos-spine-1"]["server_capabilities"]
        )
        ret = nfclient.run_job(
            "nornir",
            "netconf_get",
            workers="nornir-worker-1",
            kwargs={
                "plugin": plugin,
                "FL": ["ceos-spine-1"],
                "on_failed": True,
                "filter_xpath": expression,
            },
        )
        result = ret["nornir-worker-1"]
        if not supports_xpath:
            assert result["failed"] is True, result
            error = str(result["result"]).lower()
            assert "xpath" in error or "filter" in error, result
            return
        assert result["failed"] is False, result
        root = ElementTree.fromstring(result["result"]["ceos-spine-1"]["get"])
        assert any(node.text == "ceos-spine-1" for node in root.iter())
        assert not any(node.tag.split("}")[-1] == "interfaces" for node in root.iter())

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    @pytest.mark.parametrize(
        "getter",
        [
            "ietf_interfaces",
            "openconfig_interfaces",
            "openconfig_lldp",
            "openconfig_bgp",
            "openconfig_system",
            "ietf_routing",
            "ietf_hardware",
        ],
    )
    def test_getters(self, nfclient: object, plugin: str, getter: str) -> None:
        """Getters return a data reply without RPC errors on a supported device."""
        host = "csr1k-r1"
        worker = "nornir-worker-6"
        result = nfclient.run_job(
            "nornir",
            "netconf_get",
            workers=worker,
            kwargs={
                "plugin": plugin,
                "FL": [host],
                "on_failed": True,
                getter: True,
            },
        )[worker]
        assert result["failed"] is False, result
        reply = ElementTree.fromstring(result["result"][host]["get"])
        assert reply.tag.split("}")[-1] == "rpc-reply"
        assert not any(node.tag.split("}")[-1] == "rpc-error" for node in reply.iter())
        assert any(node.tag.split("}")[-1] == "data" for node in reply.iter())


class TestNetconfXmlProcessors:
    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    @pytest.mark.parametrize("task", ["netconf_get", "netconf_get_config"])
    @pytest.mark.parametrize("processor", ["xmltodict", "xml_flake", "xpath"])
    def test_xml_processors(
        self, nfclient: object, plugin: str, task: str, processor: str
    ) -> None:
        """Process real NETCONF XML replies through the public task interface."""
        options = {
            "xmltodict": {"xmltodict": True},
            "xml_flake": {"xml_flake": "*hostname*"},
            "xpath": {"xpath": "//hostname"},
        }
        result = nfclient.run_job(
            "nornir",
            task,
            workers="nornir-worker-1",
            kwargs={
                "plugin": plugin,
                "FL": ["ceos-spine-1"],
                "on_failed": True,
                "filter_subtree": '<system xmlns="http://openconfig.net/yang/system"><config><hostname/></config></system>',
                **options[processor],
            },
        )["nornir-worker-1"]
        assert result["failed"] is False, result
        value = result["result"]["ceos-spine-1"][task.removeprefix("netconf_")]
        if processor == "xmltodict":
            assert isinstance(value, dict) and value
            assert "ceos-spine-1" in str(value)
        elif processor == "xml_flake":
            assert isinstance(value, dict) and value
            assert all("hostname" in key for key in value)
            assert "ceos-spine-1" in value.values()
        else:
            assert isinstance(value, str)
            assert "<hostname" in value
            assert ">ceos-spine-1</hostname>" in value

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    def test_xpath_then_xmltodict(self, nfclient: object, plugin: str) -> None:
        """Select one XML element before converting it to a dictionary."""
        result = nfclient.run_job(
            "nornir",
            "netconf_get",
            workers="nornir-worker-1",
            kwargs={
                "plugin": plugin,
                "FL": ["ceos-spine-1"],
                "on_failed": True,
                "filter_subtree": '<system xmlns="http://openconfig.net/yang/system"><config><hostname/></config></system>',
                "xpath": "(//hostname)[1]",
                "xmltodict": True,
            },
        )["nornir-worker-1"]
        assert result["failed"] is False, result
        value = result["result"]["ceos-spine-1"]["get"]
        assert isinstance(value, dict) and "hostname" in value
        assert "ceos-spine-1" in str(value["hostname"])


class TestNetconfDatastoreOperations:
    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    @pytest.mark.parametrize(
        "task,options",
        [
            ("netconf_discard_changes", {}),
            ("netconf_lock", {}),
            ("netconf_unlock", {}),
            ("netconf_copy_config", {"source": "running", "target": "candidate"}),
            ("netconf_delete_config", {"target": "startup"}),
            (
                "netconf_rpc",
                {"rpc": '<get xmlns="urn:ietf:params:xml:ns:netconf:base:1.0"/>'},
            ),
        ],
    )
    def test_no_match(
        self, nfclient: object, plugin: str, task: str, options: dict
    ) -> None:
        result = nfclient.run_job(
            "nornir",
            task,
            workers="nornir-worker-1",
            kwargs={"plugin": plugin, "FB": "no-such-netconf-host", **options},
        )["nornir-worker-1"]
        assert result["status"] == "no_match"
        assert result["result"] == {}

    @pytest.mark.parametrize(
        "task,options",
        [
            ("netconf_discard_changes", {"plugin": "invalid"}),
            ("netconf_lock", {"target": "invalid"}),
            ("netconf_unlock", {"target": "invalid"}),
            ("netconf_copy_config", {}),
            ("netconf_copy_config", {"source": "running", "target": "running"}),
            ("netconf_copy_config", {"source": "invalid", "target": "startup"}),
            ("netconf_delete_config", {}),
            ("netconf_delete_config", {"target": "running"}),
            ("netconf_delete_config", {"target": "invalid"}),
            ("netconf_rpc", {}),
            ("netconf_rpc", {"rpc": ""}),
        ],
    )
    def test_invalid_arguments(
        self, nfclient: object, task: str, options: dict
    ) -> None:
        result = nfclient.run_job(
            "nornir",
            task,
            workers="nornir-worker-1",
            kwargs=options,
        )["nornir-worker-1"]
        assert result["failed"] is True, result
        assert result["errors"], result

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    @pytest.mark.parametrize("target", ["running", "candidate"])
    def test_lock_unlock(self, nfclient: object, plugin: str, target: str) -> None:
        """Acquire and release only this test's datastore lock."""
        common = {
            "plugin": plugin,
            "target": target,
            "FL": ["ceos-spine-1"],
            "on_failed": True,
            "run_task_retry": 0,
            "add_details": True,
        }
        locked = nfclient.run_job(
            "nornir",
            "netconf_lock",
            workers="nornir-worker-1",
            kwargs=common,
        )["nornir-worker-1"]
        assert locked["failed"] is False, locked
        try:
            record = locked["result"]["ceos-spine-1"]["lock"]
            assert record["failed"] is False
            assert "ok" in record["result"]
        finally:
            unlocked = nfclient.run_job(
                "nornir",
                "netconf_unlock",
                workers="nornir-worker-1",
                kwargs={**common, "to_dict": False},
            )["nornir-worker-1"]
            assert unlocked["failed"] is False, unlocked
            record = unlocked["result"][0]
            assert record["host"] == "ceos-spine-1"
            assert record["name"] == "unlock"
            assert record["failed"] is False
            assert "ok" in record["result"]

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    @pytest.mark.parametrize("task", ["netconf_discard_changes", "netconf_copy_config"])
    def test_candidate_operations(
        self, nfclient: object, plugin: str, task: str
    ) -> None:
        """Copy running configuration to candidate or discard pending edits."""
        host = "csr1k-r1"
        worker = "nornir-worker-6"
        common = {
            "plugin": plugin,
            "FL": [host],
            "on_failed": True,
            "run_task_retry": 0,
        }
        options = (
            {"source": "running", "target": "candidate"}
            if task == "netconf_copy_config"
            else {}
        )
        result = nfclient.run_job(
            "nornir",
            task,
            workers=worker,
            kwargs={**common, **options},
        )[worker]
        assert result["failed"] is False, result
        operation = (
            "copy_config"
            if options
            else ("discard" if plugin == "scrapli" else "discard_changes")
        )
        root = ElementTree.fromstring(result["result"][host][operation])
        assert any(node.tag.split("}")[-1] == "ok" for node in root.iter())


class TestNetconfRpc:
    def test_invalid_xml_and_recovery(self, nfclient: object) -> None:
        """Clear rendered ncclient payloads after an XML parsing failure."""
        common = {"FL": ["ceos-spine-1"], "on_failed": True, "run_task_retry": 0}
        failed = nfclient.run_job(
            "nornir",
            "netconf_rpc",
            workers="nornir-worker-1",
            kwargs={**common, "rpc": "<broken"},
        )["nornir-worker-1"]
        assert failed["failed"] is True, failed
        assert "XMLSyntaxError" in str(failed["errors"]), failed
        recovered = nfclient.run_job(
            "nornir",
            "netconf_get",
            workers="nornir-worker-1",
            kwargs=common,
        )["nornir-worker-1"]
        assert recovered["failed"] is False, recovered
        assert "ceos-spine-1" in recovered["result"]["ceos-spine-1"]["get"]

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    @pytest.mark.parametrize("template_file", [False, True])
    @pytest.mark.parametrize("xmltodict", [False, True])
    def test_rendered_get(
        self, nfclient: object, plugin: str, template_file: bool, xmltodict: bool
    ) -> None:
        """Send a read-only RPC with rendered namespaces through either backend."""
        rpc = (
            '<get xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">'
            '<filter type="subtree"><system xmlns="{{ job_data.namespace }}">'
            "<config><hostname/></config></system></filter></get>"
        )
        result = nfclient.run_job(
            "nornir",
            "netconf_rpc",
            workers="nornir-worker-1",
            kwargs={
                "plugin": plugin,
                "FL": ["ceos-spine-1"],
                "on_failed": True,
                "rpc": "nf://netconf/get_system_rpc.xml" if template_file else rpc,
                "job_data": {"namespace": "http://openconfig.net/yang/system"},
                "to_dict": not template_file,
                "add_details": template_file,
                "xmltodict": xmltodict,
                "run_task_retry": 0,
            },
        )["nornir-worker-1"]
        assert result["failed"] is False, result
        if template_file:
            record = result["result"][0]
            assert record["host"] == "ceos-spine-1"
            assert record["name"] == "rpc"
            value = record["result"]
        else:
            value = result["result"]["ceos-spine-1"]["rpc"]
        assert isinstance(value, dict if xmltodict else str)
        assert "ceos-spine-1" in str(value)
