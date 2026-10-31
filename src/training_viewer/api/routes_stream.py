"""服务器发送事件（SSE）实时更新通道。

只推送“哪个版本发生变化、哪些运行有更新”的轻量消息；前端收到后按需拉取
指标与产物，避免把全部历史数据塞进事件流。断线后前端重新建立连接并重新查询。
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/v1")


@router.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    service = request.app.state.service
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    loop = asyncio.get_running_loop()
    service.subscribe(loop, queue)

    async def event_generator():
        yield "retry: 3000\n\n"
        yield f"event: ready\ndata: {json.dumps({'version': service.version})}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"event: update\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        finally:
            service.unsubscribe(loop, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
