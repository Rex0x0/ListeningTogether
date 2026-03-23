"""
客户端与服务端共用的 Pydantic 载荷（JSON 友好）。
含聊天、房主、播放位、音频流等预留字段，首迭代可为空或省略。
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from MusicFriend.Domain.Enums import RoomEventType


class TrackStateDto(BaseModel):
    title: str = ""
    artUrl: Optional[str] = None
    platform: str = "unknown"
    updatedAtEpoch: float = 0.0


class MemberDto(BaseModel):
    memberId: str
    displayName: str
    track: TrackStateDto
    role: str = "member"
    presenceState: str = "online"
    seatId: Optional[str] = None
    playSeatId: Optional[str] = None
    lastSeenEpoch: float = 0.0


class RoomSnapshotDto(BaseModel):
    roomId: str
    members: List[MemberDto] = Field(default_factory=list)
    hostMemberId: Optional[str] = None


class HelloPayload(BaseModel):
    displayName: str
    platform: str = "unknown"


class TrackUpdatePayload(BaseModel):
    title: str = ""
    artUrl: Optional[str] = None
    platform: str = "unknown"


class PingPayload(BaseModel):
    pass


class ClientEnvelope(BaseModel):
    """客户端 → 服务端"""

    type: Literal["hello", "trackUpdate", "ping"]
    payload: Union[HelloPayload, TrackUpdatePayload, PingPayload, Dict[str, Any]]


class RoomEventPayloadDto(BaseModel):
    """通用事件载荷；按 type 解读字段。"""

    model_config = {"extra": "allow"}

    # trackUpdated 等
    title: Optional[str] = None
    artUrl: Optional[str] = None
    platform: Optional[str] = None
    # 预留：聊天
    message: Optional[str] = None
    # 预留：播放位
    requestId: Optional[str] = None
    targetMemberId: Optional[str] = None
    # 预留：音频转发控制面
    streamId: Optional[str] = None
    sdp: Optional[str] = None


class ServerEventDto(BaseModel):
    type: RoomEventType
    roomId: str
    memberId: Optional[str] = None
    payload: RoomEventPayloadDto = Field(default_factory=RoomEventPayloadDto)


class ServerEnvelope(BaseModel):
    """服务端 → 客户端"""

    type: Literal["snapshot", "event", "pong", "error"]
    payload: Union[RoomSnapshotDto, ServerEventDto, Dict[str, Any], str]
