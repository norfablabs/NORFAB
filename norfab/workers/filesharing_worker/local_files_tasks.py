import hashlib
import os

from norfab.core.worker import Job, Task
from norfab.models import Result

from .filesharing_models import (
    FetchFileInput,
    FetchFileResult,
    FileDetailsInput,
    FileDetailsResult,
    ListFilesInput,
    ListFilesResult,
    WalkInput,
    WalkResult,
)


class LocalFilesTasks:
    def _safe_path(self, url: str) -> str:
        """Resolve an ``nf://`` URL within the configured publication directory.

        Args:
            url: File Sharing URL to resolve. The value must start with
                ``nf://`` and contain a path relative to the worker's base
                directory.

        Returns:
            The normalized absolute filesystem path represented by ``url``.

        Raises:
            ValueError: If the URL does not use the ``nf://`` scheme or resolves
                outside the configured File Sharing base directory.
        """
        if not url.startswith("nf://"):
            raise ValueError(f"'{url}' - invalid URL format")
        url_path = url.replace("nf://", "")
        url_path = url_path.lstrip("/\\")
        base_abs = os.path.abspath(self.base_dir)
        candidate = os.path.abspath(os.path.join(base_abs, *url_path.split("/")))
        if os.path.commonpath([base_abs, candidate]) != base_abs:
            raise ValueError(f"'{url}' - invalid URL path")
        return candidate

    @Task(
        input=ListFilesInput,
        output=ListFilesResult,
        fastapi={"methods": ["GET"]},
        agent={"enabled": False},
        mcp={
            "annotations": {
                "title": "List Files",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            }
        },
    )
    def list_files(self, url: str) -> Result:
        """List direct children of a published File Sharing directory.

        The task resolves the supplied ``nf://`` URL below the configured base
        directory and returns the names produced by ``os.listdir``. It does not
        recurse into child directories.

        Args:
            url: Directory URL beginning with ``nf://``.

        Returns:
            A result containing the directory entries. The result is marked as
            failed when the URL is unsafe or the directory does not exist.
        """
        ret = Result(result=None)
        try:
            full_path = self._safe_path(url)
        except ValueError as exc:
            ret.failed = True
            ret.errors = [str(exc)]
            return ret

        if os.path.exists(full_path) and os.path.isdir(full_path):
            ret.result = os.listdir(full_path)
        else:
            ret.errors = ["Directory Not Found"]
            ret.failed = True
        return ret

    @Task(
        input=FileDetailsInput,
        output=FileDetailsResult,
        fastapi={"methods": ["GET"]},
        agent={"enabled": False},
        mcp={
            "annotations": {
                "title": "Get File Details",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            }
        },
    )
    def file_details(self, url: str) -> Result:
        """Return integrity and size details for one published file.

        Args:
            url: File URL beginning with ``nf://``.

        Returns:
            A result containing ``md5hash``, ``size_bytes``, and ``exists``.
            Missing files and unsafe URLs produce failed results.
        """
        ret = Result(result={"md5hash": None, "size_bytes": None, "exists": False})
        try:
            full_path = self._safe_path(url)
        except ValueError as exc:
            ret.failed = True
            ret.errors = [str(exc)]
            return ret
        exists = os.path.exists(full_path) and os.path.isfile(full_path)

        if exists:
            with open(full_path, "rb") as file_obj:
                file_hash = hashlib.md5()
                chunk = file_obj.read(8192)
                while chunk:
                    file_hash.update(chunk)
                    chunk = file_obj.read(8192)
            ret.result = {
                "md5hash": file_hash.hexdigest(),
                "size_bytes": os.path.getsize(full_path),
                "exists": True,
            }
        else:
            ret.failed = True
            ret.errors = [f"'{url}' file not found"]

        return ret

    @Task(
        input=WalkInput,
        output=WalkResult,
        fastapi={"methods": ["GET"]},
        agent={"enabled": False},
        mcp={
            "annotations": {
                "title": "Walk Files",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            }
        },
    )
    def walk(self, url: str) -> Result:
        """Recursively list published files beneath an ``nf://`` directory.

        Hidden files and internal paths containing double-underscore directory
        markers are omitted from the returned namespace.

        Args:
            url: Root directory URL beginning with ``nf://``.

        Returns:
            A result containing normalized ``nf://`` file URLs. Missing
            directories and unsafe URLs produce failed results.
        """
        ret = Result(result=None)
        try:
            full_path = self._safe_path(url)
        except ValueError as exc:
            ret.failed = True
            ret.errors = [str(exc)]
            return ret

        if os.path.exists(full_path) and os.path.isdir(full_path):
            files_list = []
            for root, _directories, files in os.walk(full_path):
                if root.count("__") >= 2:
                    continue
                root = root.replace(self.base_dir, "")
                root = root.lstrip("\\")
                root = root.replace("\\", "/")
                for filename in files:
                    if filename.startswith("."):
                        continue
                    if root:
                        files_list.append(f"nf://{root}/{filename}")
                    else:
                        files_list.append(f"nf://{filename}")
            ret.result = files_list
        else:
            ret.failed = True
            ret.errors = ["Directory Not Found"]
        return ret

    @Task(
        input=FetchFileInput,
        output=FetchFileResult,
        fastapi={"methods": ["GET"]},
        agent={"enabled": False},
        mcp={
            "annotations": {
                "title": "Fetch File",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            }
        },
    )
    def fetch_file(
        self,
        job: Job,
        url: str,
        chunk_size: int = 256000,
        offset: int = 0,
        chunk_timeout: int = 5,
    ) -> Result:
        """Stream a published file to the requesting client in chunks.

        After each non-final chunk, the task waits for the client to provide the
        next byte offset. This credit-based exchange limits buffered data and
        supports client-controlled continuation.

        Args:
            job: Active worker job used to stream bytes and receive the next
                requested offset.
            url: File URL beginning with ``nf://``.
            chunk_size: Maximum number of bytes streamed in each chunk.
            offset: Initial byte offset within the file.
            chunk_timeout: Seconds to wait for the client's next offset.

        Returns:
            A result containing ``True`` after the complete file is streamed.
            Missing files and unsafe URLs produce failed results.

        Raises:
            RuntimeError: If the client does not request the next chunk before
                ``chunk_timeout`` expires.
        """
        ret = Result(result=None)
        try:
            full_path = self._safe_path(url)
        except ValueError as exc:
            ret.failed = True
            ret.errors = [str(exc)]
            return ret

        if os.path.exists(full_path):
            size = os.path.getsize(full_path)
            with open(full_path, "rb") as file_obj:
                while True:
                    file_obj.seek(offset, os.SEEK_SET)
                    chunk = file_obj.read(chunk_size)
                    if chunk:
                        job.stream(chunk)
                    if file_obj.tell() >= size:
                        break
                    client_response = job.wait_client_input(timeout=chunk_timeout)
                    if not client_response:
                        raise RuntimeError(
                            f"{self.name}:fetch_file - {chunk_timeout}s chunk timeout reached before received next chunk request from client"
                        )
                    offset = client_response["offset"]

            ret.result = True
        else:
            ret.failed = True
            ret.errors = [f"'{url}' file not found"]

        return ret
