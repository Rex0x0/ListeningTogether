"""
桌面客户端唯一正式发布入口（PySide6，Win / macOS 共用）。
主界面为内嵌本地网页（QWebEngineView），房间状态仍走正式 WebSocket 房间服务。
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path
from typing import Optional

# 与 PyInstaller 打包后的工作目录兼容：优先将源码根加入路径
_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# 必须在导入任何 WebEngine 模块之前生效（见 WebEngineBootstrap 说明）
from MusicFriend.Desktop.WebEngineBootstrap import apply_webengine_platform_defaults  # noqa: E402

apply_webengine_platform_defaults()

# 规避部分环境下系统代理导致 requests/websocket 超时
os.environ["HTTP_PROXY"] = ""
os.environ["HTTPS_PROXY"] = ""
os.environ["http_proxy"] = ""
os.environ["https_proxy"] = ""

if not (os.environ.get("MF_PROJECT_ROOT") or "").strip():
    os.environ["MF_PROJECT_ROOT"] = str(_ROOT)

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Slot  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from MusicFriend.Desktop.LocalWebUiServer import LocalWebUiServer  # noqa: E402
from MusicFriend.Desktop.QtDesignTokens import application_stylesheet  # noqa: E402
from MusicFriend.Desktop.RoomMainWindow import (  # noqa: E402
    SongDetectorWorker,
    _generateRandomRoomId,
    fetchRoomListJsonFromHttpBase,
)
from MusicFriend.Desktop.RoomWebSocketWorker import RoomWebSocketWorker  # noqa: E402
from MusicFriend.Desktop.RoomWebUiAdapter import WebRoomStateBuilder  # noqa: E402
from MusicFriend.Desktop.WebRoomWindow import WebRoomWindow  # noqa: E402
from MusicFriend.Desktop.WebShellBridge import WebFollowCoordinator, WebShellBridge  # noqa: E402
from MusicFriend.Domain.RoomId import isValidRoomId  # noqa: E402
from MusicFriend.Integrations.FollowPlaybackController import FollowPlaybackController  # noqa: E402


def _wait_local_http_port(port: int, timeout_sec: float = 8.0) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def _normalize_room_list_items(raw: list) -> list[dict]:
    out: list[dict] = []
    for item in raw:
        if isinstance(item, dict) and item.get("roomId"):
            out.append({"roomId": str(item["roomId"]), "memberCount": int(item.get("memberCount", 0) or 0)})
    return out


class DesktopRoomLifecycle(QObject):
    """可重复建立 WebSocket：切房、改名后重连；与网页桥接、跟播、本地 Socket.IO 同步。"""

    def __init__(
        self,
        *,
        main_win: WebRoomWindow,
        local_server: LocalWebUiServer,
        http_base: str,
        display_name: str,
        platform: str,
        room_id: str,
        follow_coord: WebFollowCoordinator,
        state_builder: WebRoomStateBuilder,
        bridge: WebShellBridge,
        ping_timer: QTimer,
        detector: SongDetectorWorker,
    ) -> None:
        super().__init__(parent=main_win)
        self._main_win = main_win
        self._local = local_server
        self._http_base = http_base.rstrip("/")
        self._display_name = display_name.strip() or "游客"
        self._platform = (platform or "netease").strip().lower()
        self._room_id = room_id
        self._follow_coord = follow_coord
        self._state_builder = state_builder
        self._bridge = bridge
        self._ping_timer = ping_timer
        self._detector = detector
        self._ws_worker: Optional[RoomWebSocketWorker] = None
        self._suppress_ws_err_until = 0.0

    def _push_session_state(self) -> None:
        rooms_norm: Optional[list] = None
        try:
            raw = fetchRoomListJsonFromHttpBase(self._http_base)
            rooms_norm = _normalize_room_list_items(raw)
        except Exception:
            pass
        payload: dict = {
            "displayName": self._display_name,
            "roomId": self._room_id,
            "platform": self._platform,
            "serverUrl": self._http_base,
        }
        if rooms_norm is not None:
            payload["rooms"] = rooms_norm
        self._local.emit_session_state(payload)

    def _on_snapshot(self, payload: dict) -> None:
        web_payload = self._state_builder.build(payload)
        self._follow_coord.apply_web_snapshot(web_payload)
        self._local.emit_room_snapshot(web_payload)

    @Slot(str)
    def _on_event(self, raw: str) -> None:
        try:
            evt = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return
        self._follow_coord.handle_room_event_dict(evt)
        self._local.emit_room_event(evt)

    @Slot(str)
    def _on_member_assigned(self, mid: str) -> None:
        self._follow_coord.set_self_member_id(mid)
        self._local.emit_self_member(mid)

    @Slot(str)
    def _on_ws_err(self, msg: str) -> None:
        if time.monotonic() < self._suppress_ws_err_until:
            return
        self._local.emit_connection_status("房间连接异常 · 详见弹窗")
        hint = ""
        if any(
            x in msg
            for x in (
                "10061",
                "积极拒绝",
                "Connection refused",
                "Errno 111",
            )
        ):
            hint = (
                "\n\n请先启动「房间服务」（监听 8765）：\n"
                "• 在项目根目录执行：scripts\\RunRoomServer.ps1\n"
                "或：python apps\\RoomServer\\Main.py\n"
                "若连远程服务器，请设置环境变量 MF_SERVER_URL 为正确的服务地址。"
            )
        QMessageBox.warning(self._main_win, "连接异常", msg + hint)

    def _teardown_worker(self) -> None:
        try:
            self._ping_timer.timeout.disconnect()
        except TypeError:
            pass
        try:
            self._detector.song_detected.disconnect()
        except TypeError:
            pass
        old = self._ws_worker
        if old is None:
            return
        for sig, slot in (
            (old.snapshotReceived, self._on_snapshot),
            (old.eventReceived, self._on_event),
            (old.memberIdAssigned, self._on_member_assigned),
            (old.connectionFailed, self._on_ws_err),
        ):
            try:
                sig.disconnect(slot)
            except TypeError:
                pass
        old.closeConnection()
        old.deleteLater()
        self._ws_worker = None

    def _bind_ping_and_detector(self, ws: RoomWebSocketWorker) -> None:
        try:
            self._ping_timer.timeout.disconnect()
        except TypeError:
            pass
        try:
            self._detector.song_detected.disconnect()
        except TypeError:
            pass
        self._ping_timer.timeout.connect(ws.sendPing, Qt.QueuedConnection)
        self._detector.song_detected.connect(ws.sendTrackFromDetector, Qt.QueuedConnection)

    def attach_worker(self, ws: RoomWebSocketWorker) -> None:
        """首次挂载 WebSocket 工作器（启动时调用一次）。"""
        ws.setParent(self)
        self._ws_worker = ws
        ws.snapshotReceived.connect(self._on_snapshot, Qt.QueuedConnection)
        ws.eventReceived.connect(self._on_event, Qt.QueuedConnection)
        ws.memberIdAssigned.connect(self._on_member_assigned, Qt.QueuedConnection)
        ws.connectionFailed.connect(self._on_ws_err, Qt.QueuedConnection)
        self._bridge.bind_room_actions(
            send_chat=ws.sendChatMessage,
            request_play_seat=ws.sendPlaySeatRequest,
            approve_play_seat=ws.sendPlaySeatApprove,
            reject_play_seat=ws.sendPlaySeatReject,
            follow=self._follow_coord,
        )
        self._bind_ping_and_detector(ws)
        self._push_session_state()

    def reconnect_room(self, room_id: str, *, display_name: Optional[str] = None) -> None:
        """切换房间或改名后重建连接（会短暂忽略旧连接上的误报错误）。"""
        if display_name is not None:
            self._display_name = (display_name.strip() or "游客")
        self._room_id = room_id
        self._suppress_ws_err_until = time.monotonic() + 1.2
        self._follow_coord.set_self_member_id(None)
        self._local.emit_self_member("")
        self._teardown_worker()
        ws = RoomWebSocketWorker(self._http_base, self._room_id, self._display_name, self._platform)
        self.attach_worker(ws)
        self._main_win.apply_session_labels(self._room_id, self._display_name)
        self._local.emit_connection_status("正在连接房间服务…")
        QTimer.singleShot(0, ws.connectAndRun)

    def get_session_json(self) -> str:
        return json.dumps(
            {
                "ok": True,
                "displayName": self._display_name,
                "roomId": self._room_id,
                "platform": self._platform,
                "serverUrl": self._http_base,
            },
            ensure_ascii=False,
        )

    def fetch_rooms_json(self) -> str:
        try:
            raw = fetchRoomListJsonFromHttpBase(self._http_base)
            rooms = _normalize_room_list_items(raw)
            return json.dumps({"ok": True, "rooms": rooms}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "message": str(e)}, ensure_ascii=False)

    def create_room_json(self) -> str:
        rid = _generateRandomRoomId()
        self.reconnect_room(rid)
        return json.dumps({"ok": True, "roomId": rid}, ensure_ascii=False)

    def switch_room_json(self, room_id: str) -> str:
        rid = (room_id or "").strip()
        if not isValidRoomId(rid):
            return json.dumps({"ok": False, "message": "房间号须为恰好 4 位数字（0000–9999）。"}, ensure_ascii=False)
        if rid == self._room_id:
            self._push_session_state()
            return json.dumps({"ok": True, "roomId": rid, "unchanged": True}, ensure_ascii=False)
        self._local.emit_connection_status("正在切换房间…")
        self.reconnect_room(rid)
        return json.dumps({"ok": True, "roomId": rid}, ensure_ascii=False)

    def set_display_name_json(self, name: str) -> str:
        n = (name or "").strip() or "游客"
        if n == self._display_name:
            self._push_session_state()
            return json.dumps({"ok": True, "displayName": n, "unchanged": True}, ensure_ascii=False)
        self._local.emit_connection_status("正在用新昵称重新连接…")
        self.reconnect_room(self._room_id, display_name=n)
        return json.dumps({"ok": True, "displayName": n}, ensure_ascii=False)

    def shutdown(self) -> None:
        self._teardown_worker()


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(application_stylesheet())

    default_srv = (os.environ.get("MF_SERVER_URL", "http://127.0.0.1:8765") or "").strip().rstrip("/") or "http://127.0.0.1:8765"
    http_base = default_srv
    display_name = "游客"
    platform = "netease"
    initial_room_id = _generateRandomRoomId()

    local_server = LocalWebUiServer(project_root=_ROOT)
    local_server.start_background()
    if not _wait_local_http_port(local_server.port):
        QMessageBox.warning(
            None,
            "本地网页服务",
            f"无法在超时内启动本地网页服务（端口 {local_server.port}）。\n请检查防火墙或更换 MF_LOCAL_WEB_UI_PORT 后重试。",
        )
        sys.exit(1)

    follow_ctrl = FollowPlaybackController(platform)
    follow_coord = WebFollowCoordinator(platform, follow_ctrl)
    state_builder = WebRoomStateBuilder()
    bridge = WebShellBridge()

    start_url = f"{local_server.base_url}/"
    main_win = WebRoomWindow(
        start_url=start_url,
        bridge=bridge,
        room_id=initial_room_id,
        display_name=display_name,
    )

    ping_ms = int(float(os.environ.get("MF_PING_INTERVAL_SEC", "15")) * 1000)
    ping_timer = QTimer(main_win)
    ping_timer.setInterval(max(ping_ms, 3000))

    det_thread = QThread()
    detector = SongDetectorWorker(platform)
    detector.moveToThread(det_thread)
    det_thread.started.connect(detector.run)

    lifecycle = DesktopRoomLifecycle(
        main_win=main_win,
        local_server=local_server,
        http_base=http_base,
        display_name=display_name,
        platform=platform,
        room_id=initial_room_id,
        follow_coord=follow_coord,
        state_builder=state_builder,
        bridge=bridge,
        ping_timer=ping_timer,
        detector=detector,
    )

    ws_worker = RoomWebSocketWorker(http_base, initial_room_id, display_name, platform)
    lifecycle.attach_worker(ws_worker)

    bridge.bind_session_actions(
        get_session_json=lifecycle.get_session_json,
        fetch_rooms_json=lifecycle.fetch_rooms_json,
        create_room_json=lifecycle.create_room_json,
        switch_room_json=lifecycle.switch_room_json,
        set_display_name_json=lifecycle.set_display_name_json,
    )

    det_thread.start()
    ping_timer.start()
    QTimer.singleShot(0, ws_worker.connectAndRun)
    main_win.show()

    def on_about_to_quit() -> None:
        ping_timer.stop()
        detector.stop()
        det_thread.quit()
        det_thread.wait(8000)
        lifecycle.shutdown()

    app.aboutToQuit.connect(on_about_to_quit)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
