from typing import Any, Dict, List, Union

from picle.models import ConfigModel
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr

from norfab.models.norfab_configuration_logging import (
    LoggingConfig,
)
from norfab.workers.netbox_worker.netbox_models import NetboxConfigModel

# ------------------------------------------------------
# Agent profile configuration models
# ------------------------------------------------------


class AgentLLMConfig(BaseModel):
    """LLM provider configuration for an agent profile."""

    provider: StrictStr = Field(
        ...,
        description="LLM provider name: openai, anthropic, ollama, groq, mistral, openrouter, google, bedrock",
    )
    model: StrictStr = Field(
        None,
        description="Model name, e.g. 'gpt-4o' or 'anthropic/claude-3.5-sonnet'",
    )
    api_key: StrictStr = Field(
        None,
        description="API key; supports Jinja2 env var syntax e.g. '${MY_API_KEY}'",
    )
    base_url: StrictStr = Field(
        None,
        description="Custom base URL, required for openrouter or self-hosted models",
    )
    temperature: StrictFloat = Field(
        None,
        description="Sampling temperature (0.0 = deterministic)",
    )


class AgentMCPServerConfig(BaseModel):
    """Single MCP server connection configuration."""

    name: StrictStr = Field(..., description="Unique MCP server name")
    transport: StrictStr = Field(
        "stdio",
        description="Transport type: stdio, sse, streamable-http",
    )
    command: StrictStr = Field(
        None,
        description="Executable command for stdio transport",
    )
    args: List[Any] = Field(
        None,
        description="Arguments list for the stdio command",
    )
    url: StrictStr = Field(
        None,
        description="Server URL for sse or streamable-http transport",
    )


class AgentMCPConfig(BaseModel):
    """MCP server tools configuration for an agent profile."""

    enabled: StrictBool = Field(False, description="Enable MCP server tools")
    servers: List[AgentMCPServerConfig] = Field(
        None,
        description="List of MCP server definitions",
    )


class AgentRAGConfig(BaseModel):
    """RAG knowledge base configuration for an agent profile."""

    enabled: StrictBool = Field(False, description="Enable RAG knowledge base tool")
    embed_model: StrictStr = Field(
        "sentence-transformers/all-MiniLM-L6-v2",
        description="fastembed-compatible embeddings model name",
    )
    collection: StrictStr = Field("norfab", description="Vector collection name")
    persist_dir: StrictStr = Field(
        None,
        description="Directory to persist the vector store; supports '{profile}' placeholder",
    )
    top_k: StrictInt = Field(4, description="Number of documents to retrieve")
    sources: List[StrictStr] = Field(
        None,
        description="List of file paths or directories to index into the knowledge base",
    )


class AgentMemoryConfig(BaseModel):
    """Conversation memory configuration for an agent profile."""

    enabled: StrictBool = Field(False, description="Enable conversation memory")
    backend: StrictStr = Field(
        "buffer",
        description="Memory backend: buffer (in-process), sqlite (persistent)",
    )


class AgentProfile(BaseModel):
    """Single named agent profile configuration."""

    llm: AgentLLMConfig = Field(..., description="LLM provider configuration")
    tools: Dict[StrictStr, Any] = Field(
        None,
        description="Tools configuration, e.g. {norfab_services: true}",
    )
    mcp: AgentMCPConfig = Field(
        None,
        description="External MCP server tools configuration",
    )
    rag: AgentRAGConfig = Field(
        None,
        description="RAG knowledge base configuration",
    )
    memory: AgentMemoryConfig = Field(
        None,
        description="Conversation memory configuration",
    )
    system_prompt: StrictStr = Field(
        None,
        description="System prompt for the agent",
    )


class ClientConfig(BaseModel):
    """NorFab client-side configuration."""

    agent_profiles: Dict[StrictStr, AgentProfile] = Field(
        None,
        description="Named agent profiles for NFPClient.get_agent()",
        json_schema_extra={"pkey": "profile_name", "pkey_description": "Profile name"},
    )


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
    autostart_watchdog: StrictBool = Field(
        None, description="Start watch dog on worker startup"
    )
    watchdog_interval: StrictInt = Field(
        30, description="Intervals between watchdog thread runs"
    )
    memory_threshold_mbyte: StrictInt = Field(1000, description="RAM usage threshold")
    memory_threshold_action: StrictStr = Field(
        "log", description="RAM threshold exceed action"
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
    client: ClientConfig = Field(
        None,
        description="Client-side configuration including agent profiles",
    )
