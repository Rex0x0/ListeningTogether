"""
Windows 网易云：窗口标题解析 + 封面检索（非 Windows 环境返回 None）。
"""

from __future__ import annotations

import sys
from typing import Optional, Tuple

from MusicFriend.Integrations.NowPlayingProvider import NowPlayingSnapshot

if sys.platform == "win32":
    import win32api  # type: ignore
    import win32con  # type: ignore
    import win32gui  # type: ignore
    import win32process  # type: ignore
else:
    win32api = None  # type: ignore
    win32con = None  # type: ignore
    win32gui = None  # type: ignore
    win32process = None  # type: ignore


def _parseWindowTitle(title: str) -> Optional[Tuple[str, str]]:
    if " - " not in title:
        return None
    song, artist = title.split(" - ", 1)
    s, a = song.strip(), artist.strip()
    if not s or not a:
        return None
    return s, a


def _stripNeteaseTitleSuffix(title: str) -> str:
    """去掉窗口标题末尾的客户端品牌后缀，便于解析「歌名 - 艺术家」。"""
    t = title.strip()
    for suf in (
        " - 网易云音乐",
        " - NetEase Cloud Music",
        " - Netease Cloud Music",
        " - CloudMusic",
    ):
        if t.endswith(suf):
            t = t[: -len(suf)].strip()
    return t


def _exePathForWindow(hwnd: int) -> str:
    """根据窗口句柄解析进程可执行文件路径（用于识别 cloudmusic.exe）。"""
    if not win32api or not win32con or not win32process:
        return ""
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        h = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        try:
            return win32process.GetModuleFileNameEx(h, 0)
        finally:
            win32api.CloseHandle(h)
    except Exception:
        return ""


def _getCurrentNeteaseSongFromWindow() -> Optional[Tuple[str, str]]:
    if not win32gui:
        return None
    try:
        candidates: list[str] = []

        def _enum_orpheus(_hwnd: int, _: object) -> bool:
            try:
                if not win32gui.IsWindowVisible(_hwnd):
                    return True
                cls = win32gui.GetClassName(_hwnd)
                if cls != "OrpheusBrowserHost":
                    return True
                raw = (win32gui.GetWindowText(_hwnd) or "").strip()
                if raw:
                    candidates.append(raw)
            except Exception:
                pass
            return True

        win32gui.EnumWindows(_enum_orpheus, None)

        # 类名变更时：按进程名 cloudmusic 匹配仍带「歌 - 艺人」标题的可见顶层窗口
        if not candidates:

            def _enum_by_process(hwnd: int, _: object) -> bool:
                try:
                    if not win32gui.IsWindowVisible(hwnd):
                        return True
                    raw = (win32gui.GetWindowText(hwnd) or "").strip()
                    if " - " not in raw:
                        return True
                    path = _exePathForWindow(hwnd).lower()
                    if "cloudmusic" not in path:
                        return True
                    candidates.append(raw)
                except Exception:
                    pass
                return True

            win32gui.EnumWindows(_enum_by_process, None)

        def _try_one(raw: str) -> Optional[Tuple[str, str]]:
            normalized = _stripNeteaseTitleSuffix(raw)
            return _parseWindowTitle(normalized)

        # 优先选择带分隔符且能解析为「歌 - 艺人」的标题（通常正在展示播放信息）
        for raw in candidates:
            if " - " in raw:
                got = _try_one(raw)
                if got:
                    return got
        for raw in candidates:
            got = _try_one(raw)
            if got:
                return got
        return None
    except Exception:
        return None


def _searchSongMeta(song: str, artist: str) -> tuple[Optional[str], Optional[str]]:
    """返回 (封面 URL, 歌曲 id 字符串)；供封面展示与跟播打开客户端。"""
    # 延迟导入，避免非 Windows 环境强依赖 pyncm
    from pyncm import apis

    query = f"{song} {artist}"
    try:
        search_result = apis.cloudsearch.GetSearchResult(query, stype=1, limit=1)
        songs = (search_result or {}).get("result", {}).get("songs") or []
        if not songs:
            return None, None
        first = songs[0]
        sid = first.get("id")
        ext_id = str(sid) if sid is not None else None
        al = first.get("al") or {}
        art_url = al.get("picUrl")
        if isinstance(art_url, str) and art_url.startswith("http://"):
            art_url = art_url.replace("http://", "https://", 1)
        return art_url, ext_id
    except Exception as e:
        print(f"NetEaseWindowsProvider: 元数据查询失败 {e}")
        return None, None


class NetEaseWindowsProvider:
    platformId = "netease"

    def __init__(self) -> None:
        self._lastTitle: Optional[str] = None
        self._lastArt: Optional[str] = None
        self._lastExternalId: Optional[str] = None
        self._logged_non_win = False

    def poll(self) -> Optional[NowPlayingSnapshot]:
        if sys.platform != "win32":
            if not self._logged_non_win:
                print("NetEaseWindowsProvider: 当前平台未实现网易云检测（已预留接口）")
                self._logged_non_win = True
            return None
        pair = _getCurrentNeteaseSongFromWindow()
        if not pair:
            self._lastTitle = None
            self._lastArt = None
            self._lastExternalId = None
            return None
        song, artist = pair
        full = f"{song} - {artist}"
        if full != self._lastTitle:
            self._lastTitle = full
            art, sid = _searchSongMeta(song, artist)
            self._lastArt = art
            self._lastExternalId = sid
        return NowPlayingSnapshot(
            title=full,
            artUrl=self._lastArt,
            platform=self.platformId,
            externalId=self._lastExternalId,
        )
