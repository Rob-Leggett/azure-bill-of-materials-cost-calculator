

def stripped(val: str | None, default: str | None = None) -> str | None:
    """
    Return val as a trimmed string; if val is None, use default; if the result
    is empty after trimming, return None.
    """
    s = default if val is None else val
    if s is None:
        return None
    s = str(s).strip()
    return s or None