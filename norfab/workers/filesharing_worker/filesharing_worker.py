import yaml
import logging
import sys
import os
import hashlib
import importlib.metadata
from norfab.core.worker import NFPWorker, Task, Job
from norfab.models import Result
from typing import Any, List, Callable

SERVICE = "filesharing"

log = logging.getLogger(__name__)


class FileSharingWorker(NFPWorker):
    """ """

    def __init__(
        self,
        inventory: Any,
        broker: str,
        worker_name: str,
        exit_event: Any = None,
        init_done_event: Any = None,
        log_level: str = "WARNING",
        log_queue: object = None,
    ):
        super().__init__(
            inventory, broker, SERVICE, worker_name, exit_event, log_level, log_queue
        )
        self.init_done_event = init_done_event

        # get inventory from broker
        self.filesharing_inventory = self.load_inventory()
        self.base_dir = self.filesharing_inventory.get("base_dir")

        self.init_done_event.set()
        log.error(f"{self.name} - Started, {self.filesharing_inventory}")

    def worker_exit(self):
        pass

    @Task(fastapi={"methods": ["GET"]})
    def get_version(self) -> Result:
        libs = {
            "python": sys.version.split(" ")[0],
            "platform": sys.platform,
        }
        # get version of packages installed
        for pkg in libs.keys():
            try:
                libs[pkg] = importlib.metadata.version(pkg)
            except importlib.metadata.PackageNotFoundError:
                pass

        return Result(result=libs)

    @Task(fastapi={"methods": ["GET"]})
    def get_inventory(self) -> Result:
        return Result(result=self.filesharing_inventory)

    @Task(fastapi={"methods": ["GET"]})
    def get_status(self) -> Result:
        return Result(result="OK")

    @Task(fastapi={"methods": ["GET"]})
    def list_files(self, url: str) -> Result:
        """
        List files in a directory.

        Args:
            url: URL path starting with 'nf://' to list files from

        Returns:
            Result containing list of files or error message
        """
        ret = Result(result=None)
        if not url.startswith("nf://"):
            ret.failed = True
            ret.errors = [f"'{url}' - invalid URL format"]
            return ret

        url_path = url.replace("nf://", "")
        full_path = os.path.join(self.base_dir, url_path)

        if os.path.exists(full_path) and os.path.isdir(full_path):
            ret.result = os.listdir(full_path)
        else:
            ret.errors = ["Directory Not Found"]
            ret.failed = True
        return ret

    @Task(fastapi={"methods": ["GET"]})
    def file_details(self, url: str) -> Result:
        """
        Get file details including md5 hash, size, and existence.

        Args:
            url: URL path starting with 'nf://' to get file details

        Returns:
            Result containing md5hash, size_bytes, and exists fields
        """
        ret = Result(result={"md5hash": None, "size_bytes": None, "exists": False})
        if not url.startswith("nf://"):
            ret.failed = True
            ret.errors = [f"'{url}' - invalid URL format"]
            return ret

        url_path = url.replace("nf://", "")
        full_path = os.path.join(self.base_dir, url_path)
        exists = os.path.exists(full_path) and os.path.isfile(full_path)

        # calculate md5 hash
        md5hash = None
        if exists:
            with open(full_path, "rb") as f:
                file_hash = hashlib.md5()
                chunk = f.read(8192)
                while chunk:
                    file_hash.update(chunk)
                    chunk = f.read(8192)
            md5hash = file_hash.hexdigest()
            size = os.path.getsize(full_path)
            ret.result = {
                "md5hash": md5hash,
                "size_bytes": size,
                "exists": exists,
            }
        else:
            ret.failed = True
            ret.errors = [f"'{url}' file not found"]

        return ret

    @Task(fastapi={"methods": ["GET"]})
    def walk(self, url: str) -> Result:
        """
        Recursively list all files from all subdirectories.

        Args:
            url: URL path starting with 'nf://' to walk directories

        Returns:
            Result containing list of all file paths or error message
        """
        ret = Result(result=None)
        if not url.startswith("nf://"):
            ret.failed = True
            ret.errors = [f"'{url}' - invalid URL format"]
            return ret

        url_path = url.replace("nf://", "")
        full_path = os.path.join(self.base_dir, url_path)

        if os.path.exists(full_path) and os.path.isdir(full_path):
            files_list = []
            for root, dirs, files in os.walk(full_path):
                # skip path containing folders like __folders__
                if root.count("__") >= 2:
                    continue
                root = root.replace(self.base_dir, "")
                root = root.lstrip("\\")
                root = root.replace("\\", "/")
                for file in files:
                    # skip hidden/system files
                    if file.startswith("."):
                        continue
                    if root:
                        files_list.append(f"nf://{root}/{file}")
                    else:
                        files_list.append(f"nf://{file}")
            ret.result = files_list
        else:
            ret.failed = True
            ret.errors = ["Directory Not Found"]
        return ret

    @Task(fastapi={"methods": ["GET"]})
    def fetch_file(
        self,
        job: Job,
        url: str,
        chunk_size: int = 256000,
        offset: int = 0,
        chunk_timeout: int = 5,
    ) -> Result:
        """
        Fetch a file in chunks with offset support.

        Args:
            url: URL path starting with 'nf://' to fetch file from
            chunk_size: Size of chunk to read in bytes (default: 256KB)
            offset: Number of bytes to offset (default: 0)

        Returns:
            Result containing file chunk bytes or error message
        """
        ret = Result(result=None)
        if not url.startswith("nf://"):
            ret.failed = True
            ret.errors = [f"'{url}' file URL format is wrong"]
            return ret

        url_path = url.replace("nf://", "")
        full_path = os.path.join(self.base_dir, url_path)

        if os.path.exists(full_path):
            size = os.path.getsize(full_path)
            with open(full_path, "rb") as f:
                while True:
                    f.seek(offset, os.SEEK_SET)
                    chunk = f.read(chunk_size)
                    job.stream(chunk)
                    if f.tell() == size:
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
