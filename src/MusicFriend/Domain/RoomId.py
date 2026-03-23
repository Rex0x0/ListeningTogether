"""
房间 ID 规则：与服务端路径、客户端输入一致。
"""

from __future__ import annotations

import re

_ROOM_ID_RE = re.compile(r"^\d{4}$")


def isValidRoomId(room_id: str) -> bool:
    """房间 ID 必须为恰好 4 位数字（0000–9999）。"""
    return bool(room_id and _ROOM_ID_RE.fullmatch(room_id))
