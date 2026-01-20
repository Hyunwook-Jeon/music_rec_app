from __future__ import annotations
import requests
from typing import Optional, Dict, Any

from utils.cache import TTLCache


class ITunesClient:
    BASE = "https://itunes.apple.com/search"

    def __init__(self, cache: Optional[TTLCache] = None):
        self.cache = cache or TTLCache(ttl_seconds=3600)

    def search_track(self, track: str, artist: str, country: str = "KR") -> Optional[Dict[str, Any]]:
        term = f"{track} {artist}".strip()
        params = {
            "term": term,
            "media": "music",
            "entity": "song",
            "limit": 1,
            "country": country,
        }
        cache_key = "itunes:" + "&".join([f"{k}={params[k]}" for k in sorted(params.keys())])
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        r = requests.get(self.BASE, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        res = (data or {}).get("results") or []
        item = res[0] if res else None
        self.cache.set(cache_key, item)
        return item
