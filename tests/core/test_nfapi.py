import json
import logging
import pprint

import pytest

from norfab.core.nfapi import NorFab
from norfab.utils.nflogging import read_jsonl_logs, setup_process_logging

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
        assert not hasattr(nf, "log_listener")

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
        assert not hasattr(nf, "log_listener")

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
        assert not hasattr(nf, "log_listener")

    def test_nfapi_does_not_replace_parent_root_handlers(self, tmp_path):
        root = logging.getLogger()
        parent_handler = logging.FileHandler(tmp_path / "parent.log")
        old_handlers = root.handlers[:]
        root.addHandler(parent_handler)
        try:
            nf = NorFab(
                inventory="./nf_tests_inventory/inventory.yaml",
                run_broker=False,
                run_workers=False,
            )

            assert parent_handler in root.handlers
            assert not hasattr(nf, "log_listener")
        finally:
            root.removeHandler(parent_handler)
            parent_handler.close()
            for handler in old_handlers:
                if handler not in root.handlers:
                    root.addHandler(handler)

    def test_setup_process_logging_writes_jsonl(self, tmp_path):
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        old_level = root.level
        try:
            setup_process_logging(
                base_dir=str(tmp_path),
                role="worker",
                name="nornir-worker-1",
                log_level="INFO",
                inventory_logging={"handlers": {"file": {"level": "INFO"}}},
            )
            logging.getLogger("norfab.tests").info(
                "JSON log check",
                extra={"task": "cli", "job_uuid": "job-1"},
            )
            for handler in root.handlers:
                handler.flush()

            log_file = tmp_path / "__norfab__" / "logs" / "worker-nornir-worker-1.jsonl"
            record = json.loads(log_file.read_text(encoding="utf-8").splitlines()[-1])

            assert record["message"] == "JSON log check"
            assert record["role"] == "worker"
            assert record["name"] == "nornir-worker-1"
            assert record["module"] == "test_nfapi"
            assert record["function"] == "test_setup_process_logging_writes_jsonl"
            assert record["line"]
            assert record["task"] == "cli"
            assert record["job_uuid"] == "job-1"
            assert "pathname" not in record
        finally:
            for handler in root.handlers[:]:
                root.removeHandler(handler)
                if handler not in old_handlers:
                    handler.close()
            for handler in old_handlers:
                root.addHandler(handler)
            root.setLevel(old_level)

    def test_setup_process_logging_preserves_timed_file_handler(self, tmp_path):
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        old_level = root.level
        try:
            nf = NorFab(
                inventory_data={
                    "broker": {"endpoint": "tcp://127.0.0.1:5555"},
                    "logging": {
                        "handlers": {
                            "file": {
                                "class": ("logging.handlers.TimedRotatingFileHandler"),
                                "when": "midnight",
                                "backupCount": 7,
                            }
                        }
                    },
                },
                base_dir=str(tmp_path),
                run_broker=False,
                run_workers=False,
            )
            config = setup_process_logging(
                base_dir=str(tmp_path),
                role="worker",
                name="nornir-worker-1",
                log_level="INFO",
                inventory_logging=nf.inventory.logging,
            )
            logging.getLogger("norfab.tests").info("timed handler log")
            for handler in root.handlers:
                handler.flush()

            assert (
                config["handlers"]["file"]["class"]
                == "logging.handlers.TimedRotatingFileHandler"
            )
            assert config["handlers"]["file"]["when"] == "midnight"
            assert "maxBytes" not in config["handlers"]["file"]
            assert (
                tmp_path / "__norfab__" / "logs" / "worker-nornir-worker-1.jsonl"
            ).is_file()
        finally:
            for handler in root.handlers[:]:
                root.removeHandler(handler)
                if handler not in old_handlers:
                    handler.close()
            for handler in old_handlers:
                root.addHandler(handler)
            root.setLevel(old_level)

    def test_nfapi_setup_logging_accepts_process_name(self, tmp_path):
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        old_level = root.level
        try:
            nf = NorFab(
                inventory_data={"broker": {"endpoint": "tcp://127.0.0.1:5555"}},
                base_dir=str(tmp_path),
                run_broker=False,
                run_workers=False,
            )
            nf.setup_logging(name="nfcli")
            logging.getLogger("norfab.tests").info("named process log")
            for handler in root.handlers:
                handler.flush()

            log_file = tmp_path / "__norfab__" / "logs" / "nfapi-nfcli.jsonl"
            record = json.loads(log_file.read_text(encoding="utf-8").splitlines()[-1])

            assert record["role"] == "nfapi"
            assert record["name"] == "nfcli"
            assert record["message"] == "named process log"
        finally:
            for handler in root.handlers[:]:
                root.removeHandler(handler)
                if handler not in old_handlers:
                    handler.close()
            for handler in old_handlers:
                root.addHandler(handler)
            root.setLevel(old_level)

    def test_nfapi_configure_logging_during_init(self, tmp_path):
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        old_level = root.level
        try:
            NorFab(
                inventory_data={"broker": {"endpoint": "tcp://127.0.0.1:5555"}},
                base_dir=str(tmp_path),
                log_level="INFO",
                configure_logging=True,
                logging_name="tui",
                run_broker=False,
                run_workers=False,
            )
            logging.getLogger("norfab.tests").info("constructor configured log")
            for handler in root.handlers:
                handler.flush()

            log_file = tmp_path / "__norfab__" / "logs" / "nfapi-tui.jsonl"
            record = json.loads(log_file.read_text(encoding="utf-8").splitlines()[-1])

            assert record["role"] == "nfapi"
            assert record["name"] == "tui"
            assert record["message"] == "constructor configured log"
        finally:
            for handler in root.handlers[:]:
                root.removeHandler(handler)
                if handler not in old_handlers:
                    handler.close()
            for handler in old_handlers:
                root.addHandler(handler)
            root.setLevel(old_level)

    def test_nfapi_bootstrap_logging_captures_inventory_logs(self, tmp_path):
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        old_level = root.level
        hooks_dir = tmp_path / "bootstrap_logging_hooks"
        hooks_dir.mkdir()
        (hooks_dir / "__init__.py").write_text("", encoding="utf-8")
        (hooks_dir / "startup.py").write_text(
            "def do_on_startup(norfab):\n    return None\n", encoding="utf-8"
        )
        inventory_file = tmp_path / "inventory.yaml"
        inventory_file.write_text(
            "\n".join(
                [
                    "broker:",
                    '  endpoint: "tcp://127.0.0.1:5555"',
                    "hooks:",
                    "  startup:",
                    "    - function: bootstrap_logging_hooks.startup:do_on_startup",
                    "      args: []",
                    "      kwargs: {}",
                ]
            ),
            encoding="utf-8",
        )

        try:
            NorFab(
                inventory=str(inventory_file),
                log_level="INFO",
                configure_logging=True,
                logging_name="nfcli",
                run_broker=False,
                run_workers=False,
            )
            for handler in root.handlers:
                handler.flush()

            log_file = tmp_path / "__norfab__" / "logs" / "nfapi-nfcli.jsonl"
            records = [
                json.loads(line)
                for line in log_file.read_text(encoding="utf-8").splitlines()
            ]

            assert any(
                record["logger"] == "norfab.core.inventory"
                and "Successfully loaded hook function" in record["message"]
                for record in records
            )
        finally:
            for handler in root.handlers[:]:
                root.removeHandler(handler)
                if handler not in old_handlers:
                    handler.close()
            for handler in old_handlers:
                root.addHandler(handler)
            root.setLevel(old_level)

    def test_read_jsonl_logs_filters_and_keeps_malformed_records(self, tmp_path):
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        log_file = logs_dir / "worker-nornir-worker-1.jsonl"
        log_file.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "ts": "2026-06-24T10:00:00.000000+10:00",
                            "level": "INFO",
                            "role": "worker",
                            "name": "nornir-worker-1",
                            "logger": "norfab.core.worker",
                            "message": "Started",
                            "pid": 1,
                        }
                    ),
                    json.dumps(
                        {
                            "ts": "2026-06-24T10:01:00.000000+10:00",
                            "level": "ERROR",
                            "role": "worker",
                            "name": "nornir-worker-1",
                            "logger": "norfab.core.worker",
                            "message": "Failed",
                            "pid": 1,
                        }
                    ),
                    "{bad-json",
                ]
            ),
            encoding="utf-8",
        )

        records = read_jsonl_logs(
            logs_dir=str(logs_dir),
            log_files=["worker-nornir-worker-1.jsonl"],
            level="ERROR",
        )

        assert len(records) == 2
        assert records[0]["message"] == "Failed"
        assert records[0]["log_file"] == "worker-nornir-worker-1.jsonl"
        assert records[1]["message"].startswith("Malformed log record:")

    def test_load_inventory_from_dictionary(self, nfclient_dict_inventory):
        # test that NorFab started and workers are started as well
        reply = nfclient_dict_inventory.mmi("mmi.service.broker", "show_workers")

        ret = reply["results"]
        pprint.pprint(ret)

        assert len(ret) > 0
        for worker in ret:
            assert all(k in worker for k in ["holdtime", "name", "service", "status"])
