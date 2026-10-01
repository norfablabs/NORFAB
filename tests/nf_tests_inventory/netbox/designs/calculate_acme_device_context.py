from typing import Any


def calculate_acme_device_context(
    device: Any, context: dict, netbox: Any, dry_run: bool, profile: str
) -> dict:
    """Calculate local context from the deployed device and its interfaces."""
    if context.get("profile", profile) != profile:
        raise ValueError("design context profile does not match")
    return {
        "acme": {
            "profile": profile,
            "site": device.site.name,
            "role": device.role.name,
            "interface_count": len(
                list(netbox.dcim.interfaces.filter(device_id=device.id, fields="id"))
            ),
            "primary_ip": device.primary_ip4.address if device.primary_ip4 else None,
        }
    }
