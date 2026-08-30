import time

import pytest

pytestmark = pytest.mark.core


class TestBroker:
    def test_broker_registers_live_workers(self, nfclient) -> None:
        reply = nfclient.mmi("mmi.service.broker", "show_workers")

        assert reply["status"] == "200"
        workers = [worker for worker in reply["results"] if worker["name"]]
        assert workers
        assert all(worker["service"] for worker in workers)
        assert all(worker["status"] in {"alive", "dead"} for worker in workers)

    def test_broker_exchanges_worker_keepalives(self, nfclient) -> None:
        initial_reply = nfclient.mmi("mmi.service.broker", "show_workers")
        initial = {
            worker["name"]: tuple(
                int(value.strip()) for value in worker["keepalives tx/rx"].split("/")
            )
            for worker in initial_reply["results"]
            if worker["name"]
        }

        deadline = time.time() + 10
        while time.time() < deadline:
            time.sleep(0.5)
            current_reply = nfclient.mmi("mmi.service.broker", "show_workers")
            current = {
                worker["name"]: tuple(
                    int(value.strip())
                    for value in worker["keepalives tx/rx"].split("/")
                )
                for worker in current_reply["results"]
                if worker["name"] in initial
            }
            if any(
                current[name][0] > counts[0] and current[name][1] > counts[1]
                for name, counts in initial.items()
                if name in current
            ):
                break
        else:
            pytest.fail("Broker keepalive counters did not advance")

    def test_show_broker_status_and_process_resources(self, nfclient) -> None:
        reply = nfclient.mmi("mmi.service.broker", "show_broker")

        assert reply["status"] == "200"
        result = reply["results"]
        assert result["status"] == "active"
        assert result["keepalives"]["interval"] > 0
        assert result["keepalives"]["multiplier"] > 0
        assert result["workers count"] > 0
        assert result["services count"] > 0
        assert isinstance(result["cpu_percent"], (int, float))
        assert result["cpu_percent"] >= 0
        assert result["memory_rss_mbyte"] > 0
        assert result["uptime_seconds"] >= 0
