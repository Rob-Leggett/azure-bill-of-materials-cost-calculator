from typing import Optional


def stripped(val: Optional[str], default: Optional[str] = None) -> Optional[str]:
    """
    Return val as a trimmed string; if val is None, use default; if the result
    is empty after trimming, return None.
    """
    s = default if val is None else val
    if s is None:
        return None
    s = str(s).strip()
    return s or None