from __future__ import annotations
import os
import requests
from typing import Any, Dict, List, Optional


class LastFMClient:
    BASE_URL = "https://ws.audioscrobbler.com/2.0/"

    def __init__(self, api_key: Optional[str] = None, timeout: int = 10):
        self.api_key = api_key or os.getenv("LASTFM_API_KEY")
        if not self.api_key:
            raise RuntimeError("LASTFM_API_KEY is missing. Put it in .env or environment variables.")
        self.timeout = timeout
        self.session = requests.Session()

    def _get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        q = dict(params)
        q["api_key"] = self.api_key
        q["format"] = "json"

        r = self.session.get(self.BASE_URL, params=q, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()

        # Last.fm errors come as: {"error":..., "message":...}
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(f"Last.fm error: {data.get('message')} (code={data.get('error')})")
        return data if isinstance(data, dict) else {}

    # ------------------------------
    # Track
    # ------------------------------
    def track_get_similar(self, track: str, artist: str, limit: int = 20) -> List[Dict[str, Any]]:
        data = self._get({
            "method": "track.getSimilar",
            "track": track,
            "artist": artist,
            "limit": limit,
            "autocorrect": 1,
        })
        # expected: {"similartracks": {"track": [...]}}
        similar = (data.get("similartracks") or {}).get("track")
        if isinstance(similar, list):
            return similar
        if isinstance(similar, dict):
            return [similar]
        return []

    def track_get_toptags(self, track: str, artist: str, limit: int = 5) -> List[str]:
        data = self._get({
            "method": "track.getTopTags",
            "track": track,
            "artist": artist,
            "autocorrect": 1,
        })
        tags_obj = ((data.get("toptags") or {}).get("tag")) or []
        tags: List[str] = []

        if isinstance(tags_obj, list):
            for t in tags_obj[:limit]:
                name = (t or {}).get("name")
                if name:
                    tags.append(str(name))
        elif isinstance(tags_obj, dict):
            name = tags_obj.get("name")
            if name:
                tags.append(str(name))

        return tags

    # ------------------------------
    # Artist
    # ------------------------------
    def artist_get_similar(self, artist: str, limit: int = 10) -> List[Dict[str, Any]]:
        data = self._get({
            "method": "artist.getSimilar",
            "artist": artist,
            "limit": limit,
            "autocorrect": 1,
        })
        sim = (data.get("similarartists") or {}).get("artist")
        if isinstance(sim, list):
            return sim
        if isinstance(sim, dict):
            return [sim]
        return []

    def artist_get_top_tracks(self, artist: str, limit: int = 3) -> List[Dict[str, Any]]:
        data = self._get({
            "method": "artist.getTopTracks",
            "artist": artist,
            "limit": limit,
            "autocorrect": 1,
        })
        tracks = ((data.get("toptracks") or {}).get("track")) or []
        if isinstance(tracks, list):
            return tracks
        if isinstance(tracks, dict):
            return [tracks]
        return []

    def artist_get_toptags(self, artist: str, limit: int = 5) -> List[str]:
        data = self._get({
            "method": "artist.getTopTags",
            "artist": artist,
            "autocorrect": 1,
        })
        tags_obj = ((data.get("toptags") or {}).get("tag")) or []
        tags: List[str] = []

        if isinstance(tags_obj, list):
            for t in tags_obj[:limit]:
                name = (t or {}).get("name")
                if name:
                    tags.append(str(name))
        elif isinstance(tags_obj, dict):
            name = tags_obj.get("name")
            if name:
                tags.append(str(name))

        return tags
