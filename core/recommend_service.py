from __future__ import annotations
from typing import List, Optional

from models.dto import RecommendResult, TrackRecommendation
from utils.text import parse_user_query, normalize_space
from utils.cache import TTLCache
from core.providers.lastfm_client import LastFMClient
from core.providers.itunes_client import ITunesClient
from core.providers.musicbrainz_client import MusicBrainzClient


class RecommendService:
    def __init__(self):
        cache = TTLCache(ttl_seconds=600)
        self.lastfm = LastFMClient()
        self.itunes = ITunesClient(cache=cache)
        self.mb = MusicBrainzClient(cache=cache)

    def recommend(self, user_text: str, limit_tracks: int = 20) -> RecommendResult:
        raw = normalize_space(user_text)
        if not raw:
            return RecommendResult(mode="none", query_raw=user_text, message="입력값이 비어있어요.")

        track, artist = parse_user_query(raw)

        # 1) Track+Artist 모드 우선 시도
        if track and artist:
            resolved_track, resolved_artist = self._resolve_track_artist(track, artist)
            items = self._recommend_by_track(resolved_track, resolved_artist, limit_tracks)
            if items:
                self._sort_items(items)
                return RecommendResult(
                    mode="track",
                    resolved_track=resolved_track,
                    resolved_artist=resolved_artist,
                    query_raw=raw,
                    items=items,
                    message=f"'{resolved_track} - {resolved_artist}' 기반 추천",
                )

        # 2) artist-only fallback
        fallback_artist = artist or raw
        resolved_artist = self._resolve_artist(fallback_artist) or fallback_artist
        items = self._recommend_by_artist_fallback(resolved_artist, limit_tracks)
        if not items:
            return RecommendResult(
                mode="artist_fallback",
                resolved_artist=resolved_artist,
                query_raw=raw,
                items=[],
                message="추천을 만들지 못했어요. 아티스트/곡명을 조금 더 정확히 입력해보세요.",
            )

        self._sort_items(items)
        return RecommendResult(
            mode="artist_fallback",
            resolved_artist=resolved_artist,
            query_raw=raw,
            items=items,
            message=f"'{resolved_artist}'(아티스트) 기반 추천",
        )

    def _resolve_track_artist(self, track: str, artist: str) -> tuple[str, str]:
        try:
            q = f'recording:"{track}" AND artist:"{artist}"'
            recs = self.mb.search_recording(q, limit=3)
            if recs:
                best = recs[0]
                title = best.get("title") or track
                credit = (best.get("artist-credit") or [])
                if credit and isinstance(credit, list):
                    name = (credit[0] or {}).get("name")
                else:
                    name = None
                return normalize_space(title), normalize_space(name or artist)
        except Exception:
            pass
        return track, artist

    def _resolve_artist(self, artist: str) -> Optional[str]:
        try:
            arts = self.mb.search_artist(f'artist:"{artist}"', limit=3)
            if arts:
                return normalize_space(arts[0].get("name") or artist)
        except Exception:
            return None
        return None

    def _attach_preview(self, items: List[TrackRecommendation]) -> None:
        for it in items:
            try:
                hit = self.itunes.search_track(it.track, it.artist, country="KR")
                if hit:
                    it.preview_url = hit.get("previewUrl")
                    it.artwork_url = hit.get("artworkUrl100")
                    it.itunes_url = hit.get("trackViewUrl")
            except Exception:
                continue

    def _safe_float(self, x) -> Optional[float]:
        try:
            return float(x) if x is not None else None
        except Exception:
            return None

    def _reason(self, base: str, tags: List[str]) -> str:
        if tags:
            return f"{base} | tags: {', '.join(tags[:3])}"
        return base

    def _get_fallback_tags_for_track(
        self,
        track: str,
        artist: str,
        similar_artist: str,
        query_artist: str,
        limit: int = 5,
    ) -> List[str]:
        """
        Tags robust strategy:
        1) similar artist top tags
        2) query artist top tags
        3) track top tags
        """
        # 1) similar artist tags
        try:
            tags = self.lastfm.artist_get_toptags(similar_artist, limit=limit)
            if tags:
                return tags
        except Exception:
            pass

        # 2) original/query artist tags
        try:
            tags = self.lastfm.artist_get_toptags(query_artist, limit=limit)
            if tags:
                return tags
        except Exception:
            pass

        # 3) track tags
        try:
            tags = self.lastfm.track_get_toptags(track, artist, limit=limit)
            if tags:
                return tags
        except Exception:
            pass

        return []

    def _recommend_by_track(self, track: str, artist: str, limit_tracks: int) -> List[TrackRecommendation]:
        raws = self.lastfm.track_get_similar(track, artist, limit=limit_tracks)
        items: List[TrackRecommendation] = []

        for idx, r in enumerate(raws, start=1):
            name = (r or {}).get("name")
            art = ((r or {}).get("artist") or {}).get("name")
            url = (r or {}).get("url")
            sim = self._safe_float((r or {}).get("match"))

            if not name or not art:
                continue

            try:
                tags = self.lastfm.track_get_toptags(name, art, limit=5)
            except Exception:
                tags = []

            items.append(TrackRecommendation(
                track=str(name),
                artist=str(art),
                rank=idx,
                similarity=sim,
                lastfm_url=url,
                tags=tags,
                reason=self._reason("Similar track based on Last.fm similarity", tags),
            ))

        self._attach_preview(items)
        return items

    def _recommend_by_artist_fallback(self, artist: str, limit_tracks: int) -> List[TrackRecommendation]:
        sim_artists = self.lastfm.artist_get_similar(artist, limit=10)

        items: List[TrackRecommendation] = []
        rank = 1

        for a in sim_artists:
            a_name = (a or {}).get("name")
            if not a_name:
                continue

            a_match = self._safe_float((a or {}).get("match"))

            top_tracks = self.lastfm.artist_get_top_tracks(a_name, limit=3)
            for t in top_tracks:
                t_name = (t or {}).get("name")
                t_artist = ((t or {}).get("artist") or {}).get("name") or a_name
                url = (t or {}).get("url")

                if not t_name:
                    continue

                # ✅ robust tags for fallback
                tags = self._get_fallback_tags_for_track(
                    track=str(t_name),
                    artist=str(t_artist),
                    similar_artist=str(a_name),
                    query_artist=str(artist),
                    limit=5,
                )

                items.append(TrackRecommendation(
                    track=str(t_name),
                    artist=str(t_artist),
                    rank=rank,
                    similarity=a_match,
                    lastfm_url=url,
                    tags=tags,
                    reason=self._reason(f"Top track from similar artist: {a_name}", tags),
                ))

                rank += 1
                if len(items) >= limit_tracks:
                    break

            if len(items) >= limit_tracks:
                break

        self._attach_preview(items)
        return items

    def _sort_items(self, items: List[TrackRecommendation]) -> None:
        def key(x: TrackRecommendation):
            return (
                1 if x.preview_url else 0,
                x.similarity if isinstance(x.similarity, float) else -1,
            )
        items.sort(key=key, reverse=True)
