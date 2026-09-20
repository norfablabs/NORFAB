"""Exercise FakeNOS parsing and record process file descriptor counts."""

import argparse
import csv
import time
from pathlib import Path

from norfab.core.client import NFPClient
from norfab.core.inventory import NorFabInventory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=120)
    parser.add_argument("--interval", type=float, default=0)
    args = parser.parse_args()
    if args.duration <= 0 or args.interval < 0:
        parser.error("duration must be positive and interval must be non-negative")

    inventory = NorFabInventory(
        path="/workspace/tests/nf_tests_inventory/inventory.yaml"
    )
    client = NFPClient(inventory, inventory.broker["endpoint"], "fd-profile-client")
    output = Path(inventory.base_dir) / "__norfab__" / "artifacts" / "fd-profile.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    hosts = ["fn-ceos-lf-1", "fn-ceos-lf-2"]
    failures = 0
    try:
        for _ in range(10):
            warmup = client.run_job(
                "nornir",
                "parse_ttp",
                workers=["nornir-worker-4"],
                kwargs={"get": "vrrp", "FL": hosts},
                timeout=60,
            )
            if warmup and all(not item["failed"] for item in warmup.values()):
                break
            time.sleep(2)
        else:
            raise RuntimeError(f"FakeNOS parsing did not become ready: {warmup}")
        started = time.monotonic()
        with output.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=[
                    "elapsed_seconds",
                    "iteration",
                    "broker_fds",
                    "worker_fds",
                    "client_fds",
                    "failed",
                ],
            )
            writer.writeheader()
            iteration = 0
            while time.monotonic() - started < args.duration:
                iteration += 1
                result = client.run_job(
                    "nornir",
                    "parse_ttp",
                    workers=["nornir-worker-4"],
                    kwargs={"get": "vrrp", "FL": hosts},
                    timeout=60,
                )
                failed = not result or any(item["failed"] for item in result.values())
                failures += failed
                broker = client.mmi("mmi.service.broker", "get_stats")["results"]
                worker = client.run_job(
                    "nornir",
                    "get_stats",
                    workers=["nornir-worker-4"],
                    timeout=30,
                )["nornir-worker-4"]["result"]
                writer.writerow(
                    {
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                        "iteration": iteration,
                        "broker_fds": broker["process"]["open_file_descriptors"],
                        "worker_fds": worker["process"]["open_file_descriptors"],
                        "client_fds": client.get_stats()["process"][
                            "open_file_descriptors"
                        ],
                        "failed": failed,
                    }
                )
                stream.flush()
                if args.interval:
                    time.sleep(args.interval)
        print(
            f"Completed {iteration} parse_ttp jobs; failures: {failures}; CSV: {output}"
        )
        return 1 if failures else 0
    finally:
        client.destroy()


if __name__ == "__main__":
    raise SystemExit(main())
