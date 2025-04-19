import logging
import sys
import threading
import time
import os
import signal
import importlib.metadata
import subprocess
import yaml
import json

from norfab.core.worker import NFPWorker
from norfab.models import Result
from typing import Union, List, Dict, Any, Annotated, Optional, Tuple

SERVICE = "containerlab"

log = logging.getLogger(__name__)


class ContainerlabWorker(NFPWorker):
    """
    FastAPContainerlabWorker IWorker is a worker class that integrates with containerlab to run network topologies.

    Args:
        inventory (str): Inventory configuration for the worker.
        broker (str): Broker URL to connect to.
        worker_name (str): Name of this worker.
        exit_event (threading.Event, optional): Event to signal worker to stop/exit.
        init_done_event (threading.Event, optional): Event to signal when worker is done initializing.
        log_level (str, optional): Logging level for this worker.
        log_queue (object, optional): Queue for logging.
    """

    def __init__(
        self,
        inventory: str,
        broker: str,
        worker_name: str,
        exit_event=None,
        init_done_event=None,
        log_level: str = None,
        log_queue: object = None,
    ):
        super().__init__(
            inventory, broker, SERVICE, worker_name, exit_event, log_level, log_queue
        )
        self.init_done_event = init_done_event
        self.exit_event = exit_event
        
        # create directory to store lab topologies
        self.topologies_dir = os.path.join(self.base_dir, "topologies")
        os.makedirs(self.topologies_dir, exist_ok=True)
        
        # get inventory from broker
        self.containerlab_inventory = self.load_inventory()
        
        self.init_done_event.set()

    def worker_exit(self):
        """
        Terminates the current process by sending a SIGTERM signal to itself.

        This method retrieves the current process ID using `os.getpid()` and then
        sends a SIGTERM signal to terminate the process using `os.kill()`.
        """
        os.kill(os.getpid(), signal.SIGTERM)

    def get_version(self):
        """
        Produce a report of the versions of various Python packages.

        This method collects the versions of several specified Python packages
        and returns them in a dictionary.

        Returns:
            Result: An object containing the task name and a dictionary with
                    the package names as keys and their respective versions as values.
        """
        libs = {
            "norfab": "",
            "pydantic": "",
            "python": sys.version.split(" ")[0],
            "platform": sys.platform,
            "containerlab": "",
        }
        ret = Result(task=f"{self.name}:get_version", result=libs)
        
        # get version of packages installed
        for pkg in libs.keys():
            try:
                libs[pkg] = importlib.metadata.version(pkg)
            except importlib.metadata.PackageNotFoundError:
                pass
            
        # get containerlab version
        clab_version = subprocess.run(["containerlab", "version"], capture_output=True, text=True)
        if clab_version.returncode == 0:
            libs["containerlab"] = clab_version.stdout
            libs["containerlab"] = "\n".join(libs["containerlab"].splitlines()[6:])
        else:
            ret.failed = True
            ret.errors = [
                clab_version.stderr.decode("utf-8")
            ]
        
        return ret        

    def get_inventory(self) -> Dict:
        """
        Retrieve the inventory of the Containerlab worker.

        Returns:
            Dict: A dictionary containing the combined inventory of Containerlab.
        """
        return Result(
            result=self.containerlab_inventory,
            task=f"{self.name}:get_inventory",
        )
    
    def get_containerlab_status(self) -> Result:
        """
        Retrieve the status of the Containerlab worker.

        Returns:
            Result: A result object containing the status of the Containerlab worker.
        """
        status = "OS NOT SUPPORTED" if sys.platform.startswith("win") else "READY"
        return Result(
            task=f"{self.name}:get_containerlab_status",
            result={"status": status},
        )
    
    def get_running_labs(self, timeout: int = None) -> Result:
        "Return a list of containerlab lab names that are running"
        ret = Result(task=f"{self.name}:get_running_labs", result=[])
        inspect = self.inspect(timeout=timeout)
        
        # form topologies list if any of them are runing
        if inspect.result:
            ret.result = [i["lab_name"] for i in inspect.result["containers"]]
            ret.result = list(sorted(set(ret.result)))
        
        return ret
    
    def run_containerlab_command(self, args: list, cwd: str=None, timeout: int=None, ret: Result =None) -> Tuple:
        output, logs = "", []
        
        with subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as proc:       
            while proc.poll() is None:
                msg = proc.stderr.readline().strip()
                if msg.strip():
                    self.event(msg.split("msg=")[-1].replace('\\"',"").strip('"'))
                    logs.append(msg)
                time.sleep(0.01)
            output = proc.stdout.read()
            
        # populate Norfab result object
        if ret is not None:
            try:
                ret.result = json.loads(output)
            except Exception as e:
                ret.result = output
                log.error(f"{self.name} - failed to load containerlab results into JSON, error: {e}")
            # check if command failed
            if proc.returncode != 0:
                ret.failed = True
                ret.errors = ["\n".join(logs)]
            else:
                ret.messages = ["\n".join(logs)]
            return ret
        # return command results as is
        else:
            return output, logs, proc

        
    def deploy(self, topology: str, reconfigure: bool = False, timeout: int = None) -> Result:
        ret = Result(task=f"{self.name}:deploy", result={"topology_folder": "", "topology_file": "", "deployment": None})
        
        # create folder to store topology
        topology_folder = os.path.split(os.path.split(topology)[0])[-1]
        topology_folder = os.path.join(self.topologies_dir, topology_folder)
        os.makedirs(topology_folder, exist_ok=True)
        ret.result["topology_folder"] = topology_folder
        
        # download topology file
        topology_file = os.path.join(topology_folder, os.path.split(topology)[-1])
        downloaded_topology_file = self.fetch_file(topology, raise_on_fail=True, read=False)
        os.rename(downloaded_topology_file, topology_file) # move tpology file under desired folder
        ret.result["topology_file"] = topology_file
        
        # form command arguments
        args = ["containerlab", "deploy", "-f", "json", "-t", topology_file]
        if reconfigure is True:
            args.append("--reconfigure")
            self.event(f"Re-deploying lab {os.path.split(topology_file)[-1]}")
        else:
            self.event(f"Deploying lab {os.path.split(topology_file)[-1]}")
            
        # run containerlab command
        return self.run_containerlab_command(args, cwd=topology_folder, timeout=timeout, ret=ret)
                    
        
    def destroy(self, lab_name: str, timeout: int = None) -> Result:
        ret = Result(task=f"{self.name}:destroy")
        
        # get lab details
        inspect = self.inspect(timeout=timeout, lab_name=lab_name, details=True)
        
        if not inspect.result:
            ret.failed = True
            ret.errors = [f"'{lab_name}' lab not found"]
            ret.result = {lab_name: False}
        else:
            topology_file = inspect.result[0]["Labels"]["clab-topo-file"]
            topology_folder = os.path.split(topology_file)[0]

            # run destroy command
            args = ["containerlab", "destroy", "-t", topology_file]
            ret = self.run_containerlab_command(args, cwd=topology_folder, timeout=timeout, ret=ret)

            if not ret.failed:
                ret.result = {lab_name: True}
        
        return ret
        
        
    def inspect(self, lab_name: str = None, timeout: int = None, details: bool = False) -> Result:
        ret = Result(task=f"{self.name}:inspect")
        
        if lab_name:
            args = ["containerlab", "inspect", "-f", "json", "--name", lab_name]
        else:
            args = ["containerlab", "inspect", "-f", "json", "--all"]
        if details:
            args.append("--details")
            
        ret = self.run_containerlab_command(args, timeout=timeout, ret=ret)
                
        return ret

        
    def save(self, lab_name: str, timeout: int = None) -> Result:
        ret = Result(task=f"{self.name}:save")
        
        # get lab details
        inspect = self.inspect(timeout=timeout, lab_name=lab_name, details=True)
        
        if not inspect.result:
            ret.failed = True
            ret.errors = [f"'{lab_name}' lab not found"]
            ret.result = {lab_name: False}
        else:
            topology_file = inspect.result[0]["Labels"]["clab-topo-file"]
            topology_folder = os.path.split(topology_file)[0]

            # run destroy command
            args = ["containerlab", "save", "-t", topology_file]
            ret = self.run_containerlab_command(args, cwd=topology_folder, timeout=timeout, ret=ret)

            if not ret.failed:
                ret.result = {lab_name: True}
        
        return ret

    def restart(self, lab_name: str, timeout: int = None) -> Result:
        ret = Result(task=f"{self.name}:restart")
        
        # get lab details
        inspect = self.inspect(timeout=timeout, lab_name=lab_name, details=True)
        
        if not inspect.result:
            ret.failed = True
            ret.errors = [f"'{lab_name}' lab not found"]
            ret.result = {lab_name: False}
        else:
            topology_file = inspect.result[0]["Labels"]["clab-topo-file"]
            topology_folder = os.path.split(topology_file)[0]

            # run destroy command
            args = ["containerlab", "deploy", "-f", "json", "-t", topology_file, "--reconfigure"]
            ret = self.run_containerlab_command(args, cwd=topology_folder, timeout=timeout, ret=ret)

            if not ret.failed:
                ret.result = {lab_name: True}
        
        return ret
        
