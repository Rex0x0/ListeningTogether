"""
桌面内嵌用本地 HTTP + Socket.IO 服务：仅向本机提供新版网页 UI，与正式房间服务分离。
使用 threading 模式，避免与 Qt / eventlet 抢事件循环。
"""

from __future__ import annotations

import os
import socket
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Flask, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, emit as sio_emit


def resolve_project_root() -> Path:
    """开发目录或 PyInstaller 解压目录下解析项目根（含 templates、static）。"""
    env = os.environ.get("MF_PROJECT_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()
    # src/MusicFriend/Desktop/LocalWebUiServer.py -> 根为 parents[3]
    return Path(__file__).resolve().parents[3]


def pick_listen_port(preferred: Optional[int] = None) -> int:
    if preferred and preferred > 0:
        return int(preferred)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class LocalWebUiServer:
    """在后台线程中运行 Flask-SocketIO；从任意线程在 app_context 下广播事件。"""

    def __init__(self, *, project_root: Optional[Path] = None, port: Optional[int] = None) -> None:
        root = project_root or resolve_project_root()
        self._root = root
        pref = port
        if pref is None:
            env_p = os.environ.get("MF_LOCAL_WEB_UI_PORT", "").strip()
            pref = int(env_p) if env_p.isdigit() else None
        self._port = pick_listen_port(pref)

        tpl = root / "templates"
        static = root / "static"
        self._app = Flask(
            __name__,
            template_folder=str(tpl),
            static_folder=str(static),
            static_url_path="/static",
        )
        CORS(self._app)
        self._socketio = SocketIO(
            self._app,
            async_mode="threading",
            cors_allowed_origins="*",
        )
        self._thread: Optional[threading.Thread] = None
        # 网页 Socket 客户端若晚于首帧快照连接，连接时补发最后一次快照，避免座位长期空白
        self._last_room_snapshot: Optional[Dict[str, Any]] = None
        self._last_self_member: Optional[str] = None
        self._last_session_state: Optional[Dict[str, Any]] = None
        self._register_routes()

    @property
    def port(self) -> int:
        return self._port

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    def _register_routes(self) -> None:
        @self._app.route("/")
        def index() -> str:
            return render_template("index.html")

        @self._socketio.on("connect")
        def _on_sio_connect() -> None:
            if self._last_room_snapshot is not None:
                sio_emit("room_snapshot", self._last_room_snapshot)
            if self._last_self_member is not None:
                sio_emit("self_member", {"memberId": self._last_self_member})
            if self._last_session_state is not None:
                sio_emit("session_state", self._last_session_state)

    def emit_room_snapshot(self, payload: Dict[str, Any]) -> None:
        """向所有连接的网页客户端推送房间视图快照。"""
        self._last_room_snapshot = payload
        with self._app.app_context():
            self._socketio.emit("room_snapshot", payload, namespace="/")

    def emit_room_event(self, payload: Dict[str, Any]) -> None:
        """推送单条房间领域事件（聊天、播放位等）。"""
        with self._app.app_context():
            self._socketio.emit("room_event", payload, namespace="/")

    def emit_connection_status(self, text: str) -> None:
        with self._app.app_context():
            self._socketio.emit("connection_status", {"text": text}, namespace="/")

    def emit_self_member(self, member_id: Optional[str]) -> None:
        """下发本连接在房间服务中的 memberId，供网页判断房主/播放位按钮状态。"""
        mid = member_id or ""
        self._last_self_member = mid
        with self._app.app_context():
            self._socketio.emit("self_member", {"memberId": mid}, namespace="/")

    def emit_session_state(self, payload: Dict[str, Any]) -> None:
        """同步当前昵称、房间号、房间列表等，供右侧栏与页刷新后恢复。"""
        self._last_session_state = dict(payload)
        with self._app.app_context():
            self._socketio.emit("session_state", self._last_session_state, namespace="/")

    def start_background(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        def run() -> None:
            # use_reloader=False：避免子进程与固定端口冲突
            self._socketio.run(
                self._app,
                host="127.0.0.1",
                port=self._port,
                debug=False,
                use_reloader=False,
                allow_unsafe_werkzeug=True,
            )

        self._thread = threading.Thread(target=run, name="MusicFriendLocalWebUi", daemon=True)
        self._thread.start()
