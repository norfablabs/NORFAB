import copy
import glob
import json
import logging
import logging.config
import os
from datetime import datetime

DEFAULT_NORFAB_LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "class": "logging.Formatter",
            "format": "%(asctime)s.%(msecs)d %(levelname)s [%(name)s:%(lineno)d ] -- %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "norfab_json": {
            "()": "norfab.utils.nflogging.NorFabJsonFormatter",
            "role": "norfab",
            "name": "norfab",
        },
    },
    "handlers": {
        "terminal": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "level": "CRITICAL",
        },
        "file": {
            "backupCount": 30,
            "class": "logging.handlers.RotatingFileHandler",
            "delay": False,
            "encoding": "utf-8",
            "filename": None,
            "formatter": "norfab_json",
            "level": "INFO",
            "maxBytes": 1024000,
            "mode": "a",
        },
    },
    "root": {"handlers": ["terminal", "file"], "level": "INFO"},
}


class NorFabJsonFormatter(logging.Formatter):
    """Format NorFab file logs as JSON lines."""

    OPTIONAL_FIELDS = (
        "service",
        "worker",
        "client",
        "task",
        "job_uuid",
        "event_type",
    )

    def __init__(self, role: str = "norfab", name: str = "norfab") -> None:
        super().__init__()
        self.role = role
        self.name = name

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.fromtimestamp(record.created)
            .astimezone()
            .isoformat(timespec="microseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "pid": record.process,
            "processName": record.processName,
            "threadName": record.threadName,
            "role": self.role,
            "name": self.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "filename": record.filename,
        }

        # Keep task-specific metadata when a caller attaches it with ``extra``.
        for field in self.OPTIONAL_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                data[field] = value
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


def make_logging_config(
    base_dir: str,
    inventory: dict,
    role: str = "norfab",
    name: str = None,
) -> dict:
    """
    Combine inventory logging settings with NorFab default logging config.

    The handler named ``file`` is always treated as NorFab's managed local JSONL
    sink and receives a role/name-specific filename.
    """
    role = str(role or "norfab")
    name = str(name or role)
    filename = os.path.join(base_dir, "__norfab__", "logs", f"{role}-{name}.jsonl")
    log_cfg = copy.deepcopy(inventory or {})
    ret = copy.deepcopy(DEFAULT_NORFAB_LOGGING_CONFIG)

    # Inventory can replace handler settings, but ``file`` remains NorFab's
    # process-specific JSONL sink.
    handlers = log_cfg.pop("handlers", {}) or {}
    ret["handlers"]["terminal"].update(handlers.pop("terminal", {}))
    file_handler = handlers.pop("file", {})
    if (
        file_handler.get("class")
        and file_handler["class"] != ret["handlers"]["file"]["class"]
    ):
        ret["handlers"]["file"] = {
            "level": ret["handlers"]["file"]["level"],
            **file_handler,
        }
    else:
        ret["handlers"]["file"].update(file_handler)
    ret["handlers"]["file"].update(
        {
            "filename": filename,
            "formatter": "norfab_json",
            "encoding": "utf-8",
        }
    )
    ret["handlers"].update(handlers)

    formatters = log_cfg.pop("formatters", {}) or {}
    ret["formatters"]["default"].update(formatters.pop("default", {}))
    ret["formatters"]["norfab_json"].update(formatters.pop("norfab_json", {}))
    ret["formatters"]["norfab_json"].update({"role": role, "name": name})
    ret["formatters"].update(formatters)

    ret["root"].update(log_cfg.pop("root", {}))
    ret["root"].setdefault("handlers", [])
    for handler_name in ("file", "terminal"):
        if handler_name not in ret["root"]["handlers"]:
            ret["root"]["handlers"].append(handler_name)

    # Preserve standard dictConfig sections such as filters and named loggers.
    ret.update(log_cfg)
    ret["disable_existing_loggers"] = False

    return ret


def setup_process_logging(
    base_dir: str,
    role: str,
    name: str = None,
    log_level: str = None,
    inventory_logging: dict = None,
) -> dict:
    """
    Configure logging for the current NorFab-owned process.

    Applications using NFAPI directly own their parent-process logging and can
    call this helper explicitly if they want NorFab JSONL process files.
    """
    config = make_logging_config(
        base_dir=base_dir,
        inventory=inventory_logging or {},
        role=role,
        name=name,
    )
    if log_level is not None:
        config["root"]["level"] = log_level
        for handler in config["handlers"].values():
            handler["level"] = log_level

    os.makedirs(os.path.join(base_dir, "__norfab__", "logs"), exist_ok=True)

    # ``log_events`` is a NorFab worker option, not a dictConfig setting.
    logging.config.dictConfig(
        {key: value for key, value in config.items() if key != "log_events"}
    )
    return config


def read_jsonl_logs(
    logs_dir: str,
    log_files: list[str],
    last: int = 100,
    level: str = None,
    logger: str = None,
    since: str = None,
    until: str = None,
) -> list[dict]:
    """Read and filter NorFab JSONL log records from selected files."""
    records = []
    for log_file in log_files:
        path = os.path.join(logs_dir, log_file)
        for matched_path in glob.glob(path):
            matched_file = os.path.basename(matched_path)
            with open(matched_path, "r", encoding="utf-8") as f:
                for line_number, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        # Return malformed lines as visible error records instead
                        # of making one damaged line hide the rest of the file.
                        record = {
                            "ts": "",
                            "level": "ERROR",
                            "message": f"Malformed log record: {exc}",
                            "line": line_number,
                        }
                    record["log_file"] = matched_file

                    # Apply filters while reading so only matching records are
                    # retained before the final cross-file timestamp ordering.
                    if logger and record.get("logger") != logger:
                        continue
                    if level and record.get("level", "").upper() != level.upper():
                        continue
                    if since and record.get("ts", "") < since:
                        continue
                    if until and record.get("ts", "") > until:
                        continue
                    records.append(record)

    records.sort(key=lambda item: item.get("ts") or "9999")
    return records[-last:] if last else records
