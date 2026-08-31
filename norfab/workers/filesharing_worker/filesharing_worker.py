import importlib.metadata
import logging
import os
import sys
import threading
from typing import Any

from norfab.core.worker import NFPWorker, Task
from norfab.models import Result

from .filesharing_models import (
    FileSharingInventory,
    GetInventoryInput,
    GetInventoryResult,
    GetRemotesInput,
    GetRemotesResult,
    GetStatusInput,
    GetStatusResult,
    GetVersionInput,
    GetVersionResult,
)
from .git_tasks import GitTasks
from .local_files_tasks import LocalFilesTasks

SERVICE = "filesharing"

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# FILE SHARING WORKER
# --------------------------------------------------------------------------


class FileSharingWorker(NFPWorker, GitTasks, LocalFilesTasks):
    """File Sharing worker providing Git-based remote synchronization and file access.

    Supports managing multiple configured Git remotes with automatic periodic
    synchronization. Provides tasks for listing, fetching, and walking published
    remote content via a safe filesystem interface.
    """

    def __init__(
        self,
        inventory: Any,
        broker: str,
        worker_name: str,
        exit_event: Any = None,
        init_done_event: Any = None,
        log_level: str = "WARNING",
    ) -> None:
        super().__init__(inventory, broker, SERVICE, worker_name, exit_event, log_level)
        self.init_done_event = init_done_event

        # get inventory from broker
        inventory_data = self.load_inventory()
        validated_inventory = FileSharingInventory.model_validate(inventory_data)

        self.runtime_dir = self.base_dir
        self.filesharing_inventory = validated_inventory.model_dump()
        self.base_dir = os.path.abspath(validated_inventory.base_dir)

        self.setup_remotes(validated_inventory)

        self.init_done_event.set()
        log.debug(f"{self.name} - Started")

    def setup_remotes(self, validated_inventory: FileSharingInventory) -> None:
        """Set up all configured remotes and start synchronization thread.

        Initializes remote locks, validates each remote's type, and starts the
        automatic synchronization thread if any remotes have auto_sync enabled.

        Args:
            validated_inventory: Validated FileSharingInventory instance.

        Raises:
            ValueError: If any remote has an unsupported type.
        """
        self.remotes = {}
        self.remote_sync_stop = threading.Event()
        self.remote_sync_thread = None
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(os.path.join(self.runtime_dir, "remotes"), exist_ok=True)

        # Initialize each configured remote based on its type
        for remote in validated_inventory.remotes:
            if remote.type == "git":
                result = self.create_remote_git(None, **remote.model_dump())
                if result.failed:
                    log.error(f"{self.name} - Failed to create remote '{remote.name}'")
            else:
                raise ValueError(
                    f"Remote type '{remote.type}' is not supported. "
                    f"Supported types: git"
                )

        if self.remote_sync_thread is None:
            self.remote_sync_thread = self.start_git_sync()

    def worker_exit(self) -> None:
        self.remote_sync_stop.set()
        if self.remote_sync_thread is not None:
            self.remote_sync_thread.join()

    @Task(
        input=GetVersionInput,
        output=GetVersionResult,
        fastapi={"methods": ["GET"]},
        agent={"enabled": False},
        mcp={
            "annotations": {
                "title": "Get Version",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            }
        },
    )
    def get_version(self) -> Result:
        """Return runtime versions reported by the File Sharing worker.

        Returns:
            A result mapping runtime component names to version strings. Python
            and platform information are always included.
        """
        libs = {
            "python": sys.version.split(" ")[0],
            "platform": sys.platform,
            "gitpython": "",
        }
        # get version of packages installed
        for pkg in libs.keys():
            try:
                libs[pkg] = importlib.metadata.version(pkg)
            except importlib.metadata.PackageNotFoundError:
                pass

        return Result(result=libs)

    @Task(
        input=GetInventoryInput,
        output=GetInventoryResult,
        fastapi={"methods": ["GET"]},
        agent={"enabled": False},
        mcp={
            "annotations": {
                "title": "Get Inventory",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            }
        },
    )
    def get_inventory(self) -> Result:
        """Return the validated File Sharing worker inventory.

        Remote definitions are returned in their configured order. Every
        non-empty password or access token is replaced with ``***`` before the
        inventory leaves the worker.

        Returns:
            A result containing the validated inventory with credentials
            redacted.
        """
        inventory = self.filesharing_inventory.copy()
        inventory["remotes"] = []
        for configured_remote in self.filesharing_inventory.get("remotes", []):
            remote = configured_remote.copy()
            if remote.get("password") is not None:
                remote["password"] = "***"
            inventory["remotes"].append(remote)
        return Result(result=inventory)

    @Task(
        input=GetRemotesInput,
        output=GetRemotesResult,
        fastapi={"methods": ["GET"]},
        agent={"enabled": False},
        mcp={
            "annotations": {
                "title": "Get File Sharing Remotes",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            }
        },
    )
    def get_remotes(self, name: str | None = None) -> Result:
        """Return all runtime remotes or one remote selected by name.

        Args:
            name: Optional remote name used to filter the result.

        Returns:
            A result containing remote inventory dictionaries. Passwords and
            access tokens are replaced with ``***``; public remotes retain a
            ``None`` password.
        """
        remotes = []
        for configured_remote in self.remotes.values():
            if name is not None and configured_remote["name"] != name:
                continue
            remote = configured_remote.copy()
            remote.pop("lock")
            remote.pop("last_sync_timer")
            remote.pop("repository")
            if remote.get("password") is not None:
                remote["password"] = "***"
            remotes.append(remote)
        return Result(result=remotes)

    @Task(
        input=GetStatusInput,
        output=GetStatusResult,
        fastapi={"methods": ["GET"]},
        agent={"enabled": False},
        mcp={
            "annotations": {
                "title": "Get Status",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            }
        },
    )
    def get_status(self) -> Result:
        """Return the File Sharing worker health status.

        Returns:
            A result containing ``OK`` while the worker can process tasks.
        """
        return Result(result="OK")
