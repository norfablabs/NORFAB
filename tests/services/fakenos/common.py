NET1_INVENTORY = "nf://fakenos/net1.yaml"
NET2_INVENTORY = "nf://fakenos/net2.yaml"


def _stop_all_networks(nfclient):
    """Stop all running FakeNOS networks on every worker."""
    nfclient.run_job("fakenos", "stop")


def _start_network(nfclient, network, inventory):
    """Start a FakeNOS network and return the raw result."""
    return nfclient.run_job(
        "fakenos",
        "start",
        kwargs={"network": network, "inventory": inventory},
    )


# ----------------------------------------------------------------------------
# FAKENOS WORKER TESTS
# ----------------------------------------------------------------------------
