"""
Differential Relay Protection System - FastAPI Backend
======================================================
Main application entry point.
  - Serves REST API for configuration and status
  - WebSocket for real-time data streaming
  - Starts in real mode, but leaves COM ports untouched until explicit connect
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.modbus import modbus_service
from services.display import esp_display_service
from routers import modbus_router, relay_router, ws_router


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the API in real mode without auto-opening serial ports."""
    logger.info("=" * 60)
    logger.info("  Differential Relay Protection System")
    logger.info("  Tirathai 15kVA Transformer (Dd0 / YNyn0)")
    logger.info("=" * 60)

    modbus_service._simulation = False
    await modbus_service.start_polling()
    logger.info("Polling started (REAL / DISCONNECTED)")

    yield

    logger.info("Shutting down...")
    await modbus_service.stop_polling()
    await modbus_service.disconnect()
    await esp_display_service.shutdown()


app = FastAPI(
    title="Differential Relay Protection",
    description="Real-time transformer differential relay monitoring system",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(modbus_router.router)
app.include_router(relay_router.router)
app.include_router(ws_router.router)


@app.get("/")
async def root():
    return {
        "name": "Differential Relay Protection System",
        "version": "1.0.0",
        "status": "running",
        "meters_connected": modbus_service.is_connected,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
