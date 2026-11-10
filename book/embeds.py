"""Turn a pasted video link into a safe iframe src.

Only known hosts are embedded, and the src is rebuilt from parsed parts, so
pasted text never ends up in the page as HTML. Unknown hosts are shown as a
plain link instead.
"""

import re
from urllib.parse import parse_qs, urlparse

_ID = re.compile(r"^[A-Za-z0-9_-]{2,64}$")


def _seconds(t):
    """'90', '90s', '1m30s' -> 90."""
    if not t:
        return 0
    if t.isdigit():
        return int(t)
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", t)
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def embed_src(url):
    if not url:
        return None
    try:
        u = urlparse(url.strip())
    except ValueError:
        return None
    if u.scheme not in ("http", "https"):
        return None
    host = (u.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m."):
        host = host[2:]
    path = [p for p in u.path.split("/") if p]
    qs = parse_qs(u.query)

    # YouTube
    vid = None
    if host == "youtu.be" and path:
        vid = path[0]
    elif host in ("youtube.com", "youtube-nocookie.com"):
        if path[:1] == ["watch"]:
            vid = (qs.get("v") or [None])[0]
        elif len(path) >= 2 and path[0] in ("shorts", "embed", "live"):
            vid = path[1]
    if vid:
        if not _ID.match(vid):
            return None
        start = _seconds((qs.get("t") or qs.get("start") or [""])[0])
        src = f"https://www.youtube-nocookie.com/embed/{vid}"
        return f"{src}?start={start}" if start else src

    # Streamable: streamable.com/<id> or /e/<id>
    if host == "streamable.com" and path:
        sid = path[1] if path[0] in ("e", "o") and len(path) > 1 else path[0]
        return f"https://streamable.com/e/{sid}" if _ID.match(sid) else None

    # Medal: medal.tv/games/<game>/clips/<clipId>/<contentId>
    if host == "medal.tv" and len(path) >= 4 and path[0] == "games" and path[2] == "clips":
        parts = [path[1], *path[3:5]]
        if all(_ID.match(p) for p in parts):
            game, *clip = parts
            return f"https://medal.tv/games/{game}/clips/{'/'.join(clip)}?theater=true"

    return None
