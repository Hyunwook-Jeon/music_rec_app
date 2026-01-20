from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class TrackRecommendation:
    track: str
    artist: str
    rank: int
    similarity: Optional[float] = None

    lastfm_url: Optional[str] = None
    preview_url: Optional[str] = None
    artwork_url: Optional[str] = None
    itunes_url: Optional[str] = None

    tags: List[str] = field(default_factory=list)
    reason: str = ""  

@dataclass
class RecommendResult:
    mode: str  # "track" or "artist_fallback"
    resolved_track: Optional[str] = None
    resolved_artist: Optional[str] = None
    query_raw: str = ""
    items: List[TrackRecommendation] = field(default_factory=list)
    message: str = ""
