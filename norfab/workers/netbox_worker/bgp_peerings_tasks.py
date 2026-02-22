import logging

from typing import Union
from norfab.core.worker import Task, Job
from norfab.models import Result
from norfab.models.netbox import NetboxFastApiArgs

log = logging.getLogger(__name__)


class NetboxBgpPeeringsTasks:

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_bgp_peerings(
        self,
        job: Job,
        instance: Union[None, str] = None,
        devices: Union[None, list] = None,
        cache: Union[bool, str] = None,
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
        """
        instance = instance or self.default_instance
        devices = devices or []
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
                    f"Using cached BGP peerings for '{device_name}' (forced)",
                    resource=instance,
                )
                continue

            # Mode: cache disabled - fetch without caching
            if cache is False:
                bgp_sessions = nb.plugins.bgp.session.filter(device_id=device_id)
                ret.result[device_name] = {s.name: dict(s) for s in bgp_sessions}
                job.event(
                    f"Retrieved {len(ret.result[device_name])} BGP session(s) for '{device_name}'",
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
                    f"Fetched and cached {len(ret.result[device_name])} BGP session(s) for '{device_name}'",
                    resource=instance,
                )
                continue

            # Mode: cache=True with cached data - smart update (only fetch changed sessions)
            ret.result[device_name] = dict(cached_data)
            job.event(
                f"Retrieved {len(cached_data)} BGP session(s) from cache for '{device_name}'",
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
                    f"Removed deleted session '{session_name}' from cache for '{device_name}'",
                    resource=instance,
                )

            # Fetch updated/new sessions
            if session_ids_to_fetch:
                job.event(
                    f"Fetching {len(session_ids_to_fetch)} updated BGP session(s) for '{device_name}'",
                    resource=instance,
                )
                for session in nb.plugins.bgp.session.filter(id=session_ids_to_fetch):
                    ret.result[device_name][session.name] = dict(session)

            # Update cache if any changes occurred
            if session_ids_to_fetch or sessions_to_remove:
                self.cache.set(
                    cache_key, ret.result[device_name], expire=self.cache_ttl
                )
                job.event(f"Updated cache for '{device_name}'", resource=instance)
            else:
                job.event(
                    f"Using cache, it is up to date for '{device_name}'",
                    resource=instance,
                )

        return ret
