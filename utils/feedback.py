from __future__ import annotations
import json
import os
from typing import Dict, Tuple


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def normalize_key(track: str, artist: str) -> str:
    return f"{track.strip().lower()}|{artist.strip().lower()}"


class FeedbackStore:
    def __init__(self, filepath: str):
        self.filepath = filepath
        ensure_dir(os.path.dirname(filepath))
        self._data: Dict[str, Dict[str, int | str]] = {}
        self.load()

    def load(self):
        if not os.path.exists(self.filepath):
            self._data = {}
            return
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                self._data = json.load(f)
            if not isinstance(self._data, dict):
                self._data = {}
        except Exception:
            self._data = {}

    def save(self):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def clear(self):
        self._data = {}
        self.save()

    def get_counts(self, track: str, artist: str) -> Tuple[int, int, str]:
        """
        Returns: (like_count, dislike_count, last_action)
        last_action: "like" | "dislike" | ""
        """
        key = normalize_key(track, artist)
        rec = self._data.get(key)
        if not rec:
            return 0, 0, ""
        like = int(rec.get("like", 0))
        dislike = int(rec.get("dislike", 0))
        last = str(rec.get("last", "") or "")
        return like, dislike, last

    def like(self, track: str, artist: str):
        key = normalize_key(track, artist)
        rec = self._data.get(key, {"like": 0, "dislike": 0})
        rec["like"] = int(rec.get("like", 0)) + 1
        rec["last"] = "like"
        self._data[key] = rec
        self.save()

    def dislike(self, track: str, artist: str):
        key = normalize_key(track, artist)
        rec = self._data.get(key, {"like": 0, "dislike": 0})
        rec["dislike"] = int(rec.get("dislike", 0)) + 1
        rec["last"] = "dislike"
        self._data[key] = rec
        self.save()

    def score(self, track: str, artist: str) -> float:
        key = normalize_key(track, artist)
        rec = self._data.get(key)
        if not rec:
            return 0.0

        like = int(rec.get("like", 0))
        dislike = int(rec.get("dislike", 0))

        base = like * 120.0 - dislike * 120.0

        # 최근 피드백 가중
        if rec.get("last") == "like":
            base += 40.0
        elif rec.get("last") == "dislike":
            base -= 40.0

        return base
