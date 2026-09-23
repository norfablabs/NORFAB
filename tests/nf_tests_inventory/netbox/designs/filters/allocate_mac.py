def allocate_mac(prefix: str, suffix: int) -> str:
    return f"{prefix}:{suffix:02x}"
