"""
Waveform Synthesis Service
===========================
PM2200 provides RMS values, not instantaneous waveforms.
This service synthesizes sine waves from RMS + phase angles
for real-time display on the frontend.
"""

import math
import numpy as np
from typing import Dict, List

from config import app_config
from services.modbus import MeterReading


# Number of points per waveform (3 cycles at 50 Hz)
NUM_CYCLES = 3
POINTS_PER_CYCLE = 100
TOTAL_POINTS = NUM_CYCLES * POINTS_PER_CYCLE


def synthesize_waveforms(hv: MeterReading, lv: MeterReading) -> dict:
    """
    Generate sine wave arrays from RMS values and phase angles.

    Returns dict with waveform arrays for:
    - HV & LV line-line voltages (V_AB, V_BC, V_CA)
    - HV & LV line currents (I_A, I_B, I_C)
    - HV & LV neutral current (I_N)

    Each array has TOTAL_POINTS elements representing NUM_CYCLES of 50Hz.
    """
    freq = hv.frequency if hv.frequency > 0 else 50.0
    period = 1.0 / freq
    total_time = NUM_CYCLES * period

    t = np.linspace(0, total_time, TOTAL_POINTS, endpoint=False)
    omega = 2 * math.pi * freq

    result = {
        "time_ms": (t * 1000).tolist(),  # Time axis in milliseconds
        "hv": _build_side_waveforms(t, omega, hv, "hv"),
        "lv": _build_side_waveforms(t, omega, lv, "lv"),
    }

    return result


def _build_side_waveforms(t: np.ndarray, omega: float, reading: MeterReading, side: str) -> dict:
    """Build all waveforms for one side (HV or LV)."""

    sqrt2 = math.sqrt(2)

    # ── Voltage waveforms (Line-Line) ──
    # V_AB: reference angle = angle_v1 (phase A leads)
    # For Dd connection: line voltage = phase voltage
    # V_AB ≈ V_AN - V_BN → phase angle is avg of A-B shifted by 30°
    # Simplified: use measured VLL with standard phase angles

    v_angles = [0, -120, 120]  # Standard 3-phase voltage angles

    v_ab = reading.voltage_ab * sqrt2 * np.sin(omega * t + np.radians(v_angles[0] + 30))
    v_bc = reading.voltage_bc * sqrt2 * np.sin(omega * t + np.radians(v_angles[1] + 30))
    v_ca = reading.voltage_ca * sqrt2 * np.sin(omega * t + np.radians(v_angles[2] + 30))

    # ── Current waveforms (Line) ──
    i_a = reading.current_a * sqrt2 * np.sin(omega * t + np.radians(reading.angle_i1))
    i_b = reading.current_b * sqrt2 * np.sin(omega * t + np.radians(reading.angle_i2))
    i_c = reading.current_c * sqrt2 * np.sin(omega * t + np.radians(reading.angle_i3))

    # ── Neutral current ──
    # IN is typically not sinusoidal; approximate as residual
    i_n = reading.current_n * sqrt2 * np.sin(omega * t)  # Simplified

    return {
        "voltage_ll": {
            "ab": np.round(v_ab, 2).tolist(),
            "bc": np.round(v_bc, 2).tolist(),
            "ca": np.round(v_ca, 2).tolist(),
        },
        "current_l": {
            "a": np.round(i_a, 4).tolist(),
            "b": np.round(i_b, 4).tolist(),
            "c": np.round(i_c, 4).tolist(),
        },
        "current_n": np.round(i_n, 4).tolist(),
    }


def get_phasor_data(hv: MeterReading, lv: MeterReading) -> dict:
    """
    Return phasor magnitudes and angles for phasor diagram display.
    """
    return {
        "hv": {
            "voltage": [
                {"phase": "A", "magnitude": hv.voltage_an, "angle": hv.angle_v1},
                {"phase": "B", "magnitude": hv.voltage_bn, "angle": hv.angle_v2},
                {"phase": "C", "magnitude": hv.voltage_cn, "angle": hv.angle_v3},
            ],
            "current": [
                {"phase": "A", "magnitude": hv.current_a, "angle": hv.angle_i1},
                {"phase": "B", "magnitude": hv.current_b, "angle": hv.angle_i2},
                {"phase": "C", "magnitude": hv.current_c, "angle": hv.angle_i3},
            ],
        },
        "lv": {
            "voltage": [
                {"phase": "A", "magnitude": lv.voltage_an, "angle": lv.angle_v1},
                {"phase": "B", "magnitude": lv.voltage_bn, "angle": lv.angle_v2},
                {"phase": "C", "magnitude": lv.voltage_cn, "angle": lv.angle_v3},
            ],
            "current": [
                {"phase": "A", "magnitude": lv.current_a, "angle": lv.angle_i1},
                {"phase": "B", "magnitude": lv.current_b, "angle": lv.angle_i2},
                {"phase": "C", "magnitude": lv.current_c, "angle": lv.angle_i3},
            ],
        },
    }
