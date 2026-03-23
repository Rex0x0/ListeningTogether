"""
FastAPI 房间服务：HTTP 快照 + WebSocket 实时事件。
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from MusicFriend.Contracts.ProtocolModels import (
    ChatMessagePayload,
    HelloPayload,
    PlaySeatApprovePayload,
    PlaySeatRejectPayload,
    TrackUpdatePayload,
)
from MusicFriend.Domain.RoomId import isValidRoomId
from MusicFriend.Server.RoomRepository import RoomRepository
from MusicFriend.Server.RoomService import RoomService, buildSnapshotDto, startCleanupTask

_repo = RoomRepository()
_room_service = RoomService(_repo, inactiveThresholdSec=float(os.environ.get("MF_INACTIVE_SEC", "30")))
_cleanup_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _cleanup_task
    interval = float(os.environ.get("MF_CLEANUP_INTERVAL_SEC", "10"))
    _cleanup_task = startCleanupTask(_room_service, interval)
    yield
    if _cleanup_task:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass


def createApp() -> FastAPI:
    app = FastAPI(title="MusicFriend RoomServer", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("MF_CORS_ORIGINS", "*").split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    def _roomListPayload() -> dict:
        rows = [(rid, n) for rid, n in _repo.listRoomsWithMembers() if isValidRoomId(rid)]
        return {
            "rooms": [{"roomId": rid, "memberCount": n} for rid, n in rows],
        }

    # 静态路径须写在 /rooms/{room_id}/snapshot 之前，避免部分路由实现下的匹配歧义
    @app.get("/rooms")
    async def listRooms() -> dict:
        """供客户端展示可加入的房间列表（仅包含有在线成员的房间）。"""
        return _roomListPayload()

    @app.get("/api/rooms")
    async def listRoomsApiAlias() -> dict:
        """HTTP 列表备用路径，便于反代只转发 /api 前缀。"""
        return _roomListPayload()

    @app.get("/rooms/{room_id}/snapshot")
    async def httpSnapshot(room_id: str) -> dict:
        if not isValidRoomId(room_id):
            raise HTTPException(status_code=400, detail="房间 ID 必须为 4 位数字")
        return buildSnapshotDto(_repo, room_id).model_dump()

    async def _roomListWebsocketHandler(websocket: WebSocket) -> None:
        """连接后下发房间列表 JSON 并关闭（无需客户端发帧）。"""
        await websocket.accept()
        try:
            await websocket.send_text(json.dumps(_roomListPayload(), ensure_ascii=False))
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass

    # 须写在 /ws/room/{room_id} 之前，且路径与房间 WS 同前缀，避免反代仅放行 /ws/room/* 时 403
    @app.websocket("/ws/room/_list")
    async def roomListOnRoomPrefixWebsocket(websocket: WebSocket) -> None:
        """与 GET /rooms 相同；供与 /ws/room/1024 共用一条反代规则的环境。"""
        await _roomListWebsocketHandler(websocket)

    @app.websocket("/ws/directory")
    async def roomDirectoryWebsocket(websocket: WebSocket) -> None:
        """历史备用路径；部分环境会拦截路径名 directory。"""
        await _roomListWebsocketHandler(websocket)

    @app.websocket("/ws/room/{room_id}")
    async def roomWebsocket(websocket: WebSocket, room_id: str) -> None:
        await websocket.accept()
        if not isValidRoomId(room_id):
            await websocket.close(code=4400)
            return
        member_id: str | None = None
        try:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            if data.get("type") != "hello":
                await websocket.close(code=4400)
                return
            pl = data.get("payload") or {}
            hello = HelloPayload.model_validate(pl)
            member_id = await _room_service.registerMember(
                room_id,
                hello.displayName,
                hello.platform,
                websocket,
            )
            while True:
                raw2 = await websocket.receive_text()
                msg = json.loads(raw2)
                mtype = msg.get("type")
                if mtype == "trackUpdate" and member_id:
                    p = TrackUpdatePayload.model_validate(msg.get("payload") or {})
                    await _room_service.handleTrackUpdate(
                        member_id,
                        p.title,
                        p.artUrl,
                        p.platform,
                        p.externalId,
                    )
                elif mtype == "ping" and member_id:
                    await _room_service.handlePing(member_id)
                    await _room_service.sendPong(member_id)
                elif mtype == "chatMessage" and member_id:
                    cp = ChatMessagePayload.model_validate(msg.get("payload") or {})
                    await _room_service.handleChatMessage(member_id, cp.message)
                elif mtype == "playSeatRequest" and member_id:
                    await _room_service.handlePlaySeatRequest(member_id)
                elif mtype == "playSeatApprove" and member_id:
                    ap = PlaySeatApprovePayload.model_validate(msg.get("payload") or {})
                    await _room_service.handlePlaySeatApprove(member_id, ap.requestId)
                elif mtype == "playSeatReject" and member_id:
                    rp = PlaySeatRejectPayload.model_validate(msg.get("payload") or {})
                    await _room_service.handlePlaySeatReject(member_id, rp.requestId)
                elif mtype == "hello":
                    continue
        except WebSocketDisconnect:
            pass
        finally:
            if member_id:
                await _room_service.unregisterMember(member_id)

    return app
