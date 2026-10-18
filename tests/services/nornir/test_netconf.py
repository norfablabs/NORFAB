"""NETCONF task tests; live tests require the cEOS integration lab."""

from xml.etree import ElementTree

import pytest

pytestmark = [pytest.mark.nornir, pytest.mark.nornir_netconf]


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
