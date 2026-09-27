def custom_create_tenant(netbox, dry_run, name, slug, prerequisite):
    """Create a test tenant after its explicit prerequisite has been deployed."""
    if not netbox.tenancy.tenants.get(name=prerequisite):
        raise ValueError("explicit prerequisite tenant is missing")
    tenant = netbox.tenancy.tenants.get(name=name)
    if not dry_run:
        if tenant:
            tenant.update({"slug": slug})
        else:
            netbox.tenancy.tenants.create({"name": name, "slug": slug})
    return {"name": name, "dry_run": dry_run}
