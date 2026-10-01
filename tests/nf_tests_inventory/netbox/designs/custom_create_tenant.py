from typing import Any


def custom_create_tenant(
    context: dict, netbox: Any, dry_run: bool, name: str, slug: str, prerequisite: str
) -> dict:
    """Create a test tenant after its explicit prerequisite has been deployed."""
    if not netbox.tenancy.tenants.get(name=prerequisite):
        raise ValueError("explicit prerequisite tenant is missing")
    if context["tenant_name"] != name:
        raise ValueError("design context tenant does not match")
    tenant = netbox.tenancy.tenants.get(name=name)
    if not dry_run:
        if tenant:
            tenant.update({"slug": slug})
        else:
            netbox.tenancy.tenants.create({"name": name, "slug": slug})
    return {"name": name, "dry_run": dry_run, "context_tenant": context["tenant_name"]}
