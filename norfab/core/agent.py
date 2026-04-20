import asyncio
import concurrent.futures
import copy
import importlib
import logging
import os
import uuid
from fnmatch import fnmatch
from typing import Any, Callable, Iterator, List

import yaml
from datamodel_code_generator import Formatter, GenerateConfig, generate_dynamic_models
from fastembed import TextEmbedding
from langchain.agents import create_agent
from langchain.tools import tool as langchain_tool
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from norfab.core.inventory import merge_recursively

log = logging.getLogger(__name__)

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


def _make_llm(cfg: dict):
    """Instantiate a LangChain chat model from an agent profile LLM config dict.

    Args:
        cfg (dict): LLM configuration dict from the agent profile.

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
    kwargs: dict = {}
    if cfg.get("model"):
        kwargs["model"] = cfg["model"]
    if cfg.get("api_key"):
        kwargs["api_key"] = cfg["api_key"]
    if cfg.get("temperature") is not None:
        kwargs["temperature"] = cfg["temperature"]
    if cfg.get("base_url"):
        kwargs["base_url"] = cfg["base_url"]
    # OpenRouter uses ChatOpenAI — provide default base_url if not set
    if provider == "openrouter" and "base_url" not in kwargs:
        kwargs["base_url"] = "https://openrouter.ai/api/v1"

    return cls(**kwargs)


# ------------------------------------------------------------------------------------------
# NorFab Service Tools
# ------------------------------------------------------------------------------------------


def _make_service_tool(client, service: str, task_name: str, description: str):
    """Return a single LangChain StructuredTool wrapping one NorFab task.

    Args:
        client: NFPClient instance used to dispatch jobs.
        service (str): NorFab service name.
        task_name (str): Task name within the service.
        description (str): Tool description shown to the LLM.

    Returns:
        StructuredTool: Configured LangChain tool for the given task.
    """

    def run(**kwargs: Any) -> Any:
        workers = kwargs.pop("workers", "all")
        log.info(
            f"NFAgent - tool call started: service='{service}', task='{task_name}', workers='{workers}'"
        )
        try:
            ret = client.run_job(
                service=service, task=task_name, kwargs=kwargs, workers=workers
            )
        except Exception as exc:
            log.error(
                f"NFAgent - tool call failed: service='{service}', task='{task_name}', error='{exc}'",
                exc_info=True,
            )
            raise

        log.info(
            f"NFAgent - tool call completed: service='{service}', task='{task_name}'"
        )

        return ret

    tool_name = f"service_{service}__task_{task_name}".replace("-", "_")
    return StructuredTool.from_function(
        func=run,
        name=tool_name,
        description=description or f"Run NorFab task {service}/{task_name}",
    )


def _make_norfab_tools(client, timeout: int = 10) -> list:
    """
    Auto-discover NorFab services and generate one LangChain tool per task.

    Uses the same MMI discovery pattern as the FastMCP worker.  Tasks that
    set ``mcp: false`` in their ``@Task`` decorator are skipped.

    Args:
        client: NFPClient instance.
        timeout (int): Timeout in seconds for each discovery call.

    Returns:
        list[StructuredTool]: List of LangChain StructuredTool objects.
    """
    tools = []

    # Discover available services from the broker
    svc_result = client.mmi("mmi.service.broker", "show_workers", timeout=timeout)
    if svc_result.get("status") != "200" or svc_result.get("errors"):
        log.warning(
            f"NFAgent - NorFab service discovery failed: {svc_result.get('errors')}"
        )
        return tools

    services = list({s["service"] for s in svc_result.get("results", [])})
    log.debug(f"NFAgent - discovered services for tool generation: {services}")

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
                if task.get("agent", {}).get("enabled") is False:
                    continue
                task_name = f"service_{service}__task_{task['name']}".replace("-", "_")
                description = (
                    task.get("agent", {}).get("description")
                    or task.get("description")
                    or f"NorFab {service}/{task_name}"
                )
                task["norfab"] = {"service": service, "task": task["name"]}
                if isinstance(task.get("input_schema"), dict):
                    task["input_schema"] = make_pydantic_model(
                        task["input_schema"], task_name
                    )
                tools.append(
                    langchain_tool(
                        task_name,
                        make_runnable(client, task, task_name),
                        infer_schema=False,
                        parse_docstring=False,
                        description=description,
                        args_schema=task.get("input_schema", {}),
                    )
                )

                # task_name = task["name"]
                # description = task.get("description") or f"NorFab {service}/{task_name}"
                # try:
                #     tools.append(
                #         _make_service_tool(client, service, task_name, description)
                #     )
                # except Exception as exc:
                #     log.warning(
                #         f"NFAgent - could not create tool for {service}/{task_name}: {exc}"
                #     )

    return tools


# ------------------------------------------------------------------------------------------
# Agent Inline Definition Tools
# ------------------------------------------------------------------------------------------


def make_runnable(client: object, tool: dict, tool_name: str) -> Callable:
    def run_norfab_task(kwargs: dict) -> dict:
        """
        Args:
            kwargs (dict): arguments passed on by LLM
        """
        log.debug(f"'{tool_name}' agent calling tool with kwargs: {kwargs}")

        # get service name
        tool_defined_service = tool["norfab"].get("service")
        llm_requested_service = kwargs.pop("service", None)
        service = tool_defined_service or llm_requested_service
        if not service:
            raise RuntimeError(f"No service name provided for '{tool_name}' tool call")

        # extract job data from LLM kwargs
        job_data = tool["norfab"].get("kwargs", {}).pop("job_data", {})
        if tool["norfab"].get("job_data"):
            for key in tool["norfab"]["job_data"]:
                if key in kwargs:
                    job_data[key] = kwargs.pop(key)

        # merge arguments for NorFab task call
        all_kwargs = {**kwargs, **tool["norfab"].get("kwargs", {})}
        if job_data:
            all_kwargs["job_data"] = job_data

        log.info(f"Agent running '{service}' service, task '{tool['norfab']['task']}'")

        # run norfab task
        try:
            ret = client.run_job(
                service=service,
                task=tool["norfab"]["task"],
                kwargs=all_kwargs,
            )
        except Exception as exc:
            log.error(
                f"NFAgent - tool call failed: service='{service}', task='{tool['norfab']['task']}', error='{exc}'",
                exc_info=True,
            )
            raise

        log.info(
            f"Agent '{service}' service, task '{tool['norfab']['task']}' completed"
        )

        return ret

    return RunnableLambda(run_norfab_task).with_types(
        input_type=tool.get("input_schema", {})
    )


def make_pydantic_model(schema, model_name):
    schema.setdefault("type", "object")
    config = GenerateConfig(formatters=[Formatter.RUFF_FORMAT, Formatter.RUFF_CHECK])
    models = generate_dynamic_models(schema, config=config)

    return models["Model"]


def make_agent_inline_tools(client: object, tools: dict) -> List[langchain_tool]:
    ret = []

    for tool_name, tool in tools.items():
        if isinstance(tool.get("input_schema"), dict):
            tool["input_schema"] = make_pydantic_model(tool["input_schema"], tool_name)
        ret.append(
            langchain_tool(
                tool_name,
                make_runnable(client, tool, tool_name),
                infer_schema=False,
                parse_docstring=False,
                description=tool["description"],
                args_schema=tool.get("input_schema", {}),
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
                f"NFAgent - unknown MCP transport '{transport}' for server '{name}', skipping"
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


def _make_rag_tool(rag_cfg: dict, base_dir: str):
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
                                f"NFAgent - could not read RAG source {fpath}: {exc}"
                            )
            elif os.path.isfile(src):
                try:
                    with open(src, encoding="utf-8", errors="ignore") as fh:
                        text = fh.read()
                    chunks.extend((src, c) for c in _split_text(text))
                except Exception as exc:  # noqa: BLE001
                    log.warning(f"NFAgent - could not read RAG source {src}: {exc}")
            else:
                log.warning(f"NFAgent - RAG source not found: {src}")

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
                f"NFAgent - indexed {len(chunks)} chunks into Qdrant collection '{collection}'"
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
        log.info(
            f"NFAgent - tool call started: service='{service}', task='{task_name}'"
        )
        try:
            query_vec = list(embedder.embed([query]))[0].tolist()
            results = qdrant.query_points(
                collection_name=collection,
                query=query_vec,
                limit=top_k,
            )
            hit_count = len(results.points or [])
            log.info(
                f"NFAgent - tool call completed: service='{service}', task='{task_name}', hits={hit_count}"
            )
            if not results.points:
                return "No relevant information found."
            return "\n\n---\n\n".join(
                f"[Source: {p.payload.get('source', 'unknown')}]\n{p.payload.get('text', '')}"
                for p in results.points
            )
        except Exception as exc:  # noqa: BLE001
            log.error(
                f"NFAgent - tool call failed: service='{service}', task='{task_name}', error='{exc}'",
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
            f"NFAgent - tool call started: service='{service}', task='{task_name}', path='{path}'"
        )
        try:
            safe = _safe_path(path)
        except PermissionError as exc:
            log.error(
                f"NFAgent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='{exc}'"
            )
            return f"Error: {exc}"
        if not os.path.isfile(safe):
            log.error(
                f"NFAgent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='file not found'"
            )
            return f"Error: file not found: {path}"
        try:
            with open(safe, encoding="utf-8", errors="replace") as fh:
                ret = fh.read()
        except Exception as exc:
            log.error(
                f"NFAgent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='{exc}'"
            )
            return f"Error reading '{path}': {exc}"

        log.info(
            f"NFAgent - tool call completed: service='{service}', task='{task_name}', path='{path}'"
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
            f"NFAgent - tool call started: service='{service}', task='{task_name}', path='{path}'"
        )
        try:
            safe = _safe_path(path)
        except PermissionError as exc:
            log.error(
                f"NFAgent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='{exc}'"
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
                f"NFAgent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='{exc}'"
            )
            return f"Error writing '{path}': {exc}"

        log.info(
            f"NFAgent - tool call completed: service='{service}', task='{task_name}', path='{path}'"
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
            f"NFAgent - tool call started: service='{service}', task='{task_name}', path='{path}'"
        )
        try:
            safe = _safe_path(path)
        except PermissionError as exc:
            log.error(
                f"NFAgent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='{exc}'"
            )
            return f"Error: {exc}"
        if not os.path.isfile(safe):
            log.error(
                f"NFAgent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='file not found'"
            )
            return f"Error: file not found: {path}"
        try:
            with open(safe, encoding="utf-8", errors="replace") as fh:
                original = fh.read()
            if old_text not in original:
                log.error(
                    f"NFAgent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='old_text not found'"
                )
                return f"Error: old_text not found in '{path}'"
            updated = original.replace(old_text, new_text, 1)
            with open(safe, "w", encoding="utf-8") as fh:
                fh.write(updated)
            ret = f"File edited successfully: {path}"
        except Exception as exc:
            log.error(
                f"NFAgent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='{exc}'"
            )
            return f"Error editing '{path}': {exc}"

        log.info(
            f"NFAgent - tool call completed: service='{service}', task='{task_name}', path='{path}'"
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
            f"NFAgent - tool call started: service='{service}', task='{task_name}', path='{path}'"
        )
        try:
            safe = _safe_path(path)
        except PermissionError as exc:
            log.error(
                f"NFAgent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='{exc}'"
            )
            return f"Error: {exc}"
        if not os.path.isdir(safe):
            log.error(
                f"NFAgent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='directory not found'"
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
                f"NFAgent - tool call failed: service='{service}', task='{task_name}', path='{path}', error='{exc}'"
            )
            return f"Error listing '{path}': {exc}"

        log.info(
            f"NFAgent - tool call completed: service='{service}', task='{task_name}', path='{path}'"
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
# AGENT CONFIG LOADING FUNCTIONS
# ------------------------------------------------------------------------------------------


def load_agent_cfg_from_yaml_file(filename: str) -> dict:
    if os.path.isfile(filename):
        try:
            with open(filename, encoding="utf-8") as fh:
                return yaml.safe_load(fh.read())
        except Exception:
            log.error(
                f"NFAgent - failed to load configuration from YAML file: {filename}",
                exc_info=True,
            )
    return {}


# ------------------------------------------------------------------------------------------
# Default System Prompt
# ------------------------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are a Network Automation Fabric (NorFab) Agent — an expert AI assistant for
provisioning, configuring, testing, and documenting network infrastructure.

Your primary responsibilities:

1. NETWORK PROVISIONING
   Use nornir service tasks to push configuration changes to network devices:
   - `nornir_cfg` — deploy structured configuration (Jinja2 templates or raw config).
   - `nornir_cli` — run show or exec commands on one or many devices.
   - `nornir_task` — execute arbitrary Nornir task plugins for advanced automation.
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
   Never assume device details — always query NetBox when Netbox service is available.   

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
    """
    Agentic AI companion built into the NorFab client.

    Wraps a LangGraph ReAct agent that can call NorFab services as tools,
    connect to external MCP servers, and optionally use a RAG knowledge base.

    The agent graph is built lazily on the first call to :meth:`invoke` or
    :meth:`stream` so there is zero overhead when the agent is not used.

    Activated via ``NFPClient.get_agent(profile="default")``. Install dependencies::

        pip install norfab[clientagent]

    Supported LLM providers:
        openai, anthropic, ollama, groq, mistral, openrouter, google, bedrock

    OpenRouter uses ``ChatOpenAI`` with a custom ``base_url`` — no extra package
    needed beyond ``langchain-openai``.

    Sample ``inventory.yaml`` configuration:

        client:
          agent_profiles:
            default:
              llm:
                provider: openrouter
                model: anthropic/claude-3.5-sonnet
                api_key: "${OPENROUTER_API_KEY}"
                temperature: 0.0
              tools:
                norfab_services: true
                filesystem: true
              mcp:
                enabled: false
                servers:
                  - name: fastmcp
                    transport: streamable-http
                    url: http://localhost:8001/mcp/
                  - name: filesystem
                    transport: stdio
                    command: npx
                    args: ["@modelcontextprotocol/server-filesystem", "/tmp"]
              rag:
                enabled: false
                embed_model: sentence-transformers/all-MiniLM-L6-v2
                collection: norfab
                sources: []
                top_k: 4
              memory:
                enabled: false
                backend: buffer   # buffer | sqlite
              system_prompt: |
                You are a network automation assistant with access to NorFab services.

    Args:
        client: :class:`~norfab.core.client.NFPClient` instance.
        profile (str): Agent profile name from the inventory. Defaults to ``"default"``.

    Example:

        agent = client.get_agent(profile="default")

        # single-turn
        answer = agent.invoke("Show me all interfaces with errors on R1")

        # streaming tokens
        for token in agent.stream("Summarise nornir service tasks"):
            print(token, end="", flush=True)

        # multi-turn conversation (requires memory.enabled: true in profile)
        agent.invoke("List all nornir workers", thread_id="session-1")
        agent.invoke("Now run cli on all of them", thread_id="session-1")
    """

    def __init__(self, client: object, profile: str = "default") -> None:
        self.client = client
        self.profile = profile
        self.tools = []
        self._agent = None
        self._thread_id = str(
            uuid.uuid4()
        )  # unique thread per instance for continuous chat
        client_cfg = getattr(client.inventory, "client", {}) or {}
        self.profiles = client_cfg.get("agent_profiles", {})
        default_cfg = self.profiles.get("default", {})
        if profile not in self.profiles:
            raise ValueError(
                f"Agent profile '{profile}' not found in inventory. "
                f"Define it under client->agent_profiles->{profile} in inventory.yaml"
            )
        cfg = self.profiles[profile]
        if "from_yaml_file" in cfg:
            cfg = load_agent_cfg_from_yaml_file(cfg.pop("from_yaml_file"))

        if profile != "default" and default_cfg:
            self._cfg = copy.deepcopy(default_cfg)
            merge_recursively(self._cfg, cfg)
        else:
            self._cfg = cfg

        self._build()

    def _build(self) -> None:
        """Build the LangGraph ReAct agent graph (runs once on first use)."""
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
                f"NFAgent - discovering NorFab service tools for profile '{self.profile}'"
            )
            norfab_tools = _make_norfab_tools(self.client)
            self.tools.extend(norfab_tools)
            log.info(f"NFAgent - discovered {len(norfab_tools)} NorFab service tools")

        # Add built-in filesystem tools
        fs_cfg = tools_cfg.pop("filesystem", True)
        if fs_cfg is True or (isinstance(fs_cfg, dict) and fs_cfg.get("enabled", True)):
            fs_tools = _make_filesystem_tools()
            self.tools.extend(fs_tools)
            log.info(f"NFAgent - added {len(fs_tools)} built-in filesystem tools")

        if tools_cfg:
            log.info(f"NFAgent - building tools from profile '{self.profile}'")
            self.tools.extend(make_agent_inline_tools(self.client, tools_cfg))

        # Load tools from external MCP servers
        if mcp_cfg.get("enabled") and mcp_cfg.get("servers"):
            log.info(f"NFAgent - loading MCP tools for profile '{self.profile}'")
            mcp_tools = _make_mcp_tools(mcp_cfg["servers"])
            self.tools.extend(mcp_tools)
            log.info(f"NFAgent - loaded {len(mcp_tools)} MCP tools")

        # Add RAG retriever tool
        if rag_cfg.get("enabled"):
            log.info(f"NFAgent - setting up RAG retriever for profile '{self.profile}'")
            rag_cfg["_profile"] = self.profile
            rag_tool = _make_rag_tool(rag_cfg, self.client.inventory.base_dir)
            self.tools.append(rag_tool)
            log.info("NFAgent - RAG retriever tool ready")

        llm = _make_llm(llm_cfg)

        # Conversation memory — always enable at least an in-memory checkpointer
        # so every agent instance supports continuous multi-turn chat by default.
        if memory_cfg.get("enabled") and memory_cfg.get("backend") == "sqlite":
            db_path = os.path.join(
                self.client.inventory.base_dir,
                "__norfab__",
                "files",
                "client",
                self.client.name,
                f"agent_{self.profile}.db",
            )
            checkpointer = SqliteSaver.from_conn_string(db_path)
        else:
            checkpointer = MemorySaver()

        self._agent = create_agent(
            model=llm,
            tools=self.tools,
            system_prompt=system_prompt,
            checkpointer=checkpointer,
        )

    def _run_config(self, thread_id: str | None) -> dict:
        """Return LangGraph run config dict using the given or instance thread ID.

        Args:
            thread_id (str | None): Thread ID override; uses instance thread if None.

        Returns:
            dict: LangGraph config dict with ``thread_id`` set.
        """
        return {"configurable": {"thread_id": thread_id or self._thread_id}}

    def reset(self) -> None:
        """
        Start a fresh conversation by rotating the instance thread ID.

        All subsequent calls to :meth:`invoke` and :meth:`stream` will begin
        a new conversation with no memory of previous exchanges.
        """
        self._thread_id = str(uuid.uuid4())
        log.debug(f"NFAgent - conversation reset, new thread_id: {self._thread_id}")

    def invoke(self, message: str, thread_id: str = None) -> str:
        """
        Run the agent with a user message and return the final response.

        Args:
            message (str): User message or instructions for the agent.
            thread_id (str, optional): Conversation thread ID enabling multi-turn
                memory when ``memory.enabled`` is ``true`` in the profile config.

        Returns:
            str: Agent's final response text.
        """
        result = self._agent.invoke(
            {"messages": [{"role": "user", "content": message}]},
            config=self._run_config(thread_id),
        )

        return result["messages"][-1].content

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
            if chunk and hasattr(chunk[0], "content") and chunk[0].content:
                yield chunk[0].content

    def list_tools(self, name: str = "*") -> list:
        return [{t.name: t.description} for t in self.tools if fnmatch(t.name, name)]
