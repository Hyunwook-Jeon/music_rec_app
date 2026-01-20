from __future__ import annotations
import requests
from typing import Optional, Dict, Any, List

from utils.cache import TTLCache


class MusicBrainzClient:
    BASE = "https://musicbrainz.org/ws/2/"

    def __init__(self, cache: Optional[TTLCache] = None):
        self.cache = cache or TTLCache(ttl_seconds=3600)

    def _get(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        params = dict(params)
        params["fmt"] = "json"

        cache_key = "mb:" + endpoint + "?" + "&".join([f"{k}={params[k]}" for k in sorted(params.keys())])
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        headers = {
            # MusicBrainz는 User-Agent 권장/사실상 필수
            "User-Agent": "music-rec-app/0.1 ( https://example.com )"
        }
        r = requests.get(self.BASE + endpoint, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        self.cache.set(cache_key, data)
        return data

    def search_recording(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        data = self._get("recording/", {"query": query, "limit": limit})
        return (data or {}).get("recordings") or []

    def search_artist(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        data = self._get("artist/", {"query": query, "limit": limit})
        return (data or {}).get("artists") or []
