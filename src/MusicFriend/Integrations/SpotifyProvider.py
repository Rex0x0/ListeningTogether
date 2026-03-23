"""
Spotify 当前播放（凭证来自环境变量，避免硬编码密钥）。
"""

from __future__ import annotations

import os
from typing import Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from MusicFriend.Integrations.NowPlayingProvider import NowPlayingSnapshot


class SpotifyProvider:
    platformId = "spotify"

    def __init__(self) -> None:
        self._sp: Optional[spotipy.Spotify] = None

    def initialize(self) -> bool:
        client_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
        client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
        redirect_uri = os.environ.get("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback").strip()
        if not client_id or not client_secret:
            print("SpotifyProvider: 请设置环境变量 SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET")
            return False
        cache_path = os.path.join(os.getcwd(), ".spotify_cache")
        auth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope="user-read-currently-playing",
            open_browser=False,
            cache_path=cache_path,
        )
        token = auth.get_access_token(check_cache=True)
        if not token:
            url = auth.get_authorize_url()
            print("SpotifyProvider: 需要授权，请在浏览器打开:\n", url)
            return False
        self._sp = spotipy.Spotify(auth_manager=auth)
        try:
            self._sp.current_user()
        except Exception as e:
            print(f"SpotifyProvider: 初始化失败 {e}")
            return False
        return True

    def poll(self) -> Optional[NowPlayingSnapshot]:
        if not self._sp:
            return None
        try:
            cur = self._sp.current_user_playing_track()
            if not cur or not cur.get("is_playing"):
                return None
            item = cur.get("item") or {}
            name = item.get("name")
            if not name:
                return None
            artists = item.get("artists") or []
            artist_names = ", ".join(a.get("name", "") for a in artists if a.get("name"))
            title = f"{name} - {artist_names}" if artist_names else str(name)
            images = (item.get("album") or {}).get("images") or []
            art_url = images[0].get("url") if images else None
            return NowPlayingSnapshot(title=title, artUrl=art_url, platform=self.platformId)
        except Exception as e:
            print(f"SpotifyProvider: poll 异常 {e}")
            return None
