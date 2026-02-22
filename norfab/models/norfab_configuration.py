from pydantic import BaseModel, StrictBool, StrictInt, StrictStr, Field, ConfigDict
from typing import Union, List, Any, Dict
from norfab.models.norfab_configuration_logging import (
    LoggingConfig,
    LoggingFormatterConfig,
    LoggingFilterConfig,
    LoggingHandlerConfig,
    LoggingLoggerConfig,
)
from picle.models import ConfigModel

# ------------------------------------------------------
# Broker configuration models
# ------------------------------------------------------


class BrokerConfig(BaseModel):
    """NorFab broker connection configuration."""

    endpoint: StrictStr = Field(
        ...,
        description="Broker ZMQ endpoint address",
        examples=["tcp://192.168.1.128:5555"],
    )
    shared_key: StrictStr = Field(
        None,
        description="Shared key for ZMQ CURVE authentication",
        examples=["D>[[2]NH9#dN5?!o5DtibYYvV)ev?oRl}#P[>(q3"],
    )
    zmq_auth: StrictBool = Field(
        None,
        description="Enable ZMQ CURVE authentication",
        examples=[True],
    )


# ------------------------------------------------------
# Hooks configuration models
# ------------------------------------------------------


class HookItem(BaseModel):
    """Single hook function definition."""

    function: StrictStr = Field(
        ...,
        description="Hook function name to call",
        examples=["do_on_startup", "do_on_exit", "nornir_do_on_startup"],
    )
    description: StrictStr = Field(
        None,
        description="Human-readable description of the hook",
        examples=["Function to run on startup"],
    )
    args: List[Any] = Field(
        None,
        description="Positional arguments to pass to the hook function",
        examples=[[]],
    )
    kwargs: Dict[str, Any] = Field(
        None,
        description="Keyword arguments to pass to the hook function",
        examples=[{}],
    )


class HooksConfig(BaseModel):
    """
    NorFab lifecycle hooks configuration.

    Each field corresponds to a named hook event. A hook event is a list of
    callables (``HookItem``) that are invoked in order when the event fires.
    """

    model_config = ConfigDict(populate_by_name=True)

    startup: List[HookItem] = Field(
        None,
        description="Hooks executed once when the worker process starts up",
        examples=[
            [
                {
                    "function": "do_on_startup",
                    "description": "Function to run on startup",
                    "args": [],
                    "kwargs": {},
                }
            ]
        ],
    )
    exit: List[HookItem] = Field(
        None,
        description="Hooks executed once when the worker process is about to exit",
        examples=[
            [
                {
                    "function": "do_on_exit",
                    "description": "Function to run on exit",
                    "args": [],
                    "kwargs": {},
                }
            ]
        ],
    )
    nornir_startup: List[HookItem] = Field(
        None,
        alias="nornir-startup",
        description="Hooks executed after the Nornir instance is initialised",
        examples=[
            [
                {
                    "function": "nornir_do_on_startup",
                    "description": "Function to run on Nornir startup",
                    "args": [],
                    "kwargs": {},
                }
            ]
        ],
    )
    nornir_exit: List[HookItem] = Field(
        None,
        alias="nornir-exit",
        description="Hooks executed before the Nornir instance is torn down",
        examples=[
            [
                {
                    "function": "nornir_do_on_exit",
                    "description": "Function to run on Nornir exit",
                    "args": [],
                    "kwargs": {},
                }
            ]
        ],
    )


# ------------------------------------------------------
# Logging configuration models
# (defined in norfab_configuration_logging.py)
# ------------------------------------------------------
# LoggingConfig, LoggingFormatterConfig, LoggingFilterConfig,
# LoggingHandlerConfig, LoggingLoggerConfig are imported at the top of this file.


# ------------------------------------------------------
# Plugins configuration models
# ------------------------------------------------------


class PluginNfcliConfig(BaseModel):
    """Plugin NorFab CLI integration configuration."""

    mount_path: StrictStr = Field(
        ...,
        description="CLI shell mount path for the plugin",
        examples=["dummy"],
    )
    shell_model: StrictStr = Field(
        ...,
        description="Dotted import path to the plugin shell model class",
        examples=["plugins.dummy_service:DummyServiceNfcliShell"],
    )


class PluginConfig(BaseModel):
    """Single plugin entry configuration."""

    worker: StrictStr = Field(
        None,
        description="Dotted import path to the plugin worker class",
        examples=["plugins.dummy_service:DummyServiceWorker"],
    )
    nfcli: PluginNfcliConfig = Field(
        None,
        description="NorFab CLI integration configuration for this plugin",
        examples=[
            {
                "mount_path": "dummy",
                "shell_model": "plugins.dummy_service:DummyServiceNfcliShell",
            }
        ],
    )


# ------------------------------------------------------
# Topology configuration models
# ------------------------------------------------------


class WorkerTopologyConfig(BaseModel):
    """Per-worker topology settings."""

    depends_on: List[StrictStr] = Field(
        None,
        description="List of worker names that must be running before this worker starts",
        examples=[["netbox-worker-1.1", "netbox-worker-1.2"]],
    )


# Workers list items can be plain strings or single-key dicts:
# "nornir-worker-1"  ->  StrictStr
# {"nornir-worker-5": {"depends_on": [...]}}  ->  Dict[StrictStr, WorkerTopologyConfig]
TopologyWorkerEntry = Union[StrictStr, Dict[StrictStr, WorkerTopologyConfig]]


class TopologyConfig(BaseModel):
    """NorFab deployment topology configuration."""

    broker: StrictBool = Field(
        True,
        description="Start broker as part of this topology",
        examples=[True],
    )
    workers: List[TopologyWorkerEntry] = Field(
        None,
        description="Ordered list of workers to start in this topology",
        examples=[
            [
                "nornir-worker-1",
                "netbox-worker-1.1",
                {
                    "nornir-worker-5": {
                        "depends_on": ["netbox-worker-1.1", "netbox-worker-1.2"]
                    }
                },
            ]
        ],
    )


# ------------------------------------------------------
# Workers inventory configuration models
# ------------------------------------------------------

# Each workers entry value is a list of inventory sources.
# A source can be a YAML file path (str) or an inline dict with worker settings.
WorkerInventoryEntry = Union[StrictStr, Dict[StrictStr, Any]]


# ------------------------------------------------------
# Top-level NorFab inventory model
# ------------------------------------------------------


class NorFabInventory(ConfigModel):
    """
    Top-level NorFab inventory / configuration model.

    Attributes:
        broker: Broker connection settings shared by all components.
        hooks: Named lifecycle hooks mapping event names to lists of callables.
        logging: Python dictConfig-compatible logging configuration.
        plugins: Third-party service plugin registrations.
        topology: Describes which broker and workers to launch.
        workers: Per-worker (or glob-matched) inventory source lists.
    """

    class PicleConfig:
        config_file = "inventory.yaml"
        subshell = True
        prompt = "norfab-config#"
        backup_on_save = 5

    broker: BrokerConfig = Field(
        None,
        description="Broker configuration",
        examples=[
            {
                "endpoint": "tcp://192.168.1.128:5555",
                "shared_key": "D>[[2]NH9#dN5?!o5DtibYYvV)ev?oRl}#P[>(q3",
                "zmq_auth": True,
            }
        ],
    )
    hooks: HooksConfig = Field(
        None,
        description="Lifecycle hooks for named worker events",
        examples=[
            {
                "startup": [
                    {
                        "function": "do_on_startup",
                        "description": "Function to run on startup",
                        "args": [],
                        "kwargs": {},
                    }
                ],
                "exit": [
                    {
                        "function": "do_on_exit",
                        "description": "Function to run on exit",
                        "args": [],
                        "kwargs": {},
                    }
                ],
                "nornir-startup": [
                    {
                        "function": "nornir_do_on_startup",
                        "description": "Function to run on Nornir startup",
                        "args": [],
                        "kwargs": {},
                    }
                ],
                "nornir-exit": [
                    {
                        "function": "nornir_do_on_exit",
                        "description": "Function to run on Nornir exit",
                        "args": [],
                        "kwargs": {},
                    }
                ],
            }
        ],
    )
    logging: LoggingConfig = Field(
        None,
        description="Logging configuration (Python dictConfig format)",
        examples=[
            {
                "version": 1,
                "disable_existing_loggers": False,
                "log_events": True,
                "root": {"level": "INFO", "handlers": ["terminal", "file"]},
            }
        ],
    )
    plugins: Dict[StrictStr, PluginConfig] = Field(
        None,
        description="Registered service plugins",
        examples=[
            {
                "DummyService": {
                    "worker": "plugins.dummy_service:DummyServiceWorker",
                    "nfcli": {
                        "mount_path": "dummy",
                        "shell_model": "plugins.dummy_service:DummyServiceNfcliShell",
                    },
                }
            }
        ],
    )
    topology: TopologyConfig = Field(
        None,
        description="Deployment topology (broker and workers to start)",
        examples=[
            {
                "broker": True,
                "workers": [
                    "nornir-worker-1",
                    "netbox-worker-1.1",
                    {"nornir-worker-5": {"depends_on": ["netbox-worker-1.1"]}},
                ],
            }
        ],
    )
    workers: Dict[StrictStr, List[WorkerInventoryEntry]] = Field(
        None,
        description=(
            "Worker inventory sources keyed by worker name or glob pattern. "
            "Each value is a list of YAML file paths or inline inventory dicts."
        ),
        examples=[
            {
                "nornir-*": ["nornir/common.yaml"],
                "nornir-worker-1": ["nornir/nornir-worker-1.yaml"],
                "filesharing-worker-1": [
                    {"base_dir": "/path/to/inventory", "service": "filesharing"}
                ],
            }
        ],
    )
