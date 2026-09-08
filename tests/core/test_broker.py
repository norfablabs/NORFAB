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
        initial_reply = nfclient.mmi("mmi.service.broker", "get_stats")
        initial = {
            worker["name"]: (
                worker["keepalives_sent"],
                worker["keepalives_received"],
            )
            for worker in initial_reply["results"]["workers"]
        }

        deadline = time.time() + 10
        while time.time() < deadline:
            time.sleep(0.5)
            current_reply = nfclient.mmi("mmi.service.broker", "get_stats")
            current = {
                worker["name"]: (
                    worker["keepalives_sent"],
                    worker["keepalives_received"],
                )
                for worker in current_reply["results"]["workers"]
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

    def test_get_stats_reports_broker_resources_and_messages(self, nfclient) -> None:
        reply = nfclient.mmi("mmi.service.broker", "get_stats")

        assert reply["status"] == "200"
        result = reply["results"]
        assert result["schema_version"] == "1.0"
        assert result["role"] == "broker"
        assert result["status"] == "active"
        assert result["keepalive_interval_ms"] > 0
        assert result["keepalive_multiplier"] > 0
        assert result["worker_count"] > 0
        assert result["service_count"] > 0
        assert result["process"]["cpu_percent"] >= 0
        assert result["process"]["memory_rss_mbyte"] > 0
        assert result["process"]["uptime_seconds"] >= 0
        assert result["messaging"]["received"] > 0

    def test_get_status_reports_broker_environment(self, nfclient) -> None:
        reply = nfclient.mmi("mmi.service.broker", "get_status")

        assert reply["status"] == "200"
        result = reply["results"]
        assert result["role"] == "broker"
        assert result["status"] == "active"
        assert result["endpoint"]
        assert result["directories"]["broker_base_dir"]
        assert result["security"]["zmq_auth"] is False
        assert result["security"]["broker_private_key_file"] is None
