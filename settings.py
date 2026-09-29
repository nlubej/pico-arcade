import storage

FILE = "settings.json"

_data = storage.load(FILE)


def get(game, key, default, allowed=None):
    """Return the saved value, or `default` if unset or no longer in `allowed`."""
    value = _data.get(game, {}).get(key, default)
    if allowed is not None and value not in allowed:
        return default
    return value


def set(game, key, value):
    """Store a setting, writing to flash only when it actually changed."""
    update(game, {key: value})


def update(game, values):
    """Store several settings with at most one flash write (none if nothing changed)."""
    section = _data.setdefault(game, {})
    changed = {k: v for k, v in values.items() if section.get(k) != v}
    if not changed:
        return
    section.update(changed)
    storage.save(FILE, _data)
