from __future__ import annotations
import json
import os
from datetime import datetime
from typing import List, Dict, Any


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


class SearchHistoryStore:
    """
    history.json schema:
    {
      "version": 1,
      "items": [
        {"q": "The Weeknd", "ts": "2026-01-20T12:34:56"},
        ...
      ]
    }
    """
    def __init__(self, filepath: str, max_items: int = 50):
        self.filepath = filepath
        self.max_items = max_items
        ensure_dir(os.path.dirname(filepath))

    def load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.filepath):
            return []
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = data.get("items", [])
            return items if isinstance(items, list) else []
        except Exception:
            return []

    def save(self, items: List[Dict[str, Any]]) -> None:
        payload = {"version": 1, "items": items[: self.max_items]}
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def add(self, q: str) -> None:
        q = (q or "").strip()
        if not q:
            return
        items = self.load()

        # de-dup: remove existing q (case-insensitive)
        qlow = q.lower()
        items = [it for it in items if str(it.get("q", "")).lower() != qlow]

        items.insert(0, {"q": q, "ts": datetime.now().isoformat(timespec="seconds")})
        self.save(items)

    def clear(self) -> None:
        self.save([])
