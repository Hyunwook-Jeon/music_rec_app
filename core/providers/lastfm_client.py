from __future__ import annotations
import os
import requests
from typing import List, Dict, Any, Optional

from utils.cache import TTLCache


class LastFMClient:
    BASE = "https://ws.audioscrobbler.com/2.0/"

    def __init__(self, api_key: Optional[str] = None, cache: Optional[TTLCache] = None):
        self.api_key = api_key or os.getenv("LASTFM_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("LASTFM_API_KEY is missing. Put it in .env or environment variables.")
        self.cache = cache or TTLCache(ttl_seconds=600)

    def _get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        params = dict(params)
        params.update({
            "api_key": self.api_key,
            "format": "json",
        })
        cache_key = "lastfm:" + "&".join([f"{k}={params[k]}" for k in sorted(params.keys())])
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        r = requests.get(self.BASE, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        self.cache.set(cache_key, data)
        return data

    def track_get_similar(self, track: str, artist: str, limit: int = 20) -> List[Dict[str, Any]]:
        data = self._get({
            "method": "track.getSimilar",
            "track": track,
            "artist": artist,
            "limit": limit,
            "autocorrect": 1,
        })
        # { similartracks: { track: [ ... ] } }
        tracks = (((data or {}).get("similartracks") or {}).get("track")) or []
        if isinstance(tracks, dict):
            tracks = [tracks]
        return tracks

    def artist_get_similar(self, artist: str, limit: int = 10) -> List[Dict[str, Any]]:
        data = self._get({
            "method": "artist.getSimilar",
            "artist": artist,
            "limit": limit,
            "autocorrect": 1,
        })
        artists = (((data or {}).get("similarartists") or {}).get("artist")) or []
        if isinstance(artists, dict):
            artists = [artists]
        return artists

    def artist_get_top_tracks(self, artist: str, limit: int = 5) -> List[Dict[str, Any]]:
        data = self._get({
            "method": "artist.getTopTracks",
            "artist": artist,
            "limit": limit,
            "autocorrect": 1,
        })
        tracks = (((data or {}).get("toptracks") or {}).get("track")) or []
        if isinstance(tracks, dict):
            tracks = [tracks]
        return tracks

    def track_get_toptags(self, track: str, artist: str, limit: int = 5) -> List[str]:
        data = self._get({
            "method": "track.getTopTags",
            "track": track,
            "artist": artist,
            "autocorrect": 1,
        })
        tags = (((data or {}).get("toptags") or {}).get("tag")) or []
        if isinstance(tags, dict):
            tags = [tags]
        names = []
        for t in tags[:limit]:
            n = (t or {}).get("name")
            if n:
                names.append(str(n))
        return names
