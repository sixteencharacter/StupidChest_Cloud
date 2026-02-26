# so this is basically the traffic controller for the SSE stream

import asyncio
import logging
from typing import Dict,Set,Any

logger = logging.getLogger(__name__)

class Broadcaster: 
    def __init__(self, max_queue_size: int = 100):
        self.max_queue_size = max_queue_size
        self.sub_device: Dict[str,Set[asyncio.Queue]] = {}
        self.sub_all: Set[asyncio.Queue] = set()

    # Subscribe a queue to a specific device_id or to all devices if device_id is None
    async def subscribe(self, device_id: str | None, queue: asyncio.Queue):
        if device_id:
            if device_id not in self.sub_device:
                self.sub_device[device_id] = set()
            self.sub_device[device_id].add(queue)
        else:
            self.sub_all.add(queue)

    # Unsubscribe a queue from a specific device_id or from all devices if device_id is None
    async def unsubscribe(self, device_id: str | None, queue: asyncio.Queue):
        if device_id:
            if device_id in self.sub_device:
                self.sub_device[device_id].discard(queue)
        else:
            self.sub_all.discard(queue)

    async def boardcast(self, msg:Any):
        targets = set(self.sub_all)

        for q in targets:
            if q.full():
                try:
                    _ = q.get_nowait()
                except asyncio.QueueEmpty:
                    logger.warning("Queue full but empty on get_nowait")
                    pass
            try: 
                q.put_nowait(msg)
            except asyncio.QueueFull:
                logger.warning("Queue full on put_nowait despite prior check")

boardcaster = Broadcaster()

            