"""Small helpers shared across modules."""

import concurrent.futures
import datetime


def days_since(stamp):
    """Whole days between an ISO-8601 stamp and now, or None if unparseable.

    Store timestamps arrive as UTC, so the comparison is made in UTC rather
    than in the machine's local zone.
    """
    if not stamp:
        return None
    try:
        when = datetime.datetime.strptime(stamp[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
    when = when.replace(tzinfo=datetime.timezone.utc)
    return (datetime.datetime.now(datetime.timezone.utc) - when).days


def human_size(size):
    """Byte count as KB or MB, whichever reads better."""
    if not size:
        return "0 KB"
    if size < 1048576:
        return "%.0f KB" % (size / 1024.0)
    return "%.1f MB" % (size / 1048576.0)


def wrap(text, width):
    """Greedy word wrap, for console output."""
    words, line, out = (text or "").split(), "", []
    for word in words:
        if len(line) + len(word) + 1 > width:
            out.append(line)
            line = word
        else:
            line = (line + " " + word).strip()
    if line:
        out.append(line)
    return out


def parallel_map(func, items, workers=6):
    """Apply `func` over `items` concurrently, preserving input order.

    Every call site here is network-bound, so threads are the right tool and
    the pool stays small enough to be polite to Apple's endpoints. Exceptions
    propagate to the caller as they would from a plain map.
    """
    items = list(items)
    if len(items) < 2:
        return [func(item) for item in items]
    size = max(1, min(workers, len(items)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=size) as pool:
        return list(pool.map(func, items))
