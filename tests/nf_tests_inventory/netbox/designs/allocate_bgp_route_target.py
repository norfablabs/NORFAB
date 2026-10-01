from typing import Any


def allocate_bgp_route_target(
    context: dict, netbox: Any, dry_run: bool, tenant: str, description: str
) -> dict:
    """Create or update the ACME example route target during deployment."""
    name = "4200650001:300"
    existing = netbox.ipam.route_targets.get(name=name)
    if not dry_run:
        if existing:
            existing.update({"tenant": {"name": tenant}, "description": description})
        else:
            netbox.ipam.route_targets.create(
                {"name": name, "tenant": {"name": tenant}, "description": description}
            )
    return {"name": name}
