import json
import os


def load(path):
    """Return the dict stored in `path`, or {} if it is missing or unreadable."""
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(path, data):
    """Write `data` as JSON, replacing `path` only once the new copy is complete.

    Losing power mid-write then leaves the previous file intact instead of a
    truncated one (littlefs rename is atomic and overwrites the target).
    """
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.rename(tmp, path)
