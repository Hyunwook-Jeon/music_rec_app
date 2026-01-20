from __future__ import annotations
import json
import os
from dataclasses import asdict
from typing import Dict, List, Any


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def normalize_key(track: str, artist: str) -> str:
    t = (track or "").strip().lower()
    a = (artist or "").strip().lower()
    return f"{t}|||{a}"


class FavoritesStore:
    """
    favorites.json schema:
    {
      "version": 1,
      "items": [
        {
          "track": "...",
          "artist": "...",
          "tags": ["...", ...],
          "lastfm_url": "...",
          "itunes_url": "...",
          "preview_url": "...",
          "artwork_url": "...",
          "reason": "..."
        },
        ...
      ]
    }
    """

    def __init__(self, filepath: str):
        self.filepath = filepath
        ensure_dir(os.path.dirname(filepath))

    def load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.filepath):
            return []
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = data.get("items", [])
            if isinstance(items, list):
                return items
            return []
        except Exception:
            return []

    def save(self, items: List[Dict[str, Any]]) -> None:
        payload = {"version": 1, "items": items}
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def to_map(self) -> Dict[str, Dict[str, Any]]:
        """
        key -> item dict
        """
        items = self.load()
        m: Dict[str, Dict[str, Any]] = {}
        for it in items:
            key = normalize_key(it.get("track", ""), it.get("artist", ""))
            if key.strip("|||"):
                m[key] = it
        return m

    def upsert(self, item_dict: Dict[str, Any]) -> None:
        m = self.to_map()
        key = normalize_key(item_dict.get("track", ""), item_dict.get("artist", ""))
        if not key.strip("|||"):
            return
        m[key] = item_dict
        self.save(list(m.values()))

    def remove(self, track: str, artist: str) -> None:
        m = self.to_map()
        key = normalize_key(track, artist)
        if key in m:
            m.pop(key, None)
            self.save(list(m.values()))

    def clear(self) -> None:
        self.save([])

    def export_snapshot_from_reco(self, reco_obj) -> Dict[str, Any]:
        """
        Convert TrackRecommendation-like object to dict for persistence.
        (We avoid importing dto here to keep utils independent.)
        """
        d = {}
        for k in [
            "track", "artist", "tags", "lastfm_url", "itunes_url",
            "preview_url", "artwork_url", "reason"
        ]:
            d[k] = getattr(reco_obj, k, None)
        if d.get("tags") is None:
            d["tags"] = []
        return d

    def favorite_artists(self) -> set[str]:
        items = self.load()
        return {str(it.get("artist", "")).strip().lower() for it in items if it.get("artist")}

    def favorite_tags(self) -> set[str]:
        items = self.load()
        tags = set()
        for it in items:
            for t in it.get("tags", []) or []:
                if t:
                    tags.add(str(t).strip().lower())
        return tags
