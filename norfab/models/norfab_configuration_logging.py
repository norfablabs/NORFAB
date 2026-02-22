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
        examples=["logging.Formatter", "mypackage.formatters.ColourFormatter"],
    )
    format: StrictStr = Field(
        None,
        description="Log record format string.",
        examples=[
            "%(asctime)s.%(msecs)d %(levelname)s [%(name)s:%(lineno)d ] -- %(message)s"
        ],
    )
    datefmt: StrictStr = Field(
        None,
        description="Date/time format string passed to time.strftime().",
        examples=["%Y-%m-%d %H:%M:%S"],
    )
    style: Literal["%", "{", "$"] = Field(
        None,
        description=(
            "Format string style. "
            "'%' (printf, default), '{' (str.format), or '$' (string.Template)."
        ),
        examples=["%"],
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
        examples=[{"app": "norfab", "env": "production"}],
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
        examples=["norfab", "norfab.workers"],
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
        examples=[
            "logging.StreamHandler",
            "logging.FileHandler",
            "logging.handlers.RotatingFileHandler",
            "logging.handlers.TimedRotatingFileHandler",
            "logging.handlers.SysLogHandler",
            "logging.handlers.SMTPHandler",
            "logging.handlers.SocketHandler",
            "logging.handlers.MemoryHandler",
            "logging.handlers.QueueHandler",
        ],
    )
    level: StrictStr = Field(
        None,
        description="Minimum severity level for this handler.",
        examples=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    formatter: StrictStr = Field(
        None,
        description="Id of the formatter (key in formatters) to use with this handler.",
        examples=["default", "brief", "precise"],
    )
    filters: List[StrictStr] = Field(
        None,
        description="List of filter ids (keys in filters) to attach to this handler.",
        examples=[["allow_foo", "deny_bar"]],
    )
    # ---- Common handler constructor kwargs (kept typed for IDE support) ----
    # StreamHandler
    stream: StrictStr = Field(
        None,
        description=(
            "Stream for logging.StreamHandler. "
            "Use ext://sys.stdout or ext://sys.stderr."
        ),
        examples=["ext://sys.stderr", "ext://sys.stdout"],
    )
    # FileHandler / RotatingFileHandler / TimedRotatingFileHandler
    filename: StrictStr = Field(
        None,
        description="Absolute or relative path to the log file.",
        examples=["/var/log/norfab/norfab.log", "logs/norfab.log"],
    )
    mode: StrictStr = Field(
        None,
        description="File open mode for file-based handlers.",
        examples=["a", "w"],
    )
    encoding: StrictStr = Field(
        None,
        description="File encoding for file-based handlers.",
        examples=["utf-8"],
    )
    delay: StrictBool = Field(
        None,
        description=(
            "If True, file creation is deferred until the first record is emitted. "
            "Applies to FileHandler and subclasses."
        ),
        examples=[False],
    )
    # RotatingFileHandler
    maxBytes: StrictInt = Field(
        None,
        description=(
            "Maximum log file size in bytes before rollover "
            "(RotatingFileHandler). 0 disables rollover."
        ),
        examples=[1024000, 10485760],
    )
    backupCount: StrictInt = Field(
        None,
        description=(
            "Number of backup files to keep after rollover "
            "(RotatingFileHandler / TimedRotatingFileHandler)."
        ),
        examples=[5, 50],
    )
    # TimedRotatingFileHandler
    when: StrictStr = Field(
        None,
        description=(
            "Rollover interval type for TimedRotatingFileHandler. "
            "One of: 'S', 'M', 'H', 'D', 'W0'–'W6', 'midnight'."
        ),
        examples=["midnight", "H", "D"],
    )
    interval: StrictInt = Field(
        None,
        description="Rollover interval value for TimedRotatingFileHandler.",
        examples=[1, 6, 12],
    )
    utc: StrictBool = Field(
        None,
        description=("Use UTC for rollover timing in TimedRotatingFileHandler."),
        examples=[False],
    )
    # SysLogHandler
    address: Union[StrictStr, List[Any]] = Field(
        None,
        description="Address for SysLogHandler, e.g. '/dev/log' or ['host', port].",
        examples=["/dev/log", ["localhost", 514]],
    )
    facility: StrictInt = Field(
        None,
        description="Syslog facility code for SysLogHandler.",
        examples=[1],
    )
    socktype: StrictInt = Field(
        None,
        description=(
            "Socket type for SysLogHandler: socket.SOCK_DGRAM (2) or "
            "socket.SOCK_STREAM (1)."
        ),
        examples=[2],
    )
    # SMTPHandler
    mailhost: Union[StrictStr, List[Any]] = Field(
        None,
        description="SMTP host (string) or [host, port] for SMTPHandler.",
        examples=["smtp.example.com", ["smtp.example.com", 587]],
    )
    fromaddr: StrictStr = Field(
        None,
        description="Sender address for SMTPHandler.",
        examples=["norfab@example.com"],
    )
    toaddrs: List[StrictStr] = Field(
        None,
        description="Recipient address list for SMTPHandler.",
        examples=[["ops@example.com"]],
    )
    subject: StrictStr = Field(
        None,
        description="Email subject for SMTPHandler.",
        examples=["NorFab – alert"],
    )
    # MemoryHandler
    capacity: StrictInt = Field(
        None,
        description="Buffer capacity (number of records) for MemoryHandler.",
        examples=[100],
    )
    flushLevel: StrictStr = Field(
        None,
        description="Level that triggers a flush for MemoryHandler.",
        examples=["ERROR"],
    )
    target: StrictStr = Field(
        None,
        description="Target handler id for MemoryHandler (cfg://handlers.<id>).",
        examples=["cfg://handlers.file"],
    )
    # QueueHandler
    queue: StrictStr = Field(
        None,
        description=(
            "Queue factory callable path or cfg:// reference for QueueHandler. "
            "Defaults to an unbounded queue.Queue if omitted."
        ),
        examples=["my.module.queue_factory"],
    )
    listener: StrictStr = Field(
        None,
        description=(
            "QueueListener subclass path for QueueHandler. "
            "Defaults to logging.handlers.QueueListener."
        ),
        examples=["my.package.CustomListener"],
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
        examples=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "NOTSET"],
    )
    handlers: List[StrictStr] = Field(
        None,
        description="List of handler ids (keys in handlers) to attach to this logger.",
        examples=[["terminal", "file"]],
    )
    filters: List[StrictStr] = Field(
        None,
        description="List of filter ids (keys in filters) to attach to this logger.",
        examples=[["allow_foo"]],
    )
    propagate: StrictBool = Field(
        None,
        description=(
            "Whether records should propagate to ancestor loggers. "
            "Not applicable for the root logger."
        ),
        examples=[True, False],
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
        examples=[1],
    )
    disable_existing_loggers: StrictBool = Field(
        True,
        description=(
            "If True (Python stdlib default), any loggers that exist at "
            "configuration time and are not explicitly named are disabled. "
            "Set to False to preserve existing loggers."
        ),
        examples=[False],
    )
    incremental: StrictBool = Field(
        False,
        description=(
            "If True, the configuration is applied incrementally — only the "
            "level and propagate settings of existing handlers and loggers "
            "are updated; formatters and filters are ignored."
        ),
        examples=[False],
    )
    formatters: Dict[StrictStr, LoggingFormatterConfig] = Field(
        None,
        description="Named formatter definitions keyed by formatter id.",
        examples=[
            {
                "default": {
                    "class": "logging.Formatter",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                    "format": "%(asctime)s.%(msecs)d %(levelname)s [%(name)s:%(lineno)d ] -- %(message)s",
                },
                "brief": {"format": "%(levelname)s %(message)s"},
            }
        ],
    )
    filters: Dict[StrictStr, LoggingFilterConfig] = Field(
        None,
        description="Named filter definitions keyed by filter id.",
        examples=[{"norfab_only": {"name": "norfab"}}],
    )
    handlers: Dict[StrictStr, LoggingHandlerConfig] = Field(
        None,
        description="Name of handler definitions",
        examples=[
            {
                "terminal": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "level": "WARNING",
                    "stream": "ext://sys.stderr",
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
                    "delay": False,
                },
            }
        ],
    )
    loggers: Dict[StrictStr, LoggingLoggerConfig] = Field(
        None,
        description=(
            "Per-logger configurations keyed by logger name "
            "(as used in logging.getLogger(name))."
        ),
        examples=[
            {
                "norfab.workers": {"level": "DEBUG", "propagate": True},
                "norfab.broker": {
                    "level": "INFO",
                    "handlers": ["file"],
                    "propagate": False,
                },
            }
        ],
    )
    root: LoggingLoggerConfig = Field(
        None,
        description=(
            "Root logger configuration. propagate is not applicable here. "
            "All loggers without an explicit propagate=False ultimately forward "
            "records to the root logger."
        ),
        examples=[{"level": "INFO", "handlers": ["terminal", "file"]}],
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
        examples=[True],
    )
