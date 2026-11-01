import asyncio
import concurrent.futures
import copy
import importlib
import logging
import os
import sqlite3
import uuid
from fnmatch import fnmatch
from typing import Callable, Iterator

from langchain.agents import create_agent
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import MemorySaver

log = logging.getLogger(__name__)


class AgentProgress(BaseCallbackHandler):
    """Report model and tool activity to a message/severity event receiver."""

    def __init__(self, event: Callable) -> None:
        self.event = event

    def on_chat_model_start(
        self, serialized: dict, messages: list, **kwargs: object
    ) -> None:
        self.event("thinking...", severity="INFO")

    def on_tool_start(self, serialized: dict, input_str: str, **kwargs: object) -> None:
        self.event(f"calling {serialized['name']}", severity="INFO")

    def on_tool_end(self, output: object, **kwargs: object) -> None:
        self.event(f"tool {kwargs['name']} completed", severity="INFO")

    def on_tool_error(self, error: BaseException, **kwargs: object) -> None:
        self.event(f"tool failed: {error}", severity="ERROR")


# ------------------------------------------------------------------------------------------
# LLM Factory
# ------------------------------------------------------------------------------------------

# Maps provider name → (module, class).  OpenRouter reuses ChatOpenAI with a
# custom base_url, so no extra package is needed beyond langchain-openai.
_PROVIDER_MAP = {
    "openai": ("langchain_openai", "ChatOpenAI"),
    "anthropic": ("langchain_anthropic", "ChatAnthropic"),
    "ollama": ("langchain_ollama", "ChatOllama"),
    "groq": ("langchain_groq", "ChatGroq"),
    "mistral": ("langchain_mistralai", "ChatMistralAI"),
    "openrouter": ("langchain_openai", "ChatOpenAI"),
    "google": ("langchain_google_genai", "ChatGoogleGenerativeAI"),
    "bedrock": ("langchain_aws", "ChatBedrock"),
}


def _make_llm(cfg: dict) -> BaseChatModel:
    """Instantiate a LangChain chat model from an agent profile LLM config dict.

    Args:
        cfg (dict): Provider selector and provider constructor arguments.

    Returns:
        BaseChatModel: Instantiated LangChain chat model.
    """
    provider = cfg.get("provider", "openai").lower()
    if provider not in _PROVIDER_MAP:
        raise ValueError(
            f"Unsupported LLM provider '{provider}'. "
            f"Supported: {sorted(_PROVIDER_MAP)}"
        )

    module_name, class_name = _PROVIDER_MAP[provider]
    try:
        mod = importlib.import_module(module_name)
    except ImportError as exc:
        raise ImportError(
            f"LLM provider '{provider}' requires '{module_name}'. "
            f"Install it: pip install {module_name.replace('_', '-')}"
        ) from exc

    cls = getattr(mod, class_name)
    kwargs = {key: value for key, value in cfg.items() if key != "provider"}
    # OpenRouter uses ChatOpenAI — provide default base_url if not set
    if provider == "openrouter" and "base_url" not in kwargs:
        kwargs["base_url"] = "https://openrouter.ai/api/v1"

    return cls(**kwargs)


# ------------------------------------------------------------------------------------------
# NorFab Service Tools
# ------------------------------------------------------------------------------------------


def _make_norfab_tools(client: object, timeout: int = 10) -> list:
    """
    Auto-discover NorFab services and generate one LangChain tool per task.

    Tasks with ``agent=False`` or ``agent.enabled=False`` are skipped.

    Args:
        client: NFPClient instance.
        timeout (int): Timeout in seconds for each discovery call.

    Returns:
        list[StructuredTool]: List of LangChain StructuredTool objects.
    """
    tools = {}

    # Discover available services from the broker
    svc_result = client.mmi("mmi.service.broker", "show_workers", timeout=timeout)
    if svc_result.get("status") != "200" or svc_result.get("errors"):
        log.warning(
            f"agent - NorFab service discovery failed: {svc_result.get('errors')}"
        )
        return []

    services = list({s["service"] for s in svc_result.get("results", [])})
    log.debug(f"agent - discovered services for tool generation: {services}")

    for service in services:
        tasks_result = client.run_job(
            service=service,
            task="list_tasks",
            workers="any",
            timeout=timeout,
        )
        if not tasks_result:
            continue
        for wres in tasks_result.values():
            for task in wres.get("result", []):
                if (
                    task.get("agent") is False
                    or task.get("agent", {}).get("enabled") is False
                ):
                    continue
                task_name = f"service_{service}__task_{task['name']}".replace("-", "_")
                description = (
                    task.get("agent", {}).get("description")
                    or task.get("description")
                    or f"NorFab {service}/{task_name}"
                )
                schema = copy.deepcopy(task.get("inputSchema", {}))
                schema.get("properties", {}).pop("job", None)
                schema["required"] = [
                    key for key in schema.get("required", []) if key != "job"
                ]
                tools[task_name] = {
                    "description": description,
                    "input_schema": schema,
                    "norfab": {"service": service, "task": task["name"]},
                }

    return make_agent_inline_tools(client, tools)


# ------------------------------------------------------------------------------------------
# Agent Inline Definition Tools
# ------------------------------------------------------------------------------------------


def make_runnable(client: object, tool: dict, tool_name: str) -> Callable:
    """Wrap a native task call for an agent tool.

    Args:
        client (object): NFPClient used to execute the task.
        tool (dict): Inline tool definition with a ``norfab`` task mapping.
        tool_name (str): Name used in logging and progress events.

    Returns:
        Callable: Function accepting model keyword arguments and returning task
            results. Fixed arguments override model-supplied values.
    """

    def run_norfab_task(**kwargs: object) -> dict:
        """
        Args:
            **kwargs (object): Task arguments supplied by the model.
        """
        log.debug(f"agent calling {tool_name} with kwargs: {kwargs}")

        fixed_kwargs = copy.deepcopy(tool["norfab"].get("kwargs", {}))

        # get service name
        service = tool["norfab"].get("service") or kwargs.pop("service", None)
        if not service:
            raise RuntimeError(f"No service name provided for '{tool_name}' tool call")

        # extract job data from LLM kwargs
        job_data = fixed_kwargs.pop("job_data", {})
        if tool["norfab"].get("job_data"):
            for key in tool["norfab"]["job_data"]:
                if key in kwargs:
                    job_data[key] = kwargs.pop(key)

        # merge arguments for NorFab task call
        all_kwargs = {**kwargs, **fixed_kwargs}
        if job_data:
            all_kwargs["job_data"] = job_data

        log.info(f"agent running '{service}' service, task '{tool['norfab']['task']}'")

        # run norfab task
        try:
            ret = client.run_job(
                service=service,
                task=tool["norfab"]["task"],
                kwargs=all_kwargs,
            )
        except Exception as exc:
            log.error(
                f"agent - tool call failed: service='{service}', task='{tool['norfab']['task']}', error='{exc}'",
                exc_info=True,
            )
            raise

        log.info(
            f"agent '{service}' service, task '{tool['norfab']['task']}' completed"
        )

        return ret

    return run_norfab_task


def make_agent_inline_tools(client: object, tools: dict) -> list[StructuredTool]:
    """Build named native tools from inline definitions.

    Args:
        client (object): NFPClient used to execute tasks.
        tools (dict): Tool names mapped to definitions.

    Returns:
        list: LangChain tools using the supplied descriptions and schemas.
    """
    ret = []

    for tool_name, tool in tools.items():
        ret.append(
            StructuredTool.from_function(
                name=tool_name,
                func=make_runnable(client, tool, tool_name),
                infer_schema=False,
                parse_docstring=False,
                description=tool["description"],
                args_schema={"type": "object", **tool.get("input_schema", {})},
            )
        )

    return ret


# ------------------------------------------------------------------------------------------
# MCP Tools
# ------------------------------------------------------------------------------------------


async def _make_mcp_tools_async(mcp_servers: list) -> list:
    """Load MCP server tools via langchain-mcp-adapters.

    Args:
        mcp_servers (list): List of MCP server configuration dicts.

    Returns:
        list: LangChain tools loaded from all configured MCP servers.
    """
    from langchain_mcp_adapters.client import MultiServerMCPClient

    servers: dict = {}
    for s in mcp_servers:
        name = s["name"]
        transport = s.get("transport", "stdio")
        if transport == "stdio":
            servers[name] = {
                "transport": "stdio",
                "command": s["command"],
                "args": s.get("args", []),
                "env": s.get("env"),
            }
        elif transport in ("sse", "streamable-http"):
            servers[name] = {"transport": transport, "url": s["url"]}
        else:
            log.warning(
                f"agent - unknown MCP transport '{transport}' for server '{name}', skipping"
            )

    if not servers:
        return []

    mcp_client = MultiServerMCPClient(servers)
    return await mcp_client.get_tools()


def _make_mcp_tools(mcp_servers: list) -> list:
    """Synchronous wrapper around the async MCP tool loader.

    Args:
        mcp_servers (list): List of MCP server configuration dicts.

    Returns:
        list: LangChain tools loaded from all configured MCP servers.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        # Already inside a running event loop (e.g. Jupyter) — delegate to a new thread
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _make_mcp_tools_async(mcp_servers))
            return future.result()

    return loop.run_until_complete(_make_mcp_tools_async(mcp_servers))


# ------------------------------------------------------------------------------------------
# RAG Retriever Tool
# ------------------------------------------------------------------------------------------

_CHUNK_SIZE = 800
_CHUNK_OVERLAP = 100


def _split_text(text: str) -> list[str]:
    """Split text into overlapping chunks of _CHUNK_SIZE characters.

    Args:
        text (str): Input text to split.

    Returns:
        list[str]: List of overlapping text chunks.
    """
    chunks = []
    step = _CHUNK_SIZE - _CHUNK_OVERLAP
    for start in range(0, len(text), step):
        chunk = text[start : start + _CHUNK_SIZE].strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def _make_rag_tool(rag_cfg: dict, base_dir: str) -> StructuredTool:
    """
    Build a LangChain retriever tool backed by fastembed embeddings and Qdrant.

    Sources (files or directories) are indexed on first use if provided.
    The Qdrant collection is persisted on disk under ``__norfab__/rag/<profile>/``.

    Args:
        rag_cfg (dict): RAG configuration dict from the agent profile.
        base_dir (str): NorFab inventory base directory.

    Returns:
        StructuredTool: LangChain tool that searches the Qdrant knowledge base.
    """
    from fastembed import TextEmbedding
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    embed_model = rag_cfg.get("embed_model", "sentence-transformers/all-MiniLM-L6-v2")
    collection = rag_cfg.get("collection", "norfab")
    profile_name = rag_cfg.get("_profile", "default")
    persist_dir = rag_cfg.get(
        "persist_dir",
        os.path.join(base_dir, "__norfab__", "rag", profile_name),
    ).replace("{profile}", profile_name)
    sources = rag_cfg.get("sources") or []
    top_k = rag_cfg.get("top_k", 4)

    embedder = TextEmbedding(model_name=embed_model)

    os.makedirs(persist_dir, exist_ok=True)
    qdrant = QdrantClient(path=persist_dir)

    # Determine vector size from a single test embedding
    _sample_vec = list(embedder.embed(["probe"]))[0]
    vector_size = len(_sample_vec)

    existing_cols = {c.name for c in qdrant.get_collections().collections}
    if collection not in existing_cols:
        qdrant.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

    # Index sources if provided
    if sources:
        chunks: list[tuple[str, str]] = []  # (source_path, text)
        for src in sources:
            if os.path.isdir(src):
                for root, _, files in os.walk(src):
                    for fname in files:
                        fpath = os.path.join(root, fname)
                        try:
                            with open(fpath, encoding="utf-8", errors="ignore") as fh:
                                text = fh.read()
                            chunks.extend((fpath, c) for c in _split_text(text))
                        except Exception as exc:  # noqa: BLE001
                            log.warning(
                                f"agent - could not read RAG source {fpath}: {exc}"
                            )
            elif os.path.isfile(src):
                try:
                    with open(src, encoding="utf-8", errors="ignore") as fh:
                        text = fh.read()
                    chunks.extend((src, c) for c in _split_text(text))
                except Exception as exc:  # noqa: BLE001
                    log.warning(f"agent - could not read RAG source {src}: {exc}")
            else:
                log.warning(f"agent - RAG source not found: {src}")

        if chunks:
            texts = [c[1] for c in chunks]
            vectors = [v.tolist() for v in embedder.embed(texts)]
            points = [
                PointStruct(
                    id=i,
                    vector=vectors[i],
                    payload={"text": chunks[i][1], "source": chunks[i][0]},
                )
                for i in range(len(chunks))
            ]
            qdrant.upsert(collection_name=collection, points=points)
            log.info(
                f"agent - indexed {len(chunks)} chunks into Qdrant collection '{collection}'"
            )

    def search_knowledge_base(query: str) -> str:
        """Search the NorFab knowledge base for information relevant to the query.

        Args:
            query (str): Natural language search query.

        Returns:
            str: Formatted search results from the Qdrant knowledge base.
        """
        service = "rag"
        task_name = "search_knowledge_base"
        log.info(f"agent - tool call started: service='{service}', task='{task_name}'")
        try:
            query_vec = list(embedder.embed([query]))[0].tolist()
            results = qdrant.query_points(
                collection_name=collection,
                query=query_vec,
                limit=top_k,
            )
            hit_count = len(results.points or [])
            log.info(
                f"agent - tool call completed: service='{service}', task='{task_name}', hits={hit_count}"
            )
            if not results.points:
                return "No relevant information found."
            return "\n\n---\n\n".join(
                f"[Source: {p.payload.get('source', 'unknown')}]\n{p.payload.get('text', '')}"
                for p in results.points
            )
        except Exception as exc:  # noqa: BLE001
            log.error(
                f"agent - tool call failed: service='{service}', task='{task_name}', error='{exc}'",
                exc_info=True,
            )
            return f"Error searching knowledge base: {exc}"

    return StructuredTool.from_function(
        func=search_knowledge_base,
        name="norfab_knowledge_base",
        description="Search NorFab documentation and knowledge base for relevant information.",
    )


# ------------------------------------------------------------------------------------------
# Filesystem Tools
# ------------------------------------------------------------------------------------------


def _make_filesystem_tools() -> list:
    """
    Build built-in filesystem tools: read, write, edit, and list-directory.

    All paths are resolved relative to the current working directory and access
    outside that directory is denied.

    Returns:
        list[StructuredTool]: Four LangChain StructuredTool objects.
    """

    base_dir = os.path.abspath(os.getcwd())

    def _safe_path(path: str) -> str:
        """Resolve *path* and verify it stays within the current working directory."""
        resolved = os.path.abspath(path)
        root = base_dir
        if not resolved.startswith(root + os.sep) and resolved != root:
            raise PermissionError(
                f"Access denied: '{path}' is outside the allowed base directory '{root}'"
            )
        return resolved

    def fs_read_file(path: str) -> str:
        """Read and return the text contents of a file.

        Args:
            path (str): Path to the file to read.

        Returns:
            str: File contents as text, or an error message.
        """
        service = "filesystem"
        task_name = "read_file"
        log.info(
            f"agent - tool call started: service='{service}', task='{task_name}', path='{path}'"
        )
        try:
            safe = _safe_path(path)
        except PermissionError as exc:
            log.error(
                f"agent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='{exc}'"
            )
            return f"Error: {exc}"
        if not os.path.isfile(safe):
            log.error(
                f"agent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='file not found'"
            )
            return f"Error: file not found: {path}"
        try:
            with open(safe, encoding="utf-8", errors="replace") as fh:
                ret = fh.read()
        except Exception as exc:
            log.error(
                f"agent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='{exc}'"
            )
            return f"Error reading '{path}': {exc}"

        log.info(
            f"agent - tool call completed: service='{service}', task='{task_name}', path='{path}'"
        )
        return ret

    def fs_write_file(path: str, content: str) -> str:
        """Create a new file or overwrite an existing file with the provided content.

        Missing parent directories are created automatically.

        Args:
            path (str): Destination file path.
            content (str): Text content to write.

        Returns:
            str: Success or error message.
        """
        service = "filesystem"
        task_name = "write_file"
        log.info(
            f"agent - tool call started: service='{service}', task='{task_name}', path='{path}'"
        )
        try:
            safe = _safe_path(path)
        except PermissionError as exc:
            log.error(
                f"agent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='{exc}'"
            )
            return f"Error: {exc}"
        try:
            parent = os.path.dirname(safe)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(safe, "w", encoding="utf-8") as fh:
                fh.write(content)
            ret = f"File written successfully: {path}"
        except Exception as exc:
            log.error(
                f"agent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='{exc}'"
            )
            return f"Error writing '{path}': {exc}"

        log.info(
            f"agent - tool call completed: service='{service}', task='{task_name}', path='{path}'"
        )
        return ret

    def fs_edit_file(path: str, old_text: str, new_text: str) -> str:
        """Edit an existing file by replacing the first occurrence of *old_text* with *new_text*.

        Use this for targeted in-place edits rather than rewriting the entire file.

        Args:
            path (str): Path to the file to edit.
            old_text (str): Exact text to find and replace.
            new_text (str): Replacement text.

        Returns:
            str: Success or error message.
        """
        service = "filesystem"
        task_name = "edit_file"
        log.info(
            f"agent - tool call started: service='{service}', task='{task_name}', path='{path}'"
        )
        try:
            safe = _safe_path(path)
        except PermissionError as exc:
            log.error(
                f"agent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='{exc}'"
            )
            return f"Error: {exc}"
        if not os.path.isfile(safe):
            log.error(
                f"agent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='file not found'"
            )
            return f"Error: file not found: {path}"
        try:
            with open(safe, encoding="utf-8", errors="replace") as fh:
                original = fh.read()
            if old_text not in original:
                log.error(
                    f"agent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='old_text not found'"
                )
                return f"Error: old_text not found in '{path}'"
            updated = original.replace(old_text, new_text, 1)
            with open(safe, "w", encoding="utf-8") as fh:
                fh.write(updated)
            ret = f"File edited successfully: {path}"
        except Exception as exc:
            log.error(
                f"agent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='{exc}'"
            )
            return f"Error editing '{path}': {exc}"

        log.info(
            f"agent - tool call completed: service='{service}', task='{task_name}', path='{path}'"
        )
        return ret

    def fs_list_dir(path: str = ".") -> str:
        """List files and sub-directories at the given path.

        Directories are shown with a trailing ``/``.  Entries are sorted
        alphabetically.

        Args:
            path (str): Directory path to list. Defaults to the current directory.

        Returns:
            str: Newline-separated list of directory entries, or an error message.
        """
        service = "filesystem"
        task_name = "list_dir"
        log.info(
            f"agent - tool call started: service='{service}', task='{task_name}', path='{path}'"
        )
        try:
            safe = _safe_path(path)
        except PermissionError as exc:
            log.error(
                f"agent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='{exc}'"
            )
            return f"Error: {exc}"
        if not os.path.isdir(safe):
            log.error(
                f"agent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='directory not found'"
            )
            return f"Error: directory not found: {path}"
        try:
            entries = sorted(os.listdir(safe))
            lines = []
            for entry in entries:
                suffix = "/" if os.path.isdir(os.path.join(safe, entry)) else ""
                lines.append(f"{entry}{suffix}")
            ret = "\n".join(lines) if lines else "(empty)"
        except Exception as exc:
            log.error(
                f"agent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='{exc}'"
            )
            return f"Error listing '{path}': {exc}"

        log.info(
            f"agent - tool call completed: service='{service}', task='{task_name}', path='{path}'"
        )
        return ret

    return [
        StructuredTool.from_function(
            func=fs_read_file,
            name="fs_read_file",
            description="Read and return the text contents of a file.",
        ),
        StructuredTool.from_function(
            func=fs_write_file,
            name="fs_write_file",
            description=(
                "Create a new file or overwrite an existing file with the provided content. "
                "Parent directories are created automatically."
            ),
        ),
        StructuredTool.from_function(
            func=fs_edit_file,
            name="fs_edit_file",
            description=(
                "Edit an existing file by replacing the first occurrence of old_text with "
                "new_text. Use for targeted in-place edits rather than full rewrites."
            ),
        ),
        StructuredTool.from_function(
            func=fs_list_dir,
            name="fs_list_dir",
            description="List files and sub-directories at the given path.",
        ),
    ]


# ------------------------------------------------------------------------------------------
# Default System Prompt
# ------------------------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are a Network Automation Fabric (NorFab) Agent — an expert AI assistant for
provisioning, configuring, testing, and documenting network infrastructure.

Your primary responsibilities:

1. NETWORK PROVISIONING
   Use nornir service tasks to push configuration changes to network devices:
   - `service_nornir__task_cfg` — deploy structured configuration.
   - `service_nornir__task_cli` — run show or exec commands on network devices.
   - `service_nornir__task_task` — execute Nornir task plugins.
   Always confirm the target scope (device, group, or all workers) before applying
   changes. Prefer dry-run or diff mode when available.

2. NETWORK TESTING & VALIDATION
   Use the nornir `test` task to verify network state after changes:
   - Run test suites to check interface status, routing, reachability, and protocols.
   - Report pass/fail results clearly and suggest remediation for failures.
   Treat testing as a mandatory post-change step unless the user explicitly skips it.

3. DEVICE INVENTORY & DATA RETRIEVAL
   Use the NetBox `get_devices` task to look up authoritative device information:
   - Resolve hostnames, management IPs, roles, sites, platforms, and tags.
   - Use NetBox data to scope automation targets and validate change requests.
   Never assume device details — query Netbox when its service is available.

GENERAL GUIDELINES
- Always choose the most specific tool available. 
- Prefer targeted, narrowly scoped calls over broad ones to minimise risk and execution time.
- Think step-by-step. Break complex requests into ordered sub-tasks.
- When device scope is ambiguous, ask the user to clarify before executing.
- Summarise what you did and what changed after every action.
- Surface errors immediately with the raw error text and a proposed fix.
- Never fabricate command output or device state — use tools to retrieve real data.
- Keep responses concise; show full output only when explicitly requested.
"""


# ------------------------------------------------------------------------------------------
# NFAgent
# ------------------------------------------------------------------------------------------


class NFAgent:
    """Shared model and native tool backend for client and worker agents.

    Builds the graph during construction. Conversation history is held in memory
    by default; each instance has its own default thread. Client profiles are
    resolved by ``NFPClient.get_agent``; workers supply parsed YAML definitions.
    Set ``memory: {enabled: true, backend: sqlite}`` to keep history on disk.
    Clients close their cached agents automatically; direct callers must close
    the agent when finished. ``thread_id`` identifies the active conversation.

    Args:
        client: NFPClient used to discover and execute NorFab tasks.
        config (dict): Agent definition with ``llm``, optional ``system_prompt``
            and ``tools``. Native task discovery defaults to enabled; filesystem,
            MCP and RAG tools require explicit configuration. Copied on entry.
        profile (str): Instance label used for profile-specific storage.
            Defaults to ``"default"``.

    Raises:
        ValueError: Tool names are duplicated or the LLM provider is unsupported.
        ImportError: A configured provider or optional feature is not installed.

    Example:
        agent = client.get_agent(profile="default")
        answer = agent.invoke("Check interfaces on r1")
        agent.invoke("Summarize the errors", thread_id="review")
    """

    def __init__(
        self,
        client: object,
        config: dict,
        profile: str = "default",
    ) -> None:
        self.client = client
        self.profile = profile
        self.tools = []
        self._agent = None
        self.thread_id = str(uuid.uuid4())
        self._memory_connection = None
        self._cfg = copy.deepcopy(config)
        try:
            self._build()
        except Exception:
            self.close()
            raise

    def _build(self) -> None:
        """Build the agent graph during construction."""
        cfg = self._cfg
        llm_cfg = cfg.get("llm", {})
        tools_cfg = cfg.get("tools", {})
        mcp_cfg = cfg.get("mcp", {})
        rag_cfg = cfg.get("rag", {})
        memory_cfg = cfg.get("memory", {})
        system_prompt = cfg.get("system_prompt", SYSTEM_PROMPT)

        # Auto-generate LangChain tools from discovered NorFab services
        if tools_cfg.pop("norfab_services", True):
            log.info(
                f"agent - discovering NorFab service tools for profile '{self.profile}'"
            )
            norfab_tools = _make_norfab_tools(self.client)
            self.tools.extend(norfab_tools)
            log.info(f"agent - discovered {len(norfab_tools)} NorFab service tools")

        # Add built-in filesystem tools
        fs_cfg = tools_cfg.pop("filesystem", False)
        if fs_cfg is True or (isinstance(fs_cfg, dict) and fs_cfg.get("enabled", True)):
            fs_tools = _make_filesystem_tools()
            self.tools.extend(fs_tools)
            log.info(f"agent - added {len(fs_tools)} built-in filesystem tools")

        if tools_cfg:
            log.info(f"agent - building tools from profile '{self.profile}'")
            self.tools.extend(make_agent_inline_tools(self.client, tools_cfg))

        # Load tools from external MCP servers
        if mcp_cfg.get("enabled") and mcp_cfg.get("servers"):
            log.info(f"agent - loading MCP tools for profile '{self.profile}'")
            mcp_tools = _make_mcp_tools(mcp_cfg["servers"])
            self.tools.extend(mcp_tools)
            log.info(f"agent - loaded {len(mcp_tools)} MCP tools")

        # Add RAG retriever tool
        if rag_cfg.get("enabled"):
            log.info(f"agent - setting up RAG retriever for profile '{self.profile}'")
            rag_cfg["_profile"] = self.profile
            rag_tool = _make_rag_tool(rag_cfg, self.client.inventory.base_dir)
            self.tools.append(rag_tool)
            log.info("agent - RAG retriever tool ready")

        names = [tool.name for tool in self.tools]
        if len(names) != len(set(names)):
            raise ValueError("duplicate agent tool names")

        llm = _make_llm(llm_cfg)

        # Conversation memory — always enable at least an in-memory checkpointer
        # so every agent instance supports continuous multi-turn chat by default.
        if memory_cfg.get("enabled") and memory_cfg.get("backend") == "sqlite":
            from langgraph.checkpoint.sqlite import SqliteSaver

            os.makedirs(self.client.base_dir, exist_ok=True)
            self._memory_connection = sqlite3.connect(
                os.path.join(self.client.base_dir, f"agent_{self.profile}.db"),
                check_same_thread=False,
            )
            self._checkpointer = SqliteSaver(self._memory_connection)
        else:
            self._checkpointer = MemorySaver()

        self._agent = create_agent(
            name=cfg.get("name", self.profile),
            model=llm,
            tools=self.tools,
            system_prompt=system_prompt,
            checkpointer=self._checkpointer,
        )

    def _run_config(self, thread_id: str | None) -> dict:
        """Return LangGraph run config dict using the given or instance thread ID.

        Args:
            thread_id (str | None): Thread ID override; uses instance thread if None.

        Returns:
            dict: LangGraph config dict with ``thread_id`` set.
        """
        return {"configurable": {"thread_id": thread_id or self.thread_id}}

    def close(self) -> None:
        """Close the owned conversation database. Repeated calls are harmless."""
        if self._memory_connection is not None:
            self._memory_connection.close()
            self._memory_connection = None

    def list_conversations(self, limit: int | None = 20) -> list[dict]:
        """List recent conversations for this agent's client and profile.

        Args:
            limit (int | None): Maximum conversations returned, or None for all.
                Defaults to 20.

        Returns:
            list[dict]: Thread ID, last checkpoint timestamp and first user message
                as a title, newest first. Empty conversations are omitted.
        """
        conversations = {}
        for checkpoint in self._checkpointer.list(None):
            config = checkpoint.config["configurable"]
            thread_id = config["thread_id"]
            if config.get("checkpoint_ns") or thread_id in conversations:
                continue
            messages = checkpoint.checkpoint["channel_values"].get("messages", [])
            if not messages:
                continue
            conversations[thread_id] = {
                "thread_id": thread_id,
                "updated_at": checkpoint.checkpoint["ts"],
                "title": next((m.text[:80] for m in messages if m.type == "human"), ""),
            }
        return sorted(
            conversations.values(), key=lambda row: row["updated_at"], reverse=True
        )[:limit]

    def resume(self, thread_id: str) -> None:
        """Select an existing conversation for subsequent invoke/stream calls.

        Args:
            thread_id (str): Conversation ID returned by ``list_conversations``.

        Raises:
            ValueError: The conversation has no saved messages in this profile.
        """
        if not thread_id or not self._agent.get_state(
            self._run_config(thread_id)
        ).values.get("messages"):
            raise ValueError(f"conversation '{thread_id}' not found")
        self.thread_id = thread_id

    def rename(self, thread_id: str) -> None:
        """Move the current conversation to a human-readable thread ID.

        Args:
            thread_id (str): New, nonempty conversation ID.

        Raises:
            ValueError: The ID is empty or already belongs to another thread.

        Notes:
            Preserves current conversation state, but not older checkpoints.
            Rename only while the conversation is idle.
        """
        thread_id = thread_id.strip()
        if not thread_id:
            raise ValueError("conversation name cannot be empty")
        if thread_id == self.thread_id:
            return
        config = self._run_config(thread_id)
        if self._checkpointer.get_tuple(config):
            raise ValueError(f"conversation '{thread_id}' already exists")
        state = self._agent.get_state(self._run_config(None))
        if state.values:
            self._agent.update_state(config, state.values, as_node="model")
            self._checkpointer.delete_thread(self.thread_id)
        self.thread_id = thread_id

    def reset(self) -> None:
        """
        Start a fresh conversation by rotating the instance thread ID.

        Subsequent calls to :meth:`invoke` and :meth:`stream` without an explicit
        thread ID begin a new conversation. Existing history remains available
        through :meth:`resume` or an explicit thread ID.
        """
        self.thread_id = str(uuid.uuid4())
        log.debug(f"agent - conversation reset, new thread_id: {self.thread_id}")

    def invoke(
        self,
        message: str,
        thread_id: str = None,
        verbose_result: bool = False,
        callbacks: list[BaseCallbackHandler] | None = None,
    ) -> str | dict:
        """
        Run the agent with a user message and return the final response.

        Args:
            message (str): User message or instructions for the agent.
            thread_id (str, optional): Conversation thread ID enabling multi-turn
                history. Omit to use the instance conversation.
            verbose_result (bool): Return the full graph payload instead of final
                message content. Defaults to false.
            callbacks (list[BaseCallbackHandler] | None): Optional progress
                listeners for this invocation only. Defaults to None.

        Returns:
            str | dict: Final response content, or full payload when verbose.
        """
        config = self._run_config(thread_id)
        config["callbacks"] = callbacks
        result = self._agent.invoke(
            {"messages": [{"role": "user", "content": message}]},
            config=config,
        )

        return result if verbose_result else result["messages"][-1].text

    def stream(self, message: str, thread_id: str = None) -> Iterator[str]:
        """
        Stream agent response tokens for a user message.

        Args:
            message (str): User message or instructions for the agent.
            thread_id (str, optional): Conversation thread ID for memory continuity.

        Yields:
            str: Text token chunks from the agent's response.
        """
        for chunk in self._agent.stream(
            {"messages": [{"role": "user", "content": message}]},
            config=self._run_config(thread_id),
            stream_mode="messages",
        ):
            if chunk and chunk[0].text:
                yield chunk[0].text

    def list_tools(self, name: str = "*") -> list:
        """List tools matching a name pattern.

        Args:
            name (str): Tool name glob pattern. Defaults to ``"*"``.

        Returns:
            list: Tool names and descriptions.
        """
        return [{t.name: t.description} for t in self.tools if fnmatch(t.name, name)]
