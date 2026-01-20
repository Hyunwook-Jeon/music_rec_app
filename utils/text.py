import re
from typing import Tuple, Optional


def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def parse_user_query(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    returns (track, artist)
    - "Track - Artist"
    - "Track — Artist"
    - "Track by Artist"
    If cannot parse, returns (None, artist_or_text)
    """
    t = normalize_space(text)
    if not t:
        return None, None

    # Track by Artist
    m = re.match(r"^(?P<track>.+?)\s+by\s+(?P<artist>.+)$", t, flags=re.IGNORECASE)
    if m:
        return normalize_space(m.group("track")), normalize_space(m.group("artist"))

    # Track - Artist (including em dash)
    for sep in [" - ", " — ", " – "]:
        if sep in t:
            left, right = t.split(sep, 1)
            left, right = normalize_space(left), normalize_space(right)
            if left and right:
                return left, right

    # if only one chunk, treat as artist (fallback)
    return None, t
