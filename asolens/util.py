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


# Apple states app sizes in decimal units: the store page shows 2.5 MB for
# 2,520,064 bytes. Dividing by 2^20 gives 2.4 and quietly disagrees with the
# page the reader is comparing against, and the 200 MB cellular download limit
# is quoted in these same units.
MB = 1_000_000
KB = 1_000


def megabytes(size):
    """Bytes as Apple counts megabytes."""
    return (size or 0) / float(MB)


def human_size(size):
    """Byte count as KB or MB, in the units Apple's own listings use."""
    if not size:
        return "0 KB"
    if size < MB:
        return "%.0f KB" % (size / float(KB))
    return "%.1f MB" % megabytes(size)


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
