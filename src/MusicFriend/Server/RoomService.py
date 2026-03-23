"""
房间应用服务：成员生命周期、曲目更新、广播快照与领域事件。
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Dict, List, Optional

from fastapi import WebSocket

from MusicFriend.Contracts.ProtocolModels import (
    AssignedPayload,
    MemberDto,
    RoomEventPayloadDto,
    RoomSnapshotDto,
    ServerEnvelope,
    ServerEventDto,
    TrackStateDto,
)
from MusicFriend.Domain.Enums import RoomEventType
from MusicFriend.Domain.Models import Member
from MusicFriend.Server.RoomRepository import RoomRepository

# 单条聊天最大字符数（防刷屏与超大帧）
_MAX_CHAT_MESSAGE_LEN = 500


def _memberToDto(m: Member) -> MemberDto:
    return MemberDto(
        memberId=m.memberId,
        displayName=m.displayName,
        track=TrackStateDto(
            title=m.track.title,
            artUrl=m.track.artUrl,
            platform=m.track.platform,
            externalId=m.track.externalId,
            updatedAtEpoch=m.track.updatedAtEpoch,
        ),
        role=m.role.value,
        presenceState=m.presenceState.value,
        seatId=m.seatId,
        playSeatId=m.playSeatId,
        lastSeenEpoch=m.lastSeenEpoch,
    )


def buildSnapshotDto(repo: RoomRepository, roomId: str) -> RoomSnapshotDto:
    room = repo.getOrCreateRoom(roomId)
    members = [_memberToDto(m) for m in room.members.values()]
    return RoomSnapshotDto(
        roomId=roomId,
        members=members,
        hostMemberId=room.hostMemberId,
        playSeatMemberId=room.playSeatMemberId,
    )


class RoomService:
    """协调仓储与 WebSocket 连接。"""

    def __init__(
        self,
        repo: RoomRepository,
        inactiveThresholdSec: float = 30.0,
    ) -> None:
        self._repo = repo
        self._inactiveThresholdSec = inactiveThresholdSec
        # memberId -> websocket
        self._sockets: Dict[str, WebSocket] = {}
        # memberId -> roomId
        self._memberRoom: Dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def registerMember(
        self,
        roomId: str,
        displayName: str,
        platform: str,
        websocket: WebSocket,
    ) -> str:
        memberId = str(uuid.uuid4())
        async with self._lock:
            self._repo.upsertMember(roomId, memberId, displayName, platform)
            self._sockets[memberId] = websocket
            self._memberRoom[memberId] = roomId
        await self._sendAssigned(memberId)
        await self._broadcastSnapshot(roomId)
        await self._broadcastEvent(
            roomId,
            ServerEventDto(
                type=RoomEventType.memberJoined,
                roomId=roomId,
                memberId=memberId,
                payload=RoomEventPayloadDto(),
            ),
        )
        return memberId

    async def unregisterMember(self, memberId: str) -> None:
        async with self._lock:
            roomId = self._memberRoom.pop(memberId, None)
            self._sockets.pop(memberId, None)
            if not roomId:
                return
            self._repo.removeMemberIfPresent(roomId, memberId)
        await self._broadcastSnapshot(roomId)
        await self._broadcastEvent(
            roomId,
            ServerEventDto(
                type=RoomEventType.memberLeft,
                roomId=roomId,
                memberId=memberId,
                payload=RoomEventPayloadDto(),
            ),
        )

    async def handleTrackUpdate(
        self,
        memberId: str,
        title: str,
        artUrl: Optional[str],
        platform: str,
        external_id: Optional[str],
    ) -> None:
        async with self._lock:
            roomId = self._memberRoom.get(memberId)
            if not roomId:
                return
            self._repo.updateMemberTrack(roomId, memberId, title, artUrl, platform, external_id)
        await self._broadcastSnapshot(roomId)
        await self._broadcastEvent(
            roomId,
            ServerEventDto(
                type=RoomEventType.trackUpdated,
                roomId=roomId,
                memberId=memberId,
                payload=RoomEventPayloadDto(
                    title=title,
                    artUrl=artUrl,
                    platform=platform,
                    externalId=external_id,
                ),
            ),
        )

    async def handlePing(self, memberId: str) -> None:
        async with self._lock:
            roomId = self._memberRoom.get(memberId)
            if not roomId:
                return
            self._repo.touchMember(roomId, memberId)

    async def handleChatMessage(self, memberId: str, raw_text: str) -> None:
        """广播房间公共聊天；发送成功也会刷新成员 lastSeen。"""
        text = (raw_text or "").strip()
        if not text:
            return
        if len(text) > _MAX_CHAT_MESSAGE_LEN:
            text = text[:_MAX_CHAT_MESSAGE_LEN]
        async with self._lock:
            room_id = self._memberRoom.get(memberId)
            if not room_id:
                return
            room = self._repo.getOrCreateRoom(room_id)
            member = room.members.get(memberId)
            if not member:
                return
            display_name = member.displayName
            self._repo.touchMember(room_id, memberId)
        await self._broadcastEvent(
            room_id,
            ServerEventDto(
                type=RoomEventType.chatMessageSent,
                roomId=room_id,
                memberId=memberId,
                payload=RoomEventPayloadDto(message=text, senderDisplayName=display_name),
            ),
        )

    async def handlePlaySeatRequest(self, memberId: str) -> None:
        """申请公共播放位；房主本人直接占用，其余成员向房主发通知。"""
        room_id: Optional[str] = None
        host_id: Optional[str] = None
        display_name = ""
        request_id: Optional[str] = None
        host_self_seat = False
        async with self._lock:
            room_id = self._memberRoom.get(memberId)
            if not room_id:
                return
            room = self._repo.getOrCreateRoom(room_id)
            host_id = room.hostMemberId
            applicant = room.members.get(memberId)
            if not applicant:
                return
            display_name = applicant.displayName
            if memberId == host_id:
                self._repo.setPlaySeatMember(room_id, memberId)
                host_self_seat = True
            else:
                request_id = self._repo.addPlaySeatRequest(room_id, memberId)
        if host_self_seat:
            if not room_id:
                return
            await self._broadcastSnapshot(room_id)
            await self._broadcastEvent(
                room_id,
                ServerEventDto(
                    type=RoomEventType.playSeatApproved,
                    roomId=room_id,
                    memberId=memberId,
                    payload=RoomEventPayloadDto(targetMemberId=memberId),
                ),
            )
            return
        if not request_id or not host_id or not room_id:
            return
        await self._sendEnvelopeToMember(
            host_id,
            ServerEnvelope(
                type="event",
                payload=ServerEventDto(
                    type=RoomEventType.playSeatRequested,
                    roomId=room_id,
                    memberId=memberId,
                    payload=RoomEventPayloadDto(
                        requestId=request_id,
                        applicantMemberId=memberId,
                        applicantDisplayName=display_name,
                    ),
                ),
            ),
        )

    async def handlePlaySeatApprove(self, actorMemberId: str, requestId: str) -> None:
        """仅房主可通过申请。"""
        async with self._lock:
            room_id = self._memberRoom.get(actorMemberId)
            if not room_id:
                return
            room = self._repo.getOrCreateRoom(room_id)
            if room.hostMemberId != actorMemberId:
                return
            applicant_id = self._repo.takePlaySeatRequest(room_id, requestId)
            if not applicant_id or applicant_id not in room.members:
                return
            self._repo.setPlaySeatMember(room_id, applicant_id)
        await self._broadcastSnapshot(room_id)
        await self._broadcastEvent(
            room_id,
            ServerEventDto(
                type=RoomEventType.playSeatApproved,
                roomId=room_id,
                memberId=applicant_id,
                payload=RoomEventPayloadDto(targetMemberId=applicant_id),
            ),
        )

    async def handlePlaySeatReject(self, actorMemberId: str, requestId: str) -> None:
        """仅房主可拒绝申请。"""
        async with self._lock:
            room_id = self._memberRoom.get(actorMemberId)
            if not room_id:
                return
            room = self._repo.getOrCreateRoom(room_id)
            if room.hostMemberId != actorMemberId:
                return
            applicant_id = self._repo.takePlaySeatRequest(room_id, requestId)
            if not applicant_id:
                return
        await self._broadcastEvent(
            room_id,
            ServerEventDto(
                type=RoomEventType.playSeatRejected,
                roomId=room_id,
                memberId=applicant_id,
                payload=RoomEventPayloadDto(requestId=requestId, applicantMemberId=applicant_id),
            ),
        )

    async def cleanupInactive(self) -> None:
        """扫描所有房间，移除超时成员。"""
        async with self._lock:
            room_ids = list({rid for rid in self._memberRoom.values()})
            stale_ids: List[str] = []
            for room_id in room_ids:
                for mid in self._repo.listStaleMemberIds(room_id, self._inactiveThresholdSec):
                    if mid in self._sockets:
                        stale_ids.append(mid)
        for mid in set(stale_ids):
            ws = self._sockets.get(mid)
            try:
                if ws:
                    await ws.close()
            except Exception:
                pass
            await self.unregisterMember(mid)

    def _roomSubscriberIds(self, roomId: str) -> List[str]:
        return [mid for mid, rid in self._memberRoom.items() if rid == roomId]

    async def _sendEnvelopeToMember(self, memberId: str, env: ServerEnvelope) -> None:
        ws = self._sockets.get(memberId)
        if not ws:
            return
        try:
            await ws.send_text(env.model_dump_json())
        except Exception:
            pass

    async def _sendAssigned(self, memberId: str) -> None:
        env = ServerEnvelope(type="assigned", payload=AssignedPayload(memberId=memberId))
        await self._sendEnvelopeToMember(memberId, env)

    async def _broadcastSnapshot(self, roomId: str) -> None:
        snap = buildSnapshotDto(self._repo, roomId)
        env = ServerEnvelope(type="snapshot", payload=snap)
        text = env.model_dump_json()
        for mid in self._roomSubscriberIds(roomId):
            ws = self._sockets.get(mid)
            if ws:
                try:
                    await ws.send_text(text)
                except Exception:
                    pass

    async def _broadcastEvent(self, roomId: str, event: ServerEventDto) -> None:
        env = ServerEnvelope(type="event", payload=event)
        text = env.model_dump_json()
        for mid in self._roomSubscriberIds(roomId):
            ws = self._sockets.get(mid)
            if ws:
                try:
                    await ws.send_text(text)
                except Exception:
                    pass

    async def sendPong(self, memberId: str) -> None:
        ws = self._sockets.get(memberId)
        if not ws:
            return
        env = ServerEnvelope(type="pong", payload={})
        try:
            await ws.send_text(env.model_dump_json())
        except Exception:
            pass


def startCleanupTask(
    service: RoomService,
    intervalSec: float = 10.0,
) -> asyncio.Task:
    """后台定时清理任务。"""

    async def _loop() -> None:
        while True:
            await asyncio.sleep(intervalSec)
            await service.cleanupInactive()

    return asyncio.create_task(_loop())
