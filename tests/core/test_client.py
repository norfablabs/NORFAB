import pprint
import json
import time
from uuid import uuid4


class TestClientApi:
    def test_mmi_show_workers(self, nfclient):
        reply = nfclient.mmi(b"mmi.service.broker", "show_workers")

        ret = reply["results"]
        pprint.pprint(ret)

        assert ret, "No workers status returned"
        for worker in ret:
            assert all(k in worker for k in ["holdtime", "name", "service", "status"])

    def test_mmi_show_workers_nornir(self, nfclient):
        reply = nfclient.mmi(b"mmi.service.broker", "show_workers", kwargs={"service": "nornir"})

        ret = reply["results"]
        pprint.pprint(ret)

        assert ret, "No workers status returned"
        for worker in ret:
            assert all(k in worker for k in ["holdtime", "name", "service", "status"])

    def test_mmi_show_broker(self, nfclient):
        reply = nfclient.mmi("mmi.service.broker", "show_broker")

        ret = reply["results"]
        pprint.pprint(ret)

        for k in [
            "endpoint",
            "keepalives",
            "services count",
            "status",
            "workers count",
        ]:
            assert k in ret, "Not all broker params returned"
            assert ret[k], "Some broker params seems wrong"

    def test_mmi_show_broker_version(self, nfclient):
        reply = nfclient.mmi("mmi.service.broker", "show_broker_version")

        ret = reply["results"]
        pprint.pprint(ret)

        for k in [
            "norfab",
            "python",
            "platform",
        ]:
            assert k in ret, "Not all broker params returned"
            assert ret[k], "Some broker params seems wrong"

    def test_mmi_show_broker_inventory(self, nfclient):
        reply = nfclient.mmi("mmi.service.broker", "show_broker_inventory")

        ret = reply["results"]
        pprint.pprint(ret)

        for k in ["broker", "logging", "workers", "topology"]:
            assert k in ret, "Not all broker params returned"
            assert ret[k], "Some broker params seems wrong"

    def test_mmi_sid_inventory(self, nfclient):
        reply = nfclient.mmi("sid.service.broker", "get_inventory", kwargs={"name": "nornir-worker-1"})

        ret = reply["results"]
        pprint.pprint(ret)

        assert ret, "nornir-worker-1 inventory not returned"
        for k in ["defaults", "groups", "hosts", "service"]:
            assert k in ret, "Not all worker params returned"
            assert ret[k], "Some worker inventory params seems wrong"


class TestClientRunJob:

    def test_generic_markdown_output(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "get_inventory",
            markdown=True,
        )
        print(ret)
        assert "Overall Summary" in ret
        assert "Worker:" in ret
        assert "Results" in ret
