"""
Pydantic models for Python logging.config.dictConfig() configuration schema.

Reference: https://docs.python.org/3/library/logging.config.html#logging-config-dictschema

The top-level model is LoggingConfig, which is a full, typed representation of
the dictConfig dictionary schema including the NorFab-specific log_events extension.
"""

from pydantic import BaseModel, StrictBool, StrictInt, StrictStr, Field, ConfigDict
from typing import Literal, Union, List, Any, Dict

# ------------------------------------------------------
# Formatter models
# ------------------------------------------------------


class LoggingFormatterConfig(BaseModel):
    """
    Configuration for a single Python logging formatter (dictConfig formatters entry).

    Corresponds to arguments passed to logging.Formatter.__init__() plus an
    optional class key for custom formatter subclasses, or a () key for a
    fully user-defined factory callable.

    Reference: https://docs.python.org/3/library/logging.config.html#dictionary-schema-details
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    class_: StrictStr = Field(
        None,
        alias="class",
        description=(
            "Dotted path to a custom Formatter subclass. "
            "Omit to use the default logging.Formatter."
        ),
    )
    format: StrictStr = Field(
        None,
        description="Log record format string.",
    )
    datefmt: StrictStr = Field(
        None,
        description="Date/time format string passed to time.strftime().",
    )
    style: Literal["%", "{", "$"] = Field(
        None,
        description=(
            "Format string style. "
            "'%' (printf, default), '{' (str.format), or '$' (string.Template)."
        ),
    )
    validate_: StrictBool = Field(
        None,
        description=(
            "If True (default), validate the format string against the log record "
            "fields. Added in Python 3.8."
        ),
        examples=[True],
        alias="validate",
    )
    defaults: Dict[StrictStr, Any] = Field(
        None,
        description=(
            "A dictionary of default values for custom formatting fields, "
            "available for use in the format string. Added in Python 3.12."
        ),
    )


# ------------------------------------------------------
# Filter models
# ------------------------------------------------------


class LoggingFilterConfig(BaseModel):
    """
    Configuration for a single Python logging filter (dictConfig filters entry).

    For the built-in logging.Filter provide name (logger name prefix).
    For user-defined filters supply a () factory key (extra fields allowed).

    Reference: https://docs.python.org/3/library/logging.config.html#dictionary-schema-details
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: StrictStr = Field(
        None,
        description=(
            "Logger name prefix for the built-in logging.Filter. "
            "Only records from loggers whose name starts with this value are passed through. "
            "Empty string (default) allows every record."
        ),
    )


# ------------------------------------------------------
# Handler models
# ------------------------------------------------------


class LoggingHandlerConfig(BaseModel):
    """
    Configuration for a single Python logging handler (dictConfig handlers entry).

    class is mandatory. All unrecognised keys are forwarded as keyword arguments
    to the handler's constructor, so handler-specific parameters (filename,
    maxBytes, stream, …) are stored via extra="allow".

    Reference: https://docs.python.org/3/library/logging.config.html#dictionary-schema-details
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    class_: StrictStr = Field(
        ...,
        alias="class",
        description="Fully-qualified dotted path to the handler class (mandatory).",
    )
    level: StrictStr = Field(
        None,
        description="Minimum severity level for this handler.",
    )
    formatter: StrictStr = Field(
        None,
        description="Id of the formatter (key in formatters) to use with this handler.",
    )
    filters: List[StrictStr] = Field(
        None,
        description="List of filter ids (keys in filters) to attach to this handler.",
    )
    # ---- Common handler constructor kwargs (kept typed for IDE support) ----
    # StreamHandler
    stream: StrictStr = Field(
        None,
        description=(
            "Stream for logging.StreamHandler. "
            "Use ext://sys.stdout or ext://sys.stderr."
        ),
    )
    # FileHandler / RotatingFileHandler / TimedRotatingFileHandler
    filename: StrictStr = Field(
        None,
        description="Absolute or relative path to the log file.",
    )
    mode: StrictStr = Field(
        None,
        description="File open mode for file-based handlers.",
    )
    encoding: StrictStr = Field(
        None,
        description="File encoding for file-based handlers.",
    )
    delay: StrictBool = Field(
        None,
        description=(
            "If True, file creation is deferred until the first record is emitted. "
            "Applies to FileHandler and subclasses."
        ),
    )
    # RotatingFileHandler
    maxBytes: StrictInt = Field(
        None,
        description=(
            "Maximum log file size in bytes before rollover "
            "(RotatingFileHandler). 0 disables rollover."
        ),
    )
    backupCount: StrictInt = Field(
        None,
        description=(
            "Number of backup files to keep after rollover "
            "(RotatingFileHandler / TimedRotatingFileHandler)."
        ),
    )
    # TimedRotatingFileHandler
    when: StrictStr = Field(
        None,
        description=(
            "Rollover interval type for TimedRotatingFileHandler. "
            "One of: 'S', 'M', 'H', 'D', 'W0'–'W6', 'midnight'."
        ),
    )
    interval: StrictInt = Field(
        None,
        description="Rollover interval value for TimedRotatingFileHandler.",
    )
    utc: StrictBool = Field(
        None,
        description=("Use UTC for rollover timing in TimedRotatingFileHandler."),
    )
    # SysLogHandler
    address: Union[StrictStr, List[Any]] = Field(
        None,
        description="Address for SysLogHandler, e.g. '/dev/log' or ['host', port].",
    )
    facility: StrictInt = Field(
        None,
        description="Syslog facility code for SysLogHandler.",
    )
    socktype: StrictInt = Field(
        None,
        description=(
            "Socket type for SysLogHandler: socket.SOCK_DGRAM (2) or "
            "socket.SOCK_STREAM (1)."
        ),
    )
    # SMTPHandler
    mailhost: Union[StrictStr, List[Any]] = Field(
        None,
        description="SMTP host (string) or [host, port] for SMTPHandler.",
    )
    fromaddr: StrictStr = Field(
        None,
        description="Sender address for SMTPHandler.",
    )
    toaddrs: List[StrictStr] = Field(
        None,
        description="Recipient address list for SMTPHandler.",
    )
    subject: StrictStr = Field(
        None,
        description="Email subject for SMTPHandler.",
    )
    # MemoryHandler
    capacity: StrictInt = Field(
        None,
        description="Buffer capacity (number of records) for MemoryHandler.",
    )
    flushLevel: StrictStr = Field(
        None,
        description="Level that triggers a flush for MemoryHandler.",
    )
    target: StrictStr = Field(
        None,
        description="Target handler id for MemoryHandler (cfg://handlers.<id>).",
    )
    # QueueHandler
    queue: StrictStr = Field(
        None,
        description=(
            "Queue factory callable path or cfg:// reference for QueueHandler. "
            "Defaults to an unbounded queue.Queue if omitted."
        ),
    )
    listener: StrictStr = Field(
        None,
        description=(
            "QueueListener subclass path for QueueHandler. "
            "Defaults to logging.handlers.QueueListener."
        ),
    )


# ------------------------------------------------------
# Logger models
# ------------------------------------------------------


class LoggingLoggerConfig(BaseModel):
    """
    Configuration for a named logger or the root logger (dictConfig loggers /
    root entry).

    Reference: https://docs.python.org/3/library/logging.config.html#dictionary-schema-details
    """

    level: StrictStr = Field(
        None,
        description="Logger severity level.",
    )
    handlers: List[StrictStr] = Field(
        None,
        description="List of handler ids (keys in handlers) to attach to this logger.",
    )
    filters: List[StrictStr] = Field(
        None,
        description="List of filter ids (keys in filters) to attach to this logger.",
    )
    propagate: StrictBool = Field(
        None,
        description=(
            "Whether records should propagate to ancestor loggers. "
            "Not applicable for the root logger."
        ),
    )


# ------------------------------------------------------
# Top-level logging configuration model
# ------------------------------------------------------


class LoggingConfig(BaseModel):
    """
    Full logging.config.dictConfig()-compatible configuration model.

    This model covers the complete dictConfig schema (version 1) and adds the
    NorFab-specific log_events flag.

    Reference: https://docs.python.org/3/library/logging.config.html#logging-config-dictschema

    Example (minimal)::

        {
            "version": 1,
            "disable_existing_loggers": false,
            "handlers": {
                "terminal": {"class": "logging.StreamHandler", "level": "WARNING"}
            },
            "root": {"level": "INFO", "handlers": ["terminal"]}
        }

    Example (full)::

        {
            "version": 1,
            "disable_existing_loggers": false,
            "incremental": false,
            "formatters": {
                "default": {
                    "class": "logging.Formatter",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                    "format": "%(asctime)s.%(msecs)d %(levelname)s [%(name)s:%(lineno)d ] -- %(message)s"
                }
            },
            "filters": {
                "norfab_only": {"name": "norfab"}
            },
            "handlers": {
                "terminal": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "level": "WARNING",
                    "stream": "ext://sys.stderr"
                },
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "formatter": "default",
                    "level": "INFO",
                    "filename": "/var/log/norfab/norfab.log",
                    "maxBytes": 1024000,
                    "backupCount": 50,
                    "encoding": "utf-8",
                    "mode": "a",
                    "delay": false
                }
            },
            "loggers": {
                "norfab.workers": {"level": "DEBUG", "propagate": true}
            },
            "root": {"level": "INFO", "handlers": ["terminal", "file"]},
            "log_events": true
        }
    """

    version: StrictInt = Field(
        1,
        description=(
            "dictConfig schema version. Must be 1 — the only valid value "
            "in the current Python standard library."
        ),
    )
    disable_existing_loggers: StrictBool = Field(
        True,
        description=(
            "If True (Python stdlib default), any loggers that exist at "
            "configuration time and are not explicitly named are disabled. "
            "Set to False to preserve existing loggers."
        ),
    )
    incremental: StrictBool = Field(
        False,
        description=(
            "If True, the configuration is applied incrementally — only the "
            "level and propagate settings of existing handlers and loggers "
            "are updated; formatters and filters are ignored."
        ),
    )
    formatters: Dict[StrictStr, LoggingFormatterConfig] = Field(
        None,
        description="Named formatter definitions keyed by formatter id.",
    )
    filters: Dict[StrictStr, LoggingFilterConfig] = Field(
        None,
        description="Named filter definitions keyed by filter id.",
    )
    handlers: Dict[StrictStr, LoggingHandlerConfig] = Field(
        None,
        description="Name of handler definitions",
    )
    loggers: Dict[StrictStr, LoggingLoggerConfig] = Field(
        None,
        description=(
            "Per-logger configurations keyed by logger name "
            "(as used in logging.getLogger(name))."
        ),
    )
    root: LoggingLoggerConfig = Field(
        None,
        description=(
            "Root logger configuration. propagate is not applicable here. "
            "All loggers without an explicit propagate=False ultimately forward "
            "records to the root logger."
        ),
    )
    # ------------------------------------------------------------------
    # NorFab extension — not part of the Python dictConfig standard
    # ------------------------------------------------------------------
    log_events: StrictBool = Field(
        None,
        description=(
            "NorFab-specific flag. When True, NorFab system events are forwarded "
            "to the Python logging system in addition to the internal event bus."
        ),
    )
