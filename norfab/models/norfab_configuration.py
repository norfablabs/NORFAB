from typing import Any, Dict, List, Union

from picle.models import ConfigModel
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from norfab.models.norfab_configuration_logging import (
    LoggingConfig,
)
from norfab.workers.netbox_worker.netbox_models import NetboxConfigModel

# ------------------------------------------------------
# Broker configuration models
# ------------------------------------------------------


class BrokerConfig(BaseModel):
    """NorFab broker connection configuration."""

    endpoint: StrictStr = Field(
        ...,
        description="Broker ZMQ endpoint address",
    )
    shared_key: StrictStr = Field(
        None,
        description="Shared key for ZMQ CURVE authentication",
    )
    zmq_auth: StrictBool = Field(
        None,
        description="Enable ZMQ CURVE authentication",
        json_schema_extra={"presence": True},
    )


# ------------------------------------------------------
# Hooks configuration models
# ------------------------------------------------------


class HookItem(BaseModel):
    """Single hook function definition."""

    function: StrictStr = Field(
        ...,
        description="Hook function name to call",
    )
    description: StrictStr = Field(
        None,
        description="Human-readable description of the hook",
    )
    args: List[Any] = Field(
        None,
        description="Positional arguments to pass to the hook function",
    )
    kwargs: Dict[str, Any] = Field(
        None,
        description="Keyword arguments to pass to the hook function",
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
    )
    exit: List[HookItem] = Field(
        None,
        description="Hooks executed once when the worker process is about to exit",
    )
    nornir_startup: List[HookItem] = Field(
        None,
        alias="nornir-startup",
        description="Hooks executed after the Nornir instance is initialised",
    )
    nornir_exit: List[HookItem] = Field(
        None,
        alias="nornir-exit",
        description="Hooks executed before the Nornir instance is torn down",
    )


# ------------------------------------------------------
# Plugins configuration models
# ------------------------------------------------------


class PluginNfcliConfig(BaseModel):
    """Plugin NorFab CLI integration configuration."""

    mount_path: StrictStr = Field(
        ...,
        description="CLI shell mount path for the plugin",
    )
    shell_model: StrictStr = Field(
        ...,
        description="Dotted import path to the plugin shell model class",
    )


class PluginConfig(BaseModel):
    """Single plugin entry configuration."""

    worker: StrictStr = Field(
        None,
        description="Dotted import path to the plugin worker class",
    )
    nfcli: PluginNfcliConfig = Field(
        None,
        description="NorFab CLI integration configuration for this plugin",
    )


# ------------------------------------------------------
# Topology configuration models
# ------------------------------------------------------


class WorkerTopologyConfig(BaseModel):
    """Per-worker topology settings."""

    depends_on: List[StrictStr] = Field(
        None,
        description="List of worker names that must be running before this worker starts",
    )


TopologyWorkerEntry = Union[StrictStr, Dict[StrictStr, WorkerTopologyConfig]]


class TopologyConfig(BaseModel):
    """NorFab deployment topology configuration."""

    broker: StrictBool = Field(
        True,
        description="Start broker as part of this topology",
    )
    workers: List[TopologyWorkerEntry] = Field(
        None,
        description="Ordered list of workers to start in this topology",
    )


# ------------------------------------------------------
# Workers inventory configuration models
# ------------------------------------------------------


class NorfabServices(BaseModel):
    netbox: NetboxConfigModel = Field(None, description="Netbox workers configuration")


class WorkerInventoryEntry(BaseModel):
    service: NorfabServices = Field(None, description="Service name")
    jobs_compress: StrictBool = Field(None, description="Enable jobs compression")
    max_concurrent_jobs: StrictInt = Field(
        None, description="Maximum number of threads to run jobs"
    )


# ------------------------------------------------------
# Top-level NorFab inventory model
# ------------------------------------------------------


class NorFabInventory(ConfigModel):

    class PicleConfig:
        config_file = "inventory.yaml"
        subshell = True
        prompt = "norfab-config#"
        backup_on_save = 5

    broker: BrokerConfig = Field(
        None,
        description="Broker configuration",
    )
    hooks: HooksConfig = Field(
        None,
        description="Lifecycle hooks for named worker events",
    )
    logging: LoggingConfig = Field(
        None,
        description="Logging configuration (Python dictConfig format)",
    )
    plugins: Dict[StrictStr, PluginConfig] = Field(
        None,
        description="Registered service plugins",
        json_schema_extra={"pkey": "plugin_name", "pkey_description": "Plugin name"},
    )
    topology: TopologyConfig = Field(
        None,
        description="Deployment topology (broker and workers to start)",
    )
    workers: Dict[StrictStr, WorkerInventoryEntry] = Field(
        None,
        description="Worker inventory sources keyed by worker name or glob pattern",
        json_schema_extra={"pkey": "worker_name", "pkey_description": "Worker name"},
    )
