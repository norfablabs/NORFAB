from nornir.core.inventory import Host
from nornir.core.task import Result


def run(result: Result, host: Host) -> dict:
    """Compare IOS LLDP neighbors with loaded NetBox connection records.

    Args:
        result: Result containing raw ``show lldp neighbors detail`` output.
        host: Nornir host with point-to-point Ethernet connections in its data.

    Returns:
        dict: PASS or FAIL with details of missing, extra, or incorrect neighbors.
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
        return {
            "result": "FAIL",
            "success": False,
            "exception": "No Ethernet connection records loaded in host data",
        }
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
    differences = [
        f"{port}: expected {neighbors}, observed {observed[port]}"
        for port, neighbors in expected.items()
        if observed[port] != neighbors
    ]
    return {
        "result": "FAIL" if differences else "PASS",
        "success": not differences,
        "exception": "; ".join(differences) if differences else None,
    }
