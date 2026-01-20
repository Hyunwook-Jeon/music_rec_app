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
                return RecommendResult(
                    mode="track",
                    resolved_track=resolved_track,
                    resolved_artist=resolved_artist,
                    query_raw=raw,
                    items=items,
                    message=f"'{resolved_track} - {resolved_artist}' 기반 추천",
                )

        # 2) Track이 없거나 실패하면 artist-only fallback
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

        return RecommendResult(
            mode="artist_fallback",
            resolved_artist=resolved_artist,
            query_raw=raw,
            items=items,
            message=f"'{resolved_artist}'(아티스트) 기반 추천",
        )

    def _resolve_track_artist(self, track: str, artist: str) -> tuple[str, str]:
        # MusicBrainz로 오타/동명이곡 보정 시도(가볍게 top-1만)
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
                # preview 없으면 그냥 넘어감
                continue

    def _recommend_by_track(self, track: str, artist: str, limit_tracks: int) -> List[TrackRecommendation]:
        raws = self.lastfm.track_get_similar(track, artist, limit=limit_tracks)
        items: List[TrackRecommendation] = []
        for idx, r in enumerate(raws, start=1):
            name = (r or {}).get("name")
            art = ((r or {}).get("artist") or {}).get("name")
            url = (r or {}).get("url")
            match = (r or {}).get("match")
            sim = None
            try:
                if match is not None:
                    sim = float(match)
            except Exception:
                sim = None

            if not name or not art:
                continue

            tags = []
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
            ))

        self._attach_preview(items)
        return items

    def _recommend_by_artist_fallback(self, artist: str, limit_tracks: int) -> List[TrackRecommendation]:
        # 1) 유사 아티스트 10명
        sim_artists = self.lastfm.artist_get_similar(artist, limit=10)

        # 2) 각 아티스트의 top tracks를 모아서 track 추천 리스트를 구성
        items: List[TrackRecommendation] = []
        rank = 1
        for a in sim_artists:
            a_name = (a or {}).get("name")
            if not a_name:
                continue
            top_tracks = self.lastfm.artist_get_top_tracks(a_name, limit=3)
            for t in top_tracks:
                t_name = (t or {}).get("name")
                t_artist = ((t or {}).get("artist") or {}).get("name") or a_name
                url = (t or {}).get("url")
                if not t_name:
                    continue

                items.append(TrackRecommendation(
                    track=str(t_name),
                    artist=str(t_artist),
                    rank=rank,
                    similarity=None,
                    lastfm_url=url,
                    tags=[],
                ))
                rank += 1
                if len(items) >= limit_tracks:
                    break
            if len(items) >= limit_tracks:
                break

        self._attach_preview(items)
        return items
