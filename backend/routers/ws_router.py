"""WebSocket Router — Real-time data streaming"""

import asyncio
import json
import time
import logging
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.modbus import modbus_service
from services.relay import relay_service
from services.waveform import synthesize_waveforms, get_phasor_data

logger = logging.getLogger(__name__)
router = APIRouter()

# Active WebSocket connections
_connections: Set[WebSocket] = set()


@router.websocket("/ws/realtime")
async def websocket_realtime(websocket: WebSocket):
    """
    Real-time data WebSocket endpoint.
    Streams meter readings, relay status, and waveforms at ~2-3Hz.
    """
    await websocket.accept()
    _connections.add(websocket)
    logger.info(f"WebSocket connected ({len(_connections)} total)")

    try:
        while True:
            # Run relay pipeline (detection → protection)
            relay_service.process(
                modbus_service.hv_reading,
                modbus_service.lv_reading,
            )

            # Build payload
            payload = {
                "timestamp": time.time(),
                "mode": "simulation" if modbus_service._simulation else "real",
                "port": modbus_service.current_port,
                "meters": {
                    "hv": modbus_service.hv_reading.to_dict(),
                    "lv": modbus_service.lv_reading.to_dict(),
                },
                "relay": relay_service.relay_status.to_dict(),
                "waveforms": synthesize_waveforms(
                    modbus_service.hv_reading,
                    modbus_service.lv_reading,
                ),
                "phasors": get_phasor_data(
                    modbus_service.hv_reading,
                    modbus_service.lv_reading,
                ),
            }

            await websocket.send_json(payload)
            await asyncio.sleep(0.4)  # ~2.5 updates per second

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        _connections.discard(websocket)
        logger.info(f"WebSocket disconnected ({len(_connections)} remaining)")
