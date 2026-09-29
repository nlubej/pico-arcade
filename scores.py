import storage

FILE = "scores.json"

_data = storage.load(FILE)

# Boards are stored per "game/mode" (e.g. "reflex/classic"), then per difficulty.
# Each board is a sorted list of [name, score], one entry (their best) per player.
# Drop anything else, e.g. bare scores saved before entries had names.
for _boards in _data.values():
    for _difficulty, _board in _boards.items():
        _boards[_difficulty] = [e for e in _board if isinstance(e, list) and len(e) == 2]

# Scores saved before games had modes are keyed by game alone; they were all Classic.
_old_keys = [k for k in _data if "/" not in k]
for _key in _old_keys:
    _data.setdefault(_key + "/classic", _data.pop(_key))
if _old_keys:
    storage.save(FILE, _data)


def board(key, difficulty):
    """Return every player's best as [name, score], best first."""
    return _data.get(key, {}).get(difficulty, [])


def best(key, difficulty, player):
    """Return (rank, score) of `player`'s best, or None if they have no score yet."""
    for i, (name, score) in enumerate(board(key, difficulty)):
        if name == player:
            return i + 1, score
    return None


def add(key, difficulty, player, score, higher_is_better):
    """Record `player`'s score if it beats their best; return (rank, is_new_best).

    `rank` is the player's 1-based position on the board after the update.
    """
    board = _data.setdefault(key, {}).setdefault(difficulty, [])
    entry = None
    for e in board:
        if e[0] == player:
            entry = e
            break

    if entry is not None:
        better = score > entry[1] if higher_is_better else score < entry[1]
        if not better:
            return board.index(entry) + 1, False
        board.remove(entry)

    # Insert after every entry at least as good, so ties keep older entries ahead.
    # (Done by hand because MicroPython's sort() isn't guaranteed to be stable.)
    rank = 0
    for e in board:
        if (e[1] < score) if higher_is_better else (e[1] > score):
            break
        rank += 1
    board.insert(rank, [player, score])
    storage.save(FILE, _data)
    return rank + 1, True
