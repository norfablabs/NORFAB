import pprint

import pytest

from norfab.core.nfapi import NorFab

pytestmark = pytest.mark.core


class TestNfApi:
    def test_load_dot_env_before_inventory(self, monkeypatch):
        monkeypatch.delenv("NFAPI_TEST_VARIABLE", raising=False)

        nf = NorFab(
            inventory="./nf_tests_inventory/inventory.yaml",
            run_broker=False,
            run_workers=False,
        )

        assert (
            nf.list_environment_variables()["NFAPI_TEST_VARIABLE"] == "loaded from .env"
        )
        assert nf.list_environment_variables()["NFAPI_TEST_EXPORTED"] == "loaded too"
        assert nf.inventory.client["nfapi_test_variable"] == "loaded from .env"
        nf.log_listener.stop()

    def test_dot_env_overrides_environment(self, monkeypatch):
        monkeypatch.setenv("NFAPI_TEST_VARIABLE", "existing environment value")

        nf = NorFab(
            inventory="./nf_tests_inventory/inventory.yaml",
            run_broker=False,
            run_workers=False,
        )

        assert (
            nf.list_environment_variables()["NFAPI_TEST_VARIABLE"] == "loaded from .env"
        )
        assert nf.inventory.client["nfapi_test_variable"] == "loaded from .env"
        nf.log_listener.stop()

    def test_dot_env_override_can_be_disabled(self, monkeypatch):
        monkeypatch.setenv("NFAPI_TEST_VARIABLE", "existing environment value")

        nf = NorFab(
            inventory="./nf_tests_inventory/inventory.yaml",
            run_broker=False,
            run_workers=False,
            load_env_override=False,
        )

        assert (
            nf.list_environment_variables()["NFAPI_TEST_VARIABLE"]
            == "existing environment value"
        )
        assert (
            nf.inventory.client["nfapi_test_variable"] == "existing environment value"
        )
        nf.log_listener.stop()

    def test_load_inventory_from_dictionary(self, nfclient_dict_inventory):
        # test that NorFab started and workers are started as well
        reply = nfclient_dict_inventory.mmi("mmi.service.broker", "show_workers")

        ret = reply["results"]
        pprint.pprint(ret)

        assert len(ret) > 0
        for worker in ret:
            assert all(k in worker for k in ["holdtime", "name", "service", "status"])
