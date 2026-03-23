"""
QWebChannel 桥接：网页调用发聊天、播放位、跟播；桌面侧连接房间 WebSocket 与跟播控制器。
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, Signal, Slot

from MusicFriend.Integrations.FollowPlaybackController import FollowPlaybackController


class WebFollowCoordinator(QObject):
    """根据网页用快照与房间事件维护播放位状态，并驱动跟播。"""

    def __init__(self, platform: str, follow_ctrl: FollowPlaybackController, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._platform = (platform or "").strip().lower()
        self._follow_ctrl = follow_ctrl
        self._self_member_id: Optional[str] = None
        self._play_seat_member_id: Optional[str] = None
        self._play_seat_platform: Optional[str] = None
        self._play_seat_external_id: Optional[str] = None
        self._follow = False
        self._last_applied: Optional[str] = None

    def set_self_member_id(self, mid: Optional[str]) -> None:
        self._self_member_id = (mid or None) and str(mid)

    def apply_web_snapshot(self, snap: dict) -> None:
        """snap 为 build_web_room_state 的结果（含 playSeat、playSeatMemberId）。"""
        ps = snap.get("playSeatMemberId")
        self._play_seat_member_id = str(ps) if ps else None
        pseat = snap.get("playSeat")
        if pseat:
            self._play_seat_platform = ((pseat.get("platform") or "unknown").strip() or "unknown")
            ex = pseat.get("externalId")
            self._play_seat_external_id = str(ex).strip() if ex else None
        else:
            self._play_seat_platform = None
            self._play_seat_external_id = None

        if self._follow and (
            not self._play_seat_member_id
            or self._platform_mismatch()
            or (self._self_member_id and self._play_seat_member_id == self._self_member_id)
        ):
            self._follow = False
            self._last_applied = None
        self._maybe_follow(show_errors=False)

    def handle_room_event_dict(self, evt: dict) -> None:
        """解析房间服务下发的 event 载荷（与 RoomMainWindow.on_event 一致）。"""
        typ = evt.get("type")
        if typ != "trackUpdated":
            return
        um = evt.get("memberId")
        ps = self._play_seat_member_id
        if not um or not ps or str(um) != str(ps):
            return
        inner = evt.get("payload") or {}
        p = inner.get("platform")
        if p is not None:
            self._play_seat_platform = str(p).strip() or "unknown"
        ex = inner.get("externalId")
        if ex is not None:
            self._play_seat_external_id = str(ex).strip() if ex else None
        if self._follow and self._platform_mismatch():
            self._follow = False
            self._last_applied = None
        self._maybe_follow(show_errors=False)

    def _platform_mismatch(self) -> bool:
        p = self._play_seat_platform
        return p not in (None, "unknown") and p != self._platform

    def _maybe_follow(self, *, show_errors: bool) -> Optional[str]:
        if not self._follow or not self._play_seat_member_id:
            return None
        if self._self_member_id and self._play_seat_member_id == self._self_member_id:
            return None
        plat = self._play_seat_platform or ""
        if not plat or plat == "unknown" or plat != self._platform:
            return None
        ext = (self._play_seat_external_id or "").strip()
        if not ext:
            self._last_applied = None
            return None
        if ext == self._last_applied:
            return None
        ok, err = self._follow_ctrl.play(ext)
        if ok:
            self._last_applied = ext
            return None
        if show_errors:
            return err or "跟播失败"
        return None

    @Slot(result=str)
    def toggle_follow(self) -> str:
        """返回 JSON：{"ok":true} 或 {"ok":false,"message":"..."}。"""
        if self._follow:
            self._follow = False
            self._last_applied = None
            return json.dumps({"ok": True, "following": False}, ensure_ascii=False)
        if not self._play_seat_member_id:
            return json.dumps({"ok": False, "message": "当前无人占用播放位。"}, ensure_ascii=False)
        if self._self_member_id and self._play_seat_member_id == self._self_member_id:
            return json.dumps({"ok": False, "message": "你已在播放位，无需跟播。"}, ensure_ascii=False)
        plat = self._play_seat_platform or ""
        if not plat or plat == "unknown":
            return json.dumps({"ok": False, "message": "暂无法确认播放位的音乐软件，请稍候再试。"}, ensure_ascii=False)
        if plat != self._platform:
            return json.dumps(
                {"ok": False, "message": "仅支持与播放位使用相同音乐软件时才能跟播。"},
                ensure_ascii=False,
            )
        self._follow = True
        self._last_applied = None
        err = self._maybe_follow(show_errors=True)
        if err:
            self._follow = False
            self._last_applied = None
            return json.dumps({"ok": False, "message": err}, ensure_ascii=False)
        return json.dumps({"ok": True, "following": True}, ensure_ascii=False)

    @Slot(result=str)
    def follow_status_json(self) -> str:
        return json.dumps({"following": self._follow}, ensure_ascii=False)


class WebShellBridge(QObject):
    """注册为 qt_bridge，供 index.html 调用。"""

    sync_started = Signal(str, str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._send_chat: Optional[Callable[[str], Any]] = None
        self._request_play_seat: Optional[Callable[[], Any]] = None
        self._approve_play_seat: Optional[Callable[[str], Any]] = None
        self._reject_play_seat: Optional[Callable[[str], Any]] = None
        self._follow: Optional[WebFollowCoordinator] = None
        self._get_session_json: Optional[Callable[[], str]] = None
        self._fetch_rooms_json: Optional[Callable[[], str]] = None
        self._create_room_json: Optional[Callable[[], str]] = None
        self._switch_room_json: Optional[Callable[[str], str]] = None
        self._set_display_name_json: Optional[Callable[[str], str]] = None

    def bind_room_actions(
        self,
        *,
        send_chat: Callable[[str], Any],
        request_play_seat: Callable[[], Any],
        approve_play_seat: Callable[[str], Any],
        reject_play_seat: Callable[[str], Any],
        follow: WebFollowCoordinator,
    ) -> None:
        self._send_chat = send_chat
        self._request_play_seat = request_play_seat
        self._approve_play_seat = approve_play_seat
        self._reject_play_seat = reject_play_seat
        self._follow = follow

    def bind_session_actions(
        self,
        *,
        get_session_json: Callable[[], str],
        fetch_rooms_json: Callable[[], str],
        create_room_json: Callable[[], str],
        switch_room_json: Callable[[str], str],
        set_display_name_json: Callable[[str], str],
    ) -> None:
        """由 Main 注入：房间列表、切房、改名等（返回 JSON 字符串）。"""
        self._get_session_json = get_session_json
        self._fetch_rooms_json = fetch_rooms_json
        self._create_room_json = create_room_json
        self._switch_room_json = switch_room_json
        self._set_display_name_json = set_display_name_json

    @Slot(str, str)
    def start_sync(self, username: str, platform: str) -> None:
        """浏览器独立打开页面时使用；桌面嵌入时也可作为重新开始检测的入口。"""
        self.sync_started.emit((username or "").strip(), (platform or "").strip().lower())

    @Slot(str)
    def send_chat(self, text: str) -> None:
        t = (text or "").strip()
        if not t or not self._send_chat:
            return
        self._send_chat(t)

    @Slot()
    def request_play_seat(self) -> None:
        if self._request_play_seat:
            self._request_play_seat()

    @Slot(str)
    def approve_play_seat(self, request_id: str) -> None:
        if self._approve_play_seat:
            self._approve_play_seat((request_id or "").strip())

    @Slot(str)
    def reject_play_seat(self, request_id: str) -> None:
        if self._reject_play_seat:
            self._reject_play_seat((request_id or "").strip())

    @Slot(result=str)
    def toggle_follow(self) -> str:
        if not self._follow:
            return json.dumps({"ok": False, "message": "跟播未初始化"}, ensure_ascii=False)
        return self._follow.toggle_follow()

    @Slot(result=str)
    def follow_status_json(self) -> str:
        if not self._follow:
            return json.dumps({"following": False}, ensure_ascii=False)
        return self._follow.follow_status_json()

    @Slot(result=str)
    def get_session_json(self) -> str:
        if not self._get_session_json:
            return json.dumps({"ok": False, "message": "会话未就绪"}, ensure_ascii=False)
        return self._get_session_json()

    @Slot(result=str)
    def fetch_room_list_json(self) -> str:
        if not self._fetch_rooms_json:
            return json.dumps({"ok": False, "message": "房间列表未就绪"}, ensure_ascii=False)
        return self._fetch_rooms_json()

    @Slot(result=str)
    def create_room_json(self) -> str:
        if not self._create_room_json:
            return json.dumps({"ok": False, "message": "创建房间未就绪"}, ensure_ascii=False)
        return self._create_room_json()

    @Slot(str, result=str)
    def switch_room_json(self, room_id: str) -> str:
        if not self._switch_room_json:
            return json.dumps({"ok": False, "message": "切换房间未就绪"}, ensure_ascii=False)
        return self._switch_room_json((room_id or "").strip())

    @Slot(str, result=str)
    def set_display_name_json(self, display_name: str) -> str:
        if not self._set_display_name_json:
            return json.dumps({"ok": False, "message": "改名未就绪"}, ensure_ascii=False)
        return self._set_display_name_json(display_name or "")
