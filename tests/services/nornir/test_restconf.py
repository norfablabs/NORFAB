"""Core RESTCONF integration tests against the cEOS lab."""

import pytest

pytestmark = [pytest.mark.nornir, pytest.mark.nornir_restconf]


class TestRestconfGet:
    def test_openconfig_interfaces(self, nfclient: object) -> None:
        result = nfclient.run_job(
            "nornir",
            "restconf_get",
            workers="nornir-worker-1",
            kwargs={
                "FL": ["ceos-spine-1", "ceos-spine-2"],
                "openconfig_interfaces": True,
            },
        )["nornir-worker-1"]
        assert result["failed"] is False, result
        for host in ["ceos-spine-1", "ceos-spine-2"]:
            assert "Management0" in [
                interface["name"]
                for interface in result["result"][host]["get"][
                    "openconfig-interfaces:interface"
                ]
            ]

    def test_openconfig_lldp(self, nfclient: object) -> None:
        result = nfclient.run_job(
            "nornir",
            "restconf_get",
            workers="nornir-worker-1",
            kwargs={
                "FL": ["ceos-spine-1", "ceos-spine-2"],
                "openconfig_lldp": True,
            },
        )["nornir-worker-1"]
        assert result["failed"] is False, result
        for host in ["ceos-spine-1", "ceos-spine-2"]:
            assert (
                result["result"][host]["get"]["openconfig-lldp:state"][
                    "chassis-id-type"
                ]
                == "MAC_ADDRESS"
            )

    def test_openconfig_system(self, nfclient: object) -> None:
        result = nfclient.run_job(
            "nornir",
            "restconf_get",
            workers="nornir-worker-1",
            kwargs={
                "FL": ["ceos-spine-1", "ceos-spine-2"],
                "openconfig_system": True,
            },
        )["nornir-worker-1"]
        assert result["failed"] is False, result
        for host in ["ceos-spine-1", "ceos-spine-2"]:
            assert (
                result["result"][host]["get"]["openconfig-system:state"]["hostname"]
                == host
            )

    def test_spine_hostnames(self, nfclient: object) -> None:
        result = nfclient.run_job(
            "nornir",
            "restconf_get",
            workers="nornir-worker-1",
            kwargs={
                "FL": ["ceos-spine-1", "ceos-spine-2"],
                "url": "openconfig-system:system/state/hostname",
            },
        )["nornir-worker-1"]
        assert result["failed"] is False, result
        assert result["result"]["ceos-spine-1"]["get"] == {
            "openconfig-system:hostname": "ceos-spine-1"
        }
        assert result["result"]["ceos-spine-2"]["get"] == {
            "openconfig-system:hostname": "ceos-spine-2"
        }


class TestRestconfOwnedMutation:
    def test_owned_mutation(self, nfclient: object) -> None:
        result = nfclient.run_job(
            "nornir",
            "restconf_get",
            workers="nornir-worker-1",
            kwargs={
                "FL": ["ceos-spine-1"],
                "on_failed": True,
                "url": "openconfig-interfaces:interfaces/interface=Loopback987",
            },
        )["nornir-worker-1"]
        assert result["failed"] is True, "test requires an absent owned loopback"
        try:
            result = nfclient.run_job(
                "nornir",
                "restconf_put",
                workers="nornir-worker-1",
                kwargs={
                    "FL": ["ceos-spine-1"],
                    "on_failed": True,
                    "url": "openconfig-interfaces:interfaces/interface=Loopback987/config",
                    "data": '{"openconfig-interfaces:name": "Loopback987", "openconfig-interfaces:type": "iana-if-type:softwareLoopback", "openconfig-interfaces:description": "norfab-restconf-test"}',
                },
            )["nornir-worker-1"]
            assert result["failed"] is False, result
            result = nfclient.run_job(
                "nornir",
                "restconf_get",
                workers="nornir-worker-1",
                kwargs={
                    "FL": ["ceos-spine-1"],
                    "on_failed": True,
                    "url": "openconfig-interfaces:interfaces/interface=Loopback987/config/description",
                },
            )["nornir-worker-1"]
            assert result["failed"] is False, result
            assert result["result"]["ceos-spine-1"]["get"] == {
                "openconfig-interfaces:description": "norfab-restconf-test"
            }
        finally:
            result = nfclient.run_job(
                "nornir",
                "restconf_delete",
                workers="nornir-worker-1",
                kwargs={
                    "FL": ["ceos-spine-1"],
                    "on_failed": True,
                    "url": "openconfig-interfaces:interfaces/interface=Loopback987",
                },
            )["nornir-worker-1"]
            assert result["failed"] is False, result


class TestRestconfInlineRendering:
    def test_inline_rendering(self, nfclient: object) -> None:
        result = nfclient.run_job(
            "nornir",
            "restconf_get",
            workers="nornir-worker-1",
            kwargs={
                "FL": ["ceos-spine-1"],
                "on_failed": True,
                "url": "openconfig-interfaces:interfaces/interface=Loopback988",
            },
        )["nornir-worker-1"]
        assert result["failed"] is True, "test requires an absent owned loopback"
        try:
            result = nfclient.run_job(
                "nornir",
                "restconf_put",
                workers="nornir-worker-1",
                kwargs={
                    "FL": ["ceos-spine-1"],
                    "on_failed": True,
                    "url": "openconfig-interfaces:interfaces/interface=Loopback988/config",
                    "data": '{"openconfig-interfaces:name": "Loopback988", "openconfig-interfaces:type": "iana-if-type:softwareLoopback", "openconfig-interfaces:description": "{{ host.name }}"}',
                },
            )["nornir-worker-1"]
            assert result["failed"] is False, result
            result = nfclient.run_job(
                "nornir",
                "restconf_get",
                workers="nornir-worker-1",
                kwargs={
                    "FL": ["ceos-spine-1"],
                    "on_failed": True,
                    "url": "openconfig-interfaces:interfaces/interface=Loopback988/config/description",
                },
            )["nornir-worker-1"]
            assert result["failed"] is False, result
            assert result["result"]["ceos-spine-1"]["get"] == {
                "openconfig-interfaces:description": "ceos-spine-1"
            }
        finally:
            result = nfclient.run_job(
                "nornir",
                "restconf_delete",
                workers="nornir-worker-1",
                kwargs={
                    "FL": ["ceos-spine-1"],
                    "on_failed": True,
                    "url": "openconfig-interfaces:interfaces/interface=Loopback988",
                },
            )["nornir-worker-1"]
            assert result["failed"] is False, result


class TestRestconfFileRendering:
    def test_file_rendering(self, nfclient: object) -> None:
        result = nfclient.run_job(
            "nornir",
            "restconf_get",
            workers="nornir-worker-1",
            kwargs={
                "FL": ["ceos-spine-1"],
                "on_failed": True,
                "url": "openconfig-interfaces:interfaces/interface=Loopback989",
            },
        )["nornir-worker-1"]
        assert result["failed"] is True, "test requires an absent owned loopback"
        try:
            result = nfclient.run_job(
                "nornir",
                "restconf_put",
                workers="nornir-worker-1",
                kwargs={
                    "FL": ["ceos-spine-1"],
                    "on_failed": True,
                    "url": "openconfig-interfaces:interfaces/interface=Loopback989/config",
                    "data": "nf://http/owned-resource.json.j2",
                },
            )["nornir-worker-1"]
            assert result["failed"] is False, result
            result = nfclient.run_job(
                "nornir",
                "restconf_get",
                workers="nornir-worker-1",
                kwargs={
                    "FL": ["ceos-spine-1"],
                    "on_failed": True,
                    "url": "openconfig-interfaces:interfaces/interface=Loopback989/config/description",
                },
            )["nornir-worker-1"]
            assert result["failed"] is False, result
            assert result["result"]["ceos-spine-1"]["get"] == {
                "openconfig-interfaces:description": "ceos-spine-1"
            }
        finally:
            result = nfclient.run_job(
                "nornir",
                "restconf_delete",
                workers="nornir-worker-1",
                kwargs={
                    "FL": ["ceos-spine-1"],
                    "on_failed": True,
                    "url": "openconfig-interfaces:interfaces/interface=Loopback989",
                },
            )["nornir-worker-1"]
            assert result["failed"] is False, result


class TestRestconfFailure:
    def test_missing_resource(self, nfclient: object) -> None:
        result = nfclient.run_job(
            "nornir",
            "restconf_get",
            workers="nornir-worker-1",
            kwargs={
                "FL": ["ceos-spine-1"],
                "on_failed": True,
                "url": "openconfig-interfaces:interfaces/interface=Loopback987654",
            },
        )["nornir-worker-1"]
        assert result["failed"] is True, result
        assert result["resources_failed"] == ["ceos-spine-1"]


class TestRestconfPost:
    def test_post_resource(self, nfclient: object) -> None:
        result = nfclient.run_job(
            "nornir",
            "restconf_get",
            workers="nornir-worker-1",
            kwargs={
                "FL": ["ceos-spine-1"],
                "on_failed": True,
                "url": "openconfig-interfaces:interfaces/interface=Loopback990",
            },
        )["nornir-worker-1"]
        assert result["failed"] is True, "test requires an absent owned loopback"
        try:
            result = nfclient.run_job(
                "nornir",
                "restconf_post",
                workers="nornir-worker-1",
                kwargs={
                    "FL": ["ceos-spine-1"],
                    "on_failed": True,
                    "url": "openconfig-interfaces:interfaces/interface=Loopback990/config",
                    "data": '{"openconfig-interfaces:name": "Loopback990", "openconfig-interfaces:type": "iana-if-type:softwareLoopback", "openconfig-interfaces:description": "norfab-restconf-test"}',
                },
            )["nornir-worker-1"]
            assert result["failed"] is False, result
            result = nfclient.run_job(
                "nornir",
                "restconf_get",
                workers="nornir-worker-1",
                kwargs={
                    "FL": ["ceos-spine-1"],
                    "on_failed": True,
                    "url": "openconfig-interfaces:interfaces/interface=Loopback990/config/description",
                },
            )["nornir-worker-1"]
            assert result["failed"] is False, result
            assert result["result"]["ceos-spine-1"]["get"] == {
                "openconfig-interfaces:description": "norfab-restconf-test"
            }
        finally:
            result = nfclient.run_job(
                "nornir",
                "restconf_delete",
                workers="nornir-worker-1",
                kwargs={
                    "FL": ["ceos-spine-1"],
                    "on_failed": True,
                    "url": "openconfig-interfaces:interfaces/interface=Loopback990",
                },
            )["nornir-worker-1"]
            assert result["failed"] is False, result
