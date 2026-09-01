import base64
import logging
import os
import shutil
import threading
import time
from datetime import datetime, timezone

from git import Repo

from norfab.core.worker import Job, Task
from norfab.models import Result

from .filesharing_models import (
    CreateRemoteGitInput,
    CreateRemoteGitResult,
    DeleteRemoteGitResult,
    GitCloneResult,
    RemoteNameInput,
    ResolveGitUrlInput,
    ResolveGitUrlResult,
)

log = logging.getLogger(__name__)


class GitTasks:
    @staticmethod
    def _git_fetch_environment(remote: dict) -> dict[str, str]:
        """Build an isolated, non-interactive environment for a Git fetch."""
        environment = {
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "0",
            "GCM_GUI_PROMPT": "0",
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "credential.helper",
            "GIT_CONFIG_VALUE_0": "",
            "GIT_CONFIG_KEY_1": "credential.interactive",
            "GIT_CONFIG_VALUE_1": "false",
        }
        if remote["username"] is not None:
            credentials = base64.b64encode(
                f"{remote['username']}:{remote['password']}".encode()
            ).decode()
            environment.update(
                {
                    "GIT_CONFIG_COUNT": "3",
                    "GIT_CONFIG_KEY_2": "http.extraHeader",
                    "GIT_CONFIG_VALUE_2": f"Authorization: Basic {credentials}",
                }
            )
        return environment

    @Task(
        input=CreateRemoteGitInput,
        output=CreateRemoteGitResult,
        fastapi={"methods": ["POST"]},
        agent={"enabled": False},
        mcp={
            "annotations": {
                "title": "Create Git Remote",
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            }
        },
    )
    def create_remote_git(
        self,
        job: Job,
        name: str,
        url: str,
        type: str,
        mount: str | None = None,
        description: str = "",
        branch: str | None = None,
        username: str | None = None,
        password: str | None = None,
        auto_sync: bool = False,
        sync_interval: int = 30,
    ) -> Result:
        """Initialize the private local repository for a configured Git remote.

        The task creates ``<runtime>/remotes/<name>/repository``, initializes it
        with GitPython and configures a credential-free ``origin`` URL. It does
        not contact the remote server, fetch commits, or make files available.

        Args:
            job: Active worker job. Internal startup calls pass ``None`` and do
                not wait when the remote lock is held.
            name: Unique runtime name used by clone and delete tasks.
            url: Git repository URL.
            type: Remote driver type. This task accepts ``git``.
            mount: Relative File Sharing publication path. Defaults to name.
            description: Optional description shown by remote listing tasks.
            branch: Git branch to fetch.
            username: Optional HTTPS username.
            password: Optional HTTPS password or access token.
            auto_sync: Whether the worker periodically synchronizes the remote.
            sync_interval: Seconds between automatic synchronization attempts.

        Returns:
            A result containing the remote name and ``unsynchronized`` status.
        """
        msg = f"{self.name} - initializing Git remote '{name}'"
        log.info(msg)
        if job is not None:
            job.event(msg)

        mount = (mount or name).replace("\\", "/")
        remote = {
            "name": name,
            "url": url,
            "type": type,
            "mount": f"nf://{mount}",
            "description": description,
            "branch": branch,
            "username": username,
            "password": password,
            "auto_sync": auto_sync,
            "sync_interval": max(5, min(sync_interval, 86_400)),
            "last_sync_attempt": None,
            "last_sync_timer": None,
            "status": "unsynchronized",
            "repository": os.path.join(self.runtime_dir, "remotes", name, "repository"),
            "lock": threading.Lock(),
        }

        # Preserve synchronization state and the lock when inventory reloads a
        # remote that is already registered.
        existing_remote = self.remotes.get(name)
        if existing_remote is not None:
            remote["last_sync_attempt"] = existing_remote["last_sync_attempt"]
            remote["last_sync_timer"] = existing_remote["last_sync_timer"]
            remote["status"] = existing_remote["status"]
            remote["lock"] = existing_remote["lock"]
        if remote["type"] != "git":
            msg = f"{self.name} - remote '{name}' is not a git remote"
            log.warning(msg)
            if job is not None:
                job.event(msg, severity="ERROR")
            return Result(failed=True, errors=[f"Remote '{name}' is not a git remote"])

        # A mount cannot contain or be contained by another remote mount.
        mount_path = self._safe_path(remote["mount"])
        for existing_name, existing in self.remotes.items():
            if existing_name == name:
                continue
            existing_path = self._safe_path(existing["mount"])
            if os.path.commonpath([mount_path, existing_path]) in {
                mount_path,
                existing_path,
            }:
                msg = (
                    f"{self.name} - remote mount '{remote['mount']}' collides with "
                    f"remote '{existing_name}'"
                )
                log.error(msg)
                if job is not None:
                    job.event(msg, severity="ERROR")
                return Result(
                    failed=True,
                    errors=[
                        f"Remote mount '{remote['mount']}' collides with another remote"
                    ],
                )

        lock = remote["lock"]
        if job is None:
            acquired = lock.acquire(blocking=False)
        else:
            acquired = lock.acquire(
                timeout=job.timeout if job.timeout is not None else -1
            )
        if not acquired:
            msg = f"{self.name} - remote '{name}' is busy"
            log.warning(msg)
            if job is not None:
                job.event(msg, severity="WARNING")
            return Result(failed=True, errors=[f"Remote '{name}' is busy"])

        try:
            # The private repository is retained between syncs; only its
            # working tree is later made available in the File Sharing namespace.
            os.makedirs(remote["repository"], exist_ok=True)
            with Repo.init(remote["repository"]) as repository:
                if "origin" in repository.remotes:
                    repository.remotes.origin.set_url(remote["url"])
                else:
                    repository.create_remote("origin", remote["url"])
            self.remotes[name] = remote
        finally:
            lock.release()

        if remote["auto_sync"] and self.remote_sync_thread is None:
            self.remote_sync_thread = self.start_git_sync()
        msg = f"{self.name} - initialized Git remote '{name}' at {remote['mount']}"
        log.info(msg)
        if job is not None:
            job.event(msg)
        return Result(result={"name": remote["name"], "status": remote["status"]})

    @Task(
        input=RemoteNameInput,
        output=DeleteRemoteGitResult,
        fastapi={"methods": ["DELETE"]},
        agent={"enabled": False},
        mcp={
            "annotations": {
                "title": "Delete Git Remote",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": True,
                "openWorldHint": False,
            }
        },
    )
    def delete_remote_git(self, job: Job, name: str) -> Result:
        """Delete all worker-managed local data for a configured Git remote.

        The runtime definition, private repository, shared
        ``nf://<mount>/`` snapshot, and staging data are removed.

        Args:
            job: Active worker job. Internal calls may pass ``None`` to avoid
                waiting when the remote lock is held.
            name: Name of a ``type: git`` remote defined in File Sharing
                inventory.

        Returns:
            A result containing ``True`` after the local data is removed.
        """
        msg = f"{self.name} - deleting Git remote '{name}'"
        log.info(msg)
        if job is not None:
            job.event(msg)

        if name not in self.remotes:
            msg = f"{self.name} - remote '{name}' is not configured"
            log.warning(msg)
            if job is not None:
                job.event(msg, severity="ERROR")
            return Result(failed=True, errors=[f"Remote '{name}' is not configured"])
        remote = self.remotes[name]
        if remote["type"] != "git":
            msg = f"{self.name} - remote '{name}' is not a git remote"
            log.warning(msg)
            if job is not None:
                job.event(msg, severity="ERROR")
            return Result(failed=True, errors=[f"Remote '{name}' is not a git remote"])

        lock = remote["lock"]
        if job is None:
            acquired = lock.acquire(blocking=False)
        else:
            acquired = lock.acquire(
                timeout=job.timeout if job.timeout is not None else -1
            )
        if not acquired:
            msg = f"{self.name} - remote '{name}' is busy"
            log.warning(msg)
            if job is not None:
                job.event(msg, severity="WARNING")
            return Result(failed=True, errors=[f"Remote '{name}' is busy"])

        try:
            # Remove both the public snapshot and the private Git working tree.
            shutil.rmtree(self._safe_path(remote["mount"]), ignore_errors=True)
            shutil.rmtree(os.path.dirname(remote["repository"]), ignore_errors=True)
        finally:
            lock.release()
        self.remotes.pop(name, None)
        msg = f"{self.name} - deleted Git remote '{name}'"
        log.info(msg)
        if job is not None:
            job.event(msg)
        return Result(result=True)

    @Task(
        input=RemoteNameInput,
        output=GitCloneResult,
        fastapi={"methods": ["POST"]},
        agent={"enabled": False},
        mcp={
            "annotations": {
                "title": "Clone Git Remote",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def git_clone(self, job: Job, name: str) -> Result:
        """Synchronize content from an initialized Git remote and make it available.

        The task shallow-fetches the configured branch, checks out the fetched
        commit, and compares it with the current local Git HEAD. Changed
        working-tree content is copied into a staging snapshot with ``.git``
        and symbolic links excluded, then atomically made available beneath the File
        Sharing base directory. Public and HTTP Basic authenticated remotes are
        supported.

        Args:
            job: Active worker job. Scheduler calls pass ``None`` and skip the
                operation when another task holds the remote lock.
            name: Name of a Git remote initialized by ``create_remote_git``.

        Returns:
            A result containing the updated synchronization state. Successful
            results use ``cloned`` when a snapshot is made available and
            ``unchanged`` when Git reports the same commit and the mount exists.
        """
        msg = f"{self.name} - synchronizing Git remote '{name}'"
        log.info(msg)
        if job is not None:
            job.event(msg)

        if name not in self.remotes:
            msg = f"{self.name} - remote '{name}' is not configured"
            log.warning(msg)
            if job is not None:
                job.event(msg, severity="ERROR")
            return Result(failed=True, errors=[f"Remote '{name}' is not configured"])

        remote = self.remotes[name]
        if remote["type"] != "git":
            msg = f"{self.name} - remote '{name}' is not a git remote"
            log.warning(msg)
            if job is not None:
                job.event(msg, severity="ERROR")
            return Result(failed=True, errors=[f"Remote '{name}' is not a git remote"])

        lock = remote["lock"]
        if job is None:
            acquired = lock.acquire(blocking=False)
        else:
            acquired = lock.acquire(
                timeout=job.timeout if job.timeout is not None else -1
            )
        if not acquired:
            msg = f"{self.name} - remote '{name}' is busy"
            log.warning(msg)
            if job is not None:
                job.event(msg, severity="WARNING")
            return Result(failed=True, errors=[f"Remote '{name}' is busy"])

        remote_dir = os.path.dirname(remote["repository"])
        mount_dir = self._safe_path(remote["mount"])
        staging_dir = os.path.join(remote_dir, "staging")
        snapshot_dir = os.path.join(staging_dir, "snapshot")
        error = "Remote synchronization failed"

        try:
            # Staging is recreated for each sync so an incomplete snapshot is
            # never visible from the configured mount.
            shutil.rmtree(staging_dir, ignore_errors=True)
            if not os.path.isdir(os.path.join(remote["repository"], ".git")):
                raise ValueError("Local Git repository is not initialized")

            msg = (
                f"{self.name} - fetching branch '{remote['branch']}' for remote "
                f"'{name}'"
            )
            log.info(msg)
            if job is not None:
                job.event(msg)
            with Repo(remote["repository"]) as repository:
                previous_sha = (
                    repository.head.commit.hexsha
                    if repository.head.is_valid()
                    else None
                )
                fetched = repository.remotes.origin.fetch(
                    remote["branch"],
                    depth=1,
                    env=self._git_fetch_environment(remote),
                )
                sha = fetched[0].commit.hexsha
                repository.git.checkout("-B", remote["branch"], sha)

            changed = previous_sha != sha or not os.path.isdir(mount_dir)
            if changed:
                msg = f"{self.name} - making Git remote '{name}' available at {remote['mount']}"
                log.info(msg)
                if job is not None:
                    job.event(msg)

                # Copy only regular repository files; the Git metadata and
                # symbolic links must not enter the shared namespace.
                os.makedirs(snapshot_dir, exist_ok=False)
                for root, directories, files in os.walk(
                    remote["repository"], topdown=True
                ):
                    relative_root = os.path.relpath(root, remote["repository"]).replace(
                        os.sep, "/"
                    )
                    if relative_root == ".":
                        relative_root = ""

                    for directory in directories[:]:
                        path = os.path.join(root, directory)
                        if os.path.islink(path):
                            raise ValueError("Git repository contains a symbolic link")
                        if directory == ".git":
                            directories.remove(directory)

                    for filename in files:
                        relative_path = "/".join(
                            part for part in [relative_root, filename] if part
                        )
                        source = os.path.join(root, filename)
                        if os.path.islink(source):
                            raise ValueError("Git repository contains a symbolic link")
                        destination = os.path.join(
                            snapshot_dir, *relative_path.split("/")
                        )
                        os.makedirs(os.path.dirname(destination), exist_ok=True)
                        shutil.copy2(source, destination)

                # Swap complete directories so readers see either the old or
                # the new snapshot, never a partially copied one.
                previous_dir = os.path.join(staging_dir, "previous")
                os.makedirs(os.path.dirname(mount_dir), exist_ok=True)
                if os.path.exists(mount_dir):
                    os.replace(mount_dir, previous_dir)
                try:
                    os.replace(snapshot_dir, mount_dir)
                except Exception:
                    if os.path.exists(previous_dir):
                        os.replace(previous_dir, mount_dir)
                    raise

            remote["status"] = "cloned" if changed else "unchanged"
        except Exception as exc:
            remote["status"] = "failed"
            error = f"{type(exc).__name__}: remote synchronization failed"
            msg = (
                f"{self.name} - Git remote '{name}' synchronization failed with "
                f"{type(exc).__name__}"
            )
            log.error(msg)
            if job is not None:
                job.event(msg, severity="ERROR")
        finally:
            remote["last_sync_attempt"] = datetime.now(timezone.utc).isoformat()
            remote["last_sync_timer"] = time.monotonic()
            shutil.rmtree(staging_dir, ignore_errors=True)
            lock.release()

        result = {
            "name": remote["name"],
            "status": remote["status"],
            "last_sync_attempt": remote["last_sync_attempt"],
        }
        if remote["status"] == "failed":
            return Result(
                result=result,
                failed=True,
                errors=[error],
            )
        msg = (
            f"{self.name} - Git remote '{name}' synchronization completed with status "
            f"'{remote['status']}'"
        )
        log.info(msg)
        if job is not None:
            job.event(msg)
        return Result(result=result)

    @Task(
        input=ResolveGitUrlInput,
        output=ResolveGitUrlResult,
        fastapi={"methods": ["POST"]},
        agent={"enabled": False},
        mcp={
            "annotations": {
                "title": "Resolve Git URL",
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        },
    )
    def resolve_git_url(self, job: Job, url: str) -> Result:
        """Synchronize a Git remote and resolve its file URL to an nf:// URL.

        Args:
            job: Active worker job used by the Git synchronization task.
            url: File URL in ``git://<remote-name>/<path>`` format.

        Returns:
            A result containing the published ``nf://`` file URL. Invalid URLs,
            unknown remotes, unsafe paths, and synchronization failures produce
            failed results.
        """
        remote_path = url.removeprefix("git://").replace("\\", "/")
        name, separator, file_path = remote_path.partition("/")
        if not url.startswith("git://") or not name or not separator or not file_path:
            return Result(failed=True, errors=[f"'{url}' - invalid Git URL format"])

        remote = self.remotes.get(name)
        if remote is None:
            return Result(failed=True, errors=[f"Remote '{name}' is not configured"])
        if remote["type"] != "git":
            return Result(failed=True, errors=[f"Remote '{name}' is not a git remote"])

        mount_path = self._safe_path(remote["mount"])
        resolved_path = os.path.abspath(os.path.join(mount_path, *file_path.split("/")))
        if os.path.commonpath([mount_path, resolved_path]) != mount_path:
            return Result(failed=True, errors=[f"'{url}' - invalid Git URL path"])

        sync_result = self.git_clone(job, name)
        if sync_result.failed:
            return Result(failed=True, errors=sync_result.errors)
        if not os.path.isfile(resolved_path):
            return Result(failed=True, errors=[f"'{url}' file not found"])

        published_path = os.path.relpath(resolved_path, mount_path).replace(os.sep, "/")
        resolved_url = f"{remote['mount'].rstrip('/')}/{published_path}"
        return Result(result=resolved_url)

    def start_git_sync(self) -> threading.Thread | None:
        """Start periodic Git synchronization when at least one remote enables it.

        Spawns a background daemon thread that periodically synchronizes all
        configured Git remotes that have auto_sync enabled. The thread runs
        until the worker shuts down.

        Returns:
            threading.Thread | None: The started daemon thread if at least one
                remote has auto_sync enabled, otherwise None. The thread runs the
                git_sync_loop method.
        """
        if not any(
            remote["type"] == "git" and remote["auto_sync"]
            for remote in self.remotes.values()
        ):
            return None

        log.info(f"{self.name} - Starting Git remote synchronization thread")
        thread = threading.Thread(
            target=self.git_sync_loop,
            name=f"{self.name}-git-sync",
            daemon=True,
        )
        thread.start()
        return thread

    def git_sync_loop(self) -> None:
        """Synchronize due Git remotes until worker shutdown.

        Every second, clone each Git remote whose automatic synchronization is
        enabled and whose interval has elapsed. Errors are logged without
        stopping the loop.

        Returns:
            None: Runs until remote_sync_stop event is set (during worker shutdown).
        """
        while not self.remote_sync_stop.wait(1):
            try:
                now = time.monotonic()
                for remote in self.remotes.values():
                    if (
                        remote["type"] == "git"
                        and remote["auto_sync"]
                        and (
                            remote["last_sync_timer"] is None
                            or now - remote["last_sync_timer"]
                            >= remote["sync_interval"]
                        )
                    ):
                        log.info(
                            f"{self.name} - Automatically synchronizing Git remote "
                            f"'{remote['name']}'"
                        )
                        self.git_clone(None, remote["name"])
            except Exception as exc:
                log.error(
                    f"{self.name} - Git synchronization loop failed with {type(exc).__name__}"
                )
