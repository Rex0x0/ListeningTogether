"""
FastAPI 房间服务：HTTP 快照 + WebSocket 实时事件。
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from MusicFriend.Contracts.ProtocolModels import HelloPayload, TrackUpdatePayload
from MusicFriend.Server.RoomRepository import RoomRepository
from MusicFriend.Server.RoomService import RoomService, buildSnapshotDto, startCleanupTask

DEFAULT_ROOM_ID = "default"

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

    @app.get("/rooms/{room_id}/snapshot")
    async def httpSnapshot(room_id: str) -> dict:
        return buildSnapshotDto(_repo, room_id).model_dump()

    @app.websocket("/ws/room/{room_id}")
    async def roomWebsocket(websocket: WebSocket, room_id: str) -> None:
        await websocket.accept()
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
                    )
                elif mtype == "ping" and member_id:
                    await _room_service.handlePing(member_id)
                    await _room_service.sendPong(member_id)
                elif mtype == "hello":
                    continue
        except WebSocketDisconnect:
            pass
        finally:
            if member_id:
                await _room_service.unregisterMember(member_id)

    return app
