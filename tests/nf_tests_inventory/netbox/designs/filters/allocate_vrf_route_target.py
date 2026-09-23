def allocate_vrf_route_target(rd_prefix: int, rd_suffix: int = 1) -> str:
    return f"{rd_prefix}:{rd_suffix}"
