"""Relay Configuration & Control REST API Router"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from services.relay import relay_service
from services.case_match import get_baseline_overview, match_meter_to_baseline
from services.detector import detect_vector_group, detect_vector_group_shared_vref
from services.modbus import modbus_service
from services.display import esp_display_service
from config import app_config, TAP_TABLE

router = APIRouter(prefix="/api/relay", tags=["relay"])


class RelayConfigUpdate(BaseModel):
    i_pickup: Optional[float] = None
    slope1: Optional[float] = None
    slope2: Optional[float] = None
    bias_breakpoint: Optional[float] = None
    inrush_block_ms: Optional[int] = None
    trip_enabled: Optional[bool] = None
    auto_reset: Optional[bool] = None
    reset_delay_ms: Optional[int] = None
    filter_zero_seq_hv: Optional[bool] = None
    filter_zero_seq_lv: Optional[bool] = None


class TransformerConfigUpdate(BaseModel):
    equipment_mode: Optional[str] = None
    kva: Optional[float] = None
    detection_mode: Optional[str] = None
    vector_group: Optional[str] = None
    tap_position: Optional[int] = None
    autotransformer_turns_ratio: Optional[float] = None
    ct_ratio_hv: Optional[float] = None
    ct_ratio_lv: Optional[float] = None
    current_base_hv_secondary: Optional[float] = None
    current_base_lv_secondary: Optional[float] = None


AUTOTRANSFORMER_TEST_PRESET = {
    "transformer": {
        "equipment_mode": "autotransformer",
        "detection_mode": "auto_family",
        "tap_position": 1,
        "autotransformer_turns_ratio": 2.0,
        "ct_ratio_hv": 1.0,
        "ct_ratio_lv": 1.0,
    },
    "relay": {
        "trip_enabled": False,
        "auto_reset": True,
        "reset_delay_ms": 1500,
    },
    "notes": [
        "The backend will auto-classify DD/DY/YD/YY from live voltages.",
        "Keep HV CT on meter #1 and LV CT on meter #2.",
        "Autotransformer mode uses a fixed line-current ratio of 2:1 for referred current.",
        "The dashboard shows raw current and referred current separately.",
    ],
}


@router.get("/status")
async def get_relay_status():
    """Get current relay status with differential currents."""
    return relay_service.relay_status.to_dict()


@router.post("/reset")
async def reset_relay():
    """Manual reset of trip latch."""
    relay_service.manual_reset()
    return {"success": True, "status": relay_service.relay_status.status}


@router.get("/config")
async def get_config():
    """Get all relay and transformer configuration."""
    tx = app_config.transformer
    return {
        "transformer": {
            "equipment_mode": tx.equipment_mode,
            "kva": tx.kva,
            "detection_mode": tx.detection_mode,
            "vector_group": tx.vector_group,
            "tap_position": tx.tap_position,
            "autotransformer_turns_ratio": tx.autotransformer_turns_ratio,
            "v_hv": tx.v_hv,
            "v_lv": tx.v_lv,
            "i_rated_hv": round(tx.i_rated_hv, 2),
            "i_rated_lv": round(tx.i_rated_lv, 2),
            "nameplate_i_hv": round(tx.nameplate_i_hv, 2),
            "nameplate_i_lv": round(tx.nameplate_i_lv, 2),
            "ct_ratio_hv": tx.ct_ratio_hv,
            "ct_ratio_lv": tx.ct_ratio_lv,
            "current_base_hv_secondary": tx.current_base_hv_secondary,
            "current_base_lv_secondary": tx.current_base_lv_secondary,
            "phase_shift_deg": tx.phase_shift_deg,
            "taps": tx.get_all_taps(),
        },
        "modbus": app_config.modbus.model_dump(),
        "relay": app_config.relay.model_dump(),
    }


@router.put("/config/relay")
async def update_relay_config(update: RelayConfigUpdate):
    """Update relay protection settings."""
    for field, value in update.model_dump(exclude_none=True).items():
        setattr(app_config.relay, field, value)
    return {"success": True, "relay": app_config.relay.model_dump()}


@router.put("/config/transformer")
async def update_transformer_config(update: TransformerConfigUpdate):
    """Update transformer settings (vector group, tap, CT ratios)."""
    for field, value in update.model_dump(exclude_none=True).items():
        setattr(app_config.transformer, field, value)

    # Auto-update zero-seq filters based on vector group
    app_config.update_zero_seq_filters()

    tx = app_config.transformer
    return {
        "success": True,
        "transformer": {
            "equipment_mode": tx.equipment_mode,
            "kva": tx.kva,
            "detection_mode": tx.detection_mode,
            "vector_group": tx.vector_group,
            "tap_position": tx.tap_position,
            "autotransformer_turns_ratio": tx.autotransformer_turns_ratio,
            "current_base_hv_secondary": tx.current_base_hv_secondary,
            "current_base_lv_secondary": tx.current_base_lv_secondary,
            "v_hv": tx.v_hv,
            "v_lv": tx.v_lv,
            "i_rated_hv": round(tx.i_rated_hv, 2),
            "i_rated_lv": round(tx.i_rated_lv, 2),
            "nameplate_i_hv": round(tx.nameplate_i_hv, 2),
            "nameplate_i_lv": round(tx.nameplate_i_lv, 2),
        },
    }


@router.post("/presets/autotransformer-test")
async def apply_autotransformer_test_preset():
    """Apply a fast-start preset for the autotransformer lab setup."""
    hv_base = app_config.transformer.i_rated_hv_secondary
    lv_base = app_config.transformer.i_rated_lv_secondary
    for field, value in AUTOTRANSFORMER_TEST_PRESET["transformer"].items():
        setattr(app_config.transformer, field, value)
    app_config.transformer.current_base_hv_secondary = hv_base
    app_config.transformer.current_base_lv_secondary = lv_base
    for field, value in AUTOTRANSFORMER_TEST_PRESET["relay"].items():
        setattr(app_config.relay, field, value)

    app_config.update_zero_seq_filters()
    relay_service.re_detect()

    return {
        "success": True,
        "preset": "autotransformer_test",
        "notes": AUTOTRANSFORMER_TEST_PRESET["notes"],
        "transformer": {
            "equipment_mode": app_config.transformer.equipment_mode,
            "kva": app_config.transformer.kva,
            "detection_mode": app_config.transformer.detection_mode,
            "vector_group": app_config.transformer.vector_group,
            "tap_position": app_config.transformer.tap_position,
            "autotransformer_turns_ratio": app_config.transformer.autotransformer_turns_ratio,
            "ct_ratio_hv": app_config.transformer.ct_ratio_hv,
            "ct_ratio_lv": app_config.transformer.ct_ratio_lv,
            "current_base_hv_secondary": app_config.transformer.current_base_hv_secondary,
            "current_base_lv_secondary": app_config.transformer.current_base_lv_secondary,
        },
        "relay": {
            "trip_enabled": app_config.relay.trip_enabled,
            "auto_reset": app_config.relay.auto_reset,
            "reset_delay_ms": app_config.relay.reset_delay_ms,
        },
    }


@router.post("/detect-vector-group")
async def auto_detect_vector_group():
    """Auto-detect vector group from live voltage measurements (ratio method)."""
    if app_config.transformer.detection_mode == "manual_confirmed":
        return {
            "detected": False,
            "method": "manual_confirmed",
            "vector_group": app_config.transformer.vector_group,
            "tap_position": app_config.transformer.tap_position,
            "reason": "manual_confirmed mode uses operator-selected compensation",
        }
    result = relay_service._resolve_active_group(modbus_service.hv_reading, modbus_service.lv_reading)
    if result["detected"]:
        app_config.transformer.vector_group = result["vector_group"]
        app_config.transformer.tap_position = result["tap_position"]
        app_config.update_zero_seq_filters()
    return result


@router.post("/detect-vector-group/shared-vref")
async def detect_vg_shared_vref():
    """Detect vector group using shared V_HV reference + current angles.
    REQUIRES: Both meters wired to same HV PT, separate CTs."""
    if app_config.transformer.detection_mode == "manual_confirmed":
        return {
            "detected": False,
            "method": "manual_confirmed",
            "vector_group": app_config.transformer.vector_group,
            "tap_position": app_config.transformer.tap_position,
            "reason": "manual_confirmed mode uses operator-selected compensation",
        }
    result = detect_vector_group_shared_vref(
        modbus_service.hv_reading, modbus_service.lv_reading
    )
    if result.get("detected"):
        app_config.transformer.vector_group = result["vector_group"]
        if "tap_position" in result:
            app_config.transformer.tap_position = result["tap_position"]
        app_config.update_zero_seq_filters()
    return result


@router.post("/re-detect")
async def re_detect():
    """Trigger re-detection of vector group (e.g., after tap change or rewiring).
    The pipeline will re-run detection before resuming protection."""
    relay_service.re_detect()
    return {
        "success": True,
        "system_phase": relay_service.relay_status.system_phase,
    }


@router.get("/bias-characteristic")
async def get_bias_characteristic():
    """Get bias characteristic curve data for plotting."""
    return relay_service.get_bias_characteristic()


@router.post("/esp-display/test")
async def test_esp_display(message: str = "HELLO"):
    """Send a test message to the ESP Wi-Fi display."""
    success = await esp_display_service.show_test_message(message)
    return {
        "success": success,
        "message": message,
        "target": esp_display_service.base_url,
    }


@router.get("/taps")
async def get_tap_table():
    """Get full tap table."""
    return {
        "current_tap": app_config.transformer.tap_position,
        "current_vector_group": app_config.transformer.vector_group,
        "taps": app_config.transformer.get_all_taps(),
    }


@router.get("/lab-baseline")
async def get_lab_baseline_overview():
    """Get summary metadata for the committed Hioki lab baseline."""
    return get_baseline_overview()


@router.get("/lab-baseline/match")
async def match_live_meter_to_lab_baseline(source: str = "hv", top_n: int = 5):
    """Match current live meter data against the committed lab baseline cases."""
    source_key = source.lower()
    if source_key == "hv":
        reading = modbus_service.hv_reading
    elif source_key == "lv":
        reading = modbus_service.lv_reading
    else:
        return {"success": False, "reason": "source must be 'hv' or 'lv'"}

    return {
        "success": True,
        "source": source_key,
        **match_meter_to_baseline(reading, top_n=top_n),
    }
