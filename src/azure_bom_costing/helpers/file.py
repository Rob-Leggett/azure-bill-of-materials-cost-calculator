import os
from pathlib import Path

def filesize(p: str) -> int:
    """Return file size in bytes, 0 if missing. Defensive against bad paths."""
    try:
        return os.path.getsize(p)
    except Exception:
        try:
            path = Path(p)
            return path.stat().st_size if path.exists() else 0
        except Exception:
            return 0