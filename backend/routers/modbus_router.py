"""Modbus REST API Router"""

from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel

from services.modbus import modbus_service, scan_com_ports, scan_candidate_com_ports
from config import app_config

router = APIRouter(prefix="/api/modbus", tags=["modbus"])


class ConnectRequest(BaseModel):
    port: Optional[str] = None  # None or "auto" → auto-detect


class ModbusConfigUpdate(BaseModel):
    port: Optional[str] = None
    baudrate: Optional[int] = None
    parity: Optional[str] = None
    stopbits: Optional[int] = None
    bytesize: Optional[int] = None
    timeout: Optional[float] = None
    poll_interval_ms: Optional[int] = None
    hv_meter_address: Optional[int] = None
    lv_meter_address: Optional[int] = None


@router.get("/status")
async def get_modbus_status():
    """Get connection status of both meters."""
    return {
        "connected": modbus_service.is_connected,
        "port": modbus_service.current_port,
        "hv_meter": {
            "port": modbus_service.current_port,
            "address": app_config.modbus.hv_meter_address,
            "connected": modbus_service.hv_reading.connected,
            "last_update": modbus_service.hv_reading.timestamp,
        },
        "lv_meter": {
            "port": modbus_service.current_port,
            "address": app_config.modbus.lv_meter_address,
            "connected": modbus_service.lv_reading.connected,
            "last_update": modbus_service.lv_reading.timestamp,
        },
    }


@router.get("/ports")
async def list_ports():
    """List available COM ports."""
    ports = await scan_candidate_com_ports()
    all_ports = await scan_com_ports()
    return {"ports": ports, "all_ports": all_ports}


@router.get("/config")
async def get_modbus_config():
    """Get current Modbus communication settings."""
    return app_config.modbus.model_dump()


@router.put("/config")
async def update_modbus_config(update: ModbusConfigUpdate):
    """Update Modbus communication settings."""
    payload = update.model_dump(exclude_none=True)
    payload.pop("hv_meter_address", None)
    payload.pop("lv_meter_address", None)
    for field, value in update.model_dump(exclude_none=True).items():
        if field in {"hv_meter_address", "lv_meter_address"}:
            continue
        setattr(app_config.modbus, field, value)
    app_config.modbus.hv_meter_address = 1
    app_config.modbus.lv_meter_address = 2
    return {"success": True, "modbus": app_config.modbus.model_dump()}


@router.post("/connect")
async def connect(req: ConnectRequest):
    """Connect to Modbus serial port."""
    await modbus_service.stop_polling()
    success = await modbus_service.connect(
        port=req.port or "auto"
    )
    if success:
        await modbus_service.start_polling()
        return {
            "success": True,
            "port": modbus_service.current_port,
        }
    raise HTTPException(
        status_code=500,
        detail=modbus_service.last_connect_error or "Failed to connect",
    )


@router.post("/disconnect")
async def disconnect():
    """Disconnect from Modbus."""
    await modbus_service.stop_polling()
    await modbus_service.disconnect()
    return {"success": True}


@router.get("/readings/hv")
async def get_hv_readings():
    """Get latest HV meter readings."""
    return modbus_service.hv_reading.to_dict()


@router.get("/readings/lv")
async def get_lv_readings():
    """Get latest LV meter readings."""
    return modbus_service.lv_reading.to_dict()


@router.get("/mode")
async def get_mode():
    """Get current operating mode (simulation or real)."""
    return {
        "mode": "simulation" if modbus_service._simulation else "real",
        "connected": modbus_service.is_connected,
        "port": modbus_service.current_port,
    }


@router.post("/mode/simulation")
async def set_simulation_mode():
    """Switch to simulation mode (no hardware needed)."""
    await modbus_service.stop_polling()
    await modbus_service.disconnect()
    modbus_service._simulation = True
    await modbus_service.connect()
    await modbus_service.start_polling()
    return {"success": True, "mode": "simulation"}


@router.post("/mode/real")
async def set_real_mode(req: ConnectRequest = ConnectRequest()):
    """Switch to real hardware mode. Optionally specify port.
    If hardware not found, stays in real mode with not-connected status (shows zeros)."""
    try:
        await modbus_service.stop_polling()
        await modbus_service.disconnect()
        modbus_service._simulation = False
        success = await modbus_service.connect(
            port=req.port or "auto",
        )
        await modbus_service.start_polling()
        return {
            "success": True,
            "mode": "real",
            "connected": success,
            "port": modbus_service.current_port if success else None,
            "message": "Connected to hardware" if success else "Hardware not found — showing zeros. Plug in meter and retry.",
        }
    except Exception as e:
        # Even if something crashes, stay in real mode (not-connected)
        modbus_service._simulation = False
        modbus_service._connected = False
        modbus_service._reset_readings()
        await modbus_service.start_polling()
        return {
            "success": True,
            "mode": "real",
            "connected": False,
            "port": None,
            "message": f"Error: {e} — showing zeros.",
        }


class FaultInjectRequest(BaseModel):
    phases: Optional[list] = ["A", "B", "C"]
    factor: Optional[float] = 3.0
    side: Optional[str] = "lv"


@router.post("/fault/inject")
async def inject_fault(req: FaultInjectRequest):
    """Inject a simulated fault (simulation mode only)."""
    if not modbus_service._simulation:
        raise HTTPException(400, "Fault injection only works in simulation mode")
    modbus_service.inject_fault(
        phases=req.phases, factor=req.factor, side=req.side
    )
    return {
        "success": True,
        "fault": modbus_service._fault_inject,
    }


@router.post("/fault/clear")
async def clear_fault():
    """Clear injected fault."""
    modbus_service.clear_fault()
    return {"success": True, "fault": modbus_service._fault_inject}


@router.get("/fault")
async def get_fault_status():
    """Get current fault injection status."""
    return modbus_service._fault_inject
