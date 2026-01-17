import pprint
import time

CLAB_VERSION = None


def check_containerlab_worker(nfclient):
    workers = nfclient.get(
        "mmi.service.broker", "show_workers", kwargs={"service": "containerlab"}
    )
    print(f"Checking if containerlab worker running: {workers}")
    return any(w["name"] == "containerlab-worker-1" for w in workers["results"])


def check_netbox_worker(nfclient):
    workers = nfclient.get(
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


class TestWorker:
    def test_get_inventory(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret = nfclient.run_job("containerlab", "get_inventory")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert all(
                k in data["result"] for k in ["service"]
            ), f"{worker_name} inventory incomplete"

    def test_get_version(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret = nfclient.run_job("containerlab", "get_version")
        pprint.pprint(ret)

        assert isinstance(ret, dict), f"Expected dictionary but received {type(ret)}"
        for worker_name, version_report in ret.items():
            for package, version in version_report["result"].items():
                assert version != "", f"{worker_name}:{package} version is empty"

    def test_get_running_labs(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret = nfclient.run_job("containerlab", "get_running_labs")
        pprint.pprint(ret)

        assert isinstance(ret, dict), f"Expected dictionary but received {type(ret)}"
        for w, r in ret.items():
            assert r["failed"] == False, f"{w} - failed to get running labs"
            assert r["result"], f"{w} - result is empty"


class TestDeployTask:
    def test_deploy(self, nfclient):
        wait_for_containerlab_worker(nfclient)

        # destroy the lab first
        ret_labs = nfclient.run_job("containerlab", "get_running_labs")
        print("Running labs:")
        pprint.pprint(ret_labs)
        for worker_name, res in ret_labs.items():
            if "three-routers-lab" in res["result"]:
                ret_destroy = nfclient.run_job(
                    "containerlab",
                    "destroy_lab",
                    kwargs={"lab_name": "three-routers-lab"},
                    workers=worker_name,
                )

                print("Lab destroyed:")
                pprint.pprint(ret_destroy)

                for w, r in ret_destroy.items():
                    assert r["failed"] == False, f"{w} - failed to destroy lab"
                    assert (
                        r["result"]["three-routers-lab"] == True
                    ), f"{w} - worker did not destroy three-routers-lab lab"

        ret_deploy = nfclient.run_job(
            "containerlab",
            "deploy",
            kwargs={"topology": "nf://containerlab/three-routers-topology.yaml"},
        )

        print("Lab deployed:")
        pprint.pprint(ret_deploy)

        for w, r in ret_deploy.items():
            assert r["failed"] == False, f"{w} - failed to deploy lab"
            assert r["result"][
                "three-routers-lab"
            ], f"{w} - worker did not deploy three-routers-lab"
            assert (
                len(r["result"]["three-routers-lab"]) == 3
            ), f"{w} - worker did not deploy all three-routers-lab containers"

    def test_deploy_reconfigure(self, nfclient):
        wait_for_containerlab_worker(nfclient)

        ret_deploy = nfclient.run_job(
            "containerlab",
            "deploy",
            kwargs={
                "topology": "nf://containerlab/three-routers-topology.yaml",
                "reconfigure": True,
            },
        )

        print("Lab deployed:")
        pprint.pprint(ret_deploy)

        for w, r in ret_deploy.items():
            assert r["failed"] == False, f"{w} - failed to deploy lab"
            assert r["result"][
                "three-routers-lab"
            ], f"{w} - worker did not deploy three-routers-lab"
            assert (
                len(r["result"]["three-routers-lab"]) == 3
            ), f"{w} - worker did not deploy all three-routers-lab containers"

    def test_deploy_node_filter(self, nfclient):
        wait_for_containerlab_worker(nfclient)

        # destroy the lab first
        ret_labs = nfclient.run_job("containerlab", "get_running_labs")
        print("Running labs:")
        pprint.pprint(ret_labs)
        for worker_name, res in ret_labs.items():
            if "three-routers-lab" in res["result"]:
                ret_destroy = nfclient.run_job(
                    "containerlab",
                    "destroy_lab",
                    kwargs={"lab_name": "three-routers-lab"},
                    workers=worker_name,
                )

                print("Lab destroyed:")
                pprint.pprint(ret_destroy)

                for w, r in ret_destroy.items():
                    assert r["failed"] == False, f"{w} - failed to destroy lab"
                    assert (
                        r["result"]["three-routers-lab"] == True
                    ), f"{w} - worker did not destroy three-routers-lab lab"

        ret_deploy = nfclient.run_job(
            "containerlab",
            "deploy",
            kwargs={
                "topology": "nf://containerlab/three-routers-topology.yaml",
                "node_filter": "r1,r2",
            },
        )

        print("Lab destroyed:")
        pprint.pprint(ret_destroy)

        print("Lab deployed:")
        pprint.pprint(ret_deploy)

        for w, r in ret_destroy.items():
            assert r["failed"] == False, f"{w} - failed to destroy lab"
            assert (
                r["result"]["three-routers-lab"] == True
            ), f"{w} - worker did not destroy three-routers-lab lab"

        for w, r in ret_deploy.items():
            assert r["failed"] == False, f"{w} - failed to deploy lab"
            assert r["result"][
                "three-routers-lab"
            ], f"{w} - worker did not deploy three-routers-lab"
            assert (
                len(r["result"]["three-routers-lab"]) == 2
            ), f"{w} - worker did not deplpoy 2 containers"


class TestInspectTask:
    def test_inspect_all(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret = nfclient.run_job("containerlab", "inspect")
        pprint.pprint(ret)

        for w, r in ret.items():
            assert r["failed"] == False, f"{w} - failed to inspect labs"
            assert (
                len(list(r["result"].keys())) > 0
            ), f"{w} - no containerlab labs details returned"
            for lab_name, containers in r["result"].items():
                assert (
                    len(containers) > 0
                ), f"{w} - no container {lab_name} lab has no containers"

    def test_inspect_by_lab_name(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret = nfclient.run_job(
            "containerlab", "inspect", kwargs={"lab_name": "three-routers-lab"}
        )
        pprint.pprint(ret)

        for w, r in ret.items():
            assert r["failed"] == False, f"{w} - failed to inspect labs"
            assert (
                len(list(r["result"].keys())) > 0
            ), f"{w} - no containerlab labs details returned"
            assert all(
                "clab-three-routers" in cntr["name"]
                for cntr in r["result"]["three-routers-lab"]
            ), f"{w} - did not filter container by lab name properly"

    def test_inspect_details(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret = nfclient.run_job(
            "containerlab",
            "inspect",
            kwargs={"lab_name": "three-routers-lab", "details": True},
        )
        pprint.pprint(ret)

        for w, r in ret.items():
            assert r["failed"] == False, f"{w} - failed to inspect labs"
            assert len(r["result"]) > 0, f"{w} - no container details returned"
            assert (
                len(list(r["result"].keys())) > 0
            ), f"{w} - no containerlab labs details returned"
            for lab_name, containers in r["result"].items():
                assert (
                    len(containers) > 0
                ), f"{w} - no container {lab_name} lab has no containers"
                assert all(
                    k in containers[0]
                    for k in ["ID", "Labels", "Mounts", "Names", "NetworkSettings"]
                ), f"{w} - no container missing details, lab {lab_name}"

    def test_inspect_nonexist_lab(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret = nfclient.run_job(
            "containerlab", "inspect", kwargs={"lab_name": "nonexist"}
        )
        pprint.pprint(ret)

        for w, r in ret.items():
            assert r["failed"] == True, f"{w} - should have failed"


class TestSaveTask:
    def test_save(self, nfclient):
        wait_for_containerlab_worker(nfclient)

        ret_deploy = nfclient.run_job(
            "containerlab",
            "deploy",
            kwargs={
                "topology": "nf://containerlab/three-routers-topology.yaml",
                "reconfigure": True,
            },
        )

        ret = nfclient.run_job(
            "containerlab", "save", kwargs={"lab_name": "three-routers-lab"}
        )

        print("Ret deploy:")
        pprint.pprint(ret_deploy)

        print("Ret save:")
        pprint.pprint(ret)

        for w, r in ret.items():
            assert r["failed"] == False, f"{w} - failed to save lab"
            assert (
                r["result"]["three-routers-lab"] == True
            ), f"{w} - failed to save lab three-routers-lab"

    def test_save_nonexistlab(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret = nfclient.run_job("containerlab", "save", kwargs={"lab_name": "nonexist"})
        pprint.pprint(ret)

        for w, r in ret.items():
            assert r["failed"] == True, f"{w} - should have failed to save lab"


class TestRestartTask:
    def test_restart(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret = nfclient.run_job(
            "containerlab", "restart_lab", kwargs={"lab_name": "three-routers-lab"}
        )
        pprint.pprint(ret)

        for w, r in ret.items():
            assert r["failed"] == False, f"{w} - failed to restart lab"
            assert (
                r["result"]["three-routers-lab"] == True
            ), f"{w} - failed to restart lab three-routers-lab"

    def test_restart_nonexist_lab(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret = nfclient.run_job(
            "containerlab", "restart_lab", kwargs={"lab_name": "nonexist"}
        )
        pprint.pprint(ret)

        for w, r in ret.items():
            assert r["failed"] == True, f"{w} - should have failed to restart lab"


class TestGetNornirInventoryTask:
    def test_get_nornir_inventory_by_lab_name(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret_deploy = nfclient.run_job(
            "containerlab",
            "deploy",
            kwargs={
                "topology": "nf://containerlab/three-routers-topology.yaml",
                "reconfigure": True,
            },
        )
        ret_inventory = nfclient.run_job(
            "containerlab",
            "get_nornir_inventory",
            kwargs={"lab_name": "three-routers-lab", "groups": ["g1", "g2"]},
        )

        print("Lab deployed:")
        pprint.pprint(ret_deploy)

        print("Lab Nornir Inventory generated:")
        pprint.pprint(ret_inventory)

        for w, r in ret_deploy.items():
            assert r["failed"] == False, f"{w} - failed to re-deploy lab"
            assert r["result"][
                "three-routers-lab"
            ], f"{w} - worker did not re-deploy all three-routers-lab containers"

        for w, r in ret_inventory.items():
            assert r["failed"] == False, f"{w} - failed to get lab Nornir inventory"
            assert all(
                k in r["result"]["hosts"] for k in ["r1", "r2", "r3"]
            ), f"{w} - failed to get inventory for all devices"
            for h, i in r["result"]["hosts"].items():
                assert all(
                    k in i
                    for k in [
                        "groups",
                        "hostname",
                        "password",
                        "platform",
                        "port",
                        "username",
                    ]
                ), f"{w}:{h} - inventory incomplete"
                assert i["groups"] == ["g1", "g2"], f"{w}:{h} - groups content wrong"

    def test_get_nornir_inventory_all_labs(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret_deploy = nfclient.run_job(
            "containerlab",
            "deploy",
            kwargs={
                "topology": "nf://containerlab/three-routers-topology.yaml",
                "reconfigure": True,
            },
        )
        ret_inventory = nfclient.run_job(
            "containerlab", "get_nornir_inventory", kwargs={"groups": ["g1", "g2"]}
        )

        print("Lab deployed:")
        pprint.pprint(ret_deploy)

        print("Lab Nornir Inventory generated:")
        pprint.pprint(ret_inventory)

        for w, r in ret_deploy.items():
            assert r["failed"] == False, f"{w} - failed to re-deploy lab"
            assert r["result"][
                "three-routers-lab"
            ], f"{w} - worker did not re-deploy all three-routers-lab containers"

        for w, r in ret_inventory.items():
            assert r["failed"] == False, f"{w} - failed to get lab Nornir inventory"
            assert all(
                k in r["result"]["hosts"] for k in ["r1", "r2", "r3"]
            ), f"{w} - failed to get inventory for all devices"
            for h, i in r["result"]["hosts"].items():
                assert all(
                    k in i
                    for k in [
                        "groups",
                        "hostname",
                        "password",
                        "platform",
                        "port",
                        "username",
                    ]
                ), f"{w}:{h} - inventory incomplete"
                assert i["groups"] == ["g1", "g2"], f"{w}:{h} - groups content wrong"

    def test_get_nornir_inventory_nonexisting_lab_name(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret_inventory = nfclient.run_job(
            "containerlab", "get_nornir_inventory", kwargs={"lab_name": "notexist"}
        )

        print("Lab Nornir Inventory generated:")
        pprint.pprint(ret_inventory)

        for w, r in ret_inventory.items():
            assert (
                r["failed"] == True
            ), f"{w} - inventory retrieval for non existing lab should fail"
            assert r["result"] == {
                "hosts": {}
            }, f"{w} - inventory should contain no hosts"


class TestDeployNetboxTask:
    def test_deploy_netbox(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        wait_for_netbox_worker(nfclient)

        # destroy the lab first
        ret_labs = nfclient.run_job("containerlab", "get_running_labs")
        print("Running labs:")
        pprint.pprint(ret_labs)
        for worker_name, res in ret_labs.items():
            if "foobar" in res["result"]:
                ret_destroy = nfclient.run_job(
                    "containerlab",
                    "destroy_lab",
                    kwargs={"lab_name": "foobar"},
                    workers=worker_name,
                )

                print("Lab destroyed:")
                pprint.pprint(ret_destroy)

                for w, r in ret_destroy.items():
                    assert r["failed"] == False, f"{w} - failed to destroy lab"
                    assert (
                        r["result"]["foobar"] == True
                    ), f"{w} - worker did not destroy foobar lab"

        ret_deploy = nfclient.run_job(
            "containerlab",
            "deploy_netbox",
            kwargs={"lab_name": "foobar", "devices": ["fceos4", "fceos5"]},
        )

        print("Lab deployed from Netbox:")
        pprint.pprint(ret_deploy)

        for w, r in ret_deploy.items():
            assert r["failed"] == False, f"{w} - failed to deploy lab"
            assert (
                len(r["result"]["foobar"]) == 2
            ), f"{w} - worker did not deploy foobar containers"

    def test_deploy_netbox_reconfigure(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        wait_for_netbox_worker(nfclient)
        ret_deploy = nfclient.run_job(
            "containerlab",
            "deploy_netbox",
            kwargs={
                "lab_name": "foobar",
                "devices": ["fceos4", "fceos5"],
                "reconfigure": True,
            },
        )

        print("Lab deployed from Netbox:")
        pprint.pprint(ret_deploy)

        for w, r in ret_deploy.items():
            assert r["failed"] == False, f"{w} - failed to deploy lab"
            assert (
                len(r["result"]["foobar"]) == 2
            ), f"{w} - worker did not deploy foobar containers"

    def test_deploy_netbox_node_filter(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        wait_for_netbox_worker(nfclient)

        # destroy the lab first
        ret_labs = nfclient.run_job("containerlab", "get_running_labs")
        print("Running labs:")
        pprint.pprint(ret_labs)
        for worker_name, res in ret_labs.items():
            if "foobar" in res["result"]:
                ret_destroy = nfclient.run_job(
                    "containerlab",
                    "destroy_lab",
                    kwargs={"lab_name": "foobar"},
                    workers=worker_name,
                )

                print("Lab destroyed:")
                pprint.pprint(ret_destroy)

                for w, r in ret_destroy.items():
                    assert r["failed"] == False, f"{w} - failed to destroy lab"
                    assert (
                        r["result"]["foobar"] == True
                    ), f"{w} - worker did not destroy foobar lab"

        ret_deploy = nfclient.run_job(
            "containerlab",
            "deploy_netbox",
            kwargs={
                "lab_name": "foobar",
                "devices": ["fceos4", "fceos5"],
                "node_filter": "fceos4",
            },
        )

        print("Lab deployed from Netbox:")
        pprint.pprint(ret_deploy)

    def test_deploy_netbox_with_nb_filters(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        wait_for_netbox_worker(nfclient)

        # destroy the lab first
        ret_labs = nfclient.run_job("containerlab", "get_running_labs")
        print("Running labs:")
        pprint.pprint(ret_labs)
        for worker_name, res in ret_labs.items():
            if "foobar" in res["result"]:
                ret_destroy = nfclient.run_job(
                    "containerlab",
                    "destroy_lab",
                    kwargs={"lab_name": "foobar"},
                    workers=worker_name,
                )

                print("Lab destroyed:")
                pprint.pprint(ret_destroy)

                for w, r in ret_destroy.items():
                    assert r["failed"] == False, f"{w} - failed to destroy lab"
                    assert (
                        r["result"]["foobar"] == True
                    ), f"{w} - worker did not destroy foobar lab"

        ret_deploy = nfclient.run_job(
            "containerlab",
            "deploy_netbox",
            kwargs={
                "lab_name": "foobar",
                "filters": [
                    {
                        "tenant": '{name: {exact: "NORFAB"}}',
                        "name": '{i_contains: "spine"}',
                    }
                ],
            },
        )

        print("Lab deployed from Netbox:")
        pprint.pprint(ret_deploy)

        for w, r in ret_deploy.items():
            assert r["failed"] == False, f"{w} - failed to deploy lab"
            assert (
                len(r["result"]["foobar"]) == 2
            ), f"{w} - worker did not deploy correct number of foobar lab containers"
