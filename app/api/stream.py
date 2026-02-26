


import asyncio
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()


async def event_generator(queue: asyncio.Queue):
    while True:
        try: 
            event = await queue.get()
            yield f"data: {event}\n\n"
        except asyncio.CancelledError:
            break

@router.get("/devices/events/stream")
async def stream_all():
    q = await boardcaster.subscribe(None)
    return StreamingResponse(event_generator(q), media_type="text/event-stream")