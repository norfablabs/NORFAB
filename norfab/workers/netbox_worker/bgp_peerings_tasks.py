import ipaddress
import logging
from enum import Enum
from typing import List, Union

import pynetbox
from deepdiff import DeepDiff
from pydantic import Field, StrictInt

from norfab.core.worker import Job, Task
from norfab.models import Result

from .netbox_models import NetboxCommonArgs, NetboxFastApiArgs

log = logging.getLogger(__name__)


class BgpSessionStatusEnum(str, Enum):
    active = "active"
    planned = "planned"
    maintenance = "maintenance"
    offline = "offline"
    decommissioned = "decommissioned"


class CreateBgpPeeringsInput(NetboxCommonArgs, use_enum_values=True):
    devices: Union[None, List] = Field(
        None,
        description="List of device names to create BGP peerings for",
    )
    status: BgpSessionStatusEnum = Field(
        "active",
        description="Status to set on created/updated BGP sessions",
    )
    process_deletions: bool = Field(
        False,
        description="Delete BGP sessions present in NetBox but not found on the device",
    )
    timeout: StrictInt = Field(
        60,
        description="Timeout in seconds for Nornir parse_ttp job",
    )
    batch_size: StrictInt = Field(
        10,
        description="Number of devices to process per Nornir batch",
    )
    rir: Union[None, str] = Field(
        None,
        description="RIR name to use when creating new ASNs in NetBox (e.g. 'RFC 1918', 'ARIN')",
    )


class NetboxBgpPeeringsTasks:

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_bgp_peerings(
        self,
        job: Job,
        instance: Union[None, str] = None,
        devices: Union[None, list] = None,
        cache: Union[None, bool, str] = None,
    ) -> Result:
        """
        Retrieve device BGP peerings from Netbox using REST API.

        Args:
            job: NorFab Job object containing relevant metadata
            instance (str, optional): Netbox instance name.
            devices (list, optional): List of devices to retrieve BGP peerings for.
            cache (Union[bool, str], optional): Cache usage options:

                - True: Use data stored in cache if it is up to date, refresh it otherwise.
                - False: Do not use cache and do not update cache.
                - refresh: Ignore data in cache and replace it with data fetched from Netbox.
                - force: Use data in cache without checking if it is up to date.

        Returns:
            dict: Dictionary keyed by device name with BGP peerings details.

        Example return data for single bgp peering - same data as returned by Netbox built-in REST
        API explorer:

        ```
        "fceos4-fceos5-eth105": {
            "comments": "",
            "created": "2026-04-08T10:29:13.404863Z",
            "custom_fields": {},
            "description": "BGP peering between fceos4 and fceos5 on eth105",
            "device": {
                "description": "",
                "display": "fceos4 (UUID-123451)",
                "id": 119,
                "name": "fceos4",
                "url": "http://netbox.lab:8000/api/dcim/devices/119/"
            },
            "display": "fceos4 (UUID-123451):fceos4-fceos5-eth105",
            "export_policies": [
                {
                    "description": "",
                    "display": "RPL1",
                    "id": 1,
                    "name": "RPL1",
                    "url": "http://netbox.lab:8000/api/plugins/bgp/routing-policy/1/"
                }
            ],
            "id": 7,
            "import_policies": [
                {
                    "description": "",
                    "display": "RPL1",
                    "id": 1,
                    "name": "RPL1",
                    "url": "http://netbox.lab:8000/api/plugins/bgp/routing-policy/1/"
                }
            ],
            "last_updated": "2026-04-18T21:39:38.947199Z",
            "local_address": {
                "address": "10.0.2.1/30",
                "description": "",
                "display": "10.0.2.1/30",
                "family": {
                    "label": "IPv4",
                    "value": 4
                },
                "id": 489,
                "url": "http://netbox.lab:8000/api/ipam/ip-addresses/489/"
            },
            "local_as": {
                "asn": 65100,
                "description": "BGP ASN for fceos4",
                "display": "AS65100",
                "id": 3,
                "url": "http://netbox.lab:8000/api/ipam/asns/3/"
            },
            "name": "fceos4-fceos5-eth105",
            "peer_group": {
                "description": "Test BGP peer group 1 for standard peerings",
                "display": "TEST_BGP_PEER_GROUP_1",
                "id": 3,
                "name": "TEST_BGP_PEER_GROUP_1",
                "url": "http://netbox.lab:8000/api/plugins/bgp/bgppeergroup/3/"
            },
            "prefix_list_in": {
                "description": "",
                "display": "PFL1",
                "id": 1,
                "name": "PFL1",
                "url": "http://netbox.lab:8000/api/plugins/bgp/prefix-list/1/"
            },
            "prefix_list_out": {
                "description": "",
                "display": "PFL1",
                "id": 1,
                "name": "PFL1",
                "url": "http://netbox.lab:8000/api/plugins/bgp/prefix-list/1/"
            },
            "remote_address": {
                "address": "10.0.2.2/30",
                "description": "",
                "display": "10.0.2.2/30",
                "family": {
                    "label": "IPv4",
                    "value": 4
                },
                "id": 490,
                "url": "http://netbox.lab:8000/api/ipam/ip-addresses/490/"
            },
            "remote_as": {
                "asn": 65101,
                "description": "BGP ASN for fceos5",
                "display": "AS65101",
                "id": 4,
                "url": "http://netbox.lab:8000/api/ipam/asns/4/"
            },
            "site": {
                "description": "",
                "display": "SALTNORNIR-LAB",
                "id": 13,
                "name": "SALTNORNIR-LAB",
                "slug": "saltnornir-lab",
                "url": "http://netbox.lab:8000/api/dcim/sites/13/"
            },
            "status": {
                "label": "Active",
                "value": "active"
            },
            "tags": [],
            "tenant": {
                "description": "",
                "display": "SALTNORNIR",
                "id": 10,
                "name": "SALTNORNIR",
                "slug": "saltnornir",
                "url": "http://netbox.lab:8000/api/tenancy/tenants/10/"
            },
            "url": "http://netbox.lab:8000/api/plugins/bgp/bgpsession/7/",
            "virtualmachine": null
        }
        ```
        """
        instance = instance or self.default_instance
        devices = devices or []
        log.info(
            f"{self.name} - Get BGP peerings: Fetching BGP peerings for {len(devices)} device(s) from '{instance}' Netbox"
        )
        cache = self.cache_use if cache is None else cache
        ret = Result(
            task=f"{self.name}:get_bgp_peerings",
            result={d: {} for d in devices},
            resources=[instance],
        )

        # Check if BGP plugin is installed
        if not self.has_plugin("netbox_bgp", instance, strict=True):
            ret.errors.append(f"{instance} Netbox instance has no BGP Plugin installed")
            ret.failed = True
            return ret

        self.cache.expire()

        # Get device details to collect device IDs
        devices_result = self.get_devices(
            job=job, devices=devices, instance=instance, cache=False
        )
        if devices_result.errors:
            ret.errors.append(
                f"Failed to retrieve device details: {devices_result.errors}"
            )
            return ret

        nb = self._get_pynetbox(instance)

        for device_name in devices:
            # Skip devices not found in Netbox
            if device_name not in devices_result.result:
                msg = f"Device '{device_name}' not found in Netbox"
                job.event(msg, resource=instance, severity="WARNING")
                log.warning(msg)
                continue

            device_id = devices_result.result[device_name]["id"]
            cache_key = f"get_bgp_peerings::{device_name}"
            cached_data = self.cache.get(cache_key)

            # Mode: force with cached data - use cache directly
            if cache == "force" and cached_data is not None:
                ret.result[device_name] = cached_data
                job.event(
                    f"using cached BGP peerings for '{device_name}' (forced)",
                    resource=instance,
                )
                continue

            # Mode: cache disabled - fetch without caching
            if cache is False:
                bgp_sessions = nb.plugins.bgp.session.filter(device_id=device_id)
                ret.result[device_name] = {s.name: dict(s) for s in bgp_sessions}
                job.event(
                    f"retrieved {len(ret.result[device_name])} BGP session(s) for '{device_name}'",
                    resource=instance,
                )
                continue

            # Mode: refresh or no cached data - fetch and cache
            if cache == "refresh" or cached_data is None:
                if cache == "refresh" and cached_data is not None:
                    self.cache.delete(cache_key, retry=True)
                bgp_sessions = nb.plugins.bgp.session.filter(device_id=device_id)
                ret.result[device_name] = {s.name: dict(s) for s in bgp_sessions}
                self.cache.set(
                    cache_key, ret.result[device_name], expire=self.cache_ttl
                )
                job.event(
                    f"fetched and cached {len(ret.result[device_name])} BGP session(s) for '{device_name}'",
                    resource=instance,
                )
                continue

            # Mode: cache=True with cached data - smart update (only fetch changed sessions)
            ret.result[device_name] = dict(cached_data)
            job.event(
                f"retrieved {len(cached_data)} BGP session(s) from cache for '{device_name}'",
                resource=instance,
            )

            # Fetch brief session info to compare timestamps
            brief_sessions = nb.plugins.bgp.session.filter(
                device_id=device_id, fields="id,last_updated,name"
            )
            netbox_sessions = {
                s.id: {"name": s.name, "last_updated": s.last_updated}
                for s in brief_sessions
            }

            # Build lookup maps
            cached_by_id = {s["id"]: name for name, s in cached_data.items()}
            session_ids_to_fetch = []
            sessions_to_remove = []

            # Find stale sessions (exist in both but timestamps differ) and deleted sessions
            for session_name, cached_session in cached_data.items():
                cached_id = cached_session["id"]
                if cached_id in netbox_sessions:
                    if (
                        cached_session["last_updated"]
                        != netbox_sessions[cached_id]["last_updated"]
                    ):
                        session_ids_to_fetch.append(cached_id)
                else:
                    sessions_to_remove.append(session_name)

            # Find new sessions in Netbox not in cache
            for nb_id in netbox_sessions:
                if nb_id not in cached_by_id:
                    session_ids_to_fetch.append(nb_id)

            # Remove deleted sessions
            for session_name in sessions_to_remove:
                ret.result[device_name].pop(session_name, None)
                job.event(
                    f"removed deleted session '{session_name}' from cache for '{device_name}'",
                    resource=instance,
                )

            # Fetch updated/new sessions
            if session_ids_to_fetch:
                job.event(
                    f"fetching {len(session_ids_to_fetch)} updated BGP session(s) for '{device_name}'",
                    resource=instance,
                )
                for session in nb.plugins.bgp.session.filter(id=session_ids_to_fetch):
                    ret.result[device_name][session.name] = dict(session)

            # Update cache if any changes occurred
            if session_ids_to_fetch or sessions_to_remove:
                self.cache.set(
                    cache_key, ret.result[device_name], expire=self.cache_ttl
                )
                job.event(f"updated cache for '{device_name}'", resource=instance)
            else:
                job.event(
                    f"using cache, it is up to date for '{device_name}'",
                    resource=instance,
                )

        return ret

    def _build_dataset_diff(
        self,
        source_data: dict,
        target_data: dict,
    ) -> dict:
        """
        Compare two flat dicts of items and categorise them using DeepDiff tree view.

        Args:
            source_data: dict keyed by item name with item dicts as values (live/device data).
            target_data: dict keyed by item name with item dicts as values (existing/netbox data).

        Returns:
            dict with keys ``missing_in_target``, ``missing_in_source``, ``needs_update``, ``in_sync``.
            ``needs_update`` is keyed by item name with ``{field: {"old_value": t1, "new_value": t2}}``.
        """
        # t1=target (netbox), t2=source (device live data)
        diff = DeepDiff(target_data, source_data, ignore_order=True, view="tree", threshold_to_diff_deeper=0)

        missing_in_target = []  # in source but absent in target → create
        missing_in_source = []  # in target but absent in source → delete
        needs_update = {}

        for item in diff.get("dictionary_item_added", []):
            path = item.path(output_format="list")
            if len(path) == 1:
                missing_in_target.append(path[0])

        for item in diff.get("dictionary_item_removed", []):
            path = item.path(output_format="list")
            if len(path) == 1:
                missing_in_source.append(path[0])

        for item in diff.get("values_changed", []):
            path = item.path(output_format="list")
            if len(path) == 2:
                sname, field = path
                needs_update.setdefault(sname, {})[field] = {
                    "old_value": item.t1,
                    "new_value": item.t2,
                }

        common = set(source_data.keys()) & set(target_data.keys())
        in_sync = sorted(name for name in common if name not in needs_update)

        return {
            "missing_in_target": sorted(missing_in_target),
            "missing_in_source": sorted(missing_in_source),
            "needs_update": needs_update,
            "in_sync": in_sync,
        }

    @Task(fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()})
    def create_bgp_peerings(
        self,
        job: Job,
        instance: Union[None, str] = None,
        devices: Union[None, list] = None,
        status: str = "active",
        dry_run: bool = False,
        process_deletions: bool = False,
        timeout: int = 60,
        batch_size: int = 10,
        branch: str = None,
        rir: str = None,
        **kwargs,
    ) -> Result:
        """
        Synchronise BGP sessions between live devices and NetBox.

        Collects BGP session data from devices via Nornir ``parse_ttp`` with
        ``get="bgp_neighbors"``, compares against existing NetBox BGP sessions and
        creates, updates, or (optionally) deletes sessions in NetBox accordingly.

        Args:
            job: NorFab Job object.
            instance (str, optional): NetBox instance name.
            devices (list, optional): List of device names to process.
            status (str): Status to assign to created/updated sessions when not ``established`` on device.
            dry_run (bool): If True, return diff report without writing to NetBox.
            process_deletions (bool): If True, delete NetBox sessions not found on device.
            timeout (int): Timeout in seconds for Nornir ``parse_ttp`` job.
            batch_size (int): Devices per Nornir batch (reserved for future use).
            branch (str, optional): NetBox branching plugin branch name.
            rir (str, optional): RIR name to use when creating new ASNs in NetBox (e.g. ``RFC 1918``, ``ARIN``).
            **kwargs: Nornir host filters (e.g. ``FC``, ``FL``, ``FB``).

        Returns:
            Normal run result keyed by device name::

                {
                    "<device>": {
                        "created": ["<session_name>", ...],
                        "updated": ["<session_name>", ...],
                        "deleted": ["<session_name>", ...],
                        "skipped": ["<session_name>", ...],
                    }
                }

            Dry-run result keyed by device name::

                {
                    "<device>": {
                        "missing_in_netbox": ["<session_name>", ...],
                        "missing_on_device": ["<session_name>", ...],
                        "needs_update": {"<session_name>": <deepdiff_delta>, ...},
                        "in_sync": ["<session_name>", ...],
                    }
                }
        """
        instance = instance or self.default_instance
        devices = devices or []
        ret = Result(
            task=f"{self.name}:create_bgp_peerings",
            result={},
            resources=[instance],
        )

        # Validate BGP plugin
        if not self.has_plugin("netbox_bgp", instance, strict=True):
            ret.errors.append(f"'{instance}' NetBox instance has no BGP plugin installed")
            ret.failed = True
            return ret

        # Source additional devices from Nornir filters
        if kwargs:
            nornir_hosts = self.get_nornir_hosts(kwargs, timeout)
            for host in nornir_hosts:
                if host not in devices:
                    devices.append(host)

        if not devices:
            ret.errors.append("no devices specified")
            ret.failed = True
            return ret

        log.info(
            f"{self.name} - Create BGP peerings: processing {len(devices)} device(s) in '{instance}'"
        )

        # Fetch existing NetBox BGP sessions
        nb_sessions_result = self.get_bgp_peerings(
            job=job, instance=instance, devices=devices, cache=True
        )
        if nb_sessions_result.errors:
            ret.errors.extend(nb_sessions_result.errors)
            ret.failed = True
            return ret

        # Fetch live BGP data from devices via Nornir parse_ttp
        job.event(f"fetching BGP session data from {len(devices)} device(s) via Nornir parse_ttp")
        parse_data = self.client.run_job(
            "nornir",
            "parse_ttp",
            kwargs={"get": "bgp_neighbors", "FL": devices},
            workers="all",
            timeout=timeout,
        )

        # Build per-device diff
        diff_results = {}
        for device_name in devices:
            # Normalise NetBox sessions
            nb_raw = nb_sessions_result.result.get(device_name, {})
            normalised_nb = {}
            for sname, nb_session in nb_raw.items():
                try:
                    normalised_nb[sname] = {
                        "name":            nb_session["name"],
                        "description":     nb_session.get("description") or "",
                        "local_address":   nb_session["local_address"]["address"].split("/")[0],
                        "local_as":        str(nb_session["local_as"]["asn"]),
                        "remote_address":  nb_session["remote_address"]["address"].split("/")[0],
                        "remote_as":       str(nb_session["remote_as"]["asn"]),
                        "vrf":             nb_session["vrf"]["name"] if nb_session.get("vrf") else None,
                        "status":          nb_session["status"]["value"],
                        "peer_group":      nb_session["peer_group"]["name"] if nb_session.get("peer_group") else None,
                        "import_policies": "|".join(sorted(p["name"] for p in nb_session.get("import_policies") or [])),
                        "export_policies": "|".join(sorted(p["name"] for p in nb_session.get("export_policies") or [])),
                        "prefix_list_in":  nb_session["prefix_list_in"]["name"] if nb_session.get("prefix_list_in") else None,
                        "prefix_list_out": nb_session["prefix_list_out"]["name"] if nb_session.get("prefix_list_out") else None,
                    }
                except Exception as e:
                    log.warning(f"{self.name} - failed to normalise NetBox session '{sname}' for '{device_name}': {e}")

            # Normalise live parse data
            normalised_live = {}
            for worker_name, worker_data in parse_data.items():
                if worker_data.get("failed"):
                    continue
                host_data = worker_data.get("result", {})
                if device_name not in host_data:
                    continue
                host_sessions = host_data[device_name]
                for s in host_sessions:
                    session_name = f"{device_name}_{s['name']}"
                    normalised_live[session_name] = {
                        "name":            session_name,
                        "description":     s.get("description") or "",
                        "local_address":   s.get("local_address"),
                        "local_as":        str(s.get("local_as", "")),
                        "remote_address":  s.get("remote_address"),
                        "remote_as":       str(s.get("remote_as", "")),
                        "vrf":             s.get("vrf"),
                        "status":          "active" if s.get("state") == "established" else status,
                        "peer_group":      s.get("peer_group"),
                        "import_policies": "|".join(sorted(s.get("import_policies") or [])),
                        "export_policies": "|".join(sorted(s.get("export_policies") or [])),
                        "prefix_list_in":  s.get("prefix_list_in"),
                        "prefix_list_out": s.get("prefix_list_out"),
                    }

            # Compute diff: source=live, target=netbox
            raw_diff = self._build_dataset_diff(normalised_live, normalised_nb)
            diff_results[device_name] = {
                "missing_in_netbox": raw_diff["missing_in_target"],
                "missing_on_device": raw_diff["missing_in_source"],
                "needs_update":      raw_diff["needs_update"],
                "in_sync":           raw_diff["in_sync"],
                "_normalised_live":  normalised_live,
            }

        # return dry run results
        if dry_run:
            for device_name, diff in diff_results.items():
                ret.result[device_name] = {
                    "missing_in_netbox": diff["missing_in_netbox"],
                    "missing_on_device": diff["missing_on_device"],
                    "needs_update":      diff["needs_update"],
                    "in_sync":           diff["in_sync"],
                }
            return ret

        # proceed with sessions updates
        nb = self._get_pynetbox(instance, branch=branch)

        # Pre-fetch device IDs once
        devices_result = {d.name: d.id for d in nb.dcim.devices.filter(name=devices, fields="name,id")}

        # Resolve RIR ID once if rir name provided
        rir_id = None
        if rir:
            rir_obj = nb.ipam.rirs.get(name=rir)
            if rir_obj:
                rir_id = rir_obj.id
            else:
                msg = f"RIR '{rir}' not found in NetBox, ASN creation will fail if needed"
                job.event(msg, severity="WARNING")
                log.warning(f"{self.name} - {msg}")

        for device_name in devices:
            created = []
            updated = []
            deleted = []
            skipped = []

            diff = diff_results[device_name]
            normalised_live = diff["_normalised_live"]

            if device_name not in devices_result:
                msg = f"device '{device_name}' not found in NetBox, skipping"
                job.event(msg, severity="WARNING")
                ret.errors.append(msg)
                continue

            device_id = devices_result[device_name]

            def _resolve_ip(address):
                """Resolve or create an IP address in IPAM, return its ID or None."""
                if not address:
                    return None
                existing = list(nb.ipam.ip_addresses.filter(q=f"{address}/"))
                if existing:
                    return existing[0].id
                # Try to find a containing prefix for mask length
                mask = None
                prefixes = list(nb.ipam.prefixes.filter(contains=address))
                if prefixes:
                    mask = prefixes[0].prefix.split("/")[1]
                if not mask:
                    try:
                        net = ipaddress.ip_network(address, strict=False)
                        mask = "128" if net.version == 6 else "32"
                    except Exception:
                        mask = "32"
                try:
                    new_ip = nb.ipam.ip_addresses.create(address=f"{address}/{mask}")
                    msg = f"created IP address '{address}/{mask}' in NetBox IPAM"
                    job.event(msg)
                    log.info(f"{self.name} - {msg}")
                    return new_ip.id
                except Exception as e:
                    msg = f"failed to create IP address '{address}/{mask}': {e}"
                    job.event(msg, severity="ERROR")
                    log.error(f"{self.name} - {msg}")
                    ret.errors.append(msg)
                    return None

            def _resolve_asn(asn_str):
                """Resolve or create an ASN, return its ID or None."""
                if not asn_str:
                    return None
                try:
                    asn_int = int(asn_str)
                except (ValueError, TypeError):
                    return None
                existing = list(nb.ipam.asns.filter(asn=asn_int))
                if existing:
                    return existing[0].id
                if not rir_id:
                    msg = f"cannot create ASN '{asn_str}': no RIR provided, use 'rir' parameter"
                    job.event(msg, severity="WARNING")
                    log.warning(f"{self.name} - {msg}")
                    ret.errors.append(msg)
                    return None
                try:
                    new_asn = nb.ipam.asns.create(asn=asn_int, rir=rir_id)
                    msg = f"created ASN '{asn_str}' in NetBox IPAM"
                    job.event(msg)
                    log.info(f"{self.name} - {msg}")
                    return new_asn.id
                except Exception as e:
                    msg = f"failed to create ASN '{asn_str}': {e}"
                    job.event(msg, severity="ERROR")
                    log.error(f"{self.name} - {msg}")
                    ret.errors.append(msg)
                    return None


            def _resolve_or_create(endpoint, name, family=None):
                """Resolve or create a named object (peer_group / routing_policy / prefix_list)."""
                if not name:
                    return None
                if family:
                    existing = endpoint.get(name=name, family=family)
                else:
                    existing = endpoint.get(name=name)
                if existing:
                    return existing.id
                create_kwargs = {"name": name}
                if family is not None:
                    create_kwargs["family"] = family
                try:
                    new_obj = endpoint.create(**create_kwargs)
                    msg = f"created object '{name}' via {endpoint}"
                    job.event(msg)
                    log.info(f"{self.name} - {msg}")
                    return new_obj.id
                except Exception as e:
                    msg = f"failed to create object '{name}' via {endpoint}: {e}"
                    job.event(msg, severity="ERROR")
                    log.error(f"{self.name} - {msg}")
                    ret.errors.append(msg)
                    return None

            def _get_addr_family(address):
                """Return 'ipv4' or 'ipv6' based on the IP address version."""
                try:
                    return "ipv6" if ipaddress.ip_address(address).version == 6 else "ipv4"
                except Exception:
                    return "ipv4"

            # --- Create ---
            create_payloads = []
            for sname in diff["missing_in_netbox"]:
                s = normalised_live[sname]

                local_ip_id = _resolve_ip(s["local_address"])
                remote_ip_id = _resolve_ip(s["remote_address"])
                local_as_id = _resolve_asn(s["local_as"])
                remote_as_id = _resolve_asn(s["remote_as"])

                resolution_errors = []
                if not local_ip_id:
                    resolution_errors.append(f"local IP '{s['local_address']}'")
                if not remote_ip_id:
                    resolution_errors.append(f"remote IP '{s['remote_address']}'")
                if not local_as_id:
                    resolution_errors.append(f"local ASN '{s['local_as']}'")
                if not remote_as_id:
                    resolution_errors.append(f"remote ASN '{s['remote_as']}'")
                if resolution_errors:
                    msg = f"skipping '{sname}': could not resolve {', '.join(resolution_errors)}"
                    job.event(msg, severity="WARNING")
                    log.warning(f"{self.name} - {msg}")
                    ret.errors.append(msg)
                    skipped.append(sname)
                    continue

                payload = {
                    "name":          sname,
                    "description":   s["description"],
                    "device":        device_id,
                    "local_address": local_ip_id,
                    "local_as":      local_as_id,
                    "remote_address": remote_ip_id,
                    "remote_as":     remote_as_id,
                    "status":        s["status"],
                }

                if s.get("vrf"):
                    vrf = nb.ipam.vrfs.get(name=s["vrf"])
                    if vrf:
                        payload["vrf"] = vrf.id

                if s.get("peer_group"):
                    pg_id = _resolve_or_create(nb.plugins.bgp.peer_group, s["peer_group"])
                    if pg_id:
                        payload["peer_group"] = pg_id

                addr_family = _get_addr_family(s["local_address"])

                if s.get("import_policies"):
                    names = [p for p in s["import_policies"].split("|") if p]
                    ids = [_resolve_or_create(nb.plugins.bgp.routing_policy, p, family=addr_family) for p in names]
                    payload["import_policies"] = [i for i in ids if i]

                if s.get("export_policies"):
                    names = [p for p in s["export_policies"].split("|") if p]
                    ids = [_resolve_or_create(nb.plugins.bgp.routing_policy, p, family=addr_family) for p in names]
                    payload["export_policies"] = [i for i in ids if i]

                if s.get("prefix_list_in"):
                    pl_id = _resolve_or_create(nb.plugins.bgp.prefix_list, s["prefix_list_in"], family=addr_family)
                    if pl_id:
                        payload["prefix_list_in"] = pl_id

                if s.get("prefix_list_out"):
                    pl_id = _resolve_or_create(nb.plugins.bgp.prefix_list, s["prefix_list_out"], family=addr_family)
                    if pl_id:
                        payload["prefix_list_out"] = pl_id

                create_payloads.append(payload)
                created.append(sname)

            if create_payloads:
                try:
                    nb.plugins.bgp.session.create(create_payloads)
                    msg = f"created {len(create_payloads)} BGP session(s) for '{device_name}'"
                    log.info(msg)
                    job.event(msg)
                except Exception as e:
                    msg = f"failed to create BGP sessions for '{device_name}': {e}"
                    ret.errors.append(msg)
                    log.error(f"{self.name} - {msg}")
                    # Move failed names from created to skipped
                    skipped.extend(created)
                    created = []

            # --- Update ---
            for sname, field_changes in diff["needs_update"].items():
                try:
                    session = nb.plugins.bgp.session.get(name=sname)
                    if not session:
                        msg = f"BGP session '{sname}' not found in NetBox, skipping update"
                        job.event(msg, severity="WARNING")
                        log.warning(f"{self.name} - {msg}")
                        ret.errors.append(msg)
                        skipped.append(sname)
                        continue

                    
                    addr_family = _get_addr_family(session.local_address.address.split("/")[0])

                    changed_payload = {}
                    for field, change in field_changes.items():
                        new_value = change["new_value"]
                        if field == "local_address":
                            ip_id = _resolve_ip(new_value)
                            if ip_id:
                                changed_payload["local_address"] = ip_id
                        elif field == "remote_address":
                            ip_id = _resolve_ip(new_value)
                            if ip_id:
                                changed_payload["remote_address"] = ip_id
                        elif field == "local_as":
                            asn_id = _resolve_asn(new_value)
                            if asn_id:
                                changed_payload["local_as"] = asn_id
                        elif field == "remote_as":
                            asn_id = _resolve_asn(new_value)
                            if asn_id:
                                changed_payload["remote_as"] = asn_id
                        elif field in ("description", "status"):
                            changed_payload[field] = new_value
                        elif field == "vrf":
                            if new_value:
                                vrf = nb.ipam.vrfs.get(name=new_value)
                                changed_payload["vrf"] = vrf.id if vrf else None
                            else:
                                changed_payload["vrf"] = None
                        elif field == "peer_group":
                            if new_value:
                                pg_id = _resolve_or_create(nb.plugins.bgp.peer_group, new_value)
                                changed_payload["peer_group"] = pg_id
                            else:
                                changed_payload["peer_group"] = None
                        elif field in ("import_policies", "export_policies"):
                            names = [p for p in new_value.split("|") if p] if new_value else []
                            ids = [_resolve_or_create(nb.plugins.bgp.routing_policy, p, family=addr_family) for p in names]
                            changed_payload[field] = [i for i in ids if i]
                        elif field == "prefix_list_in":
                            if new_value:
                                pl_id = _resolve_or_create(nb.plugins.bgp.prefix_list, new_value, family=addr_family)
                                changed_payload["prefix_list_in"] = pl_id
                            else:
                                changed_payload["prefix_list_in"] = None
                        elif field == "prefix_list_out":
                            if new_value:
                                pl_id = _resolve_or_create(nb.plugins.bgp.prefix_list, new_value, family=addr_family)
                                changed_payload["prefix_list_out"] = pl_id
                            else:
                                changed_payload["prefix_list_out"] = None

                    if changed_payload:
                        session.update(changed_payload)
                        updated.append(sname)
                        msg = f"updated BGP session '{sname}' for '{device_name}'"
                        job.event(msg)
                        log.info(f"{self.name} - {msg}")
                except Exception as e:
                    msg = f"failed to update BGP session '{sname}' for '{device_name}': {e}"
                    ret.errors.append(msg)
                    log.error(f"{self.name} - {msg}")
                    skipped.append(sname)

            # --- Delete ---
            if process_deletions:
                for sname in diff["missing_on_device"]:
                    try:
                        session = nb.plugins.bgp.session.get(name=sname)
                        if session:
                            session.delete()
                            deleted.append(sname)
                            msg = f"deleted BGP session '{sname}' for '{device_name}'"
                            job.event(msg)
                            log.info(f"{self.name} - {msg}")
                    except Exception as e:
                        msg = f"failed to delete BGP session '{sname}' for '{device_name}': {e}"
                        ret.errors.append(msg)
                        log.error(f"{self.name} - {msg}")
                        skipped.append(sname)

            ret.result[device_name] = {
                "created": created,
                "updated": updated,
                "deleted": deleted,
                "skipped": skipped,
            }

        return ret

