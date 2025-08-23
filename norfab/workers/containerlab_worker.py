import logging
import sys
import time
import os
import signal
import importlib.metadata
import subprocess
import yaml
import json
import socket
import ipaddress

from norfab.core.worker import NFPWorker, Task, Job
from norfab.core.inventory import merge_recursively
from norfab.models.containerlab import DeployTask, DeployTaskResponse
from norfab.models import Result
from norfab.utils.platform_map import PlatformMap
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

        # merge local inventory with inventory from broker
        merge_recursively(self.inventory[self.name], self.load_inventory())

        self.clab_version = self.get_clab_version()

        self.init_done_event.set()

    def get_clab_version(self):
        clab_version = None
        clab_version = subprocess.run(
            ["containerlab", "version"], capture_output=True, text=True
        )
        if clab_version.returncode == 0:
            clab_version = clab_version.stdout
            for line in clab_version.splitlines()[6:]:
                if "version" in line.lower():
                    clab_version = [int(i) for i in line.split(" ")[-1].split(".")]
                    break
            else:
                raise RuntimeError(
                    f"Containerlab worker failed to get containerlab version"
                )
        else:
            raise RuntimeError(
                f"Containerlab worker failed to get containerlab version, "
                f"error: '{clab_version.stderr.decode('utf-8')}'"
            )

        return clab_version

    def worker_exit(self):
        """
        Terminates the current process by sending a SIGTERM signal to itself.

        This method retrieves the current process ID using `os.getpid()` and then
        sends a SIGTERM signal to terminate the process using `os.kill()`.
        """
        os.kill(os.getpid(), signal.SIGTERM)

    @Task(fastapi={"methods": ["GET"]})
    def get_version(self) -> Result:
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
            "containerlab": ".".join([str(i) for i in self.clab_version]),
        }
        ret = Result(task=f"{self.name}:get_version", result=libs)

        # get version of packages installed
        for pkg in libs.keys():
            try:
                libs[pkg] = importlib.metadata.version(pkg)
            except importlib.metadata.PackageNotFoundError:
                pass

        return ret

    @Task(fastapi={"methods": ["GET"]})
    def get_inventory(self) -> Result:
        """
        Retrieve the inventory of the Containerlab worker.

        Returns:
            Dict: A dictionary containing the combined inventory of Containerlab.
        """
        return Result(
            result=self.inventory[self.name],
            task=f"{self.name}:get_inventory",
        )

    @Task(fastapi={"methods": ["GET"]})
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

    @Task(fastapi={"methods": ["GET"]})
    def get_running_labs(self, job: Job, timeout: int = None) -> Result:
        """
        Retrieve a list of running containerlab lab names.

        This method inspects the current state of containerlab and returns
        the names of labs that are currently running. The names are sorted
        and duplicates are removed.

        Args:
            timeout (int, optional): The timeout value in seconds for the inspection
                operation. Defaults to None.

        Returns:
            Result: A Result object containing the task name and a list of running
            lab names.
        """
        timeout = timeout or 600
        ret = Result(task=f"{self.name}:get_running_labs", result=[])
        inspect = self.inspect(job=job, timeout=timeout)

        # form topologies list if any of them are runing
        if inspect.result:
            ret.result = inspect.result.keys()
            ret.result = list(sorted(set(ret.result)))

        return ret

    @Task(fastapi={"methods": ["POST"]})
    def run_containerlab_command(
        self,
        job: Job,
        args: list,
        cwd: str = None,
        timeout: int = None,
        ret: Result = None,
        env: Union[None, dict] = None,
        expect_output: bool = True,
    ) -> Tuple:
        """
        Executes a containerlab command using subprocess and processes its output.

        Args:
            args (list): The list of command-line arguments to execute.
            cwd (str, optional): The working directory to execute the command in. Defaults to None.
            timeout (int, optional): The timeout for the command execution in seconds. Defaults to None.
            ret (Result, optional): An optional Norfab result object to populate with the command's output. Defaults to None.
            env (dict, Optional): OS Environment variables ti use when running the process
            expect_output (bool, Optional): whether to expect any output from command

        Returns:
            Tuple: If `ret` is None, returns a tuple containing:
                - output (str): The standard output of the command.
                - logs (list): A list of log messages from the command's standard error.
                - proc (subprocess.Popen): The subprocess object for the executed command.
            Result: If `ret` is provided, returns the populated `Result` object with the following attributes:
                - result: The parsed JSON output or raw output of the command.
                - failed (bool): Indicates if the command execution failed.
                - errors (list): A list of error messages if the command failed.
                - messages (list): A list of log messages if the command succeeded.

        Raises:
            Exception: If the output cannot be parsed as JSON when `ret` is provided.

        Notes:
            - The method reads the command's standard error line by line and processes messages containing "msg=".
            - If the command fails (non-zero return code), the `ret.failed` attribute is set to True, and errors are populated.
            - If the command succeeds, the `ret.messages` attribute is populated with log messages.
        """
        timeout = timeout or 600
        output, logs = "", []
        begin = time.time()
        timeout = timeout or 600
        env = env or dict(os.environ)

        with subprocess.Popen(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        ) as proc:
            while proc.poll() is None:
                if time.time() - begin > timeout:
                    raise TimeoutError(
                        f"Containerlab output collection {timeout}s timeout expired."
                    )
                msg = proc.stderr.readline().strip()
                if msg:
                    job.event(msg.split("msg=")[-1].replace('\\"', "").strip('"'))
                    logs.append(msg)
                time.sleep(0.01)
            # read remaining messages
            for msg in proc.stderr.readlines():
                msg = msg.strip()
                if msg:
                    job.event(msg.split("msg=")[-1].replace('\\"', "").strip('"'))
                    logs.append(msg)
                time.sleep(0.01)
            # read process output
            output = proc.stdout.read()

        # populate Norfab result object
        if ret is not None:
            # check if command failed
            if proc.returncode != 0:
                ret.failed = True
                ret.errors = ["\n".join(logs)]
            # check if got no output
            elif not output.strip() and expect_output is True:
                ret.failed = True
                ret.errors = ["\n".join(logs)]
            else:
                ret.messages = ["\n".join(logs)]
                try:
                    ret.result = json.loads(output)
                except Exception as e:
                    # if failed, remove any beginning lines that are not part of json
                    try:
                        line_split = output.splitlines()
                        for index, line in enumerate(line_split):
                            # find first json output line
                            if "{" in line or "[" in line:
                                ret.result = json.loads("\n".join(line_split[index:]))
                                break
                    except Exception as e:
                        ret.result = output
                        log.error(
                            f"{self.name} - failed to load containerlab results into JSON, error: {e}, result: '{output}'"
                        )

            return ret
        # return command results as is
        else:
            return output, logs, proc

    @Task(fastapi={"methods": ["POST"]}, input=DeployTask, output=DeployTaskResponse)
    def deploy(
        self,
        job: Job,
        topology: str,
        reconfigure: bool = False,
        timeout: int = None,
        node_filter: Union[None, str] = None,
    ) -> Result:
        """
        Deploys a containerlab topology.

        This method handles the deployment of a containerlab topology by downloading
        the topology file, organizing it into a specific folder structure, and executing
        the `containerlab deploy` command with the appropriate arguments.

        Args:
            topology (str): The path to the topology file to be deployed.
            reconfigure (bool, optional): If True, reconfigures an already deployed lab.
                Defaults to False.
            timeout (int, optional): The timeout in seconds for the deployment process.
                Defaults to None (no timeout).
            node_filter (str, optional): A filter to specify which nodes to deploy.

        Returns:
            Result: deployment results with a list of nodes deployed

        Raises:
            Exception: If the topology file cannot be fetched.
        """
        timeout = timeout or 600
        ret = Result(task=f"{self.name}:deploy")

        # create folder to store topology
        topology_folder = os.path.split(os.path.split(topology)[0])[-1]
        topology_folder = os.path.join(self.topologies_dir, topology_folder)
        os.makedirs(topology_folder, exist_ok=True)

        # download topology file
        topology_file = os.path.join(topology_folder, os.path.split(topology)[-1])
        if self.is_url(topology):
            downloaded_topology_file = self.fetch_file(
                topology, raise_on_fail=True, read=False
            )
            os.rename(
                downloaded_topology_file, topology_file
            )  # move tpology file under desired folder

        # form command arguments
        args = ["containerlab", "deploy", "-f", "json", "-t", topology_file]
        if reconfigure is True:
            args.append("--reconfigure")
            job.event(f"Re-deploying lab {os.path.split(topology_file)[-1]}")
        else:
            job.event(f"Deploying lab {os.path.split(topology_file)[-1]}")
        if node_filter:
            args.append("--node-filter")
            args.append(node_filter)

        # add needed env variables
        env = dict(os.environ)
        env["CLAB_VERSION_CHECK"] = "disable"

        # run containerlab command
        return self.run_containerlab_command(
            args=args, cwd=topology_folder, timeout=timeout, ret=ret, env=env, job=job
        )

    @Task(fastapi={"methods": ["DELETE"]})
    def destroy_lab(self, lab_name: str, job: Job, timeout: int = None) -> Result:
        """
        Destroys a specified lab.

        Args:
            lab_name (str): The name of the lab to be destroyed.
            timeout (int, optional): The timeout value in seconds for the operation. Defaults to None.

        Returns:
            Result: An object containing the status of the operation, errors (if any),
                    and the result indicating whether the lab was successfully destroyed.

        Behavior:
            - Retrieves the lab details using the `inspect` method.
            - If the lab is not found, marks the operation as failed and returns an error.
            - If the lab is found, retrieves the topology file and its folder.
            - Executes the `containerlab destroy` command using the topology file.
            - Updates the result to indicate success or failure of the destruction process.
        """
        timeout = timeout or 600
        ret = Result(task=f"{self.name}:destroy_lab")

        # get lab details
        inspect = self.inspect(
            job=job, timeout=timeout, lab_name=lab_name, details=True
        )

        if not inspect.result:
            ret.failed = True
            ret.errors = [f"'{lab_name}' lab not found"]
            ret.result = {lab_name: False}
        else:
            topology_file = inspect.result[lab_name][0]["Labels"]["clab-topo-file"]
            topology_folder = os.path.split(topology_file)[0]

            # run destroy command
            args = ["containerlab", "destroy", "-t", topology_file]
            ret = self.run_containerlab_command(
                args=args,
                cwd=topology_folder,
                timeout=timeout,
                ret=ret,
                job=job,
                expect_output=False,
            )

            if not ret.failed:
                ret.result = {lab_name: True}

        return ret

    @Task(fastapi={"methods": ["GET"]})
    def inspect(
        self,
        job: Job,
        lab_name: Union[None, str] = None,
        timeout: int = None,
        details: bool = False,
    ) -> Result:
        """
        Inspect the container lab containers configuration and status.

        This method retrieves information about a specific container lab or all
        container labs, optionally including detailed information.

        Args:
            lab_name (str, optional): The name of the container lab to inspect.
                If not provided, all container labs will be inspected.
            timeout (int, optional): The maximum time in seconds to wait for the
                inspection command to complete. Defaults to None.
            details (bool, optional): Whether to include detailed information in
                the inspection output. Defaults to False.

        Returns:
            Result: An object containing the result of the inspection task.
        """
        timeout = timeout or 600
        ret = Result(task=f"{self.name}:inspect")

        if lab_name:
            args = ["containerlab", "inspect", "-f", "json", "--name", lab_name]
        else:
            args = ["containerlab", "inspect", "-f", "json", "--all"]
        if details:
            args.append("--details")

        ret = self.run_containerlab_command(
            args=args, timeout=timeout, ret=ret, job=job
        )

        # check if lab name given and it is not in output
        if lab_name and lab_name not in ret.result:
            ret.failed = True
            msg = f"'{lab_name}' lab not found"
            ret.errors.append(msg)
            log.error(msg)

        return ret

    @Task(fastapi={"methods": ["POST"]})
    def save(self, job: Job, lab_name: str, timeout: int = None) -> Result:
        """
        Saves the config of a specified lab devices by invoking the `containerlab save` command.

        Args:
            lab_name (str): The name of the lab to save.
            timeout (int, optional): The maximum time in seconds to wait for the operation
                to complete. Defaults to None.

        Returns:
            Result: An object containing the outcome of the save operation. If successful,
                `result` will contain a dictionary with the lab name as the key and `True`
                as the value. If unsuccessful, `failed` will be set to True, and `errors`
                will contain a list of error messages.
        """
        timeout = timeout or 600
        ret = Result(task=f"{self.name}:save")

        # get lab details
        inspect = self.inspect(
            job=job, timeout=timeout, lab_name=lab_name, details=True
        )

        if not inspect.result:
            ret.failed = True
            ret.errors = [f"'{lab_name}' lab not found"]
            ret.result = {lab_name: False}
        else:
            topology_file = inspect.result[lab_name][0]["Labels"]["clab-topo-file"]
            topology_folder = os.path.split(topology_file)[0]

            # run destroy command
            args = ["containerlab", "save", "-t", topology_file]
            ret = self.run_containerlab_command(
                args=args,
                cwd=topology_folder,
                timeout=timeout,
                ret=ret,
                job=job,
                expect_output=False,
            )

            if not ret.failed:
                ret.result = {lab_name: True}

        return ret

    @Task(fastapi={"methods": ["POST"]})
    def restart_lab(self, job: Job, lab_name: str, timeout: int = None) -> Result:
        """
        Restart a specified Containerlab lab.

        This method retrieves the lab details, destroys the existing lab, and redeploys it
        using the provided topology file.

        Args:
            lab_name (str): The name of the lab to restart.
            timeout (int, optional): The timeout value for the operation in seconds. Defaults to None.

        Returns:
            Result: An object containing the status of the operation, any errors encountered,
                    and the result indicating whether the lab was successfully restarted.
        """
        timeout = timeout or 600
        ret = Result(task=f"{self.name}:restart_lab")

        # get lab details
        inspect = self.inspect(
            job=job, timeout=timeout, lab_name=lab_name, details=True
        )

        if not inspect.result:
            ret.failed = True
            ret.errors = [f"'{lab_name}' lab not found"]
            ret.result = {lab_name: False}
        else:
            topology_file = inspect.result[lab_name][0]["Labels"]["clab-topo-file"]
            topology_folder = os.path.split(topology_file)[0]

            # add needed env variables
            env = dict(os.environ)
            env["CLAB_VERSION_CHECK"] = "disable"

            # run destroy command
            args = [
                "containerlab",
                "deploy",
                "-f",
                "json",
                "-t",
                topology_file,
                "--reconfigure",
            ]
            ret = self.run_containerlab_command(
                args=args,
                cwd=topology_folder,
                timeout=timeout,
                ret=ret,
                env=env,
                job=job,
            )

            if not ret.failed:
                ret.result = {lab_name: True}

        return ret

    @Task(fastapi={"methods": ["GET"]})
    def get_nornir_inventory(
        self,
        job: Job,
        lab_name: Union[None, str] = None,
        timeout: int = None,
        groups: Union[None, list] = None,
        use_default_credentials: bool = True,
    ) -> Result:
        """
        Retrieves the Nornir inventory for a specified lab.

        This method inspects the container lab environment and generates a Nornir-compatible
        inventory of hosts based on the lab's configuration. It maps containerlab node kinds
        to Netmiko SSH platform types and extracts relevant connection details.

        Args:
            lab_name (str): The name of the container lab to inspect. If not given loads inventory for all labs.
            timeout (int, optional): The timeout value for the inspection operation. Defaults to None.
            groups (list, optional): A list of group names to assign to the hosts in the inventory. Defaults to None.
            use_default_credentials (bool, optional): Use Containerlab default credentials for hosts ot not.

        Returns:
            Result: A `Result` object containing the Nornir inventory. The `result` attribute
            includes a dictionary with host details. If the lab is not found or an error occurs,
            the `failed` attribute is set to True, and the `errors` attribute contains error messages.

        Notes:
            - The method uses a predefined mapping (`norfab.utils.platform_map`) to translate containerlab
              node kinds to Netmiko platform types.
            - If a container's SSH port cannot be determined, it is skipped, and an error is logged.
            - The primary host IP address is determined dynamically using a UDP socket connection or
              by checking the host IP address in the container's port configuration.

        Example of returned inventory structure:
            {
                "hosts": {
                    "host_name": {
                        "hostname": "host_ip",
                        "platform": "netmiko_platform",
                        "groups": ["group1", "group2"],
                    },
                    ...
        """
        timeout = timeout or 600
        groups = groups or []
        ret = Result(task=f"{self.name}:get_nornir_inventory", result={"hosts": {}})

        # get lab details
        inspect = self.inspect(
            job=job, lab_name=lab_name, timeout=timeout, details=True
        )

        # return empty result if lab not found
        if not inspect.result:
            ret.failed = True
            ret.errors = [f"'{lab_name}' lab not found"]
            return ret

        # get host primary IP address
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.connect(("1.2.3.4", 12345))
        primary_host_ip = s.getsockname()[0]
        log.debug(
            f"{self.name} - determined Containerlab host primary IP - '{primary_host_ip}'"
        )

        # form hosts inventory
        for lname, containers in inspect.result.items():
            if lab_name and lname != lab_name:
                continue
            for container in containers:
                host_name = container["Labels"]["clab-node-name"]
                host_port = None
                host_ip = None

                # get ssh port
                for port in container["Ports"]:
                    host_ip = primary_host_ip
                    if port["port"] == 22 and port["protocol"] == "tcp":
                        host_port = port["host_port"]
                        # get host ip address
                        if port["host_ip"] not in [
                            "0.0.0.0",
                            "127.0.0.1",
                            "localhost",
                            "::",
                        ]:
                            host_ip = port["host_ip"]
                        break
                else:
                    log.error(f"{self.name} - {host_name} failed to map SSH port.")
                    continue

                # add host to Nornir inventory
                ret.result["hosts"][host_name] = {
                    "hostname": host_ip,
                    "port": host_port,
                    "groups": groups,
                }

                # get netmiko platform
                clab_platform_name = container["Labels"]["clab-node-kind"]
                netmiko_platform = PlatformMap.convert(
                    "containerlab", "netmiko", clab_platform_name
                )
                if netmiko_platform:
                    ret.result["hosts"][host_name]["platform"] = netmiko_platform[
                        "platform"
                    ]
                else:
                    log.warning(
                        f"{self.name} - {host_name} clab-node-kind '{clab_platform_name}' not mapped to Netmiko platform."
                    )
                    continue

                # get default credentials
                if use_default_credentials:
                    clab_platform = PlatformMap.get("containerlab", clab_platform_name)
                    if not clab_platform:
                        log.warning(
                            f"{self.name} - {host_name} clab-node-kind '{clab_platform_name}' not found."
                        )
                        continue
                    if clab_platform.get("username"):
                        ret.result["hosts"][host_name]["username"] = clab_platform[
                            "username"
                        ]
                    if clab_platform.get("password"):
                        ret.result["hosts"][host_name]["password"] = clab_platform[
                            "password"
                        ]

        return ret

    @Task(fastapi={"methods": ["GET"]})
    def deploy_netbox(
        self,
        job: Job,
        lab_name: str = None,
        tenant: str = None,
        filters: Union[None, list] = None,
        devices: Union[None, list] = None,
        instance: str = None,
        image: str = None,
        ipv4_subnet: str = "172.100.100.0/24",
        ports: tuple = (12000, 15000),
        progress: bool = False,
        reconfigure: bool = False,
        timeout: int = 600,
        node_filter: Union[None, str] = None,
        dry_run: bool = False,
    ) -> Result:
        """
        Deploys a containerlab topology using device data from the Netbox database.

        This method orchestrates the deployment of a containerlab topology by:

        - Inspecting existing containers to determine subnets and ports in use.
        - Allocating a management IPv4 subnet for the new lab, avoiding conflicts.
        - Downloading inventory data from Netbox for the specified lab and filters.
        - Saving the generated topology file to a dedicated folder.
        - Executing the `containerlab deploy` command with appropriate arguments.

        To retrieve topology data from Netbox at least one of these arguments must be provided
        to identify a set of devices to include into Containerlab topology:

        - `tenant` - deploys lab using all devices and links that belong to this tenant
        - `devices` - lab deployed only using devices in the lists
        - `filters` - list of device filters to retrieve from Netbox

        If multiple of above arguments provided, resulting lab topology is a sum of all
        devices matched.

        Args:
            lab_name (str, optional): The name to use for the lab to deploy.
            tenant (str, optional): Deploy lab for given tenant, lab name if not set
                becomes equal to tenant name.
            filters (list, optional): List of filters to apply when fetching devices from Netbox.
            devices (list, optional): List of specific devices to include in the topology.
            instance (str, optional): Netbox instance identifier.
            image (str, optional): Container image to use for devices.
            ipv4_subnet (str, optional): Management IPv4 subnet for the lab.
            ports (tuple, optional): Tuple specifying the range of ports to allocate.
            progress (bool, optional): If True, emits progress events.
            reconfigure (bool, optional): If True, reconfigures an already deployed lab.
            timeout (int, optional): Timeout in seconds for the deployment process.
            node_filter (str, optional): Comma-separated string of nodes to deploy.
            dry_run (bool, optional): If True, only generates and returns the topology
                inventory without deploying.

        Returns:
            Result: deployment results with a list of nodes deployed

        Raises:
            Exception: If the topology file cannot be fetched.
        """
        timeout = timeout or 600
        ret = Result(task=f"{self.name}:deploy_netbox")
        subnets_in_use = set()
        ports_in_use = {}

        # handle lab name and tenant name
        if lab_name is None and tenant:
            lab_name = tenant

        # inspect existing containers
        job.event(f"Checking existing containers")
        get_containers = self.inspect(job=job, details=True)
        if get_containers.failed is True:
            get_containers.task = f"{self.name}:deploy_netbox"
            return get_containers

        # collect TCP/UDP ports and subnets in use
        job.event(f"Existing containers found, retrieving details")
        for lname, containers in get_containers.result.items():
            for container in containers:
                clab_name = container["Labels"]["containerlab"]
                clab_topo = container["Labels"]["clab-topo-file"]
                node_name = container["Labels"]["clab-node-name"]
                # collect ports that are in use
                ports_in_use[node_name] = list(
                    set(
                        [
                            f"{p['host_port']}:{p['port']}/{p['protocol']}"
                            for p in container["Ports"]
                            if "host_port" in p and "port" in p and "protocol" in p
                        ]
                    )
                )
                # check existing subnets
                if (
                    container["NetworkSettings"]["IPv4addr"]
                    and container["NetworkSettings"]["IPv4pLen"]
                ):
                    ip = ipaddress.ip_interface(
                        f"{container['NetworkSettings']['IPv4addr']}/"
                        f"{container['NetworkSettings']['IPv4pLen']}"
                    )
                    subnet = str(ip.network.with_prefixlen)
                else:
                    with open(clab_topo, encoding="utf-8") as f:
                        clab_topo_data = yaml.safe_load(f.read())
                        if clab_topo_data.get("mgmt", {}).get("ipv4-subnet"):
                            subnet = clab_topo_data["mgmt"]["ipv4-subnet"]
                        else:
                            msg = f"{clab_name} lab {node_name} node failed to determine mgmt subnet"
                            log.warning(msg)
                            job.event(msg, severity="WARNING")
                            continue
                subnets_in_use.add(subnet)
                # re-use existing lab subnet
                if clab_name == lab_name:
                    ipv4_subnet = subnet
                    job.event(
                        f"{ipv4_subnet} not in use by existing containers, using it"
                    )
                # allocate new subnet if its in use by other lab
                elif clab_name != lab_name and ipv4_subnet == subnet:
                    msg = f"{ipv4_subnet} already in use, allocating new subnet"
                    log.info(msg)
                    job.event(msg)
                    ipv4_subnet = None

        job.event(f"Collected TCP/UDP ports used by existing containers")

        # allocate new subnet
        if ipv4_subnet is None:
            pool = set(f"172.100.{i}.0/24" for i in range(100, 255))
            ipv4_subnet = list(sorted(pool.difference(subnets_in_use)))[0]
            job.event(f"{lab_name} allocated new subnet {ipv4_subnet}")

        job.event(f"{lab_name} fetching lab topology data from Netbox")

        # download inventory data from Netbox
        netbox_reply = self.client.run_job(
            service="netbox",
            task="get_containerlab_inventory",
            workers="any",
            timeout=timeout,
            retry=3,
            kwargs={
                "lab_name": lab_name,
                "tenant": tenant,
                "filters": filters,
                "devices": devices,
                "instance": instance,
                "image": image,
                "ipv4_subnet": ipv4_subnet,
                "ports": ports,
                "ports_map": ports_in_use,
                "progress": progress,
            },
        )

        # use inventory from first worker that returned hosts data
        for wname, wdata in netbox_reply.items():
            if wdata["failed"] is False and wdata["result"]:
                topology_inventory = wdata["result"]
                break
        else:
            msg = f"{self.name} - Netbox returned no data for '{lab_name}' lab"
            log.error(msg)
            raise RuntimeError(msg)

        job.event(f"{lab_name} topology data retrieved from Netbox")

        if dry_run is True:
            ret.result = topology_inventory
            return ret

        # create folder to store topology
        topology_folder = os.path.join(self.topologies_dir, lab_name)
        os.makedirs(topology_folder, exist_ok=True)

        # create topology file
        topology_file = os.path.join(topology_folder, f"{lab_name}.yaml")
        with open(topology_file, "w", encoding="utf-8") as tf:
            tf.write(yaml.dump(topology_inventory, default_flow_style=False))

        job.event(f"{lab_name} topology data saved to '{topology_file}'")

        return self.deploy(
            job=job,
            topology=topology_file,
            reconfigure=reconfigure,
            timeout=timeout,
            node_filter=node_filter or "",
        )
