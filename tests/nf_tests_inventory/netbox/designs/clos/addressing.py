"""Address arithmetic for the compact CLOS design; no NetBox reads or writes."""

from ipaddress import IPv4Network, ip_network


def fabric_pool(prefix: str) -> IPv4Network:
    """Return a strictly aligned IPv4 /20 for Jinja indexing.

    Args:
        prefix: Site allocation in CIDR notation, with no host bits set.

    Returns:
        IPv4Network: The 4096-address pool; indexing returns an IPv4 address.

    Raises:
        ValueError: The prefix is malformed, unaligned, IPv6, or not a /20.
    """
    pool = ip_network(prefix, strict=True)
    if pool.version != 4 or pool.prefixlen != 20:
        raise ValueError("prefix must be an aligned IPv4 /20")
    return pool
