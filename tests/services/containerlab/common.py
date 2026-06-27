import time

CLAB_VERSION = None


def check_containerlab_worker(nfclient):
    workers = nfclient.mmi(
        "mmi.service.broker", "show_workers", kwargs={"service": "containerlab"}
    )
    print(f"Checking if containerlab worker running: {workers}")
    return any(w["name"] == "containerlab-worker-1" for w in workers["results"])


def check_netbox_worker(nfclient):
    workers = nfclient.mmi(
        "mmi.service.broker", "show_workers", kwargs={"service": "netbox"}
    )
    print(f"Checking if netbox worker running: {workers}")
    return any(w["name"] == "netbox-worker-1.1" for w in workers["results"])


def wait_for_containerlab_worker(nfclient, timer=10):
    global CLAB_VERSION
    begin = time.time()
    while (time.time() - begin) < timer:
        if check_containerlab_worker(nfclient) is True:
            break
        time.sleep(1)
    else:
        raise TimeoutError(
            f"Containerlab worker did not come online within {timer} seconds"
        )
    # fetch containerlab version
    ret = nfclient.run_job("containerlab", "get_version")
    wname, wres = tuple(ret.items())[0]
    CLAB_VERSION = [int(i) for i in wres["result"]["containerlab"].split(".")]
    print(f"CLAB_VERSION: {CLAB_VERSION}")


def wait_for_netbox_worker(nfclient, timer=10):
    begin = time.time()
    while (time.time() - begin) < timer:
        if check_netbox_worker(nfclient) is True:
            break
        time.sleep(1)
    else:
        raise TimeoutError(f"Netbox worker did not come online within {timer} seconds")
