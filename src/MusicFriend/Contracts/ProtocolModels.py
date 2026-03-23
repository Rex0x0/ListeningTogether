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
    externalId: Optional[str] = None
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
    # 当前占用公共播放位的成员（无则 None）
    playSeatMemberId: Optional[str] = None


class HelloPayload(BaseModel):
    displayName: str
    platform: str = "unknown"


class TrackUpdatePayload(BaseModel):
    title: str = ""
    artUrl: Optional[str] = None
    platform: str = "unknown"
    externalId: Optional[str] = None


class PingPayload(BaseModel):
    pass


class ChatMessagePayload(BaseModel):
    """公共聊天：客户端上行"""

    message: str = ""


class PlaySeatRequestPayload(BaseModel):
    """申请占用公共播放位（上行）。"""

    pass


class PlaySeatApprovePayload(BaseModel):
    """房主通过播放位申请。"""

    requestId: str


class PlaySeatRejectPayload(BaseModel):
    """房主拒绝播放位申请。"""

    requestId: str


class ClientEnvelope(BaseModel):
    """客户端 → 服务端"""

    type: Literal[
        "hello",
        "trackUpdate",
        "ping",
        "chatMessage",
        "playSeatRequest",
        "playSeatApprove",
        "playSeatReject",
    ]
    payload: Union[
        HelloPayload,
        TrackUpdatePayload,
        PingPayload,
        ChatMessagePayload,
        PlaySeatRequestPayload,
        PlaySeatApprovePayload,
        PlaySeatRejectPayload,
        Dict[str, Any],
    ]


class RoomEventPayloadDto(BaseModel):
    """通用事件载荷；按 type 解读字段。"""

    model_config = {"extra": "allow"}

    # trackUpdated 等
    title: Optional[str] = None
    artUrl: Optional[str] = None
    platform: Optional[str] = None
    externalId: Optional[str] = None
    # 聊天（chatMessageSent：正文与发送者展示名）
    message: Optional[str] = None
    senderDisplayName: Optional[str] = None
    # 播放位
    requestId: Optional[str] = None
    targetMemberId: Optional[str] = None
    applicantMemberId: Optional[str] = None
    applicantDisplayName: Optional[str] = None
    # 预留：音频转发控制面
    streamId: Optional[str] = None
    sdp: Optional[str] = None


class ServerEventDto(BaseModel):
    type: RoomEventType
    roomId: str
    memberId: Optional[str] = None
    payload: RoomEventPayloadDto = Field(default_factory=RoomEventPayloadDto)


class AssignedPayload(BaseModel):
    """连接成功后下发当前连接的 memberId，供客户端识别自身。"""

    memberId: str


class ServerEnvelope(BaseModel):
    """服务端 → 客户端"""

    type: Literal["snapshot", "event", "pong", "error", "assigned"]
    payload: Union[RoomSnapshotDto, ServerEventDto, AssignedPayload, Dict[str, Any], str]
