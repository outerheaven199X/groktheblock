def rel(ts: int, origin: int) -> str:
    d = ts - origin
    if d < 0: return "-" + rel(origin, ts)[1:]  # e.g. X posts before the analyzed window
    if d == 0: return "+0s"
    if d < 60: return f"+{d}s"
    m, s = divmod(d, 60)
    if m < 60: return f"+{m}m {s}s" if s else f"+{m}m"
    h, mm = divmod(m, 60)
    return f"+{h}h {mm}m" if mm else f"+{h}h"


def lifespan(sec: int) -> str:
    if sec < 60: return f"{sec} seconds"
    m = sec // 60
    if m < 60: return f"{m} minute{'s' if m > 1 else ''}"
    h, mm = divmod(m, 60)
    if h < 24: return f"{h}h {mm}m" if mm else f"{h} hour{'s' if h > 1 else ''}"
    d = h // 24
    return f"{d} day{'s' if d > 1 else ''}"


def age(sec: int) -> str:
    if sec < 3600: return f"{sec // 60}m"
    if sec < 86400: return f"{sec // 3600}h"
    return f"{sec // 86400}d"
