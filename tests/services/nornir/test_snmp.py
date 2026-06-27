import pprint
import pytest

pytestmark = [pytest.mark.nornir, pytest.mark.snmp, pytest.mark.task_nornir_snmp]


@pytest.mark.task_nornir_snmp
class TestSnmpWorker:
    """cEOS integration tests for SNMP tasks."""

    def test_snmp_get(self, nfclient):
        """Verify snmp_get returns sysName matching hostname."""
        ret = nfclient.run_job(
            "nornir",
            "snmp_get",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={"oid": "1.3.6.1.2.1.1.5.0"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed"
            for host, res in results["result"].items():
                assert "get" in res, f"{worker}:{host} missing 'get' key"
                oid_val = res["get"].get("1.3.6.1.2.1.1.5.0", "")
                assert (
                    host in oid_val
                ), f"{worker}:{host} sysName '{oid_val}' does not contain hostname"

    def test_snmp_getnext(self, nfclient):
        """Verify snmp_getnext returns an OID after the requested OID."""
        ret = nfclient.run_job(
            "nornir",
            "snmp_getnext",
            workers=["nornir-worker-1"],
            kwargs={"oid": "1.3.6.1.2.1.1.5.0"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed"
            for host, res in results["result"].items():
                assert "getnext" in res, f"{worker}:{host} missing 'getnext' key"

    def test_snmp_multiget(self, nfclient):
        """Verify snmp_multiget returns sysDescr and sysName."""
        ret = nfclient.run_job(
            "nornir",
            "snmp_multiget",
            workers=["nornir-worker-1"],
            kwargs={
                "oids": ["1.3.6.1.2.1.1.1.0", "1.3.6.1.2.1.1.5.0"],
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed"
            for host, res in results["result"].items():
                assert "multiget" in res, f"{worker}:{host} missing 'multiget' key"

    def test_snmp_walk(self, nfclient):
        """Verify snmp_walk walks the system subtree."""
        ret = nfclient.run_job(
            "nornir",
            "snmp_walk",
            workers=["nornir-worker-1"],
            kwargs={"oid": "1.3.6.1.2.1.1"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed"
            for host, res in results["result"].items():
                assert "walk" in res, f"{worker}:{host} missing 'walk' key"
                # Should have at least sysDescr and sysName
                assert (
                    len(res["walk"]) >= 2
                ), f"{worker}:{host} walk returned too few OIDs"

    def test_snmp_multiwalk(self, nfclient):
        """Verify snmp_multiwalk walks system and interface subtrees."""
        ret = nfclient.run_job(
            "nornir",
            "snmp_multiwalk",
            workers=["nornir-worker-1"],
            kwargs={
                "oids": ["1.3.6.1.2.1.1", "1.3.6.1.2.1.2.2"],
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed"
            for host, res in results["result"].items():
                assert "multiwalk" in res, f"{worker}:{host} missing 'multiwalk' key"

    def test_snmp_bulkget(self, nfclient):
        """Verify snmp_bulkget returns scalar and column data."""
        ret = nfclient.run_job(
            "nornir",
            "snmp_bulkget",
            workers=["nornir-worker-1"],
            kwargs={
                "scalar_oids": ["1.3.6.1.2.1.1.5.0"],
                "repeating_oids": ["1.3.6.1.2.1.2.2.1.2"],
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed"
            for host, res in results["result"].items():
                assert "bulkget" in res, f"{worker}:{host} missing 'bulkget' key"

    def test_snmp_bulkwalk(self, nfclient):
        """Verify snmp_bulkwalk returns interface OID/value pairs."""
        ret = nfclient.run_job(
            "nornir",
            "snmp_bulkwalk",
            workers=["nornir-worker-1"],
            kwargs={"oids": ["1.3.6.1.2.1.2.2.1.2"]},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed"
            for host, res in results["result"].items():
                assert "bulkwalk" in res, f"{worker}:{host} missing 'bulkwalk' key"

    def test_snmp_table(self, nfclient):
        """Verify snmp_table returns interface table rows."""
        ret = nfclient.run_job(
            "nornir",
            "snmp_table",
            workers=["nornir-worker-1"],
            kwargs={"oid": "1.3.6.1.2.1.2.2"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed"
            for host, res in results["result"].items():
                assert "table" in res, f"{worker}:{host} missing 'table' key"

    def test_snmp_bulktable(self, nfclient):
        """Verify snmp_bulktable returns interface table rows using GETBULK."""
        ret = nfclient.run_job(
            "nornir",
            "snmp_bulktable",
            workers=["nornir-worker-1"],
            kwargs={"oid": "1.3.6.1.2.1.2.2"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed"
            for host, res in results["result"].items():
                assert "bulktable" in res, f"{worker}:{host} missing 'bulktable' key"

    def test_snmp_host_filters(self, nfclient):
        """Verify host filters restrict SNMP results."""
        ret = nfclient.run_job(
            "nornir",
            "snmp_get",
            kwargs={"oid": "1.3.6.1.2.1.1.5.0", "FC": "spine"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed"
            for host in results["result"]:
                assert "spine" in host, f"Non-spine host {host} matched FC=spine"

    def test_snmp_no_match(self, nfclient):
        """Verify no_match status when no hosts match filters."""
        ret = nfclient.run_job(
            "nornir",
            "snmp_get",
            kwargs={"oid": "1.3.6.1.2.1.1.5.0", "FC": "nonexistent"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False
            assert results["status"] == "no_match"

    def test_snmp_invalid_model(self, nfclient):
        """Verify invalid model arguments fail validation."""
        # Missing OID
        ret = nfclient.run_job(
            "nornir",
            "snmp_get",
            kwargs={},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is True
            assert "ValidationError" in results["errors"][0]

    def test_snmp_set_and_restore(self, nfclient):
        """Verify snmp_set writes a value and restores original."""
        # Read current sysLocation
        ret = nfclient.run_job(
            "nornir",
            "snmp_get",
            workers=["nornir-worker-1"],
            kwargs={"oid": "1.3.6.1.2.1.1.6.0", "FC": "spine"},
        )
        pprint.pprint(ret)

        # Save original value
        original_values = {}
        for worker, results in ret.items():
            for host, res in results["result"].items():
                original_values[host] = res["get"].get("1.3.6.1.2.1.1.6.0", "")

        try:
            # Set new value
            test_value = "NorFab SNMP test"
            ret = nfclient.run_job(
                "nornir",
                "snmp_set",
                workers=["nornir-worker-1"],
                kwargs={
                    "oid": "1.3.6.1.2.1.1.6.0",
                    "value": test_value,
                    "FC": "spine",
                },
            )
            pprint.pprint(ret)

            for worker, results in ret.items():
                assert results["failed"] is False, f"{worker} snmp_set failed"

            # Verify value was set
            ret = nfclient.run_job(
                "nornir",
                "snmp_get",
                workers=["nornir-worker-1"],
                kwargs={"oid": "1.3.6.1.2.1.1.6.0", "FC": "spine"},
            )
            pprint.pprint(ret)

            for worker, results in ret.items():
                for host, res in results["result"].items():
                    assert test_value in res["get"].get(
                        "1.3.6.1.2.1.1.6.0", ""
                    ), f"{worker}:{host} value was not set correctly"

        finally:
            # Restore original values
            for host, orig_val in original_values.items():
                if orig_val:
                    nfclient.run_job(
                        "nornir",
                        "snmp_set",
                        workers=["nornir-worker-1"],
                        kwargs={
                            "oid": "1.3.6.1.2.1.1.6.0",
                            "value": orig_val,
                            "FL": [host],
                        },
                    )

    def test_snmp_multiset_and_restore(self, nfclient):
        """Verify snmp_multiset writes multiple values and restores originals."""
        # Read current values
        ret = nfclient.run_job(
            "nornir",
            "snmp_multiget",
            workers=["nornir-worker-1"],
            kwargs={
                "oids": ["1.3.6.1.2.1.1.6.0", "1.3.6.1.2.1.1.4.0"],
                "FC": "spine",
            },
        )
        pprint.pprint(ret)

        # Save original values
        original_values = {}
        for worker, results in ret.items():
            for host, res in results["result"].items():
                original_values[host] = {
                    "1.3.6.1.2.1.1.6.0": res["multiget"].get("1.3.6.1.2.1.1.6.0", ""),
                    "1.3.6.1.2.1.1.4.0": res["multiget"].get("1.3.6.1.2.1.1.4.0", ""),
                }

        try:
            # Set new values
            ret = nfclient.run_job(
                "nornir",
                "snmp_multiset",
                workers=["nornir-worker-1"],
                kwargs={
                    "mappings": {
                        "1.3.6.1.2.1.1.6.0": "NorFab test location",
                        "1.3.6.1.2.1.1.4.0": "norfab@test.local",
                    },
                    "FC": "spine",
                },
            )
            pprint.pprint(ret)

            for worker, results in ret.items():
                assert results["failed"] is False, f"{worker} snmp_multiset failed"

            # Verify values were set
            ret = nfclient.run_job(
                "nornir",
                "snmp_multiget",
                workers=["nornir-worker-1"],
                kwargs={
                    "oids": ["1.3.6.1.2.1.1.6.0", "1.3.6.1.2.1.1.4.0"],
                    "FC": "spine",
                },
            )
            pprint.pprint(ret)

            for worker, results in ret.items():
                for host, res in results["result"].items():
                    assert "NorFab test location" in res["multiget"].get(
                        "1.3.6.1.2.1.1.6.0", ""
                    ), f"{worker}:{host} sysLocation not set"
                    assert "norfab@test.local" in res["multiget"].get(
                        "1.3.6.1.2.1.1.4.0", ""
                    ), f"{worker}:{host} sysContact not set"

        finally:
            # Restore original values
            for host, orig in original_values.items():
                restore_mappings = {}
                if orig.get("1.3.6.1.2.1.1.6.0"):
                    restore_mappings["1.3.6.1.2.1.1.6.0"] = orig["1.3.6.1.2.1.1.6.0"]
                if orig.get("1.3.6.1.2.1.1.4.0"):
                    restore_mappings["1.3.6.1.2.1.1.4.0"] = orig["1.3.6.1.2.1.1.4.0"]
                if restore_mappings:
                    nfclient.run_job(
                        "nornir",
                        "snmp_multiset",
                        workers=["nornir-worker-1"],
                        kwargs={
                            "mappings": restore_mappings,
                            "FL": [host],
                        },
                    )
