import settings

FILE = "players.txt"
FALLBACK = "Player"


def names():
    """Return the names in players.txt (re-read each call), or [FALLBACK] if there are none."""
    result = []
    try:
        with open(FILE) as f:
            for line in f:
                name = line.strip()
                if name and name not in result:
                    result.append(name)
    except OSError:
        pass
    return result or [FALLBACK]


def current():
    """Return the saved current player, falling back to the first name if it was removed."""
    all_names = names()
    return settings.get("global", "player", all_names[0], all_names)


def _recent(all_names):
    """Previously picked players still in players.txt, most recent first."""
    return [n for n in settings.get("global", "recent", []) if n in all_names]


def by_recent():
    """All names, most recently picked first, then the never-picked ones in file order.

    The current player is always first.
    """
    all_names = names()
    cur = current()
    order = [cur] + [n for n in _recent(all_names) if n != cur]
    return order + [n for n in all_names if n not in order]


def set_current(name):
    """Make `name` the current player and move it to the front of the recent list."""
    all_names = names()
    # Include the outgoing player, who may predate the recent list.
    previous = [current()] + _recent(all_names)
    recent = [name]
    for n in previous:
        if n not in recent:
            recent.append(n)
    settings.update("global", {"player": name, "recent": recent})
