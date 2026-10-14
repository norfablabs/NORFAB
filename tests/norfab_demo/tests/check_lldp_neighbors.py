from nornir.core.inventory import Host
from nornir.core.task import Result


def run(result: Result, host: Host) -> list[dict]:
    """Compare IOS LLDP neighbors with loaded NetBox connection records.

    Args:
        result: Result containing raw ``show lldp neighbors detail`` output.
        host: Nornir host with point-to-point Ethernet connections in its data.

    Returns:
        list[dict]: One PASS or FAIL dictionary per inventory link, with
            ``name``, ``result``, ``success``, and ``exception`` keys. The name
            identifies the local and expected remote endpoints. Failed links include
            details of missing, extra, or incorrect neighbors. If no links are
            loaded, returns a list containing one failure dictionary.
            Only inventory-connected Ethernet ports are checked; management
            neighbors on other ports are ignored. IOS Et port abbreviations and
            DNS suffixes in system names are normalized. Breakout links and
            non-Ethernet connections are outside this demo's scope.
    """
    expected = {
        port: [(connection["remote_device"], connection["remote_interface"])]
        for port, connection in host.data.get("connections", {}).items()
        if port.startswith("Ethernet")
        and "." not in port
        and connection.get("remote_device")
    }
    if not expected:
        return [
            {
                "name": f"LLDP peer check for {host.name}: no inventory links",
                "result": "FAIL",
                "success": False,
                "exception": "No Ethernet connection records loaded in host data",
            }
        ]
    observed = {port: [] for port in expected}
    for block in result.result.split("Local Intf: ")[1:]:
        local = block.splitlines()[0].strip()
        fields = dict(
            line.split(": ", 1)
            for line in block.splitlines()
            if line.startswith(("Port id: ", "System Name: "))
        )
        if not local:
            continue
        port = "Ethernet" + local[2:] if local.startswith("Et0/") else local
        if port in observed:
            remote = fields.get("Port id", "<missing port id>").strip()
            device = fields.get("System Name", "<missing system name>").strip()
            observed[port].append(
                (
                    device.split(".")[0],
                    "Ethernet" + remote[2:] if remote.startswith("Et0/") else remote,
                )
            )
    return [
        {
            "name": (
                f"LLDP peer check for {host.name}:{port} connected to "
                f"{neighbors[0][0]}:{neighbors[0][1]}"
            ),
            "result": "PASS" if observed[port] == neighbors else "FAIL",
            "success": observed[port] == neighbors,
            "exception": (
                f"{port}: expected {neighbors}, observed {observed[port]}"
                if observed[port] != neighbors
                else None
            ),
        }
        for port, neighbors in expected.items()
    ]
